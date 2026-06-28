#!/usr/bin/env bash
set -euo pipefail

MODEL_ID="${1:-microsoft/BitNet-b1.58-2B-4T-gguf}"
BITNET_DIR="${2:-$HOME/BitNet}"
MODEL_NAME=$(echo "$MODEL_ID" | sed 's|.*/||')
MODEL_DIR="$BITNET_DIR/models/$MODEL_NAME"

echo "=== Downloading BitNet Model ==="
echo "Model: $MODEL_ID"
echo "Target: $MODEL_DIR"

if ! command -v huggingface-cli &>/dev/null; then
  echo "Installing huggingface-cli..."
  pip install huggingface-hub -q
fi

if [ -d "$MODEL_DIR" ] && [ "$(ls -A "$MODEL_DIR" 2>/dev/null)" ]; then
  echo "Model already downloaded at $MODEL_DIR"
else
  echo "Downloading from HuggingFace..."
  huggingface-cli download "$MODEL_ID" --local-dir "$MODEL_DIR"
fi

echo ""
echo "=== Download Complete ==="
echo "Model at: $MODEL_DIR"
echo "Files:"
ls -lh "$MODEL_DIR"/ | grep -E '\.(gguf|safetensors|bin|json)' | head -10
