"""A two-colour aura derived from measured behaviour.

Spotify's 2021 Audio Aura mapped mood features onto colour; its engineering
write-up describes the move as going "mystical to mathematical".  The same
applies here, with every channel bound to something that was actually counted:

* **primary hue** — where the work sat on the build/explore/delegate triangle
* **secondary hue** — the circular mean of the hour-of-day histogram
* **saturation**    — token intensity, log-scaled
* **lightness**     — typical session length

The mapping is published rather than tuned by eye, so two different corpora
that behave alike produce colours that look alike.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

#: Hue anchors on the colour wheel for each behavioural pole.
HUE_BUILD = 18.0     # ember
HUE_EXPLORE = 200.0  # deep cyan
HUE_DELEGATE = 285.0 # violet

AURA_NAMES = (
    (0, 40, "Ember"), (40, 75, "Amber"), (75, 150, "Verdant"), (150, 195, "Aqua"),
    (195, 240, "Cobalt"), (240, 290, "Indigo"), (290, 330, "Orchid"), (330, 361, "Rose"),
)


def _hue_name(hue: float) -> str:
    hue %= 360
    for lo, hi, name in AURA_NAMES:
        if lo <= hue < hi:
            return name
    return "Ember"


def _circular_mean_hour(by_hour: list[int]) -> float | None:
    """Mean hour on a 24-hour circle, so 23:00 and 01:00 average to midnight."""
    total = sum(by_hour)
    if total == 0:
        return None
    x = sum(n * math.cos(2 * math.pi * h / 24) for h, n in enumerate(by_hour))
    y = sum(n * math.sin(2 * math.pi * h / 24) for h, n in enumerate(by_hour))
    if x == 0 and y == 0:
        return None
    angle = math.atan2(y, x)
    # Round before the final wrap so a mean of exactly midnight reports 0.0
    # rather than a floating-point 23.999… that prints as 24.0.
    return round((angle * 24 / (2 * math.pi)) % 24, 6) % 24


def _hsl_to_hex(h: float, s: float, lightness: float) -> str:
    h = (h % 360) / 360.0
    s = max(0.0, min(1.0, s))
    lightness = max(0.0, min(1.0, lightness))
    if s == 0:
        value = round(lightness * 255)
        return f"#{value:02x}{value:02x}{value:02x}"
    q = lightness * (1 + s) if lightness < 0.5 else lightness + s - lightness * s
    p = 2 * lightness - q

    def channel(t: float) -> int:
        t %= 1.0
        if t < 1 / 6:
            v = p + (q - p) * 6 * t
        elif t < 1 / 2:
            v = q
        elif t < 2 / 3:
            v = p + (q - p) * (2 / 3 - t) * 6
        else:
            v = p
        return round(v * 255)

    return f"#{channel(h + 1/3):02x}{channel(h):02x}{channel(h - 1/3):02x}"


@dataclass(slots=True)
class Aura:
    primary: str
    secondary: str
    name: str
    inputs: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "secondary": self.secondary,
            "name": self.name,
            "inputs": self.inputs,
        }


def compute(
    build: int, explore: int, delegate: int, by_hour: list[int],
    total_tokens: int, median_session_minutes: float | None,
) -> Aura | None:
    """Derive the aura, or ``None`` when there is nothing to derive it from."""
    weight = build + explore + delegate
    if weight == 0 or sum(by_hour) == 0:
        return None

    # Angular blend across the three poles, weighted by how the work split.
    x = (build * math.cos(math.radians(HUE_BUILD))
         + explore * math.cos(math.radians(HUE_EXPLORE))
         + delegate * math.cos(math.radians(HUE_DELEGATE)))
    y = (build * math.sin(math.radians(HUE_BUILD))
         + explore * math.sin(math.radians(HUE_EXPLORE))
         + delegate * math.sin(math.radians(HUE_DELEGATE)))
    primary_hue = math.degrees(math.atan2(y, x)) % 360

    mean_hour = _circular_mean_hour(by_hour)
    secondary_hue = (mean_hour / 24 * 360) if mean_hour is not None else (primary_hue + 150) % 360

    # Log-scaled so a 10x corpus does not saturate the channel outright.
    saturation = 0.45 + 0.5 * min(1.0, math.log10(max(total_tokens, 1)) / 10.0)
    minutes = median_session_minutes if median_session_minutes is not None else 15.0
    lightness = 0.62 - 0.18 * min(1.0, minutes / 60.0)

    primary = _hsl_to_hex(primary_hue, saturation, lightness)
    secondary = _hsl_to_hex(secondary_hue, saturation * 0.85, min(0.78, lightness + 0.18))
    return Aura(
        primary=primary,
        secondary=secondary,
        name=f"{_hue_name(primary_hue)} {_hue_name(secondary_hue)}",
        inputs={
            "primary_hue": round(primary_hue, 1),
            "secondary_hue": round(secondary_hue, 1),
            "mean_hour": round(mean_hour, 2) if mean_hour is not None else None,
            "build": build, "explore": explore, "delegate": delegate,
            "saturation": round(saturation, 3), "lightness": round(lightness, 3),
        },
    )
