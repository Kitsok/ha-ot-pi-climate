"""Tests for temperature conversion and controller update timing."""

from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import frame

from custom_components.ot_pi_climate.const import DEFAULTS
from custom_components.ot_pi_climate.controller import PIController
from custom_components.ot_pi_climate.coordinator import OpenThermCoordinator


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        ("20", UnitOfTemperature.CELSIUS, 20),
        ("68", UnitOfTemperature.FAHRENHEIT, 20),
        ("293.15", UnitOfTemperature.KELVIN, 20),
        ("nan", UnitOfTemperature.CELSIUS, None),
        ("inf", UnitOfTemperature.CELSIUS, None),
        ("-inf", UnitOfTemperature.CELSIUS, None),
        ("unavailable", UnitOfTemperature.CELSIUS, None),
        ("invalid", UnitOfTemperature.CELSIUS, None),
        ("20", None, None),
        ("20", "%", None),
    ],
)
async def test_room_temperature_and_command(tmp_path, value, unit, expected) -> None:
    hass = HomeAssistant(str(tmp_path))
    frame.async_setup(hass)
    hass.states.async_set("sensor.room", value, {ATTR_UNIT_OF_MEASUREMENT: unit})
    controller = PIController({**DEFAULTS, "initial_target_temperature": 21})
    gateway = Mock(async_update=AsyncMock(return_value={"Tout": 30, "Flame": False}))
    coordinator = OpenThermCoordinator(hass, gateway, controller, "sensor.room")

    if expected is None:
        assert coordinator.room_temperature is None
    else:
        assert coordinator.room_temperature == pytest.approx(expected)
    await coordinator._async_update_data()

    gateway.async_update.assert_awaited_once_with(60 if expected is None else 61)
    assert coordinator.result.sensor_failsafe_active is (expected is None)


@pytest.mark.asyncio
async def test_refreshes_integrate_actual_elapsed_time(tmp_path, monkeypatch) -> None:
    hass = HomeAssistant(str(tmp_path))
    frame.async_setup(hass)
    hass.states.async_set(
        "sensor.room", "19", {ATTR_UNIT_OF_MEASUREMENT: UnitOfTemperature.CELSIUS}
    )
    controller = PIController(dict(DEFAULTS))
    gateway = Mock(async_update=AsyncMock(return_value={"Tout": 30, "Flame": False}))
    coordinator = OpenThermCoordinator(hass, gateway, controller, "sensor.room")
    clock = Mock(monotonic=Mock(side_effect=[100, 100, 110, 160]))
    monkeypatch.setattr("custom_components.ot_pi_climate.coordinator.time", clock)

    await coordinator._async_update_data()
    await coordinator._async_update_data()
    assert controller.integral == 0

    await coordinator._async_update_data()
    await coordinator._async_update_data()
    assert controller.integral == pytest.approx(0.8)
