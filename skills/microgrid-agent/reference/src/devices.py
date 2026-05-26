"""Hardware abstraction layer for energy devices.

Supports Modbus RTU (inverters, meters), Victron VE.Direct, and simulated devices.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import struct
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # Python < 3.11

log = logging.getLogger(__name__)


class DeviceStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    FAULT = "fault"
    STANDBY = "standby"


@dataclass
class DeviceReading:
    power_kw: float
    energy_kwh: float
    status: DeviceStatus
    timestamp: float = field(default_factory=time.time)
    extra: dict[str, Any] = field(default_factory=dict)


class EnergyDevice(ABC):
    """Base class for all energy devices in the microgrid."""

    def __init__(self, device_id: str, name: str, device_type: str):
        self.device_id = device_id
        self.name = name
        self.device_type = device_type
        self._last_reading: DeviceReading | None = None

    @abstractmethod
    async def read_power_kw(self) -> float:
        ...

    @abstractmethod
    async def read_energy_kwh(self) -> float:
        ...

    @abstractmethod
    async def read_status(self) -> DeviceStatus:
        ...

    @abstractmethod
    async def set_power_limit(self, limit_kw: float) -> bool:
        ...

    @abstractmethod
    async def start(self) -> bool:
        ...

    @abstractmethod
    async def stop(self) -> bool:
        ...

    async def read(self) -> DeviceReading:
        reading = DeviceReading(
            power_kw=await self.read_power_kw(),
            energy_kwh=await self.read_energy_kwh(),
            status=await self.read_status(),
        )
        self._last_reading = reading
        return reading

    @property
    def last_reading(self) -> DeviceReading | None:
        return self._last_reading


class ModbusRtuDevice(EnergyDevice):
    """RS-485 Modbus RTU device (inverters, charge controllers, meters)."""

    def __init__(
        self,
        device_id: str,
        name: str,
        device_type: str,
        port: str,
        slave_id: int,
        baudrate: int = 9600,
        power_register: int = 0,
        energy_register: int = 2,
        status_register: int = 4,
        control_register: int = 6,
        register_scale: float = 0.1,
    ):
        super().__init__(device_id, name, device_type)
        self.port = port
        self.slave_id = slave_id
        self.baudrate = baudrate
        self.power_register = power_register
        self.energy_register = energy_register
        self.status_register = status_register
        self.control_register = control_register
        self.register_scale = register_scale
        self._client = None

    async def _get_client(self):
        if self._client is None:
            from pymodbus.client import AsyncModbusSerialClient

            self._client = AsyncModbusSerialClient(
                port=self.port,
                baudrate=self.baudrate,
                parity="N",
                stopbits=1,
                bytesize=8,
                timeout=3,
            )
            await self._client.connect()
        return self._client

    async def _read_registers(self, address: int, count: int = 2) -> list[int]:
        client = await self._get_client()
        result = await client.read_holding_registers(
            address, count, slave=self.slave_id
        )
        if result.isError():
            raise IOError(f"Modbus read error at register {address}: {result}")
        return result.registers

    async def _write_register(self, address: int, value: int) -> bool:
        client = await self._get_client()
        result = await client.write_register(address, value, slave=self.slave_id)
        return not result.isError()

    async def read_power_kw(self) -> float:
        regs = await self._read_registers(self.power_register, 2)
        raw = (regs[0] << 16) | regs[1]
        return raw * self.register_scale / 1000.0

    async def read_energy_kwh(self) -> float:
        regs = await self._read_registers(self.energy_register, 2)
        raw = (regs[0] << 16) | regs[1]
        return raw * self.register_scale

    async def read_status(self) -> DeviceStatus:
        regs = await self._read_registers(self.status_register, 1)
        status_map = {0: DeviceStatus.OFFLINE, 1: DeviceStatus.ONLINE,
                      2: DeviceStatus.STANDBY, 3: DeviceStatus.FAULT}
        return status_map.get(regs[0], DeviceStatus.OFFLINE)

    async def set_power_limit(self, limit_kw: float) -> bool:
        raw = int(limit_kw * 1000.0 / self.register_scale)
        return await self._write_register(self.control_register, raw)

    async def start(self) -> bool:
        return await self._write_register(self.control_register + 2, 1)

    async def stop(self) -> bool:
        return await self._write_register(self.control_register + 2, 0)


class VeDirectDevice(EnergyDevice):
    """Victron VE.Direct serial protocol device (MPPT controllers, BMVs)."""

    def __init__(
        self,
        device_id: str,
        name: str,
        device_type: str,
        port: str,
        baudrate: int = 19200,
    ):
        super().__init__(device_id, name, device_type)
        self.port = port
        self.baudrate = baudrate
        self._data: dict[str, str] = {}
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._parse_task: asyncio.Task | None = None

    async def _connect(self):
        if self._reader is not None:
            return
        import serial_asyncio

        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self.port, baudrate=self.baudrate
        )
        self._parse_task = asyncio.create_task(self._parse_loop())

    async def _parse_loop(self):
        """Continuously parse VE.Direct text protocol frames."""
        buffer = b""
        while True:
            try:
                chunk = await self._reader.read(256)
                if not chunk:
                    await asyncio.sleep(0.1)
                    continue
                buffer += chunk
                # VE.Direct frames are delimited by \r\n with key\tvalue lines
                while b"\r\n" in buffer:
                    line, buffer = buffer.split(b"\r\n", 1)
                    decoded = line.decode("ascii", errors="ignore").strip()
                    if "\t" in decoded:
                        key, value = decoded.split("\t", 1)
                        self._data[key] = value
            except Exception as e:
                log.warning("VE.Direct parse error: %s", e)
                await asyncio.sleep(1)

    def _get_float(self, key: str, scale: float = 1.0, default: float = 0.0) -> float:
        try:
            return float(self._data.get(key, str(default))) * scale
        except (ValueError, TypeError):
            return default

    async def read_power_kw(self) -> float:
        await self._connect()
        # PPV = panel power (W) for MPPT, P = battery power for BMV
        watts = self._get_float("PPV") or self._get_float("P")
        return watts / 1000.0

    async def read_energy_kwh(self) -> float:
        await self._connect()
        # H19 = total yield (0.01 kWh) for MPPT
        return self._get_float("H19", scale=0.01)

    async def read_status(self) -> DeviceStatus:
        await self._connect()
        cs = self._data.get("CS", "0")
        # CS: 0=Off, 2=Fault, 3=Bulk, 4=Absorption, 5=Float
        if cs in ("3", "4", "5"):
            return DeviceStatus.ONLINE
        elif cs == "2":
            return DeviceStatus.FAULT
        elif cs == "0":
            return DeviceStatus.STANDBY
        return DeviceStatus.OFFLINE

    async def set_power_limit(self, limit_kw: float) -> bool:
        log.warning("VE.Direct does not support power limit setting")
        return False

    async def start(self) -> bool:
        log.warning("VE.Direct start not supported via serial")
        return False

    async def stop(self) -> bool:
        log.warning("VE.Direct stop not supported via serial")
        return False


class SimulatedDevice(EnergyDevice):
    """Simulated device for testing without hardware."""

    def __init__(
        self,
        device_id: str,
        name: str,
        device_type: str,
        base_power_kw: float = 1.0,
        noise_pct: float = 0.05,
    ):
        super().__init__(device_id, name, device_type)
        self.base_power_kw = base_power_kw
        self.noise_pct = noise_pct
        self._energy_kwh = 0.0
        self._running = True
        self._power_limit = base_power_kw * 2
        self._last_time = time.time()

    async def read_power_kw(self) -> float:
        if not self._running:
            return 0.0
        now = time.time()
        dt = now - self._last_time
        self._last_time = now

        if self.device_type == "solar":
            # Simple solar curve: sine wave peaking at noon
            hour = (time.localtime().tm_hour + time.localtime().tm_min / 60.0)
            solar_factor = max(0, math.sin(math.pi * (hour - 6) / 12))
            power = self.base_power_kw * solar_factor
        elif self.device_type == "load":
            # Load with diurnal pattern
            hour = time.localtime().tm_hour
            load_factor = 0.4 + 0.6 * (1.0 if 7 <= hour <= 22 else 0.3)
            power = self.base_power_kw * load_factor
        else:
            power = self.base_power_kw

        noise = random.gauss(0, self.noise_pct * power) if power > 0 else 0
        power = max(0, min(power + noise, self._power_limit))
        self._energy_kwh += power * (dt / 3600.0)
        return power

    async def read_energy_kwh(self) -> float:
        return self._energy_kwh

    async def read_status(self) -> DeviceStatus:
        return DeviceStatus.ONLINE if self._running else DeviceStatus.STANDBY

    async def set_power_limit(self, limit_kw: float) -> bool:
        self._power_limit = limit_kw
        return True

    async def start(self) -> bool:
        self._running = True
        return True

    async def stop(self) -> bool:
        self._running = False
        return True


class DeviceRegistry:
    """Loads and manages devices from config/devices.toml."""

    def __init__(self):
        self.devices: dict[str, EnergyDevice] = {}

    def load_config(self, config_path: Path):
        with open(config_path, "rb") as f:
            config = tomllib.load(f)

        for dev_cfg in config.get("device", []):
            device = self._create_device(dev_cfg)
            if device:
                self.devices[device.device_id] = device
                log.info("Registered device: %s (%s)", device.name, device.device_type)

    def _create_device(self, cfg: dict) -> EnergyDevice | None:
        protocol = cfg.get("protocol", "simulated")
        device_id = cfg["id"]
        name = cfg.get("name", device_id)
        device_type = cfg.get("type", "generic")

        if protocol == "modbus_rtu":
            return ModbusRtuDevice(
                device_id=device_id,
                name=name,
                device_type=device_type,
                port=cfg["port"],
                slave_id=cfg.get("slave_id", 1),
                baudrate=cfg.get("baudrate", 9600),
                power_register=cfg.get("power_register", 0),
                energy_register=cfg.get("energy_register", 2),
                status_register=cfg.get("status_register", 4),
                control_register=cfg.get("control_register", 6),
                register_scale=cfg.get("register_scale", 0.1),
            )
        elif protocol == "vedirect":
            return VeDirectDevice(
                device_id=device_id,
                name=name,
                device_type=device_type,
                port=cfg["port"],
                baudrate=cfg.get("baudrate", 19200),
            )
        elif protocol == "simulated":
            return SimulatedDevice(
                device_id=device_id,
                name=name,
                device_type=device_type,
                base_power_kw=cfg.get("base_power_kw", 1.0),
                noise_pct=cfg.get("noise_pct", 0.05),
            )
        else:
            log.warning("Unknown protocol '%s' for device '%s'", protocol, device_id)
            return None

    def get(self, device_id: str) -> EnergyDevice | None:
        return self.devices.get(device_id)

    def by_type(self, device_type: str) -> list[EnergyDevice]:
        return [d for d in self.devices.values() if d.device_type == device_type]

    async def read_all(self) -> dict[str, DeviceReading]:
        results = {}
        for device_id, device in self.devices.items():
            try:
                results[device_id] = await device.read()
            except Exception as e:
                log.error("Failed to read device %s: %s", device_id, e)
                results[device_id] = DeviceReading(
                    power_kw=0.0, energy_kwh=0.0, status=DeviceStatus.OFFLINE
                )
        return results
