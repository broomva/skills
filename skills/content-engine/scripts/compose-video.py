#!/usr/bin/env python3
"""
Content Engine — Multi-Shot Video Composer (compose-video.py)

Generates long-form videos by chaining multiple clips with continuity.
Supports two backends:
  1. Veo 3.0 API (clip chain with last-frame continuity)
  2. Higgsfield Cinema Studio (browser automation via agent-browser)

Usage:
    # From a storyboard file
    python3 scripts/compose-video.py storyboard.md

    # Quick multi-shot from a single concept
    python3 scripts/compose-video.py --concept "Fashion model in urban night" --shots 4

    # With compiled brand DNA
    python3 scripts/compose-video.py storyboard.md --brand arcan-studio

    # Using Higgsfield backend
    python3 scripts/compose-video.py storyboard.md --backend higgsfield

    # Dry run (show what would be generated)
    python3 scripts/compose-video.py storyboard.md --dry-run
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPILED_DIR = REPO_ROOT / "knowledge" / "compiled"
OUTPUT_DIR = REPO_ROOT / "knowledge" / "compiled" / "output"

# ---------------------------------------------------------------------------
# Storyboard Parsing
# ---------------------------------------------------------------------------

def parse_storyboard(path: Path) -> dict:
    """Parse a storyboard Markdown file into structured shots.

    Format:
    ---
    title: "Video Title"
    brand: arcan-studio
    aspect_ratio: 16:9
    duration_per_shot: 8
    ---

    ## Shot 1: Establishing
    Cinematic wide shot of city at night...

    ## Shot 2: Character Introduction
    Model walks through rain-soaked street...
    """
    content = path.read_text()
    meta = {}
    shots = []

    # Parse frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    meta[key.strip()] = val.strip().strip('"')
            content = parts[2]

    # Parse shots
    current_shot = None
    current_text = []

    for line in content.split("\n"):
        if line.startswith("## Shot") or line.startswith("## shot"):
            if current_shot is not None:
                shots.append({
                    "name": current_shot,
                    "prompt": "\n".join(current_text).strip(),
                })
            current_shot = line.replace("##", "").strip()
            current_text = []
        elif current_shot is not None:
            current_text.append(line)

    if current_shot is not None:
        shots.append({
            "name": current_shot,
            "prompt": "\n".join(current_text).strip(),
        })

    return {"meta": meta, "shots": shots}


def generate_storyboard_from_concept(concept: str, num_shots: int, brand_dna: dict | None = None) -> dict:
    """Auto-generate a multi-shot storyboard from a concept using Gemini."""
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    brand_context = ""
    if brand_dna:
        brand_context = f"""
Use this brand DNA to guide the visual style:
- Mood: {brand_dna.get('mood', 'cinematic')}
- Lighting: {brand_dna.get('lighting_type', 'dramatic')}, {brand_dna.get('lighting_temp', 'cool')}
- Composition: {brand_dna.get('composition', 'rule-of-thirds')}
- Colors: {brand_dna.get('colors', 'deep purple, charcoal, neon accents')}
"""

    prompt = f"""Create a {num_shots}-shot cinematic video storyboard for this concept: "{concept}"

{brand_context}

For each shot, write a detailed visual description (3-4 sentences) that a video AI model can use as a prompt.
Include: camera movement, lighting, mood, composition, and action.
Each shot should flow naturally into the next for visual continuity.

Return as JSON:
{{
  "title": "Video Title",
  "shots": [
    {{"name": "Shot 1: Description", "prompt": "detailed visual prompt..."}},
    ...
  ]
}}
Return ONLY valid JSON."""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text[:-3]
    if text.startswith("json"):
        text = text[4:]

    result = json.loads(text.strip())
    return {"meta": {"title": result.get("title", concept)}, "shots": result["shots"]}


# ---------------------------------------------------------------------------
# Brand DNA Loading
# ---------------------------------------------------------------------------

def load_brand_dna(brand_slug: str) -> dict | None:
    """Load compiled brand DNA and extract key visual parameters."""
    brand_path = COMPILED_DIR / "brands" / f"{brand_slug}.md"
    if not brand_path.exists():
        print(f"  WARNING: Brand '{brand_slug}' not found at {brand_path}")
        return None

    content = brand_path.read_text()
    dna = {}

    # Extract key fields
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- **Type**:"):
            dna["lighting_type"] = line.split(":", 1)[1].strip()
        elif line.startswith("- **Temperature**:"):
            dna["lighting_temp"] = line.split(":", 1)[1].strip()
        elif line.startswith("- **Style**:") and "composition" not in str(dna):
            dna["composition"] = line.split(":", 1)[1].strip()
        elif line.startswith("- **Primary**:"):
            dna["texture"] = line.split(":", 1)[1].strip()

    # Extract mood
    in_mood = False
    for line in content.split("\n"):
        if "### Overall Mood" in line:
            in_mood = True
            continue
        if in_mood and line.strip() and not line.startswith("#"):
            dna["mood"] = line.strip()
            break

    # Extract color hex values
    colors = []
    for line in content.split("\n"):
        if line.startswith("| #"):
            hex_val = line.split("|")[1].strip()
            colors.append(hex_val)
    dna["colors"] = ", ".join(colors[:6])

    return dna


def inject_brand_into_prompt(prompt: str, brand_dna: dict) -> str:
    """Inject compiled brand DNA into a shot prompt."""
    suffix = []
    if brand_dna.get("mood"):
        suffix.append(brand_dna["mood"])
    if brand_dna.get("lighting_type"):
        suffix.append(f"{brand_dna['lighting_type']} lighting")
    if brand_dna.get("lighting_temp"):
        suffix.append(f"{brand_dna['lighting_temp']} color temperature")
    if brand_dna.get("composition"):
        suffix.append(f"{brand_dna['composition']} composition")
    if brand_dna.get("colors"):
        suffix.append(f"color palette: {brand_dna['colors']}")

    if suffix:
        return f"{prompt}\n\nVisual style: {', '.join(suffix)}. Cinematic quality, 8K, film grain."
    return prompt


# ---------------------------------------------------------------------------
# Veo Backend
# ---------------------------------------------------------------------------

def generate_clip_veo(prompt: str, shot_index: int, output_dir: Path,
                      aspect_ratio: str = "16:9", duration: int = 8,
                      reference_frame: Path | None = None) -> Path | None:
    """Generate a single video clip via Veo 3.0 API."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    # If we have a reference frame from the previous clip, mention continuity
    if reference_frame and reference_frame.exists():
        prompt += "\n\nMaintain visual continuity with the previous shot. Same character, same environment, smooth transition."

    print(f"  Generating clip {shot_index + 1} via Veo 3.0...")

    try:
        operation = client.models.generate_videos(
            model="veo-3.0-generate-001",
            prompt=prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio=aspect_ratio,
                number_of_videos=1,
                duration_seconds=duration,
                person_generation="allow_all",
            ),
        )

        while not operation.done:
            time.sleep(10)
            operation = client.operations.get(operation)
            print(f"    polling...")

        if operation.response and operation.response.generated_videos:
            gv = operation.response.generated_videos[0]
            uri = gv.video.uri
            api_key = os.environ["GEMINI_API_KEY"]

            out_path = output_dir / f"shot_{shot_index + 1:02d}.mp4"
            urllib.request.urlretrieve(f"{uri}&key={api_key}", str(out_path))
            size = out_path.stat().st_size
            print(f"    Saved: {out_path.name} ({size:,} bytes)")
            return out_path
        else:
            print(f"    No video generated")
            return None

    except Exception as e:
        print(f"    Error: {e}")
        return None


def extract_last_frame(video_path: Path, output_path: Path) -> Path | None:
    """Extract the last frame of a video for continuity reference."""
    try:
        subprocess.run(
            ["ffmpeg", "-sseof", "-0.1", "-i", str(video_path),
             "-frames:v", "1", "-q:v", "2", "-y", str(output_path)],
            capture_output=True, timeout=30,
        )
        if output_path.exists():
            return output_path
    except Exception as e:
        print(f"    Could not extract last frame: {e}")
    return None


# ---------------------------------------------------------------------------
# Higgsfield Backend
# ---------------------------------------------------------------------------

def generate_clip_higgsfield(prompt: str, shot_index: int, output_dir: Path,
                              aspect_ratio: str = "16:9",
                              reference_image: Path | None = None) -> Path | None:
    """Generate a video clip via Higgsfield API (Seedance/DOP models)."""
    import higgsfield_client

    print(f"  Generating clip {shot_index + 1} via Higgsfield...")

    if reference_image and reference_image.exists():
        # Image-to-video mode
        try:
            from PIL import Image
            img = Image.open(reference_image)
            image_url = higgsfield_client.upload_image(img)
            print(f"    Uploaded reference image: {reference_image.name}")

            result = higgsfield_client.subscribe(
                "/v1/image2video/dop",
                {
                    "input": {
                        "model": "dop-turbo",
                        "prompt": prompt,
                        "input_images": [{"type": "image_url", "image_url": image_url}],
                    }
                },
                on_queue_update=lambda s: print(f"    Status: {s}"),
            )
        except ImportError:
            print("    WARNING: Pillow not installed for image upload, falling back to text-to-video")
            reference_image = None

    if not reference_image or not reference_image.exists():
        # Text-to-video: generate start frame, then animate
        print(f"    Step 1: Generating start frame...")
        result = higgsfield_client.subscribe(
            "bytedance/seedream/v4/text-to-image",
            {
                "prompt": prompt,
                "resolution": "2K",
                "aspect_ratio": aspect_ratio,
            },
            on_queue_update=lambda s: print(f"    Status: {s}"),
        )

        # Get the image URL and convert to video
        if result and "images" in result and result["images"]:
            image_url = result["images"][0].get("url")
            if image_url:
                print(f"    Step 2: Animating start frame...")
                result = higgsfield_client.subscribe(
                    "/v1/image2video/dop",
                    {
                        "input": {
                            "model": "dop-turbo",
                            "prompt": prompt,
                            "input_images": [{"type": "image_url", "image_url": image_url}],
                        }
                    },
                    on_queue_update=lambda s: print(f"    Status: {s}"),
                )

    # Download result
    if result:
        video_url = None
        # Try different result formats
        if isinstance(result, dict):
            if "url" in result:
                video_url = result["url"]
            elif "video" in result and isinstance(result["video"], dict):
                video_url = result["video"].get("url")
            elif "jobs" in result:
                jobs = result["jobs"]
                if jobs and isinstance(jobs[0], dict):
                    raw = jobs[0].get("results", {}).get("raw", {})
                    video_url = raw.get("url")

        if video_url:
            out_path = output_dir / f"shot_{shot_index + 1:02d}.mp4"
            urllib.request.urlretrieve(video_url, str(out_path))
            size = out_path.stat().st_size
            print(f"    Saved: {out_path.name} ({size:,} bytes)")
            return out_path

    print(f"    Could not extract video URL from result")
    return None


# ---------------------------------------------------------------------------
# Stitching
# ---------------------------------------------------------------------------

def stitch_clips(clip_paths: list[Path], output_path: Path,
                 crossfade_duration: float = 0.5) -> Path | None:
    """Stitch multiple video clips into one with crossfade transitions."""
    if not clip_paths:
        print("  No clips to stitch")
        return None

    if len(clip_paths) == 1:
        # Just copy the single clip
        import shutil
        shutil.copy2(clip_paths[0], output_path)
        return output_path

    # Build ffmpeg concat with xfade filter
    # For N clips, we need N-1 xfade filters
    inputs = []
    for p in clip_paths:
        inputs.extend(["-i", str(p)])

    # Simple concat (no crossfade for reliability)
    # Create concat file
    concat_file = output_path.parent / "concat_list.txt"
    with open(concat_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    try:
        subprocess.run(
            ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_file),
             "-c", "copy", "-y", str(output_path)],
            capture_output=True, timeout=120,
        )
        concat_file.unlink()

        if output_path.exists():
            size = output_path.stat().st_size
            duration_result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
                capture_output=True, text=True, timeout=10,
            )
            duration = float(duration_result.stdout.strip()) if duration_result.stdout.strip() else 0
            print(f"  Final video: {output_path.name} ({size:,} bytes, {duration:.1f}s)")
            return output_path
    except Exception as e:
        print(f"  Stitch error: {e}")
        concat_file.unlink(missing_ok=True)

    return None


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def write_manifest(output_dir: Path, storyboard: dict, clips: list, brand_slug: str | None):
    """Write manifest.json tracking what was generated."""
    manifest = {
        "title": storyboard["meta"].get("title", "Untitled"),
        "brand": brand_slug,
        "generated": datetime.now(timezone.utc).isoformat(),
        "backend": "veo-3.0",
        "shots": [],
    }

    for i, shot in enumerate(storyboard["shots"]):
        clip_path = clips[i] if i < len(clips) and clips[i] else None
        manifest["shots"].append({
            "name": shot["name"],
            "prompt": shot["prompt"][:200],
            "clip": str(clip_path.name) if clip_path else None,
            "status": "generated" if clip_path else "failed",
        })

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  Manifest: {manifest_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Content Engine — Multi-Shot Video Composer")
    parser.add_argument("storyboard", nargs="?", help="Path to storyboard.md file")
    parser.add_argument("--concept", help="Auto-generate storyboard from concept")
    parser.add_argument("--shots", type=int, default=4, help="Number of shots (with --concept)")
    parser.add_argument("--brand", help="Brand slug for compiled DNA injection")
    parser.add_argument("--backend", choices=["veo", "higgsfield"], default="veo",
                        help="Generation backend (default: veo)")
    parser.add_argument("--aspect-ratio", default="16:9", help="Aspect ratio (default: 16:9)")
    parser.add_argument("--duration", type=int, default=8, help="Duration per shot in seconds")
    parser.add_argument("--output", help="Output directory (default: auto-generated)")
    parser.add_argument("--captions", action="store_true",
                        help="Generate OpenCaptions CWI captions for each clip")
    parser.add_argument("--remotion", action="store_true",
                        help="Render final video with Remotion (transitions, captions, brand)")
    parser.add_argument("--dry-run", action="store_true", help="Show storyboard without generating")
    args = parser.parse_args()

    print("Content Engine — Multi-Shot Video Composer")
    print()

    # Load brand DNA
    brand_dna = None
    if args.brand:
        brand_dna = load_brand_dna(args.brand)
        if brand_dna:
            print(f"  Brand: {args.brand} (mood: {brand_dna.get('mood', 'N/A')})")

    # Get storyboard
    if args.storyboard:
        storyboard_path = Path(args.storyboard)
        if not storyboard_path.exists():
            print(f"ERROR: Storyboard not found: {storyboard_path}")
            sys.exit(1)
        storyboard = parse_storyboard(storyboard_path)
    elif args.concept:
        print(f"  Generating storyboard for: \"{args.concept}\" ({args.shots} shots)")
        storyboard = generate_storyboard_from_concept(args.concept, args.shots, brand_dna)
    else:
        print("ERROR: Provide a storyboard file or --concept")
        sys.exit(1)

    title = storyboard["meta"].get("title", "untitled")
    shots = storyboard["shots"]
    print(f"  Title: {title}")
    print(f"  Shots: {len(shots)}")
    print()

    # Show storyboard
    for i, shot in enumerate(shots):
        print(f"  [{i + 1}/{len(shots)}] {shot['name']}")
        print(f"       {shot['prompt'][:120]}...")
        print()

    if args.dry_run:
        print("DRY RUN — no generation performed.")
        return

    # Setup output directory
    slug = title.lower().replace(" ", "-").replace("/", "-")[:50]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    output_dir = Path(args.output) if args.output else OUTPUT_DIR / f"{slug}-{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Output: {output_dir}")
    print()

    if args.backend == "higgsfield":
        hf_key = os.environ.get("HF_KEY")
        if not hf_key:
            # Try constructing from separate ID + SECRET
            hf_id = os.environ.get("HF_KEY_ID")
            hf_secret = os.environ.get("HF_KEY_SECRET")
            if hf_id and hf_secret:
                os.environ["HF_KEY"] = f"{hf_id}:{hf_secret}"
            else:
                print("ERROR: HF_KEY not set. Get your API key from https://cloud.higgsfield.ai/api-keys")
                print("  export HF_KEY='your-key-id:your-key-secret'")
                print("  or: export HF_KEY_ID='...' && export HF_KEY_SECRET='...'")
                sys.exit(1)

    # Generate clips
    clips = []
    last_frame = None

    for i, shot in enumerate(shots):
        prompt = shot["prompt"]
        if brand_dna:
            prompt = inject_brand_into_prompt(prompt, brand_dna)

        if args.backend == "higgsfield":
            clip = generate_clip_higgsfield(
                prompt=prompt,
                shot_index=i,
                output_dir=output_dir,
                aspect_ratio=args.aspect_ratio,
                reference_image=last_frame,
            )
        else:
            clip = generate_clip_veo(
                prompt=prompt,
                shot_index=i,
                output_dir=output_dir,
                aspect_ratio=args.aspect_ratio,
                duration=args.duration,
                reference_frame=last_frame,
            )
        clips.append(clip)

        # Extract last frame for continuity
        if clip:
            last_frame_path = output_dir / f"frame_last_{i + 1:02d}.jpg"
            last_frame = extract_last_frame(clip, last_frame_path)

    # Stitch clips
    successful_clips = [c for c in clips if c is not None]
    if successful_clips:
        print()
        print(f"Stitching {len(successful_clips)} clips...")
        final_path = output_dir / f"{slug}-final.mp4"
        stitch_clips(successful_clips, final_path)

    # OpenCaptions (optional)
    if args.captions and successful_clips:
        captions_dir = output_dir / "captions"
        captions_dir.mkdir(exist_ok=True)
        print()
        print("Generating OpenCaptions CWI captions...")

        opencaptions_available = subprocess.run(
            ["npx", "opencaptions", "doctor"], capture_output=True, timeout=15,
        ).returncode == 0 if True else False

        try:
            subprocess.run(["npx", "opencaptions", "doctor"], capture_output=True, timeout=15)
            opencaptions_available = True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            opencaptions_available = False

        if opencaptions_available:
            for clip in successful_clips:
                cwi_path = captions_dir / f"{clip.stem}.cwi.json"
                print(f"  Captioning: {clip.name}")
                try:
                    subprocess.run(
                        ["npx", "opencaptions", "generate", str(clip),
                         "--output", str(cwi_path)],
                        timeout=120,
                    )
                    if cwi_path.exists():
                        print(f"    Saved: {cwi_path.name}")
                except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                    print(f"    Caption error: {e}")
        else:
            print("  OpenCaptions not installed. Falling back to scene brief text.")
            print("  Install: cd ~/broomva/apps/opencaptions && bun install")
            # Write scene brief text as fallback captions
            for i, clip in enumerate(successful_clips):
                if i < len(shots):
                    fallback = {"text": shots[i]["prompt"][:200], "type": "scene-brief"}
                    fallback_path = captions_dir / f"{clip.stem}.fallback.json"
                    with open(fallback_path, "w") as f:
                        json.dump(fallback, f, indent=2)

    # Remotion render (optional)
    if args.remotion and successful_clips:
        print()
        remotion_dir = REPO_ROOT / "remotion"
        render_script = remotion_dir / "render.sh"

        if render_script.exists():
            print("Rendering with Remotion (transitions + captions + brand)...")
            rendered_path = output_dir / f"{slug}-rendered.mp4"
            try:
                subprocess.run(
                    ["bash", str(render_script), str(output_dir), str(rendered_path)],
                    timeout=300,
                )
                if rendered_path.exists():
                    size = rendered_path.stat().st_size
                    print(f"  Rendered: {rendered_path.name} ({size:,} bytes)")
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                print(f"  Remotion render error: {e}")
        else:
            print("Remotion not set up. Run: cd remotion && bun install")

    # Write manifest
    write_manifest(output_dir, storyboard, clips, args.brand)

    # Summary
    print()
    print(f"Done. {len(successful_clips)}/{len(shots)} clips generated.")
    print(f"Output: {output_dir}")
    if successful_clips:
        total_duration = len(successful_clips) * args.duration
        print(f"Total duration: ~{total_duration}s ({total_duration / 60:.1f} min)")
    if args.captions:
        print(f"Captions: {output_dir / 'captions'}")
    if args.remotion:
        print(f"Rendered: {output_dir / f'{slug}-rendered.mp4'}")


if __name__ == "__main__":
    main()
