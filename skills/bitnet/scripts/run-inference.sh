#!/usr/bin/env bash
set -euo pipefail

BITNET_DIR="${BITNET_DIR:-$HOME/BitNet}"

# Find the GGUF model file
MODEL_PATH=""
if [ -n "${MODEL:-}" ]; then
  MODEL_PATH="$MODEL"
else
  MODEL_PATH=$(find "$BITNET_DIR/models" -name "ggml-model-*.gguf" -type f 2>/dev/null | head -1)
fi

if [ -z "$MODEL_PATH" ]; then
  echo "ERROR: No GGUF model found. Run download-model.sh and build-bitnet.sh first."
  exit 1
fi

echo "=== BitNet Inference ==="
echo "Model: $MODEL_PATH"

cd "$BITNET_DIR"
eval "$(conda shell.bash hook)"
conda activate bitnet-cpp

python run_inference.py -m "$MODEL_PATH" "$@"
