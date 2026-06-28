#!/usr/bin/env bash
# End-to-end smoke test for the video-cut pipeline — fully local.
# Synthesizes a talking clip, transcribes (local faster_whisper), packs, builds an EDL,
# renders, self-evals. Portable: if no TTS is present, uses a synthetic transcript so the
# ffmpeg render path is still exercised.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$SKILL_DIR/scripts"
PY="${PYTHON:-python3}"
MODEL="${VIDEOCUT_WHISPER_MODEL:-tiny}"
TMP="$(mktemp -d)"
EDIT="$TMP/edit"
mkdir -p "$EDIT/transcripts"
trap 'rm -rf "$TMP"' EXIT

pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗ %s\033[0m\n' "$1"; exit 1; }

# Assert audio and video stream durations match within TOL seconds (A/V sync, no
# per-seam AAC-priming drift). Defends against the cross-review's finding B.
av_sync_ok() {
  local f="$1" tol="${2:-0.06}"
  local vd ad
  vd=$(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of csv=p=0 "$f")
  ad=$(ffprobe -v error -select_streams a:0 -show_entries stream=duration -of csv=p=0 "$f")
  awk -v v="$vd" -v a="$ad" -v t="$tol" \
    'BEGIN{d=v-a; if(d<0)d=-d; if(d<=t){printf "v=%.3f a=%.3f Δ=%.3fs\n",v,a,d; exit 0} else {printf "A/V DRIFT v=%.3f a=%.3f Δ=%.3fs > %.3f\n",v,a,d,t; exit 1}}'
}

echo "== video-cut E2E smoke ($TMP) =="

TEXT="Ninety percent of what a web agent does is completely wasted. We fixed this today."

# 1. synthesize speech audio (say -> espeak -> sine fallback)
HAVE_SPEECH=0
if command -v say >/dev/null 2>&1; then
  say -o "$TMP/speech.aiff" "$TEXT"; AUDIO="$TMP/speech.aiff"; HAVE_SPEECH=1
elif command -v espeak-ng >/dev/null 2>&1; then
  espeak-ng -w "$TMP/speech.wav" "$TEXT"; AUDIO="$TMP/speech.wav"; HAVE_SPEECH=1
else
  ffmpeg -y -f lavfi -i "sine=frequency=220:duration=6" "$TMP/speech.wav" >/dev/null 2>&1
  AUDIO="$TMP/speech.wav"
fi
[ -s "$AUDIO" ] && pass "synthesized audio ($([ $HAVE_SPEECH = 1 ] && echo speech || echo sine))" || fail "no audio"

# 2. mux onto a test video pattern
ffmpeg -y -f lavfi -i "testsrc=size=640x360:rate=30" -i "$AUDIO" -shortest \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -ar 48000 -ac 2 "$TMP/clip.mp4" >/dev/null 2>&1
[ -s "$TMP/clip.mp4" ] || fail "clip.mp4 not produced"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TMP/clip.mp4")
pass "built clip.mp4 (${DUR}s)"

# 3. transcribe locally (real ASR if we have speech), else synthetic transcript
if [ "$HAVE_SPEECH" = 1 ]; then
  "$PY" "$SCRIPTS/transcribe_local.py" "$TMP/clip.mp4" --model "$MODEL" --edit-dir "$EDIT" \
    || fail "transcribe_local.py failed"
  WORDS=$("$PY" -c "import json,sys; d=json.load(open('$EDIT/transcripts/clip.json')); print(len(d['words']))")
  [ "$WORDS" -gt 0 ] || fail "transcript has no words"
  pass "transcribed locally: $WORDS words (model=$MODEL)"
else
  cat > "$EDIT/transcripts/clip.json" <<JSON
{"source":"$TMP/clip.mp4","source_hash":"synthetic","duration":$DUR,"language":"en",
"model":"synthetic","words":[
 {"word":"Ninety","start":0.30,"end":0.70,"prob":0.9,"speaker":null},
 {"word":"percent","start":0.75,"end":1.20,"prob":0.9,"speaker":null},
 {"word":"wasted","start":2.60,"end":3.10,"prob":0.9,"speaker":null},
 {"word":"fixed","start":4.20,"end":4.60,"prob":0.9,"speaker":null}],
"segments":[]}
JSON
  pass "synthetic transcript written (no TTS available)"
fi

# 4. pack
"$PY" "$SCRIPTS/pack_transcripts.py" --edit-dir "$EDIT" >/dev/null || fail "pack failed"
grep -q "## clip" "$EDIT/takes_packed.md" || fail "takes_packed.md missing header"
pass "packed -> takes_packed.md"

# 5. author an EDL cutting two segments, with burned subtitles
cat > "$EDIT/edl.json" <<JSON
{"version":1,"sources":{"clip":"$TMP/clip.mp4"},
"ranges":[
 {"source":"clip","start":0.3,"end":2.0,"beat":"HOOK","grade":"warm_cinematic"},
 {"source":"clip","start":2.3,"end":4.0,"beat":"PAYOFF"}],
"grade":"neutral_punch","fade_ms":30,"pad_ms":60,"overlays":[],
"subtitles":{"mode":"burn","style":"bold-overlay","chunk_words":2},
"output":"edit/final.mp4"}
JSON
pass "authored edl.json (2 ranges, burn subs)"

# 6. render
"$PY" "$SCRIPTS/render.py" "$EDIT/edl.json" >/dev/null || fail "render.py failed"
[ -s "$EDIT/final.mp4" ] || fail "final.mp4 not produced"
FDUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$EDIT/final.mp4")
# expected ~ (1.7 + 1.7) + 4*0.06 padding = ~3.64s
awk -v d="$FDUR" 'BEGIN{exit !(d>2.8 && d<4.8)}' || fail "final duration $FDUR out of expected range"
VS=$(ffprobe -v error -select_streams v -show_entries stream=codec_type -of csv=p=0 "$EDIT/final.mp4")
AS=$(ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 "$EDIT/final.mp4")
[ "$VS" = "video" ] || fail "no video stream"
[ "$AS" = "audio" ] || fail "no audio stream"
pass "rendered final.mp4 (${FDUR}s, video+audio)"
SYNC=$(av_sync_ok "$EDIT/final.mp4" 0.06) || fail "single-source A/V drift: $SYNC"
pass "A/V in sync ($SYNC)"
[ -s "$EDIT/master.srt" ] || fail "master.srt not produced"
pass "subtitles burned (master.srt non-empty)"

# 7. preview path
"$PY" "$SCRIPTS/render.py" "$EDIT/edl.json" --preview >/dev/null || fail "preview render failed"
[ -s "$EDIT/preview.mp4" ] || fail "preview.mp4 not produced"
PH=$(ffprobe -v error -select_streams v -show_entries stream=height -of csv=p=0 "$EDIT/preview.mp4")
[ "$PH" = "720" ] || fail "preview height $PH != 720"
pass "preview.mp4 rendered at 720p"

# 8. timeline_view
"$PY" "$SCRIPTS/timeline_view.py" "$TMP/clip.mp4" 0 2 -o "$EDIT/verify/tv.png" >/dev/null || fail "timeline_view failed"
[ -s "$EDIT/verify/tv.png" ] || fail "timeline_view png not produced"
pass "timeline_view.py -> verify/tv.png"

# 9. self_eval
"$PY" "$SCRIPTS/self_eval.py" "$EDIT/edl.json" "$EDIT/final.mp4" --json > "$TMP/eval.json" \
  || fail "self_eval failed"
"$PY" -c "import json; r=json.load(open('$TMP/eval.json')); assert 'ok' in r and 'boundaries' in r; print('  eval boundaries:', len(r['boundaries']), 'ok:', r['ok'])"
pass "self_eval.py produced a report"

# 10. multi-source / mixed-resolution / silent source / absolute -o
#     (regression coverage for the P20 cross-review findings 1-4)
echo "-- multi-source / silent / -o --"
if [ "$HAVE_SPEECH" = 1 ]; then
  if command -v say >/dev/null 2>&1; then
    say -o "$TMP/s2.aiff" "This is the second camera angle for the montage."; A2="$TMP/s2.aiff"
  else
    espeak-ng -w "$TMP/s2.wav" "This is the second camera angle for the montage."; A2="$TMP/s2.wav"
  fi
else
  ffmpeg -y -f lavfi -i "sine=frequency=330:duration=4" "$TMP/s2.wav" >/dev/null 2>&1; A2="$TMP/s2.wav"
fi
# clip2 at a DIFFERENT resolution (320x240); broll is SILENT (no audio) at a THIRD res (480x360)
ffmpeg -y -f lavfi -i "testsrc=size=320x240:rate=30" -i "$A2" -shortest \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -ar 48000 -ac 2 "$TMP/clip2.mp4" >/dev/null 2>&1
ffmpeg -y -f lavfi -i "testsrc2=size=480x360:rate=30:duration=3" -an \
  -c:v libx264 -pix_fmt yuv420p "$TMP/broll.mp4" >/dev/null 2>&1
[ -s "$TMP/clip2.mp4" ] && [ -s "$TMP/broll.mp4" ] || fail "multi-source clips not built"
pass "built clip2 (320x240, audio) + broll (480x360, SILENT)"

if [ "$HAVE_SPEECH" = 1 ]; then
  "$PY" "$SCRIPTS/transcribe_local.py" "$TMP/clip2.mp4" --model "$MODEL" --edit-dir "$EDIT" >/dev/null \
    || fail "clip2 transcribe failed"
else
  cp "$EDIT/transcripts/clip.json" "$EDIT/transcripts/clip2.json"
fi
# broll intentionally has NO transcript (tests subtitles built from available sources)

OUT="$TMP/exported_final.mp4"   # absolute path OUTSIDE edit/
cat > "$EDIT/edl_multi.json" <<JSON
{"version":1,"sources":{"clip":"$TMP/clip.mp4","clip2":"$TMP/clip2.mp4","broll":"$TMP/broll.mp4"},
"ranges":[
 {"source":"clip","start":0.3,"end":1.8,"grade":"warm_cinematic"},
 {"source":"broll","start":0.0,"end":1.0,"grade":"neutral_punch"},
 {"source":"clip2","start":0.3,"end":1.6}],
"grade":"neutral_punch","fade_ms":30,"pad_ms":60,"overlays":[],
"subtitles":{"mode":"burn","style":"natural-sentence","chunk_words":4},
"output":"edit/final.mp4"}
JSON
"$PY" "$SCRIPTS/render.py" "$EDIT/edl_multi.json" -o "$OUT" 2>"$TMP/multi.log" \
  || { cat "$TMP/multi.log"; fail "multi-source render failed"; }
[ -s "$OUT" ] || fail "[finding 2] -o absolute path not honored ($OUT missing)"
pass "multi-source rendered to absolute -o"
DIMS=$(ffprobe -v error -select_streams v -show_entries stream=width,height -of csv=s=x:p=0 "$OUT")
[ "$DIMS" = "640x360" ] || fail "[finding 3] canvas not normalized (got $DIMS, want 640x360)"
pass "canvas normalized to 640x360 across 3 mixed-res sources (concat valid)"
AS2=$(ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 "$OUT")
[ "$AS2" = "audio" ] || fail "[finding 4] output lost audio due to the silent source"
pass "audio preserved despite a silent source (anullsrc synthesized)"
SYNC2=$(av_sync_ok "$OUT" 0.06) || fail "[finding B] multi-source A/V drift across seams: $SYNC2"
pass "A/V in sync across 3 cuts incl. silent seam ($SYNC2)"
[ -s "$EDIT/master.srt" ] || fail "[finding 4] subtitles dropped despite available transcripts"
pass "subtitles built from available transcripts (silent broll skipped)"
"$PY" "$SCRIPTS/self_eval.py" "$EDIT/edl_multi.json" "$OUT" --json > "$TMP/eval2.json" \
  || fail "multi self_eval failed"
"$PY" - "$TMP/eval2.json" <<'PYEOF'
import json, sys
r = json.load(open(sys.argv[1]))
ct, td = r["computed_total_s"], r["total_duration_s"]
assert td is not None and abs(ct - td) < 0.35, f"[finding 1] self_eval misaligned: computed={ct} rendered={td}"
print(f"  self_eval aligned: computed={ct:.2f}s rendered={td:.2f}s, boundaries={len(r['boundaries'])}")
PYEOF
pass "self_eval timeline matches clamped render (finding 1)"

echo "== ALL SMOKE CHECKS PASSED =="
