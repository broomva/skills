#!/usr/bin/env python3
"""
run_experiment.py — Batch stimulus experiment runner using TRIBE v2.

Runs TRIBE v2 on all stimuli in a directory, computes per-stimulus region-averaged
activations, and outputs a summary CSV for downstream analysis.

Usage:
    python run_experiment.py --stimuli-dir stimuli/faces/ --modality video --output-dir results/
    python run_experiment.py --stimuli-dir stimuli/ --modality video --output-dir results/ --region FFA_right
    python run_experiment.py --stimuli-dir stimuli/ --modality audio --output-dir results/ --list-regions

Output:
    <output-dir>/experiment_summary.csv
        Columns: stimulus_file, region, mean_activation, peak_activation,
                 peak_timestep, n_timesteps, n_vertices_in_region

    <output-dir>/activations/<stimulus_name>.npy  (optional, raw preds)
"""

import argparse
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd


# fsaverage5 cortical region definitions
# Format: region_name -> (vertex_start, vertex_end)
# All indices are into the combined (left+right hemisphere) array of 20,484 vertices
# Left hemisphere: 0–10,241  |  Right hemisphere: 10,242–20,483
BRAIN_REGIONS = {
    # ── Visual cortex ──────────────────────────────────────────────────────────
    "V1_left":            (0,     1500),
    "V2V3_left":          (1500,  2500),
    "V4_ventral_left":    (2500,  3000),
    "MT_left":            (2800,  3200),    # motion-selective
    "LOC_left":           (4200,  5200),    # lateral occipital complex
    "FFA_left":           (1100,  1600),    # fusiform face area (smaller, left)
    "PPA_left":           (1600,  2100),    # parahippocampal place area
    "EBA_left":           (5200,  5700),    # extrastriate body area
    "V1_right":           (10242, 11742),
    "MT_right":           (13042, 13442),
    "LOC_right":          (14442, 15442),
    "FFA_right":          (9900,  10400),   # dominant face region
    "PPA_right":          (10400, 11000),
    "EBA_right":          (15442, 15942),
    # ── Auditory cortex ────────────────────────────────────────────────────────
    "A1_left":            (3500,  4200),    # primary auditory cortex
    "belt_auditory_left": (4200,  4800),    # auditory belt (pitch, timbre)
    "STS_left":           (4800,  5300),    # superior temporal sulcus
    "A1_right":           (13742, 14442),
    "belt_auditory_right": (14442, 15000),
    "STS_right":          (15000, 15500),
    # ── Language network ───────────────────────────────────────────────────────
    "Broca_left":         (6200,  6800),    # IFG pars triangularis / opercularis
    "Wernicke_left":      (5700,  6200),    # posterior STG / MTG
    "VWFA_left":          (7100,  7500),    # visual word form area
    "Broca_right":        (16442, 17042),   # typically weaker
    "Wernicke_right":     (15942, 16442),
    # ── Default Mode Network ───────────────────────────────────────────────────
    "mPFC_left":          (8000,  8600),    # medial prefrontal cortex
    "PCC_left":           (9000,  9500),    # posterior cingulate cortex
    "angular_gyrus_left": (7500,  8000),
    "mPFC_right":         (18200, 18800),
    "PCC_right":          (19200, 19700),
    "angular_gyrus_right": (17700, 18200),
    # ── Motor / Somatosensory ──────────────────────────────────────────────────
    "M1_left":            (8600,  9000),    # primary motor cortex
    "S1_left":            (9100,  9600),    # primary somatosensory cortex
    "M1_right":           (18800, 19200),
    "S1_right":           (19200, 19600),
    # ── Prefrontal cortex ──────────────────────────────────────────────────────
    "DLPFC_left":         (6800,  7100),    # dorsolateral PFC
    "OFC_left":           (9600,  10000),   # orbitofrontal cortex
    "DLPFC_right":        (17042, 17342),
    "OFC_right":          (19600, 20000),
}

# File extensions that TRIBE v2 accepts per modality
MODALITY_EXTENSIONS = {
    "video": {".mp4", ".avi", ".mov", ".mkv", ".webm"},
    "audio": {".wav", ".flac", ".mp3", ".ogg"},
    "text":  {".txt", ".md", ".json"},
}


def load_model(cache_dir: str):
    """Load TRIBE v2 model from HuggingFace."""
    try:
        from tribev2 import TribeModel  # type: ignore[import-untyped]
    except ImportError:
        print("ERROR: tribev2 not installed.", file=sys.stderr)
        print("Install with:", file=sys.stderr)
        print("  git clone https://github.com/facebookresearch/tribev2", file=sys.stderr)
        print("  cd tribev2 && pip install -e .", file=sys.stderr)
        sys.exit(1)

    print(f"Loading TRIBE v2 (cache: {cache_dir}) ...")
    model = TribeModel.from_pretrained("facebook/tribev2", cache_folder=cache_dir)
    print("Model loaded.\n")
    return model


def get_stimuli_files(stimuli_dir: str, modality: str) -> list:
    """Return sorted list of stimulus files matching the modality."""
    d = Path(stimuli_dir)
    if not d.exists():
        print(f"ERROR: Stimuli directory not found: {stimuli_dir}", file=sys.stderr)
        sys.exit(1)

    valid_exts = MODALITY_EXTENSIONS.get(modality, set())
    files = sorted([f for f in d.iterdir() if f.is_file() and f.suffix.lower() in valid_exts])

    if not files:
        print(f"ERROR: No {modality} files found in {stimuli_dir}", file=sys.stderr)
        print(f"Expected extensions: {', '.join(sorted(valid_exts))}", file=sys.stderr)
        sys.exit(1)

    return files


def predict_stimulus(model, stimulus_path: Path, modality: str) -> tuple:
    """Run TRIBE v2 prediction on one stimulus. Returns (preds, segments)."""
    modality = modality.lower()
    if modality == "video":
        df = model.get_events_dataframe(video_path=str(stimulus_path))
    elif modality == "audio":
        df = model.get_events_dataframe(audio_path=str(stimulus_path))
    elif modality == "text":
        df = model.get_events_dataframe(text_path=str(stimulus_path))
    else:
        raise ValueError(f"Unknown modality: {modality}")

    preds, segments = model.predict(events=df)
    return preds, segments


def compute_region_stats(preds: np.ndarray, regions: dict) -> list:
    """
    Compute per-region activation statistics for one stimulus.

    Returns list of dicts with keys:
        region, mean_activation, peak_activation, peak_timestep, n_vertices_in_region
    """
    records = []
    for region_name, (v_start, v_end) in regions.items():
        # Guard against out-of-bounds
        actual_end = min(v_end, preds.shape[1])
        actual_start = min(v_start, preds.shape[1])
        if actual_start >= actual_end:
            continue

        roi_preds = preds[:, actual_start:actual_end]  # (n_timesteps, n_roi_vertices)
        roi_mean_over_time   = roi_preds.mean(axis=1)  # (n_timesteps,)
        peak_t               = int(np.argmax(roi_mean_over_time))
        mean_activation      = float(roi_mean_over_time.mean())
        peak_activation      = float(roi_mean_over_time[peak_t])

        records.append({
            "region":              region_name,
            "mean_activation":     mean_activation,
            "peak_activation":     peak_activation,
            "peak_timestep":       peak_t,
            "n_vertices_in_region": actual_end - actual_start,
        })

    return records


def save_raw_predictions(preds: np.ndarray, stimulus_path: Path, output_dir: Path):
    """Save raw (n_timesteps, n_vertices) predictions as .npy."""
    raw_dir = output_dir / "activations"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_file = raw_dir / f"{stimulus_path.stem}.npy"
    np.save(out_file, preds)
    return out_file


def main():
    parser = argparse.ArgumentParser(
        description="TRIBE v2 batch experiment: run predictions on a directory of stimuli.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all videos, output summary for all regions
  python run_experiment.py --stimuli-dir stimuli/ --modality video --output-dir results/

  # Filter to a specific region
  python run_experiment.py --stimuli-dir stimuli/ --modality video --output-dir results/ --region FFA_right

  # Run on audio, save raw predictions
  python run_experiment.py --stimuli-dir stimuli/ --modality audio --output-dir results/ --save-raw

  # List available regions
  python run_experiment.py --list-regions
        """,
    )
    parser.add_argument(
        "--stimuli-dir",
        help="Directory containing stimulus files (all files matching the modality are processed)",
    )
    parser.add_argument(
        "--modality", choices=["video", "audio", "text"],
        help="Stimulus modality",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for output files",
    )
    parser.add_argument(
        "--region", default=None,
        help=(
            "Optional: restrict output to a specific region name "
            "(e.g., FFA_right, Broca_left). Run --list-regions to see options."
        ),
    )
    parser.add_argument(
        "--cache-dir", default="./tribe2-cache",
        help="Directory to cache model weights (default: ./tribe2-cache)",
    )
    parser.add_argument(
        "--save-raw", action="store_true",
        help="Save raw (n_timesteps, n_vertices) .npy arrays for each stimulus",
    )
    parser.add_argument(
        "--list-regions", action="store_true",
        help="List all available region names and exit",
    )
    args = parser.parse_args()

    # Handle --list-regions
    if args.list_regions:
        print("Available regions (fsaverage5 vertex ranges):")
        print(f"\n  {'Region':<30}  {'Start':>8}  {'End':>8}  {'N vertices':>12}")
        print(f"  {'-'*30}  {'-'*8}  {'-'*8}  {'-'*12}")
        for name, (v_start, v_end) in sorted(BRAIN_REGIONS.items()):
            print(f"  {name:<30}  {v_start:>8}  {v_end:>8}  {v_end - v_start:>12}")
        return 0

    # Validate required args
    if not args.stimuli_dir or not args.modality or not args.output_dir:
        parser.error("--stimuli-dir, --modality, and --output-dir are required unless --list-regions is used")

    # Validate region filter
    if args.region and args.region not in BRAIN_REGIONS:
        print(f"ERROR: Unknown region '{args.region}'", file=sys.stderr)
        print(f"Run with --list-regions to see available regions.", file=sys.stderr)
        sys.exit(1)

    # Determine which regions to report
    if args.region:
        active_regions = {args.region: BRAIN_REGIONS[args.region]}
    else:
        active_regions = BRAIN_REGIONS

    # Discover stimuli
    stimulus_files = get_stimuli_files(args.stimuli_dir, args.modality)
    print(f"Found {len(stimulus_files)} {args.modality} file(s) in {args.stimuli_dir}")
    print(f"Reporting on {len(active_regions)} brain region(s)\n")

    # Prepare output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load model once
    model = load_model(args.cache_dir)

    # Run experiment
    all_results = []
    errors = []

    for i, stim_path in enumerate(stimulus_files, start=1):
        print(f"[{i}/{len(stimulus_files)}] Processing: {stim_path.name}")
        try:
            preds, segments = predict_stimulus(model, stim_path, args.modality)
            print(f"  Prediction shape: {preds.shape}")

            region_stats = compute_region_stats(preds, active_regions)
            for stat in region_stats:
                stat["stimulus_file"] = stim_path.name
            all_results.extend(region_stats)

            if args.save_raw:
                raw_path = save_raw_predictions(preds, stim_path, output_dir)
                print(f"  Raw saved: {raw_path}")

        except Exception as exc:
            print(f"  ERROR processing {stim_path.name}: {exc}", file=sys.stderr)
            errors.append({"stimulus_file": stim_path.name, "error": str(exc)})

    # Build summary DataFrame
    if not all_results:
        print("ERROR: No predictions succeeded.", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(all_results)
    # Reorder columns for clarity
    cols = ["stimulus_file", "region", "mean_activation", "peak_activation",
            "peak_timestep", "n_vertices_in_region"]
    df = df[cols]
    df = df.sort_values(["stimulus_file", "region"]).reset_index(drop=True)

    # Save summary CSV
    summary_path = output_dir / "experiment_summary.csv"
    df.to_csv(summary_path, index=False)
    print(f"\nSummary saved: {summary_path}  ({len(df):,} rows)")

    # Save errors if any
    if errors:
        error_path = output_dir / "errors.json"
        with open(error_path, "w") as f:
            json.dump(errors, f, indent=2)
        print(f"Errors ({len(errors)}): {error_path}")

    # Print pivot table for quick inspection
    print("\n--- Mean Activation by Stimulus × Region (top 10 regions by variance) ---")
    try:
        pivot = df.pivot_table(
            index="stimulus_file", columns="region",
            values="mean_activation", aggfunc="mean"
        )
        # Show only regions with highest variance across stimuli (most informative)
        region_variance = pivot.var(axis=0).nlargest(min(10, len(pivot.columns)))  # type: ignore[union-attr]
        pivot_display = pivot[region_variance.index]
        print(pivot_display.to_string(float_format=lambda x: f"{x:.4f}"))  # type: ignore[arg-type]
    except Exception:
        # Pivot may fail with single stimulus or single region; just skip
        print("(pivot table unavailable for this result shape)")

    print("\nExperiment complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
