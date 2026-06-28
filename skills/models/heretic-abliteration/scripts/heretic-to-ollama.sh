#!/usr/bin/env bash
# heretic-to-ollama.sh — convert a Heretic-saved HF model into a GGUF and register
# it with Ollama. This is the bridge: Heretic outputs HF safetensors; Ollama serves
# GGUF. Ollama can NEVER be Heretic's backend — it only runs the finished model.
#
# Pipeline:  HF safetensors  →  convert_hf_to_gguf.py  →  llama-quantize  →  ollama create
#
# Usage:
#   scripts/heretic-to-ollama.sh <hf-model-dir> [ollama-name] [quant]
#   scripts/heretic-to-ollama.sh ./Qwen3-4B-heretic my-heretic Q4_K_M
set -euo pipefail

MODEL_DIR="${1:-}"
NAME="${2:-heretic-model}"
QUANT="${3:-Q4_K_M}"
VENV="${HERETIC_VENV:-$HOME/.venvs/heretic}"
WORK="${HERETIC_WORK:-$(pwd)/gguf-out}"

if [[ -z "$MODEL_DIR" || ! -d "$MODEL_DIR" ]]; then
  echo "Usage: $0 <hf-model-dir> [ollama-name] [quant]"; exit 1
fi

CONVERT="$(command -v convert_hf_to_gguf.py || echo /opt/homebrew/bin/convert_hf_to_gguf.py)"
if [[ ! -e "$CONVERT" ]]; then
  echo "ERROR: convert_hf_to_gguf.py not found. brew install llama.cpp"; exit 1
fi
if ! command -v llama-quantize >/dev/null 2>&1; then
  echo "ERROR: llama-quantize not found. brew install llama.cpp"; exit 1
fi
if ! command -v ollama >/dev/null 2>&1; then
  echo "ERROR: ollama not found. brew install ollama"; exit 1
fi

# Ensure gguf python dep (convert script needs it)
[[ -d "$VENV" ]] && source "$VENV/bin/activate" || true
python3 -c "import gguf" 2>/dev/null || python3 -m pip install -U gguf

mkdir -p "$WORK"
F16="$WORK/${NAME}-f16.gguf"
Q="$WORK/${NAME}-${QUANT}.gguf"

echo "=== 1/3 HF → GGUF (f16) ==="
python3 "$CONVERT" "$MODEL_DIR" --outfile "$F16" --outtype f16

echo "=== 2/3 quantize → $QUANT ==="
llama-quantize "$F16" "$Q" "$QUANT"

echo "=== 3/3 ollama create '$NAME' ==="
MODELFILE="$WORK/Modelfile.$NAME"
printf 'FROM %s\n' "$Q" > "$MODELFILE"
ollama create "$NAME" -f "$MODELFILE"

echo
echo "✅ Registered. Smoke test:"
echo "   ollama run $NAME \"In one word, capital of Australia?\""
