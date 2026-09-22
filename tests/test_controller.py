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


def test_configurable_baseline_threshold_and_off_command() -> None:
    controller = PIController(
        {
            **DEFAULTS,
            "off_water_temperature": 30,
            "output_baseline": 50,
            "heat_threshold": 50,
        }
    )

    assert controller.calculate(20, 30, elapsed_seconds=0).water_setpoint == 30
    assert controller.calculate(19.5, 30, elapsed_seconds=0).water_setpoint == 60


@pytest.mark.parametrize(("baseline", "expected"), [(43, 45), (41, 41), (74, 73)])
def test_water_step_keeps_outputs_inside_limits(baseline, expected) -> None:
    controller = PIController(
        {
            **DEFAULTS,
            "output_baseline": baseline,
            "water_temperature_step": 5,
            "max_water_temperature": 73,
        }
    )

    assert controller.calculate(20, 30, elapsed_seconds=0).water_setpoint == expected


@pytest.mark.parametrize(
    "settings",
    [
        {"frost_enabled": False},
        {"frost_override_off": False},
    ],
)
def test_frost_can_be_disabled_or_prevented_from_overriding_off(settings) -> None:
    controller = PIController({**DEFAULTS, **settings})
    controller.hvac_mode = HVACMode.OFF

    result = controller.calculate(20, 10)

    assert not result.frost_protection_active
    assert result.water_setpoint == OFF_WATER_TEMP


def test_room_frost_source_and_separate_target() -> None:
    controller = PIController({**DEFAULTS, "frost_source": "room", "frost_target": 55})
    controller.hvac_mode = HVACMode.OFF

    assert not controller.calculate(25, 10).frost_protection_active
    result = controller.calculate(15, 30)
    assert result.frost_protection_active
    assert result.water_setpoint == 55


@pytest.mark.parametrize(("action", "expected"), [("heat", 60), ("off", 39), ("hold", 61)])
def test_sensor_failure_policies(action, expected) -> None:
    controller = PIController({**DEFAULTS, "sensor_failure_action": action})
    controller.calculate(19, 30, elapsed_seconds=0)

    result = controller.calculate(None, 30)

    assert result.sensor_failsafe_active
    assert result.water_setpoint == expected
    assert result.heating_requested is (expected != 39)
    # Frost protection still overrides the selected failure action.
    assert controller.calculate(None, 10).heating_requested


def test_hold_on_first_update_does_not_start_heating() -> None:
    controller = PIController({**DEFAULTS, "sensor_failure_action": "hold"})
    assert not controller.calculate(None, None).heating_requested


def test_configured_startup_state_and_disabled_restore() -> None:
    controller = PIController(
        {
            **DEFAULTS,
            "initial_hvac_mode": "off",
            "initial_integral": 10,
            "initial_target_temperature": 18,
            "restore_state": False,
        }
    )
    controller.restore({"hvac_mode": "heat", "integral": 50, "target_temperature": 30})

    assert controller.hvac_mode == HVACMode.OFF
    assert controller.integral == 10
    assert controller.target_temperature == 18


def test_restored_state_respects_changed_limits_and_modes() -> None:
    controller = PIController(
        {
            **DEFAULTS,
            "hvac_modes": ["off"],
            "initial_hvac_mode": "off",
            "target_temperature_min": 15,
            "target_temperature_max": 25,
            "integral_max": 40,
        }
    )
    controller.restore({"hvac_mode": "heat", "integral": 80, "target_temperature": 30})

    assert controller.hvac_mode == HVACMode.OFF
    assert controller.integral == 40
    assert controller.target_temperature == 25


def test_legacy_entry_receives_defaults_and_frost_follows_minimum() -> None:
    controller = PIController({"initial_target_temperature": 20, "min_water_temperature": 47})
    controller.hvac_mode = HVACMode.OFF
    assert controller.calculate(20, 10).water_setpoint == 47
