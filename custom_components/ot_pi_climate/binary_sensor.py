"""Boiler status binary sensors."""

from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import OpenThermEntity
from .models import OpenThermConfigEntry


@dataclass(frozen=True, kw_only=True)
class OpenThermBinarySensorDescription(BinarySensorEntityDescription):
    data_key: str


BINARY_SENSORS = (
    OpenThermBinarySensorDescription(
        key="connected", translation_key="connected", data_key="Connected"
    ),
    OpenThermBinarySensorDescription(key="flame", translation_key="flame", data_key="Flame"),
    OpenThermBinarySensorDescription(key="fault", translation_key="fault", data_key="Fault"),
    OpenThermBinarySensorDescription(
        key="central_heating", translation_key="central_heating", data_key="Heating"
    ),
    OpenThermBinarySensorDescription(
        key="domestic_hot_water", translation_key="domestic_hot_water", data_key="DHW"
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenThermConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(OpenThermBinarySensor(entry, description) for description in BINARY_SENSORS)


class OpenThermBinarySensor(OpenThermEntity, BinarySensorEntity):
    entity_description: OpenThermBinarySensorDescription

    def __init__(
        self, entry: OpenThermConfigEntry, description: OpenThermBinarySensorDescription
    ) -> None:
        super().__init__(entry.runtime_data.coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        value = self.coordinator.data.get(self.entity_description.data_key)
        return None if value is None else bool(value)
