"""Config flow for OpenTherm PI Climate."""

import math
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import const as c

# Only protocol constraints and mathematical requirements impose numeric bounds.
# PI tuning and frost thresholds no longer have arbitrary UI caps or increments.
NUMBERS = (
    (c.CONF_KP, 0, None, "any"),
    (c.CONF_TI, None, None, "any"),
    (c.CONF_INTEGRAL_FACTOR, 0, None, "any"),
    (c.CONF_INTEGRAL_MIN, None, None, "any"),
    (c.CONF_INTEGRAL_MAX, None, None, "any"),
    (c.CONF_MIN_WATER_TEMP, 41, 85, 1),
    (c.CONF_MAX_WATER_TEMP, 41, 85, 1),
    (c.CONF_FROST_TEMP, None, None, "any"),
    (c.CONF_FAILSAFE_TEMP, 41, 85, 1),
    (c.CONF_INITIAL_TARGET_TEMP, None, None, "any"),
    (c.CONF_UPDATE_INTERVAL, None, None, "any"),
    (c.CONF_BAUD_RATE, 1, None, 1),
    (c.CONF_COMMAND_TIMEOUT, None, None, "any"),
    (c.CONF_COMMAND_ATTEMPTS, 1, None, 1),
    (c.CONF_OFF_WATER_TEMP, 1, 40, 1),
    (c.CONF_HEAT_THRESHOLD, None, None, "any"),
    (c.CONF_OUTPUT_BASELINE, None, None, "any"),
    (c.CONF_WATER_TEMP_STEP, 1, None, 1),
    (c.CONF_TARGET_MIN, None, None, "any"),
    (c.CONF_TARGET_MAX, None, None, "any"),
    (c.CONF_TARGET_STEP, None, None, "any"),
    (c.CONF_INITIAL_INTEGRAL, None, None, "any"),
    (c.CONF_FROST_TARGET, 41, 85, 1),
)
CHOICES = {
    c.CONF_HVAC_MODES: ["heat", "off"],
    c.CONF_INITIAL_HVAC_MODE: ["heat", "off"],
    c.CONF_FROST_SOURCE: ["water", "room"],
    c.CONF_SENSOR_FAILURE_ACTION: ["heat", "off", "hold"],
    c.CONF_DTR_ON_OPEN: ["unchanged", "low", "high"],
    c.CONF_DTR_ON_CLOSE: ["unchanged", "low", "high"],
    c.CONF_RTS_ON_OPEN: ["unchanged", "low", "high"],
    c.CONF_RTS_ON_CLOSE: ["unchanged", "low", "high"],
}
BOOLEANS = (c.CONF_RESTORE_STATE, c.CONF_FROST_ENABLED, c.CONF_FROST_OVERRIDE_OFF)


def _schema(values: dict[str, Any]) -> vol.Schema:
    """Build the shared setup/options schema."""

    defaults = {**c.DEFAULTS, **values}
    temperature_entity = (
        vol.Required(c.CONF_TEMPERATURE_ENTITY, default=values[c.CONF_TEMPERATURE_ENTITY])
        if c.CONF_TEMPERATURE_ENTITY in values
        else vol.Required(c.CONF_TEMPERATURE_ENTITY)
    )
    fields = {
        vol.Required(c.CONF_NAME, default=defaults[c.CONF_NAME]): selector.TextSelector(),
        vol.Required(
            c.CONF_SERIAL_PORT, default=values.get(c.CONF_SERIAL_PORT, "/dev/serial/by-id/")
        ): selector.TextSelector(),
        temperature_entity: selector.EntitySelector(
            selector.EntitySelectorConfig(domain=Platform.SENSOR)
        ),
    }
    for key, minimum, maximum, step in NUMBERS:
        config = {"step": step, "mode": "box"}
        if minimum is not None:
            config["min"] = minimum
        if maximum is not None:
            config["max"] = maximum
        if key == c.CONF_FROST_TARGET:
            field = vol.Optional(key, description={"suggested_value": defaults[key]})
        else:
            field = vol.Required(key, default=defaults[key])
        fields[field] = selector.NumberSelector(selector.NumberSelectorConfig(**config))
    for key, choices in CHOICES.items():
        fields[vol.Required(key, default=defaults[key])] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=choices,
                multiple=key == c.CONF_HVAC_MODES,
                translation_key=key,
            )
        )
    for key in BOOLEANS:
        fields[vol.Required(key, default=defaults[key])] = selector.BooleanSelector()
    return vol.Schema(fields)


def _validate(values: dict[str, Any]) -> dict[str, str]:
    """Validate relationships as well as positive, finite protocol values."""

    values = {**c.DEFAULTS, **values}
    errors: dict[str, str] = {}
    for key, minimum, maximum, step in NUMBERS:
        value = values[key]
        if key == c.CONF_FROST_TARGET and value is None:
            continue
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            errors[key] = "invalid_number"
        elif (
            (minimum is not None and value < minimum)
            or (maximum is not None and value > maximum)
            or (step == 1 and value != int(value))
        ):
            errors[key] = "invalid_number"
    if errors:
        return errors
    for key in (c.CONF_TI, c.CONF_UPDATE_INTERVAL, c.CONF_COMMAND_TIMEOUT, c.CONF_TARGET_STEP):
        if values[key] <= 0:
            errors[key] = "must_be_positive"
    if values[c.CONF_MIN_WATER_TEMP] > values[c.CONF_MAX_WATER_TEMP]:
        errors["base"] = "invalid_water_range"
    if (
        not values[c.CONF_MIN_WATER_TEMP]
        <= values[c.CONF_FAILSAFE_TEMP]
        <= values[c.CONF_MAX_WATER_TEMP]
    ):
        errors[c.CONF_FAILSAFE_TEMP] = "invalid_failsafe"
    frost_target = values[c.CONF_FROST_TARGET]
    if frost_target is not None and not (
        values[c.CONF_MIN_WATER_TEMP] <= frost_target <= values[c.CONF_MAX_WATER_TEMP]
    ):
        errors[c.CONF_FROST_TARGET] = "invalid_frost_target"
    if values[c.CONF_INTEGRAL_MIN] > values[c.CONF_INTEGRAL_MAX]:
        errors["base"] = "invalid_integral_range"
    if (
        not values[c.CONF_INTEGRAL_MIN]
        <= values[c.CONF_INITIAL_INTEGRAL]
        <= values[c.CONF_INTEGRAL_MAX]
    ):
        errors[c.CONF_INITIAL_INTEGRAL] = "invalid_initial_integral"
    if values[c.CONF_TARGET_MIN] >= values[c.CONF_TARGET_MAX]:
        errors["base"] = "invalid_target_range"
    if (
        not values[c.CONF_TARGET_MIN]
        <= values[c.CONF_INITIAL_TARGET_TEMP]
        <= values[c.CONF_TARGET_MAX]
    ):
        errors[c.CONF_INITIAL_TARGET_TEMP] = "invalid_initial_target"
    if values[c.CONF_TARGET_STEP] > values[c.CONF_TARGET_MAX] - values[c.CONF_TARGET_MIN]:
        errors[c.CONF_TARGET_STEP] = "invalid_target_step"
    for key, choices in CHOICES.items():
        selected = values[key] if key == c.CONF_HVAC_MODES else [values[key]]
        if (
            not isinstance(selected, list)
            or not selected
            or any(v not in choices for v in selected)
        ):
            errors[key] = "invalid_choice"
    if values[c.CONF_INITIAL_HVAC_MODE] not in values[c.CONF_HVAC_MODES]:
        errors[c.CONF_INITIAL_HVAC_MODE] = "invalid_initial_mode"
    return errors


class OpenThermConfigFlow(config_entries.ConfigFlow, domain=c.DOMAIN):
    """Handle an OpenTherm PI Climate config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                await self.async_set_unique_id(user_input[c.CONF_SERIAL_PORT])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[c.CONF_NAME], data={**c.DEFAULTS, **user_input}
                )
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "OpenThermOptionsFlow":
        return OpenThermOptionsFlow()


class OpenThermOptionsFlow(config_entries.OptionsFlow):
    """Edit every integration setting from the UI."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(title="", data={**c.DEFAULTS, **user_input})
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(user_input or current),
            errors=errors,
        )
