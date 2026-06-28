#!/usr/bin/env bash
# claude-code-on-ollama.sh — drive Claude Code with a LOCAL Ollama model.
#
# Ollama serves the Anthropic Messages API natively at /v1/messages — the exact
# protocol Claude Code speaks — so NO proxy (claude-code-router / LiteLLM) is needed.
# Claude Code just points at Ollama:
#     ANTHROPIC_BASE_URL=http://localhost:11434  ANTHROPIC_API_KEY=ollama  claude --model <m>
#
# Validated 2026-05-31 (M4 Pro / 24GB / Ollama 0.20.7):
#  - Text round-trips fine -> usable as a CHAT backend with any model.
#  - Tool-calls are MODEL-FAMILY specific: Llama-3.x emits the format Ollama parses
#    into tool_use blocks (works even abliterated); Qwen2.5 does NOT. Default below is
#    a Llama-family model for that reason.
#  - The FULL Claude Code agent loop does NOT complete on 24GB: 128K ctx overflows RAM
#    (empty), capped 32K ctx starves/crashes decode (empty). A working local agent
#    needs 64GB+ unified RAM or a GPU box (broomva/remote-gpu). On 24GB: chat only.
#
# Usage:
#   scripts/claude-code-on-ollama.sh [model] [--smoke] [-- <extra claude args>]
#   scripts/claude-code-on-ollama.sh huihui_ai/qwen2.5-coder-abliterate:14b --smoke
#   scripts/claude-code-on-ollama.sh                      # launch interactive claude on default model
set -euo pipefail

MODEL="${1:-huihui_ai/llama3.2-abliterate:3b}"   # Llama family: tool-calls parse in Ollama (Qwen2.5 don't)
[ $# -gt 0 ] && shift || true
OLLAMA_URL="${OLLAMA_HOST:-http://localhost:11434}"
SMOKE=0; PASS=()
for a in "$@"; do [ "$a" = "--smoke" ] && SMOKE=1 || PASS+=("$a"); done

command -v claude >/dev/null 2>&1 || { echo "ERROR: claude (Claude Code) not on PATH."; exit 1; }
command -v ollama >/dev/null 2>&1 || { echo "ERROR: ollama not on PATH (brew install ollama)."; exit 1; }

# daemon up?
curl -sf "$OLLAMA_URL/api/version" >/dev/null 2>&1 || { echo "starting ollama daemon…"; ollama serve >/tmp/ollama.log 2>&1 & for _ in $(seq 1 20); do curl -sf "$OLLAMA_URL/api/version" >/dev/null 2>&1 && break; sleep 0.5; done; }

# native Anthropic endpoint present? (the whole trick)
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$OLLAMA_URL/v1/messages" \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$MODEL\",\"max_tokens\":5,\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}" 2>/dev/null)
if [ "$code" != "200" ]; then
  echo "ERROR: Ollama at $OLLAMA_URL does not serve /v1/messages (HTTP $code)."
  echo "       Upgrade Ollama (brew upgrade ollama) — native Anthropic Messages API required."
  exit 1
fi

# model present? pull if not
if ! ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$MODEL"; then
  echo "pulling $MODEL …"; ollama pull "$MODEL"
fi

# capability nudge
case "$MODEL" in
  *:1b|*:0.5b|*:1.5b|*:2b|*:3b) echo "⚠️  $MODEL is small — expect poor tool-use / agentic reliability. 14B+ recommended." ;;
esac

export ANTHROPIC_BASE_URL="$OLLAMA_URL"
export ANTHROPIC_API_KEY="ollama"        # dummy; Ollama ignores auth
export ANTHROPIC_MODEL="$MODEL"

if [ "$SMOKE" = 1 ]; then
  echo "=== capability probe: can $MODEL drive Claude Code's tools? ==="
  echo "    (one agent turn on a 14B can take minutes — be patient)"
  WORK="$(mktemp -d)"; LOG="$WORK/stream.json"
  ( cd "$WORK" && timeout "${SMOKE_TIMEOUT:-600}" \
      claude -p "Use the Bash tool to run exactly: echo OLLAMA_AGENT_OK" \
        --model "$MODEL" --dangerously-skip-permissions \
        --output-format stream-json --verbose < /dev/null > "$LOG" 2>&1 ) || true
  python3 - "$LOG" <<'PY'
import json, sys, re
tu = tr = False; result = ""
for line in open(sys.argv[1]):
    line = line.strip()
    if not line.startswith("{"): continue
    try: o = json.loads(line)
    except Exception: continue
    m = o.get("message", {})
    if isinstance(m, dict):
        for c in (m.get("content") or []):
            if isinstance(c, dict) and c.get("type") == "tool_use": tu = True
            if isinstance(c, dict) and c.get("type") == "tool_result": tr = True
    if o.get("type") == "result": result = str(o.get("result", ""))
texty = bool(re.search(r'```json|tool_call|"arguments"\s*:|"name"\s*:\s*"(Bash|Read|Edit|Write|Glob|Grep)"', result))
if tu and tr:
    print("✅ AGENTIC — tool_use round-tripped and executed. Usable as a Claude Code agent.")
elif texty:
    print("⚠️  CHAT-ONLY — model emitted the tool call as TEXT, not a structured tool_use")
    print("    block; Ollama /v1/messages did not translate it, so Claude Code can't run it.")
    print("    Fine as a chat/Q&A backend; NOT a tool-using agent.")
else:
    print("✗  no usable tool attempt (model too weak, or endpoint lacks tool translation).")
PY
  rm -rf "$WORK"
else
  echo "Launching Claude Code on $MODEL (Ctrl-C to exit)…"
  exec claude --model "$MODEL" "${PASS[@]}"
fi
