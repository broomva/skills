#!/usr/bin/env bash
# Render a Content Engine video from manifest.json
# Usage: ./render.sh <output-dir> [output-file] [composition]
#   composition: ContentEngineVideo (16:9, default) or ContentEngineReel (9:16).
#   Gate a ContentEngineReel render with scripts/check_vertical_layout.py.
set -euo pipefail

DIR="${1:-.}"
OUT="${2:-$DIR/final-rendered.mp4}"
COMPOSITION="${3:-ContentEngineVideo}"
MANIFEST="$DIR/manifest.json"

if [ ! -f "$MANIFEST" ]; then
  echo "No manifest.json in $DIR"
  exit 1
fi

cd "$(dirname "$0")"
npx remotion render src/index.ts "$COMPOSITION" "$OUT" --props "$MANIFEST"
echo "Rendered: $OUT"
