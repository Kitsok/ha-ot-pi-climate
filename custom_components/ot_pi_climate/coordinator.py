"""Update coordinator for OpenTherm PI Climate."""

import logging
import math
import time
from datetime import timedelta
from typing import Any

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import CONF_UPDATE_INTERVAL
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
            update_interval=timedelta(seconds=controller.settings[CONF_UPDATE_INTERVAL]),
        )
        self.gateway = gateway
        self.controller = controller
        self.temperature_entity = temperature_entity
        self.result = ControllerResult(controller.off_water_temperature, False, False, False)
        self._last_calculation: float | None = None

    @property
    def room_temperature(self) -> float | None:
        """Return the configured room sensor value, or None when unavailable."""

        state = self.hass.states.get(self.temperature_entity)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            temperature = float(state.state)
        except (TypeError, ValueError):
            return None
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if not math.isfinite(temperature) or unit not in (
            UnitOfTemperature.CELSIUS,
            UnitOfTemperature.FAHRENHEIT,
            UnitOfTemperature.KELVIN,
        ):
            return None
        return TemperatureConverter.convert(temperature, unit, UnitOfTemperature.CELSIUS)

    async def _async_update_data(self) -> dict[str, Any]:
        previous_water_temperature = None
        if self.data is not None:
            try:
                previous_water_temperature = float(self.data["Tout"])
            except (KeyError, TypeError, ValueError):
                pass

        now = time.monotonic()
        elapsed_seconds = 0.0 if self._last_calculation is None else now - self._last_calculation
        self._last_calculation = now
        self.result = self.controller.calculate(
            self.room_temperature, previous_water_temperature, elapsed_seconds=elapsed_seconds
        )
        try:
            return await self.gateway.async_update(self.result.water_setpoint)
        except OpenThermGatewayError as err:
            raise UpdateFailed(str(err)) from err
