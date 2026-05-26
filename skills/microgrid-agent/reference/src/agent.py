"""Main agent runtime: perceive -> predict -> optimize -> actuate loop.

Reads sensors, runs forecasts every 15 minutes, runs LP dispatch every 5 seconds,
and logs every decision. Falls back to rule-based control if ML/LP fails.
"""

from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .autonomic import AutonomicController, SafetyConfig
from .dashboard import DashboardServer
from .devices import DeviceRegistry, DeviceReading, DeviceStatus
from .dispatch import Dispatcher, DispatchConfig, DispatchDecision, MicrogridState
from .forecast import Forecaster, ForecastResult
from .knowledge import KnowledgeGraph
from .sync import SyncDaemon

log = logging.getLogger(__name__)

# Ring buffer size for historical readings
HISTORY_SIZE = 2880  # 48 hours at 1-minute resolution


@dataclass
class AgentConfig:
    site_id: str = "site-001"
    dispatch_interval_s: float = 5.0
    forecast_interval_s: float = 900.0  # 15 minutes
    sensor_interval_s: float = 1.0
    metrics_publish_interval_s: float = 60.0

    # Battery
    battery_capacity_kwh: float = 10.0
    battery_max_charge_kw: float = 5.0
    battery_max_discharge_kw: float = 5.0
    initial_soc_pct: float = 50.0

    # Diesel
    diesel_max_kw: float = 5.0
    diesel_min_kw: float = 1.0

    # Dashboard
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8080

    # MQTT
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None

    # Paths
    data_dir: Path = Path("data")
    config_dir: Path = Path("config")
    db_path: Path = Path("data/knowledge.db")
    model_dir: Path = Path("data/models")
    sync_queue_dir: Path = Path("data/sync-queue")


class MicrogridAgent:
    """Core agent that runs the perceive-predict-optimize-actuate loop."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self._start_time = time.time()
        self._running = False

        # State
        self._soc_pct = config.initial_soc_pct
        self._diesel_running = False
        self._history_gen = collections.deque(maxlen=HISTORY_SIZE)
        self._history_demand = collections.deque(maxlen=HISTORY_SIZE)
        self._event_journal: list[dict[str, Any]] = []
        self._latest_readings: dict[str, DeviceReading] = {}

        # Subsystems
        self.devices = DeviceRegistry()
        self.forecaster = Forecaster(config.model_dir)
        self.dispatcher = Dispatcher(DispatchConfig(
            dispatch_interval_s=config.dispatch_interval_s,
            min_soc_pct=20.0,
            max_soc_pct=95.0,
        ))
        self.safety = AutonomicController(SafetyConfig())
        self.knowledge = KnowledgeGraph(config.db_path)
        self.sync = SyncDaemon(
            site_id=config.site_id,
            broker_host=config.mqtt_broker,
            broker_port=config.mqtt_port,
            queue_dir=config.sync_queue_dir,
            username=config.mqtt_username,
            password=config.mqtt_password,
        )
        self.dashboard = DashboardServer(self, config.dashboard_host, config.dashboard_port)

        # Latest results (exposed to dashboard)
        self.last_forecast: ForecastResult | None = None
        self.last_dispatch: DispatchDecision | None = None

    async def start(self):
        """Initialize all subsystems and start the main loops."""
        log.info("Starting microgrid agent for site %s", self.config.site_id)
        self._running = True

        # Load device config
        devices_toml = self.config.config_dir / "devices.toml"
        if devices_toml.exists():
            self.devices.load_config(devices_toml)
        else:
            log.warning("No devices.toml found at %s, using empty registry", devices_toml)

        # Open knowledge graph
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        await self.knowledge.open()

        # Start subsystems
        await self.sync.start()
        await self.dashboard.start()

        # Register MQTT handlers
        self.sync.on("model-update", self._handle_model_update)
        self.sync.on("config-change", self._handle_config_change)
        self.sync.on("fleet/alerts", self._handle_fleet_alert)

        # Notify systemd we're ready
        self._notify_systemd("READY=1")

        self._log_event("agent_start", {"site_id": self.config.site_id})

        # Launch concurrent loops
        await asyncio.gather(
            self._sensor_loop(),
            self._dispatch_loop(),
            self._forecast_loop(),
            self._metrics_loop(),
            self._watchdog_loop(),
        )

    async def stop(self):
        """Graceful shutdown."""
        log.info("Stopping microgrid agent")
        self._running = False
        self._log_event("agent_stop", {})
        await self.dashboard.stop()
        await self.sync.stop()
        await self.knowledge.close()
        self._notify_systemd("STOPPING=1")

    # ── Main loops ──────────────────────────────────────────────

    async def _sensor_loop(self):
        """Read all sensors at the configured interval."""
        while self._running:
            try:
                self._latest_readings = await self.devices.read_all()

                # Aggregate generation and demand
                gen_kw = sum(
                    r.power_kw for d_id, r in self._latest_readings.items()
                    if self.devices.get(d_id) and self.devices.get(d_id).device_type in ("solar", "wind")
                )
                demand_kw = sum(
                    r.power_kw for d_id, r in self._latest_readings.items()
                    if self.devices.get(d_id) and self.devices.get(d_id).device_type == "load"
                )

                self._history_gen.append(gen_kw)
                self._history_demand.append(demand_kw)

                # Update knowledge graph with load observations
                for d_id, reading in self._latest_readings.items():
                    device = self.devices.get(d_id)
                    if device and device.device_type == "load":
                        await self.knowledge.update_load_observation(d_id, reading.power_kw)
                        hour = time.localtime().tm_hour
                        await self.knowledge.update_hourly_pattern(d_id, hour, reading.power_kw)

            except Exception as e:
                log.error("Sensor loop error: %s", e)

            await asyncio.sleep(self.config.sensor_interval_s)

    async def _dispatch_loop(self):
        """Run dispatch optimization every N seconds."""
        while self._running:
            try:
                state = self._build_microgrid_state()
                decision = self.dispatcher.dispatch(state)

                # Safety enforcement
                decision, overrides = self.safety.enforce(decision, state)

                # Update internal state
                self._soc_pct = decision.soc_pct
                self._diesel_running = decision.diesel_kw > 0

                # Actuate devices
                await self._actuate(decision)

                self.last_dispatch = decision
                self._log_event("dispatch", decision.to_dict())

                if overrides:
                    await self.sync.publish_event("safety_override", {
                        "overrides": [
                            {"field": o.field_name, "original": o.original_value,
                             "corrected": o.corrected_value, "reason": o.reason}
                            for o in overrides
                        ]
                    })

            except Exception as e:
                log.error("Dispatch loop error: %s", e)
                # Use last-known-good from safety controller
                fallback = self.safety.get_fallback_dispatch()
                if fallback:
                    self.last_dispatch = fallback
                    log.info("Using fallback dispatch decision")

            await asyncio.sleep(self.config.dispatch_interval_s)

    async def _forecast_loop(self):
        """Run ML forecast every 15 minutes."""
        while self._running:
            try:
                gen_arr = np.array(list(self._history_gen)) if self._history_gen else np.array([0.0])
                dem_arr = np.array(list(self._history_demand)) if self._history_demand else np.array([0.0])

                self.last_forecast = await self.forecaster.forecast(gen_arr, dem_arr)
                self._log_event("forecast", {
                    "model": self.last_forecast.model_version,
                    "steps": self.last_forecast.steps,
                    "avg_gen": float(np.mean(self.last_forecast.generation_kw)),
                    "avg_dem": float(np.mean(self.last_forecast.demand_kw)),
                })
                log.info(
                    "Forecast updated (model=%s): avg_gen=%.2f kW, avg_dem=%.2f kW",
                    self.last_forecast.model_version,
                    np.mean(self.last_forecast.generation_kw),
                    np.mean(self.last_forecast.demand_kw),
                )
            except Exception as e:
                log.error("Forecast loop error: %s", e)

            await asyncio.sleep(self.config.forecast_interval_s)

    async def _metrics_loop(self):
        """Publish metrics to fleet sync."""
        while self._running:
            try:
                metrics = self.get_state_snapshot()
                await self.sync.publish_metrics(metrics)
            except Exception as e:
                log.error("Metrics publish error: %s", e)
            await asyncio.sleep(self.config.metrics_publish_interval_s)

    async def _watchdog_loop(self):
        """Send systemd watchdog pings."""
        while self._running:
            self.safety.ping_watchdog()
            await asyncio.sleep(self.safety.config.watchdog_interval_s)

    # ── Internal methods ────────────────────────────────────────

    def _build_microgrid_state(self) -> MicrogridState:
        solar_kw = sum(
            r.power_kw for d_id, r in self._latest_readings.items()
            if self.devices.get(d_id) and self.devices.get(d_id).device_type in ("solar", "wind")
        )
        demand_kw = sum(
            r.power_kw for d_id, r in self._latest_readings.items()
            if self.devices.get(d_id) and self.devices.get(d_id).device_type == "load"
        )
        return MicrogridState(
            solar_available_kw=solar_kw,
            demand_kw=demand_kw,
            battery_soc_pct=self._soc_pct,
            battery_capacity_kwh=self.config.battery_capacity_kwh,
            battery_max_charge_kw=self.config.battery_max_charge_kw,
            battery_max_discharge_kw=self.config.battery_max_discharge_kw,
            diesel_max_kw=self.config.diesel_max_kw,
            diesel_min_kw=self.config.diesel_min_kw,
            diesel_running=self._diesel_running,
            priority_loads_kw=0.0,  # populated from KG at runtime
        )

    async def _actuate(self, decision: DispatchDecision):
        """Send commands to physical devices based on dispatch decision."""
        # Set diesel generator
        for device in self.devices.by_type("diesel"):
            try:
                if decision.diesel_kw > 0:
                    await device.start()
                    await device.set_power_limit(decision.diesel_kw)
                else:
                    await device.stop()
            except Exception as e:
                log.error("Failed to actuate diesel %s: %s", device.device_id, e)

        # Set battery charge/discharge
        for device in self.devices.by_type("battery"):
            try:
                await device.set_power_limit(abs(decision.battery_kw))
            except Exception as e:
                log.error("Failed to actuate battery %s: %s", device.device_id, e)

    def _log_event(self, event_type: str, data: dict[str, Any]):
        event = {
            "timestamp": time.time(),
            "type": event_type,
            "data": data,
        }
        self._event_journal.append(event)
        # Keep journal bounded
        if len(self._event_journal) > 10000:
            self._event_journal = self._event_journal[-5000:]

    def _notify_systemd(self, message: str):
        notify_socket = os.environ.get("NOTIFY_SOCKET")
        if not notify_socket:
            return
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            if notify_socket.startswith("@"):
                notify_socket = "\0" + notify_socket[1:]
            sock.sendto(message.encode(), notify_socket)
            sock.close()
        except Exception as e:
            log.debug("systemd notify failed: %s", e)

    # ── Public API (for dashboard) ──────────────────────────────

    def get_state_snapshot(self) -> dict[str, Any]:
        d = self.last_dispatch
        uptime_s = time.time() - self._start_time
        hours, remainder = divmod(int(uptime_s), 3600)
        minutes, seconds = divmod(remainder, 60)

        return {
            "agent_status": "running" if self._running else "stopped",
            "site_id": self.config.site_id,
            "solar_kw": d.solar_kw if d else 0.0,
            "battery_kw": d.battery_kw if d else 0.0,
            "diesel_kw": d.diesel_kw if d else 0.0,
            "demand_kw": (d.solar_kw + d.battery_kw + d.diesel_kw - d.curtailed_kw + d.unserved_kw) if d else 0.0,
            "curtailed_kw": d.curtailed_kw if d else 0.0,
            "unserved_kw": d.unserved_kw if d else 0.0,
            "battery_soc_pct": self._soc_pct,
            "dispatch_method": d.method if d else None,
            "mqtt_connected": self.sync.is_connected,
            "sync_queue_depth": self.sync.queue_depth,
            "uptime": f"{hours}h {minutes}m {seconds}s",
            "timestamp": time.time(),
        }

    def get_history(self, limit: int = 100) -> list[dict]:
        return self._event_journal[-limit:]

    # ── MQTT handlers ───────────────────────────────────────────

    def _handle_model_update(self, topic: str, payload: dict):
        log.info("Received model update notification: %s", payload.get("model_name", "unknown"))
        # Forecaster will auto-detect new .tflite files on next cycle

    def _handle_config_change(self, topic: str, payload: dict):
        log.info("Received config change: %s", payload)
        self._log_event("config_change_received", payload)

    def _handle_fleet_alert(self, topic: str, payload: dict):
        log.warning("Fleet alert: %s", payload.get("message", "unknown"))
        self._log_event("fleet_alert", payload)
