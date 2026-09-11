# Independent Read-Only URSim Viewer

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: implemented; independent read-only and browser checks PASS.
Manual leader-driven direction observation remains separate.

## Aligned scope

On 2026-09-12 the user requested an independent read-only 3D window driven by
URSim actual joint angles, without Gazebo or changes to the control chain.
This extends the already aligned disposable Mac rehearsal scope, not production
teleoperation or recording acceptance. No physical or simulated motion is needed
to install or validate the viewer; the user operates the separate controller.

## Design and implementation steps

1. Add `scripts/sim_viewer.py` and isolated support files under
   `scripts/sim_viewer/`. Reuse the existing image and official simulator identity
   inspection. Start only a receive-only RTDE client in the internal simulator
   network. Do not acquire the control lease, initialize the robot, upload a
   program, read USB, or import/use RTDE control or IO clients.
2. Subscribe to actual_q and controller timestamp at 30 Hz. Transfer bounded JSON
   observations over the reader container's stdout. A local HTTP server binds
   only 127.0.0.1, serves a fixed asset allowlist and read-only state endpoint,
   and reports both reception loss and controller timestamp stagnation. Browser
   refresh does not reconnect RTDE; viewer exit closes only its own reader.
3. Render an orbitable 3D model using official nominal UR10e/UR12e DH dimensions,
   six actual joint angles, a grid, base axes and an asymmetric flange marker so
   wrist3 rotation is visible. Simplified link geometry is a trend aid; it is
   not calibrated collision geometry or a Hand-E/TCP model. No interpolation,
   predicted poses, target substitution, or joint control widgets.
4. Bundle pinned Three.js assets and MIT license for offline runtime. Show
   current/stale/disconnected status, joint degrees and data age. Orbit, zoom
   and camera presets affect only the view. No Gazebo, ROS observer, recorder,
   new collector image, or production dependency is required.

## Checks under M13-A04

- Read-only boundary: receiver-only imports/operations; no motion lease or
  initialization; fixed inspected simulator identity; loopback HTTP only.
- Malformed/nonfinite angles, timestamp regression, frozen timestamps and lost
  reader/browser polling must never appear as fresh motion.
- Kinematic fixtures: HOME flange position and direction match nominal UR data;
  each axis changes the rendered chain/orientation, including wrist3 rotation.
- Live readonly smoke: actual angles and progressing timestamp from URSim;
  browser rendering/orbit/resize and stale indication; close/restart reader
  without controlling or stopping the existing robot program.
- Manual leader direction observation remains the user's separate action.

## Sources and versions

- [UR official DH table](https://www.universal-robots.com/articles/ur/application-installation/dh-parameters-for-calculations-of-kinematics-and-dynamics):
  nominal UR10e/UR12e geometry, meters/radians.
- Three.js 0.180.0 from its npm release, bundled with its MIT license and hashes.
- Existing `ur12e-collection:live-leader`, Python 3.12, ur-rtde 1.6.5.

## Results

- PASS: 11 focused tests in `scripts/sim_viewer/tests/test_viewer.py`; isolated
  from the installed collector test suite because this viewer and Node-based
  geometry checks are Mac-side utilities. Includes frozen timestamps, malformed
  data, regression, reader EOF/size bounds, launch isolation, receive-only API
  calls, HOME flange position/direction and all six joint rotations.
- PASS: Black and Pylint 10.00 for the Python launcher/reader.
- PASS: actual URSim readback at 30 Hz, displayed approximately
  [3.8, -93.1, -85.8, -96.0, 90.0, 0.0] degrees during the smoke. Controller
  timestamps progressed; observed sample ages were generally tens of ms.
  This is measured state, not an injected HOME pose or commanded target.
- PASS: browser perspective/front/top, drag orbit and wheel zoom visually
  inspected. Wrist3 changes flange orientation in the deterministic fixture.
- PASS: stopping only the viewer reader retained the last measured pose with
  `STALE` and `URSim reader disconnected`; restarting the viewer restored live
  data. No control program, motor interface or USB device was opened or stopped.
- PASS: loopback GET `/state` returns observed state; traversal path returns 404;
  POST `/state` returns 501. Evidence: local
  `artifacts/simulator-viewer/http-smoke.json`.
- NOT RUN: manual leader sweep and responsive narrow-window testing. No motion,
  physical calibration, collision-model or production acceptance is claimed.

## Run

From the repository root, in a separate terminal:

```bash
.venv/bin/python scripts/sim_viewer.py
```

Open http://127.0.0.1:8787. Keep the existing control terminal unchanged. Drag to
orbit, scroll to zoom, or use Perspective / Front / Top. Ctrl+C in the viewer
terminal closes only this observer. To use another local port, pass `--port`.
The script reuses `ur12e-collection:live-leader`; no image rebuild is required.
Three.js assets are bundled for offline use. The gold flange mark is an
orientation aid, not a simulated Hand-E model.

Focused checks:

```bash
.venv/bin/pytest -q scripts/sim_viewer/tests
.venv/bin/pylint --persistent=no scripts/sim_viewer.py scripts/sim_viewer/reader.py
```
