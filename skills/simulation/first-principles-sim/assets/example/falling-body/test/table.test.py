"""reference: fall times against the stored table. Run from the package directory."""

import sys

sys.path.insert(0, "src")

from model import fall_time

with open("test/reference/drop.txt", encoding="utf-8") as table:
    rows = [line.split() for line in table if line.strip() and not line.startswith("#")]
assert len(rows) >= 2
for height, seconds in rows:
    assert abs(fall_time(float(height)) - float(seconds)) < 1e-3, height
