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
@pytest.mark.parametrize("ack", ['{"status":false}', "{}", '{"status":"true"}', "bad"])
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


@pytest.mark.asyncio
async def test_custom_attempt_limit() -> None:
    gateway = OpenThermGateway("fake", {"command_attempts": 2})
    gateway.async_connect = AsyncMock()
    gateway.async_close = AsyncMock()
    gateway._send_command = AsyncMock()
    gateway._read_response = AsyncMock(return_value='{"status":false}')

    with pytest.raises(OpenThermGatewayError, match="after 2 attempts"):
        await gateway.async_update(30)

    assert gateway._send_command.await_args_list == [call("s 30")] * 2
    assert gateway.async_close.await_count == 2


@pytest.mark.asyncio
async def test_serial_options_reach_connection(monkeypatch) -> None:
    from serialx import PinState

    connect = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
    monkeypatch.setattr("custom_components.ot_pi_climate.gateway.open_serial_connection", connect)
    gateway = OpenThermGateway(
        "fake",
        {
            "baud_rate": 9600,
            "dtr_on_open": "high",
            "dtr_on_close": "low",
            "rts_on_open": "low",
            "rts_on_close": "unchanged",
        },
    )

    await gateway.async_connect()

    connect.assert_awaited_once_with(
        url="fake",
        baudrate=9600,
        dtr_on_open=PinState.HIGH,
        dtr_on_close=PinState.LOW,
        rts_on_open=PinState.LOW,
        rts_on_close=PinState.UNDEFINED,
    )


@pytest.mark.asyncio
async def test_configured_timeout_applies_to_writes_and_reads(monkeypatch) -> None:
    import asyncio
    from unittest.mock import Mock

    wait_for = AsyncMock(wraps=asyncio.wait_for)
    monkeypatch.setattr("custom_components.ot_pi_climate.gateway.asyncio.wait_for", wait_for)
    gateway = OpenThermGateway("fake", {"command_timeout": 0.25})
    gateway._writer = Mock(drain=AsyncMock())
    gateway._reader = Mock(readuntil=AsyncMock(return_value=b'{"status":true}\n'))

    await gateway._send_command("s 45")
    assert await gateway._read_response() == '{"status":true}'

    gateway._writer.write.assert_called_once_with(b"s 45\r")
    assert [item.kwargs["timeout"] for item in wait_for.await_args_list] == [0.25, 0.25]
