#!/usr/bin/env python3
"""Standalone simulator for the project's Arduino OpenTherm gateway.

The consumer-facing interface is a single-client Unix stream socket. QEMU can
expose that socket to a guest as a serial port. The accepted shell commands and
JSON responses match the installed gateway firmware: ``s <temperature>`` and
``g``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import signal
import stat
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("ot_gateway_simulator")


class MessageType(IntEnum):
    """OpenTherm message types."""

    READ_DATA = 0
    WRITE_DATA = 1
    INVALID_DATA = 2
    RESERVED = 3
    READ_ACK = 4
    WRITE_ACK = 5
    DATA_INVALID = 6
    UNKNOWN_DATA_ID = 7


DATA_IDS = {
    0: ("Status", "flags"),
    1: ("TSet", "f8.8"),
    5: ("ASFFlags", "u8/u8"),
    17: ("RelativeModulation", "f8.8"),
    18: ("CHPressure", "f8.8"),
    25: ("BoilerTemperature", "f8.8"),
    28: ("ReturnTemperature", "f8.8"),
}


def encode_f88(value: float) -> int:
    """Encode a signed OpenTherm f8.8 value."""

    scaled = round(value * 256)
    return scaled & 0xFFFF


def decode_f88(value: int) -> float:
    """Decode a signed OpenTherm f8.8 value."""

    if value & 0x8000:
        value -= 0x10000
    return value / 256.0


def build_frame(message_type: MessageType, data_id: int, data_value: int) -> int:
    """Build a 32-bit OpenTherm frame with even parity."""

    frame = (int(message_type) << 28) | ((data_id & 0xFF) << 16) | (data_value & 0xFFFF)
    if frame.bit_count() & 1:
        frame |= 1 << 31
    return frame


def decode_frame(frame: int) -> dict[str, Any]:
    """Return raw and decoded OpenTherm frame fields."""

    message_value = (frame >> 28) & 0x7
    data_id = (frame >> 16) & 0xFF
    data_value = frame & 0xFFFF
    try:
        message_type = MessageType(message_value).name
    except ValueError:
        message_type = f"UNKNOWN_{message_value}"

    name, value_type = DATA_IDS.get(data_id, (f"DataId{data_id}", "raw"))
    if value_type == "f8.8":
        decoded_value: Any = decode_f88(data_value)
    elif value_type == "flags":
        decoded_value = {
            "high_byte": (data_value >> 8) & 0xFF,
            "low_byte": data_value & 0xFF,
        }
    elif value_type == "u8/u8":
        decoded_value = {
            "high_byte": (data_value >> 8) & 0xFF,
            "low_byte": data_value & 0xFF,
        }
    else:
        decoded_value = data_value

    return {
        "raw": f"0x{frame:08X}",
        "parity_valid": frame.bit_count() % 2 == 0,
        "message_type": message_type,
        "data_id": data_id,
        "data_name": name,
        "data_raw": f"0x{data_value:04X}",
        "value": decoded_value,
    }


class EventLogger:
    """Write readable local-time events and structured JSON Lines."""

    def __init__(self, json_path: Path | None) -> None:
        self._json_file = None
        if json_path is not None:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            self._json_file = json_path.open("a", encoding="utf-8", buffering=1)

    def close(self) -> None:
        if self._json_file is not None:
            self._json_file.close()

    def emit(self, event: str, message: str, **fields: Any) -> None:
        now = datetime.now().astimezone()
        timestamp = now.isoformat(timespec="milliseconds")
        print(f"{timestamp} {event:<18} {message}", flush=True)
        if self._json_file is not None:
            record = {
                "timestamp": timestamp,
                "event": event,
                "message": message,
                **fields,
            }
            self._json_file.write(json.dumps(record, separators=(",", ":")) + "\n")

    def ot_frame(self, direction: str, frame: int) -> None:
        decoded = decode_frame(frame)
        message = (
            f"{direction:<15} {decoded['raw']} "
            f"{decoded['message_type']} {decoded['data_name']}({decoded['data_id']}) "
            f"value={decoded['value']}"
        )
        self.emit("ot_frame", message, direction=direction, frame=decoded)


@dataclass(slots=True)
class BoilerState:
    """Small deterministic boiler model."""

    water_temperature: float = 25.0
    return_temperature: float = 22.0
    pressure: float = 1.7
    modulation: float = 0.0
    target_temperature: int = 45
    heating_requested: bool = False
    dhw_active: bool = False
    flame: bool = False
    fault: bool = False
    fault_code: int = 0
    connected: bool = True
    ambient_temperature: float = 20.0
    heat_rate: float = 0.12
    cooling_time_constant: float = 600.0
    gateway_response_mode: str = "normal"
    ot_response_delay_ms: int = 0
    last_set_command: float = field(default_factory=time.monotonic)
    watchdog_active: bool = False

    def apply_setpoint(self, value: int, now: float) -> None:
        """Apply the gateway's existing set-temperature semantics."""

        self.last_set_command = now
        self.watchdog_active = False
        if value < 41:
            self.heating_requested = False
            self.target_temperature = 39
        else:
            self.heating_requested = True
            self.target_temperature = value

    def update(self, elapsed: float) -> None:
        """Advance the intentionally simple thermal model."""

        if elapsed <= 0:
            return
        effective_target = (
            max(self.target_temperature, 60) if self.dhw_active else self.target_temperature
        )
        can_burn = self.connected and not self.fault
        demand = self.heating_requested or self.dhw_active
        gap = effective_target - self.water_temperature
        self.flame = can_burn and demand and gap > 0.5

        if self.flame:
            self.modulation = min(100.0, max(10.0, gap * 8.0))
            rise = self.heat_rate * (self.modulation / 100.0) * elapsed
            self.water_temperature = min(float(effective_target), self.water_temperature + rise)
        else:
            self.modulation = 0.0
            cooling_fraction = min(1.0, elapsed / self.cooling_time_constant)
            self.water_temperature += (
                self.ambient_temperature - self.water_temperature
            ) * cooling_fraction

        return_drop = 4.0 + self.modulation * 0.04
        self.return_temperature = max(
            self.ambient_temperature,
            self.water_temperature - return_drop,
        )

    @property
    def heating_active(self) -> bool:
        return self.heating_requested and self.flame

    def snapshot(self, started_at: float) -> dict[str, Any]:
        """Return the firmware-compatible ``g`` payload."""

        return {
            "status": True,
            "Connected": self.connected,
            "TS": round((time.monotonic() - started_at) * 1000),
            "Tout": round(self.water_temperature, 2),
            "Tin": round(self.return_temperature, 2),
            "Modulation": round(self.modulation, 2),
            "Fault": self.fault,
            "Setpoint": self.target_temperature,
            "Heating": self.heating_active,
            "DHW": self.dhw_active,
            "Flame": self.flame,
        }


class GatewaySimulator:
    """Run the virtual gateway, boiler, control file, and Unix server."""

    def __init__(
        self,
        socket_path: Path,
        control_path: Path | None,
        event_logger: EventLogger,
        poll_interval: float,
        watchdog_timeout: float,
        initial_temperature: float,
    ) -> None:
        self.socket_path = socket_path
        self.control_path = control_path
        self.log = event_logger
        self.poll_interval = poll_interval
        self.watchdog_timeout = watchdog_timeout
        self.state = BoilerState(water_temperature=initial_temperature)
        self.started_at = time.monotonic()
        self._last_update = self.started_at
        self._control_mtime_ns: int | None = None
        self._server: asyncio.Server | None = None
        self._client_lock = asyncio.Lock()
        self._stopping = asyncio.Event()

    async def run(self) -> None:
        """Run until a termination signal is received."""

        self._prepare_socket_path()
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self.socket_path,
            limit=64 * 1024,
        )
        os.chmod(self.socket_path, 0o660)
        self.log.emit(
            "simulator_started",
            f"socket={self.socket_path} poll={self.poll_interval}s",
            socket=str(self.socket_path),
            poll_interval=self.poll_interval,
            watchdog_timeout=self.watchdog_timeout,
        )

        poll_task = asyncio.create_task(self._poll_loop(), name="boiler-poll")
        control_task = asyncio.create_task(self._control_loop(), name="control-file")
        async with self._server:
            await self._stopping.wait()

        poll_task.cancel()
        control_task.cancel()
        await asyncio.gather(poll_task, control_task, return_exceptions=True)
        self._server.close()
        await self._server.wait_closed()
        self._remove_socket()
        self.log.emit("simulator_stopped", "shutdown complete")

    def stop(self) -> None:
        self._stopping.set()

    def _prepare_socket_path(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            mode = self.socket_path.lstat().st_mode
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(mode):
            raise RuntimeError(f"Refusing to replace non-socket path: {self.socket_path}")
        self.socket_path.unlink()

    def _remove_socket(self) -> None:
        try:
            if stat.S_ISSOCK(self.socket_path.lstat().st_mode):
                self.socket_path.unlink()
        except FileNotFoundError:
            pass

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = repr(writer.get_extra_info("peername"))
        if self._client_lock.locked():
            self.log.emit("client_rejected", "a consumer is already connected", peer=peer)
            writer.close()
            await writer.wait_closed()
            return

        async with self._client_lock:
            self.log.emit("client_connected", peer, peer=peer)
            buffer = bytearray()
            try:
                while data := await reader.read(1024):
                    buffer.extend(data)
                    for command in self._extract_commands(buffer):
                        await self._handle_command(command, writer)
            except (ConnectionError, asyncio.CancelledError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()
                self.log.emit("client_disconnected", peer, peer=peer)

    @staticmethod
    def _extract_commands(buffer: bytearray) -> list[str]:
        commands: list[str] = []
        start = 0
        for index, value in enumerate(buffer):
            if value not in (10, 13):
                continue
            if index > start:
                commands.append(
                    bytes(buffer[start:index]).decode("ascii", errors="replace").strip()
                )
            start = index + 1
        if start:
            del buffer[:start]
        if len(buffer) > 4096:
            buffer.clear()
        return [command for command in commands if command]

    async def _handle_command(self, command: str, writer: asyncio.StreamWriter) -> None:
        self.log.emit("consumer_rx", command, command=command)
        parts = command.split()
        response: dict[str, Any]
        if parts == ["g"]:
            response = self.state.snapshot(self.started_at)
        elif len(parts) == 2 and parts[0] == "s":
            try:
                setpoint = int(parts[1])
            except ValueError:
                response = {"status": False}
            else:
                if 1 <= setpoint <= 85:
                    self.state.apply_setpoint(setpoint, time.monotonic())
                    response = {"status": True}
                    self.log.emit(
                        "setpoint_changed",
                        f"requested={setpoint} effective={self.state.target_temperature}",
                        requested=setpoint,
                        effective=self.state.target_temperature,
                        heating_requested=self.state.heating_requested,
                    )
                else:
                    response = {"status": False}
        else:
            response = {"status": False}

        await self._send_gateway_response(response, writer)

    async def _send_gateway_response(
        self, response: dict[str, Any], writer: asyncio.StreamWriter
    ) -> None:
        mode = self.state.gateway_response_mode
        if mode == "drop":
            self.log.emit("consumer_tx_drop", "response intentionally dropped", response=response)
            return
        if mode == "malformed":
            payload = b"{malformed\r\n"
        else:
            payload = json.dumps(response, separators=(",", ":")).encode() + b"\r\n"
        writer.write(payload)
        await writer.drain()
        self.log.emit(
            "consumer_tx",
            payload.decode("ascii", errors="replace").rstrip(),
            response=response,
            response_mode=mode,
        )

    async def _poll_loop(self) -> None:
        while True:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._last_update = now
            self._apply_watchdog(now)
            self.state.update(elapsed)
            await self._poll_boiler()
            await asyncio.sleep(self.poll_interval)

    def _apply_watchdog(self, now: float) -> None:
        if now - self.state.last_set_command < self.watchdog_timeout:
            return
        if self.state.watchdog_active:
            return
        self.state.watchdog_active = True
        self.state.heating_requested = True
        self.state.target_temperature = 60
        self.log.emit(
            "watchdog",
            "consumer heartbeat missing; heating fallback set to 60 C",
            target_temperature=60,
            timeout=self.watchdog_timeout,
        )

    async def _poll_boiler(self) -> None:
        master_flags = int(self.state.heating_requested) | (1 << 1)
        status_request = build_frame(MessageType.READ_DATA, 0, master_flags << 8)
        slave_flags = (
            int(self.state.fault)
            | (int(self.state.heating_active) << 1)
            | (int(self.state.dhw_active) << 2)
            | (int(self.state.flame) << 3)
        )
        if not await self._exchange(status_request, MessageType.WRITE_ACK, slave_flags):
            return

        reads = (
            (25, self.state.water_temperature),
            (28, self.state.return_temperature),
            (18, self.state.pressure),
            (17, self.state.modulation),
            (5, ((int(self.state.fault) & 0xFF) << 8) | (self.state.fault_code & 0xFF)),
        )
        for data_id, value in reads:
            request = build_frame(MessageType.READ_DATA, data_id, 0)
            encoded = int(value) if data_id == 5 else encode_f88(float(value))
            await self._exchange(request, MessageType.READ_ACK, encoded)

        setpoint_request = build_frame(
            MessageType.WRITE_DATA,
            1,
            encode_f88(float(self.state.target_temperature)),
        )
        await self._exchange(
            setpoint_request,
            MessageType.WRITE_ACK,
            encode_f88(float(self.state.target_temperature)),
        )

    async def _exchange(
        self,
        request: int,
        response_type: MessageType,
        response_value: int,
    ) -> bool:
        self.log.ot_frame("gateway->boiler", request)
        if not self.state.connected:
            self.log.emit(
                "ot_timeout",
                f"no boiler response to {decode_frame(request)['raw']}",
                request=decode_frame(request),
            )
            return False
        if self.state.ot_response_delay_ms:
            await asyncio.sleep(self.state.ot_response_delay_ms / 1000)
        data_id = (request >> 16) & 0xFF
        response = build_frame(response_type, data_id, response_value)
        self.log.ot_frame("boiler->gateway", response)
        return True

    async def _control_loop(self) -> None:
        while True:
            self._load_control_file()
            await asyncio.sleep(0.5)

    def _load_control_file(self) -> None:
        if self.control_path is None:
            return
        try:
            file_stat = self.control_path.stat()
        except FileNotFoundError:
            return
        if file_stat.st_mtime_ns == self._control_mtime_ns:
            return
        self._control_mtime_ns = file_stat.st_mtime_ns
        try:
            document = json.loads(self.control_path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("control document must be a JSON object")
            self._apply_control(document)
        except (OSError, ValueError, json.JSONDecodeError) as err:
            self.log.emit("control_error", str(err), error=str(err))
            return
        self.log.emit("control_loaded", str(self.control_path), values=document)

    def _apply_control(self, values: dict[str, Any]) -> None:
        boolean_fields = ("connected", "dhw_active", "fault")
        float_fields = (
            "ambient_temperature",
            "heat_rate",
            "cooling_time_constant",
            "pressure",
        )
        for name in boolean_fields:
            if name in values:
                setattr(self.state, name, bool(values[name]))
        for name in float_fields:
            if name in values:
                value = float(values[name])
                if not math.isfinite(value):
                    raise ValueError(f"{name} must be finite")
                if name in {"heat_rate", "cooling_time_constant"} and value <= 0:
                    raise ValueError(f"{name} must be greater than zero")
                setattr(self.state, name, value)
        if "water_temperature" in values:
            value = float(values["water_temperature"])
            if not math.isfinite(value):
                raise ValueError("water_temperature must be finite")
            self.state.water_temperature = value
        if "return_temperature" in values:
            value = float(values["return_temperature"])
            if not math.isfinite(value):
                raise ValueError("return_temperature must be finite")
            self.state.return_temperature = value
        if "fault_code" in values:
            self.state.fault_code = int(values["fault_code"]) & 0xFF
        if "ot_response_delay_ms" in values:
            self.state.ot_response_delay_ms = max(0, int(values["ot_response_delay_ms"]))
        if "gateway_response_mode" in values:
            mode = str(values["gateway_response_mode"])
            if mode not in {"normal", "drop", "malformed"}:
                raise ValueError("gateway_response_mode must be normal, drop, or malformed")
            self.state.gateway_response_mode = mode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--socket",
        type=Path,
        default=Path("/tmp/otgw-simulator.sock"),
        help="Unix socket exposed to QEMU (default: %(default)s)",
    )
    parser.add_argument(
        "--control-file",
        type=Path,
        default=Path("/tmp/otgw-simulator-control.json"),
        help="watched JSON control file (default: %(default)s)",
    )
    parser.add_argument(
        "--json-log",
        type=Path,
        default=Path("otgw-simulator.jsonl"),
        help="structured JSON Lines log (default: %(default)s)",
    )
    parser.add_argument("--poll-interval", type=float, default=0.9)
    parser.add_argument("--watchdog-timeout", type=float, default=300.0)
    parser.add_argument("--initial-temperature", type=float, default=25.0)
    return parser.parse_args(argv)


async def async_main(args: argparse.Namespace) -> None:
    event_logger = EventLogger(args.json_log)
    simulator = GatewaySimulator(
        socket_path=args.socket,
        control_path=args.control_file,
        event_logger=event_logger,
        poll_interval=args.poll_interval,
        watchdog_timeout=args.watchdog_timeout,
        initial_temperature=args.initial_temperature,
    )
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_name, simulator.stop)
    try:
        await simulator.run()
    finally:
        event_logger.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.poll_interval <= 0:
        raise SystemExit("--poll-interval must be greater than zero")
    if args.watchdog_timeout <= 0:
        raise SystemExit("--watchdog-timeout must be greater than zero")
    if not math.isfinite(args.initial_temperature):
        raise SystemExit("--initial-temperature must be finite")
    try:
        asyncio.run(async_main(args))
    except (OSError, RuntimeError) as err:
        LOGGER.error("%s", err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
