#!/usr/bin/env bash
# setup-ltx-wsl2.sh — LTX-2.3 setup for Windows/WSL2 with RTX 4090 (12GB VRAM)
#
# Designed for Intel NUC + RTX 4090 12GB on WSL2 (Ubuntu).
# Defaults to distilled model + FP8 quantization to fit within 12GB VRAM budget.
#
# Usage: bash scripts/setup-ltx-wsl2.sh [OPTIONS]
#
# Prerequisites:
#   - WSL2 with Ubuntu 22.04+
#   - NVIDIA CUDA Toolkit >= 12.7 installed inside WSL2
#   - Python >= 3.12
#   - uv (Python package manager)
#   - nvidia-smi accessible from WSL2
#   - huggingface-cli (installed automatically if missing)
#
set -euo pipefail

# ──────────────────────────────────────────────────────────
# Defaults
# ──────────────────────────────────────────────────────────
MODELS_DIR="${MODELS_DIR:-./models}"
VARIANT="${VARIANT:-distilled}"          # distilled by default for 12GB VRAM
INSTALL_DIR="${INSTALL_DIR:-.}"          # where to clone LTX-2
SKIP_CLONE="${SKIP_CLONE:-false}"
SKIP_MODELS="${SKIP_MODELS:-false}"
HF_REPO="Lightricks/LTX-2.3"
REPO_URL="https://github.com/Lightricks/LTX-2.git"
REQUIRED_CUDA_MAJOR=12
REQUIRED_CUDA_MINOR=7
REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=12

# ──────────────────────────────────────────────────────────
# Help
# ──────────────────────────────────────────────────────────
show_help() {
  cat <<'HELP'
setup-ltx-wsl2.sh — LTX-2.3 setup for Windows/WSL2 + RTX 4090 12GB

USAGE:
  bash scripts/setup-ltx-wsl2.sh [OPTIONS]

OPTIONS:
  --models-dir DIR      Where to download models         (default: ./models)
  --variant TYPE        dev | distilled | both            (default: distilled)
  --install-dir DIR     Where to clone LTX-2 repo        (default: .)
  --skip-clone          Skip git clone (repo already exists)
  --skip-models         Skip model downloads
  --help                Show this help message

ENVIRONMENT VARIABLES:
  MODELS_DIR            Same as --models-dir
  VARIANT               Same as --variant
  INSTALL_DIR           Same as --install-dir
  HF_TOKEN              Hugging Face token for gated models (Gemma 3)

NOTES:
  - Defaults to distilled variant + FP8 quantization (fits 12GB VRAM)
  - The dev model requires 24GB+ VRAM without FP8; use with caution on 12GB cards
  - Gemma 3 text encoder download requires a Hugging Face account with access granted

EXAMPLES:
  # Standard setup (distilled, recommended for 12GB VRAM)
  bash scripts/setup-ltx-wsl2.sh

  # Dev model (will need --quantization fp8-cast at inference time)
  bash scripts/setup-ltx-wsl2.sh --variant dev

  # Custom model directory
  bash scripts/setup-ltx-wsl2.sh --models-dir /mnt/d/models/ltx
HELP
  exit 0
}

# ──────────────────────────────────────────────────────────
# Parse arguments
# ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --models-dir)   MODELS_DIR="$2";   shift 2 ;;
    --variant)      VARIANT="$2";      shift 2 ;;
    --install-dir)  INSTALL_DIR="$2";  shift 2 ;;
    --skip-clone)   SKIP_CLONE=true;   shift ;;
    --skip-models)  SKIP_MODELS=true;  shift ;;
    --help|-h)      show_help ;;
    *) echo "ERROR: Unknown option: $1"; echo "Run with --help for usage."; exit 1 ;;
  esac
done

# ──────────────────────────────────────────────────────────
# Utility functions
# ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()    { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }
skip()    { echo -e "${YELLOW}[SKIP]${NC}  $*"; }

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    fail "$1 is not installed. $2"
  fi
}

# ──────────────────────────────────────────────────────────
# 1. Prerequisites
# ──────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  LTX-2.3 Setup — WSL2 + RTX 4090 12GB VRAM"
echo "=============================================="
echo ""
echo "Models directory : $MODELS_DIR"
echo "Variant          : $VARIANT"
echo "Install directory: $INSTALL_DIR"
echo ""

info "Checking prerequisites..."
echo ""

# --- WSL2 check ---
if grep -qi microsoft /proc/version 2>/dev/null; then
  ok "Running inside WSL2"
else
  warn "WSL2 not detected (no 'microsoft' in /proc/version)."
  warn "This script is designed for WSL2. Proceeding anyway, but YMMV."
fi

# --- git ---
check_cmd git "Install with: sudo apt install git"
ok "git found"

# --- Python version ---
check_cmd python3 "Install with: sudo apt install python3.12"
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [[ "$PYTHON_MAJOR" -lt "$REQUIRED_PYTHON_MAJOR" ]] || \
   [[ "$PYTHON_MAJOR" -eq "$REQUIRED_PYTHON_MAJOR" && "$PYTHON_MINOR" -lt "$REQUIRED_PYTHON_MINOR" ]]; then
  fail "Python >= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR} required (found $PYTHON_VERSION)"
fi
ok "Python $PYTHON_VERSION"

# --- uv ---
check_cmd uv "Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
ok "uv found ($(uv --version 2>/dev/null || echo 'unknown version'))"

# --- nvidia-smi ---
check_cmd nvidia-smi "NVIDIA driver not accessible from WSL2. Ensure the Windows NVIDIA driver supports WSL2 CUDA."
ok "nvidia-smi found"

# --- GPU info ---
info "Querying GPU..."
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")
GPU_VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 || echo "0")
GPU_DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")

if [[ "$GPU_VRAM_MB" -gt 0 ]]; then
  GPU_VRAM_GB=$((GPU_VRAM_MB / 1024))
  ok "GPU: $GPU_NAME — ${GPU_VRAM_GB}GB VRAM — Driver $GPU_DRIVER"
  if [[ "$GPU_VRAM_GB" -lt 12 ]]; then
    warn "Less than 12GB VRAM detected. LTX-2 distilled+FP8 needs ~12GB."
    warn "You may experience OOM errors at higher resolutions."
  fi
else
  warn "Could not query GPU VRAM. Proceeding, but expect issues if no GPU is available."
fi

# --- CUDA toolkit version ---
if command -v nvcc &>/dev/null; then
  CUDA_VERSION=$(nvcc --version | grep -oP 'release \K[\d.]+' || echo "unknown")
  CUDA_MAJOR=$(echo "$CUDA_VERSION" | cut -d. -f1)
  CUDA_MINOR=$(echo "$CUDA_VERSION" | cut -d. -f2)
  if [[ "$CUDA_MAJOR" -lt "$REQUIRED_CUDA_MAJOR" ]] || \
     [[ "$CUDA_MAJOR" -eq "$REQUIRED_CUDA_MAJOR" && "$CUDA_MINOR" -lt "$REQUIRED_CUDA_MINOR" ]]; then
    warn "CUDA Toolkit $CUDA_VERSION detected. LTX-2 recommends >= ${REQUIRED_CUDA_MAJOR}.${REQUIRED_CUDA_MINOR}."
    warn "You may encounter compatibility issues."
  else
    ok "CUDA Toolkit $CUDA_VERSION"
  fi
else
  warn "nvcc not found. CUDA Toolkit may not be installed inside WSL2."
  warn "Install with: sudo apt install nvidia-cuda-toolkit"
  warn "Or follow: https://developer.nvidia.com/cuda-downloads (select WSL-Ubuntu)"
  warn "Proceeding — PyTorch bundles its own CUDA runtime, but nvcc is needed for some extensions."
fi

echo ""
info "All critical prerequisites passed."
echo ""

# ──────────────────────────────────────────────────────────
# 2. Clone the LTX-2 repository
# ──────────────────────────────────────────────────────────
if [[ "$SKIP_CLONE" == "true" ]]; then
  skip "Cloning (--skip-clone)"
else
  CLONE_TARGET="$INSTALL_DIR/LTX-2"
  if [ -d "$CLONE_TARGET" ]; then
    ok "LTX-2 repo already exists at $CLONE_TARGET"
    info "Pulling latest changes..."
    git -C "$CLONE_TARGET" pull --ff-only 2>/dev/null || warn "Could not pull (detached HEAD or conflicts). Skipping."
  else
    echo "=== Cloning LTX-2 repository ==="
    git clone "$REPO_URL" "$CLONE_TARGET"
    ok "Cloned to $CLONE_TARGET"
  fi
fi

# Determine working directory
if [[ "$SKIP_CLONE" == "true" ]]; then
  if [ -d "$INSTALL_DIR/LTX-2" ]; then
    WORK_DIR="$INSTALL_DIR/LTX-2"
  elif [ -f "$INSTALL_DIR/pyproject.toml" ]; then
    WORK_DIR="$INSTALL_DIR"
  else
    fail "Cannot find LTX-2 repo. Run without --skip-clone or set --install-dir to the LTX-2 directory."
  fi
else
  WORK_DIR="$INSTALL_DIR/LTX-2"
fi

cd "$WORK_DIR"
info "Working directory: $(pwd)"
echo ""

# ──────────────────────────────────────────────────────────
# 3. Install dependencies
# ──────────────────────────────────────────────────────────
echo "=== Installing Python dependencies with uv ==="
if [ -f "pyproject.toml" ]; then
  uv sync --frozen 2>/dev/null || uv sync
  ok "Dependencies installed"
else
  fail "pyproject.toml not found in $(pwd). Is this the LTX-2 repo root?"
fi

# Verify PyTorch CUDA
info "Verifying PyTorch CUDA support..."
if uv run python3 -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'" 2>/dev/null; then
  TORCH_CUDA=$(uv run python3 -c "import torch; print(torch.version.cuda)" 2>/dev/null || echo "unknown")
  ok "PyTorch CUDA $TORCH_CUDA is available"
else
  warn "PyTorch cannot access CUDA. Check your NVIDIA driver and WSL2 GPU passthrough."
  warn "Proceeding with setup, but inference will fail without CUDA."
fi
echo ""

# ──────────────────────────────────────────────────────────
# 4. Download models
# ──────────────────────────────────────────────────────────
if [[ "$SKIP_MODELS" == "true" ]]; then
  skip "Model downloads (--skip-models)"
else
  echo "=== Downloading models ==="
  mkdir -p "$MODELS_DIR"

  # Ensure huggingface-cli is available
  if ! command -v huggingface-cli &>/dev/null; then
    info "Installing huggingface_hub CLI..."
    uv pip install "huggingface_hub[cli]"
  fi
  ok "huggingface-cli available"

  # Check HF authentication (needed for Gemma 3 gated model)
  if ! huggingface-cli whoami &>/dev/null; then
    warn "Not logged in to Hugging Face."
    warn "Gemma 3 is a gated model — you need to:"
    warn "  1. Create an account at https://huggingface.co"
    warn "  2. Accept the Gemma 3 license at https://huggingface.co/google/gemma-3-12b-it"
    warn "  3. Run: huggingface-cli login"
    warn "Proceeding with non-gated downloads first..."
    echo ""
  fi

  download_model() {
    local filename="$1"
    local dest="$MODELS_DIR/$filename"
    if [ -f "$dest" ]; then
      skip "$filename (already exists)"
    else
      info "Downloading $filename..."
      if huggingface-cli download "$HF_REPO" "$filename" --local-dir "$MODELS_DIR"; then
        ok "$filename"
      else
        warn "Failed to download $filename — check network and HF access."
        return 1
      fi
    fi
  }

  # --- Core model weights ---
  echo ""
  info "--- Core model weights ---"
  if [[ "$VARIANT" == "dev" || "$VARIANT" == "both" ]]; then
    download_model "ltx-2.3-22b-dev.safetensors" || true
  fi
  if [[ "$VARIANT" == "distilled" || "$VARIANT" == "both" ]]; then
    download_model "ltx-2.3-22b-distilled.safetensors" || true
    download_model "ltx-2.3-22b-distilled-lora-384.safetensors" || true
  fi

  # --- Spatial upscaler ---
  echo ""
  info "--- Spatial upscaler ---"
  # Use x1.5 upscaler by default for 12GB VRAM (less VRAM than x2)
  download_model "ltx-2.3-spatial-upscaler-x1.5-1.0.safetensors" || true
  # Also grab x2 for when VRAM allows
  download_model "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" || true

  # --- Temporal upscaler ---
  echo ""
  info "--- Temporal upscaler ---"
  download_model "ltx-2.3-temporal-upscaler-x2-1.0.safetensors" || true

  # --- Gemma 3 text encoder (gated — requires HF login) ---
  echo ""
  info "--- Gemma 3 text encoder (required for all pipelines) ---"
  GEMMA_DIR="$MODELS_DIR/gemma-3-12b"
  if [ -d "$GEMMA_DIR" ] && [ "$(ls -A "$GEMMA_DIR" 2>/dev/null)" ]; then
    skip "Gemma 3 text encoder (already exists at $GEMMA_DIR)"
  else
    info "Downloading Gemma 3 12B text encoder (this is large, ~24GB)..."
    if huggingface-cli download google/gemma-3-12b-it --local-dir "$GEMMA_DIR"; then
      ok "Gemma 3 text encoder"
    else
      echo ""
      warn "Failed to download Gemma 3. This is a gated model."
      warn "To fix:"
      warn "  1. Go to https://huggingface.co/google/gemma-3-12b-it"
      warn "  2. Accept the license agreement"
      warn "  3. Run: huggingface-cli login"
      warn "  4. Re-run this script (existing downloads will be skipped)"
    fi
  fi
fi

echo ""

# ──────────────────────────────────────────────────────────
# 5. Print usage examples for 12GB VRAM
# ──────────────────────────────────────────────────────────
cat <<'USAGE'
==============================================
  Setup Complete — RTX 4090 12GB Usage Guide
==============================================

IMPORTANT: With 12GB VRAM, ALWAYS use --quantization fp8-cast

Activate the environment:
  cd LTX-2
  source .venv/bin/activate

─── Recommended: Distilled + FP8 (fastest, fits 12GB) ───

  python -m ltx_pipelines.run \
    --config configs/ltx-2.3-22b-distilled-2stage.yaml \
    --quantization fp8-cast \
    --prompt "A golden retriever running through autumn leaves in a sunlit park" \
    --height 704 --width 1216 \
    --num_frames 97 \
    --output output.mp4

─── If you get OOM at 704x1216, drop to 480x832 ───

  python -m ltx_pipelines.run \
    --config configs/ltx-2.3-22b-distilled-2stage.yaml \
    --quantization fp8-cast \
    --prompt "A golden retriever running through autumn leaves in a sunlit park" \
    --height 480 --width 832 \
    --num_frames 97 \
    --output output_lowres.mp4

─── Single-stage pipeline (tightest VRAM, ~30% less) ───

  python -m ltx_pipelines.run \
    --config configs/ltx-2.3-22b-distilled-1stage.yaml \
    --quantization fp8-cast \
    --prompt "A golden retriever running through autumn leaves in a sunlit park" \
    --height 480 --width 832 \
    --num_frames 65 \
    --output output_1stage.mp4

─── Dev model with FP8 (higher quality, slower) ───

  python -m ltx_pipelines.run \
    --config configs/ltx-2.3-22b-dev-2stage.yaml \
    --quantization fp8-cast \
    --prompt "A golden retriever running through autumn leaves in a sunlit park" \
    --height 704 --width 1216 \
    --num_frames 97 \
    --output output_dev.mp4

─── Image-to-video ───

  python -m ltx_pipelines.run \
    --config configs/ltx-2.3-22b-distilled-2stage.yaml \
    --quantization fp8-cast \
    --prompt "The scene slowly comes alive with gentle motion..." \
    --conditioning_image path/to/image.png \
    --height 704 --width 1216 \
    --num_frames 97 \
    --output output_i2v.mp4

─── 12GB VRAM Cheat Sheet ───

  Resolution rules:
    - Width & height must be divisible by 32
    - Frame count must be 8n + 1 (33, 65, 97, 129)

  If you hit OOM, try in order:
    1. Add --quantization fp8-cast (if not already)
    2. Reduce resolution: 704x1216 -> 480x832 -> 384x672
    3. Reduce frames: 97 -> 65 -> 33
    4. Switch to single-stage pipeline (1stage config)
    5. Use distilled model instead of dev

  Optimal 12GB defaults:
    - Model: distilled (8 inference steps vs 40)
    - Quantization: fp8-cast (~40% VRAM savings)
    - Resolution: 704x1216 (try first), 480x832 (fallback)
    - Frames: 97 (3.2s at 30fps) or 65 (2.1s)

USAGE

echo "Models directory: $(cd "$MODELS_DIR" 2>/dev/null && pwd || echo "$MODELS_DIR")"
echo ""
echo "For prompting best practices, see: references/prompting-guide.md"
echo "For ComfyUI setup, see: references/comfyui-setup.md"
echo ""
