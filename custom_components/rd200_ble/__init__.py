"""The RD200 BLE integration."""
from __future__ import annotations

import dataclasses
from datetime import timedelta
import logging
from typing import Any

from .rd200_ble import RD200BluetoothDeviceData, RD200Device

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import METRIC_SYSTEM
from bleak_retry_connector import close_stale_connections_by_address

from .const import (
    CONF_KEEP_LAST_VALID_VALUE,
    CONF_MAX_CACHE_AGE_HOURS,
    DEFAULT_KEEP_LAST_VALID_VALUE,
    DEFAULT_MAX_CACHE_AGE_HOURS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

PLATFORMS: list[Platform] = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RD200 BLE device from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    address = entry.unique_id

    elevation = hass.config.elevation
    is_metric = hass.config.units is METRIC_SYSTEM
    assert address is not None
    store = Store[dict[str, Any]](hass, 1, f"{DOMAIN}.{entry.entry_id}")
    cached_data = await store.async_load()

    def _cache_enabled() -> bool:
        return entry.options.get(
            CONF_KEEP_LAST_VALID_VALUE, DEFAULT_KEEP_LAST_VALID_VALUE
        )

    def _cache_expired() -> bool:
        if cached_data is None or cached_data.get("last_valid_update") is None:
            return False
        max_age = entry.options.get(
            CONF_MAX_CACHE_AGE_HOURS, DEFAULT_MAX_CACHE_AGE_HOURS
        )
        if not max_age:
            return False
        last_update = dt_util.parse_datetime(cached_data["last_valid_update"])
        return last_update is None or dt_util.utcnow() - last_update > timedelta(
            hours=max_age
        )

    def _cached_device() -> RD200Device | None:
        if cached_data is None:
            return None
        try:
            return RD200Device(**cached_data)
        except (TypeError, ValueError):
            _LOGGER.warning("Ignoring invalid cached data for %s", address)
            return None

    def _unknown_cached_device(cached_device: RD200Device) -> RD200Device:
        return dataclasses.replace(
            cached_device,
            sensors={key: None for key in cached_device.sensors},
        )

    await close_stale_connections_by_address(address)
    
    ble_device = bluetooth.async_ble_device_from_address(hass, address)

    if not ble_device and not (_cache_enabled() and _cached_device()):
        raise ConfigEntryNotReady(f"Could not find RD200 device with address {address}")

    async def _async_update_method() -> RD200Device:
        """Get data from RD200 BLE."""
        nonlocal cached_data
        ble_device = bluetooth.async_ble_device_from_address(hass, address)
        rd200 = RD200BluetoothDeviceData(_LOGGER, elevation, is_metric)

        try:
            if ble_device is None:
                raise RuntimeError("Bluetooth device is not currently available")
            data = await rd200.update_device(ble_device)
        except Exception as err:
            cached_device = _cached_device()
            if _cache_enabled() and cached_device is not None:
                if _cache_expired():
                    _LOGGER.warning("Cached data for %s has expired", address)
                    return _unknown_cached_device(cached_device)
                _LOGGER.warning("Using cached data for %s after update error: %s", address, err)
                return cached_device
            raise UpdateFailed(f"Unable to fetch data: {err}") from err

        valid_sensors = {
            key: value for key, value in data.sensors.items() if value is not None
        }
        if not valid_sensors:
            cached_device = _cached_device()
            if _cache_enabled() and cached_device is not None:
                if _cache_expired():
                    return _unknown_cached_device(cached_device)
                _LOGGER.warning("Using cached data for %s after an empty update", address)
                return cached_device
            return data

        cached_device = _cached_device()
        merged_sensors = cached_device.sensors.copy() if cached_device else {}
        merged_sensors.update(valid_sensors)
        cached_data = dataclasses.asdict(
            dataclasses.replace(
                data,
                name=data.name or (cached_device.name if cached_device else ""),
                identifier=data.identifier
                or (cached_device.identifier if cached_device else ""),
                hw_version=data.hw_version
                or (cached_device.hw_version if cached_device else ""),
                sw_version=data.sw_version
                or (cached_device.sw_version if cached_device else ""),
                last_valid_update=dt_util.utcnow().isoformat(),
                sensors=merged_sensors,
            )
        )
        await store.async_save(cached_data)

        if _cache_enabled():
            return RD200Device(**cached_data)
        return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_async_update_method,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
