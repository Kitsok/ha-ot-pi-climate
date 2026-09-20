"""Shared entity base for OpenTherm PI Climate."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DOMAIN
from .coordinator import OpenThermCoordinator
from .models import OpenThermConfigEntry, merged_config


class OpenThermEntity(CoordinatorEntity[OpenThermCoordinator]):
    """Base entity linked to one OpenTherm gateway."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OpenThermCoordinator, entry: OpenThermConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=merged_config(entry)[CONF_NAME],
            manufacturer="Custom OpenTherm Gateway",
            model="OpenTherm PI controller",
        )
