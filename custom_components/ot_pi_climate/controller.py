"""PI room-temperature controller."""

import math
from dataclasses import dataclass
from typing import Any

from homeassistant.components.climate.const import HVACMode

from . import const as c


@dataclass(slots=True)
class ControllerResult:
    """Result of one controller calculation."""

    water_setpoint: int
    heating_requested: bool
    frost_protection_active: bool
    sensor_failsafe_active: bool


class PIController:
    """Calculate boiler demand using configurable PI and fallback policies."""

    def __init__(self, settings: dict[str, Any]) -> None:
        self.update_settings(settings)
        self.integral = self.initial_integral
        self.target_temperature = self.initial_target_temperature
        self.hvac_mode = self.initial_hvac_mode
        self.last_output = self.off_water_temperature

    def update_settings(self, settings: dict[str, Any]) -> None:
        """Apply config-entry settings, including defaults for older entries."""

        self.settings = values = {**c.DEFAULTS, **settings}
        self.kp = float(values[c.CONF_KP])
        self.ti = float(values[c.CONF_TI])
        self.integral_factor = float(values[c.CONF_INTEGRAL_FACTOR])
        self.integral_min = float(values[c.CONF_INTEGRAL_MIN])
        self.integral_max = float(values[c.CONF_INTEGRAL_MAX])
        self.min_water_temperature = float(values[c.CONF_MIN_WATER_TEMP])
        self.max_water_temperature = float(values[c.CONF_MAX_WATER_TEMP])
        self.frost_temperature = float(values[c.CONF_FROST_TEMP])
        self.failsafe_temperature = float(values[c.CONF_FAILSAFE_TEMP])
        self.off_water_temperature = int(values[c.CONF_OFF_WATER_TEMP])
        self.heat_threshold = float(values[c.CONF_HEAT_THRESHOLD])
        self.output_baseline = float(values[c.CONF_OUTPUT_BASELINE])
        self.water_temperature_step = int(values[c.CONF_WATER_TEMP_STEP])
        self.target_min = float(values[c.CONF_TARGET_MIN])
        self.target_max = float(values[c.CONF_TARGET_MAX])
        self.target_step = float(values[c.CONF_TARGET_STEP])
        self.hvac_modes = [HVACMode(mode) for mode in values[c.CONF_HVAC_MODES]]
        self.initial_hvac_mode = HVACMode(values[c.CONF_INITIAL_HVAC_MODE])
        self.initial_integral = self.clamp_integral(float(values[c.CONF_INITIAL_INTEGRAL]))
        self.initial_target_temperature = self.clamp_target(
            float(values[c.CONF_INITIAL_TARGET_TEMP])
        )
        self.restore_state = bool(values[c.CONF_RESTORE_STATE])
        self.frost_enabled = bool(values[c.CONF_FROST_ENABLED])
        self.frost_override_off = bool(values[c.CONF_FROST_OVERRIDE_OFF])
        frost_target = values[c.CONF_FROST_TARGET]
        self.frost_target = (
            self.min_water_temperature if frost_target is None else float(frost_target)
        )
        self.frost_source = values[c.CONF_FROST_SOURCE]
        self.sensor_failure_action = values[c.CONF_SENSOR_FAILURE_ACTION]

    def clamp_integral(self, value: float) -> float:
        return min(self.integral_max, max(self.integral_min, value))

    def clamp_target(self, value: float) -> float:
        return min(self.target_max, max(self.target_min, value))

    def restore(self, state: dict[str, Any] | None) -> None:
        """Restore saved state within the current limits and enabled modes."""

        if not state or not self.restore_state:
            return
        self.integral = self.clamp_integral(float(state.get("integral", self.initial_integral)))
        self.target_temperature = self.clamp_target(
            float(state.get("target_temperature", self.initial_target_temperature))
        )
        try:
            mode = HVACMode(state.get("hvac_mode", self.initial_hvac_mode))
        except ValueError:
            mode = self.initial_hvac_mode
        self.hvac_mode = mode if mode in self.hvac_modes else self.initial_hvac_mode

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
        elapsed_seconds: float = c.INTEGRAL_TIMEBASE_SECONDS,
    ) -> ControllerResult:
        """Calculate output, scaling the integral by elapsed time in minutes."""

        if room_temperature is not None and not math.isfinite(room_temperature):
            room_temperature = None
        if water_temperature is not None and not math.isfinite(water_temperature):
            water_temperature = None

        sensor_failsafe = room_temperature is None and self.hvac_mode == HVACMode.HEAT
        frost_reading = water_temperature if self.frost_source == "water" else room_temperature
        frost_active = (
            self.frost_enabled
            and (self.hvac_mode != HVACMode.OFF or self.frost_override_off)
            and frost_reading is not None
            and frost_reading < self.frost_temperature
        )

        if sensor_failsafe:
            if self.sensor_failure_action == "heat":
                calculated = self.failsafe_temperature
                heating = True
            elif self.sensor_failure_action == "hold":
                calculated = float(self.last_output)
                heating = self.last_output != self.off_water_temperature
            else:
                calculated = float(self.off_water_temperature)
                heating = False
        elif self.hvac_mode == HVACMode.OFF:
            calculated = float(self.off_water_temperature)
            heating = False
        else:
            error = self.target_temperature - room_temperature
            self.integral = self.clamp_integral(
                self.integral
                + error * self.integral_factor * elapsed_seconds / c.INTEGRAL_TIMEBASE_SECONDS
            )
            calculated = self.kp * (error + self.integral / self.ti) + self.output_baseline
            heating = calculated > self.heat_threshold

        if frost_active:
            calculated = max(calculated, self.frost_target)
            heating = True

        if heating:
            calculated = min(
                self.max_water_temperature,
                max(self.min_water_temperature, calculated),
            )
            # Quantize within the limits; endpoints take priority over the step.
            output = int(
                min(
                    math.floor(self.max_water_temperature),
                    max(
                        math.ceil(self.min_water_temperature),
                        round(calculated / self.water_temperature_step)
                        * self.water_temperature_step,
                    ),
                )
            )
        else:
            output = self.off_water_temperature

        self.last_output = output
        return ControllerResult(output, heating, frost_active, sensor_failsafe)
