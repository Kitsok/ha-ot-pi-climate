# OpenTherm gateway simulator

`ot_gateway_simulator.py` emulates the Arduino OpenTherm gateway and a simple
boiler. It accepts the same `s <temperature>` and `g` commands as the real
gateway and exposes them on a Unix socket. QEMU connects that socket to a
virtual PCI serial port in the Home Assistant VM.

The simulator is the socket server, so start it before starting the VM. Only
one consumer can be connected at a time.

## Run it manually

Python 3.10 or newer is required. The simulator has no third-party Python
dependencies.

From the repository root, run:

```bash
python3 tools/ot_gateway_simulator.py \
  --socket /tmp/otgw-simulator.sock \
  --control-file /tmp/otgw-simulator-control.json \
  --json-log /tmp/otgw-simulator.jsonl
```

Stop it with Ctrl+C. It removes its socket during a normal shutdown. If the
process is killed, it safely replaces a stale socket the next time it starts.
It will refuse to replace a non-socket file at the configured path.

Useful options are:

```text
--socket PATH                 Unix socket exposed to QEMU
--control-file PATH           Optional runtime-control JSON file
--json-log PATH               Structured event log in JSON Lines format
--poll-interval SECONDS       Boiler polling interval; default 0.9
--watchdog-timeout SECONDS    Missing-command timeout; default 300
--initial-temperature CELSIUS Initial boiler-water temperature; default 25
```

The terminal output and JSON Lines log include consumer commands, gateway
responses, and decoded OpenTherm request/response frames. Follow the structured
log with:

```bash
tail -f /tmp/otgw-simulator.jsonl
```

### Change the simulated boiler state

The control file is optional. Create or edit it while the simulator is
running; changes are detected automatically. For example:

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

`gateway_response_mode` can be `normal`, `drop`, or `malformed`. Setting
`connected` to `false` simulates OpenTherm timeouts while leaving the consumer
serial interface available. The temperature fields set the current value when
the file changes; the thermal model then continues from that value.

### Test the socket without a VM

If `socat` is installed, connect to the running simulator with:

```bash
socat STDIO,raw,echo=0 UNIX-CONNECT:/tmp/otgw-simulator.sock
```

Enter `g` or, for example, `s 55`, followed by Enter. Exit with Ctrl+C. Do not
run this test while QEMU is connected because the simulator permits one client.

## Attach it with QEMU directly

Add these options to the existing `qemu-system-x86_64` command:

```bash
-chardev socket,id=otgw,path=/tmp/otgw-simulator.sock,server=off,reconnect=1 \
-device pci-serial,id=otgw-serial,chardev=otgw
```

A complete command therefore has this general shape:

```bash
qemu-system-x86_64 \
  ...the existing VM options... \
  -chardev socket,id=otgw,path=/tmp/otgw-simulator.sock,server=off,reconnect=1 \
  -device pci-serial,id=otgw-serial,chardev=otgw
```

`server=off` is important: the simulator owns the listening socket and QEMU is
the client. `reconnect=1` asks QEMU to reconnect after a disconnect. QEMU 9.2
and newer also accepts the more precise `reconnect-ms=1000`; use only one of
the two reconnect options.

Start the simulator first, then QEMU. The VM receives a 16550-compatible PCI
serial controller. Linux normally names it `/dev/ttyS0`, `/dev/ttyS1`, or the
next available `ttyS` device. The socket path exists only on the host and must
not be entered in the Home Assistant integration.

For regular use, prefer a socket under `/run` rather than `/tmp`:

```bash
python3 tools/ot_gateway_simulator.py \
  --socket /run/otgw-simulator/otgw.sock \
  --control-file /etc/otgw-simulator/control.json \
  --json-log /var/lib/otgw-simulator/events.jsonl
```

The parent directories must exist and be writable by the account running the
simulator. QEMU's process must be able to traverse the socket directory and
open the socket, which the simulator creates with mode `0660`.

## Attach it to a Proxmox VM

Run the simulator on the Proxmox node that hosts the Home Assistant VM. The
following example uses `/run/otgw-simulator/otgw.sock`; substitute the actual VM
ID for `<VMID>`.

First stop the VM and inspect its existing extra QEMU arguments:

```bash
qm stop <VMID>
qm config <VMID> | grep '^args:'
```

If there is no existing `args:` setting, add the serial backend and device:

```bash
qm set <VMID> --args '-chardev socket,id=otgw,path=/run/otgw-simulator/otgw.sock,server=off,reconnect=1 -device pci-serial,id=otgw-serial,chardev=otgw'
```

If `args:` already exists, preserve its entire current value and append the two
new QEMU options to it. `qm set --args` replaces the property; blindly running
the command above would discard existing custom arguments. The resulting VM
configuration contains a line like this:

```text
args: -chardev socket,id=otgw,path=/run/otgw-simulator/otgw.sock,server=off,reconnect=1 -device pci-serial,id=otgw-serial,chardev=otgw
```

Confirm that Proxmox includes the options in the generated command, then start
the VM:

```bash
qm showcmd <VMID> --pretty
qm start <VMID>
```

The VM configuration is stored by Proxmox under
`/etc/pve/qemu-server/<VMID>.conf` (internally under the current node's
`qemu-server` directory). Prefer `qm set` over editing that file directly.

Custom host socket paths are node-local. Live migration will not carry the
simulator or socket to another node. Either keep the VM on that node or install
and start the simulator with the identical socket path on every possible target
node. Test migration and HA reconnection explicitly before relying on it.

### Run the simulator as a service on a Proxmox or QEMU host

For a durable `/run` socket, install the script and create a systemd service.
These commands are examples and require root privileges:

```bash
install -D -m 0755 tools/ot_gateway_simulator.py \
  /usr/local/libexec/ot_gateway_simulator.py
install -d -m 0755 /etc/otgw-simulator
```

Save the following as `/etc/systemd/system/otgw-simulator.service`:

```ini
[Unit]
Description=OpenTherm gateway simulator
After=local-fs.target
Before=pve-guests.service

[Service]
Type=simple
RuntimeDirectory=otgw-simulator
RuntimeDirectoryMode=0755
StateDirectory=otgw-simulator
ExecStart=/usr/bin/python3 /usr/local/libexec/ot_gateway_simulator.py --socket /run/otgw-simulator/otgw.sock --control-file /etc/otgw-simulator/control.json --json-log /var/lib/otgw-simulator/events.jsonl
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
```

Then enable and start it:

```bash
systemctl daemon-reload
systemctl enable --now otgw-simulator.service
systemctl status otgw-simulator.service
journalctl -u otgw-simulator.service -f
```

This simple unit runs as root, which also makes its `0660` socket accessible to
the root-owned QEMU process used by Proxmox. On a non-Proxmox host, a dedicated
service account and shared group are preferable; ensure the QEMU process is in
the socket's group before tightening the unit.

Because the VM may start before the service during host boot, keep the reconnect
option in the QEMU configuration. Starting the service before manually starting
the VM makes initial diagnosis easier.

## Select the serial port in Home Assistant

After booting Home Assistant OS, open **Settings → System → Hardware → All
Hardware** and find the newly added serial controller. Its device path will
usually be `/dev/ttyS0` or `/dev/ttyS1`.

Configure **OpenTherm PI Climate** with that `/dev/ttyS*` path and the desired
room-temperature sensor and PI settings. The configured baud rate remains
115200. The emulated UART transports a byte stream through QEMU, so it does not
need to match a physical host UART.

Unlike USB passthrough, a PCI serial port commonly has no
`/dev/serial/by-id/...` alias. Its `/dev/ttyS*` number remains stable while the
VM's serial hardware and device order are unchanged.

## Troubleshooting

- **QEMU cannot connect to the socket:** verify the simulator is running and
  `ls -l /run/otgw-simulator/otgw.sock` shows a socket. Check every parent
  directory's execute permission and the QEMU process's access to the socket.
- **The simulator rejects a client:** disconnect `socat` or another test client;
  only the VM should remain connected.
- **No serial device appears in Home Assistant:** check `qm showcmd <VMID>
  --pretty` or the raw QEMU command for both `-chardev` and `-device`. Fully stop
  and restart the VM after changing its virtual hardware.
- **Home Assistant opens the wrong port:** inspect All Hardware and try the new
  `/dev/ttyS*` device rather than the host's Unix-socket path.
- **The integration reports timeouts:** watch both `journalctl -u
  otgw-simulator.service -f` and the JSON Lines log. Look for `client_connected`,
  `consumer_rx`, and `consumer_tx` events.
- **The VM moved to another Proxmox node:** start an equivalent simulator there
  at the same path or move the VM back to the original node.
