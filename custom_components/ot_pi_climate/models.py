"""Runtime models for OpenTherm PI Climate."""

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import DEFAULTS
from .controller import PIController
from .coordinator import OpenThermCoordinator
from .gateway import OpenThermGateway


@dataclass(slots=True)
class OpenThermRuntimeData:
    """Runtime data stored on a config entry."""

    gateway: OpenThermGateway
    controller: PIController
    coordinator: OpenThermCoordinator


type OpenThermConfigEntry = ConfigEntry[OpenThermRuntimeData]


def merged_config(entry: ConfigEntry[Any]) -> dict[str, Any]:
    """Return config-entry data with options taking precedence."""

    return {**DEFAULTS, **entry.data, **entry.options}
