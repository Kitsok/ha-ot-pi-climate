# OpenTherm PI Climate

A Home Assistant custom integration for a USB OpenTherm gateway. It exposes a
native climate entity, calculates the boiler-water setpoint with a PI controller,
and publishes boiler telemetry.

## Requirements

- Home Assistant 2026.5 or newer.
- The compatible gateway connected to the Home Assistant host or passed through
  to its virtual machine.
- Matching gateway serial speed (115200 baud by default).
- A Home Assistant temperature sensor for the controlled room.

The integration intentionally uses only the firmware's existing `s <temp>` and
`g` serial commands. Domestic hot water is not controlled. The
supported firmware accepts integer commands from 1 to 85: values below 41
switch central heating off, while 41–85 request heating. The default off
command is `s 39`; the firmware uses an internal 39 °C target for all off commands.

## Installation with HACS

1. In HACS, add this GitHub repository as a custom repository of type
   **Integration**.
2. Download **OpenTherm PI Climate**.
3. Restart Home Assistant.
4. Open **Settings → Devices & services → Add integration** and search for
   **OpenTherm PI Climate**.

## Configuration

The setup form and **Configure** options expose the following settings. Prefer a
stable `/dev/serial/by-id/...` serial path.

| Settings | Defaults / behavior |
| --- | --- |
| Name, serial path, room temperature sensor | Select the gateway and sensor during setup |
| Kp, Ti, integral factor | 20.6, 105.2, 0.8 per minute |
| Integral minimum / maximum | −5 / 90 |
| Minimum / maximum heating water temperature | 41 / 75 °C |
| Control and telemetry interval | 60 seconds |
| Baud rate, read/write timeout, total communication attempts | 115200, 2 seconds, 5 attempts |
| Heating-off command, PI activation threshold, PI output baseline | 39, 40 °C, 40 °C |
| Water setpoint step | 1 °C; configurable whole-degree multiples, clamped to water limits |
| Room target minimum / maximum / step | 5 / 35 / 0.5 °C |
| Available operating modes | Heat and Off; one or both can be exposed |
| Initial room target, operating mode, integral | 20 °C, Heat, 0 |
| Restore saved target, mode and integral | Enabled |
| Frost protection and permission to override Off | Both enabled |
| Frost temperature source and threshold | Gateway heating water, 22 °C; room sensor can be selected |
| Frost heating water target | Empty: follows minimum water temperature; optional separate target |
| Room-sensor failure action and target | Heat at 60 °C; Off or Hold last water command can be selected |
| DTR/RTS on serial open and close | Leave unchanged; each can be set Low or High |

Changes automatically reload the integration; no Home Assistant restart is needed.
Existing entries receive the new defaults. Multiple gateways are supported as
separate integration entries.

PI tuning and frost thresholds have no arbitrary upper limits or fixed decimal
increments. Values must be finite; Kp and the integral factor must be nonnegative,
and Ti, timeouts, the update interval and room-target step must be positive.
Gateway temperature commands remain whole numbers within its supported ranges.
Failsafe and explicit frost targets must lie within the configured water limits.
The initial room target and integral must lie within their respective limits,
and the initial mode must be among the available modes.

Saved state takes precedence over initial values. Disable **Restore saved target,
mode and integral** to apply the initial settings on restart or options reload.
Restored values are clamped to the current limits; a saved mode that is no longer
available falls back to the initial mode. Change the current room target through
the climate entity for immediate control.

The room sensor must declare a Celsius, Fahrenheit, or Kelvin unit. Readings are
converted to Celsius; missing or unsupported units and nonfinite readings are
treated as sensor failures.

## Operation and safety behavior

At the configured interval, the integration sends `s <setpoint>` as the firmware
heartbeat and then sends `g` to retrieve boiler state. Target and HVAC mode
changes also request an immediate update. Room-temperature changes are consumed
by the next control cycle. Integral accumulation remains proportional to elapsed
time in minutes regardless of the polling interval. The first update after
setup uses the restored or initial integral without adding time spent offline.

The PI water target is `Kp × (room error + integral / Ti) + output baseline`.
Heating is requested when this exceeds the activation threshold. Heating targets
are clamped to the water limits and rounded to multiples of the configured
whole-degree step; the limits take priority at the endpoints.

The serial connection is kept open. By default, DTR/RTS remain untouched so
reconnecting does not intentionally reset the gateway controller; their open
and close states are configurable.

- In Heat mode, the PI controller determines the water target.
- In Off mode, the integration sends the configured off command (`s 39` by default).
- When enabled, frost protection requests heating below its selected temperature
  threshold. It raises the water target to at least the frost target, subject to
  water limits and output rounding. It overrides Off only if that option is enabled.
- If the room sensor is unavailable in Heat mode, the selected failure action
  applies: heat at the failsafe target, turn heating off, or hold the last calculated
  command. Hold starts with the off command after setup/reload, until another
  output is calculated. Frost protection can override any failure action.
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

See the [simulator operations guide](tools/README.md) for complete instructions
for running it and attaching it with QEMU or Proxmox.

Run it with:

```bash
python3 tools/ot_gateway_simulator.py \
  --socket /tmp/otgw-simulator.sock
```

The control JSON file is optional. If it does not exist, the simulator uses its
built-in boiler defaults. The JSON Lines event log is separate output created
by the simulator; it is not an input file. See the operations guide for the
corresponding command-line options.

The simulator prints readable local-time logs and always writes all events as
JSON Lines. Add `--log-ot` to also show OpenTherm frames and timeouts in the
terminal. Its virtual firmware polls the boiler every 900 ms using decoded
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
