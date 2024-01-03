"""Support for rd200 ble sensors."""
from __future__ import annotations

import logging
import dataclasses

from .rd200_ble import RD200Device

from homeassistant import config_entries
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_BILLION,
    CONCENTRATION_PARTS_PER_MILLION,
    LIGHT_LUX,
    PERCENTAGE,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util.unit_system import METRIC_SYSTEM

from .const import DOMAIN, VOLUME_BECQUEREL, VOLUME_PICOCURIE, COUNT_PULSES

_LOGGER = logging.getLogger(__name__)

SENSORS_MAPPING_TEMPLATE: dict[str, SensorEntityDescription] = {
    "radon": SensorEntityDescription(
        key="radon",
        native_unit_of_measurement=VOLUME_BECQUEREL,
        name="Radon",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radioactive",
    ),
    "radon_peak": SensorEntityDescription(
        key="radon_peak",
        native_unit_of_measurement=VOLUME_BECQUEREL,
        name="Radon Peak",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radioactive",
    ),
    "radon_C_now": SensorEntityDescription(
        key="radon_C_now",
        native_unit_of_measurement=COUNT_PULSES,
        name="Radon C pulse now",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radioactive-circle-outline",
    ),
    "radon_C_last": SensorEntityDescription(
        key="radon_C_last",
        native_unit_of_measurement=COUNT_PULSES,
        name="Radon C pulse last",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radioactive-circle-outline",
    ),
    "radon_1day_level": SensorEntityDescription(
        key="radon_1day_level",
        native_unit_of_measurement=VOLUME_BECQUEREL,
        name="Radon 1-day Level",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radioactive",
    ),
    "radon_1month_level": SensorEntityDescription(
        key="radon_1month_level",
        native_unit_of_measurement=VOLUME_BECQUEREL,
        name="Radon 1-month Level",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radioactive",
    ),
    "radon_uptime": SensorEntityDescription(
        key="radon_uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        name="Radon Uptime",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
    ),
    "radon_uptime_string": SensorEntityDescription(
        key="radon_uptime_string",
        name="Radon Uptime String",
        state_class=None,
        icon="mdi:timer-outline",
    ),
    "temperature": SensorEntityDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        name="Temperature",
    ),
    "humidity": SensorEntityDescription(
        key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        name="Humidity",
    ),
    "pressure": SensorEntityDescription(
        key="pressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.MBAR,
        name="Pressure",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the RD200 BLE sensors."""
    is_metric = hass.config.units is METRIC_SYSTEM

    coordinator: DataUpdateCoordinator[RD200Device] = hass.data[DOMAIN][entry.entry_id]

    # we need to change some units
    sensors_mapping = SENSORS_MAPPING_TEMPLATE.copy()
    if not is_metric:
        for key, val in sensors_mapping.items():
            if val.native_unit_of_measurement is not VOLUME_BECQUEREL:
                continue
            #val.native_unit_of_measurement = VOLUME_PICOCURIE
            sensors_mapping[key] = dataclasses.replace(
                val,
                native_unit_of_measurement=VOLUME_PICOCURIE,
            )

    entities = []
    _LOGGER.debug("got sensors: %s", coordinator.data.sensors)
    for sensor_type, sensor_value in coordinator.data.sensors.items():
        if sensor_type not in sensors_mapping:
            _LOGGER.debug(
                "Unknown sensor type detected: %s, %s",
                sensor_type,
                sensor_value,
            )
            continue
        entities.append(
            RD200Sensor(coordinator, coordinator.data, sensors_mapping[sensor_type])
        )

    async_add_entities(entities)


class RD200Sensor(CoordinatorEntity[DataUpdateCoordinator[RD200Device]], SensorEntity):
    """RD200 BLE sensors for the device."""

    ## Setting the Device State to None fixes Uptime String, Appears to override line: https://github.com/Makr91/rd200v2/blob/3d87d6e005f5efb7c143ff32256153c517ccade9/custom_components/rd200_ble/sensor.py#L78
    # Had to comment this line out to avoid it setting all state_class to none
    #_attr_state_class = None
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        rd200_device: RD200Device,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Populate the rd200 entity with relevant data."""
        super().__init__(coordinator)
        self.entity_description = entity_description

        name = f"{rd200_device.name} {rd200_device.identifier}"

        self._attr_unique_id = f"{name}_{entity_description.key}"

        self._id = rd200_device.address
        self._attr_device_info = DeviceInfo(
            connections={
                (
                    CONNECTION_BLUETOOTH,
                    rd200_device.address,
                )
            },
            name=name,
            manufacturer="FTLAB Co., LTD.",
            model="RD200",
            hw_version=rd200_device.hw_version,
            sw_version=rd200_device.sw_version,
        )

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        try:
            return self.coordinator.data.sensors[self.entity_description.key]
        except KeyError:
            return None
