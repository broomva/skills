#!/bin/bash
# p9-escalate-notify.sh — default escalation notify hook.
#
# Invoked by P9 after a Linear ticket is created for an unclassified or
# evaluator-stalled CI failure. Receives JSON on stdin:
#   {pr: int, repo: str, failure_signature: str, linear_ticket: str, attempt: int}
#
# Default behavior: log to ~/.config/broomva/p9/escalations.log. Override
# this hook in .control/policy.yaml -> ci_heal.escalation_channel.notify_hook
# to wire Discord, Telegram, or any other channel via the existing
# claude-remote-sessions infra.

set -euo pipefail

LOG="${BROOMVA_P9_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/broomva/p9}/escalations.log"
mkdir -p "$(dirname "$LOG")"

PAYLOAD="$(cat)"
TS="$(date -u +%FT%TZ)"
echo "[$TS] $PAYLOAD" >> "$LOG"

exit 0
