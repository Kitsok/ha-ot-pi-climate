"""Tests for the configurable thermostat range and modes."""

from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components.climate.const import HVACMode

from custom_components.ot_pi_climate.climate import OpenThermClimate
from custom_components.ot_pi_climate.controller import PIController


def make_climate():
    controller = PIController(
        {
            "target_temperature_min": 10,
            "target_temperature_max": 30,
            "target_temperature_step": 0.1,
            "hvac_modes": ["off"],
            "initial_hvac_mode": "off",
        }
    )
    coordinator = Mock(controller=controller, async_request_refresh=AsyncMock())
    entry = Mock(entry_id="test", data={}, options={})
    entry.runtime_data.coordinator = coordinator
    climate = OpenThermClimate(entry)
    climate.async_write_ha_state = Mock()
    return climate, coordinator


@pytest.mark.asyncio
async def test_entity_uses_configured_range_step_and_modes() -> None:
    climate, coordinator = make_climate()
    assert climate.min_temp == 10
    assert climate.max_temp == 30
    assert climate.target_temperature_step == 0.1
    assert climate.hvac_modes == [HVACMode.OFF]

    await climate.async_set_temperature(temperature=22.3)
    assert climate.target_temperature == 22.3
    coordinator.async_request_refresh.assert_awaited_once()
    with pytest.raises(ValueError, match="Unsupported HVAC mode"):
        await climate.async_set_hvac_mode(HVACMode.HEAT)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [9, 31, float("nan"), float("inf")])
async def test_entity_rejects_targets_outside_configured_range(value) -> None:
    climate, coordinator = make_climate()
    with pytest.raises(ValueError, match="outside the configured range"):
        await climate.async_set_temperature(temperature=value)
    coordinator.async_request_refresh.assert_not_awaited()
