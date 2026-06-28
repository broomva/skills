#!/usr/bin/env bash
# capture_chart.sh — capture a TradingView chart screenshot at alert moment.
#
# This is the P11 evidence layer for the dogfood pattern: visual proof that
# the strategy fired AND the chart context that produced the signal. Without
# this, the dogfood receipt for trading strategies has no visual artifact.
#
# Approach: drive the Interceptor browser extension via its CLI. Interceptor
# attaches to a real Chrome session (your logged-in TradingView account, not
# a headless puppet) and captures pixel-accurate screenshots that pass any
# bot-detection that TradingView might apply.
#
# Prerequisites:
#   - Interceptor browser extension installed and active
#     (see ~/.claude/skills/Interceptor/SKILL.md for setup)
#   - The Interceptor MCP server registered in ~/.claude/settings.json
#   - You're logged into TradingView in the Interceptor-controlled tab
#
# Usage:
#   ./capture_chart.sh <chart_url> <output_path>
#
# Example:
#   ./capture_chart.sh "https://www.tradingview.com/chart/?symbol=AAPL&interval=15" \
#                      /tmp/aapl-alert-001.png

set -euo pipefail

CHART_URL="${1:-}"
OUTPUT_PATH="${2:-}"

if [[ -z "$CHART_URL" || -z "$OUTPUT_PATH" ]]; then
  echo "Usage: $0 <chart_url> <output_path>" >&2
  echo "" >&2
  echo "Captures a TradingView chart screenshot via the Interceptor MCP." >&2
  echo "Used by the tradingview-bridge dogfood loop to attach visual" >&2
  echo "evidence to each alert receipt." >&2
  exit 1
fi

# The actual capture is performed by the Interceptor MCP tool, invoked from
# whatever agent is running this script. This shell wrapper exists as the
# documented entry point — agents can shell out to it OR invoke Interceptor's
# MCP tools directly, depending on context.
#
# Documented MCP-tool sequence (run from an agent with Interceptor active):
#   1. interceptor open "$CHART_URL"
#   2. wait ~3s for chart to render
#   3. interceptor read (verify the chart loaded — ticker, price visible)
#   4. interceptor screenshot --output "$OUTPUT_PATH"
#
# When you do NOT have Interceptor MCP available, fall back to manual:
#   - Open $CHART_URL in your browser
#   - Cmd+Shift+S (macOS) or screencapture -R region for the chart area
#   - Save as $OUTPUT_PATH
#
# When run from an agent context with Interceptor MCP active, the agent
# should invoke the MCP tools directly rather than shelling out — see
# `services/tradingview-bridge/strategies/README.md` §Capturing chart
# screenshots on alert fire.

if command -v interceptor >/dev/null 2>&1; then
  echo "Using Interceptor CLI..." >&2
  interceptor open "$CHART_URL"
  sleep 3
  interceptor read >/dev/null
  interceptor screenshot --output "$OUTPUT_PATH"
  echo "Captured: $OUTPUT_PATH" >&2
elif command -v screencapture >/dev/null 2>&1; then
  echo "Interceptor CLI not on PATH; falling back to macOS screencapture." >&2
  echo "Manually open the chart URL first; this script will capture the" >&2
  echo "frontmost window after 3 seconds." >&2
  open "$CHART_URL"
  sleep 5
  screencapture -x "$OUTPUT_PATH"
  echo "Captured: $OUTPUT_PATH" >&2
else
  echo "ERROR: neither Interceptor CLI nor macOS screencapture available." >&2
  echo "Install Interceptor (https://github.com/broomva/Interceptor) or" >&2
  echo "capture the chart manually and save to $OUTPUT_PATH." >&2
  exit 1
fi
