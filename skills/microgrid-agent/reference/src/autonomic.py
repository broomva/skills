"""Safety controller that enforces hard constraints on all dispatch decisions.

Acts as the final gate before actuation. Overrides any decision that violates
safety limits. Logs all overrides for audit. Manages systemd watchdog pings.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

from .dispatch import DispatchDecision, MicrogridState

log = logging.getLogger(__name__)


@dataclass
class SafetyConfig:
    min_soc_pct: float = 15.0  # hard minimum (below dispatch optimizer's soft limit)
    max_soc_pct: float = 98.0
    max_diesel_continuous_hours: float = 8.0
    max_battery_charge_rate_c: float = 1.0  # max C-rate for charging
    max_battery_discharge_rate_c: float = 1.0
    max_unserved_before_diesel_start: float = 0.5  # kW
    diesel_cooldown_minutes: float = 5.0
    watchdog_interval_s: float = 15.0


@dataclass
class SafetyOverride:
    timestamp: float
    field_name: str
    original_value: float
    corrected_value: float
    reason: str


class AutonomicController:
    """Enforces hard safety constraints on dispatch decisions."""

    def __init__(self, config: SafetyConfig | None = None):
        self.config = config or SafetyConfig()
        self._overrides: list[SafetyOverride] = []
        self._diesel_start_time: float | None = None
        self._diesel_stop_time: float | None = None
        self._last_watchdog_ping: float = 0.0
        self._last_good_dispatch: DispatchDecision | None = None

    def enforce(
        self, decision: DispatchDecision, state: MicrogridState,
    ) -> tuple[DispatchDecision, list[SafetyOverride]]:
        """Apply all safety checks. Returns corrected decision + list of overrides."""
        overrides: list[SafetyOverride] = []
        now = time.time()

        # 1. SOC floor protection
        if decision.soc_pct < self.config.min_soc_pct and decision.battery_kw > 0:
            overrides.append(SafetyOverride(
                timestamp=now, field_name="battery_kw",
                original_value=decision.battery_kw, corrected_value=0.0,
                reason=f"SOC {decision.soc_pct:.1f}% below hard minimum {self.config.min_soc_pct}%",
            ))
            decision.battery_kw = 0.0
            decision.soc_pct = max(decision.soc_pct, self.config.min_soc_pct)

        # 2. SOC ceiling protection
        if decision.soc_pct > self.config.max_soc_pct and decision.battery_kw < 0:
            overrides.append(SafetyOverride(
                timestamp=now, field_name="battery_kw",
                original_value=decision.battery_kw, corrected_value=0.0,
                reason=f"SOC {decision.soc_pct:.1f}% above hard maximum {self.config.max_soc_pct}%",
            ))
            decision.battery_kw = 0.0

        # 3. Diesel continuous runtime limit
        if decision.diesel_kw > 0:
            if self._diesel_start_time is None:
                self._diesel_start_time = now
            runtime_hours = (now - self._diesel_start_time) / 3600.0
            if runtime_hours > self.config.max_diesel_continuous_hours:
                overrides.append(SafetyOverride(
                    timestamp=now, field_name="diesel_kw",
                    original_value=decision.diesel_kw, corrected_value=0.0,
                    reason=f"Diesel runtime {runtime_hours:.1f}h exceeds max {self.config.max_diesel_continuous_hours}h",
                ))
                decision.diesel_kw = 0.0
                self._diesel_stop_time = now
                self._diesel_start_time = None
        else:
            self._diesel_start_time = None

        # 4. Diesel cooldown
        if decision.diesel_kw > 0 and self._diesel_stop_time is not None:
            cooldown_elapsed = (now - self._diesel_stop_time) / 60.0
            if cooldown_elapsed < self.config.diesel_cooldown_minutes:
                overrides.append(SafetyOverride(
                    timestamp=now, field_name="diesel_kw",
                    original_value=decision.diesel_kw, corrected_value=0.0,
                    reason=f"Diesel cooldown: {cooldown_elapsed:.1f}min < {self.config.diesel_cooldown_minutes}min",
                ))
                decision.diesel_kw = 0.0

        # 5. Battery C-rate limits
        if state.battery_capacity_kwh > 0:
            max_discharge = self.config.max_battery_discharge_rate_c * state.battery_capacity_kwh
            if decision.battery_kw > max_discharge:
                overrides.append(SafetyOverride(
                    timestamp=now, field_name="battery_kw",
                    original_value=decision.battery_kw, corrected_value=max_discharge,
                    reason=f"Discharge {decision.battery_kw:.2f}kW exceeds {self.config.max_battery_discharge_rate_c}C rate",
                ))
                decision.battery_kw = max_discharge

            max_charge = self.config.max_battery_charge_rate_c * state.battery_capacity_kwh
            if decision.battery_kw < -max_charge:
                overrides.append(SafetyOverride(
                    timestamp=now, field_name="battery_kw",
                    original_value=decision.battery_kw, corrected_value=-max_charge,
                    reason=f"Charge {abs(decision.battery_kw):.2f}kW exceeds {self.config.max_battery_charge_rate_c}C rate",
                ))
                decision.battery_kw = -max_charge

        # 6. Auto-start diesel if unserved exceeds threshold
        if (decision.unserved_kw > self.config.max_unserved_before_diesel_start
                and decision.diesel_kw == 0
                and state.diesel_max_kw > 0):
            # Only suggest, don't override — this is logged as advisory
            log.warning(
                "Unserved load %.2f kW exceeds threshold %.2f kW, diesel should start",
                decision.unserved_kw, self.config.max_unserved_before_diesel_start,
            )

        # Log overrides
        for o in overrides:
            log.warning("SAFETY OVERRIDE: %s = %.3f -> %.3f (%s)",
                        o.field_name, o.original_value, o.corrected_value, o.reason)
            self._overrides.append(o)

        # Keep a last-known-good for graceful degradation
        self._last_good_dispatch = decision

        return decision, overrides

    def get_fallback_dispatch(self) -> DispatchDecision | None:
        """Return last-known-good dispatch for graceful degradation if agent crashes."""
        return self._last_good_dispatch

    def ping_watchdog(self):
        """Send systemd watchdog notification."""
        now = time.time()
        if now - self._last_watchdog_ping < self.config.watchdog_interval_s:
            return

        notify_socket = os.environ.get("NOTIFY_SOCKET")
        if notify_socket:
            try:
                import socket
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                if notify_socket.startswith("@"):
                    notify_socket = "\0" + notify_socket[1:]
                sock.sendto(b"WATCHDOG=1", notify_socket)
                sock.close()
            except Exception as e:
                log.debug("Watchdog ping failed: %s", e)

        self._last_watchdog_ping = now

    def recent_overrides(self, limit: int = 50) -> list[dict]:
        return [
            {
                "timestamp": o.timestamp,
                "field": o.field_name,
                "original": o.original_value,
                "corrected": o.corrected_value,
                "reason": o.reason,
            }
            for o in self._overrides[-limit:]
        ]
