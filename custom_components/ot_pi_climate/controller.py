"""PI room-temperature controller."""

import math
from dataclasses import dataclass
from typing import Any

from homeassistant.components.climate.const import HVACMode

from .const import (
    CONF_FAILSAFE_TEMP,
    CONF_FROST_TEMP,
    CONF_INTEGRAL_FACTOR,
    CONF_INTEGRAL_MAX,
    CONF_INTEGRAL_MIN,
    CONF_KP,
    CONF_MAX_WATER_TEMP,
    CONF_MIN_WATER_TEMP,
    CONF_TI,
    DEFAULTS,
    HEAT_THRESHOLD,
    OFF_WATER_TEMP,
    UPDATE_INTERVAL_SECONDS,
)


@dataclass(slots=True)
class ControllerResult:
    """Result of one controller calculation."""

    water_setpoint: int
    heating_requested: bool
    frost_protection_active: bool
    sensor_failsafe_active: bool


class PIController:
    """Preserve the legacy one-minute PI controller behavior."""

    def __init__(self, settings: dict[str, Any]) -> None:
        self.integral = 0.0
        self.target_temperature = float(settings["initial_target_temperature"])
        self.hvac_mode = HVACMode.HEAT
        self.last_output = OFF_WATER_TEMP
        self.update_settings(settings)

    def update_settings(self, settings: dict[str, Any]) -> None:
        """Apply config-entry settings."""

        values = {**DEFAULTS, **settings}
        self.kp = float(values[CONF_KP])
        self.ti = float(values[CONF_TI])
        self.integral_factor = float(values[CONF_INTEGRAL_FACTOR])
        self.integral_min = float(values[CONF_INTEGRAL_MIN])
        self.integral_max = float(values[CONF_INTEGRAL_MAX])
        self.min_water_temperature = float(values[CONF_MIN_WATER_TEMP])
        self.max_water_temperature = float(values[CONF_MAX_WATER_TEMP])
        self.frost_temperature = float(values[CONF_FROST_TEMP])
        self.failsafe_temperature = float(values[CONF_FAILSAFE_TEMP])

    def restore(self, state: dict[str, Any] | None) -> None:
        """Restore persisted controller state."""

        if not state:
            return
        self.integral = min(
            self.integral_max,
            max(self.integral_min, float(state.get("integral", 0.0))),
        )
        self.target_temperature = float(state.get("target_temperature", self.target_temperature))
        try:
            self.hvac_mode = HVACMode(state.get("hvac_mode", HVACMode.HEAT))
        except ValueError:
            self.hvac_mode = HVACMode.HEAT

    def as_dict(self) -> dict[str, Any]:
        """Return persistent controller state."""

        return {
            "integral": self.integral,
            "target_temperature": self.target_temperature,
            "hvac_mode": self.hvac_mode,
        }

    def calculate(
        self,
        room_temperature: float | None,
        water_temperature: float | None,
        *,
        elapsed_seconds: float = UPDATE_INTERVAL_SECONDS,
    ) -> ControllerResult:
        """Calculate output, scaling the integral by elapsed time in minutes."""

        if room_temperature is not None and not math.isfinite(room_temperature):
            room_temperature = None
        if water_temperature is not None and not math.isfinite(water_temperature):
            water_temperature = None

        sensor_failsafe = room_temperature is None and self.hvac_mode == HVACMode.HEAT
        frost_active = water_temperature is not None and water_temperature < self.frost_temperature

        if sensor_failsafe:
            calculated = self.failsafe_temperature
            heating = True
        elif self.hvac_mode == HVACMode.OFF:
            calculated = float(OFF_WATER_TEMP)
            heating = False
        else:
            error = self.target_temperature - room_temperature
            self.integral += error * self.integral_factor * elapsed_seconds / UPDATE_INTERVAL_SECONDS
            self.integral = min(self.integral_max, max(self.integral_min, self.integral))
            calculated = self.kp * (error + self.integral / self.ti) + 40.0
            heating = calculated > HEAT_THRESHOLD

        if frost_active:
            calculated = max(calculated, self.min_water_temperature)
            heating = True

        if heating:
            calculated = min(
                self.max_water_temperature,
                max(self.min_water_temperature, calculated),
            )
            output = round(calculated)
        else:
            output = OFF_WATER_TEMP

        self.last_output = output
        return ControllerResult(output, heating, frost_active, sensor_failsafe)
