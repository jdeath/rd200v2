"""Exercise RD200 unit selection using Home Assistant's real sensor machinery."""

from datetime import timedelta
import importlib
import logging
from types import SimpleNamespace

import pytest
import pytest_asyncio

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from custom_components.rd200_ble import sensor as sensor_module
from custom_components.rd200_ble.const import DOMAIN
from custom_components.rd200_ble.rd200_ble import RD200Device

RADON_KEYS = ("radon", "radon_peak", "radon_1day_level", "radon_1month_level")
HAS_RADON = hasattr(SensorDeviceClass, "RADON")
LOGGER = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def hass(tmp_path):
    """Use an isolated registry; no Bluetooth connection is needed."""
    instance = HomeAssistant(str(tmp_path))
    if hasattr(dr, "async_setup"):
        dr.async_setup(instance)
    await dr.async_load(instance, load_empty=True)
    await er.async_load(instance, load_empty=True)
    yield instance
    await instance.async_stop()


async def make_sensors(hass, units):
    """Run the integration's sensor setup with readings in its native units."""
    hass.config.units = units
    coordinator = DataUpdateCoordinator(hass, LOGGER, name=DOMAIN, config_entry=None)
    value = 148.0 if units is METRIC_SYSTEM else 4.0
    coordinator.data = RD200Device(
        name="RD200",
        identifier="FR:TEST",
        address="00:11:22:33:44:55",
        sensors={
            **dict.fromkeys(RADON_KEYS, value),
            "radon_C_now": 12,
            "radon_C_last": 11,
            "radon_uptime": 3600,
            "radon_uptime_string": "0d 01:00:00",
        },
        last_valid_update="2026-09-11T12:00:00+00:00",
    )
    hass.data[DOMAIN] = {"test": coordinator}
    sensors = []
    await sensor_module.async_setup_entry(
        hass, SimpleNamespace(entry_id="test"), sensors.extend
    )
    platform = EntityPlatform(
        hass=hass,
        logger=LOGGER,
        domain="sensor",
        platform_name=DOMAIN,
        platform=None,
        scan_interval=timedelta(minutes=10),
        entity_namespace=None,
    )
    return {entity.entity_description.key: entity for entity in sensors}, platform


def register_sensor(hass, platform, entity):
    """Run HA's unit migration and registry-option initialization."""
    entity.add_to_platform_start(hass, platform, None)
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        entity.unique_id,
        unit_of_measurement=entity.unit_of_measurement,
        original_device_class=entity.device_class,
        get_initial_options=entity.get_initial_entity_options,
    )
    entity.entity_id = entry.entity_id
    entity.registry_entry = entry
    entity.async_registry_entry_updated()
    return entry


@pytest.mark.asyncio
@pytest.mark.parametrize("units", [METRIC_SYSTEM, US_CUSTOMARY_SYSTEM])
@pytest.mark.parametrize("key", RADON_KEYS)
async def test_default_units_and_unrelated_sensors(hass, units, key):
    sensors, platform = await make_sensors(hass, units)
    entity = sensors[key]
    register_sensor(hass, platform, entity)
    assert entity.unit_of_measurement == (
        "Bq/m³" if units is METRIC_SYSTEM else "pCi/L"
    )
    assert entity.state == (148.0 if units is METRIC_SYSTEM else 4.0)
    assert entity.device_class == getattr(SensorDeviceClass, "RADON", None)
    for other_key in (
        "radon_C_now",
        "radon_C_last",
        "radon_uptime",
        "radon_uptime_string",
    ):
        assert sensors[other_key].device_class is None


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_RADON, reason="Native radon conversion needs HA 2026.8+")
@pytest.mark.parametrize(
    "units,target,expected",
    [
        (METRIC_SYSTEM, "pCi/L", 4.0),
        (US_CUSTOMARY_SYSTEM, "Bq/m³", 148.0),
    ],
)
@pytest.mark.parametrize("key", RADON_KEYS)
async def test_override_survives_reload_and_preserves_native_data(
    hass, units, target, expected, key
):
    sensors, platform = await make_sensors(hass, units)
    entity = sensors[key]
    entry = register_sensor(hass, platform, entity)
    registry = er.async_get(hass)
    entity.registry_entry = registry.async_update_entity_options(
        entry.entity_id, "sensor", {"unit_of_measurement": target}
    )
    entity.async_registry_entry_updated()
    assert entity.unit_of_measurement == target
    assert entity.state == pytest.approx(expected)
    assert entity.native_value == (148.0 if units is METRIC_SYSTEM else 4.0)
    assert entity.extra_state_attributes == {
        "last_valid_update": "2026-09-11T12:00:00+00:00"
    }

    # Recreate the integration entities with the same persisted registry options.
    sensors, platform = await make_sensors(hass, units)
    reloaded = sensors[key]
    reloaded.add_to_platform_start(hass, platform, None)
    assert reloaded.unique_id == entity.unique_id
    assert reloaded.unit_of_measurement == target
    assert reloaded.state == pytest.approx(expected)
    reloaded.coordinator.data.sensors[key] = None
    assert reloaded.state is None


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_RADON, reason="Native radon conversion needs HA 2026.8+")
@pytest.mark.parametrize("old_unit,expected", [("Bq/m³", 148.0), ("pCi/L", 4.0)])
async def test_upgrade_preserves_existing_entity_units(hass, old_unit, expected):
    sensors, platform = await make_sensors(hass, METRIC_SYSTEM)
    entity = sensors["radon"]
    registry = er.async_get(hass)
    old_entry = registry.async_get_or_create(
        "sensor", DOMAIN, entity.unique_id, unit_of_measurement=old_unit
    )
    entity.add_to_platform_start(hass, platform, None)
    assert entity.unit_of_measurement == old_unit
    assert entity.state == pytest.approx(expected)
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, entity.unique_id)
        == old_entry.entity_id
    )


def test_import_without_radon_device_class(monkeypatch):
    """Simulate pre-2026.8 enums even when running the latest HA version."""
    import homeassistant.components.sensor as ha_sensor

    legacy_classes = SimpleNamespace(
        TEMPERATURE=SensorDeviceClass.TEMPERATURE,
        HUMIDITY=SensorDeviceClass.HUMIDITY,
        PRESSURE=SensorDeviceClass.PRESSURE,
    )
    try:
        with monkeypatch.context() as patch:
            patch.setattr(ha_sensor, "SensorDeviceClass", legacy_classes)
            importlib.reload(sensor_module)
            assert all(
                sensor_module.SENSORS_MAPPING_TEMPLATE[key].device_class is None
                for key in RADON_KEYS
            )
    finally:
        importlib.reload(sensor_module)
