"""conservation: kinetic energy at the ground equals the potential energy lost, per kilogram."""

import sys

sys.path.insert(0, "src")

from model import G, impact_speed

for height in (1.0, 5.0, 20.0):
    assert abs(impact_speed(height) ** 2 / 2 - G * height) < 1e-9 * G * height
