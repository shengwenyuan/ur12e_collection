"""URSim test configuration; these are not physical station motion limits."""

import math

from ur12e_collection import ur
from ur12e_collection.control.model import COMMAND_HZ, Limits

HOME = (0.0, -math.pi / 2, -math.pi / 2, -math.pi / 2, math.pi / 2, 0.0)
LIMITS = Limits(
    lower=(-5.5, -3.1, -3.1, -5.5, -3.1, -5.5),
    upper=(5.5, 0.1, 0.1, 5.5, 3.1, 5.5),
    ready=HOME,
)
PERIOD = 1 / COMMAND_HZ
FEEDBACK_HZ = ur.RECEIVE_HZ
IMAGE = (
    "universalrobots/ursim_e-series@sha256:"
    "39909bad9a8247980a1c9144da322ff7c4d34db0e89870f4c6b4dabd7c55c95d"
)
SERIAL = "20245199999"
VERSION = "URSoftware 5.22.2.1214876"
HOST = "ursim-control"
