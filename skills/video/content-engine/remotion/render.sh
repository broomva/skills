#!/usr/bin/env bash
# Render a Content Engine video from manifest.json
# Usage: ./render.sh <output-dir> [output-file] [composition]
#   composition: ContentEngineVideo (16:9, default) or ContentEngineReel (9:16).
#   Gate a ContentEngineReel render with scripts/check_vertical_layout.py.
set -euo pipefail

DIR="${1:-.}"
OUT="${2:-$DIR/final-rendered.mp4}"
COMPOSITION="${3:-ContentEngineVideo}"

if [ ! -f "$DIR/manifest.json" ]; then
  echo "No manifest.json in $DIR"
  exit 1
fi

# Absolute paths before the cd below: a relative output dir would otherwise be
# resolved against remotion/ and render nothing.
DIR="$(cd "$DIR" && pwd)"
mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
MANIFEST="$DIR/manifest.json"

cd "$(dirname "$0")"
# --public-dir: manifest.json names clips relative to its own directory, and the
# composition resolves them with staticFile(), i.e. against the public dir.
npx remotion render src/index.ts "$COMPOSITION" "$OUT" --props "$MANIFEST" --public-dir "$DIR"
echo "Rendered: $OUT"
