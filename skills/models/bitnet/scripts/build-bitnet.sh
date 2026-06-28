#!/usr/bin/env bash
set -euo pipefail

BITNET_DIR="${1:-$HOME/BitNet}"
MODEL_DIR="${2:-models/BitNet-b1.58-2B-4T}"
QUANT="${3:-i2_s}"

echo "=== Building bitnet.cpp ==="
echo "Dir: $BITNET_DIR"
echo "Model: $MODEL_DIR"
echo "Quantization: $QUANT"

cd "$BITNET_DIR"

eval "$(conda shell.bash hook)"
conda activate bitnet-cpp

echo "Building with optimized kernels for this CPU..."
python setup_env.py -md "$MODEL_DIR" -q "$QUANT"

echo ""
echo "=== Build Complete ==="
echo "Ready to run inference."
