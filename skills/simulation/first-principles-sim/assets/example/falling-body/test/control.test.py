"""control: no height, no fall."""

import sys

sys.path.insert(0, "src")

from model import fall_time, impact_speed

assert fall_time(0.0) == 0.0
assert impact_speed(0.0) == 0.0
