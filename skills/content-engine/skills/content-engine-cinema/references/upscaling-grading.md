# Upscaling and Color Grading

Post-production pipeline for taking raw AI-generated output to delivery-ready quality. Covers resolution enhancement, color science, and output organization.

## Output Organization

All content flows through a four-stage directory structure. Never skip stages -- the raw output is always preserved.

```
assets/
  raw/              # Direct output from AI models (never modify, never delete)
  upscaled/         # After resolution enhancement
  graded/           # After color correction and LUT application
  final/            # Delivery-ready files (format-converted, metadata-tagged)
```

### Naming Convention

```
{project}-{scene}-{variant}-{stage}.{ext}

Examples:
  maya-workspace-morning-raw.png
  maya-workspace-morning-upscaled.png
  maya-workspace-morning-graded.png
  maya-workspace-morning-final.jpg
```

For video:
```
  maya-workspace-morning-raw.mp4
  maya-workspace-morning-upscaled.mp4
  maya-workspace-morning-graded.mp4
  maya-workspace-morning-final-1080p.mp4
  maya-workspace-morning-final-4k.mp4
```

## Upscaling

### Tier 1: Topaz Gigapixel AI (CLI)

Topaz produces the best results for AI-generated content. It handles the artifact patterns specific to diffusion model output (soft edges, texture repetition, fine detail loss) better than general-purpose upscalers.

**Installation:** Download from [topazlabs.com](https://topazlabs.com/gigapixel). The CLI is included with the desktop app.

**macOS CLI location:**
```bash
# Topaz Gigapixel AI CLI (after installing the app)
TOPAZ="/Applications/Topaz Gigapixel AI.app/Contents/Resources/tpai"
```

**Basic upscale (2x):**
```bash
"$TOPAZ" \
  --input assets/raw/scene-001.png \
  --output assets/upscaled/scene-001.png \
  --scale 2 \
  --model standard-v2 \
  --format png
```

**4x upscale with face recovery:**
```bash
"$TOPAZ" \
  --input assets/raw/portrait-001.png \
  --output assets/upscaled/portrait-001.png \
  --scale 4 \
  --model high-fidelity \
  --face-recovery on \
  --format png
```

**Batch upscale directory:**
```bash
for f in assets/raw/*.png; do
  name=$(basename "$f" .png)
  "$TOPAZ" \
    --input "$f" \
    --output "assets/upscaled/${name}.png" \
    --scale 2 \
    --model standard-v2 \
    --format png
done
```

**Model selection:**
| Model | Best For |
|-------|----------|
| `standard-v2` | General purpose, balanced quality/speed |
| `high-fidelity` | Maximum detail preservation, portraits |
| `art-and-cg` | AI-generated art, illustrations, 3D renders |
| `low-resolution` | Very small inputs (256px or less) |
| `compressed` | JPEG artifacts, heavily compressed inputs |

**Tips:**
- Always upscale from the raw output, not from a compressed version
- 2x is usually sufficient for web delivery (1024 → 2048)
- 4x for print or 4K video frames
- 6x rarely needed and increases processing time significantly
- Enable face recovery for any image containing faces, even if they are small in frame

### Tier 2: Real-ESRGAN (Open Source)

Free, GPU-accelerated, runs locally. Quality is ~85-90% of Topaz for most content types.

**Installation:**
```bash
# Via pip
pip install realesrgan

# Or build from source for latest models
git clone https://github.com/xinntao/Real-ESRGAN.git
cd Real-ESRGAN
pip install -r requirements.txt
python setup.py develop
```

**Basic usage:**
```bash
# 4x upscale (default model: RealESRGAN_x4plus)
python -m realesrgan -i assets/raw/scene-001.png -o assets/upscaled/scene-001.png -s 4

# 2x upscale
python -m realesrgan -i assets/raw/scene-001.png -o assets/upscaled/scene-001.png -s 2

# Anime/illustration model (better for non-photorealistic content)
python -m realesrgan -i assets/raw/scene-001.png -o assets/upscaled/scene-001.png -s 4 -n RealESRGAN_x4plus_anime_6B

# Face enhancement (GFPGAN integrated)
python -m realesrgan -i assets/raw/portrait-001.png -o assets/upscaled/portrait-001.png -s 4 --face_enhance
```

**Batch upscale:**
```bash
python -m realesrgan -i assets/raw/ -o assets/upscaled/ -s 2 --suffix ""
```

**Model selection:**
| Model | Best For |
|-------|----------|
| `RealESRGAN_x4plus` | Photorealistic content (default) |
| `RealESRGAN_x4plus_anime_6B` | Anime, illustration, flat art styles |
| `RealESRNet_x4plus` | Faster, slightly less detail |
| `realesr-general-x4v3` | General purpose, good balance |

### Tier 3: Lanczos via ffmpeg/ImageMagick (No GPU)

Algorithmic upscaling -- no AI, no detail hallucination. Use for quick previews or when GPU is unavailable.

```bash
# ffmpeg (video frames)
ffmpeg -i assets/raw/scene-001.png -vf "scale=4096:2304:flags=lanczos" assets/upscaled/scene-001.png

# ImageMagick (images)
magick assets/raw/scene-001.png -filter Lanczos -resize 200% assets/upscaled/scene-001.png
```

Lanczos preserves sharpness but cannot add detail that is not in the source. It is the baseline -- anything AI-based should look noticeably better.

### Video Upscaling

For video files, process frame-by-frame or use video-aware upscalers:

**Topaz Video AI:**
```bash
# Topaz Video AI CLI
tvai \
  --input assets/raw/clip-001.mp4 \
  --output assets/upscaled/clip-001.mp4 \
  --model proteus-v4 \
  --scale 2 \
  --codec h265
```

**Real-ESRGAN on extracted frames:**
```bash
# Extract frames
ffmpeg -i assets/raw/clip-001.mp4 -qscale:v 2 frames/frame_%04d.png

# Upscale all frames
python -m realesrgan -i frames/ -o frames_upscaled/ -s 2

# Reassemble with original audio
ffmpeg -framerate 30 -i frames_upscaled/frame_%04d.png \
  -i assets/raw/clip-001.mp4 -map 0:v -map 1:a \
  -c:v libx264 -crf 18 -pix_fmt yuv420p \
  assets/upscaled/clip-001.mp4
```

### Sharpening (Post-Upscale)

Apply light sharpening after upscaling, never before (pre-upscale sharpening amplifies artifacts).

```bash
# Subtle sharpen (good for most content)
ffmpeg -i assets/upscaled/scene-001.png -vf "unsharp=3:3:0.5:3:3:0.0" assets/upscaled/scene-001-sharp.png

# Stronger sharpen (for soft AI output)
ffmpeg -i assets/upscaled/scene-001.png -vf "unsharp=5:5:1.0:5:5:0.0" assets/upscaled/scene-001-sharp.png

# ImageMagick
magick assets/upscaled/scene-001.png -sharpen 0x1.0 assets/upscaled/scene-001-sharp.png
```

## Color Grading

### LUT-Based Grading (ffmpeg)

LUTs (Look-Up Tables) are the most reliable way to apply consistent color grading. A `.cube` file encodes a complete color transformation.

**Applying a LUT:**
```bash
# Apply a 3D LUT
ffmpeg -i assets/upscaled/scene-001.png \
  -vf "lut3d=luts/teal-orange-cinema.cube" \
  assets/graded/scene-001.png

# Apply to video
ffmpeg -i assets/upscaled/clip-001.mp4 \
  -vf "lut3d=luts/teal-orange-cinema.cube" \
  -c:v libx264 -crf 18 \
  assets/graded/clip-001.mp4
```

**Chaining LUT with adjustments:**
```bash
ffmpeg -i assets/upscaled/scene-001.png \
  -vf "lut3d=luts/film-stock.cube,eq=contrast=1.1:brightness=-0.03:saturation=0.9" \
  assets/graded/scene-001.png
```

### LUT Sources and Organization

Store LUTs in the project:
```
luts/
  cinematic/
    teal-orange.cube
    bleach-bypass.cube
    cross-processed.cube
    film-noir.cube
  film-stock/
    kodak-portra-400.cube
    fuji-velvia.cube
    cinestill-800t.cube
    kodak-vision3-500t.cube
  brand/
    broomva-tech.cube         # Custom brand LUT
    broomva-warm.cube
  utility/
    desaturate-30.cube
    warm-shift.cube
    cool-shift.cube
```

**Free LUT sources:**
- [lutsonline.com](https://lutsonline.com) -- free cinematic LUTs
- [filtergrade.com/free](https://filtergrade.com/free-luts) -- various styles
- Color grading communities on Reddit (r/colorgrading)

**Creating custom LUTs:**
1. Grade a reference image in DaVinci Resolve or Lightroom
2. Export the grade as a `.cube` file
3. Apply to all other images in the set via ffmpeg

### Manual Color Correction (ffmpeg)

When a LUT is too heavy-handed, use ffmpeg's EQ and color filters for precise control:

```bash
# Adjust contrast, brightness, saturation, gamma
ffmpeg -i input.png -vf "eq=contrast=1.15:brightness=-0.02:saturation=0.85:gamma=1.05" output.png

# Color balance (shift toward cooler tones)
ffmpeg -i input.png -vf "colorbalance=rs=-0.1:gs=-0.05:bs=0.1:rm=-0.1:gm=-0.05:bm=0.1" output.png

# Curves (lift shadows, compress highlights)
ffmpeg -i input.png -vf "curves=m='0/0.05 0.5/0.55 1/0.95'" output.png

# Vignette (darken edges)
ffmpeg -i input.png -vf "vignette=PI/4" output.png
```

### Lightroom Integration

For batch processing with complex grades, Lightroom presets are the most efficient approach.

**Applying presets via Lightroom Classic CLI (macOS):**

Lightroom does not have a true CLI, but you can automate via:

1. **Preset files** (`.xmp` or `.lrtemplate`) placed in Lightroom's preset directory
2. **Auto-import** with preset applied on import
3. **exiftool** for applying XMP sidecar data programmatically

**Using exiftool to apply develop settings:**
```bash
# Copy develop settings from a graded reference to all other files
exiftool -TagsFromFile graded_reference.xmp -all:all assets/upscaled/*.png

# Or apply specific settings
exiftool -Temperature=5500 -Tint=+5 -Exposure=+0.3 -Contrast=+15 \
  -Highlights=-20 -Shadows=+25 -Saturation=-10 \
  assets/upscaled/scene-001.png
```

**DaVinci Resolve (alternative):**
For video-heavy workflows, DaVinci Resolve's free tier provides professional color grading:
1. Import all clips/images into a timeline
2. Grade the first shot
3. Copy the grade to all other shots (right-click → Apply Grade)
4. Export with matching filenames

### Grade Matching Across Scenes

When multiple scenes need to look like they belong together:

1. **Grade the hero image first** -- this is the reference
2. **Export the hero grade as a LUT** from Resolve or create an ffmpeg filter chain
3. **Apply the same LUT to all other images** in the set
4. **Fine-tune individual images** if needed (exposure matching, white balance)

```bash
# Batch apply the same grade
for f in assets/upscaled/*.png; do
  name=$(basename "$f")
  ffmpeg -i "$f" \
    -vf "lut3d=luts/brand/project-grade.cube,eq=contrast=1.1:saturation=0.9" \
    "assets/graded/$name"
done
```

## Final Delivery

### Format Conversion

Convert graded assets to delivery formats:

```bash
# Web-optimized JPEG (quality 85, progressive)
ffmpeg -i assets/graded/scene-001.png -q:v 2 assets/final/scene-001.jpg

# WebP (smaller than JPEG, wide browser support)
ffmpeg -i assets/graded/scene-001.png -quality 85 assets/final/scene-001.webp

# AVIF (smallest, modern browsers)
ffmpeg -i assets/graded/scene-001.png -c:v libaom-av1 -crf 30 assets/final/scene-001.avif

# Video: H.264 for maximum compatibility
ffmpeg -i assets/graded/clip-001.mp4 \
  -c:v libx264 -crf 18 -preset slow -movflags +faststart \
  -c:a aac -b:a 128k \
  assets/final/clip-001.mp4

# Video: H.265 for smaller file size (Apple/modern devices)
ffmpeg -i assets/graded/clip-001.mp4 \
  -c:v libx265 -crf 22 -preset slow -tag:v hvc1 \
  -c:a aac -b:a 128k \
  assets/final/clip-001.mp4
```

### Size Optimization

```bash
# Check file sizes
du -sh assets/final/*

# Resize if too large for web (max 1920px wide for web delivery)
ffmpeg -i assets/graded/scene-001.png \
  -vf "scale='min(1920,iw)':'-1':flags=lanczos" \
  assets/final/scene-001.jpg

# Optimize JPEG further with mozjpeg (if installed)
cjpeg -quality 82 -progressive assets/graded/scene-001.png > assets/final/scene-001.jpg
```

### Metadata

Tag final assets with project metadata for searchability:

```bash
# Add metadata to image
exiftool \
  -Title="Maya Workspace - Morning" \
  -Description="AI-generated scene for content-engine project" \
  -Creator="Content Engine Cinema Pipeline" \
  -Copyright="Broomva Tech Corp 2026" \
  assets/final/scene-001.jpg

# Add metadata to video
ffmpeg -i assets/final/clip-001.mp4 \
  -metadata title="Maya Workspace - Morning" \
  -metadata artist="Content Engine Cinema Pipeline" \
  -metadata comment="AI-generated cinematic content" \
  -c copy \
  assets/final/clip-001-tagged.mp4
```

## Complete Post-Production Script

A full pipeline script that takes raw output through upscale, grade, and delivery:

```bash
#!/bin/bash
# post-production.sh — Full pipeline from raw to delivery
set -euo pipefail

PROJECT="${1:?Usage: post-production.sh <project-name>}"
SCALE="${2:-2}"
LUT="${3:-luts/cinematic/teal-orange.cube}"

RAW="assets/raw"
UPSCALED="assets/upscaled"
GRADED="assets/graded"
FINAL="assets/final"

mkdir -p "$UPSCALED" "$GRADED" "$FINAL"

echo "=== Upscaling (${SCALE}x) ==="
for f in "$RAW"/*.png; do
  name=$(basename "$f" .png)
  if [ -f "$UPSCALED/${name}.png" ]; then
    echo "  skip: ${name} (already upscaled)"
    continue
  fi
  echo "  upscale: ${name}"
  python -m realesrgan -i "$f" -o "$UPSCALED/${name}.png" -s "$SCALE" 2>/dev/null
done

echo "=== Color Grading ==="
for f in "$UPSCALED"/*.png; do
  name=$(basename "$f" .png)
  if [ -f "$GRADED/${name}.png" ]; then
    echo "  skip: ${name} (already graded)"
    continue
  fi
  echo "  grade: ${name}"
  ffmpeg -y -i "$f" \
    -vf "lut3d=${LUT},eq=contrast=1.1:saturation=0.9" \
    "$GRADED/${name}.png" 2>/dev/null
done

echo "=== Final Delivery ==="
for f in "$GRADED"/*.png; do
  name=$(basename "$f" .png)
  echo "  deliver: ${name}"
  # JPEG for web
  ffmpeg -y -i "$f" -q:v 2 "$FINAL/${name}.jpg" 2>/dev/null
  # WebP for modern browsers
  ffmpeg -y -i "$f" -quality 85 "$FINAL/${name}.webp" 2>/dev/null
done

echo "=== Done ==="
echo "Raw:      $(ls "$RAW"/*.png 2>/dev/null | wc -l | tr -d ' ') files"
echo "Upscaled: $(ls "$UPSCALED"/*.png 2>/dev/null | wc -l | tr -d ' ') files"
echo "Graded:   $(ls "$GRADED"/*.png 2>/dev/null | wc -l | tr -d ' ') files"
echo "Final:    $(ls "$FINAL"/*.{jpg,webp} 2>/dev/null | wc -l | tr -d ' ') files"
```

Usage:
```bash
chmod +x post-production.sh
./post-production.sh my-campaign 2 luts/film-stock/kodak-portra-400.cube
```
