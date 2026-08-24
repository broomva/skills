#!/Users/broomva/miniconda3/bin/python3
"""Deterministic raster renderer for the Parallax logo.

Uses only Python's standard library, NumPy, and Pillow. Geometry is drawn at 3x
resolution and reduced with Lanczos filtering for stable antialiasing.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


DEFAULT_SIZE = 1000
SUPERSAMPLE = 3
PREVIEW_SIZES = (256, 96, 48, 32)
VARIANT_SEEDS = (3, 11, 19, 27, 41, 58, 73, 91)
ORIGIN = np.array([250.0, 500.0])
OBSERVED_START_X = 60.0
TIP_X = 940.0


def oklch_to_srgb(lightness: float, chroma: float, hue_degrees: float) -> tuple[int, int, int]:
    """Convert an OKLCH triplet to clipped 8-bit sRGB via OKLab and linear RGB."""
    hue = math.radians(hue_degrees)
    a = chroma * math.cos(hue)
    b = chroma * math.sin(hue)

    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b

    l = l_ * l_ * l_
    m = m_ * m_ * m_
    s = s_ * s_ * s_

    linear = np.array(
        [
            4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
        ],
        dtype=np.float64,
    )
    linear = np.clip(linear, 0.0, 1.0)
    srgb = np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    )
    return tuple(int(round(value * 255.0)) for value in srgb)


GROUND = oklch_to_srgb(0.135, 0.02, 272)
OBSERVED = oklch_to_srgb(0.97, 0.004, 265)
SIMULATED = oklch_to_srgb(0.68, 0.13, 260)
SIMULATED_HI = oklch_to_srgb(0.74, 0.12, 260)
SIMULATED_DIM = oklch_to_srgb(0.48, 0.14, 260)


def cubic_points(
    p0: Sequence[float],
    p1: Sequence[float],
    p2: Sequence[float],
    p3: Sequence[float],
    count: int = 180,
) -> np.ndarray:
    t = np.linspace(0.0, 1.0, count, dtype=np.float64)[:, None]
    omt = 1.0 - t
    return omt**3 * p0 + 3.0 * omt**2 * t * p1 + 3.0 * omt * t**2 * p2 + t**3 * p3


def composite_curve(segments: Iterable[Sequence[Sequence[float]]], count: int = 130) -> np.ndarray:
    parts = []
    for index, segment in enumerate(segments):
        points = cubic_points(*[np.asarray(point, dtype=np.float64) for point in segment], count=count)
        parts.append(points if index == 0 else points[1:])
    return np.concatenate(parts, axis=0)


def draw_tapered_curve(
    image: Image.Image,
    points: np.ndarray,
    color: tuple[int, int, int],
    alpha: int,
    width_start: float,
    width_end: float,
    scale: float,
    dashed: bool = False,
) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    pts = points * scale
    total = len(pts) - 1
    for i in range(total):
        if dashed:
            # Long, quiet dashes echo the product's simulated trajectories.
            phase = i % 22
            if phase >= 12:
                continue
        progress = i / max(1, total - 1)
        width = width_start + (width_end - width_start) * progress
        local_alpha = int(alpha * (1.0 - 0.12 * progress))
        a = tuple(float(v) for v in pts[i])
        b = tuple(float(v) for v in pts[i + 1])
        draw.line((a, b), fill=(*color, local_alpha), width=max(1, int(round(width * scale))))


def draw_node(
    image: Image.Image,
    center: Sequence[float],
    radius: float,
    color: tuple[int, int, int],
    alpha: int,
    scale: float,
    ring: bool = False,
) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    x, y = float(center[0]) * scale, float(center[1]) * scale
    r = radius * scale
    draw.ellipse((x - r, y - r, x + r, y + r), fill=(*color, alpha))
    if ring:
        rr = (radius + 7.5) * scale
        draw.ellipse(
            (x - rr, y - rr, x + rr, y + rr),
            outline=(*color, min(220, alpha)),
            width=max(1, round(1.7 * scale)),
        )


def screen_layers(base: Image.Image, glow: Image.Image) -> Image.Image:
    a = np.asarray(base, dtype=np.float32) / 255.0
    glow_array = np.asarray(glow.convert("RGBA"), dtype=np.float32) / 255.0
    b = glow_array[:, :, :3] * glow_array[:, :, 3:4]
    screened = 1.0 - (1.0 - a) * (1.0 - b)
    return Image.fromarray(np.uint8(np.clip(screened * 255.0 + 0.5, 0, 255)), "RGB")


def make_ground(size: int) -> Image.Image:
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    nx = (xx - size * 0.51) / (size * 0.72)
    ny = (yy - size * 0.50) / (size * 0.72)
    radial = np.clip(np.sqrt(nx * nx + ny * ny), 0.0, 1.0)
    # A restrained vignette: enough to close the corners without reading as a halo.
    factor = 1.0 - 0.17 * np.power(radial, 1.7)
    base = np.asarray(GROUND, dtype=np.float32)[None, None, :]
    array = np.clip(base * factor[:, :, None], 0, 255).astype(np.uint8)
    return Image.fromarray(array, "RGB")


def make_plume(size: int, scale: float) -> Image.Image:
    """Build the low-frequency directional silhouette that survives tiny sizes."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    points = np.asarray(
        [
            ORIGIN,
            [395.0, 385.0],
            [650.0, 222.0],
            [TIP_X, 106.0],
            [TIP_X, 894.0],
            [650.0, 778.0],
            [395.0, 615.0],
        ],
        dtype=np.float64,
    )
    draw.polygon([tuple(point * scale) for point in points], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(1.0, 38.0 * scale)))

    x = np.arange(size, dtype=np.float32)[None, :]
    progress = np.clip((x - ORIGIN[0] * scale) / ((TIP_X - ORIGIN[0]) * scale), 0.0, 1.0)
    # 9.8% at NOW, continuously fading to zero at the tips.
    horizontal_alpha = 25.0 * np.power(1.0 - progress, 0.92)
    alpha = np.asarray(mask, dtype=np.float32) * (horizontal_alpha / 255.0)
    rgba = np.empty((size, size, 4), dtype=np.uint8)
    rgba[:, :, :3] = np.asarray(SIMULATED, dtype=np.uint8)
    rgba[:, :, 3] = np.uint8(np.clip(alpha + 0.5, 0, 255))
    return Image.fromarray(rgba, "RGBA")


def build_geometry(seed: int) -> tuple[list[dict], list[dict]]:
    rng = np.random.default_rng(seed)
    origin = ORIGIN.copy()
    # Deliberately uneven terminal spacing keeps the shape organic and recognizable.
    target_y = np.array([116, 184, 260, 338, 416, 492, 575, 655, 735, 815, 884], dtype=float)
    target_y += rng.normal(0.0, 8.0, len(target_y))
    target_y = np.clip(target_y, 108.0, 892.0)
    target_x = rng.uniform(922.0, 949.0, len(target_y))

    # Two swaps create crossings without turning the fan into visual noise.
    target_y[[2, 3]] = target_y[[3, 2]]
    target_y[[7, 8]] = target_y[[8, 7]]

    paths: list[dict] = []
    dashed_indices = {1, 7, 10}
    highlighted_index = 4
    for i, (end_x, end_y) in enumerate(zip(target_x, target_y)):
        delta = end_y - origin[1]
        waist_x = rng.uniform(525.0, 670.0)
        waist_y = origin[1] + delta * rng.uniform(0.34, 0.57) + rng.normal(0.0, 21.0)
        waist = np.array([waist_x, waist_y])
        p1 = origin + np.array([rng.uniform(88.0, 145.0), delta * rng.uniform(0.04, 0.17)])
        p2 = waist + np.array([-rng.uniform(70.0, 125.0), -delta * rng.uniform(0.03, 0.12)])
        p3 = waist
        p4 = waist + np.array([rng.uniform(58.0, 112.0), delta * rng.uniform(0.03, 0.13)])
        end = np.array([end_x, end_y])
        p5 = end - np.array([rng.uniform(130.0, 195.0), delta * rng.uniform(0.04, 0.14)])
        points = composite_curve(((origin, p1, p2, p3), (p3, p4, p5, end)))

        distance = abs(end_y - 500.0) / 395.0
        opacity = int(np.clip(205 - 88 * distance + rng.normal(0, 13), 72, 218))
        color = SIMULATED if i % 3 else SIMULATED_DIM
        width = float(np.clip(6.3 - 1.2 * distance + rng.normal(0, 0.25), 4.5, 6.8))
        if i == highlighted_index:
            opacity, color, width = 246, SIMULATED_HI, 8.0
        paths.append(
            {
                "points": points,
                "color": color,
                "alpha": opacity,
                "width": width,
                "dashed": i in dashed_indices,
                "highlight": i == highlighted_index,
                "ring": i in {0, 4, 8},
            }
        )

    forks: list[dict] = []
    for path_index, direction in ((3, -1.0), (7, 1.0)):
        parent = paths[path_index]["points"]
        fork_at = int(len(parent) * rng.uniform(0.52, 0.61))
        start = parent[fork_at]
        endpoint = np.array(
            [rng.uniform(925.0, 948.0), np.clip(start[1] + direction * rng.uniform(125.0, 185.0), 108.0, 892.0)]
        )
        delta = endpoint[1] - start[1]
        control1 = start + np.array([rng.uniform(65.0, 95.0), delta * 0.17])
        control2 = endpoint - np.array([rng.uniform(115.0, 160.0), delta * 0.16])
        forks.append(
            {
                "points": cubic_points(start, control1, control2, endpoint, count=170),
                "color": SIMULATED_DIM,
                "alpha": 95 if direction < 0 else 82,
                "width": 4.5,
                "dashed": False,
                "highlight": False,
                "ring": direction < 0,
            }
        )
    return paths, forks


def render_logo(seed: int, size: int) -> Image.Image:
    if size < 16:
        raise ValueError("--size must be at least 16 pixels")
    internal = size * SUPERSAMPLE
    scale = internal / 1000.0
    base = make_ground(internal)
    plume = make_plume(internal, scale)
    base = Image.alpha_composite(base.convert("RGBA"), plume).convert("RGB")
    strokes = Image.new("RGBA", (internal, internal), (0, 0, 0, 0))
    accent = Image.new("RGBA", (internal, internal), (0, 0, 0, 0))
    origin = ORIGIN.copy()

    paths, forks = build_geometry(seed)
    for path in [*paths, *forks]:
        draw_tapered_curve(
            strokes,
            path["points"],
            path["color"],
            path["alpha"],
            path["width"],
            max(2.2, path["width"] * 0.48),
            scale,
            path["dashed"],
        )
        end = path["points"][-1]
        radius = 7.5 if path["highlight"] else 5.7
        draw_node(strokes, end, radius, path["color"], path["alpha"], scale, path["ring"])
        draw_tapered_curve(
            accent,
            path["points"],
            path["color"],
            225 if path["highlight"] else max(18, int(path["alpha"] * 0.24)),
            path["width"] * (1.08 if path["highlight"] else 0.88),
            3.8 if path["highlight"] else 2.0,
            scale,
            path["dashed"],
        )
        if path["highlight"]:
            draw_node(accent, end, radius, path["color"], 230, scale, True)

    # The one recorded past: calm, solid, and very slightly tapered toward NOW.
    observed_points = np.column_stack(
        (np.linspace(OBSERVED_START_X, origin[0], 150), np.full(150, origin[1]))
    )
    draw_tapered_curve(strokes, observed_points, OBSERVED, 238, 9.5, 12.5, scale)

    draw = ImageDraw.Draw(strokes, "RGBA")
    ox, oy = origin * scale
    ring_r = 35.0 * scale
    draw.ellipse(
        (ox - ring_r, oy - ring_r, ox + ring_r, oy + ring_r),
        outline=(*OBSERVED, 205),
        width=max(1, round(2.0 * scale)),
    )
    draw_node(strokes, origin, 26.0, OBSERVED, 255, scale)
    draw_node(accent, origin, 27.0, OBSERVED, 220, scale)

    composed = Image.alpha_composite(base.convert("RGBA"), strokes).convert("RGB")

    # A stronger two-radius bloom unifies the fan into a scale-independent glow mass.
    glow_small = accent.filter(ImageFilter.GaussianBlur(max(1.0, 14.0 * scale)))
    glow_large = accent.filter(ImageFilter.GaussianBlur(max(1.0, 46.0 * scale)))
    glow_small.putalpha(glow_small.getchannel("A").point(lambda a: round(a * 0.52)))
    glow_large.putalpha(glow_large.getchannel("A").point(lambda a: round(a * 0.24)))
    glow = Image.alpha_composite(glow_large, glow_small)
    composed = screen_layers(composed, glow)

    if internal != size:
        composed = composed.resize((size, size), Image.Resampling.LANCZOS)

    # Fine luminance-only grain. The amplitude is 1.6% of the available range.
    rng = np.random.default_rng(seed ^ 0x50415241)
    array = np.asarray(composed, dtype=np.int16)
    grain = rng.normal(0.0, 1.45, (size, size, 1))
    sparse = rng.choice(np.array([-2.0, 0.0, 2.0]), size=(size, size, 1), p=(0.055, 0.89, 0.055))
    array = np.clip(array + grain + sparse, 0, 255).astype(np.uint8)
    return Image.fromarray(array, "RGB")


# project-logo.png is held under 500 KB as a self-imposed budget: nothing enforces
# it now, but a mark that needs three quarters of a megabyte is a mark something
# else will resize later. A 1000x1000 render with gradients, bloom and per-pixel
# grain lands near 670 KB as truecolour PNG, because grain is precisely the thing
# PNG cannot compress. An adaptive 256-colour palette takes it to ~170 KB and is
# visually indistinguishable at every size that matters.
#
# NOT dithered on purpose: Floyd-Steinberg reaches ~90 KB but spends palette entries
# on dither pattern instead of on the plume's gradient, which crushes the ground to
# black and leaves green/magenta blotches through the fan. Measured, then rejected.
#
# MAXCOVERAGE, not FASTOCTREE, though octree is smaller (126 KB vs 229 KB). Octree
# visibly flattens the plume, and the plume is the whole reason this mark survives a
# 31x downsample -- see the selftest below. Both fit the cap with room, so the choice
# is made on the thing the cap does not measure. MEDIANCUT is useless here: 521 KB,
# over the cap on its own.
MAX_LOGO_BYTES = 500_000


def save_logo(image: Image.Image, path: Path) -> int:
    """Write the logo under the size budget and return the byte count."""
    image.convert("RGB").quantize(colors=256, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE).save(
        path, optimize=True
    )
    return path.stat().st_size


def save_previews(image: Image.Image, root: Path) -> list[Path]:
    preview_dir = root / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for side in PREVIEW_SIZES:
        path = preview_dir / f"logo-{side}.png"
        image.resize((side, side), Image.Resampling.LANCZOS).save(path, optimize=True)
        outputs.append(path)
    return outputs


def tile_on_field(canvas: Image.Image, image: Image.Image, left: int, top: int, field_side: int) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((left, top, left + field_side - 1, top + field_side - 1), fill=(76, 77, 82))
    x = left + (field_side - image.width) // 2
    y = top + (field_side - image.height) // 2
    canvas.paste(image, (x, y))


def make_contact_sheet(image: Image.Image, root: Path) -> Path:
    margin, gap = 28, 16
    large_field = 1000
    small_field = 256
    width = 2 * margin + large_field
    height = 3 * margin + large_field + small_field
    canvas = Image.new("RGB", (width, height), (49, 50, 54))
    large = image.resize((1000, 1000), Image.Resampling.LANCZOS)
    tile_on_field(canvas, large, margin, margin, large_field)
    row_width = 4 * small_field + 3 * gap
    row_left = (width - row_width) // 2
    row_top = 2 * margin + large_field
    for index, side in enumerate(PREVIEW_SIZES):
        preview = image.resize((side, side), Image.Resampling.LANCZOS)
        tile_on_field(canvas, preview, row_left + index * (small_field + gap), row_top, small_field)
    path = root / "sheet.png"
    canvas.save(path, optimize=True)
    return path


def make_variants(root: Path, size: int) -> tuple[list[Path], Path]:
    variant_dir = root / "variants"
    variant_dir.mkdir(parents=True, exist_ok=True)
    variants = []
    for seed in VARIANT_SEEDS:
        path = variant_dir / f"seed-{seed}.png"
        render_logo(seed, size).save(path, optimize=True)
        variants.append(path)

    margin, gap = 24, 8
    top_side, bottom_field, bottom_image = 260, 260, 48
    width = 2 * margin + 8 * top_side + 7 * gap
    height = 3 * margin + top_side + bottom_field
    canvas = Image.new("RGB", (width, height), (49, 50, 54))
    for index, path in enumerate(variants):
        image = Image.open(path).convert("RGB")
        x = margin + index * (top_side + gap)
        tile_on_field(canvas, image.resize((top_side, top_side), Image.Resampling.LANCZOS), x, margin, top_side)
        tiny = image.resize((bottom_image, bottom_image), Image.Resampling.LANCZOS)
        tile_on_field(canvas, tiny, x, 2 * margin + top_side, bottom_field)
    path = root / "variants-sheet.png"
    canvas.save(path, optimize=True)
    return variants, path


def luminance(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    return 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]


def longest_true_run(values: np.ndarray) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if bool(value) else 0
        best = max(best, current)
    return best


def selftest(seed: int) -> dict[str, float]:
    """Measure the three required 32px readability invariants."""
    tiny = render_logo(seed, 1000).resize((32, 32), Image.Resampling.LANCZOS)
    light = luminance(tiny)
    node_x = int(round(ORIGIN[0] * 32.0 / 1000.0))
    node_y = int(round(ORIGIN[1] * 32.0 / 1000.0))

    brightest_y, brightest_x = np.unravel_index(int(np.argmax(light)), light.shape)
    brightest_distance = math.hypot(brightest_x - node_x, brightest_y - node_y)

    keep_rows = np.ones(32, dtype=bool)
    keep_rows[max(0, node_y - 2) : min(32, node_y + 3)] = False
    left_mean = float(light[keep_rows, :16].mean())
    right_mean = float(light[keep_rows, 16:].mean())
    directional_delta = right_mean - left_mean

    bar_values = light[node_y, :node_x]
    background_rows = light[[max(0, node_y - 5), min(31, node_y + 5)], :node_x]
    local_background = background_rows.mean(axis=0)
    bar_margin = bar_values - local_background
    margin_threshold = 18.0
    bar_run = longest_true_run(bar_margin > margin_threshold)
    qualifying_margin = float(bar_margin[bar_margin > margin_threshold].min()) if bar_run else 0.0

    print(
        "SELFTEST brightest-origin-distance: "
        f"{brightest_distance:.3f}px (brightest=({brightest_x},{brightest_y}), "
        f"origin=({node_x},{node_y}), limit=4.000px)"
    )
    print(
        "SELFTEST directional-mass: "
        f"right={right_mean:.3f}, left={left_mean:.3f}, delta={directional_delta:.3f} luminance"
    )
    print(
        "SELFTEST observed-bar-run: "
        f"{bar_run}px (required=3px, threshold={margin_threshold:.1f}, "
        f"minimum-qualifying-margin={qualifying_margin:.3f})"
    )

    assert brightest_distance <= 4.0, "brightest pixel is too far from NOW"
    assert directional_delta > 0.0, "right-hand plume does not register as directional mass"
    assert bar_run >= 3, "observed bar does not survive as a three-pixel run"
    print("SELFTEST PASS")
    return {
        "brightest_distance": brightest_distance,
        "left_mean": left_mean,
        "right_mean": right_mean,
        "directional_delta": directional_delta,
        "bar_run": float(bar_run),
        "bar_margin": qualifying_margin,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the deterministic Parallax raster logo.")
    parser.add_argument("--seed", type=int, default=41, help="deterministic geometry/noise seed")
    parser.add_argument("--out", type=Path, default=Path("logo.png"), help="main PNG output path")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE, help="main square size in pixels")
    parser.add_argument("--selftest", action="store_true", help="measure the required 32px readability invariants")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.selftest:
        selftest(args.seed)
        return
    args.out.parent.mkdir(parents=True, exist_ok=True)
    image = render_logo(args.seed, args.size)
    written = save_logo(image, Path(args.out))
    print(f"wrote {args.out}  {written} bytes  ({written / 1024:.1f} KB)")
    if written > MAX_LOGO_BYTES:
        raise SystemExit(
            f"FAIL: {written} bytes exceeds the {MAX_LOGO_BYTES}-byte budget"
        )

    root = args.out.parent
    save_previews(image, root)
    make_contact_sheet(image, root)
    make_variants(root, args.size)


if __name__ == "__main__":
    main()
