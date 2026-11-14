"""independent: step the motion forward and time the landing, without the closed form."""

import sys

sys.path.insert(0, "src")

from model import G, fall_time

dt = 1e-5
fallen, speed, elapsed = 0.0, 0.0, 0.0
while fallen < 5.0:
    speed += G * dt
    fallen += speed * dt
    elapsed += dt
assert abs(elapsed - fall_time(5.0)) < 1e-3 * fall_time(5.0)
