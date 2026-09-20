"""Boiler telemetry sensors."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import OpenThermEntity
from .models import OpenThermConfigEntry


@dataclass(frozen=True, kw_only=True)
class OpenThermSensorDescription(SensorEntityDescription):
    data_key: str


SENSORS = (
    OpenThermSensorDescription(
        key="water_temperature",
        translation_key="water_temperature",
        data_key="Tout",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OpenThermSensorDescription(
        key="return_temperature",
        translation_key="return_temperature",
        data_key="Tin",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OpenThermSensorDescription(
        key="modulation",
        translation_key="modulation",
        data_key="Modulation",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OpenThermSensorDescription(
        key="water_setpoint",
        translation_key="water_setpoint",
        data_key="CommandedSetpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenThermConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(OpenThermSensor(entry, description) for description in SENSORS)


class OpenThermSensor(OpenThermEntity, SensorEntity):
    entity_description: OpenThermSensorDescription

    def __init__(
        self, entry: OpenThermConfigEntry, description: OpenThermSensorDescription
    ) -> None:
        super().__init__(entry.runtime_data.coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)
