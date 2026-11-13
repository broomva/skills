"""Checks for the falling body. Run from the package directory; exits non-zero on failure."""

import sys

sys.path.insert(0, "src")

from model import G, fall_time, impact_speed

# reference: the stored table.
with open("test/reference/drop.txt", encoding="utf-8") as table:
    rows = [line.split() for line in table if line.strip() and not line.startswith("#")]
assert len(rows) >= 2
for height, seconds in rows:
    assert abs(fall_time(float(height)) - float(seconds)) < 1e-3, height

# independent: step the motion forward and time the landing, without the closed form.
dt = 1e-5
fallen, speed, elapsed = 0.0, 0.0, 0.0
while fallen < 5.0:
    speed += G * dt
    fallen += speed * dt
    elapsed += dt
assert abs(elapsed - fall_time(5.0)) < 1e-3 * fall_time(5.0)

# conservation: kinetic energy at the ground equals the potential energy lost, per kilogram.
for height in (1.0, 5.0, 20.0):
    assert abs(impact_speed(height) ** 2 / 2 - G * height) < 1e-9 * G * height

# control: no height, no fall.
assert fall_time(0.0) == 0.0
assert impact_speed(0.0) == 0.0
