"""Entry point for the microgrid agent.

Loads config from config/site.toml, initializes all modules,
and runs the async event loop. Handles SIGTERM and SIGUSR1.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # Python < 3.11

from src.agent import AgentConfig, MicrogridAgent

log = logging.getLogger("microgrid")


def load_config(config_path: Path) -> AgentConfig:
    """Load site configuration from TOML file."""
    if not config_path.exists():
        log.warning("Config file not found at %s, using defaults", config_path)
        return AgentConfig()

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    site = raw.get("site", {})
    battery = raw.get("battery", {})
    diesel = raw.get("diesel", {})
    dashboard = raw.get("dashboard", {})
    mqtt = raw.get("mqtt", {})
    paths = raw.get("paths", {})

    base_dir = config_path.parent.parent  # project root

    return AgentConfig(
        site_id=site.get("id", "site-001"),
        dispatch_interval_s=site.get("dispatch_interval_s", 5.0),
        forecast_interval_s=site.get("forecast_interval_s", 900.0),
        sensor_interval_s=site.get("sensor_interval_s", 1.0),
        metrics_publish_interval_s=site.get("metrics_publish_interval_s", 60.0),
        battery_capacity_kwh=battery.get("capacity_kwh", 10.0),
        battery_max_charge_kw=battery.get("max_charge_kw", 5.0),
        battery_max_discharge_kw=battery.get("max_discharge_kw", 5.0),
        initial_soc_pct=battery.get("initial_soc_pct", 50.0),
        diesel_max_kw=diesel.get("max_kw", 5.0),
        diesel_min_kw=diesel.get("min_kw", 1.0),
        dashboard_host=dashboard.get("host", "0.0.0.0"),
        dashboard_port=dashboard.get("port", 8080),
        mqtt_broker=mqtt.get("broker", "localhost"),
        mqtt_port=mqtt.get("port", 1883),
        mqtt_username=mqtt.get("username"),
        mqtt_password=mqtt.get("password"),
        data_dir=base_dir / paths.get("data_dir", "data"),
        config_dir=base_dir / paths.get("config_dir", "config"),
        db_path=base_dir / paths.get("db_path", "data/knowledge.db"),
        model_dir=base_dir / paths.get("model_dir", "data/models"),
        sync_queue_dir=base_dir / paths.get("sync_queue_dir", "data/sync-queue"),
    )


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Quiet down noisy libraries
    logging.getLogger("pymodbus").setLevel(logging.WARNING)
    logging.getLogger("paho").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


async def run(config_path: Path):
    config = load_config(config_path)
    agent = MicrogridAgent(config)

    loop = asyncio.get_event_loop()

    # Graceful shutdown on SIGTERM
    def handle_sigterm():
        log.info("Received SIGTERM, shutting down...")
        asyncio.create_task(agent.stop())

    # Reload knowledge graph on SIGUSR1
    def handle_sigusr1():
        log.info("Received SIGUSR1, reloading knowledge graph...")
        asyncio.create_task(agent.knowledge.close())
        asyncio.create_task(agent.knowledge.open())

    try:
        loop.add_signal_handler(signal.SIGTERM, handle_sigterm)
        loop.add_signal_handler(signal.SIGUSR1, handle_sigusr1)
    except NotImplementedError:
        pass  # Windows doesn't support signal handlers in asyncio

    try:
        await agent.start()
    except KeyboardInterrupt:
        log.info("Keyboard interrupt, shutting down...")
    finally:
        await agent.stop()


def main():
    setup_logging()

    config_path = Path("config/site.toml")
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])

    log.info("Microgrid agent starting with config: %s", config_path)
    asyncio.run(run(config_path))


if __name__ == "__main__":
    main()
