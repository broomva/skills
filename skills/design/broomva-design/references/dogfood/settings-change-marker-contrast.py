"""WCAG 2.x contrast for the settings change marker specimen (BRO-2537).

OKLCH values are the foundation tokens (DESIGN.md §2, broomva-foundation.css light and
[data-theme="dark"] blocks), converted to linear sRGB (clipped); translucent fills would be
composited in gamma-encoded sRGB, as browsers do. Text pairs need 4.5:1, non-text 3:1.
Run: python3 settings-change-marker-contrast.py
"""
import math

def oklch(L, C, h):
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    l_, m_, s_ = L + 0.3963377774 * a + 0.2158037573 * b, L - 0.1055613458 * a - 0.0638541728 * b, L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
           -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    return [min(1, max(0, x)) for x in rgb]

def ratio(fg, bg):
    lum = lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted([lum(fg), lum(bg)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)

light = dict(card=oklch(1, 0, 0), foreground=oklch(0.175, 0.022, 265), muted=oklch(0.50, 0.015, 265),
             placeholder=oklch(0.68, 0.010, 265), blue=oklch(0.60, 0.12, 260))
dark = dict(card=oklch(0.175, 0.025, 272), foreground=oklch(0.965, 0.004, 265), muted=oklch(0.62, 0.020, 270),
            blue=oklch(0.60, 0.12, 260))

PAIRS = [  # (label, fg, bg, kind) kind: text needs 4.5, non-text needs 3.0
    ("light value: foreground on card", light["foreground"], light["card"], "text"),
    ("light default label: muted-foreground on card", light["muted"], light["card"], "text"),
    ("light marker line: blue vs card", light["blue"], light["card"], "non-text"),
    ("light faded value: placeholder mist on card", light["placeholder"], light["card"], "text"),
    ("light blue value text on card", light["blue"], light["card"], "text"),
    ("dark value: foreground on card", dark["foreground"], dark["card"], "text"),
    ("dark default label: muted-foreground on card", dark["muted"], dark["card"], "text"),
    ("dark marker line: blue vs card", dark["blue"], dark["card"], "non-text"),
    ("dark blue value text on card", dark["blue"], dark["card"], "text"),
]
for label, fg, bg, kind in PAIRS:
    need = 4.5 if kind == "text" else 3.0
    r = ratio(fg, bg)
    print(f"{r:5.2f}:1  {'PASS' if r >= need else 'FAIL'} (needs {need}:1, {kind})  {label}")
