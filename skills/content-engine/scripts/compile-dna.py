#!/usr/bin/env python3
"""
Content Engine — Visual DNA Compiler (compile-dna.py)

Compiles raw brand assets, character references, and style inspiration
into structured identity files with tool-specific prompt fragments.

Uses Gemini multimodal analysis for image/video understanding.
Pattern after knowledge-graph-memory conversation_history.py.

Usage:
    python3 scripts/compile-dna.py                    # Incremental (skip existing)
    python3 scripts/compile-dna.py --force             # Full regeneration
    python3 scripts/compile-dna.py --dry-run            # Preview without writing
    python3 scripts/compile-dna.py --type brand         # Only compile brands
    python3 scripts/compile-dna.py --type character     # Only compile characters
    python3 scripts/compile-dna.py --type style         # Only compile styles
    python3 scripts/compile-dna.py lint                 # Run lint checks
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "knowledge" / "raw"
COMPILED_DIR = REPO_ROOT / "knowledge" / "compiled"
TEMPLATES_DIR = REPO_ROOT / "templates"

BRAND_ASSETS = RAW_DIR / "brand-assets"
CHARACTER_REFS = RAW_DIR / "character-refs"
STYLE_INSPIRATION = RAW_DIR / "style-inspiration"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}

# ---------------------------------------------------------------------------
# Gemini Analysis
# ---------------------------------------------------------------------------

def get_gemini_client():
    """Initialize Gemini client. Requires GEMINI_API_KEY env var."""
    try:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("WARNING: GEMINI_API_KEY not set. Using template-only compilation.")
            return None
        return genai.Client(api_key=api_key)
    except ImportError:
        print("WARNING: google-genai not installed. pip install google-genai")
        return None


def analyze_image(client, image_path: Path, analysis_type: str) -> dict:
    """Analyze an image using Gemini multimodal."""
    if client is None:
        return {"error": "No Gemini client available", "path": str(image_path)}

    with open(image_path, "rb") as f:
        image_data = f.read()

    mime_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(image_path.suffix.lower(), "image/jpeg")

    prompts = {
        "brand": """Analyze this brand/campaign image for visual DNA extraction. Return a JSON object with:
{
  "color_palette": [{"hex": "#XXXXXX", "role": "primary|secondary|accent|background|highlight", "mood": "description"}],
  "lighting": {"type": "natural|studio|neon|ambient|dramatic", "direction": "front|side|back|overhead|diffused", "temperature": "warm|neutral|cool", "notes": ""},
  "composition": {"style": "rule-of-thirds|centered|symmetrical|negative-space|diagonal|leading-lines", "framing": "tight|medium|wide|extreme-wide", "notes": ""},
  "texture": {"primary": "matte|glossy|film-grain|clean-digital|textured|organic", "notes": ""},
  "pose_language": {"style": "candid|editorial|lifestyle|portrait|action|contemplative", "energy": "low|medium|high", "notes": ""},
  "overall_mood": "",
  "brand_signals": []
}
Return ONLY valid JSON, no markdown.""",
        "character": """Analyze this character reference image. Return a JSON object with:
{
  "apparent_age": "",
  "ethnicity_features": "",
  "build": "",
  "distinguishing_features": [],
  "default_expression": "",
  "energy_vibe": "",
  "hair": {"color": "", "style": "", "length": ""},
  "skin_tone": "",
  "face_shape": "",
  "wardrobe_style": "",
  "lighting_that_flatters": ""
}
Return ONLY valid JSON, no markdown.""",
        "style": """Analyze this style reference image for visual style extraction. Return a JSON object with:
{
  "style_name": "",
  "camera_language": {"shot_types": [], "movement": [], "framing": ""},
  "color_grammar": {"primary_palette": [], "secondary_palette": [], "grading_notes": ""},
  "lighting_setup": {"key": "", "fill": "", "rim": "", "temperature": "", "direction": ""},
  "composition_rules": [],
  "texture_quality": "",
  "reference_directors": [],
  "mood_atmosphere": ""
}
Return ONLY valid JSON, no markdown.""",
    }

    prompt = prompts.get(analysis_type, prompts["brand"])

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_data).decode()}},
                prompt,
            ],
        )
        text = response.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        if text.startswith("json"):
            text = text[4:]
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {"error": "Failed to parse Gemini response", "raw": text[:500]}
    except Exception as e:
        return {"error": str(e), "path": str(image_path)}


def extract_video_keyframes(video_path: Path, output_dir: Path, count: int = 5) -> list[Path]:
    """Extract keyframes from a video using ffmpeg."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = video_path.stem
    pattern = output_dir / f"{stem}_frame_%03d.jpg"

    try:
        # Get video duration
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=30,
        )
        duration = float(result.stdout.strip())
        interval = duration / (count + 1)

        # Extract frames at intervals
        subprocess.run(
            ["ffmpeg", "-i", str(video_path), "-vf", f"fps=1/{interval}",
             "-frames:v", str(count), "-q:v", "2", str(pattern)],
            capture_output=True, timeout=60,
        )
        return sorted(output_dir.glob(f"{stem}_frame_*.jpg"))
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
        print(f"  WARNING: ffmpeg keyframe extraction failed: {e}")
        return []


# ---------------------------------------------------------------------------
# File Hashing (for change detection)
# ---------------------------------------------------------------------------

def hash_file(path: Path) -> str:
    """SHA-256 hash of a file for change detection."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def hash_directory(directory: Path) -> str:
    """Combined hash of all files in a directory."""
    h = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            h.update(hash_file(path).encode())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_entities(raw_dir: Path) -> dict:
    """Discover brand/character/style entities from raw directory structure.

    Convention: each subdirectory under brand-assets/, character-refs/, or
    style-inspiration/ is one entity. Files directly in those dirs are
    treated as a default entity.
    """
    entities = {"brands": {}, "characters": {}, "styles": {}}

    for mapping in [
        (BRAND_ASSETS, "brands"),
        (CHARACTER_REFS, "characters"),
        (STYLE_INSPIRATION, "styles"),
    ]:
        base_dir, entity_type = mapping
        if not base_dir.exists():
            continue

        for item in sorted(base_dir.iterdir()):
            if item.name.startswith("."):
                continue
            if item.is_dir():
                assets = [
                    f for f in item.rglob("*")
                    if f.is_file()
                    and not f.name.startswith(".")
                    and f.suffix.lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
                ]
                if assets:
                    entities[entity_type][item.name] = {
                        "path": item,
                        "assets": assets,
                        "hash": hash_directory(item),
                    }
            elif item.suffix.lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                slug = "default"
                if slug not in entities[entity_type]:
                    entities[entity_type][slug] = {
                        "path": base_dir,
                        "assets": [],
                        "hash": "",
                    }
                entities[entity_type][slug]["assets"].append(item)

    # Recompute hash for default entities
    for entity_type in entities.values():
        for slug, data in entity_type.items():
            if slug == "default" and data["assets"]:
                h = hashlib.sha256()
                for f in data["assets"]:
                    h.update(hash_file(f).encode())
                data["hash"] = h.hexdigest()[:16]

    return entities


def needs_recompilation(slug: str, entity_type: str, source_hash: str) -> bool:
    """Check if a compiled file needs recompilation."""
    type_dir = {"brands": "brands", "characters": "characters", "styles": "styles"}
    compiled_path = COMPILED_DIR / type_dir[entity_type] / f"{slug}.md"

    if not compiled_path.exists():
        return True

    # Check if source hash changed
    content = compiled_path.read_text()
    return f"source_hash: \"{source_hash}\"" not in content


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def compile_brand(slug: str, data: dict, client, dry_run: bool = False) -> str:
    """Compile a brand identity from raw assets."""
    print(f"  Compiling brand: {slug} ({len(data['assets'])} assets)")

    # Analyze up to 10 images
    analyses = []
    for asset in data["assets"][:10]:
        if asset.suffix.lower() in IMAGE_EXTENSIONS:
            print(f"    Analyzing: {asset.name}")
            analysis = analyze_image(client, asset, "brand")
            if "error" not in analysis:
                analyses.append(analysis)

    # Build compiled file
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sources = [str(a.relative_to(REPO_ROOT)) for a in data["assets"]]

    # Aggregate color palettes
    all_colors = []
    for a in analyses:
        all_colors.extend(a.get("color_palette", []))

    # Aggregate lighting
    lighting_types = [a.get("lighting", {}).get("type", "") for a in analyses if a.get("lighting")]
    lighting_temps = [a.get("lighting", {}).get("temperature", "") for a in analyses if a.get("lighting")]

    # Aggregate composition
    comp_styles = [a.get("composition", {}).get("style", "") for a in analyses if a.get("composition")]

    # Aggregate texture
    textures = [a.get("texture", {}).get("primary", "") for a in analyses if a.get("texture")]

    # Aggregate pose
    pose_styles = [a.get("pose_language", {}).get("style", "") for a in analyses if a.get("pose_language")]

    # Aggregate mood
    moods = [a.get("overall_mood", "") for a in analyses if a.get("overall_mood")]

    # Deduplicate colors by hex
    seen_hex = set()
    unique_colors = []
    for c in all_colors:
        h = c.get("hex", "")
        if h and h not in seen_hex:
            seen_hex.add(h)
            unique_colors.append(c)

    # Most common values
    def most_common(items):
        if not items:
            return "unknown"
        filtered = [i for i in items if i]
        if not filtered:
            return "unknown"
        return max(set(filtered), key=filtered.count)

    # Build tool-specific prompts from analysis
    brand_mood = most_common(moods) if moods else "professional, polished"
    brand_lighting = most_common(lighting_types)
    brand_temp = most_common(lighting_temps)
    brand_comp = most_common(comp_styles)
    brand_texture = most_common(textures)
    brand_pose = most_common(pose_styles)

    color_desc = ", ".join(c.get("hex", "") for c in unique_colors[:6])

    md = f"""---
name: "{slug}"
type: brand-dna
compiled: "{now}"
source_hash: "{data['hash']}"
sources:
{chr(10).join(f'  - "{s}"' for s in sources[:20])}
tools: [nano-banana-pro, soul-cinema, weavy, comfyui]
---

# {slug.replace('-', ' ').title()} — Brand DNA

## Visual Identity

### Color Palette

| Hex | Role | Mood |
|-----|------|------|
"""
    for c in unique_colors[:8]:
        md += f"| {c.get('hex', 'N/A')} | {c.get('role', 'N/A')} | {c.get('mood', 'N/A')} |\n"

    md += f"""
### Lighting
- **Type**: {brand_lighting}
- **Temperature**: {brand_temp}
- **Direction**: {most_common([a.get('lighting', {}).get('direction', '') for a in analyses])}

### Composition
- **Style**: {brand_comp}
- **Framing**: {most_common([a.get('composition', {}).get('framing', '') for a in analyses])}

### Texture
- **Primary**: {brand_texture}

### Pose Language
- **Style**: {brand_pose}
- **Energy**: {most_common([a.get('pose_language', {}).get('energy', '') for a in analyses])}

### Overall Mood
{brand_mood}

## Tool-Specific Prompts

### Nano Banana Pro
- **Positive**: {brand_mood}, {brand_lighting} lighting, {brand_temp} tones, {brand_comp} composition, {brand_texture} texture, {color_desc}
- **Negative**: blurry, low quality, oversaturated, artificial, stock photo feel
- **Parameters**: guidance_scale: 7.5, steps: 30

### Soul Cinema (Higgsfield)
- **Positive**: cinematic {brand_mood}, {brand_lighting} lighting, {brand_temp} color temperature, {brand_comp} framing, film grain, depth of field
- **Negative**: flat lighting, centered composition, digital look, harsh shadows

### Weavy
- **Scene setup**: {brand_mood} atmosphere, {brand_lighting} lighting, {brand_temp} tones
- **Environment**: match {brand_comp} composition style
- **Character direction**: {brand_pose} pose language

### ComfyUI
- **Base model**: Stable Diffusion XL
- **Recommended LoRA**: style-{slug}
- **Prompt prefix**: {brand_mood}, {brand_lighting} lighting, {brand_comp} composition, {brand_texture}
- **CFG Scale**: 7.5
- **Sampler**: DPM++ 2M Karras

## Anti-Patterns

| Pattern | Why It Breaks Consistency |
|---------|--------------------------|
| Oversaturated colors | Conflicts with {brand_temp} temperature |
| Flash photography look | Destroys {brand_lighting} lighting feel |
| Stock photo poses | Contradicts {brand_pose} pose language |
| Generic backgrounds | Loses {brand_mood} mood |

## Provenance

- **Compiled**: {now}
- **Source hash**: {data['hash']}
- **Assets analyzed**: {len(analyses)}/{len(data['assets'])}
- **Analysis model**: gemini-2.5-flash
"""
    return md


def compile_character(slug: str, data: dict, client, dry_run: bool = False) -> str:
    """Compile a character sheet from reference images."""
    print(f"  Compiling character: {slug} ({len(data['assets'])} assets)")

    analyses = []
    for asset in data["assets"][:5]:
        if asset.suffix.lower() in IMAGE_EXTENSIONS:
            print(f"    Analyzing: {asset.name}")
            analysis = analyze_image(client, asset, "character")
            if "error" not in analysis:
                analyses.append(analysis)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sources = [str(a.relative_to(REPO_ROOT)) for a in data["assets"]]

    # Aggregate character features
    primary = analyses[0] if analyses else {}

    md = f"""---
name: "{slug}"
type: character-sheet
compiled: "{now}"
source_hash: "{data['hash']}"
nano_banana_ref: ""
consistency_model: "nano-banana-pro"
sources:
{chr(10).join(f'  - "{s}"' for s in sources[:10])}
---

# {slug.replace('-', ' ').title()} — Character Sheet

## Identity

- **Apparent Age**: {primary.get('apparent_age', 'TBD')}
- **Features**: {primary.get('ethnicity_features', 'TBD')}
- **Build**: {primary.get('build', 'TBD')}
- **Distinguishing Features**: {', '.join(primary.get('distinguishing_features', ['TBD']))}
- **Default Expression**: {primary.get('default_expression', 'TBD')}
- **Energy/Vibe**: {primary.get('energy_vibe', 'TBD')}
- **Hair**: {primary.get('hair', {}).get('color', 'TBD')} {primary.get('hair', {}).get('style', '')} ({primary.get('hair', {}).get('length', '')})
- **Skin Tone**: {primary.get('skin_tone', 'TBD')}
- **Face Shape**: {primary.get('face_shape', 'TBD')}

## Consistency Anchors

- **Nano Banana Pro Character Sheet ID**: _(fill after creating in Nano Banana Pro)_
- **LoRA Weights**: _(fill if fine-tuned)_
- **Face Embedding Hash**: _(auto-generated on first consistency check)_
- **Similarity Threshold**: 0.85

## Scene Defaults

### Wardrobe
- **Default Style**: {primary.get('wardrobe_style', 'TBD')}
- **Color Palette**: _(inherit from brand DNA if linked)_

### Environments That Work
| Environment | Why |
|-------------|-----|
| Natural outdoor | Complements {primary.get('lighting_that_flatters', 'natural')} lighting |
| Urban street | Matches {primary.get('energy_vibe', 'natural')} energy |
| Studio neutral | Clean background for character focus |

### Lighting That Flatters
- **Best**: {primary.get('lighting_that_flatters', 'natural soft lighting')}
- **Avoid**: harsh direct flash, overhead fluorescent

## Tool-Specific Character Prompts

### Nano Banana Pro
- **Character prompt**: {primary.get('apparent_age', '')} year old, {primary.get('build', '')} build, {primary.get('hair', {}).get('color', '')} {primary.get('hair', {}).get('style', '')} hair, {primary.get('skin_tone', '')} skin, {primary.get('default_expression', '')} expression
- **Consistency mode**: character_sheet

### Weavy
- **Character import**: Use Nano Banana Pro character sheet ID
- **Face swap**: enabled
- **Pose direction**: {primary.get('energy_vibe', 'natural')}

## Provenance

- **Compiled**: {now}
- **Source hash**: {data['hash']}
- **Assets analyzed**: {len(analyses)}/{len(data['assets'])}
"""
    return md


def compile_style(slug: str, data: dict, client, dry_run: bool = False) -> str:
    """Compile a style guide from inspiration assets."""
    print(f"  Compiling style: {slug} ({len(data['assets'])} assets)")

    analyses = []
    for asset in data["assets"][:8]:
        if asset.suffix.lower() in IMAGE_EXTENSIONS:
            print(f"    Analyzing: {asset.name}")
            analysis = analyze_image(client, asset, "style")
            if "error" not in analysis:
                analyses.append(analysis)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sources = [str(a.relative_to(REPO_ROOT)) for a in data["assets"]]

    primary = analyses[0] if analyses else {}
    camera = primary.get("camera_language", {})
    color = primary.get("color_grammar", {})
    lighting = primary.get("lighting_setup", {})

    ref_directors = primary.get("reference_directors", [])
    ref_str = ", ".join(ref_directors) if ref_directors else "N/A"

    md = f"""---
name: "{slug}"
type: style-guide
compiled: "{now}"
source_hash: "{data['hash']}"
category: "cinematic"
camera_ref: {json.dumps(ref_directors[:3]) if ref_directors else '[]'}
sources:
{chr(10).join(f'  - "{s}"' for s in sources[:10])}
---

# {slug.replace('-', ' ').title()} — Style Guide

## Camera Language
- **Shot Types**: {', '.join(camera.get('shot_types', ['medium', 'close-up']))}
- **Movement**: {', '.join(camera.get('movement', ['static']))}
- **Framing**: {camera.get('framing', 'standard')}
- **Reference Directors**: {ref_str}

## Color Grammar
- **Primary Palette**: {', '.join(color.get('primary_palette', ['N/A']))}
- **Secondary Palette**: {', '.join(color.get('secondary_palette', ['N/A']))}
- **Grading Notes**: {color.get('grading_notes', 'N/A')}

## Lighting Setup
- **Key**: {lighting.get('key', 'N/A')}
- **Fill**: {lighting.get('fill', 'N/A')}
- **Rim**: {lighting.get('rim', 'N/A')}
- **Temperature**: {lighting.get('temperature', 'N/A')}
- **Direction**: {lighting.get('direction', 'N/A')}

## Composition Rules
{chr(10).join(f'- {r}' for r in primary.get('composition_rules', ['Follow reference imagery']))}

## Mood & Atmosphere
{primary.get('mood_atmosphere', 'Match reference imagery mood')}

## Exact Prompts

### Nano Banana Pro
- **Positive**: {primary.get('style_name', slug)} style, {primary.get('mood_atmosphere', '')}, {lighting.get('temperature', 'neutral')} lighting
- **Negative**: inconsistent style, generic, stock

### Soul Cinema
- **Positive**: {primary.get('style_name', slug)} cinematography, {ref_str} inspired, {primary.get('mood_atmosphere', '')}
- **Negative**: flat, digital, unintentional

### ComfyUI
- **LoRA**: style-{slug}
- **Prompt prefix**: in the style of {primary.get('style_name', slug)}, {', '.join(camera.get('shot_types', []))}
- **CFG**: 7.5

## Provenance

- **Compiled**: {now}
- **Source hash**: {data['hash']}
- **Assets analyzed**: {len(analyses)}/{len(data['assets'])}
"""
    return md


# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------

def run_lint() -> int:
    """Run lint checks on compiled knowledge."""
    issues = []
    compiled_files = list(COMPILED_DIR.rglob("*.md"))

    if not compiled_files:
        print("LINT: No compiled files found. Run '/content-engine compile' first.")
        return 0

    print(f"LINT: Checking {len(compiled_files)} compiled files...")

    for cf in compiled_files:
        content = cf.read_text()

        # S001: Frontmatter exists
        if not content.startswith("---"):
            issues.append(f"S001 [structural] {cf.name}: Missing YAML frontmatter")
            continue

        # S002: Required fields
        for field in ["name:", "type:", "compiled:", "source_hash:"]:
            if field not in content:
                issues.append(f"S002 [structural] {cf.name}: Missing required field '{field}'")

        # F001: Freshness (warn if > 30 days old)
        try:
            for line in content.split("\n"):
                if line.strip().startswith("compiled:"):
                    date_str = line.split(":", 1)[1].strip().strip('"')
                    compiled_date = datetime.strptime(date_str, "%Y-%m-%d")
                    age = (datetime.now() - compiled_date).days
                    if age > 30:
                        issues.append(f"F001 [freshness] {cf.name}: Compiled {age} days ago (>30 day threshold)")
        except (ValueError, IndexError):
            issues.append(f"F001 [freshness] {cf.name}: Could not parse compiled date")

        # X001: Source files exist
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith('- "knowledge/') or line.startswith('- "raw/'):
                source_path = REPO_ROOT / line.strip('- "')
                if not source_path.exists():
                    issues.append(f"X001 [cross-ref] {cf.name}: Source not found: {line.strip('- \"')}")

        # S003: Tool-specific prompts section exists
        if "## Tool-Specific" not in content and "## Exact Prompts" not in content:
            issues.append(f"S003 [structural] {cf.name}: Missing tool-specific prompts section")

        # O001: Check for TBD placeholders
        tbd_count = content.count("TBD")
        if tbd_count > 3:
            issues.append(f"O001 [completeness] {cf.name}: {tbd_count} TBD placeholders remaining")

    # Report
    if issues:
        print(f"\nLINT: {len(issues)} issue(s) found:\n")
        for issue in sorted(issues):
            print(f"  {issue}")
        return 1
    else:
        print("LINT: All checks passed.")
        return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Content Engine — Visual DNA Compiler")
    parser.add_argument("command", nargs="?", default="compile", choices=["compile", "lint"],
                        help="Command to run (default: compile)")
    parser.add_argument("--force", action="store_true", help="Force recompilation of all entities")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    parser.add_argument("--type", choices=["brand", "character", "style"],
                        help="Only compile a specific entity type")
    args = parser.parse_args()

    if args.command == "lint":
        sys.exit(run_lint())

    # Compile
    print("Content Engine — Visual DNA Compiler")
    print(f"  Raw directory: {RAW_DIR}")
    print(f"  Compiled directory: {COMPILED_DIR}")
    print()

    # Discover entities
    entities = discover_entities(RAW_DIR)

    total_brands = len(entities["brands"])
    total_chars = len(entities["characters"])
    total_styles = len(entities["styles"])
    total = total_brands + total_chars + total_styles

    if total == 0:
        print("No assets found in knowledge/raw/. Add brand images, character refs,")
        print("or style inspiration to subdirectories and re-run.")
        print()
        print("  knowledge/raw/brand-assets/{brand-name}/   → images")
        print("  knowledge/raw/character-refs/{char-name}/   → face photos")
        print("  knowledge/raw/style-inspiration/{style}/    → mood boards")
        return

    print(f"Found: {total_brands} brands, {total_chars} characters, {total_styles} styles")
    print()

    # Initialize Gemini
    client = get_gemini_client()

    compiled_count = 0
    skipped_count = 0

    # Compile brands
    if args.type is None or args.type == "brand":
        for slug, data in entities["brands"].items():
            if not args.force and not needs_recompilation(slug, "brands", data["hash"]):
                print(f"  Skipping brand '{slug}' (unchanged)")
                skipped_count += 1
                continue

            md = compile_brand(slug, data, client, args.dry_run)
            out_path = COMPILED_DIR / "brands" / f"{slug}.md"

            if args.dry_run:
                print(f"  [DRY RUN] Would write: {out_path}")
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(md)
                print(f"  Wrote: {out_path}")
            compiled_count += 1

    # Compile characters
    if args.type is None or args.type == "character":
        for slug, data in entities["characters"].items():
            if not args.force and not needs_recompilation(slug, "characters", data["hash"]):
                print(f"  Skipping character '{slug}' (unchanged)")
                skipped_count += 1
                continue

            md = compile_character(slug, data, client, args.dry_run)
            out_path = COMPILED_DIR / "characters" / f"{slug}.md"

            if args.dry_run:
                print(f"  [DRY RUN] Would write: {out_path}")
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(md)
                print(f"  Wrote: {out_path}")
            compiled_count += 1

    # Compile styles
    if args.type is None or args.type == "style":
        for slug, data in entities["styles"].items():
            if not args.force and not needs_recompilation(slug, "styles", data["hash"]):
                print(f"  Skipping style '{slug}' (unchanged)")
                skipped_count += 1
                continue

            md = compile_style(slug, data, client, args.dry_run)
            out_path = COMPILED_DIR / "styles" / f"{slug}.md"

            if args.dry_run:
                print(f"  [DRY RUN] Would write: {out_path}")
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(md)
                print(f"  Wrote: {out_path}")
            compiled_count += 1

    print()
    print(f"Done. Compiled: {compiled_count}, Skipped: {skipped_count}")

    if not args.dry_run and compiled_count > 0:
        print()
        print("Run 'python3 scripts/compile-dna.py lint' to verify consistency.")


if __name__ == "__main__":
    main()
