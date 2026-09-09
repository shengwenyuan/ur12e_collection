#!/usr/bin/env python3
"""Exercise M08 on saved logs without cameras or station role inference."""

import argparse
import collections
import decimal
import heapq
import json
import pathlib

from ur12e_collection import contracts
from ur12e_collection import matching


def frames(path: pathlib.Path, role: str):
    """Convert reported global-time values without inventing new exposures."""
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            provenance = []
            for kind in ("color", "depth"):
                if row[f"{kind}_domain"] != "timestamp_domain.global_time":
                    raise ValueError("replay requires SDK global-time logs")
                source_ns = int(
                    decimal.Decimal(str(row[f"{kind}_timestamp_ms"]))
                    * 1_000_000
                )
                provenance.append(
                    contracts.Provenance(
                        path.stem,
                        row[f"{kind}_frame_number"],
                        contracts.SampleTime(
                            source_ns,
                            row[f"{kind}_domain"],
                            row["received_monotonic_ns"],
                        ),
                        simulated=False,
                    )
                )
            yield matching.Frame(
                role,
                0,
                "assumed-sdk-global",
                provenance[0].time.source_ns,
                provenance[0],
                provenance[1],
                provenance[1].time.source_ns,
            )


def main() -> None:
    """Print counters under an explicit common-clock assumption."""
    parser = argparse.ArgumentParser(description=__doc__)
    for role in contracts.CAMERA_ROLES:
        parser.add_argument(
            "--" + role.replace("_", "-"), required=True, type=pathlib.Path
        )
    parser.add_argument(
        "--assume-common-clock", action="store_true", required=True
    )
    args = parser.parse_args()
    matcher = matching.Matcher("assumed-sdk-global")
    inputs = [
        frames(getattr(args, role), role) for role in contracts.CAMERA_ROLES
    ]
    results = collections.Counter()
    now_ns = 0
    for frame in heapq.merge(
        *inputs, key=lambda f: f.color.time.received_monotonic_ns
    ):
        now_ns = frame.color.time.received_monotonic_ns
        results.update(r.reason for r in matcher.push(frame, now_ns))
    results.update(r.reason for r in matcher.finish(now_ns))
    print(
        json.dumps(
            {
                "schema_version": 1,
                "time_basis": "SDK global_time assumed; unverified",
                "roles": "analysis labels; no station binding",
                "groups": dict(results),
                "diagnostics": dict(matcher.counters),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
