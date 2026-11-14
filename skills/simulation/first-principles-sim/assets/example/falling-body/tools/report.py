"""Prints every number the README quotes."""

import sys

sys.path.insert(0, "src")

from model import fall_time, impact_speed

print(f"fall time from 5 m:     {fall_time(5.0):.3f} s")
print(f"impact speed from 5 m:  {impact_speed(5.0):.2f} m/s")
