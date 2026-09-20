"""Constants for the OpenTherm PI Climate integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "ot_pi_climate"
PLATFORMS: Final = [Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.SENSOR]

CONF_SERIAL_PORT: Final = "serial_port"
CONF_TEMPERATURE_ENTITY: Final = "temperature_entity"
CONF_NAME: Final = "name"
CONF_KP: Final = "kp"
CONF_TI: Final = "ti"
CONF_INTEGRAL_FACTOR: Final = "integral_factor"
CONF_INTEGRAL_MIN: Final = "integral_min"
CONF_INTEGRAL_MAX: Final = "integral_max"
CONF_MIN_WATER_TEMP: Final = "min_water_temperature"
CONF_MAX_WATER_TEMP: Final = "max_water_temperature"
CONF_FROST_TEMP: Final = "frost_temperature"
CONF_FAILSAFE_TEMP: Final = "failsafe_temperature"
CONF_INITIAL_TARGET_TEMP: Final = "initial_target_temperature"

DEFAULTS: Final = {
    CONF_NAME: "OpenTherm PI Climate",
    CONF_KP: 20.6,
    CONF_TI: 105.2,
    CONF_INTEGRAL_FACTOR: 0.8,
    CONF_INTEGRAL_MIN: -5.0,
    CONF_INTEGRAL_MAX: 90.0,
    CONF_MIN_WATER_TEMP: 41.0,
    CONF_MAX_WATER_TEMP: 75.0,
    CONF_FROST_TEMP: 22.0,
    CONF_FAILSAFE_TEMP: 60.0,
    CONF_INITIAL_TARGET_TEMP: 20.0,
}

OFF_WATER_TEMP: Final = 39
HEAT_THRESHOLD: Final = 40.0
BAUD_RATE: Final = 115200
COMMAND_TIMEOUT: Final = 2.0
COMMAND_RETRIES: Final = 5
UPDATE_INTERVAL_SECONDS: Final = 60
