# Filmcraft Pipeline Contracts

Artifact and CLI handoff boundaries across the modular video production skills.
`filmcraft` routes and verifies across these boundaries without duplicating any
sibling implementation.

## Stage 1 — Reference Dissection (`scripts/video_ingest.py`)
- **Invocation**: `python3 scripts/video_ingest.py <url_or_path> --outdir work/ingest --keep-video`
- **Artifacts**:
  - `work/ingest/manifest.json` (carries `video_path` — note local inputs stay at their original path)
  - `work/ingest/contact_sheet.jpg`
  - `work/ingest/transcript.txt`
- **Probe**: `ffprobe -v error -show_format -show_streams <video_path_from_manifest>`

## Stage 2 — Setup & Asset Materialization
- **Preflight**: `python3 scripts/filmcraft.py doctor --json`
- **Liquid Midnight** (optional): `node <skills-root>/liquid-midnight/scripts/materialize.mjs install work/scene --with templates`
- **Liquid Dawn** (optional): copy `assets/` from `<skills-root>/liquid-dawn/`

## Stage 3 — Production & Rendering
### Raw Footage (`video-cut`)
1. `python3 <skills-root>/video-cut/scripts/transcribe_local.py <raw_clip.mp4> --edit-dir edit`
2. `python3 <skills-root>/video-cut/scripts/unheard.py detect <raw_clip.mp4> --transcript edit/transcripts/<clip>.json --json --annotate-out edit/annotated.txt`
3. `python3 <skills-root>/video-cut/scripts/edit_plan.py validate edit/editPlan.json --check-files`
4. `python3 <skills-root>/video-cut/scripts/edit_plan.py render edit/editPlan.json -o out/final.mp4`

### Code-First Motion (`motion-lab`)
1. `python3 <skills-root>/motion-lab/scripts/motion_lint.py work/scene/index.html`
2. `node <skills-root>/motion-lab/scripts/render.mjs work/scene/index.html [--seconds S] --serve --workers 4 --webgl --verify --out out --mp4`
   - Outputs `out/anim.mp4` (video-only), `out/contact.png`, and `out/manifest.json`.
3. When audio is included (`soundcraft`), mux the mastered score before audio QA:
   `ffmpeg -y -i out/anim.mp4 -i work/audio/master.wav -c:v copy -c:a aac -b:a 192k -movflags +faststart -shortest out/final.mp4`

### Hybrid (`video-cut` + `motion-lab`)
1. Render footage cut to `work/footage-cut.mp4` via `edit_plan.py render`.
2. Render transparent RGBA motion overlay PNG sequence to `work/overlay/frames/%04d.png` via `render.mjs --transparent --out work/overlay` (avoiding opaque `yuv420p` MP4).
3. Create `out/` and composite over footage with `overlay=0:0:eof_action=pass` so underlying footage stays visible and full footage duration is preserved.

### Audio Visual Sheet (`soundcraft`)
- `python3 <skills-root>/soundcraft/scripts/audio_qa.py sheet <final.mp4> --out out/audio-qa-sheet.png`

## Stage 4 — Unified Delivery Gate (`filmcraft.py verify`)
- **Invocation**: `python3 scripts/filmcraft.py verify <mp4_path> [--expected-dur S] [--beats 0,24,48] [--skip-audio] [--skills-root DIR] --json`
- **Child invocations (resolved absolute media path)**:
  - Visual: `python3 <skills-root>/motion-lab/scripts/video_qa.py grade <abs_mp4> --json [--beats <indices>]` — must emit JSON with boolean `"pass"` (`true`/`false`).
  - Audio (unless `--skip-audio`): `python3 <skills-root>/soundcraft/scripts/audio_qa.py check <abs_mp4> --json [--expected-dur <sec>]` — must emit JSON with boolean `"passed"` (`true`/`false`).
- **Fail-closed exit codes**:
  - `0`: every required gate ran, exited `0`, and emitted an explicit JSON `pass`/`passed: true` verdict (and duration matched if `--expected-dur` was supplied).
  - `1`: at least one required gate ran and returned a measured failure (`exit 1` with JSON `pass`/`passed: false`, or duration mismatch).
  - `2`: missing MP4, missing required sibling gate (`skipped_missing_tool`), child operational/usage error (`exit >= 2`), or empty/malformed JSON without explicit boolean verdict.

## Security & Trust Boundary
- `--skills-root` selects a trusted sibling skills root from which `filmcraft.py verify` executes sibling Python scripts; it is **not** a filesystem sandbox and follows symlinks like normal local tooling.
- No remote daemon, SMS webhook, or `bypassPermissions` execution path exists in this skill.
