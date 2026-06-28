#!/usr/bin/env bash
# setup-ltx.sh — Automated LTX-2.3 setup with model downloads
# Usage: bash scripts/setup-ltx.sh [--models-dir /path/to/models] [--variant dev|distilled|both]
set -euo pipefail

MODELS_DIR="${MODELS_DIR:-./models}"
VARIANT="${VARIANT:-both}"
HF_REPO="Lightricks/LTX-2.3"
REPO_URL="https://github.com/Lightricks/LTX-2.git"

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --models-dir) MODELS_DIR="$2"; shift 2 ;;
    --variant) VARIANT="$2"; shift 2 ;;
    --help)
      echo "Usage: setup-ltx.sh [--models-dir DIR] [--variant dev|distilled|both]"
      echo ""
      echo "Options:"
      echo "  --models-dir DIR    Where to download models (default: ./models)"
      echo "  --variant TYPE      dev, distilled, or both (default: both)"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

echo "=== LTX-2.3 Setup ==="
echo "Models directory: $MODELS_DIR"
echo "Variant: $VARIANT"
echo ""

# --- Prerequisites check ---
check_cmd() { command -v "$1" &>/dev/null || { echo "ERROR: $1 not found. Install it first."; exit 1; }; }
check_cmd git
check_cmd python3
check_cmd uv

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 12 ]]; then
  echo "ERROR: Python >= 3.12 required (found $PYTHON_VERSION)"
  exit 1
fi
echo "[OK] Python $PYTHON_VERSION"

if ! python3 -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
  echo "WARNING: CUDA not detected. LTX-2 requires a CUDA-compatible GPU."
  echo "         Proceeding with setup, but inference will fail without CUDA."
fi

# --- Clone repo ---
if [ ! -d "LTX-2" ]; then
  echo ""
  echo "=== Cloning LTX-2 repository ==="
  git clone "$REPO_URL"
fi

cd LTX-2

# --- Install dependencies ---
echo ""
echo "=== Installing dependencies with uv ==="
uv sync --frozen
echo "[OK] Dependencies installed"

# --- Download models ---
echo ""
echo "=== Downloading models ==="
mkdir -p "$MODELS_DIR"

# Check for huggingface-cli
if ! command -v huggingface-cli &>/dev/null; then
  echo "Installing huggingface_hub for model downloads..."
  uv pip install huggingface_hub[cli]
fi

download_model() {
  local filename="$1"
  local dest="$MODELS_DIR/$filename"
  if [ -f "$dest" ]; then
    echo "[SKIP] $filename already exists"
  else
    echo "[DOWNLOADING] $filename..."
    huggingface-cli download "$HF_REPO" "$filename" --local-dir "$MODELS_DIR"
    echo "[OK] $filename"
  fi
}

# Core models
if [[ "$VARIANT" == "dev" || "$VARIANT" == "both" ]]; then
  download_model "ltx-2.3-22b-dev.safetensors"
fi
if [[ "$VARIANT" == "distilled" || "$VARIANT" == "both" ]]; then
  download_model "ltx-2.3-22b-distilled.safetensors"
  download_model "ltx-2.3-22b-distilled-lora-384.safetensors"
fi

# Upscalers
download_model "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
download_model "ltx-2.3-temporal-upscaler-x2-1.0.safetensors"

# Text encoder (Gemma 3)
echo ""
echo "=== Downloading Gemma 3 text encoder ==="
if [ ! -d "$MODELS_DIR/gemma-3-12b" ]; then
  huggingface-cli download google/gemma-3-12b-it --local-dir "$MODELS_DIR/gemma-3-12b"
  echo "[OK] Gemma 3 text encoder"
else
  echo "[SKIP] Gemma 3 already exists"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Activate the environment:"
echo "  source .venv/bin/activate"
echo ""
echo "Run text-to-video:"
echo "  python -m ltx_pipelines.run \\"
echo "    --config configs/ltx-2.3-22b-dev-2stage.yaml \\"
echo "    --prompt 'Your prompt here' \\"
echo "    --height 704 --width 1216 --num_frames 97 \\"
echo "    --output output.mp4"
echo ""
echo "Models downloaded to: $MODELS_DIR"
