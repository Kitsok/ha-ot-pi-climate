"""Tests for the PI controller."""

from homeassistant.components.climate.const import HVACMode

from custom_components.ot_pi_climate.const import DEFAULTS, OFF_WATER_TEMP
from custom_components.ot_pi_climate.controller import PIController


def make_controller() -> PIController:
    return PIController(dict(DEFAULTS))


def test_off_uses_39_degree_command() -> None:
    controller = make_controller()
    controller.hvac_mode = HVACMode.OFF

    result = controller.calculate(room_temperature=20.0, water_temperature=30.0)

    assert result.water_setpoint == OFF_WATER_TEMP
    assert not result.heating_requested


def test_frost_protection_overrides_off() -> None:
    controller = make_controller()
    controller.hvac_mode = HVACMode.OFF

    result = controller.calculate(room_temperature=20.0, water_temperature=10.0)

    assert result.water_setpoint == 41
    assert result.heating_requested
    assert result.frost_protection_active


def test_missing_room_sensor_uses_failsafe() -> None:
    controller = make_controller()

    result = controller.calculate(room_temperature=None, water_temperature=30.0)

    assert result.water_setpoint == 60
    assert result.sensor_failsafe_active


def test_output_is_clamped() -> None:
    controller = make_controller()

    assert controller.calculate(0.0, 30.0).water_setpoint == 75
    controller.integral = -5.0
    assert controller.calculate(40.0, 30.0).water_setpoint == OFF_WATER_TEMP
