# M12: Serial-Bound External Extrinsics

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: aligned / implementing. The operator explicitly requested activation of
camera_3's newest colleague result on lispc, binding by serial rather than
renaming left/right roles. Collection remains operator-started.

## Contract and implementation

1. Import the fixed-camera YAML with its explicit serial header, camera name,
   timestamp, metric `T_base_camera` and original report. Preserve source bytes
   and SHA-256. Match exactly one configured camera by serial; do not swap roles.
2. Add a distinct schema-4 external calibration record. Record validation status
   as `external_provided`, with collector numerical validation not run. Existing
   schema-1/3 solved-bundle validation remains unchanged. Validate finite rigid
   transforms, source integrity, frame/units and binding before atomic activation.
3. Embed the full external record in the existing station/calibration snapshot.
   Preserve SDK-observed color intrinsics separately: an extrinsics-only import
   does not replace optics with the colleague's mapped 720p intrinsic fit.
4. Update only the selected camera result and mount generation. Preserve the
   station base generation when declared; otherwise identify the UR base by its
   configured robot serial and mark other mount generations unspecified. These
   are configuration identities, not physical accuracy claims.
5. Rebuild the installed package on cached layers, deploy to lispc and activate
   offline before the next session. Keep rollback and existing data/config.

A versioned importer under scripts accepts source YAML, serial and station
paths. YAML parsing is confined to import; runtime verification is self-contained
and does not reopen external files. No hardware access, camera restart, motion,
old-episode rewrite or automatic session start belongs to this operation.

## Acceptance

- M12-A04: reject wrong serial, invalid transform, modified source and malformed
  report before changing station; other cameras and existing optics stay intact.
- M10-A03: a synthetic MCAP plus metadata round-trip retains the exact external
  result and its source identity, with no dependency on source file location.
- M01-A01/A03: installed package/image identity, offline import on actual station,
  byte-preserved unrelated configuration, clean help/menu cancellation.
- Real capture and geometry accuracy: NOT RUN; operator performs collection.

## Operator import

Run inside the installed image with the station directory writable and the
colleague result mounted read-only. No network or device mounts are needed:

```sh
python /opt/scripts/import_extrinsics.py \
  --source /input/final_result_all_30.yaml \
  --station /station/recording.station.json --serial 327122075735
```

The importer resolves the existing role by S/N. It copies source bytes/report
into the station file; the source mount is not needed for subsequent collection.
Start a new session after activation. Every new episode embeds the snapshot in
`metadata.json` and MCAP `metadata/episode`; already started sessions and old
episodes are unchanged. External schema 4 means supplied geometry, not an M12
independent numerical acceptance claim. Consumers select the camera by serial
and read `solution.T_base_camera` in meters.

## Software acceptance

M12-A04 and M10-A03 PASS offline: wrong serial/mode/units/rotation, source
corruption and false validation claims reject; import is atomic/idempotent and
preserves other cameras. A generated-pixel MCAP plus JSON round-trip preserves
the external result after removal of its source file. Existing schema-1/3
calibration and observed-optics checks remain covered by regression.

Mac checks: Black PASS (216 files), Pylint PASS (10.00/10), pytest **724 passed,
five skipped**. The actual latest camera_3 YAML also passed import against a
copy of lispc's station; it resolves S/N 327122075735 to the existing third_left
slot. Role labels were not changed. Initial test-fixture and lint issues were
corrected before the final full run. Installed delivery acceptance follows.
