"""Tests for editable settings, option reloads, and input validation."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.ot_pi_climate import async_reload_entry
from custom_components.ot_pi_climate.config_flow import (
    OpenThermConfigFlow,
    OpenThermOptionsFlow,
    _schema,
    _validate,
)
from custom_components.ot_pi_climate.const import DEFAULTS
from custom_components.ot_pi_climate.models import merged_config


def test_form_exposes_every_setting_and_accepts_defaults() -> None:
    schema = _schema({})
    result = schema({"serial_port": "/dev/ttyUSB0", "temperature_entity": "sensor.room"})
    assert {str(key) for key in schema.schema} == set(DEFAULTS) | {
        "serial_port",
        "temperature_entity",
    }
    assert _validate(result) == {}
    assert "frost_target" not in result


def test_tuning_values_are_not_restricted_to_old_limits_or_steps() -> None:
    values = {
        "serial_port": "/dev/ttyUSB0",
        "temperature_entity": "sensor.room",
        "kp": 120.123,
        "ti": 1200.123,
        "integral_factor": 12.345,
        "integral_min": -600,
        "integral_max": 600,
        "frost_temperature": -5,
        "target_temperature_min": -10,
        "target_temperature_max": 50,
        "initial_target_temperature": 40,
        "target_temperature_step": 0.1,
    }
    assert _validate(_schema(values)(values)) == {}


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"ti": 0}, "ti"),
        ({"update_interval": 0}, "update_interval"),
        ({"command_timeout": -1}, "command_timeout"),
        ({"kp": float("nan")}, "kp"),
        ({"output_baseline": float("inf")}, "output_baseline"),
        ({"command_attempts": 1.5}, "command_attempts"),
        ({"water_temperature_step": 0.5}, "water_temperature_step"),
        ({"off_water_temperature": 41}, "off_water_temperature"),
        ({"min_water_temperature": 40}, "min_water_temperature"),
        ({"max_water_temperature": 86}, "max_water_temperature"),
        ({"min_water_temperature": 76}, "base"),
        ({"failsafe_temperature": 80}, "failsafe_temperature"),
        ({"frost_target": 80}, "frost_target"),
        ({"integral_min": 100}, "base"),
        ({"initial_integral": 100}, "initial_integral"),
        ({"target_temperature_min": 35}, "base"),
        ({"initial_target_temperature": 40}, "initial_target_temperature"),
        ({"target_temperature_step": 0}, "target_temperature_step"),
        ({"target_temperature_step": 40}, "target_temperature_step"),
        ({"hvac_modes": []}, "hvac_modes"),
        ({"hvac_modes": ["cool"]}, "hvac_modes"),
        ({"hvac_modes": ["off"]}, "initial_hvac_mode"),
    ],
)
def test_invalid_settings_are_rejected(changes, field) -> None:
    assert field in _validate(changes)


def test_optional_frost_target_can_be_cleared() -> None:
    schema = _schema({"frost_target": 50})
    values = schema({"serial_port": "/dev/ttyUSB0", "temperature_entity": "sensor.room"})
    assert "frost_target" not in values


@pytest.mark.asyncio
async def test_setup_saves_new_values_and_defaults() -> None:
    flow = OpenThermConfigFlow()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()
    result = await flow.async_step_user(
        {
            "name": "Boiler",
            "serial_port": "fake",
            "temperature_entity": "sensor.room",
            "update_interval": 15,
            "initial_hvac_mode": "off",
        }
    )
    assert result["type"] == "create_entry"
    assert result["data"]["update_interval"] == 15
    assert result["data"]["initial_hvac_mode"] == "off"
    assert result["data"]["baud_rate"] == 115200


@pytest.mark.asyncio
async def test_options_edit_legacy_entry_and_clear_frost_target() -> None:
    entry = Mock(data={"name": "Legacy", "frost_target": 50}, options={})
    flow = OpenThermOptionsFlow()
    flow.handler = "test_entry"
    flow.hass = Mock()
    flow.hass.config_entries.async_get_known_entry.return_value = entry
    form = await flow.async_step_init()
    assert form["type"] == "form"
    values = form["data_schema"](
        {
            "serial_port": "fake",
            "temperature_entity": "sensor.room",
            "baud_rate": 9600,
        }
    )
    result = await flow.async_step_init(values)
    assert result["type"] == "create_entry"
    entry.options = result["data"]
    config = merged_config(entry)
    assert config["baud_rate"] == 9600
    assert config["frost_target"] is None


@pytest.mark.asyncio
async def test_options_validation_does_not_save_invalid_values() -> None:
    flow = OpenThermOptionsFlow()
    flow.handler = "test_entry"
    flow.hass = Mock()
    flow.hass.config_entries.async_get_known_entry.return_value = Mock(data={}, options={})
    result = await flow.async_step_init({"update_interval": 0})
    assert result["type"] == "form"
    assert result["errors"] == {"update_interval": "must_be_positive"}


@pytest.mark.asyncio
async def test_options_change_triggers_reload() -> None:
    hass = Mock()
    hass.config_entries.async_reload = AsyncMock()
    await async_reload_entry(hass, Mock(entry_id="test_entry"))
    hass.config_entries.async_reload.assert_awaited_once_with("test_entry")


def test_translations_cover_all_form_fields_and_choices() -> None:
    root = Path(__file__).resolve().parents[1] / "custom_components" / "ot_pi_climate"
    strings = json.loads((root / "strings.json").read_text())
    assert strings == json.loads((root / "translations" / "en.json").read_text())
    keys = {str(key) for key in _schema({}).schema}
    assert keys == set(strings["config"]["step"]["user"]["data"])
    assert keys == set(strings["options"]["step"]["init"]["data"])
