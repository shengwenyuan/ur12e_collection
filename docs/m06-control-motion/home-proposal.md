# M06: One Application HOME / READY Pose

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: adopted for the application/simulator; physical motion acceptance NOT RUN.
The user confirmed one READY/HOME and authorized its native PolyScope Home
implementation in URSim. The earlier all-zero initialization waypoint is retired.
No encoder offsets are reset. Physical entrypoints remain disabled.

## Confirmed UR target

Joint order: base, shoulder, elbow, wrist1, wrist2, wrist3.

```text
degrees: [0, -90, -90, -90, 90, 0]
radians: [0, -pi/2, -pi/2, -pi/2, pi/2, 0]
```

The user explicitly confirmed observing this exact six-joint target on the real
robot: the arm is L-shaped and the end effector points vertically downward.
Record this static pose correspondence as user-confirmed physical evidence, not
an inferred or still-unconfirmed geometry. Approach/return paths, motion limits
and swept camera/cable clearance remain unvalidated. A simulation must reproduce
the observed pose with the actual base/tool configuration.
A nominal UR10e model may assist initial exploration but does not establish
UR12e hardware geometry or motion acceptance. Do not normalize wrist angles onto
a different branch. The shoulder-only pose and earlier all-zero pose are not
additional required waypoints in the adopted application lifecycle.

Use the existing `ready_q_rad` field as the station single source of truth;
HOME is a human-facing alias, not a second independently configured target.
Keep the generic station example unset and `motion_accepted=false`. The GELLO
mapped READY target, positioning/holding behavior, tolerances and paths remain
unresolved until its interface is delivered.

Implemented simulator lifecycle: INITIALIZE (read-only checks) -> explicit validated
GO_READY -> READY_HOLD. Both devices must reach their mapped targets before
leading/recording is enabled. Returning HOME does not start recording. Stopping
an episode still holds the current pose; it does not automatically return HOME.

The user selected official URSim for basic motion simulation and excluded Gazebo
on 2026-09-10. See the [environment setup](ursim-setup.md). Production M06
implementation and acceptance remain separate. Keep the stable M06-A01..A04
meanings; simulator motion does not authorize physical control.
