#!/usr/bin/env python3
"""Source convenience entry; the image installs the same ur12e command."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
# Imports follow the explicit source-checkout bootstrap.
# pylint: disable-next=wrong-import-position
from ur12e_collection.operator import main

if __name__ == "__main__":
    raise SystemExit(main())
