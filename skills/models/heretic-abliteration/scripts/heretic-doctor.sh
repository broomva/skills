#!/usr/bin/env bash
# heretic-doctor.sh — environment readiness check for the heretic-abliteration skill.
# Reports which path is viable: GPU-run, CPU-run (slow), or serve-only.
set -euo pipefail

VENV="${HERETIC_VENV:-$HOME/.venvs/heretic}"

echo "=== Heretic / Ollama environment doctor ==="
echo

# --- platform ---
OS="$(uname -s)"; ARCH="$(uname -m)"
echo "Platform : $OS $ARCH"
if [[ "$OS" == "Darwin" ]]; then
  echo "Chip     : $(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo '?')"
  RAM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1024 / 1024 / 1024 ))
  echo "RAM      : ${RAM_GB} GB unified"
fi

# --- accelerator ---
ACCEL="cpu"
if command -v nvidia-smi >/dev/null 2>&1; then
  ACCEL="cuda"
  echo "GPU      : CUDA detected → $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
elif [[ "$OS" == "Darwin" && "$ARCH" == "arm64" ]]; then
  ACCEL="mps-blocked"
  echo "GPU      : Apple Metal (MPS) present — but BLOCKED for GQA models (PyTorch mps.matmul bug). Heretic must run --device-map cpu here."
else
  echo "GPU      : none detected (CPU-only)"
fi

# --- python / venv / heretic ---
echo
if [[ -d "$VENV" ]]; then
  echo "venv     : $VENV (exists)"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
else
  echo "venv     : $VENV (MISSING — run scripts/heretic-install.sh)"
fi
echo "python   : $(python3 --version 2>&1) [$(command -v python3)]"
if python3 -c "import heretic.main" >/dev/null 2>&1; then
  HV=$(python3 -c "import importlib.metadata as m; print(m.version('heretic-llm'))" 2>/dev/null || echo '?')
  echo "heretic  : OK (heretic-llm $HV, importable)"
else
  echo "heretic  : NOT importable (run scripts/heretic-install.sh; check kernels/jinja2 fixes)"
fi

# --- ollama ---
echo
if command -v ollama >/dev/null 2>&1; then
  echo "ollama   : $(ollama --version 2>&1 | head -1)"
  if curl -sS http://localhost:11434/api/version >/dev/null 2>&1; then
    echo "           daemon UP"
  else
    echo "           daemon DOWN (start with: ollama serve &)"
  fi
else
  echo "ollama   : NOT installed (brew install ollama)"
fi

# --- llama.cpp (for GGUF conversion) ---
CONVERT="$(command -v convert_hf_to_gguf.py || true)"
if command -v llama-quantize >/dev/null 2>&1 && [[ -n "$CONVERT" ]]; then
  echo "llama.cpp: OK (llama-quantize + $CONVERT)"
else
  echo "llama.cpp: incomplete (need 'brew install llama.cpp' for llama-quantize + convert_hf_to_gguf.py)"
fi

# --- disk ---
echo
echo "disk     : $(df -h / | awk 'NR==2{print $4" free on /"}')"

# --- verdict ---
echo
echo "=== Recommended path ==="
case "$ACCEL" in
  cuda)        echo "→ RUN locally: scripts/heretic-run.sh <model>  (GPU; BNB_4BIT ok)." ;;
  mps-blocked) echo "→ CPU only (slow, small models). For real models use broomva/remote-gpu, then scripts/heretic-to-ollama.sh."
               echo "→ Or skip running Heretic entirely: scripts/ollama-pull-abliterated.sh (fast, recommended)." ;;
  *)           echo "→ CPU only (slow). Prefer scripts/ollama-pull-abliterated.sh, or a GPU via broomva/remote-gpu." ;;
esac
