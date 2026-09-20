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
