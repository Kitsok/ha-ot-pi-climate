"""Tests for gateway response decoding."""

import json
from unittest.mock import AsyncMock, call

import pytest

from custom_components.ot_pi_climate.const import COMMAND_RETRIES
from custom_components.ot_pi_climate.gateway import OpenThermGateway, OpenThermGatewayError


def test_decode_snapshot_with_shell_prefix() -> None:
    snapshot = OpenThermGateway._decode_snapshot('otgw> {"Tout":42.5,"Flame":true,"DHW":true}')

    assert snapshot["Tout"] == 42.5
    assert snapshot["Flame"] is True


@pytest.mark.parametrize("response", ["", "ok", '{"Tout":42}'])
def test_decode_snapshot_rejects_invalid_data(response: str) -> None:
    with pytest.raises(json.JSONDecodeError):
        OpenThermGateway._decode_snapshot(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("ack", ['{"status":false}', '{}', '{"status":"true"}', 'bad'])
async def test_rejected_setpoint_is_retried_and_reported_as_failure(ack: str) -> None:
    gateway = OpenThermGateway("fake")
    gateway.async_connect = AsyncMock()
    gateway.async_close = AsyncMock()
    gateway._send_command = AsyncMock()
    gateway._read_response = AsyncMock(return_value=ack)

    with pytest.raises(OpenThermGatewayError):
        await gateway.async_update(75)

    assert gateway._send_command.await_args_list == [call("s 75")] * COMMAND_RETRIES
    assert gateway.async_close.await_count == COMMAND_RETRIES


@pytest.mark.asyncio
async def test_rejected_setpoint_recovers_after_successful_acknowledgement() -> None:
    gateway = OpenThermGateway("fake")
    gateway.async_connect = AsyncMock()
    gateway.async_close = AsyncMock()
    gateway._send_command = AsyncMock()
    gateway._read_response = AsyncMock(
        side_effect=['{"status":false}', 'otgw> {"status":true}', '{"Flame":true}']
    )

    snapshot = await gateway.async_update(75)

    assert snapshot["CommandedSetpoint"] == 75
    assert gateway._send_command.await_args_list == [call("s 75"), call("s 75"), call("g")]
    gateway.async_close.assert_awaited_once()
