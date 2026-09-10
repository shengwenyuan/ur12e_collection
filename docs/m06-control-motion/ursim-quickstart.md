# Local UR12e Simulator

This environment uses Universal Robots' official URSim `5.22.2` image, pinned
by digest in [compose.ursim.yaml](../../compose.ursim.yaml). It runs the built-in
UR12e profile on Docker Desktop using `linux/amd64` emulation. The physical
controller runs `5.22.1`; the simulator is a different patch version.
See [setup and acceptance](ursim-setup.md) for provenance and limitations.

## Start and stop

From the repository root:

```sh
# First installation on another computer requires Internet access.
docker compose -f compose.ursim.yaml pull

# Normal startup reuses the installed, pinned image.
docker compose -f compose.ursim.yaml up -d --pull never --wait --wait-timeout 120
docker compose -f compose.ursim.yaml ps

# Stop without deleting programs or settings.
docker compose -f compose.ursim.yaml stop
```

Open [PolyScope in the browser](http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale).
The Docker Desktop project is `ur12e-sim`; its service is `ursim`.
No simulator motion starts automatically. On a fresh installation, confirm
the simulator's default safety configuration in PolyScope.
In the tested image, restart restores Local mode and powered-off state even
when the Remote Control feature remains enabled. Select Remote again for API
motion tests; do not infer readiness from the saved preference.
The health check waits for a real Dashboard version response, not merely an
open browser port. A startup timeout is a failed readiness check.

All exposed interfaces are bound to this Mac's loopback address:

| Interface | Mac endpoint | Same-network container endpoint |
| --- | --- | --- |
| PolyScope / noVNC | `127.0.0.1:6080` | `ursim:6080` |
| Dashboard | `127.0.0.1:29999` | `ursim:29999` |
| URScript secondary interface | `127.0.0.1:30002` | `ursim:30002` |
| RTDE | `127.0.0.1:30004` | `ursim:30004` |

Control checks use the internal Docker network `ur12e-sim_control` and the
verified alias `ursim-control`. The simulator also joins the separate UI network
`ur12e-sim_sim`. Control clients must not join that externally routed UI network. A container's own
`localhost` does not refer to the simulator. Production station configuration
is not mounted here, and the production collector is not started by this file.

## Basic motion

For manual pendant operations, select **Local** in the top-right mode menu,
initialize the simulated robot using the bottom-left power indicator, and use
the **Move** tab. For socket-based tests, enable **Settings > System > Remote
Control**, exit Settings, and select **Remote Control** in the top-right menu.
This setting belongs only to this local simulator.

The completed setup check used Dashboard power-on/brake-release, RTDE actual
joint readback at 30 Hz, and URScript `movej` at `v=0.2 rad/s`, `a=0.3 rad/s²`.
Targets were HOME, HOME with base +5 degrees, then HOME again. HOME is
`[0, -90, -90, -90, 90, 0]` degrees in the documented joint order. The local
programs volume contains `simulation_home.script` as an explicit test artifact;
it is not automatically loaded or executed. The initial path from URSim's
default pose is simulator-only, not an accepted physical approach route.

The [control increment](simulator-control.md) adds a shared bounded control loop
and controller watchdog. GELLO hardware and Hand-E control remain excluded;
keyboard/recording integration is not yet implemented.

With the dependency image `ur12e-collection:readonly-runtime` installed and
URSim in Remote mode, run these explicitly authorized simulator tests:

```sh
.venv/bin/python scripts/sim_control.py motion
.venv/bin/python scripts/sim_control.py watchdog --signal kill
# Explicitly release the simulator protective stop in PolyScope before another test.
.venv/bin/python scripts/sim_control.py watchdog --signal stall
```

The launcher freezes and hashes source, then mounts that copy read-only, verifies the pinned simulator
image/service/peer, and gives the client no external route or physical station
configuration. Each watchdog test intentionally kills or freezes the motion
owner. Native protective-stop recovery is deliberately not automatic.
Reports, including failures, remain under `artifacts/simulator-control/`.

For the independent native Home probe, use PolyScope Local mode to set installation
Home to READY, create a program containing one Home node, disable program looping,
set 15 deg/s and 25 deg/s², and save it as `/ursim/programs/ready.urp` with its
installation. Switch back to Remote and run:

```sh
.venv/bin/python scripts/sim_control.py native-home
```

This probe invokes the native program after closing the SDK motion program.
It does not enable the native program as the application's default READY backend.
The ordinary Home node has no client-loss watchdog; that integration is pending.

## Persistence and diagnosis

Dedicated named volumes preserve programs, PolyScope preferences, controller
configuration, GUI data and URCaps. `docker compose -f compose.ursim.yaml down`
removes the container/network while retaining those volumes. Do not add `-v`
unless intentionally resetting all simulator data. Keep volumes tied to the
pinned version, especially the GUI volume.
The fixed hostname `ursim` also keeps persisted controller host references
consistent across replacement.

```sh
docker compose -f compose.ursim.yaml logs --tail 50
docker compose -f compose.ursim.yaml exec ursim tail -50 /ursim/URControl.log
```

Dashboard reports model `UR10` even for the built-in UR12e profile; the vendor
startup script intentionally selects that control configuration and separate
UR12e serial/safety files. The tested simulator serial is `20245199999`.
Mac emulation is suitable for functional tests here; it does not qualify
real-time servo timing or physical motion. Gazebo is not required or installed.


## Current session commands

The explicit session entrypoint supports Space HOME/start/stop, `a` discard and
Ctrl+C. Keep the application console in a terminal; the source waveform is a
simulation fixture and Hand-E is explicitly bypassed.

```sh
python scripts/sim_control.py console --client-image ur12e-collection:sim-runtime-36c00b2
python scripts/sim_control.py session-faults --client-image ur12e-collection:sim-runtime-36c00b2
python scripts/sim_control.py session --episodes 20 --seconds 40 \
  --client-image ur12e-collection:sim-runtime-36c00b2
PYTHONPATH=src python tests/simulation/acceptance.py artifacts/simulator-control/session-RUN
```

The client image must already exist locally and be linux/amd64; the launcher
never pulls it implicitly. Each report identifies its frozen source and client
image. The official URSim image, identity, internal network and exclusive lease
are still mandatory; these commands accept no physical host/address argument.
The complete snapshot/MCAP validation and grouping audit must pass before claiming
a successful full batch. Failed/partial results remain available for diagnosis.
