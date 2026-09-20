# OpenTherm PI Climate

A Home Assistant custom integration for a USB OpenTherm gateway. It exposes a
native climate entity, calculates the boiler-water setpoint with a PI controller,
and publishes boiler telemetry.

## Requirements

- Home Assistant 2026.5 or newer.
- The compatible gateway connected to the Home Assistant host or passed through
  to its virtual machine.
- Gateway serial speed of 115200 baud.
- A Home Assistant temperature sensor for the controlled room.

The integration intentionally uses only the firmware's existing `s <temp>` and
`g` serial commands. Domestic hot water is not controlled. A water setpoint of
39 °C is the firmware command for central-heating off.

## Installation with HACS

1. In HACS, add this GitHub repository as a custom repository of type
   **Integration**.
2. Download **OpenTherm PI Climate**.
3. Restart Home Assistant.
4. Open **Settings → Devices & services → Add integration** and search for
   **OpenTherm PI Climate**.

## Configuration

The setup form contains all settings, including the serial path, room temperature
sensor, PI coefficients and limits, water-temperature limits, always-active frost
threshold, sensor-failure target, and initial room target. Prefer a stable
`/dev/serial/by-id/...` serial path.

All values can be changed later using **Configure** on the integration. Changes
cause an automatic integration reload and require no Home Assistant restart.
Multiple gateways are supported as separate integration entries.

## Operation and safety behavior

Every minute the integration sends `s <setpoint>` as the firmware heartbeat and
then sends `g` to retrieve boiler state. Target and HVAC mode changes also
request an immediate update. Room-temperature changes are consumed by the next
one-minute control cycle so frequent sensor updates do not distort the integral.

The serial connection is kept open and leaves DTR/RTS untouched so reconnecting
does not intentionally reset the gateway controller.

- In heat mode, the PI controller determines the water target.
- In off mode, the integration sends `s 39`.
- Frost protection overrides off mode and cannot be disabled.
- If the room sensor is unavailable in heat mode, the configured failure target
  is used (60 °C by default).
- DHW remains under boiler/firmware control.
- The installed firmware's five-minute missing-command watchdog remains the
  final fallback if Home Assistant stops communicating.

## Entities

- Climate entity with heat/off modes, target/current room temperatures, and
  heating action.
- Heating-water and return-water temperatures.
- Boiler modulation and commanded water setpoint.
- Boiler connection, flame, fault, central-heating and DHW binary sensors.

You may rename the climate entity to `climate.main_climate` after setup.

## Development status

This initial release must be validated against the physical gateway. Test USB
passthrough and serial framing while supervising the boiler before unattended use.

## OpenTherm gateway simulator

[`tools/ot_gateway_simulator.py`](tools/ot_gateway_simulator.py) is a standalone
host-side simulator for developing without a physical gateway or boiler. It
provides the existing `s <temperature>` and `g` interface through a single-client
Unix socket suitable for a QEMU serial backend.

Run it with:

```bash
python3 tools/ot_gateway_simulator.py \
  --socket /tmp/otgw-simulator.sock \
  --control-file /tmp/otgw-simulator-control.json \
  --json-log otgw-simulator.jsonl
```

The simulator prints readable local-time logs and writes the same events as
JSON Lines. Its virtual firmware polls the boiler every 900 ms using decoded
OpenTherm request/response frames for status, temperatures, pressure,
modulation, fault information, and the control setpoint.

The five-minute command watchdog enables heating at 60 °C. A valid `s` command
clears the watchdog, and `s 39` switches central heating off. DHW state is only
controlled through the simulator control file.

### Runtime control

The control file is optional and is reloaded when changed. For example:

```json
{
  "connected": true,
  "dhw_active": false,
  "fault": false,
  "fault_code": 0,
  "water_temperature": 30.0,
  "ambient_temperature": 20.0,
  "pressure": 1.7,
  "heat_rate": 0.12,
  "cooling_time_constant": 600.0,
  "ot_response_delay_ms": 0,
  "gateway_response_mode": "normal"
}
```

`gateway_response_mode` accepts `normal`, `drop`, or `malformed`. Setting
`connected` to `false` produces OpenTherm timeouts while the serial shell stays
available. Temperature values in a newly written control file set the current
state once; the thermal model continues evolving afterward.
