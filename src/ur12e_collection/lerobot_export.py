"""Explicit optional LeRobot v3 RGB/arm export; collection stays MCAP-native."""

import contextlib
import importlib.metadata
import json
import os
import pathlib
import time

import numpy as np

from ur12e_collection import contracts, projection, filesystem

LEROBOT_SOURCE = (
    "https://github.com/huggingface/lerobot/archive/"
    "7e241bd630a3719a56157a497ce5d08f244784f1.tar.gz"
)


def _dependencies():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    package = importlib.metadata.distribution("lerobot")
    origin = json.loads(package.read_text("direct_url.json") or "{}")
    if package.version != "0.6.1" or origin.get("url") != LEROBOT_SOURCE:
        raise ValueError("export requires the pinned official LeRobot source")
    # The optional ML stack is never imported by collection entrypoints.
    # pylint: disable=import-outside-toplevel,import-error
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.configs.video import RGBEncoderConfig
    import torch

    torch.set_num_threads(1)
    return LeRobotDataset, RGBEncoderConfig


def features() -> dict:
    """Six raw arm joints, RGB and integer provenance; no invented gripper."""
    result = {
        key: {
            "dtype": "float32",
            "shape": (6,),
            "names": list(contracts.JOINT_NAMES),
        }
        for key in ("observation.state", "action")
    }
    result.update(
        {
            f"observation.images.{role}": {
                "dtype": "video",
                "shape": (3, 480, 640),
                "names": ["channels", "height", "width"],
            }
            for role in contracts.CAMERA_ROLES
        }
    )
    for name in (
        "camera_ns",
        "camera_sequence",
        "wrist_receipt_ns",
        "state_receipt_ns",
        "action_receipt_ns",
        "controller_uptime_ns",
    ):
        result["source." + name] = {
            "dtype": "int64",
            "shape": (3 if name.startswith("camera_") else 1,),
            "names": None,
        }
    return result


def _compatible(episodes):
    def signature(episode):
        snapshot = episode.snapshot
        control = snapshot["control"]
        return (
            snapshot["simulated"],
            snapshot["calibration"],
            {
                role: snapshot["cameras"][role]
                for role in contracts.CAMERA_ROLES
            },
            {
                key: control[key]
                for key in ("backend", "hande", "arm_id", "leader_id")
            },
        )

    first = signature(episodes[0])
    if any(signature(episode) != first for episode in episodes[1:]):
        raise ValueError("source device/calibration contexts differ")


def export(
    paths: list[pathlib.Path],
    destination: pathlib.Path,
    action_source: str,
    *,
    rgb_arm_only: bool = False,
) -> dict:
    """Commit only after the official local loader verifies the projection."""
    if not rgb_arm_only or not paths:
        raise ValueError(
            "explicit RGB/arm-only projection and episodes required"
        )
    if destination.name.endswith((".partial", ".lock")):
        raise ValueError("reserved export suffix")
    dependencies = _dependencies()
    episodes = [projection.Episode(path, action_source) for path in paths]
    _compatible(episodes)
    partial = destination.with_name(destination.name + ".partial")
    lock = destination.with_name(destination.name + ".lock")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("x", encoding="utf-8"):
        pass
    started = time.monotonic()
    owns_partial = False
    try:
        if destination.exists() or partial.exists():
            raise FileExistsError("export output already exists")
        owns_partial = True
        _write(dependencies, partial, episodes)
        report = _verify(dependencies[0], partial, episodes)
        for episode in episodes:
            episode.unchanged()
        result = {
            "schema_version": 1,
            "format": "lerobot-v3.0",
            "lerobot_source": LEROBOT_SOURCE,
            "projection": "rgb_arm_only",
            "action_source": action_source,
            "omitted": ["depth", "gripper"],
            "raw_source_retained": True,
            "timestamp": "nominal_frame_index_divided_by_30",
            "source_timestamps": "exact_integer_source_and_receipt_clocks",
            "control_association": "latest_preceding_within_50ms",
            "interpolation": False,
            "rgb": {
                "codec": "h264",
                "crf": 18,
                "preset": "veryfast",
                "reencoded": True,
                "b_frames": 0,
            },
            "episodes": [episode.manifest() for episode in episodes],
            "verification": report,
            "elapsed_s": time.monotonic() - started,
            "dataset_bytes_excluding_export_manifest": sum(
                p.stat().st_size for p in partial.rglob("*") if p.is_file()
            ),
        }
        with (partial / "export.json").open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        filesystem.publish(partial, destination)
        return result
    except BaseException as error:
        if owns_partial and partial.is_dir():
            (partial / "failure.json").write_text(
                json.dumps({"error": str(error)}), encoding="utf-8"
            )
        raise

    finally:
        lock.unlink()


def _write(dependencies, partial, episodes):
    dataset_class, encoder_class = dependencies
    writer = dataset_class.create(
        "local/ur12e",
        fps=30,
        features=features(),
        root=partial,
        robot_type="ur12e_rgb_arm_only",
        video_backend="pyav",
        rgb_encoder=encoder_class(
            vcodec="h264",
            crf=18,
            preset="veryfast",
            g=30,
            extra_options={"bf": "0"},
        ),
        streaming_encoding=True,
        encoder_threads=1,
    )
    try:
        for episode in episodes:
            for frame in episode.frames():
                writer.add_frame(frame | {"task": episode.snapshot["task"]})
            writer.save_episode(parallel_encoding=False)
        writer.finalize()
    except BaseException:
        # Preserve the original failure; cleanup cannot publish the directory.
        with contextlib.suppress(Exception):
            writer.clear_episode_buffer()
            writer.finalize()
        raise


def _verify(dataset_class, root, episodes):
    dataset = dataset_class(
        "local/ur12e",
        root=root,
        download_videos=False,
        video_backend="pyav",
        return_uint8=True,
    )
    expected = sum(len(episode.groups) for episode in episodes)
    if len(dataset) != expected or dataset.num_episodes != len(episodes):
        raise ValueError("LeRobot loader frame/episode counts differ")
    info = json.loads((root / "meta/info.json").read_text(encoding="utf-8"))
    if info["codebase_version"] != "v3.0":
        raise ValueError("LeRobot output is not dataset v3.0")
    offset, maximum_rgb_error = 0, 0.0
    for episode in episodes:
        maximum_rgb_error = max(
            maximum_rgb_error, _verify_episode(dataset, offset, episode)
        )
        offset += len(episode.groups)
    if maximum_rgb_error > 4:
        raise ValueError(
            "second RGB encode exceeded four-level mean error gate"
        )
    return {
        "frames": expected,
        "episodes": len(episodes),
        "all_numeric_values_exact": True,
        "sampled_rgb_max_mae": maximum_rgb_error,
        "loader": "official_0.6.1_pyav",
        "hub_offline": True,
    }


def _verify_episode(dataset, offset, episode):
    maximum = 0.0
    samples = {0, len(episode.groups) // 2, len(episode.groups) - 1}
    for index, source in enumerate(episode.frames()):
        row = dataset.get_raw_item(offset + index)
        for key, value in episode.row(index).items():
            actual = (
                row[key].numpy()
                if hasattr(row[key], "numpy")
                else np.asarray(row[key])
            )
            if actual.size != value.size or not np.array_equal(
                actual.reshape(value.shape), value
            ):
                raise ValueError(f"LeRobot source values differ: {key}")
        if index in samples:
            maximum = max(maximum, _rgb_error(dataset[offset + index], source))
    return maximum


def _rgb_error(decoded, source):
    maximum = 0.0
    for role in contracts.CAMERA_ROLES:
        key = "observation.images." + role
        image = decoded[key].numpy().transpose(1, 2, 0)
        if image.dtype != np.uint8 or image.shape != (480, 640, 3):
            raise ValueError("LeRobot RGB shape/dtype differs")
        maximum = max(
            maximum, float(np.abs(image.astype(float) - source[key]).mean())
        )
    return maximum
