#!/usr/bin/env python3
"""
predict_brain.py — CLI wrapper for TRIBE v2 single-stimulus brain response prediction.

Usage:
    python predict_brain.py --input stimulus.mp4 --modality video --output results.csv
    python predict_brain.py --input speech.wav --modality audio --output results.csv
    python predict_brain.py --input transcript.txt --modality text --output results.csv

Output:
    CSV with columns: timestep, vertex_id, predicted_activation
    Prints top-5 most activated vertices at peak timestep to stdout.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


# fsaverage5 approximate vertex ranges for key regions
# Format: region_name -> (vertex_start, vertex_end, hemisphere)
BRAIN_REGIONS = {
    # Visual cortex — left hemisphere
    "V1_left":        (0,     1500,  "left"),
    "V2V3_left":      (1500,  2500,  "left"),
    "V4_ventral_left": (2500, 3000,  "left"),
    "MT_left":        (2800,  3200,  "left"),
    "LOC_left":       (4200,  5200,  "left"),
    "FFA_left":       (1100,  1600,  "left"),
    "PPA_left":       (1600,  2100,  "left"),
    "EBA_left":       (5200,  5700,  "left"),
    # Auditory cortex — left hemisphere
    "A1_left":        (3500,  4200,  "left"),
    "STS_left":       (4800,  5300,  "left"),
    # Language — left hemisphere
    "Broca_left":     (6200,  6800,  "left"),
    "Wernicke_left":  (5700,  6200,  "left"),
    "VWFA_left":      (7100,  7500,  "left"),
    # Default Mode Network — left hemisphere
    "mPFC_left":      (8000,  8600,  "left"),
    "PCC_left":       (9000,  9500,  "left"),
    # Motor/somatosensory — left hemisphere
    "M1_left":        (8600,  9000,  "left"),
    "S1_left":        (9100,  9600,  "left"),
    # Visual cortex — right hemisphere (offset by 10242)
    "V1_right":       (10242, 11742, "right"),
    "MT_right":       (13042, 13442, "right"),
    "LOC_right":      (14442, 15442, "right"),
    "FFA_right":      (9900,  10400, "right"),   # fusiform, measured in combined array
    "PPA_right":      (10400, 11000, "right"),
    "EBA_right":      (15442, 15942, "right"),
    # Auditory cortex — right hemisphere
    "A1_right":       (13742, 14442, "right"),
    "STS_right":      (15000, 15500, "right"),
    # Language — right hemisphere (typically weaker)
    "Broca_right":    (16442, 17042, "right"),
    "Wernicke_right": (15942, 16442, "right"),
    # Default Mode Network — right hemisphere
    "mPFC_right":     (18200, 18800, "right"),
    "PCC_right":      (19200, 19700, "right"),
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

    print(f"Loading TRIBE v2 from HuggingFace (cache: {cache_dir}) ...")
    model = TribeModel.from_pretrained("facebook/tribev2", cache_folder=cache_dir)
    print("Model loaded.")
    return model


def build_events_dataframe(model, input_path: str, modality: str):
    """Build the events DataFrame from a stimulus file."""
    p = Path(input_path)
    if not p.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    modality = modality.lower()
    if modality == "video":
        return model.get_events_dataframe(video_path=str(p))
    elif modality == "audio":
        return model.get_events_dataframe(audio_path=str(p))
    elif modality == "text":
        return model.get_events_dataframe(text_path=str(p))
    else:
        print(f"ERROR: Unknown modality '{modality}'. Use: video, audio, text", file=sys.stderr)
        sys.exit(1)


def predictions_to_long_df(preds: np.ndarray) -> pd.DataFrame:
    """
    Convert (n_timesteps, n_vertices) prediction array to long-format DataFrame.

    Returns DataFrame with columns: timestep, vertex_id, predicted_activation
    This is memory-intensive for long stimuli. For very long predictions,
    consider saving only peak timestep or region summaries instead.
    """
    n_timesteps, n_vertices = preds.shape

    # Build arrays directly to avoid cartesian product memory issues
    timestep_ids = np.repeat(np.arange(n_timesteps), n_vertices)
    vertex_ids   = np.tile(np.arange(n_vertices), n_timesteps)
    activations  = preds.ravel()

    df = pd.DataFrame({
        "timestep":             timestep_ids,
        "vertex_id":            vertex_ids,
        "predicted_activation": activations,
    })
    return df


def print_top_vertices(preds: np.ndarray, n_top: int = 5):
    """Print summary of top activated vertices at peak timestep."""
    # Find peak timestep (highest mean activation across cortex)
    mean_per_timestep = preds.mean(axis=1)
    peak_t = int(np.argmax(mean_per_timestep))
    peak_activations = preds[peak_t, :]

    print(f"\n--- Peak Timestep: {peak_t} (~{peak_t * 1.5:.1f}s into stimulus) ---")
    print(f"Mean cortical activation at peak: {mean_per_timestep[peak_t]:.4f}")
    print(f"\nTop {n_top} most activated vertices at peak:")
    print(f"  {'Rank':<5}  {'Vertex':>8}  {'Activation':>12}  {'Region'}")
    print(f"  {'-'*5}  {'-'*8}  {'-'*12}  {'-'*20}")

    top_verts = np.argsort(peak_activations)[-n_top:][::-1]
    for rank, vert in enumerate(top_verts, start=1):
        activation = peak_activations[vert]
        # Find the region this vertex falls in
        region_label = "unknown"
        for region_name, (v_start, v_end, _) in BRAIN_REGIONS.items():
            if v_start <= vert < v_end:
                region_label = region_name
                break
        print(f"  {rank:<5}  {vert:>8}  {activation:>12.4f}  {region_label}")

    print(f"\nRegion summary at peak timestep:")
    print(f"  {'Region':<25}  {'Mean Activation':>16}")
    print(f"  {'-'*25}  {'-'*16}")
    for region_name, (v_start, v_end, _) in sorted(BRAIN_REGIONS.items()):
        region_mean = peak_activations[v_start:v_end].mean()
        if abs(region_mean) > 0.1:  # only print non-trivial activations
            print(f"  {region_name:<25}  {region_mean:>16.4f}")


def save_predictions(preds: np.ndarray, output_path: str):
    """Save predictions to CSV. Warns if file will be large."""
    n_timesteps, n_vertices = preds.shape
    n_rows = n_timesteps * n_vertices
    estimated_mb = n_rows * 3 * 8 / 1e6  # rough estimate: 3 cols × 8 bytes

    print(f"\nPrediction shape: {preds.shape}")
    print(f"Output rows: {n_rows:,}  (~{estimated_mb:.0f} MB estimated)")

    if n_rows > 5_000_000:
        print("WARNING: Large output. Consider using --region to filter, or reducing stimulus length.")

    print(f"Saving to {output_path} ...")
    df = predictions_to_long_df(preds)

    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path_obj, index=False)
    print(f"Saved {len(df):,} rows to {output_path_obj}")


def main():
    parser = argparse.ArgumentParser(
        description="TRIBE v2 brain response prediction for a single stimulus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python predict_brain.py --input clip.mp4 --modality video --output out.csv
  python predict_brain.py --input speech.wav --modality audio --output out.csv
  python predict_brain.py --input story.txt --modality text --output out.csv --cache-dir /tmp/tribe2
        """,
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to input stimulus file (video .mp4, audio .wav, or text .txt)",
    )
    parser.add_argument(
        "--modality", required=True, choices=["video", "audio", "text"],
        help="Modality of the input file",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to output CSV file (columns: timestep, vertex_id, predicted_activation)",
    )
    parser.add_argument(
        "--cache-dir", default="./tribe2-cache",
        help="Directory to cache downloaded model weights (default: ./tribe2-cache)",
    )
    parser.add_argument(
        "--top-n", type=int, default=5,
        help="Number of top vertices to print at peak timestep (default: 5)",
    )
    args = parser.parse_args()

    # Load model
    model = load_model(args.cache_dir)

    # Build events DataFrame
    print(f"Processing {args.modality} input: {args.input}")
    events_df = build_events_dataframe(model, args.input, args.modality)
    print(f"Events DataFrame shape: {events_df.shape}")

    # Predict
    print("Running prediction ...")
    preds, segments = model.predict(events=events_df)
    print(f"Prediction complete. Shape: {preds.shape}")

    if segments:
        print(f"Detected segments: {len(segments)}")
        for i, seg in enumerate(segments[:5]):
            print(f"  Segment {i}: {seg}")
        if len(segments) > 5:
            print(f"  ... and {len(segments) - 5} more")

    # Print top vertices
    print_top_vertices(preds, n_top=args.top_n)

    # Save output
    save_predictions(preds, args.output)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
