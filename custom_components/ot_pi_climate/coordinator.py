"""Update coordinator for OpenTherm PI Climate."""

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import UPDATE_INTERVAL_SECONDS
from .controller import ControllerResult, PIController
from .gateway import OpenThermGateway, OpenThermGatewayError

_LOGGER = logging.getLogger(__name__)


class OpenThermCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate the minute heartbeat, PI calculation, and telemetry poll."""

    def __init__(
        self,
        hass: HomeAssistant,
        gateway: OpenThermGateway,
        controller: PIController,
        temperature_entity: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="OpenTherm PI Climate",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.gateway = gateway
        self.controller = controller
        self.temperature_entity = temperature_entity
        self.result = ControllerResult(39, False, False, False)

    @property
    def room_temperature(self) -> float | None:
        """Return the configured room sensor value, or None when unavailable."""

        state = self.hass.states.get(self.temperature_entity)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        previous_water_temperature = None
        if self.data is not None:
            try:
                previous_water_temperature = float(self.data["Tout"])
            except (KeyError, TypeError, ValueError):
                pass

        self.result = self.controller.calculate(self.room_temperature, previous_water_temperature)
        try:
            return await self.gateway.async_update(self.result.water_setpoint)
        except OpenThermGatewayError as err:
            raise UpdateFailed(str(err)) from err
