"""Tests for the PI controller."""

import pytest
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


@pytest.mark.parametrize("temperature", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_room_temperature_uses_failsafe(temperature: float) -> None:
    controller = make_controller()

    result = controller.calculate(temperature, 30.0)

    assert result.water_setpoint == 60
    assert result.sensor_failsafe_active
    assert controller.integral == 0


def test_integral_is_independent_of_refresh_frequency() -> None:
    regular = make_controller()
    frequent = make_controller()

    expected = regular.calculate(19.0, 30.0, elapsed_seconds=60)
    for _ in range(6):
        actual = frequent.calculate(19.0, 30.0, elapsed_seconds=10)

    assert frequent.integral == pytest.approx(regular.integral)
    assert actual.water_setpoint == expected.water_setpoint


def test_immediate_target_change_updates_output_without_advancing_integral() -> None:
    controller = make_controller()
    controller.calculate(20.0, 30.0, elapsed_seconds=0)
    controller.target_temperature = 21

    result = controller.calculate(20.0, 30.0, elapsed_seconds=0)

    assert result.water_setpoint == 61
    assert controller.integral == 0
