"""Config flow for OpenTherm PI Climate."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_FAILSAFE_TEMP,
    CONF_FROST_TEMP,
    CONF_INITIAL_TARGET_TEMP,
    CONF_INTEGRAL_FACTOR,
    CONF_INTEGRAL_MAX,
    CONF_INTEGRAL_MIN,
    CONF_KP,
    CONF_MAX_WATER_TEMP,
    CONF_MIN_WATER_TEMP,
    CONF_NAME,
    CONF_SERIAL_PORT,
    CONF_TEMPERATURE_ENTITY,
    CONF_TI,
    DEFAULTS,
    DOMAIN,
)


def _schema(values: dict[str, Any]) -> vol.Schema:
    """Build the shared setup/options schema."""

    defaults = {**DEFAULTS, **values}
    number = selector.NumberSelector
    number_config = selector.NumberSelectorConfig
    temperature_entity = (
        vol.Required(
            CONF_TEMPERATURE_ENTITY,
            default=values[CONF_TEMPERATURE_ENTITY],
        )
        if CONF_TEMPERATURE_ENTITY in values
        else vol.Required(CONF_TEMPERATURE_ENTITY)
    )
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults[CONF_NAME]): selector.TextSelector(),
            vol.Required(
                CONF_SERIAL_PORT,
                default=values.get(CONF_SERIAL_PORT, "/dev/serial/by-id/"),
            ): selector.TextSelector(),
            temperature_entity: selector.EntitySelector(
                selector.EntitySelectorConfig(domain=Platform.SENSOR)
            ),
            vol.Required(CONF_KP, default=defaults[CONF_KP]): number(
                number_config(min=0, max=100, step=0.1, mode="box")
            ),
            vol.Required(CONF_TI, default=defaults[CONF_TI]): number(
                number_config(min=0.1, max=1000, step=0.1, mode="box")
            ),
            vol.Required(CONF_INTEGRAL_FACTOR, default=defaults[CONF_INTEGRAL_FACTOR]): number(
                number_config(min=0, max=10, step=0.1, mode="box")
            ),
            vol.Required(CONF_INTEGRAL_MIN, default=defaults[CONF_INTEGRAL_MIN]): number(
                number_config(min=-500, max=0, step=0.1, mode="box")
            ),
            vol.Required(CONF_INTEGRAL_MAX, default=defaults[CONF_INTEGRAL_MAX]): number(
                number_config(min=0, max=500, step=0.1, mode="box")
            ),
            vol.Required(CONF_MIN_WATER_TEMP, default=defaults[CONF_MIN_WATER_TEMP]): number(
                number_config(min=41, max=85, step=1, mode="box")
            ),
            vol.Required(CONF_MAX_WATER_TEMP, default=defaults[CONF_MAX_WATER_TEMP]): number(
                number_config(min=41, max=85, step=1, mode="box")
            ),
            vol.Required(CONF_FROST_TEMP, default=defaults[CONF_FROST_TEMP]): number(
                number_config(min=0, max=40, step=0.5, mode="box")
            ),
            vol.Required(CONF_FAILSAFE_TEMP, default=defaults[CONF_FAILSAFE_TEMP]): number(
                number_config(min=41, max=85, step=1, mode="box")
            ),
            vol.Required(
                CONF_INITIAL_TARGET_TEMP,
                default=defaults[CONF_INITIAL_TARGET_TEMP],
            ): number(number_config(min=5, max=35, step=0.5, mode="box")),
        }
    )


def _validate(values: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if values[CONF_MIN_WATER_TEMP] > values[CONF_MAX_WATER_TEMP]:
        errors["base"] = "invalid_water_range"
    elif values[CONF_FAILSAFE_TEMP] < values[CONF_MIN_WATER_TEMP]:
        errors["base"] = "invalid_failsafe"
    elif values[CONF_INTEGRAL_MIN] > values[CONF_INTEGRAL_MAX]:
        errors["base"] = "invalid_integral_range"
    return errors


class OpenThermConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an OpenTherm PI Climate config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                await self.async_set_unique_id(user_input[CONF_SERIAL_PORT])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
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
                return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(user_input or current),
            errors=errors,
        )
