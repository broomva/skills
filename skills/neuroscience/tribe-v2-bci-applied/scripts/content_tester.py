#!/usr/bin/env python3
"""
content_tester.py — Batch content testing and engagement ranking using TRIBE v2

Tests a folder of media files and ranks them by predicted neural engagement
across specified cortical regions. Outputs a CSV with per-region scores.

Usage:
    python content_tester.py \
        --input-dir ./ad_variants/ \
        --modality video \
        --regions visual,auditory,language \
        --output engagement_rankings.csv

Supported modalities: video, audio, text
Supported regions: visual, auditory, language, motion, default_mode
                   (any combination as comma-separated list)
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Dict, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Cortical region vertex map (fsaverage5, ~20k vertices)
# Approximate ranges from published parcellations.
# ---------------------------------------------------------------------------

REGION_VERTEX_MAP: Dict[str, List[int]] = {
    "visual": list(range(1000, 7000)),         # V1–V4 + MT/V5
    "auditory": list(range(8000, 13000)),      # A1 + belt + STS
    "language": list(range(15000, 18500)),     # Broca's + Wernicke's (LH approx)
    "motion": list(range(5500, 7000)),         # MT/V5 specifically
    "default_mode": list(range(19000, 20000)), # mPFC/PCC/angular gyrus
}

VALID_REGIONS = list(REGION_VERTEX_MAP.keys())
VALID_MODALITIES = ["video", "audio", "text"]

# File extensions per modality
MODALITY_EXTENSIONS: Dict[str, List[str]] = {
    "video": [".mp4", ".avi", ".mov", ".mkv", ".webm"],
    "audio": [".wav", ".mp3", ".flac", ".aac", ".ogg", ".m4a"],
    "text": [".txt", ".md", ".rst"],
}


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
    print("Model loaded.\n")
    return model


def get_valid_files(input_dir: str, modality: str) -> List[str]:
    """
    Collect all files in input_dir with extensions matching the modality.

    Args:
        input_dir: Directory path to scan
        modality: 'video', 'audio', or 'text'

    Returns:
        Sorted list of absolute file paths
    """
    input_path = Path(input_dir)
    if not input_path.exists():
        print(f"ERROR: Input directory not found: {input_path}")
        sys.exit(1)
    if not input_path.is_dir():
        print(f"ERROR: Path is not a directory: {input_path}")
        sys.exit(1)

    valid_exts = set(MODALITY_EXTENSIONS.get(modality, []))
    files = [
        str(f.resolve())
        for f in sorted(input_path.iterdir())
        if f.is_file() and f.suffix.lower() in valid_exts
    ]

    return files


def predict_file_activations(
    model,
    file_path: str,
    modality: str,
    regions: List[str],
) -> Optional[Dict[str, float]]:
    """
    Run TRIBE v2 prediction for a single file and compute mean activation
    per requested region.

    Args:
        model: Loaded TribeModel instance
        file_path: Path to stimulus file
        modality: 'video', 'audio', or 'text'
        regions: List of region names to score

    Returns:
        Dict mapping region name -> mean activation float,
        or None if prediction failed
    """
    try:
        if modality == "video":
            df = model.get_events_dataframe(video_path=file_path)
        elif modality == "audio":
            df = model.get_events_dataframe(audio_path=file_path)
        elif modality == "text":
            df = model.get_events_dataframe(text_path=file_path)
        else:
            raise ValueError(f"Unknown modality: {modality}")

        preds, _ = model.predict(events=df)

    except Exception as e:
        print(f"  ERROR predicting {Path(file_path).name}: {e}")
        return None

    n_vertices = preds.shape[1]
    region_scores = {}

    for region in regions:
        if region not in REGION_VERTEX_MAP:
            print(f"  WARNING: Unknown region '{region}', skipping.")
            region_scores[region] = float("nan")
            continue

        raw_verts = REGION_VERTEX_MAP[region]
        valid_verts = [v for v in raw_verts if v < n_vertices]

        if not valid_verts:
            print(f"  WARNING: No valid vertices for region '{region}' "
                  f"(model has {n_vertices} vertices, region starts at {min(raw_verts)}).")
            region_scores[region] = float("nan")
        else:
            region_scores[region] = float(preds[:, valid_verts].mean())

    return region_scores


def compute_engagement_score(region_scores: Dict[str, float]) -> float:
    """
    Compute overall engagement score as mean across all non-NaN region scores.

    Args:
        region_scores: Dict mapping region name -> activation float

    Returns:
        Mean activation across all valid regions (float)
    """
    valid_scores = [v for v in region_scores.values() if not (isinstance(v, float) and v != v)]  # filter NaN
    if not valid_scores:
        return float("nan")
    return float(np.mean(valid_scores))


def save_results_csv(results: List[Dict], regions: List[str], output_path: str) -> None:
    """
    Save ranked results to CSV.

    Args:
        results: List of result dicts (already sorted descending by engagement)
        regions: List of region names (determines CSV columns)
        output_path: Output CSV file path
    """
    fieldnames = ["rank", "filename"] + [f"{r}_mean" for r in regions] + ["overall_engagement_score"]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            csv_row = {
                "rank": row["rank"],
                "filename": row["filename"],
                "overall_engagement_score": f"{row['overall_engagement_score']:.6f}",
            }
            for r in regions:
                val = row.get(f"{r}_mean", float("nan"))
                csv_row[f"{r}_mean"] = f"{val:.6f}" if val == val else "nan"  # nan check
            writer.writerow(csv_row)

    print(f"\nResults saved to: {output_path}")


def print_top_results(results: List[Dict], regions: List[str], top_n: int = 3) -> None:
    """Print the top N most engaging files to console."""
    print(f"\n{'=' * 60}")
    print(f"TOP {min(top_n, len(results))} MOST ENGAGING FILES")
    print(f"{'=' * 60}")

    for row in results[:top_n]:
        print(f"\n  #{row['rank']}: {row['filename']}")
        print(f"    Overall engagement score: {row['overall_engagement_score']:.6f}")
        for r in regions:
            val = row.get(f"{r}_mean", float("nan"))
            val_str = f"{val:.6f}" if val == val else "nan"
            print(f"    {r:20s}: {val_str}")

    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(
        description="Batch content engagement testing using TRIBE v2 neural predictions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Rank all videos by visual + auditory + language engagement
  python content_tester.py --input-dir ./videos/ --modality video --regions visual,auditory,language --output results.csv

  # Rank audio files by auditory and language activation only
  python content_tester.py --input-dir ./audio_clips/ --modality audio --regions auditory,language --output audio_results.csv

  # Rank text variants by language and default_mode activation
  python content_tester.py --input-dir ./text_variants/ --modality text --regions language,default_mode --output text_results.csv

Available regions: visual, auditory, language, motion, default_mode
        """,
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing media files to test",
    )
    parser.add_argument(
        "--modality",
        required=True,
        choices=VALID_MODALITIES,
        help=f"Input modality for all files. Options: {', '.join(VALID_MODALITIES)}",
    )
    parser.add_argument(
        "--regions",
        default="visual,auditory,language",
        help=(
            "Comma-separated list of cortical regions to score. "
            f"Options: {', '.join(VALID_REGIONS)}. "
            "Default: visual,auditory,language"
        ),
    )
    parser.add_argument(
        "--output",
        default="engagement_rankings.csv",
        help="Output CSV file path (default: engagement_rankings.csv)",
    )
    parser.add_argument(
        "--cache-folder",
        default="./cache",
        help="Cache folder for TRIBE v2 model weights (default: ./cache)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="Number of top results to print to console (default: 3)",
    )

    args = parser.parse_args()

    # Parse and validate regions
    requested_regions = [r.strip().lower() for r in args.regions.split(",") if r.strip()]
    unknown_regions = [r for r in requested_regions if r not in VALID_REGIONS]
    if unknown_regions:
        print(f"ERROR: Unknown regions: {', '.join(unknown_regions)}")
        print(f"Valid options: {', '.join(VALID_REGIONS)}")
        sys.exit(1)

    if not requested_regions:
        print("ERROR: No valid regions specified.")
        sys.exit(1)

    # Collect input files
    files = get_valid_files(args.input_dir, args.modality)

    if not files:
        valid_exts = MODALITY_EXTENSIONS.get(args.modality, [])
        print(f"ERROR: No {args.modality} files found in {args.input_dir}")
        print(f"Expected extensions: {', '.join(valid_exts)}")
        sys.exit(1)

    print(f"\nTRIBE v2 Content Tester")
    print(f"{'=' * 50}")
    print(f"Input directory: {args.input_dir}")
    print(f"Modality:        {args.modality}")
    print(f"Regions:         {', '.join(requested_regions)}")
    print(f"Files found:     {len(files)}")
    print(f"Output CSV:      {args.output}")
    print(f"{'=' * 50}\n")

    # Load model once
    model = load_model(cache_folder=args.cache_folder)

    # Process each file
    results = []

    for i, file_path in enumerate(files):
        filename = Path(file_path).name
        print(f"[{i+1}/{len(files)}] Processing: {filename}")

        region_scores = predict_file_activations(model, file_path, args.modality, requested_regions)

        if region_scores is None:
            print(f"  SKIPPED (prediction failed)")
            continue

        engagement_score = compute_engagement_score(region_scores)

        row = {
            "filename": filename,
            "overall_engagement_score": engagement_score,
        }
        for r in requested_regions:
            row[f"{r}_mean"] = region_scores.get(r, float("nan"))

        results.append(row)

        # Print inline summary
        scores_str = " | ".join(
            f"{r}={region_scores.get(r, float('nan')):.4f}" for r in requested_regions
        )
        print(f"  Engagement={engagement_score:.4f} | {scores_str}")

    if not results:
        print("\nERROR: No files were successfully processed.")
        sys.exit(1)

    # Sort by overall engagement descending
    results.sort(key=lambda x: x["overall_engagement_score"], reverse=True)

    # Add rank
    for rank, row in enumerate(results, start=1):
        row["rank"] = rank

    # Print top results
    print_top_results(results, requested_regions, top_n=args.top_n)

    # Save to CSV
    save_results_csv(results, requested_regions, args.output)

    print(f"\nProcessed {len(results)}/{len(files)} files successfully.")
    print(f"Top file: {results[0]['filename']} (score={results[0]['overall_engagement_score']:.4f})")

    if len(results) < len(files):
        n_failed = len(files) - len(results)
        print(f"WARNING: {n_failed} file(s) failed to process. Check error messages above.")


if __name__ == "__main__":
    main()
