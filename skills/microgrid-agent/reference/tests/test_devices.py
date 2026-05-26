"""
Tests for the devices hardware abstraction layer.

Covers:
- SimulatedDevice returns valid readings
- Solar diurnal pattern
- DeviceRegistry in simulate mode
- Sensor reading field completeness
"""

import asyncio
import math
import time
from unittest.mock import patch

import pytest

from src.devices import (
    DeviceReading,
    DeviceRegistry,
    DeviceStatus,
    SimulatedDevice,
)


# ===========================================================================
# SimulatedDevice Tests
# ===========================================================================

class TestSimulatedDeviceReads:
    """SimulatedDevice returns valid readings."""

    @pytest.mark.asyncio
    async def test_read_returns_device_reading(self):
        """SimulatedDevice.read() should return a DeviceReading."""
        dev = SimulatedDevice("sim-solar-1", "Test Solar", "solar", base_power_kw=5.0)
        reading = await dev.read()
        assert isinstance(reading, DeviceReading)

    @pytest.mark.asyncio
    async def test_read_power_non_negative(self):
        """Power readings must be >= 0."""
        dev = SimulatedDevice("sim-load-1", "Test Load", "load", base_power_kw=3.0, noise_pct=0.0)
        power = await dev.read_power_kw()
        assert power >= 0.0

    @pytest.mark.asyncio
    async def test_read_energy_non_negative(self):
        """Energy accumulation must be >= 0."""
        dev = SimulatedDevice("sim-gen-1", "Test Gen", "generic", base_power_kw=2.0)
        energy = await dev.read_energy_kwh()
        assert energy >= 0.0

    @pytest.mark.asyncio
    async def test_status_online_when_running(self):
        """Status should be ONLINE when device is running."""
        dev = SimulatedDevice("sim-1", "Test", "generic")
        status = await dev.read_status()
        assert status == DeviceStatus.ONLINE

    @pytest.mark.asyncio
    async def test_status_standby_when_stopped(self):
        """Status should be STANDBY when device is stopped."""
        dev = SimulatedDevice("sim-1", "Test", "generic")
        await dev.stop()
        status = await dev.read_status()
        assert status == DeviceStatus.STANDBY

    @pytest.mark.asyncio
    async def test_stopped_device_reads_zero_power(self):
        """A stopped device should return 0 power."""
        dev = SimulatedDevice("sim-1", "Test", "generic", base_power_kw=10.0, noise_pct=0.0)
        await dev.stop()
        power = await dev.read_power_kw()
        assert power == 0.0

    @pytest.mark.asyncio
    async def test_start_resumes_power(self):
        """Starting a stopped device should resume power output."""
        dev = SimulatedDevice("sim-1", "Test", "generic", base_power_kw=5.0, noise_pct=0.0)
        await dev.stop()
        await dev.start()
        power = await dev.read_power_kw()
        assert power > 0.0

    @pytest.mark.asyncio
    async def test_set_power_limit(self):
        """Power limit should cap the output."""
        dev = SimulatedDevice("sim-1", "Test", "generic", base_power_kw=10.0, noise_pct=0.0)
        await dev.set_power_limit(3.0)
        power = await dev.read_power_kw()
        assert power <= 3.0


class TestSimulatedDeviceSolarDiurnal:
    """Solar SimulatedDevice follows a day/night pattern."""

    @pytest.mark.asyncio
    async def test_solar_zero_at_night(self):
        """Solar device should output ~0 during night hours (e.g. hour 2)."""
        dev = SimulatedDevice("sim-solar-1", "Solar", "solar", base_power_kw=5.0, noise_pct=0.0)
        # Patch time.localtime to return hour=2 (nighttime)
        fake_time = time.struct_time((2026, 3, 30, 2, 0, 0, 0, 89, 0))
        with patch("src.devices.time") as mock_time:
            mock_time.time.return_value = time.time()
            mock_time.localtime.return_value = fake_time
            power = await dev.read_power_kw()
        assert power == pytest.approx(0.0, abs=0.01), "Solar should be ~0 at 2 AM"

    @pytest.mark.asyncio
    async def test_solar_positive_at_noon(self):
        """Solar device should output positive power at noon."""
        dev = SimulatedDevice("sim-solar-1", "Solar", "solar", base_power_kw=5.0, noise_pct=0.0)
        fake_time = time.struct_time((2026, 3, 30, 12, 0, 0, 0, 89, 0))
        with patch("src.devices.time") as mock_time:
            mock_time.time.return_value = time.time()
            mock_time.localtime.return_value = fake_time
            power = await dev.read_power_kw()
        assert power > 0.0, "Solar should produce power at noon"

    @pytest.mark.asyncio
    async def test_solar_peaks_at_noon(self):
        """Solar power should be highest around noon (hour 12)."""
        dev = SimulatedDevice("sim-solar-1", "Solar", "solar", base_power_kw=5.0, noise_pct=0.0)
        powers = {}
        for hour in [8, 10, 12, 14, 16]:
            # Create fresh device to reset internal _last_time
            d = SimulatedDevice("sim-solar-1", "Solar", "solar", base_power_kw=5.0, noise_pct=0.0)
            fake_time = time.struct_time((2026, 3, 30, hour, 0, 0, 0, 89, 0))
            with patch("src.devices.time") as mock_time:
                mock_time.time.return_value = time.time()
                mock_time.localtime.return_value = fake_time
                powers[hour] = await d.read_power_kw()
        assert powers[12] >= powers[8], "Noon power should be >= morning power"
        assert powers[12] >= powers[16], "Noon power should be >= afternoon power"


class TestDeviceRegistrySimulated:
    """DeviceRegistry loads simulated devices from TOML config."""

    def test_registry_starts_empty(self):
        """A new registry should have no devices."""
        reg = DeviceRegistry()
        assert len(reg.devices) == 0

    def test_load_simulated_config(self, tmp_path):
        """Registry loads simulated devices from a TOML config file."""
        config_file = tmp_path / "devices.toml"
        config_file.write_text(
            '[[device]]\n'
            'id = "sim-solar-1"\n'
            'name = "Solar Panel"\n'
            'type = "solar"\n'
            'protocol = "simulated"\n'
            'base_power_kw = 5.0\n'
            '\n'
            '[[device]]\n'
            'id = "sim-load-1"\n'
            'name = "Hospital"\n'
            'type = "load"\n'
            'protocol = "simulated"\n'
            'base_power_kw = 3.0\n'
        )
        reg = DeviceRegistry()
        reg.load_config(config_file)
        assert len(reg.devices) == 2
        assert reg.get("sim-solar-1") is not None
        assert reg.get("sim-load-1") is not None
        assert isinstance(reg.get("sim-solar-1"), SimulatedDevice)

    def test_get_returns_none_for_missing(self):
        """Registry.get() should return None for unknown device IDs."""
        reg = DeviceRegistry()
        assert reg.get("nonexistent") is None

    def test_by_type_filters(self, tmp_path):
        """Registry.by_type() should filter devices by type."""
        config_file = tmp_path / "devices.toml"
        config_file.write_text(
            '[[device]]\n'
            'id = "s1"\n'
            'name = "Solar 1"\n'
            'type = "solar"\n'
            'protocol = "simulated"\n'
            '\n'
            '[[device]]\n'
            'id = "s2"\n'
            'name = "Solar 2"\n'
            'type = "solar"\n'
            'protocol = "simulated"\n'
            '\n'
            '[[device]]\n'
            'id = "l1"\n'
            'name = "Load 1"\n'
            'type = "load"\n'
            'protocol = "simulated"\n'
        )
        reg = DeviceRegistry()
        reg.load_config(config_file)
        solar_devices = reg.by_type("solar")
        assert len(solar_devices) == 2
        load_devices = reg.by_type("load")
        assert len(load_devices) == 1

    def test_unknown_protocol_skipped(self, tmp_path):
        """Devices with unknown protocol should be skipped gracefully."""
        config_file = tmp_path / "devices.toml"
        config_file.write_text(
            '[[device]]\n'
            'id = "x1"\n'
            'name = "Unknown"\n'
            'type = "generic"\n'
            'protocol = "foobar"\n'
        )
        reg = DeviceRegistry()
        reg.load_config(config_file)
        assert len(reg.devices) == 0

    @pytest.mark.asyncio
    async def test_read_all_returns_readings(self, tmp_path):
        """read_all() should return a DeviceReading for each device."""
        config_file = tmp_path / "devices.toml"
        config_file.write_text(
            '[[device]]\n'
            'id = "s1"\n'
            'name = "Solar"\n'
            'type = "solar"\n'
            'protocol = "simulated"\n'
            '\n'
            '[[device]]\n'
            'id = "l1"\n'
            'name = "Load"\n'
            'type = "load"\n'
            'protocol = "simulated"\n'
        )
        reg = DeviceRegistry()
        reg.load_config(config_file)
        readings = await reg.read_all()
        assert len(readings) == 2
        assert "s1" in readings
        assert "l1" in readings


class TestSensorReadingsFields:
    """All expected fields present in DeviceReading."""

    @pytest.mark.asyncio
    async def test_reading_has_power_kw(self):
        dev = SimulatedDevice("d1", "D", "generic")
        reading = await dev.read()
        assert hasattr(reading, "power_kw")
        assert isinstance(reading.power_kw, float)

    @pytest.mark.asyncio
    async def test_reading_has_energy_kwh(self):
        dev = SimulatedDevice("d1", "D", "generic")
        reading = await dev.read()
        assert hasattr(reading, "energy_kwh")
        assert isinstance(reading.energy_kwh, float)

    @pytest.mark.asyncio
    async def test_reading_has_status(self):
        dev = SimulatedDevice("d1", "D", "generic")
        reading = await dev.read()
        assert hasattr(reading, "status")
        assert isinstance(reading.status, DeviceStatus)

    @pytest.mark.asyncio
    async def test_reading_has_timestamp(self):
        dev = SimulatedDevice("d1", "D", "generic")
        reading = await dev.read()
        assert hasattr(reading, "timestamp")
        assert isinstance(reading.timestamp, float)
        assert reading.timestamp > 0

    @pytest.mark.asyncio
    async def test_reading_has_extra_dict(self):
        dev = SimulatedDevice("d1", "D", "generic")
        reading = await dev.read()
        assert hasattr(reading, "extra")
        assert isinstance(reading.extra, dict)

    @pytest.mark.asyncio
    async def test_last_reading_cached(self):
        """After read(), last_reading should return the same reading."""
        dev = SimulatedDevice("d1", "D", "generic")
        assert dev.last_reading is None
        reading = await dev.read()
        assert dev.last_reading is reading
