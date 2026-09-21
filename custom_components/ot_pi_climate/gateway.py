"""Serial protocol for the installed OpenTherm gateway firmware."""

import asyncio
import json
import logging
from typing import Any

from serialx import PinState, open_serial_connection

from .const import BAUD_RATE, COMMAND_RETRIES, COMMAND_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class OpenThermGatewayError(Exception):
    """Gateway communication error."""


class OpenThermGateway:
    """Manage one persistent connection to the USB gateway."""

    def __init__(self, port: str) -> None:
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def async_connect(self) -> None:
        """Open the serial port if needed."""

        if self._writer is not None and not self._writer.is_closing():
            return
        try:
            self._reader, self._writer = await open_serial_connection(
                url=self.port,
                baudrate=BAUD_RATE,
                dtr_on_open=PinState.UNDEFINED,
                dtr_on_close=PinState.UNDEFINED,
                rts_on_open=PinState.UNDEFINED,
                rts_on_close=PinState.UNDEFINED,
            )
        except (OSError, TimeoutError) as err:
            raise OpenThermGatewayError(f"Unable to open serial port {self.port}: {err}") from err

    async def async_close(self) -> None:
        """Close the serial connection."""

        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, TimeoutError):
            pass

    async def async_update(self, setpoint: int) -> dict[str, Any]:
        """Send the heartbeat setpoint and retrieve one JSON snapshot."""

        async with self._lock:
            for attempt in range(1, COMMAND_RETRIES + 1):
                try:
                    await self.async_connect()
                    await self._send_command(f"s {setpoint}")
                    acknowledgement = self._decode_response(await self._read_response())
                    if acknowledgement.get("status") is not True:
                        raise OpenThermGatewayError("Gateway rejected the setpoint command")
                    await self._send_command("g")
                    response = await self._read_response()
                    data = self._decode_snapshot(response)
                    data["CommandedSetpoint"] = setpoint
                    return data
                except (
                    OpenThermGatewayError,
                    OSError,
                    EOFError,
                    TimeoutError,
                    UnicodeError,
                    json.JSONDecodeError,
                ) as err:
                    _LOGGER.debug("Gateway attempt %s/%s failed: %s", attempt, COMMAND_RETRIES, err)
                    await self.async_close()

            raise OpenThermGatewayError(
                f"No valid response from {self.port} after {COMMAND_RETRIES} attempts"
            )

    async def _send_command(self, command: str) -> None:
        if self._writer is None:
            raise OpenThermGatewayError("Serial connection is not open")
        self._writer.write(f"{command}\r".encode("ascii"))
        await asyncio.wait_for(self._writer.drain(), timeout=COMMAND_TIMEOUT)

    async def _read_response(self) -> str:
        if self._reader is None:
            raise OpenThermGatewayError("Serial connection is not open")
        raw = await asyncio.wait_for(self._reader.readuntil(b"\n"), timeout=COMMAND_TIMEOUT)
        return raw.decode("ascii").strip()

    @staticmethod
    def _decode_response(response: str) -> dict[str, Any]:
        start = response.find("{")
        end = response.rfind("}")
        if start < 0 or end < start:
            raise json.JSONDecodeError("No JSON object in gateway response", response, 0)
        decoded = json.loads(response[start : end + 1])
        if not isinstance(decoded, dict):
            raise json.JSONDecodeError("Gateway response is not an object", response, start)
        return decoded

    @staticmethod
    def _decode_snapshot(response: str) -> dict[str, Any]:
        decoded = OpenThermGateway._decode_response(response)
        if "Flame" not in decoded:
            raise json.JSONDecodeError("Incomplete gateway response", response, 0)
        return decoded
