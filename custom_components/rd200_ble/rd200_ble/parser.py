"""Parser for RD200 BLE devices"""

from __future__ import annotations

import asyncio
import dataclasses
import struct
from collections import namedtuple
from datetime import datetime
import logging

from functools import partial
# from logging import Logger
from math import exp
from typing import Any, Callable, Tuple, TypeVar, cast

from async_interrupt import interrupt
from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak.backends.service import BleakGATTService
from bleak_retry_connector import establish_connection, BleakClientWithServiceCache

WrapFuncType = TypeVar("WrapFuncType", bound=Callable[..., Any])

class BleakCharacteristicMissing(BleakError):
    """Raised when a characteristic is missing from a service."""


class BleakServiceMissing(BleakError):
    """Raised when a service is missing."""

class DisconnectedError(Exception):
    """Disconnected from device."""

class UnsupportedDeviceError(Exception):
    """Unsupported device."""
    
from .const import (
    BQ_TO_PCI_MULTIPLIER,
    UPDATE_TIMEOUT,
)

RADON_CHARACTERISTIC_UUID_READ = "00001525-0000-1000-8000-00805f9b34fb"
RADON_CHARACTERISTIC_UUID_WRITE = "00001524-0000-1000-8000-00805f9b34fb"
RADON_CHARACTERISTIC_UUID_READ_OLDVERSION = "00001525-1212-efde-1523-785feabcd123"
RADON_CHARACTERISTIC_UUID_WRITE_OLDVERSION = "00001524-1212-efde-1523-785feabcd123"
WRITE_VALUE = b"\x50"

# RadonEye Plus2 (RD200P2): advertises as "FR:P...", uses the V1 service and
# characteristic UUIDs, but answers 0x50/0x51 with little-endian integers
# (Bq/m3) instead of the V1 floats (pCi/L).
PLUS2_NAME_PREFIX = "FR:P"

_LOGGER = logging.getLogger(__name__)


def parse_plus2_measurement(data: bytes | bytearray) -> dict[str, int] | None:
    """Decode a RadonEye Plus2 reply to command 0x50.

    Layout (20 bytes): 0x50, 0x10, then eight little-endian uint16 values and
    two bytes of the device clock (mm, ss). Values are in Bq/m3, except the
    two pulse counters.
    """
    if data is None or len(data) < 18 or data[0] != 0x50:
        return None
    (
        now,
        day,
        month,
        week,
        peak,
        _unknown,
        pulse_now,
        pulse_last,
    ) = struct.unpack("<8H", data[2:18])
    return {
        "radon": now,
        "radon_1day_level": day,
        "radon_1month_level": month,
        "radon_7day_level": week,
        "radon_peak": peak,
        "radon_C_now": pulse_now,
        "radon_C_last": pulse_last,
    }


def parse_plus2_uptime_minutes(data: bytes | bytearray) -> int | None:
    """Decode the measuring time (minutes) from a RadonEye Plus2 reply to 0x51."""
    if data is None or len(data) < 8 or data[0] != 0x51:
        return None
    return struct.unpack("<I", data[4:8])[0]


@dataclasses.dataclass
class RD200Device:
    """Response data with information about the RD200 device"""

    hw_version: str = ""
    sw_version: str = ""
    name: str = ""
    identifier: str = ""
    address: str = ""
    last_valid_update: str | None = None
    # Sensor keys currently serving a cached (held-over) reading. Runtime-only:
    # deliberately not persisted, so the stored cache format is unchanged.
    stale_keys: list[str] = dataclasses.field(default_factory=list)
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

    def disconnect_on_missing_services(func: WrapFuncType) -> WrapFuncType:
        """Define a wrapper to disconnect on missing services and characteristics.

        This must be placed after the retry_bluetooth_connection_error
        decorator.
        """

        async def _async_disconnect_on_missing_services_wrap(
            self, *args: Any, **kwargs: Any
        ) -> None:
            try:
                return await func(self, *args, **kwargs)
            except (BleakServiceMissing, BleakCharacteristicMissing) as ex:
                logger.warning(
                    "%s: Missing service or characteristic, disconnecting to force refetch of GATT services: %s",
                    self.name,
                    ex,
                )
                if self.client:
                    await self.client.clear_cache()
                    await self.client.disconnect()
                raise

        return cast(WrapFuncType, _async_disconnect_on_missing_services_wrap)

    @disconnect_on_missing_services
    async def _get_radon(self, client: BleakClient, device: RD200Device) -> RD200Device:

        self._event = asyncio.Event()
        try:
            await client.start_notify(
                RADON_CHARACTERISTIC_UUID_READ, self.notification_handler
            )
        except:
            self.logger.warn("_get_radon Bleak error 1")
            device.sensors["radon"] = None
            device.sensors["radon_1day_level"] = None
            device.sensors["radon_1month_level"] = None
            device.sensors["radon_C_now"] = None
            device.sensors["radon_C_last"] = None
            self._command_data = None
            return device
        
        await client.write_gatt_char(RADON_CHARACTERISTIC_UUID_WRITE, WRITE_VALUE)

        # Wait for up to five seconds to see if a
        # callback comes in.
        try:
            await asyncio.wait_for(self._event.wait(), 15)
        except asyncio.TimeoutError:
            self.logger.warn("_get_radon Timeout getting command data.")
        except:
            self.logger.warn("_get_radon Bleak error 2")

        await client.stop_notify(RADON_CHARACTERISTIC_UUID_READ)

        if self._command_data is not None and len(self._command_data) == 12:
            RadonValueBQ = struct.unpack("<H", self._command_data[2:4])[0]
            device.sensors["radon"] = round(float(RadonValueBQ),2)
            if not self.is_metric:
                device.sensors["radon"] = round(float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER,2)

            RadonValueBQ = struct.unpack("<H", self._command_data[4:6])[0]
            device.sensors["radon_1day_level"] = round(float(RadonValueBQ),2)
            if not self.is_metric:
                device.sensors["radon_1day_level"] = (
                    round(float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER,2)
                )
            RadonValueBQ = struct.unpack("<H", self._command_data[6:8])[0]
            device.sensors["radon_1month_level"] = round(float(RadonValueBQ),2)
            if not self.is_metric:
                device.sensors["radon_1month_level"] = (
                    round(float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER,2)
                )
            RadonValueBQ = struct.unpack("<H", self._command_data[8:10])[0]
            device.sensors["radon_C_now"] = int(RadonValueBQ)
            RadonValueBQ = struct.unpack("<H", self._command_data[10:12])[0]
            device.sensors["radon_C_last"] = int(RadonValueBQ)
        else:
            self.logger.warn("_get_radon Data None")
            device.sensors["radon"] = None
            device.sensors["radon_1day_level"] = None
            device.sensors["radon_1month_level"] = None
            device.sensors["radon_C_now"] = None
            device.sensors["radon_C_last"] = None
            
        self._command_data = None
        return device

    @disconnect_on_missing_services
    async def _get_radon_uptime(
        self, client: BleakClient, device: RD200Device
    ) -> RD200Device:

        self._event = asyncio.Event()
        try:
            await client.start_notify(
                RADON_CHARACTERISTIC_UUID_READ, self.notification_handler
            )
        except:
            self.logger.warn("_get_radon_uptime Bleak error 1")

        await client.write_gatt_char(RADON_CHARACTERISTIC_UUID_WRITE, b"\x51")

        # Wait for up to fice seconds to see if a
        # callback comes in.
        try:
            await asyncio.wait_for(self._event.wait(), 5)
        except asyncio.TimeoutError:
            self.logger.warn("_get_radon_uptime Timeout getting command data.")
        except:
            self.logger.warn("_get_radon_uptime Bleak error 2")

        await client.stop_notify(RADON_CHARACTERISTIC_UUID_READ)

        if self._command_data is not None and len(self._command_data) == 16:

            uptimeMinutes = struct.unpack("<I", self._command_data[4:8])[0]
            #uptimeMillis = struct.unpack("<H", self._command_data[3:5])[0]
            uptimeMillis = 0
            device.sensors["radon_uptime"] = (
                int(float(uptimeMinutes) * 60 + float(uptimeMillis) / 1000)
            )
            day = int (uptimeMinutes // 1440)
            hours = int (uptimeMinutes % 1440) // 60
            mins = int (uptimeMinutes % 1440) % 60
            #sec = int(uptimeMillis / 1000)
            sec = 0

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

        # Wait for up to five seconds to see if a
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

    async def _get_radon_peak_uptime_oldVersion(
        self, client: BleakClient, device: RD200Device
    ) -> RD200Device:

        self._event = asyncio.Event()
        await client.start_notify(
            RADON_CHARACTERISTIC_UUID_READ_OLDVERSION, self.notification_handler
        )
        await client.write_gatt_char(
            RADON_CHARACTERISTIC_UUID_WRITE_OLDVERSION, b"\x51"
        )

        # Wait for up to five seconds to see if a
        # callback comes in.
        try:
            await asyncio.wait_for(self._event.wait(), 5)
        except asyncio.TimeoutError:
            self.logger.warn("Timeout getting command data.")

        await client.stop_notify(RADON_CHARACTERISTIC_UUID_READ_OLDVERSION)

        if self._command_data is not None and len(self._command_data) >= 13:
            RadonValuePCI = struct.unpack("<f", self._command_data[12:16])[0]
            device.sensors["radon_peak"] = round(float(RadonValuePCI),2)
            if self.is_metric:
                device.sensors["radon_peak"] = round(float(RadonValuePCI) / BQ_TO_PCI_MULTIPLIER,2)

            uptimeMinutes = struct.unpack("<I", self._command_data[4:8])[0]
            device.sensors["radon_uptime"] = (
                int(uptimeMinutes) * 60
            )
            day = int (uptimeMinutes // 1440)
            hours = int (uptimeMinutes % 1440) // 60
            mins = int (uptimeMinutes % 1440) % 60
            sec = 0

            device.sensors["radon_uptime_string"] = (
                str(day) + "d " + str(hours).zfill(2) + ":" + str(mins).zfill(2) + ":" + str(sec).zfill(2)
            )
        else:
            device.sensors["radon_peak"] = None
            device.sensors["radon_uptime"] = None
            device.sensors["radon_uptime_string"] = None

        self._command_data = None
        return device

    @disconnect_on_missing_services
    async def _get_radon_peak(
        self, client: BleakClient, device: RD200Device
    ) -> RD200Device:

        self._event = asyncio.Event()
        try:
            await client.start_notify(
                RADON_CHARACTERISTIC_UUID_READ, self.notification_handler
            )
        except:
            self.logger.warn("_get_radon_peak Bleak error 1")

        await client.write_gatt_char(RADON_CHARACTERISTIC_UUID_WRITE, b"\x40")

        # Wait for up to one second to see if a
        # callback comes in.

        try:
            await asyncio.wait_for(self._event.wait(), 5)
        except asyncio.TimeoutError:
            self.logger.warn("_get_radon_peak Timeout getting command data.")
        except:
            self.logger.warn("_get_radon_peak Bleak error 2")

        await client.stop_notify(RADON_CHARACTERISTIC_UUID_READ)

        if self._command_data is not None and len(self._command_data) == 68:
            RadonValueBQ = struct.unpack("<H", self._command_data[51:53])[0]
            device.sensors["radon_peak"] = round(float(RadonValueBQ),2)
            if not self.is_metric:
                device.sensors["radon_peak"] = (
                    round(float(RadonValueBQ) * BQ_TO_PCI_MULTIPLIER,2)
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

    async def _plus2_command(
        self, client: BleakClient, command: bytes
    ) -> bytearray | None:
        """Send one command to a Plus2 and return its notification, if any."""
        self._event = asyncio.Event()
        self._command_data = None
        await client.start_notify(
            RADON_CHARACTERISTIC_UUID_READ_OLDVERSION, self.notification_handler
        )
        await client.write_gatt_char(RADON_CHARACTERISTIC_UUID_WRITE_OLDVERSION, command)
        try:
            await asyncio.wait_for(self._event.wait(), 5)
        except asyncio.TimeoutError:
            self.logger.warning("Plus2: timeout waiting for reply to 0x%s", command.hex())
        await client.stop_notify(RADON_CHARACTERISTIC_UUID_READ_OLDVERSION)
        data, self._command_data = self._command_data, None
        return data

    async def _get_radon_plus2(
        self, client: BleakClient, device: RD200Device
    ) -> RD200Device:
        """Read a RadonEye Plus2 (RD200P2)."""
        data = await self._plus2_command(client, WRITE_VALUE)
        values = parse_plus2_measurement(data)
        radon_keys = ("radon", "radon_1day_level", "radon_1month_level", "radon_peak")
        if values is None:
            self.logger.warning(
                "Plus2: unexpected reply to 0x50: %s", data.hex() if data else None
            )
            for key in (*radon_keys, "radon_C_now", "radon_C_last"):
                device.sensors[key] = None
        else:
            for key in radon_keys:
                bq = float(values[key])
                device.sensors[key] = (
                    round(bq, 2) if self.is_metric
                    else round(bq * BQ_TO_PCI_MULTIPLIER, 2)
                )
            device.sensors["radon_C_now"] = values["radon_C_now"]
            device.sensors["radon_C_last"] = values["radon_C_last"]

        minutes = parse_plus2_uptime_minutes(await self._plus2_command(client, b"\x51"))
        if minutes is None:
            device.sensors["radon_uptime"] = None
            device.sensors["radon_uptime_string"] = None
        else:
            device.sensors["radon_uptime"] = minutes * 60
            device.sensors["radon_uptime_string"] = (
                f"{minutes // 1440}d {(minutes % 1440) // 60:02d}:{minutes % 60:02d}:00"
            )

        device.hw_version = "RD200P2"
        return device

    def _handle_disconnect(
        self, disconnect_future: asyncio.Future[bool], client: BleakClient
    ) -> None:
        """Handle disconnect from device."""
        self.logger.debug("Disconnected from %s", client.address)
        if not disconnect_future.done():
            disconnect_future.set_result(True)
            
    async def update_device(self, ble_device: BLEDevice) -> RD200Device:
        """Connects to the device through BLE and retrieves relevant data"""
        device = RD200Device()
        device.name = ble_device.name
        device.address = ble_device.address
        
        loop = asyncio.get_running_loop()
        disconnect_future = loop.create_future()
        client: BleakClientWithServiceCache = (
            await establish_connection(  # pylint: disable=line-too-long
                BleakClientWithServiceCache,
                ble_device,
                ble_device.address,
                # Look up disconnect_future when called, so it can be replaced below
                disconnected_callback=lambda client: self._handle_disconnect(
                    disconnect_future, client
                ),
            )
        )
        # establish_connection may retry internally (e.g. BlueZ
        # le-connection-abort-by-local), which fires the disconnect callback
        # before we are connected. Discard that stale result so interrupt()
        # does not abort the first GATT command of a healthy connection.
        if disconnect_future.done() and client.is_connected:
            disconnect_future = loop.create_future()
        try:
            async with (
                interrupt(
                    disconnect_future,
                    DisconnectedError,
                    f"Disconnected from {client.address}",
                ),
                asyncio.timeout(UPDATE_TIMEOUT),
            ):

                if ble_device.name.startswith(PLUS2_NAME_PREFIX):
                    device = await self._get_radon_plus2(client, device)
                elif ble_device.name.startswith("FR:R2"):
                    device = await self._get_radon_oldVersion(client, device)
                    device = await self._get_radon_peak_uptime_oldVersion(client, device)
                else:
                    device = await self._get_radon(client, device)
                    device = await self._get_radon_peak(client, device)
                    device = await self._get_radon_uptime(client, device)

        except BleakError as err:
            if "not found" in str(err):  # In future bleak this is a named exception
                # Clear the char cache since a char is likely
                # missing from the cache
                await client.clear_cache()
            raise
        except UnsupportedDeviceError:
            await client.disconnect()
            raise
        finally:
            await client.disconnect()

        return device
