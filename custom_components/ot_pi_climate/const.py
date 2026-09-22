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

CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_BAUD_RATE: Final = "baud_rate"
CONF_COMMAND_TIMEOUT: Final = "command_timeout"
CONF_COMMAND_ATTEMPTS: Final = "command_attempts"
CONF_OFF_WATER_TEMP: Final = "off_water_temperature"
CONF_HEAT_THRESHOLD: Final = "heat_threshold"
CONF_OUTPUT_BASELINE: Final = "output_baseline"
CONF_WATER_TEMP_STEP: Final = "water_temperature_step"
CONF_TARGET_MIN: Final = "target_temperature_min"
CONF_TARGET_MAX: Final = "target_temperature_max"
CONF_TARGET_STEP: Final = "target_temperature_step"
CONF_HVAC_MODES: Final = "hvac_modes"
CONF_INITIAL_HVAC_MODE: Final = "initial_hvac_mode"
CONF_INITIAL_INTEGRAL: Final = "initial_integral"
CONF_RESTORE_STATE: Final = "restore_state"
CONF_FROST_ENABLED: Final = "frost_enabled"
CONF_FROST_OVERRIDE_OFF: Final = "frost_override_off"
CONF_FROST_TARGET: Final = "frost_target"
CONF_FROST_SOURCE: Final = "frost_source"
CONF_SENSOR_FAILURE_ACTION: Final = "sensor_failure_action"
CONF_DTR_ON_OPEN: Final = "dtr_on_open"
CONF_DTR_ON_CLOSE: Final = "dtr_on_close"
CONF_RTS_ON_OPEN: Final = "rts_on_open"
CONF_RTS_ON_CLOSE: Final = "rts_on_close"

# Legacy defaults retained for existing entries and protocol tests.
OFF_WATER_TEMP: Final = 39
HEAT_THRESHOLD: Final = 40.0
BAUD_RATE: Final = 115200
COMMAND_TIMEOUT: Final = 2.0
COMMAND_RETRIES: Final = 5
UPDATE_INTERVAL_SECONDS: Final = 60
# PI tuning remains per minute, independently of the polling interval.
INTEGRAL_TIMEBASE_SECONDS: Final = 60

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
    CONF_UPDATE_INTERVAL: UPDATE_INTERVAL_SECONDS,
    CONF_BAUD_RATE: BAUD_RATE,
    CONF_COMMAND_TIMEOUT: COMMAND_TIMEOUT,
    CONF_COMMAND_ATTEMPTS: COMMAND_RETRIES,
    CONF_OFF_WATER_TEMP: OFF_WATER_TEMP,
    CONF_HEAT_THRESHOLD: HEAT_THRESHOLD,
    CONF_OUTPUT_BASELINE: 40.0,
    CONF_WATER_TEMP_STEP: 1,
    CONF_TARGET_MIN: 5.0,
    CONF_TARGET_MAX: 35.0,
    CONF_TARGET_STEP: 0.5,
    CONF_HVAC_MODES: ["heat", "off"],
    CONF_INITIAL_HVAC_MODE: "heat",
    CONF_INITIAL_INTEGRAL: 0.0,
    CONF_RESTORE_STATE: True,
    CONF_FROST_ENABLED: True,
    CONF_FROST_OVERRIDE_OFF: True,
    # None follows the minimum water temperature, including for older entries.
    CONF_FROST_TARGET: None,
    CONF_FROST_SOURCE: "water",
    CONF_SENSOR_FAILURE_ACTION: "heat",
    CONF_DTR_ON_OPEN: "unchanged",
    CONF_DTR_ON_CLOSE: "unchanged",
    CONF_RTS_ON_OPEN: "unchanged",
    CONF_RTS_ON_CLOSE: "unchanged",
}
