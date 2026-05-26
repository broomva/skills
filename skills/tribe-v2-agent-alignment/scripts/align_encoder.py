#!/usr/bin/env python3
"""
align_encoder.py -- Compute cortical alignment score for any HuggingFace encoder
using TRIBE v2 as the ground-truth cortical predictor.

Methodology:
1. Load the target encoder (text/video/audio).
2. Load TRIBE v2 to predict cortical responses to the same stimuli.
3. Extract encoder hidden states and TRIBE v2 cortical predictions for each stimulus.
4. Fit a ridge regression probe: encoder hidden states -> TRIBE v2 predictions (modality ROI).
5. Report R-squared as the alignment score.

Usage:
    python align_encoder.py \
        --encoder-type text \
        --encoder-model meta-llama/Llama-3.2-3B \
        --stimulus-dir ./stimuli \
        --output ./results/alignment.json
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cortical region vertex ranges on fsaverage5 (~20k vertices total)
# Based on standard atlas parcellations; left hemisphere offsets used here.
# ---------------------------------------------------------------------------
CORTICAL_ROI = {
    "text": {
        "label": "language_cortex",
        "vertex_start": 12000,
        "vertex_end": 18000,
        "description": "Broca + Wernicke areas, left hemisphere",
    },
    "video": {
        "label": "visual_cortex",
        "vertex_start": 1000,
        "vertex_end": 8000,
        "description": "V1-V4 + MT/MST motion areas",
    },
    "audio": {
        "label": "auditory_cortex",
        "vertex_start": 8000,
        "vertex_end": 11000,
        "description": "Primary + belt auditory cortex, bilateral",
    },
}

SUPPORTED_ENCODER_TYPES = ("text", "video", "audio")
TEXT_EXTENSIONS = {".txt", ".md"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg"}

EXTENSION_MAP = {
    "text": TEXT_EXTENSIONS,
    "video": VIDEO_EXTENSIONS,
    "audio": AUDIO_EXTENSIONS,
}

# Approximate fsaverage5 region boundaries for top-region labeling
REGION_ATLAS = [
    (1000, 3000, "V1/V2"),
    (3000, 5000, "V3/V4"),
    (5000, 8000, "MT/MST_motion"),
    (8000, 10000, "primary_auditory"),
    (10000, 11000, "auditory_belt"),
    (11000, 13000, "posterior_STG"),
    (13000, 15000, "Wernicke"),
    (15000, 18000, "Broca"),
    (18000, 20000, "parietal_association"),
]


# ---------------------------------------------------------------------------
# Stimulus discovery
# ---------------------------------------------------------------------------

def discover_stimuli(stimulus_dir: Path, encoder_type: str) -> list:
    """Return all stimulus files of the appropriate type from stimulus_dir."""
    valid_exts = EXTENSION_MAP[encoder_type]
    files = [
        p for p in stimulus_dir.iterdir()
        if p.is_file() and p.suffix.lower() in valid_exts
    ]
    if not files:
        raise FileNotFoundError(
            "No {} stimuli found in {}. Expected extensions: {}".format(
                encoder_type, stimulus_dir, sorted(valid_exts)
            )
        )
    files.sort()
    log.info("Found %d %s stimulus file(s) in %s", len(files), encoder_type, stimulus_dir)
    return files


# ---------------------------------------------------------------------------
# TRIBE v2 cortical predictions
# ---------------------------------------------------------------------------

def load_tribe_model(cache_folder: str = "./cache"):
    """Load TRIBE v2 from HuggingFace (downloads on first call, ~10 GB)."""
    try:
        from tribev2 import TribeModel  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "tribev2 package not found. Install with: pip install tribev2"
        ) from exc

    log.info("Loading TRIBE v2 from facebook/tribev2 (may download ~10 GB on first run)...")
    model = TribeModel.from_pretrained("facebook/tribev2", cache_folder=cache_folder)
    log.info("TRIBE v2 loaded.")
    return model


def get_tribe_predictions(tribe_model, stimuli: list, encoder_type: str, roi: dict) -> np.ndarray:
    """
    Run TRIBE v2 on all stimuli and return mean ROI activation per stimulus.

    Returns
    -------
    np.ndarray of shape (n_stimuli, n_vertices_in_roi)
    """
    roi_slice = slice(roi["vertex_start"], roi["vertex_end"])
    all_preds = []

    for stimulus_path in stimuli:
        log.info("TRIBE v2 predicting for: %s", stimulus_path.name)
        kwargs = {}
        if encoder_type == "text":
            kwargs["text_path"] = str(stimulus_path)
        elif encoder_type == "video":
            kwargs["video_path"] = str(stimulus_path)
        elif encoder_type == "audio":
            kwargs["audio_path"] = str(stimulus_path)

        events_df = tribe_model.get_events_dataframe(**kwargs)
        preds, _segments = tribe_model.predict(events=events_df)
        # preds: (n_timesteps, n_vertices) -- mean over time for a single stimulus
        stimulus_mean = np.mean(preds, axis=0)  # (n_vertices,)
        all_preds.append(stimulus_mean[roi_slice])

    return np.vstack(all_preds)  # (n_stimuli, n_roi_vertices)


# ---------------------------------------------------------------------------
# Encoder hidden state extraction
# ---------------------------------------------------------------------------

def extract_text_hidden_states(model_id: str, stimuli: list) -> np.ndarray:
    """Extract mean-pooled last-layer hidden states from a HuggingFace text model."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    log.info("Loading text encoder: %s", model_id)
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_id, trust_remote_code=True, output_hidden_states=True
    )
    model.eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    log.info("Text encoder loaded on %s.", device)

    all_states = []
    for path in stimuli:
        text = path.read_text(encoding="utf-8").strip()
        inputs = tokenizer(
            text, return_tensors="pt", truncation=True, max_length=512
        ).to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        # Use last hidden state, mean-pool over token dimension
        last_hidden = outputs.last_hidden_state  # (1, seq_len, hidden_dim)
        pooled = last_hidden.mean(dim=1).squeeze(0).cpu().numpy()  # (hidden_dim,)
        all_states.append(pooled)

    return np.vstack(all_states)  # (n_stimuli, hidden_dim)


def _sample_video_frames(path: Path, n_frames: int = 16) -> list:
    """Sample n_frames uniformly from a video file using OpenCV."""
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "OpenCV not found. Install with: pip install opencv-python-headless"
        ) from exc

    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        raise ValueError("Could not read frames from {}".format(path))

    indices = np.linspace(0, total - 1, n_frames, dtype=int)
    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret:
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()

    if not frames:
        raise ValueError("No frames could be decoded from {}".format(path))
    return frames


def extract_video_hidden_states(model_id: str, stimuli: list) -> np.ndarray:
    """
    Extract mean-pooled visual features from a video/image encoder.

    For video inputs, uniformly sample frames and run the image encoder on each,
    then average. Supports CLIP-style models via transformers and V-JEPA2 via its API.
    """
    import torch

    all_states = []

    # Try V-JEPA2 first if model_id indicates it
    if "vjepa" in model_id.lower():
        try:
            from vjepa2 import VJEPA2  # type: ignore

            log.info("Loading V-JEPA2 encoder: %s", model_id)
            vjepa = VJEPA2.from_pretrained(model_id)
            vjepa.eval()
            device = "cuda" if torch.cuda.is_available() else "cpu"
            vjepa.to(device)

            for path in stimuli:
                log.info("V-JEPA2 encoding: %s", path.name)
                features = vjepa.encode_video(str(path))  # (T, D) or (D,)
                if hasattr(features, "ndim") and features.ndim == 2:
                    features = features.mean(axis=0)
                all_states.append(np.array(features))
            return np.vstack(all_states)
        except ImportError:
            log.warning("vjepa2 package not available; falling back to CLIP-style extraction.")

    # General CLIP / ViT approach via transformers
    from transformers import CLIPModel, CLIPProcessor, AutoFeatureExtractor, AutoModel

    log.info("Loading video/image encoder via transformers: %s", model_id)
    model = None
    processor = None
    use_clip = False
    try:
        processor = CLIPProcessor.from_pretrained(model_id)
        model = CLIPModel.from_pretrained(model_id)
        use_clip = True
    except Exception:
        processor = AutoFeatureExtractor.from_pretrained(model_id, trust_remote_code=True)
        model = AutoModel.from_pretrained(model_id, trust_remote_code=True)

    model.eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    from PIL import Image

    for path in stimuli:
        log.info("Encoding video frames from: %s", path.name)
        frames = _sample_video_frames(path, n_frames=16)
        frame_features = []
        for frame in frames:
            img = Image.fromarray(frame)
            if use_clip:
                inputs = processor(images=img, return_tensors="pt").to(device)
                with torch.no_grad():
                    feat = model.get_image_features(**inputs)  # (1, D)
            else:
                inputs = processor(images=img, return_tensors="pt").to(device)
                with torch.no_grad():
                    out = model(**inputs)
                feat = out.last_hidden_state.mean(dim=1)  # (1, D)
            frame_features.append(feat.squeeze(0).cpu().numpy())
        video_rep = np.mean(frame_features, axis=0)  # (D,)
        all_states.append(video_rep)

    return np.vstack(all_states)


def extract_audio_hidden_states(model_id: str, stimuli: list) -> np.ndarray:
    """Extract mean-pooled hidden states from a Wav2Vec-style audio encoder."""
    import torch
    from transformers import AutoProcessor, AutoModel

    log.info("Loading audio encoder: %s", model_id)
    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModel.from_pretrained(model_id)
    model.eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    log.info("Audio encoder loaded on %s.", device)

    all_states = []
    for path in stimuli:
        log.info("Encoding audio: %s", path.name)
        import soundfile as sf  # type: ignore
        waveform, sample_rate = sf.read(str(path))
        if waveform.ndim == 2:
            waveform = waveform.mean(axis=1)  # mix to mono
        inputs = processor(
            waveform, sampling_rate=sample_rate, return_tensors="pt", padding=True
        ).to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        last_hidden = outputs.last_hidden_state  # (1, T, D)
        pooled = last_hidden.mean(dim=1).squeeze(0).cpu().numpy()  # (D,)
        all_states.append(pooled)

    return np.vstack(all_states)


EXTRACTOR_MAP = {
    "text": extract_text_hidden_states,
    "video": extract_video_hidden_states,
    "audio": extract_audio_hidden_states,
}


# ---------------------------------------------------------------------------
# Ridge regression probe
# ---------------------------------------------------------------------------

def compute_alignment_score(
    encoder_states: np.ndarray,
    tribe_predictions: np.ndarray,
    n_splits: int = 5,
    alpha: float = 1.0,
) -> tuple:
    """
    Fit a ridge regression probe from encoder_states to tribe_predictions and
    return (mean_r2, per_vertex_r2) across cross-validation splits.

    Parameters
    ----------
    encoder_states   : (n_stimuli, encoder_dim)
    tribe_predictions: (n_stimuli, n_roi_vertices)
    n_splits         : number of cross-validation folds
    alpha            : Ridge regularization strength

    Returns
    -------
    mean_r2          : scalar float -- the alignment score
    per_vertex_r2    : (n_roi_vertices,) array
    """
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold
    from sklearn.preprocessing import StandardScaler

    n_stimuli = encoder_states.shape[0]
    if n_stimuli < n_splits:
        # Not enough stimuli for full CV; use simple 2-fold
        n_splits = max(2, n_stimuli // 2)
        log.warning(
            "Reduced CV splits to %d because only %d stimuli are available.", n_splits, n_stimuli
        )

    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
    scaler_X = StandardScaler()
    scaler_y = StandardScaler()

    all_r2_per_vertex = []

    for fold_idx, (train_idx, test_idx) in enumerate(kf.split(encoder_states)):
        X_train = scaler_X.fit_transform(encoder_states[train_idx])
        X_test = scaler_X.transform(encoder_states[test_idx])
        y_train = scaler_y.fit_transform(tribe_predictions[train_idx])
        y_test = scaler_y.transform(tribe_predictions[test_idx])

        ridge = Ridge(alpha=alpha, fit_intercept=True)
        ridge.fit(X_train, y_train)
        y_pred = ridge.predict(X_test)

        # Per-vertex R^2: 1 - SS_res / SS_tot
        ss_res = np.sum((y_test - y_pred) ** 2, axis=0)
        ss_tot = np.sum((y_test - y_test.mean(axis=0)) ** 2, axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            r2_vertex = np.where(ss_tot > 1e-10, 1.0 - ss_res / ss_tot, 0.0)
        all_r2_per_vertex.append(r2_vertex)
        log.info("Fold %d/%d mean R^2: %.4f", fold_idx + 1, n_splits, float(r2_vertex.mean()))

    per_vertex_r2 = np.mean(all_r2_per_vertex, axis=0)
    mean_r2 = float(np.mean(per_vertex_r2))
    return mean_r2, per_vertex_r2


# ---------------------------------------------------------------------------
# Top region identification
# ---------------------------------------------------------------------------

def vertex_to_region_label(vertex: int) -> str:
    """Approximate a cortical region name from a global fsaverage5 vertex index."""
    for start, end, label in REGION_ATLAS:
        if start <= vertex < end:
            return label
    return "other_cortex"


def identify_top_regions(per_vertex_r2: np.ndarray, roi: dict, top_k: int = 5) -> list:
    """
    Return the top_k vertices with highest alignment scores within the ROI.
    Each entry: {"vertex": int, "r2": float, "region": str}
    """
    offset = roi["vertex_start"]
    top_local_indices = np.argsort(per_vertex_r2)[::-1][:top_k]
    top_regions = []
    for local_idx in top_local_indices:
        global_vertex = int(offset + local_idx)
        r2_val = float(per_vertex_r2[local_idx])
        label = vertex_to_region_label(global_vertex)
        top_regions.append({"vertex": global_vertex, "r2": round(r2_val, 4), "region": label})
    return top_regions


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_alignment(
    encoder_type: str,
    encoder_model: str,
    stimulus_dir: Path,
    output_path: Path,
    tribe_cache: str = "./cache",
    ridge_alpha: float = 1.0,
    cv_splits: int = 5,
) -> dict:
    """Full alignment pipeline. Returns the results dict."""
    start_time = time.time()
    roi = CORTICAL_ROI[encoder_type]
    log.info("=== TRIBE v2 Cortical Alignment ===")
    log.info("Encoder type  : %s", encoder_type)
    log.info("Encoder model : %s", encoder_model)
    log.info("Stimulus dir  : %s", stimulus_dir)
    log.info("Target ROI    : %s (%s)", roi["label"], roi["description"])

    # 1. Discover stimuli
    stimuli = discover_stimuli(stimulus_dir, encoder_type)

    # 2. Extract encoder hidden states
    log.info("Extracting encoder hidden states...")
    extractor = EXTRACTOR_MAP[encoder_type]
    encoder_states = extractor(encoder_model, stimuli)
    log.info("Encoder states shape: %s", encoder_states.shape)

    # 3. Load TRIBE v2 and get cortical predictions
    log.info("Running TRIBE v2 cortical predictions...")
    tribe_model = load_tribe_model(cache_folder=tribe_cache)
    tribe_preds = get_tribe_predictions(tribe_model, stimuli, encoder_type, roi)
    log.info("TRIBE v2 predictions shape: %s", tribe_preds.shape)

    # 4. Compute alignment score via ridge regression probe
    log.info("Fitting ridge regression probe (alpha=%.3f, cv_splits=%d)...", ridge_alpha, cv_splits)
    mean_r2, per_vertex_r2 = compute_alignment_score(
        encoder_states, tribe_preds, n_splits=cv_splits, alpha=ridge_alpha
    )
    log.info("Alignment score (mean R-squared): %.4f", mean_r2)

    # 5. Identify top cortical regions
    top_regions = identify_top_regions(per_vertex_r2, roi, top_k=5)

    # 6. Interpret score
    if mean_r2 >= 0.40:
        interpretation = "excellent"
    elif mean_r2 >= 0.25:
        interpretation = "good"
    elif mean_r2 >= 0.10:
        interpretation = "moderate"
    else:
        interpretation = "poor"

    elapsed = time.time() - start_time
    results = {
        "encoder": encoder_model,
        "encoder_type": encoder_type,
        "modality": encoder_type,
        "alignment_score": round(mean_r2, 4),
        "interpretation": interpretation,
        "roi_label": roi["label"],
        "roi_description": roi["description"],
        "top_regions": top_regions,
        "n_stimuli": len(stimuli),
        "cv_splits": cv_splits,
        "ridge_alpha": ridge_alpha,
        "encoder_dim": int(encoder_states.shape[1]),
        "n_roi_vertices": int(tribe_preds.shape[1]),
        "elapsed_seconds": round(elapsed, 1),
        "tribe_model": "facebook/tribev2",
    }

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2))
    log.info("Results written to: %s", output_path)
    log.info("Final alignment score: %.4f (%s)", mean_r2, interpretation)

    return results


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="align_encoder",
        description=(
            "Compute cortical alignment score between an AI encoder and "
            "TRIBE v2 cortical predictions via ridge regression probe."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python align_encoder.py --encoder-type text --encoder-model meta-llama/Llama-3.2-3B \\
      --stimulus-dir ./stimuli/text --output ./results/llama_align.json

  python align_encoder.py --encoder-type video --encoder-model openai/clip-vit-large-patch14 \\
      --stimulus-dir ./stimuli/video --output ./results/clip_align.json

  python align_encoder.py --encoder-type audio --encoder-model facebook/w2v-bert-2.0 \\
      --stimulus-dir ./stimuli/audio --output ./results/wav2vec_align.json

Output JSON fields:
  encoder          - HuggingFace model ID
  modality         - text / video / audio
  alignment_score  - mean R-squared across CV folds (0.0 to 1.0)
  interpretation   - poor / moderate / good / excellent
  top_regions      - list of top-5 cortical vertices with highest alignment
  n_stimuli        - number of stimuli processed
""",
    )
    parser.add_argument(
        "--encoder-type",
        required=True,
        choices=SUPPORTED_ENCODER_TYPES,
        help="Modality of the encoder: text, video, or audio.",
    )
    parser.add_argument(
        "--encoder-model",
        required=True,
        help="HuggingFace model ID or local path of the encoder to benchmark.",
    )
    parser.add_argument(
        "--stimulus-dir",
        required=True,
        type=Path,
        help="Directory containing stimulus files (.txt/.mp4/.wav etc.).",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to write the JSON results file.",
    )
    parser.add_argument(
        "--tribe-cache",
        default="./cache",
        help="Directory to cache TRIBE v2 model weights (default: ./cache).",
    )
    parser.add_argument(
        "--ridge-alpha",
        type=float,
        default=1.0,
        help="Ridge regression regularization strength (default: 1.0).",
    )
    parser.add_argument(
        "--cv-splits",
        type=int,
        default=5,
        help="Number of cross-validation folds (default: 5).",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    stimulus_dir = Path(args.stimulus_dir).expanduser().resolve()
    if not stimulus_dir.exists():
        log.error("Stimulus directory not found: %s", stimulus_dir)
        sys.exit(1)

    output_path = Path(args.output).expanduser().resolve()

    try:
        results = run_alignment(
            encoder_type=args.encoder_type,
            encoder_model=args.encoder_model,
            stimulus_dir=stimulus_dir,
            output_path=output_path,
            tribe_cache=args.tribe_cache,
            ridge_alpha=args.ridge_alpha,
            cv_splits=args.cv_splits,
        )
        print(json.dumps(results, indent=2))
        sys.exit(0)
    except FileNotFoundError as exc:
        log.error("Input error: %s", exc)
        sys.exit(1)
    except ImportError as exc:
        log.error("Missing dependency: %s", exc)
        sys.exit(1)
    except Exception as exc:
        log.exception("Unexpected error: %s", exc)
        sys.exit(1)
