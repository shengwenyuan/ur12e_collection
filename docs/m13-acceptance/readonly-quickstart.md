# Read-Only Observation Recording

This mode records three cameras plus independent UR and Hand-E feedback. It
never enables remote control, sends robot motion/IO/program commands, activates
the gripper or emits training action records. An unavailable service fails the
run; the collector does not enable or reset it.

## Local software check

Use the supplied immutable runtime image ID from `manifest.json`. On Mac,
`linux/amd64` runs under Docker emulation and does not validate USB or lab timing.

```sh
docker run --rm --platform linux/amd64 --network none IMAGE_ID \
  shadow --backend synthetic --read-feedback --episodes 2 --seconds 1 \
  --revision SOURCE_REVISION --output /data/software-smoke
```

Mount a local data directory if the synthetic recordings must survive container
exit. Every synthetic source is marked explicitly; no network device is opened.

## Ubuntu lab check (deferred until lab access resumes)

Load and verify the bundle using `scripts/load-release`. Preserve the existing
station configuration. Prepare a separate reviewed observation station JSON
outside Git, containing the three camera serials, confirmed UR host and serial,
and verified Hand-E bridge host/port. Physical third-left/third-right roles must
be assigned by the operator; the earlier diagnostic slots do not prove location.
Keep `motion_accepted=false`, GELLO unavailable, calibration null and unaccepted
READY angles unset. Do not activate hardware for this test.

```sh
./scripts/observation-shadow --station /config/observation-station.json \
  --revision SOURCE_REVISION --output /data/readonly-smoke-UNIQUE \
  --episodes 2 --seconds 1
```

Unlike `camera-shadow`, this explicit launcher enables host networking for
read-only telemetry. Both launchers retain non-root execution, read-only config,
explicit USB/video devices, 4 GiB memory and disabled swap, without a CPU quota.
The bundle launcher selects the manifest image ID. Never repeat an output path.
Do not interpret this short integration smoke as a new 20-episode acceptance.

## File interpretation and timing

`follower/state` carries separate `ur_feedback` and `hande_feedback` record kinds.
UR provides controller-reported q/qd/current/TCP and robot/safety modes. TCP is
base-to-active-TCP; the active offset is not independently read back. For the
operator-confirmed zero Installation TCP in the 2026-09-13 lab recordings, this
pose coincides with flange. The physical tool extends 127 mm along flange-local z,
which is not applied by that installation. Numeric offset metadata is not yet
persisted. See [M10](../m10-data-contract/plan.md#tcp-installation-and-hand-e-timing-clarification-2026-09-13)
before downstream coordinate conversion. Getter reads are bracketed by controller timestamps, not claimed to
be an atomic RTDE packet. Power-off zero joint values are not a physical HOME
measurement. Hand-E preserves POS/PRE/STA/OBJ/FLT/COU raw integers and its query
interval; PRE is the bridge's request echo, never GELLO intent or a sent command
from this collector. Inactive-gripper responses do not establish active feedback.

Feedback MCAP publish_time is host monotonic receipt mapped to Unix through the
snapshot offset. UR uptime stays separate; Hand-E has no device acquisition
timestamp. Camera publish_time retains SDK global acquisition time. Association
is by explicit receipt/provenance fields, with a 500 ms feedback freshness bound;
there is no interpolation or claim of synchronized physical sampling. Consumers
must not directly equate UR uptime with camera Unix timestamps. Each episode
requires records from both declared feedback sources and contains no action or
control-command topics. It is an observation recording, not a demonstration.

The writer uses one ordered FIFO with separate admission limits: four ordinary
image-group/event items and 64 individual feedback records. Both limits fail
explicitly on overflow. Metadata reports both queue peaks. Every image is decoded
and every aligned-depth pixel hash checked before atomic completion. Keep failed
partials and reports; a completed earlier episode survives a later failure.

Ctrl+C aborts the active episode and closes local readers. It neither moves the
arm nor changes the gripper. Real control/stop/hold behavior belongs to the later
M06/M09 implementation and is not supplied by this observation command.
