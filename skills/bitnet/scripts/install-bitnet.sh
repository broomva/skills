#!/usr/bin/env bash
set -euo pipefail

BITNET_DIR="${1:-$HOME/BitNet}"

echo "=== BitNet Installation ==="

# Check prerequisites
for cmd in cmake python3 conda; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: $cmd not found. Install it first."
    exit 1
  fi
done

# Check clang version
if command -v clang &>/dev/null; then
  CLANG_VER=$(clang --version | head -1 | grep -oE '[0-9]+\.' | head -1 | tr -d '.')
  if [ "${CLANG_VER:-0}" -lt 18 ]; then
    echo "WARNING: Clang $CLANG_VER detected, 18+ recommended."
    echo "  Install: brew install llvm"
  fi
fi

# Clone if not exists
if [ -d "$BITNET_DIR" ]; then
  echo "BitNet already exists at $BITNET_DIR"
  cd "$BITNET_DIR" && git pull --recurse-submodules
else
  echo "Cloning BitNet..."
  git clone --recursive https://github.com/microsoft/BitNet.git "$BITNET_DIR"
fi

cd "$BITNET_DIR"

# Create conda environment
if conda env list | grep -q "bitnet-cpp"; then
  echo "Conda env 'bitnet-cpp' already exists"
else
  echo "Creating conda environment..."
  conda create -n bitnet-cpp python=3.9 -y
fi

echo "Installing Python dependencies..."
eval "$(conda shell.bash hook)"
conda activate bitnet-cpp
pip install -r requirements.txt -q

echo ""
echo "=== Installation Complete ==="
echo "BitNet installed at: $BITNET_DIR"
echo "Conda env: bitnet-cpp"
echo ""
echo "Next steps:"
echo "  1. Download a model:  ./scripts/download-model.sh microsoft/BitNet-b1.58-2B-4T-gguf"
echo "  2. Build:             ./scripts/build-bitnet.sh"
echo "  3. Run:               ./scripts/run-inference.sh -p 'Hello' -n 128"
