"""Launch the mainline follower using the configured Isaac Python runtime."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from ur12e_collection.cli import main  # pylint: disable=wrong-import-position

if __name__ == "__main__":
    raise SystemExit(main(["follower", *sys.argv[1:]]))
