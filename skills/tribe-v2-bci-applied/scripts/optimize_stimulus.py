#!/usr/bin/env python3
"""
optimize_stimulus.py — Greedy stimulus optimization using TRIBE v2

Maximizes predicted activation in a target cortical region by iteratively
generating and evaluating stimulus perturbations.

Usage:
    python optimize_stimulus.py \
        --input path/to/base_stimulus.mp4 \
        --target-region visual \
        --modality video \
        --n-variants 10 \
        --output-dir ./optimized/

Supported target regions: visual, auditory, language, motion, default_mode
Supported modalities: video, audio, text
"""

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Cortical region vertex map (fsaverage5, ~20k vertices)
# These are approximate ranges derived from published parcellations.
# For production use, replace with exact parcellation indices from
# a registered fsaverage5 atlas (e.g., HCP MMP1.0, Glasser 2016).
# ---------------------------------------------------------------------------

REGION_VERTEX_MAP: Dict[str, List[int]] = {
    "visual": list(range(1000, 7000)),        # V1–V4 + MT/V5
    "auditory": list(range(8000, 13000)),     # A1 + belt + STS
    "language": list(range(15000, 18500)),    # Broca's + Wernicke's (LH approx)
    "motion": list(range(5500, 7000)),        # MT/V5 specifically
    "default_mode": list(range(19000, 20000)), # mPFC/PCC/angular gyrus
}

VALID_REGIONS = list(REGION_VERTEX_MAP.keys())
VALID_MODALITIES = ["video", "audio", "text"]


def get_region_vertices(region: str) -> List[int]:
    """
    Return approximate fsaverage5 vertex indices for a named cortical region.

    Args:
        region: One of 'visual', 'auditory', 'language', 'motion', 'default_mode'

    Returns:
        List of vertex indices (integers) for that region

    Raises:
        ValueError: If region name is not recognized
    """
    region = region.lower().strip()
    if region not in REGION_VERTEX_MAP:
        raise ValueError(
            f"Unknown region '{region}'. "
            f"Valid options: {', '.join(VALID_REGIONS)}"
        )
    return REGION_VERTEX_MAP[region]


def load_model(cache_folder: str = "./cache"):
    """Load TRIBE v2 model, downloading weights on first call."""
    try:
        from tribev2 import TribeModel  # type: ignore[import-untyped]
    except ImportError:
        print("ERROR: tribev2 not installed.")
        print("Install with: git clone https://github.com/facebookresearch/tribev2 && cd tribev2 && pip install -e .")
        sys.exit(1)

    print(f"Loading TRIBE v2 model (cache: {cache_folder})...")
    model = TribeModel.from_pretrained("facebook/tribev2", cache_folder=cache_folder)
    print("Model loaded.")
    return model


def predict_region_activation(
    model,
    file_path: str,
    modality: str,
    region_vertices: List[int],
) -> Tuple[float, np.ndarray]:
    """
    Run TRIBE v2 prediction and compute mean activation for a cortical region.

    Args:
        model: Loaded TribeModel instance
        file_path: Path to stimulus file
        modality: 'video', 'audio', or 'text'
        region_vertices: List of vertex indices to average over

    Returns:
        (region_mean_activation, full_preds_array)
    """
    if modality == "video":
        df = model.get_events_dataframe(video_path=file_path)
    elif modality == "audio":
        df = model.get_events_dataframe(audio_path=file_path)
    elif modality == "text":
        df = model.get_events_dataframe(text_path=file_path)
    else:
        raise ValueError(f"Unknown modality: {modality}")

    preds, _ = model.predict(events=df)

    # Guard against vertex indices exceeding prediction dimensionality
    n_vertices = preds.shape[1]
    valid_verts = [v for v in region_vertices if v < n_vertices]
    if len(valid_verts) == 0:
        raise ValueError(
            f"No valid vertices found. Prediction has {n_vertices} vertices "
            f"but requested range starts at {min(region_vertices)}."
        )

    region_act = float(preds[:, valid_verts].mean())
    return region_act, preds


def generate_video_variants(
    input_path: str,
    output_dir: str,
    n_variants: int,
) -> List[str]:
    """
    Generate video variants via brightness/contrast/saturation/speed perturbations.
    Requires ffmpeg to be installed.

    Args:
        input_path: Path to input video file
        output_dir: Directory to write variant files
        n_variants: Number of variants to generate

    Returns:
        List of paths to generated variant files
    """
    try:
        import subprocess
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        if result.returncode != 0:
            raise RuntimeError("ffmpeg not found")
    except (FileNotFoundError, RuntimeError):
        print("WARNING: ffmpeg not found. Cannot generate video variants automatically.")
        print("Install ffmpeg: brew install ffmpeg  (macOS) or apt install ffmpeg (Linux)")
        return []

    import subprocess

    # Define perturbation parameter grid
    perturbation_params = []

    # Brightness variations: eq=brightness=-0.2 to +0.2
    for brightness in np.linspace(-0.2, 0.2, max(3, n_variants // 3)):
        perturbation_params.append({
            "type": "brightness",
            "value": round(float(brightness), 2),
            "filter": f"eq=brightness={brightness:.2f}",
        })

    # Contrast variations: eq=contrast=0.8 to 1.4
    for contrast in np.linspace(0.8, 1.4, max(3, n_variants // 3)):
        perturbation_params.append({
            "type": "contrast",
            "value": round(float(contrast), 2),
            "filter": f"eq=contrast={contrast:.2f}",
        })

    # Speed variations: setpts for video speed 0.85x to 1.15x
    for speed in [0.85, 0.9, 1.0, 1.1, 1.15]:
        pts_factor = round(1.0 / speed, 3)
        perturbation_params.append({
            "type": "speed",
            "value": speed,
            "filter": f"setpts={pts_factor}*PTS",
        })

    # Trim to requested number
    perturbation_params = perturbation_params[:n_variants]

    input_stem = Path(input_path).stem
    input_suffix = Path(input_path).suffix
    variant_paths = []

    for i, params in enumerate(perturbation_params):
        variant_name = f"{input_stem}_variant_{i:02d}_{params['type']}_{params['value']}{input_suffix}"
        variant_path = os.path.join(output_dir, variant_name)

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", params["filter"],
            "-c:a", "copy",
            variant_path,
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode == 0:
            variant_paths.append(variant_path)
            print(f"  Generated variant {i+1}/{len(perturbation_params)}: {params['type']}={params['value']}")
        else:
            print(f"  WARNING: Failed to generate variant {i+1}: {result.stderr.decode()[:200]}")

    return variant_paths


def generate_audio_variants(
    input_path: str,
    output_dir: str,
    n_variants: int,
) -> List[str]:
    """
    Generate audio variants via speed and pitch perturbations.
    Uses pydub if available, falls back to ffmpeg.

    Args:
        input_path: Path to input audio file
        output_dir: Directory to write variant files
        n_variants: Number of variants to generate

    Returns:
        List of paths to generated variant files
    """
    try:
        import subprocess
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        if result.returncode != 0:
            raise RuntimeError("ffmpeg not found")
    except (FileNotFoundError, RuntimeError):
        print("WARNING: ffmpeg not found. Cannot generate audio variants automatically.")
        return []

    import subprocess

    input_stem = Path(input_path).stem
    input_suffix = Path(input_path).suffix or ".wav"
    variant_paths = []

    # Speed variants: atempo filter (0.85x to 1.15x)
    speed_values = np.linspace(0.85, 1.15, min(n_variants, 7)).tolist()

    # Volume normalization variants
    volume_values = [0.8, 0.9, 1.0, 1.1, 1.2]

    all_params = (
        [{"type": "speed", "value": round(s, 2), "filter": f"atempo={s:.2f}"} for s in speed_values]
        + [{"type": "volume", "value": v, "filter": f"volume={v}"} for v in volume_values]
    )[:n_variants]

    for i, params in enumerate(all_params):
        variant_name = f"{input_stem}_variant_{i:02d}_{params['type']}_{params['value']}{input_suffix}"
        variant_path = os.path.join(output_dir, variant_name)

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-af", params["filter"],
            variant_path,
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0:
            variant_paths.append(variant_path)
            print(f"  Generated variant {i+1}/{len(all_params)}: {params['type']}={params['value']}")
        else:
            print(f"  WARNING: Failed to generate variant {i+1}: {result.stderr.decode()[:200]}")

    return variant_paths


def generate_text_suggestions(input_path: str, n_variants: int) -> None:
    """
    For text modality, TRIBE v2 cannot automatically mutate semantic content
    without risking unintended meaning changes. Print paraphrase suggestions
    for human review instead.

    Args:
        input_path: Path to input text file
        n_variants: Number of variants requested
    """
    with open(input_path, "r") as f:
        text = f.read()

    print("\n" + "=" * 60)
    print("TEXT MODALITY: Manual paraphrase required")
    print("=" * 60)
    print(f"Original text ({len(text)} chars):")
    print(text[:500] + ("..." if len(text) > 500 else ""))
    print()
    print(f"To optimize text for language network activation ({n_variants} variants requested),")
    print("consider these paraphrase dimensions:")
    print()
    print("  1. SYNTAX COMPLEXITY: Vary sentence length (short/medium/complex)")
    print("  2. VOCABULARY REGISTER: Formal vs. conversational tone")
    print("  3. ACTIVE VS PASSIVE: More active voice → stronger language network response")
    print("  4. CONCRETE VS ABSTRACT: Concrete nouns activate more cortical surface")
    print("  5. READING LEVEL: Flesch-Kincaid grade 6 vs 12 → different processing load")
    print("  6. NARRATIVE STRUCTURE: First-person vs third-person perspective")
    print()
    print("After creating variants, save each as a .txt file and re-run this script")
    print("with --input pointing to each variant file.")
    print("=" * 60 + "\n")


def score_variants(
    model,
    variant_paths: List[str],
    modality: str,
    region_vertices: List[int],
    target_region: str,
) -> List[Dict]:
    """
    Run TRIBE v2 prediction on all variants and return scored results.

    Args:
        model: Loaded TribeModel instance
        variant_paths: List of variant file paths
        modality: 'video', 'audio', or 'text'
        region_vertices: Vertex indices for target region
        target_region: Region name (for reporting)

    Returns:
        List of dicts with variant_file, target_region_mean_activation, rank
    """
    results = []

    for i, vpath in enumerate(variant_paths):
        print(f"  Scoring variant {i+1}/{len(variant_paths)}: {Path(vpath).name}")
        try:
            activation, _ = predict_region_activation(model, vpath, modality, region_vertices)
            results.append({
                "variant_file": vpath,
                "target_region": target_region,
                "target_region_mean_activation": activation,
            })
        except Exception as e:
            print(f"    WARNING: Failed to score {vpath}: {e}")

    # Sort by activation descending
    results.sort(key=lambda x: x["target_region_mean_activation"], reverse=True)

    # Add rank
    for rank, row in enumerate(results, start=1):
        row["rank"] = rank

    return results


def save_results_csv(results: List[Dict], output_path: str) -> None:
    """Save ranked results to CSV."""
    if not results:
        print("No results to save.")
        return

    fieldnames = ["rank", "variant_file", "target_region", "target_region_mean_activation"]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row[k] for k in fieldnames})

    print(f"Saved rankings CSV: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Greedy stimulus optimization using TRIBE v2 cortical predictions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Optimize a video for visual cortex activation
  python optimize_stimulus.py --input ad.mp4 --target-region visual --modality video --n-variants 10 --output-dir ./optimized/

  # Optimize audio for language network activation
  python optimize_stimulus.py --input narration.wav --target-region language --modality audio --n-variants 8 --output-dir ./optimized/

  # Text optimization (prints paraphrase suggestions)
  python optimize_stimulus.py --input script.txt --target-region language --modality text --n-variants 6 --output-dir ./optimized/

Available target regions: visual, auditory, language, motion, default_mode
        """,
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the base stimulus file (video, audio, or text)",
    )
    parser.add_argument(
        "--target-region",
        required=True,
        choices=VALID_REGIONS,
        help=f"Target cortical region to maximize. Options: {', '.join(VALID_REGIONS)}",
    )
    parser.add_argument(
        "--modality",
        required=True,
        choices=VALID_MODALITIES,
        help=f"Input modality. Options: {', '.join(VALID_MODALITIES)}",
    )
    parser.add_argument(
        "--n-variants",
        type=int,
        default=10,
        help="Number of stimulus variants to generate and evaluate (default: 10)",
    )
    parser.add_argument(
        "--output-dir",
        default="./optimized",
        help="Directory to save variants and results (default: ./optimized)",
    )
    parser.add_argument(
        "--cache-folder",
        default="./cache",
        help="Cache folder for TRIBE v2 model weights (default: ./cache)",
    )

    args = parser.parse_args()

    # Validate input file
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    # Create output directory
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nTRIBE v2 Stimulus Optimizer")
    print(f"=" * 50)
    print(f"Input:         {input_path}")
    print(f"Target region: {args.target_region}")
    print(f"Modality:      {args.modality}")
    print(f"N variants:    {args.n_variants}")
    print(f"Output dir:    {output_dir}")
    print(f"=" * 50 + "\n")

    # Handle text modality separately (no auto-perturbation)
    if args.modality == "text":
        generate_text_suggestions(str(input_path), args.n_variants)
        print("For text modality, create variants manually and re-run this script.")
        print("No predictions will be run on unmodified text.")
        sys.exit(0)

    # Load model
    model = load_model(cache_folder=args.cache_folder)

    # Get target region vertices
    region_vertices = get_region_vertices(args.target_region)
    print(f"Target region '{args.target_region}': {len(region_vertices)} vertices")

    # Predict baseline activation
    print(f"\nPredicting baseline activation for: {input_path.name}")
    try:
        baseline_activation, _ = predict_region_activation(
            model, str(input_path), args.modality, region_vertices
        )
        print(f"Baseline {args.target_region} activation: {baseline_activation:.6f}")
    except Exception as e:
        print(f"ERROR: Failed to predict baseline: {e}")
        sys.exit(1)

    # Generate variants
    print(f"\nGenerating {args.n_variants} stimulus variants...")
    if args.modality == "video":
        variant_paths = generate_video_variants(
            str(input_path), str(output_dir), args.n_variants
        )
    elif args.modality == "audio":
        variant_paths = generate_audio_variants(
            str(input_path), str(output_dir), args.n_variants
        )
    else:
        variant_paths = []

    if not variant_paths:
        print("WARNING: No variants were generated.")
        print("Check that ffmpeg is installed (brew install ffmpeg) and try again.")
        sys.exit(1)

    print(f"Generated {len(variant_paths)} variants.")

    # Score all variants
    print(f"\nScoring variants on '{args.target_region}' region...")
    results = score_variants(
        model, variant_paths, args.modality, region_vertices, args.target_region
    )

    if not results:
        print("ERROR: No variants could be scored.")
        sys.exit(1)

    # Save results
    csv_path = output_dir / "rankings.csv"
    save_results_csv(results, str(csv_path))

    # Print summary
    best = results[0]
    best_activation = best["target_region_mean_activation"]
    improvement_pct = ((best_activation - baseline_activation) / abs(baseline_activation) * 100
                       if baseline_activation != 0 else 0.0)

    print(f"\n{'=' * 50}")
    print(f"OPTIMIZATION RESULTS")
    print(f"{'=' * 50}")
    print(f"Baseline activation:     {baseline_activation:.6f}")
    print(f"Best variant activation: {best_activation:.6f}")
    print(f"Improvement:             {improvement_pct:+.1f}%")
    print(f"Best variant:            {Path(best['variant_file']).name}")
    print(f"")
    print(f"Top 3 variants by {args.target_region} activation:")
    for row in results[:3]:
        print(f"  Rank {row['rank']}: {Path(row['variant_file']).name} "
              f"(activation={row['target_region_mean_activation']:.6f})")
    print(f"\nFull rankings saved to: {csv_path}")

    if improvement_pct > 5:
        print(f"\nRECOMMENDATION: Use {Path(best['variant_file']).name}")
        print(f"  +{improvement_pct:.1f}% predicted {args.target_region} activation vs baseline.")
    elif improvement_pct > 0:
        print(f"\nNote: Marginal improvement ({improvement_pct:+.1f}%). Consider wider perturbation range.")
    else:
        print(f"\nNote: No variants outperformed baseline. Original stimulus may already be optimal.")
        print(f"Try with more variants (--n-variants 20) or different target region.")


if __name__ == "__main__":
    main()
