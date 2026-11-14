"""A body falling from rest in vacuum. SI units."""

# Standard acceleration of gravity, m/s^2 (CODATA; exact by definition).
G = 9.80665


def fall_time(height):
    """Seconds to fall `height` metres from rest."""
    return (2 * height / G) ** 0.5


def impact_speed(height):
    """Speed on reaching the ground, m/s."""
    return G * fall_time(height)
