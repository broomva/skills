#!/usr/bin/env bash
# Render a Content Engine video from manifest.json
# Usage: ./render.sh <output-dir> [output-file]
set -euo pipefail

DIR="${1:-.}"
OUT="${2:-$DIR/final-rendered.mp4}"
MANIFEST="$DIR/manifest.json"

if [ ! -f "$MANIFEST" ]; then
  echo "No manifest.json in $DIR"
  exit 1
fi

cd "$(dirname "$0")"
npx remotion render ContentEngineVideo "$OUT" --props "$MANIFEST"
echo "Rendered: $OUT"
