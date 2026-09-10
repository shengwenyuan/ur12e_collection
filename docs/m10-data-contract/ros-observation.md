# M10/M01: Optional Read-Only ROS 2 Observation

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: accepted for the explicit simulator observation scope, 2026-09-10.

The collector already uses native ROS-CDR MCAP. Add an optional live observation
sidecar to make current session phase and measured state inspectable with ordinary
Jazzy tools. This sidecar is a consumer only: no motion subscriptions, services,
SDK connection or camera pipeline. Default collection remains independent of it.
Do not add a generic event framework or put DDS work in the control loop.

## Scope and interfaces

- A spawned ROS process consumes a bounded queue of existing M10 records and
  phase/snapshot events. Parent submission is nonblocking. Queue overflow or a
  dead observer records explicit telemetry loss; it cannot stop/restart following,
  modify the raw MCAP, acquire a robot lease or delay a control tick.
- Publish standard `sensor_msgs/JointState` for actual UR joints, mapped leader
  intent and sent commands on distinct namespaced topics. Actual velocities may
  populate velocity; motor current is not effort and never populates effort.
- Publish actual TCP as `geometry_msgs/PoseStamped` in the UR base frame. Convert
  its axis-angle rotation vector to a unit quaternion, not Euler angles. Preserve
  original controller/host timestamps and auxiliary registers in the existing
  JSON record envelope on a separate `std_msgs/String` topic.
- Publish phase and immutable snapshot as JSON status/context. Use bounded QoS;
  retained status/context helps a late observer without replaying motion.
- This first implementation is explicitly selected for the verified simulator
  session. ROS uses localhost-only discovery in that container. Physical control
  remains unavailable. Real GELLO and Hand-E are still absent/bypassed.
- Do not publish wrist TF from unverified TCP-to-flange offsets. Live TF and
  calibration command services remain later consumers of verified physical
  frames/configuration. Images stay in their existing single-owner path.

## Acceptance

M10-A01/A03: distinct actual/intent/sent messages, exact mapped receipt time,
raw JSON provenance, unit quaternion conversion including zero rotation, and no
current-as-effort mistake. M01 observability: real Jazzy publisher/subscriber
round trip, late status/context observation, bounded queue behavior and dead
observer handling. M09 isolation: active URSim following and MCAP completion
continue if the optional observer is killed; its loss is explicitly reported.

Run native pure tests, actual ROS tests in the pinned container, then short
URSim sessions with the sidecar enabled and killed. This optional observer does
not change the already accepted non-ROS-sidecar 20 x 40 capture gate. Record
latency/loss and update the module matrix after actual results. No lab access.

## Implementation and checks (2026-09-10)

The optional `--ros-observe` flag starts the process before any motion. Its queue
holds 32 record batches; stream QoS is best effort/depth 16, context/status are
reliable/transient local/depth 1. `dropped_records` counts parent admission loss,
not end-to-end DDS delivery. The parent never waits on a child-owned lock or DDS
operation. Observation failure is separate from authoritative archive failure.

Topics below `/ur12e_collection` are `actual_joints`, `leader_joints`,
`sent_joints`, `tcp`, `records`, `context` and `status`. Joint/pose records cover
only the recorded control window; phase/context remain available outside it.
There is no implied continuously sampled pose during Home or held review.
`header.stamp` maps host receipt to Unix, while `records` retains original source
and receipt clock domains. The snapshot retains simulated and missing-device flags.

Native checks: **248 PASS / 5 skipped**, Black and Pylint 10.00/10.
Real Jazzy observation checks: **7 PASS**, including late retained context/status,
all distinct typed streams, bounded saturation and process-death admission loss.
The first integration launch failed before motion because the read-only container
could not create `~/.ros/log`; the launcher now explicitly uses `/tmp/ros-log`.
Preserve `session-1789031363614981552` as a failed startup, never accepted capture.

Jazzy discovery is explicitly `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`; it is
not a network-wide graph. Subscriber QoS must match the stream/retained policies.
See the official [RMW QoS reference](https://docs.ros.org/en/ros2_packages/jazzy/api/rmw/generated/enum_types_8h_1a185449ad538d09dc2ded558b425bda29.html)
and [ROS durability guidance](https://docs.ros.org/en/humble/Concepts/Intermediate/About-Quality-of-Service-Settings.html).

Actual URSim integration **PASS**:
- `session-1789031391946054885`: 5 seconds, 151 accepted groups, no rejected
  wrist anchors, no observer admission loss, complete independent MCAP verification.
- `session-1789031439596946670`: observer SIGKILL halfway through 5 seconds;
  following continues, 150 accepted groups, normal stop/hold and verified MCAP.
  Observer reports its exit and 481 subsequently rejected records. No restart or
  new authority is attempted. Expired third-view buffer entries are ordinary
  pruning, not rejected wrist anchors.

Reproduce from the repository with the pinned local client image:

```sh
python scripts/sim_control.py session --ros-observe --episodes 1 --seconds 5
python scripts/sim_control.py session --ros-observe --kill-observer --episodes 1 --seconds 5
python scripts/sim_control.py console --ros-observe
```

Use `--client-image TAG` to select a tested local amd64 dependency image. The
launcher freezes and hashes current sources, verifies the official simulator and
isolated network, and never accepts a physical host. Real DDS tests are in
`tests/test_observation.py`; they must run with the Jazzy environment sourced.
Native test skips do not substitute for their seven actual container passes.
Physical ROS/control integration, calibration services and TF remain **NOT RUN**.
