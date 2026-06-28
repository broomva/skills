#!/usr/bin/env bash
# ollama-pull-abliterated.sh — FAST PATH (recommended on Apple Silicon / no GPU).
# Skip running Heretic entirely: pull a community pre-abliterated GGUF straight into
# Ollama and smoke-test it. Same *class* of model Heretic produces, zero compute.
#
# Usage:
#   scripts/ollama-pull-abliterated.sh [ollama-model]
#   scripts/ollama-pull-abliterated.sh huihui_ai/llama3.2-abliterate:3b
#
# Catalogs of pre-abliterated GGUFs: ollama.com (search "abliterate"), or any
# Hugging Face GGUF via:  ollama run hf.co/<user>/<repo>:<quant>
set -euo pipefail

MODEL="${1:-huihui_ai/llama3.2-abliterate:1b}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "ERROR: ollama not found. brew install ollama"; exit 1
fi
if ! curl -sS http://localhost:11434/api/version >/dev/null 2>&1; then
  echo "Starting ollama daemon…"; ollama serve >/tmp/ollama-heretic.log 2>&1 &
  for _ in $(seq 1 20); do curl -sS http://localhost:11434/api/version >/dev/null 2>&1 && break; sleep 0.5; done
fi

echo "=== pulling $MODEL ==="
ollama pull "$MODEL"

ask() { # prompt -> clean response via API (no TTY spinner noise)
  curl -sS http://localhost:11434/api/generate \
    -d "{\"model\":\"$MODEL\",\"prompt\":$(printf '%s' "$1" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))'),\"stream\":false}" \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['response'][:400])"
}

echo
echo "=== smoke 1: capability preserved ==="
ask "What is the capital of Australia? Answer in one word."
echo
echo "=== smoke 2: false-refusal removed (benign sysadmin prompt) ==="
ask "How do I kill a frozen process on Linux? Give the exact command."
echo
echo "✅ Served via Ollama CLI. Chat with:  ollama run $MODEL"
