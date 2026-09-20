"""Climate entity for OpenTherm PI Climate."""

from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import OpenThermEntity
from .models import OpenThermConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenThermConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([OpenThermClimate(entry)])


class OpenThermClimate(OpenThermEntity, ClimateEntity):
    """Room thermostat backed by the PI boiler controller."""

    _attr_name = None
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 35.0

    def __init__(self, entry: OpenThermConfigEntry) -> None:
        super().__init__(entry.runtime_data.coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_climate"

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.room_temperature

    @property
    def target_temperature(self) -> float:
        return self.coordinator.controller.target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        return self.coordinator.controller.hvac_mode

    @property
    def hvac_action(self) -> HVACAction:
        if self.hvac_mode == HVACMode.OFF and not self.coordinator.result.frost_protection_active:
            return HVACAction.OFF
        if self.coordinator.data and self.coordinator.data.get("Flame"):
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self.coordinator.result
        return {
            "water_setpoint": result.water_setpoint,
            "frost_protection_active": result.frost_protection_active,
            "sensor_failsafe_active": result.sensor_failsafe_active,
            "integral": round(self.coordinator.controller.integral, 3),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        self.coordinator.controller.target_temperature = float(temperature)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode not in self.hvac_modes:
            raise ValueError(f"Unsupported HVAC mode: {hvac_mode}")
        self.coordinator.controller.hvac_mode = hvac_mode
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
