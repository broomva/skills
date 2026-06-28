#!/usr/bin/env bash
# heretic-install.sh — install heretic-llm into a CLEAN, dedicated venv and apply
# the two dependency fixes discovered during the 2026-05-30 dogfood.
#
# Why a venv (not conda base): heretic pulls transformers 5.9.0 which drags in two
# breakages. One (kernels) is universal; the other (ancient jinja2) only bites
# crowded base envs. A fresh venv + these defensive fixes = clean import.
set -euo pipefail

VENV="${HERETIC_VENV:-$HOME/.venvs/heretic}"

echo "=== Installing heretic-llm into $VENV ==="

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found (need 3.10+)."; exit 1
fi

# 1. Clean venv (never the conda base env)
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python3 -m pip install -U pip >/dev/null

# 2. Install heretic
python3 -m pip install -U heretic-llm

# 3. FIX #1 (universal): transformers 5.9.x ↔ kernels 0.15.x import crash
#    "ValueError: Either a revision or a version must be specified" in
#    transformers/integrations/hub_kernels.py. kernels is an OPTIONAL accelerator.
python3 -m pip uninstall -y kernels kernels-data >/dev/null 2>&1 || true

# 4. FIX #2 (defensive): chat-template needs jinja2 >= 3.0 (pass_eval_context).
#    Fresh venvs are fine; this only matters if an old jinja2 leaked in.
python3 -m pip install -U 'jinja2>=3.1' >/dev/null

# 5. gguf (for later HF→GGUF conversion via convert_hf_to_gguf.py)
python3 -m pip install -U gguf >/dev/null 2>&1 || true

# 6. Verify the import actually works
echo
if python3 -c "import heretic.main; print('import OK')"; then
  HV=$(python3 -c "import importlib.metadata as m; print(m.version('heretic-llm'))" 2>/dev/null || echo '?')
  echo "✅ heretic-llm $HV installed and importable in $VENV"
  echo "   Activate with: source $VENV/bin/activate"
  echo "   Next: scripts/heretic-doctor.sh   then   scripts/heretic-run.sh <model>"
else
  echo "❌ heretic still not importable — see references/troubleshooting.md"
  exit 1
fi
