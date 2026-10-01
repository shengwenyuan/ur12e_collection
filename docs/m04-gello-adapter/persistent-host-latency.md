# M04: Persistent U2D2 Host Latency

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: prepared / administrator installation pending, 2026-09-15.
The operator requested replacing repeated manual FTDI latency writes with a
persistent host configuration. Scope: M04-A01 communication setup; no motor
register writes, robot control, permission relaxation or image rebuild.

## Configuration

Read-only PC inspection found the configured adapter at `ttyUSB0`, driver
`ftdi_sio`, USB vendor/product `0403:6014`, serial `FTBEQCDG`, with
`latency_timer=16`. The sysfs attribute belongs to the `usb-serial` device,
not its child `tty` node. Match USB identity rather than the assigned tty number.

The station-local file `config/local/99-gello-latency.rules` contains:

```udev
ACTION=="add|change", SUBSYSTEM=="usb-serial", DRIVER=="ftdi_sio", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6014", ATTRS{serial}=="FTBEQCDG", ATTR{latency_timer}="1"
```

All parent attributes match the same physical USB device. The rule changes only
this adapter's host receive buffering on addition/change; motor EEPROM, baud,
torque and goals are untouched. Replacing the adapter requires regenerating the
serial-specific rule. The rule is installed on the Ubuntu host, outside Docker.

From the PC, perform the one-time administrator installation:

```sh
sudo install -o root -g root -m 0644 ~/ur12e-current/config/local/99-gello-latency.rules /etc/udev/rules.d/99-gello-latency.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --action=change /sys/bus/usb-serial/devices/ttyUSB0
udevadm settle
cat /sys/bus/usb-serial/devices/ttyUSB0/latency_timer
```

Expected readback: `1`. The trigger targets the currently inspected port only;
future hardware re-enumeration may use a different tty number and is matched by
serial automatically. No collection launch is needed to apply or inspect this
setting. Do not grant passwordless general sudo or run collection as root.

## Acceptance and limits

Verify syntax on the Ubuntu host, then read back 1 ms after installation. Confirm
persistence after a later operator-controlled reconnect or reboot. Until then,
installation/reconnect acceptance remains pending. Startup failure evidence
`1789410820697186739` lost its original exception during reader cleanup; observed
16 ms buffering is a configuration regression, not proof of that first failure's
cause. Queue/error-preservation repair remains a separate work item.

Preparation PASS: station-local rule delivered to `~/ur12e-current/config/local`;
Ubuntu `udevadm verify` reports one successful file and zero failures. No sudo
installation, attribute change, device trigger or motor traffic was performed
by the agent during preparation.

References: [ROBOTIS udev latency rule](https://emanual.robotis.com/docs/en/platform/op3/recovery/)
and [U2D2 latency setup](https://emanual.robotis.com/docs/en/platform/openmanipulator_x/quick_start_guide/).
