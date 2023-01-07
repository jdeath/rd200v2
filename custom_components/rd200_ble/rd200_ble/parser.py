"""Parser for RD200 BLE devices"""

from __future__ import annotations

import asyncio
import dataclasses
import struct
from collections import namedtuple
from datetime import datetime
import logging
#from logging import Logger
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
        
        _LOGGER.debug("data: %d",data) 
        _LOGGER.debug("self._event %s",self._event) 
        if self._event is None:
            return
        self._event.set()
        
    async def _get_radon(
        self, client: BleakClient, device: RD200Device
    ) -> RD200Device:
        
        _LOGGER.debug("0") 
        self._event = asyncio.Event()
        await client.start_notify(RADON_CHARACTERISTIC_UUID_READ, self.notification_handler)
        await client.write_gatt_char(RADON_CHARACTERISTIC_UUID_WRITE, WRITE_VALUE)
        
        
        # Wait for up to one second to see if a
        # callback comes in.
        _LOGGER.debug("1") 
        
        try:
            await asyncio.wait_for(self._event.wait(), 5)
        except asyncio.TimeoutError:
            self.logger.warn("Timeout getting command data.")
        _LOGGER.debug("2") 
        await client.stop_notify(RADON_CHARACTERISTIC_UUID_READ)  
        _LOGGER.debug("3")
        _LOGGER.debug(self._command_data)
        if self._command_data is not None:
            RadonValueBQ = struct.unpack('<H',self._command_data[2:4])[0]
            device.sensors["radon"] = float(RadonValueBQ)
            if not self.is_metric:
                device.sensors["radon"] = (
                                float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER
                            )
            RadonValueBQ = struct.unpack('<H',self._command_data[4:6])[0]
            device.sensors["radon_1day_level"] = float(RadonValueBQ)
            if not self.is_metric:
                device.sensors["radon_1day_level"] = (
                                float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER
                            )
            RadonValueBQ = struct.unpack('<H',self._command_data[6:8])[0]
            device.sensors["radon_1month_level"] = float(RadonValueBQ)
            if not self.is_metric:
                device.sensors["radon_1month_level"] = (
                                float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER
                            )
            self._command_data = None    
        
        _LOGGER.debug("4")
        return device
    
    async def _get_radon_peak(
        self, client: BleakClient, device: RD200Device
    ) -> RD200Device:
        
        _LOGGER.debug("5")
        self._event = asyncio.Event()        
        await client.start_notify(RADON_CHARACTERISTIC_UUID_READ, self.notification_handler)
        await client.write_gatt_char(RADON_CHARACTERISTIC_UUID_WRITE, b"\x40")
        
        
        # Wait for up to one second to see if a
        # callback comes in.
        _LOGGER.debug("5.5")
        
        try:
            await asyncio.wait_for(self._event.wait(), 5)
        except asyncio.TimeoutError:
            self.logger.warn("Timeout getting command data.")
        
        _LOGGER.debug("6")
        await client.stop_notify(RADON_CHARACTERISTIC_UUID_READ) 
        
        _LOGGER.debug("7")
        _LOGGER.debug(self._command_data)
        if self._command_data is not None:
            RadonValueBQ = struct.unpack('<H',self._command_data[51:53])[0]
            device.sensors["radon_peak"] = float(RadonValueBQ)
            if not self.is_metric:
                device.sensors["radon_peak"] = (
                                float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER
                            ) 
            self._command_data = None
        _LOGGER.debug("8")
        return device
        
    async def update_device(self, ble_device: BLEDevice) -> RD200Device:
        """Connects to the device through BLE and retrieves relevant data"""
        
        client = await establish_connection(BleakClient, ble_device, ble_device.address)
        device = RD200Device()
        device = await self._get_radon(client, device)
        device = await self._get_radon_peak(client, device)
        _LOGGER.debug("Try to disconnect")
        await client.disconnect()
        _LOGGER.debug("disconnect")
        
        return device
