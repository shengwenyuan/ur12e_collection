# M14: Isaac Physical Joint Drives

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

- Status: implemented / dynamics acceptance pending; static scope passed.
- Updated: 2026-09-12.
- Parent: [M14](../../meta_plan.md#m14-digital-twin-interfaces).
- Dependencies: M04 input, M06 control ownership, M14
  [native follower](native-teleop.md) and [gripper](gripper-teleop.md).

## Scope and alignment

The user requests physical joint drives as a digital-twin foundation. This round
permits static development and verification on the online Ubuntu PC, without a
visual session. The user approved this concrete plan on 2026-09-12 and requested implementation.
No physical UR, Hand-E or leader motor commands, USB acquisition, or live
teleoperation are needed. Dynamics and contact execution are subsequent gates;
static success must not be reported as their acceptance.

Add `isaac_physics` beside `isaac_kinematic`, using the existing native entry,
leader mapping, ownership, limits and bounded optional-twin dispatch. Preserve
the accepted kinematic profile. Isaac and its assets remain external to the
collector image. Resolve the scene and adapter through configuration, without
repository-specific absolute paths. Real-plus-sim operation, force fidelity,
camera recording and production deployment are outside this increment.

## Findings that constrain the design

Read-only inspection of the deployed composed USD on 2026-09-12 found:

- Separate articulation roots at `/World/UR12e/Geometry/world/base_link` and
  `/World/HandE/Geometry/tool0`. The assets were imported with fixed bases;
  the current adapter continuously authors tool placement from arm FK.
- All six revolute and two prismatic joints have force DriveAPI instances,
  but their stiffness and damping are zero. Imported maximum efforts are
  330/330/150/54/54/54 for the arm and 130 for each finger. These are asset
  inputs, not verified UR12e or Hand-E actuator specifications.
- Each finger has mass approximately 0.03804 kg and diagonal inertia
  `(1e-9, 1e-9, 1e-9)` kg m². These values require an explicit physical-model
  treatment; positive numbers alone do not establish useful inertia.
- Current feedback comes from applied kinematic poses. Its stop operation
  freezes pose and sets reported velocity to zero. Neither behavior establishes
  physical braking or solver feedback.

## Design and interfaces

1. **Execution boundary.** Keep transport/ownership separate from execution.
   Share target validation, bounded HOME target generation and lifecycle logic;
   use a small execution interface for kinematic and physical backends. Physical
   execution uses force-limited position drives, never repeated teleportation.
   Initial joint placement is allowed only during explicit simulation setup/reset.

2. **External physical scene.** Add a separately selected physical overlay and
   adapter in the scene project. Retain a world-fixed arm base; attach the tool
   rigidly to the flange, removing its independent world anchoring and resolving
   articulation ownership. Validate joint anchors and the two finger DOFs;
   avoid competing mimic and independent drives. Preserve saved source assets,
   accepted kinematic transforms and unrelated scene content.

3. **Parameters and contact preparation.** Configure gravity, fixed solver step,
   drive gains, finite effort limits and contact materials explicitly. Use
   a configured 240 Hz physics step and independent display cap; 120 Hz target
   production remains unchanged. Derive provisional finger inertia from geometry
   and mass, recording the approximation and source rather than silently retaining
   placeholder values. Audit collision shapes and filter mechanically adjacent
   pairs only; preserve meaningful self, tool/object and table collisions.
   Gains, effort limits and friction remain simulation parameters pending tuning.

4. **Measured semantics.** Publish arm positions/velocities and both finger
   coordinates only after solver readback. Keep requested closure separate from
   achieved aperture; report asymmetric finger motion instead of hiding it in a
   requested 0..255 value. Use radians, rad/s, meters, seconds and explicit joint
   names at the collector boundary. Isolate any USD angular-degree conversion
   in the adapter. Include backend identity, ownership epoch, simulation time,
   sample sequence and host monotonic acquisition time. Frozen simulation time
   cannot produce fresh executed samples. Version wire changes explicitly and
   reject a configuration/feedback backend mismatch.

5. **Lifecycle.** HOME completion and gripper-open readiness use measured
   tolerances, not exact floating-point equality. Preserve existing real-control
   limits and gates. Stop, source loss and ownership loss latch physical holding
   targets at the latest measured pose; never fabricate zero velocity, teleport,
   auto-open, or resume on input recovery. Continue solver/readback while holding
   so residual motion remains observable. Simulation pause/reset invalidates the
   active interval and requires explicit reinitialization. A hold request is not
   a claim of instantaneous physical rest.

## Ordered implementation

1. Add the physical profile, validated parameters and backend-neutral execution
   boundary; retain the kinematic regression suite and optional-twin isolation.
2. Add the external physical overlay/adapter and static topology, mass, inertia,
   drives, units and collision checks against the installed Isaac 6.0.1 APIs.
3. Implement solver stepping, target application, measured feedback and lifecycle
   handling. Keep renderer/UI optional and avoid branching in leader mapping.
4. Add unit tests with explicit execution doubles and Ubuntu OpenUSD static
   tests; run formatting, lint and relevant regressions. Record source/asset
   hashes because the external scene directory currently has no Git history.
5. Record static results and remaining dynamic gates. Leave the deployed current
   image and default kinematic launch intact until a separately tested release.

## Acceptance

Detailed suffixes belong to the existing M14-A01/A02 contracts.

| Case | Criterion | This round |
| --- | --- | --- |
| M14-A01-P01 | Config selection, relocation, invalid/unsupported parameters and backend identity validation | Unit/static tests |
| M14-A01-P02 | Fixed base, rigid tool attachment, valid DOFs/anchors, finite useful inertia, drive limits and collision authoring | Ubuntu OpenUSD static tests |
| M14-A01-P03 | Targets differ from measured feedback under injected lag/contact; units, sequence and time remain truthful | Execution-double tests; no dynamics claim |
| M14-A02-P01 | Stop, expiry, owner loss, pause/reset and optional-twin faults cannot bypass ownership or fabricate rest | Unit/IPC regressions |
| M14-A01-P04 | Gravity HOME hold, signed and coupled motion, reversals, bounded tracking error and achieved stepping rate | NOT RUN; later headless dynamics |
| M14-A01-P05 | Finger/object contact, arm/table contact, stable resting contact and bounded penetration with independent jaw readback | NOT RUN; later headless contact tests |
| M14-A02-P02 | Measured stopping/holding under motion and contact, watchdog and process loss in the actual solver | NOT RUN; later headless dynamics |

Later dynamics/contact tests need quantitative thresholds and fixtures before
execution. They can run without a visual window; human visual confirmation is
not required by this plan. Static tests cannot establish convergence, stable
grasping, actual stepping rate, or accurate physical-robot dynamics.

## Implementation and validation results

The user approved the written plan and requested implementation on 2026-09-12. This
record accompanies the implementation commit based on collector `e71ca27`.
The current release image has not yet been rebuilt with this implementation.

- `config/teleop.isaac-physics.json` selects `isaac_physics` and the external
  `runtime/physical.py` adapter. The accepted kinematic profile remains selected
  by its existing configuration. No package dependencies were added.
- Native protocol **3** includes backend identity, acquisition time, sequence,
  opening readiness and physical jaw coordinates/velocities. Protocol 2 peers
  are rejected. Both native endpoint processes must use matching source before
  later runtime testing; the current release image still contains protocol 2.
- Shared bounded target generation advances HOME and jaw targets by fixed
  simulation steps. The physical owner watchdog uses host monotonic time.
  A slow host does not accumulate a burst of target-profile advancement.
- Physical feedback comes from solver readback. Repeated samples cannot renew
  freshness; fault packets retain the last acquisition time. Holding targets
  preserve separate finger positions and do not overwrite measured velocity.
  Opening readiness allows 0.2 mm per-finger position error and at most 1 mm/s
  finger speed; actual jaw values remain available without quantization.
- The external adapter uses one session overlay with a world-fixed arm and rigid
  flange/tool attachment. OpenUSD's physics parser recognizes one articulation,
  11 rigid bodies, six revolute joints, two prismatic joints and 19 colliders.
  All parsed descriptors are valid. Original saved layers remain unchanged.
- Finger inertia is estimated from collision geometry bounds and source mass.
  The bound computation includes invisible `guide` geometry. The source's tiny
  placeholder inertias are overridden only in the physical session layer.
- Force drive gains use SI configuration: arm stiffness in N m/rad, damping in
  N m s/rad, effort in N m; fingers use N/m, N s/m and N. Angular gains are
  converted to per-degree USD units; angular targets are authored in degrees.
  The articulation control/readback interface uses radians. See the official
  [OpenUSD DriveAPI units](https://openusd.org/release/api/class_usd_physics_drive_a_p_i.html).
- The runtime adapter targets the installed Isaac Sim **6.0.1.0** compatibility
  APIs `SimulationContext` and `SingleArticulation`. Their installed source
  signatures and default experience dependency were inspected without launching
  Kit. Physics is CPU TGS at a configured 240 Hz, 16 position/4 velocity solver
  iterations; rendering is independent and optional. These are configurations,
  not measured performance or accepted tuning.

| Case | Verification and environment | Result |
| --- | --- | --- |
| M14-A01-P01 | Invalid parameters, relative scene paths, explicit backend identity and protocol checks; Mac Python 3.12.13 and Ubuntu Python 3.12.3 | PASS, software |
| M14-A01-P02 | Ubuntu OpenUSD 0.26.8: connected articulation, fixed anchors, SI gain conversion, inertia, collision materials/filters, physics parser validity, repeatable overlay and unchanged source layers | PASS, static |
| M14-A01-P03 | Prescribed solver doubles: lag/contact divergence, asymmetric jaws, measured opening tolerances, duplicate clocks and independent wall/simulation timing | PASS, software; no contact execution |
| M14-A02-P01 | Shared native IPC/optional dispatch regression plus stop, release, watchdog, invalidated solver and residual-velocity tests | PASS, software |
| M14-A01-P04 | Actual solver startup, gravity hold, tracking and achieved step rate | NOT RUN |
| M14-A01-P05 | Actual contact, grasping, penetration and resting stability | NOT RUN |
| M14-A02-P02 | Actual solver stopping under motion/contact and process loss | NOT RUN |

Final regression results:

- Mac `.venv/bin/pytest -q`: **508 passed, 5 skipped**, 10.92 s. The normal
  sandbox initially denied shared memory in five existing tests; the authorized
  process/shared-memory run passed. No recorder changes were made for this.
- Ubuntu container using the unchanged `ur12e-collection:current` dependency
  image with development source mounted read-only: **511 passed, 2 skipped**,
  12.46 s. Network disabled, no devices mounted, ROS logs redirected to `/tmp`.
- Ubuntu scene `python -m unittest discover -s tests -v`: **16 passed**,
  including seven new physical-authoring checks and nine existing scene tests.
  This uses plain OpenUSD without `SimulationApp`, a timeline or a viewport.
- Repository Black check and the engineering profile's Pylint command
  (`pylint src/ur12e_collection scripts/*.py`) pass; Pylint **10.00/10**.
  The external physical adapter also passes Black/Pylint. A broader exploratory
  recursive Pylint run found existing style warnings in unchanged viewer tests;
  that directory is outside the profile's script lint selection.

Initial static failures were corrected: invisible/guide collider bounds were
excluded from inertia estimation, the installed BBoxCache binding required
positional optional arguments, and removing/reapplying the same articulation
root changed overlay list operations. Initial Ubuntu test setup also shadowed
new source with an earlier copied directory and used an unwritable default ROS
log directory. The duplicate was removed and log output moved to the container
tmpfs before the final pass. These failures are not presented as dynamics runs.

## Delivery and remaining acceptance

The new collector source is staged separately at `~/ur12e-physics-dev` on the
Ubuntu PC. The external adapter and tests are synchronized to both configured
scene repositories. All eight files in the portable
[scene manifest](physics-scene-manifest.json) have matching local/Ubuntu SHA-256
hashes. The external scene directory still has no Git history; the collector
repository records its dependency hashes, not ownership of those scene files.
Ignored run logs are under `artifacts/physics-development/`.

Current Docker images, `~/ur12e-current`, the existing native deployment and
hardware settings remain unchanged. No leader device, physical UR/Hand-E,
Isaac timeline or GUI was started. Static implementation is complete; actual
physics initialization and dynamics/contact acceptance remain pending. The next
step is a separately scoped headless solver run with synthetic input, matched
protocol-3 processes and quantitative tracking/contact thresholds. No human
visual check is required. Live leader testing and any physical actuation remain
separate decisions.

## Protocol promotion and image requirement

On 2026-09-12 the user requested committing this increment and directly updating
the protocol. Native follower IPC now requires version 3 for both kinematic and
physical backends, without a version-2 compatibility mode. An explicit regression
case rejects version-2 commands. The final native/physics/gripper subset passed
57 tests on Mac after adding that case; Black and diff checks passed.
Existing motion ownership and physical-control
authorization remain unchanged.

The mainline Docker image must be rebuilt before running this new native client
against the updated Isaac endpoint. `scripts/teleop.py` invokes the image's
installed package; its read-only repository mount does not replace that package.
The current `5185ee5` image therefore still sends protocol 2 and cannot be paired
with the new endpoint. Update the project wheel using the existing dependency
layers; no dependency version changes or Isaac installation inside the collector
image are needed. Synchronize the resulting image identity across Mac and PC
when performing the next image delivery. This commit does not itself rebuild or
replace those images, nor does it establish dynamics/contact acceptance.
