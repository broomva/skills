#!/usr/bin/env bash
set -euo pipefail

BITNET_DIR="${1:-$HOME/BitNet}"

MODEL_PATH=$(find "$BITNET_DIR/models" -name "ggml-model-*.gguf" -type f 2>/dev/null | head -1)

if [ -z "$MODEL_PATH" ]; then
  echo "ERROR: No GGUF model found. Run download-model.sh and build-bitnet.sh first."
  exit 1
fi

echo "=== BitNet Benchmark ==="
echo "Model: $MODEL_PATH"

cd "$BITNET_DIR"
eval "$(conda shell.bash hook)"
conda activate bitnet-cpp

echo ""
echo "--- Warmup ---"
python run_inference.py -m "$MODEL_PATH" -p "Warmup" -n 16 2>/dev/null

echo ""
echo "--- Benchmark: 128 tokens ---"
time python run_inference.py -m "$MODEL_PATH" -p "Write a detailed explanation of how neural networks learn through backpropagation" -n 128 -t $(sysctl -n hw.ncpu 2>/dev/null || nproc)

echo ""
echo "--- Benchmark: 256 tokens ---"
time python run_inference.py -m "$MODEL_PATH" -p "Explain the history of computing from Babbage to modern GPUs" -n 256 -t $(sysctl -n hw.ncpu 2>/dev/null || nproc)

echo ""
echo "=== Benchmark Complete ==="
