#!/usr/bin/env bash
# heretic-run.sh — run a Heretic abliteration locally with the right device flags.
#
# IMPORTANT: run this in a REAL TERMINAL. Heretic's end-of-run "save / upload / chat"
# menu (and the resume menu) use questionary, which needs a TTY. Piping stdin from
# /dev/null makes it crash (OSError [Errno 22]) AFTER optimization finishes — so you
# lose the saved model. A TTY is required to actually save the result.
#
# Usage:
#   scripts/heretic-run.sh <hf-model-id> [extra heretic args...]
#   scripts/heretic-run.sh Qwen/Qwen3-4B-Instruct-2507
#   scripts/heretic-run.sh Qwen/Qwen3-0.6B --n-trials 8        # small smoke
set -euo pipefail

VENV="${HERETIC_VENV:-$HOME/.venvs/heretic}"
MODEL="${1:-}"
if [[ -z "$MODEL" ]]; then
  echo "Usage: $0 <hf-model-id> [extra heretic args...]"; exit 1
fi
shift || true

if [[ ! -d "$VENV" ]]; then
  echo "ERROR: venv $VENV missing. Run scripts/heretic-install.sh first."; exit 1
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# TTY guard — heretic needs an interactive terminal to save.
if [[ ! -t 0 ]]; then
  echo "⚠️  stdin is not a TTY. Heretic will run the optimization but CRASH at the"
  echo "    save menu, discarding the model. Run in an interactive terminal to save."
fi

# Device selection (dogfood-validated):
OS="$(uname -s)"; ARCH="$(uname -m)"
DEV_ARGS=()
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "→ CUDA detected. Full speed; add --quantization BNB_4BIT to fit large models."
elif [[ "$OS" == "Darwin" && "$ARCH" == "arm64" ]]; then
  echo "⚠️  Apple Silicon: forcing --device-map cpu. MPS hits a PyTorch mps.matmul"
  echo "    LLVM error on grouped-query-attention models (Qwen3, Llama3, …)."
  echo "    CPU works but is slow (~50–110 tok/s). Use a real GPU for >1B models"
  echo "    (see broomva/remote-gpu)."
  export PYTORCH_ENABLE_MPS_FALLBACK=1
  DEV_ARGS=(--device-map cpu --quantization NONE)
else
  echo "→ No GPU: running on CPU (slow)."
  DEV_ARGS=(--device-map cpu --quantization NONE)
fi

set -x
heretic --model "$MODEL" "${DEV_ARGS[@]}" "$@"
