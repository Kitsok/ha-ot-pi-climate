"""Tests for the standalone OpenTherm gateway simulator."""

from __future__ import annotations

import json
import time

import pytest

from tools.ot_gateway_simulator import (
    BoilerState,
    EventLogger,
    GatewaySimulator,
    MessageType,
    build_frame,
    decode_f88,
    decode_frame,
    encode_f88,
)


class FakeWriter:
    """Minimal asyncio writer used by command tests."""

    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None


def make_simulator(tmp_path, *, watchdog_timeout: float = 300.0) -> GatewaySimulator:
    return GatewaySimulator(
        socket_path=tmp_path / "gateway.sock",
        control_path=tmp_path / "control.json",
        event_logger=EventLogger(None),
        poll_interval=0.9,
        watchdog_timeout=watchdog_timeout,
        initial_temperature=25.0,
    )


def test_f88_round_trip() -> None:
    assert decode_f88(encode_f88(42.5)) == 42.5
    assert decode_f88(encode_f88(-5.25)) == -5.25


def test_frame_has_even_parity_and_decodes() -> None:
    frame = build_frame(MessageType.WRITE_DATA, 1, encode_f88(60.0))
    decoded = decode_frame(frame)

    assert frame.bit_count() % 2 == 0
    assert decoded["parity_valid"] is True
    assert decoded["message_type"] == "WRITE_DATA"
    assert decoded["data_name"] == "TSet"
    assert decoded["value"] == 60.0


def test_boiler_off_and_watchdog_fallback(tmp_path) -> None:
    simulator = make_simulator(tmp_path, watchdog_timeout=300.0)
    now = time.monotonic()
    simulator.state.apply_setpoint(39, now)

    assert simulator.state.target_temperature == 39
    assert simulator.state.heating_requested is False

    simulator._apply_watchdog(now + 301)

    assert simulator.state.target_temperature == 60
    assert simulator.state.heating_requested is True
    assert simulator.state.watchdog_active is True


def test_firmware_snapshot_keys() -> None:
    state = BoilerState()

    assert set(state.snapshot(time.monotonic())) == {
        "status",
        "Connected",
        "TS",
        "Tout",
        "Tin",
        "Modulation",
        "Fault",
        "Setpoint",
        "Heating",
        "DHW",
        "Flame",
    }


@pytest.mark.asyncio
async def test_set_and_get_commands(tmp_path) -> None:
    simulator = make_simulator(tmp_path)
    writer = FakeWriter()

    await simulator._handle_command("s 55", writer)
    set_response, remainder = bytes(writer.data).split(b"\r\n", 1)

    assert json.loads(set_response) == {"status": True}
    assert remainder == b""
    assert simulator.state.target_temperature == 55

    writer.data.clear()
    await simulator._handle_command("g", writer)
    snapshot = json.loads(bytes(writer.data).strip())

    assert snapshot["Setpoint"] == 55
    assert snapshot["status"] is True


def test_extracts_cr_lf_commands() -> None:
    buffer = bytearray(b"s 50\rg\r\npartial")

    commands = GatewaySimulator._extract_commands(buffer)

    assert commands == ["s 50", "g"]
    assert buffer == b"partial"


def test_control_file_updates_faults_and_response_mode(tmp_path) -> None:
    simulator = make_simulator(tmp_path)
    simulator._apply_control(
        {
            "dhw_active": True,
            "fault": True,
            "fault_code": 12,
            "gateway_response_mode": "malformed",
            "water_temperature": 33.5,
        }
    )

    assert simulator.state.dhw_active is True
    assert simulator.state.fault is True
    assert simulator.state.fault_code == 12
    assert simulator.state.gateway_response_mode == "malformed"
    assert simulator.state.water_temperature == 33.5
