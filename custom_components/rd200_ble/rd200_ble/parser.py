"""Parser for RD200 BLE devices"""

from __future__ import annotations

import asyncio
import dataclasses
import struct
from collections import namedtuple
from datetime import datetime
import logging

# from logging import Logger
from math import exp
from typing import Any, Callable, Tuple

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .const import (
    BQ_TO_PCI_MULTIPLIER,
)

RADON_CHARACTERISTIC_UUID_READ = "00001525-0000-1000-8000-00805f9b34fb"
RADON_CHARACTERISTIC_UUID_WRITE = "00001524-0000-1000-8000-00805f9b34fb"
RADON_CHARACTERISTIC_UUID_READ_OLDVERSION = "00001525-1212-efde-1523-785feabcd123"
RADON_CHARACTERISTIC_UUID_WRITE_OLDVERSION = "00001524-1212-efde-1523-785feabcd123"
WRITE_VALUE = b"\x50"

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class RD200Device:
    """Response data with information about the RD200 device"""

    hw_version: str = ""
    sw_version: str = ""
    name: str = ""
    identifier: str = ""
    address: str = ""
    sensors: dict[str, str | float | None] = dataclasses.field(
        default_factory=lambda: {}
    )


# pylint: disable=too-many-locals
# pylint: disable=too-many-branches
class RD200BluetoothDeviceData:
    """Data for RD200 BLE sensors."""

    _event: asyncio.Event | None
    _command_data: bytearray | None

    def __init__(
        self,
        logger: Logger,
        elevation: int | None = None,
        is_metric: bool = True,
        voltage: tuple[float, float] = (2.4, 3.2),
    ):
        super().__init__()
        self.logger = logger
        self.is_metric = is_metric
        self.elevation = elevation
        self.voltage = voltage
        self._command_data = None
        self._event = None

    def notification_handler(self, _: Any, data: bytearray) -> None:
        """Helper for command events"""
        self._command_data = data

        if self._event is None:
            return
        self._event.set()

    async def _get_radon(self, client: BleakClient, device: RD200Device) -> RD200Device:

        self._event = asyncio.Event()
        await client.start_notify(
            RADON_CHARACTERISTIC_UUID_READ, self.notification_handler
        )
        await client.write_gatt_char(RADON_CHARACTERISTIC_UUID_WRITE, WRITE_VALUE)

        # Wait for up to fice seconds to see if a
        # callback comes in.
        try:
            await asyncio.wait_for(self._event.wait(), 5)
        except asyncio.TimeoutError:
            self.logger.warn("Timeout getting command data.")

        await client.stop_notify(RADON_CHARACTERISTIC_UUID_READ)

        if self._command_data is not None and len(self._command_data) == 12:
            RadonValueBQ = struct.unpack("<H", self._command_data[2:4])[0]
            device.sensors["radon"] = float(RadonValueBQ)

            if not self.is_metric:
                device.sensors["radon"] = float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER
                _LOGGER.debug(
                    "New Radon: " + str(float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER)
                )
            RadonValueBQ = struct.unpack("<H", self._command_data[4:6])[0]
            device.sensors["radon_1day_level"] = float(RadonValueBQ)
            if not self.is_metric:
                device.sensors["radon_1day_level"] = (
                    float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER
                )
            RadonValueBQ = struct.unpack("<H", self._command_data[6:8])[0]
            device.sensors["radon_1month_level"] = float(RadonValueBQ)
            if not self.is_metric:
                device.sensors["radon_1month_level"] = (
                    float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER
                )
        else:
            device.sensors["radon"] = None
            device.sensors["radon_1day_level"] = None
            device.sensors["radon_1month_level"] = None

        self._command_data = None
        return device

    async def _get_radon_uptime(
        self, client: BleakClient, device: RD200Device
    ) -> RD200Device:

        self._event = asyncio.Event()
        await client.start_notify(
            RADON_CHARACTERISTIC_UUID_READ, self.notification_handler
        )
        await client.write_gatt_char(RADON_CHARACTERISTIC_UUID_WRITE, b"\x51")

        # Wait for up to fice seconds to see if a
        # callback comes in.
        try:
            await asyncio.wait_for(self._event.wait(), 5)
        except asyncio.TimeoutError:
            self.logger.warn("Timeout getting command data.")

        await client.stop_notify(RADON_CHARACTERISTIC_UUID_READ)

        if self._command_data is not None and len(self._command_data) == 16:

            uptimeMinutes = struct.unpack("<H", self._command_data[4:6])[0]
            uptimeMillis = struct.unpack("<H", self._command_data[3:5])[0]
            device.sensors["radon_uptime"] = (
                float(uptimeMinutes) * 60 + float(uptimeMillis) / 1000
            )
            day = int (uptimeMinutes // 1440)
            hours = int (uptimeMinutes % 1440) // 60
            mins = int (uptimeMinutes % 1440) % 60
            sec = int(uptimeMillis / 1000)
    
            device.sensors["radon_uptime_string"] = (
                str(day) + "d " + str(hours).zfill(2) + ":" + str(mins).zfill(2) + ":" + str(sec).zfill(2)
            )
        else:
            device.sensors["radon_uptime"] = None

        self._command_data = None
        return device

    async def _get_radon_oldVersion(
        self, client: BleakClient, device: RD200Device
    ) -> RD200Device:

        self._event = asyncio.Event()
        await client.start_notify(
            RADON_CHARACTERISTIC_UUID_READ_OLDVERSION, self.notification_handler
        )
        await client.write_gatt_char(
            RADON_CHARACTERISTIC_UUID_WRITE_OLDVERSION, WRITE_VALUE
        )

        # Wait for up to fice seconds to see if a
        # callback comes in.
        try:
            await asyncio.wait_for(self._event.wait(), 5)
        except asyncio.TimeoutError:
            self.logger.warn("Timeout getting command data.")

        await client.stop_notify(RADON_CHARACTERISTIC_UUID_READ_OLDVERSION)

        if self._command_data is not None and len(self._command_data) >= 13:
            RadonValuePCI = struct.unpack("<f", self._command_data[2:6])[0]
            device.sensors["radon"] = round(float(RadonValuePCI),2)
            if self.is_metric:
                device.sensors["radon"] = round(float(RadonValuePCI) / BQ_TO_PCI_MULTIPLIER,2)
            
            RadonValuePCI = struct.unpack("<f", self._command_data[6:10])[0]
            device.sensors["radon_1day_level"] = round(float(RadonValuePCI),2)
            if self.is_metric:
                device.sensors["radon_1day_level"] = round(float(RadonValuePCI) / BQ_TO_PCI_MULTIPLIER,2)
            
            RadonValuePCI = struct.unpack("<f", self._command_data[10:14])[0]
            device.sensors["radon_1month_level"] = round(float(RadonValuePCI),2)
            if self.is_metric:
                device.sensors["radon_1month_level"] = round(float(RadonValuePCI) / BQ_TO_PCI_MULTIPLIER,2)
                
        else:
            device.sensors["radon"] = None
            device.sensors["radon_1day_level"] = None
            device.sensors["radon_1month_level"] = None

        self._command_data = None
        return device

    async def _get_radon_peak(
        self, client: BleakClient, device: RD200Device
    ) -> RD200Device:

        self._event = asyncio.Event()
        await client.start_notify(
            RADON_CHARACTERISTIC_UUID_READ, self.notification_handler
        )
        await client.write_gatt_char(RADON_CHARACTERISTIC_UUID_WRITE, b"\x40")

        # Wait for up to one second to see if a
        # callback comes in.

        try:
            await asyncio.wait_for(self._event.wait(), 5)
        except asyncio.TimeoutError:
            self.logger.warn("Timeout getting command data.")

        await client.stop_notify(RADON_CHARACTERISTIC_UUID_READ)

        if self._command_data is not None and len(self._command_data) == 68:
            RadonValueBQ = struct.unpack("<H", self._command_data[51:53])[0]
            device.sensors["radon_peak"] = float(RadonValueBQ)
            if not self.is_metric:
                device.sensors["radon_peak"] = (
                    float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER
                )
                _LOGGER.debug(
                    "New Radon Peak: " + str(float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER)
                )
            device.sw_version = self._command_data[22:30].decode('utf-8')
            device.hw_version = self._command_data[16:21].decode('utf-8')
        else:
            device.sensors["radon_peak"] = None

        self._command_data = None
        return device

    async def update_device(self, ble_device: BLEDevice) -> RD200Device:
        """Connects to the device through BLE and retrieves relevant data"""

        client = await establish_connection(BleakClient, ble_device, ble_device.address)
        device = RD200Device()
        device.name = ble_device.name
        device.address = ble_device.address
            
        if ble_device.name.startswith("FR:R2"):
            device = await self._get_radon_oldVersion(client, device)
        else:
            device = await self._get_radon(client, device)
            device = await self._get_radon_peak(client, device)
            device = await self._get_radon_uptime(client, device)

        await client.disconnect()

        return device
