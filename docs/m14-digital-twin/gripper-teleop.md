# M14: Native Simulated Gripper Teleoperation

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: accepted for native simulated motion-trend verification, 2026-09-12. The user
approved minimal implementation and deployment using this plan. The user requested gripper control as
an extension of the accepted PC-native arm teleoperation workflow. No new
implementation or physical actuation is authorized by this draft.

## Scope and existing evidence

Primary module M14; reuse M04 leader acquisition/calibration and M06 ownership.
Keep M05 physical Hand-E acceptance separate. The existing reader already
acquires seven encoder positions at 120 Hz. The existing fixed gripper endpoint
mapping is superseded for this new workflow by the user decision below. The
Robotiq-style integer command domain remains 0..255; historical calibration
artifacts must retain their original meaning.
The previous arm-only entry fixed both fingers at the URDF's 0.025 m open
position. This increment transmits a gripper component with each arm command
and applies the executed finger position in the scene session layer.

## Aligned mapping: 2026-09-12

At each explicit start of following, capture the actual leader gripper angle
as an immutable reference, theta0. The follower fingers are fully open at that
moment. This means the Space transition into following, not process startup or
the earlier HOME request. Use the actual acquisition associated with the start
reference, never a median or a fixed historical encoder count.

Define delta_deg as rotation from theta0, with counterclockwise positive:

```text
closure = clamp(delta_deg / 45, 0, 1)
position_request = round(255 * closure)
nominal_aperture_m = 0.050 * (1 - closure)
```

- Initial angle: fully open, 0% closure.
- Counterclockwise 22.5 degrees: 50% closure.
- Counterclockwise 45 degrees: fully closed, 100% closure.
- Clockwise 45 degrees from the closed endpoint returns to the original angle
  and fully opens the fingers. This is a 45-degree total effective travel,
  not a +/-45-degree interval centered on a half-open pose.
- Positions beyond either endpoint saturate. Preserve the original reference
  even after saturation; never integrate incremental deltas or rebase mid-run.
- Each new following interval captures a fresh reference with fingers open.
  Six arm joints retain their accepted episode-relative mapping.
- Counterclockwise observation side and raw encoder sign must be documented
  consistently and verified with the operator; do not infer them from an old
  absolute endpoint pair. The reader's existing 4096-count/revolution scale
  makes the nominal 45-degree travel 512 counts.

## Execution contract
- Preserve leader encoder counts, requested gripper position, applied command
  and executed simulated aperture as distinct quantities. Keep the integer
  command domain 0..255; normalized training features remain external scope.
  Simulated feedback must not masquerade as measured Robotiq registers.
- Use the same acquisition and ownership cycle as the arm, with optional twin
  dispatch carrying the accepted gripper target too. Reuse 120 Hz intent
  production; coalesce commands before independent scene updates. Do not add
  another device reader or GUI-owned teleoperation loop.
- The scene adapter maps closure to its nominal symmetric finger travel:
  each finger coordinate = 0.025 * (1 - position / 255) meters. This corresponds
  to nominal 50..0 mm total opening and models no contact or grasp force.
- Simulated aperture rate limit: 50 mm/s total opening change, hence
  one second for full travel. It is configurable and is not a physical Hand-E
  speed-register value. No force behavior or dynamics is claimed.
- Required start condition: simulated fingers are fully open before following
  begins. Open them during explicit HOME and require
  completed opening before engagement; no fixed leader lever pose is required.
  During following, Space, Ctrl+C and source/follower loss hold both arm and
  executed gripper pose. They never auto-open a held object.
- Remain PC-local with configured scene paths. No leader motor writes, physical
  UR/Hand-E control, camera/MCAP integration or dynamic grasping in this increment.

## Ordered implementation after alignment

1. Confirm opening preparation and encoder direction/viewpoint. Persist the
   mapping policy and per-interval reference separately from historical fixed
   endpoint calibration; no new workflow may silently use the old endpoints.
2. Extend the shared command/executed feedback contract and native dispatch,
   preserving the existing six-axis interface and backend-specific feedback.
3. Add bounded kinematic gripper execution and scene finger animation; retain
   tool attachment, unchanged saved layers and existing ownership/fault logic.
4. Test zero/22.5/45-degree mapping, both saturation boundaries and reversal
   after saturation, encoder sign, fresh interval baselines, rate bounds,
   first engagement, stop/fault hold, stale input and optional twin isolation.
5. Deploy the matching package and scene adapter on Ubuntu; verify live lever
   motion alone and together with arm movement, then record user acceptance.

## Acceptance

M14-A01: PASS requires distinct input/command/executed semantics; correct
open/mid/closed geometry; correct direction; no gripper-driven arm movement;
no arm-driven aperture change; and no mid-interval reference reset. Distinct
leader starting angles must produce identical aperture responses to the same
relative rotation, independently of historical endpoint counts.
M14-A02: PASS requires bounded optional delivery, stop/fault hold and no physical
control access. Existing arm acceptance remains a regression requirement.
M04 mapping checks cover the relative gripper reference and direction; no physical M05 gate is
passed by simulating a jaw opening.

Use the 50 mm/s total opening speed and
open during explicit HOME before engagement. Encoder closing sign is configured
as +1 (counterclockwise viewed toward the output shaft). The user completed
manual trend verification with the deployed configuration. The 45-degree relative mapping is confirmed.

## Implementation and software acceptance

- Relative mapping uses an immutable actual start sample and 512-count closing
  travel (45 degrees), independent of historical fixed endpoints. Integer
  command quantization remains 0..255; the midpoint rounds to 128.
- HOME sends an opening request with the arm route. `ready` requires executed
  gripper position zero. Starting enters `engaging` until follower feedback is
  fresh within the existing 100 ms input-reference gate, then captures the
  reference. Space can cancel a pending engagement. Mainline limits are unchanged.
- Local protocol version 2 sends arm and gripper atomically, including to optional
  twins. Executed simulated gripper position and nominal aperture remain separate
  from input and requested targets. Version mismatch fails rather than ignoring
  a tool command. No physical Hand-E socket or leader motor writer is opened.
- The kinematic engine applies the configured aperture speed and freezes both
  arm and gripper on stop, release or heartbeat expiry. The scene caches the
  tool model and updates both finger transforms while retaining tool attachment.

**PASS, software:** 484 tests, 5 skipped; the 32 native/gripper tests cover signed
relative mapping at different starting angles, zero/mid/endpoints, saturation
and reversal, fresh rebasing, invalid values, rate bounds, independent arm/tool
movement, stop/release/watchdog hold, atomic optional dispatch and startup
freshness. Full Black and Pylint checks pass (10.00/10).

**PASS, Ubuntu scene:** nine OpenUSD tests, including measured 25 mm per-finger
travel across open/half/closed, unchanged arm transforms and saved layers.
Scene adapter/test formatting and Pylint pass (10.00/10).

**Initial integration failure retained:** a second engagement in the original
native entry rejected follower HOME feedback older than the 100 ms reference
gate under GUI load. Engagement now waits for fresh feedback without loosening
the gate; dedicated stale/future-feedback tests cover the fix. The initial
error is retained as `gripper-integration-before-fresh-start.err`.
A host-only test attempt lacked `dynamixel_sdk` in the scene environment; no
unnecessary serial SDK was installed there. The intended control runtime is
the installed restricted Docker image.

**PASS, installed Ubuntu + actual Isaac:** a synthetic leader fixture exercised
HOME, half/full closure, saturation beyond 45 degrees, reversal to half/open,
stop holding at 128, and a new interval starting at encoder 8000 with full
opening. There were 959 conditioned arm/tool sends; no physical command was
sent. Evidence: `artifacts/native/gripper-integration.json` and its empty final
error log on the native checkout. These are simulated-input results, not manual
gripper direction acceptance.
The actual restricted terminal launcher also read the connected leader, reached
`needs_home`, and exited cleanly on Ctrl+C (130); no following was started
in that final physical-input startup check.

## Delivery and manual verification

Use `ur12e-collection:native-isaac` on Ubuntu, linux/amd64, image
`sha256:a453b21dbc31204fbf75c7e8e6bf7eea0a13101c2d02b93ae7d6d98ec823231f`.
The installed package matches the working source; label
`f99acfe-native-gripper-working` identifies this uncommitted increment.
The existing Isaac 6.0.1 environment and scene assets are reused; only the
configured pose adapter changes. Production physical control remains disabled.

Start the scene with the existing `scripts/isaac_follower.py` entry if its
window is not already open. In another PC terminal:

```bash
cd ~/ur12e-collection-sim
.venv/bin/python scripts/teleop.py --config config/teleop.isaac.json
```

Support the leader. Space requests HOME and full opening; after `ready`,
Space starts following and captures the gripper reference when `following`
appears. Rotate the lever counterclockwise through 22.5 and 45 degrees,
then return clockwise. Check saturation beyond both endpoints and stop while
partly closed; Space must hold, not release. Repeat HOME/start from a different
lever position and confirm the new origin is fully open. Verify combined arm
and gripper motion without cross-coupling. If the observed closing direction
is reversed, change configured `gripper.closing_sign` after ending the session;
no image rebuild or motor register write is required.

**PASS, operator trend verification:** on 2026-09-12 the user concluded the
PC leader + Isaac trend verification and requested committing this increment.
This closes the manual simulated arm/gripper trend scope. It does not establish
long-duration ergonomics, contact/grasp-force simulation, physical Hand-E
actuation or combined camera/MCAP acceptance.
