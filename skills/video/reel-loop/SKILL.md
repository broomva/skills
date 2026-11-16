---
name: reel-loop
category: video
description: |
  Run one short-form account as a loop: find the reels in a niche that broke out
  against their own creator's normal, take the best one apart (hook, structure,
  shots), write a new script in the account's own voice, produce it (narration,
  scenes, word-by-word captions), stop for a person's approval, publish to Instagram
  through the Graph API, measure at 48 h and 7 d, and push variants of winners as
  Trial Reels to non-followers. A composition skill: research, voice, render and
  layout come from sibling skills; the arithmetic (outlier and winner scores) and
  the publish gate live in a tested script, so no step past the approval is
  reachable without an approval bound to the exact rendered bytes.
  USE WHEN: "reel loop", "content machine", "find viral reels in my niche and remake
  them", "outliers in my niche", "x times their normal", "nightly content run",
  "remix the winners", "trial reels", "make reels while I sleep", "content-os",
  "/reel-loop". NOT FOR: editing raw footage into a cut with no loop around it
  (video-cut), one cinematic generation or brand compile (content-engine), a
  multi-account portfolio with canon and spend ledgers (that is the
  agentic-media-studio initiative, which runs one reel-loop per account lane), or
  reposting someone else's video (never).
  Triggers on: reel loop, viral outliers, niche outliers, reel remix, trial reels,
  nightly content, content machine, reel-loop.
license: MIT
primitive: null
required: false
introduced_in: "0.51.3"
---

# reel-loop

One account, one loop, one human button.

```
SENSE → OUTLIERS → DECONSTRUCT → SCRIPT → PRODUCE → QC → [APPROVE] → PUBLISH → MEASURE → TRIAL → LEARN
  1        2           3            4         5       6       7          8         9        10      11
```

Stages 1–6 may run unattended (for example nightly). Stage 7 is a person. Stage 8
refuses to run without stage 7's approval for the exact file being published. That
refusal is code (`scripts/reel_loop.py payload`), not a sentence in this file.

The pattern comes from a creator's reel (`@davidmadrazo.ia`, 2026-11-12) showing
Claude doing stages 1–10 every night at 03:55 while he only presses "Aprobar". Its
open counterparts are his free `crecer` plugin (stages 1–4, read-only) and
AttentionOS (stages 1–4 and 8–10, human-filmed video). Neither has a cloned-voice
render or an approval bound to bytes. Survey and per-stage alternatives:
[references/stage-map.md](references/stage-map.md).

## The account folder

Everything for one account lives in one folder. Inside the agentic-media-studio
repo, use `accounts/<handle>/`. Anywhere else, use any folder:

```
<account>/
├── voice.md            how the account talks: 3+ real samples, words it never uses
├── niche.tsv           seed accounts to watch (handle, why), 6–20 rows
├── rules/hooks.md      the hook rulebook, grown from what won (starter: references/script-card.md)
├── consent/voice.md    dated consent of the person whose voice is cloned (required to clone)
├── runs/<date>/        one folder per run: reels.tsv, outliers.json, cards, scripts, renders
└── posts.tsv           our published posts: id, published_at, views, is_trial, source_url
```

Missing `voice.md`, `niche.tsv` or `consent/voice.md`: create it with the person once
(3 questions, not a form), then never ask again.

## Stages

### 1 · Sense: collect view counts for the niche

Pick the first route that works. Never use the publishing account's session for
collecting anything.

1. **Official (preferred):** Business Discovery returns `view_count` for another
   professional account's reels (Facebook Login path; details in
   [references/platform-contract.md](references/platform-contract.md)). It only
   works for handles you already know, so `niche.tsv` is the input.
2. **A person's browser at a human pace:** a read-only pass over `/<handle>/reels/`
   for each seed account, at most 10 accounts per pass, seconds apart. Stop at any
   login wall or warning. This is the `crecer` method.
3. **Pasted numbers:** the person reads the counts off the grid.

Write `runs/<date>/reels.tsv` with the header `account url views date hook`.
Counts can be copied as displayed ("12,3 mil", "1,2 M", "12.3K"); the script parses them.

### 2 · Outliers: compare against the creator's normal, not raw views

```bash
python3 scripts/reel_loop.py outliers runs/<date>/reels.tsv --json > runs/<date>/outliers.json
#   --bar 4 (x the account's normal)  --min-views 20000  --max-age-days 45  --min-sample 5
```

The baseline is the **leave-one-out median** of the account's *other* reels, so a
breakout cannot lift its own baseline. Accounts with fewer than `--min-sample`
other reels never pass. A million views on an account that always gets two
million is not an outlier, and the example file shows it
(`references/example-niche.tsv`). If too many reels pass, raise `--bar`. If none
pass, lower it to 3 and say so in the run note.

### 3 · Deconstruct the top 1–3

For each outlier, fill a **deconstruction card**
([references/script-card.md](references/script-card.md)):

- the hook in three layers: what is seen, what is said, what the on-screen text says;
- why viewers are still watching at 3 s;
- the turn;
- the call to action;
- a shot list with times.

Read the video only if downloads are allowed. If Business Discovery omits
`media_url`, or the owner turned downloads off, work from the caption and the page
text instead. When the download is allowed, run the workspace's
`scripts/video_ingest.py "$URL" --query "$Q" --keep-video`, passing both values
through exported variables. Then read its contact sheet and transcript.

Its speech recognition is English-only today (BRO-3796). On a non-English reel it
returns a placeholder like "(speaking in foreign language)" and reports low speech.
In that case, extract the audio with `ffmpeg -i video.mp4 -ar 16000 -ac 1 a.wav` and
run `whisper-cli -m <ggml-small.bin> -l <lang> -f a.wav`. **Copy the structure, never the wording, footage or
audio.**

### 4 · Script, in the account's voice

Write `runs/<date>/script-<n>.md` from the card:

- **HOOK:** 3 candidates, scored against `rules/hooks.md`, with the best one marked.
- **STRUCTURE:** the beats lifted from the reference.
- **BODY:** our topic, written in the voice of `voice.md`.
- **CTA:** the call to action.

Time every line: 20–35 s total, about 2.5 words per second. Run the draft through
`humanizer` or `unslop` if they are installed. A script that could only have come
from the reference's topic is a copy: rewrite it.

### 5 · Produce

| Layer | Default | Alternatives |
|---|---|---|
| Narration | `omnivoice` local clone (`generate_speech` with the cloned `profile_id`), only with `consent/voice.md` present | ElevenLabs IVC, or the person records it |
| Scenes | `content-engine` generate (Higgsfield / Veo), from the script's shot list | `video-cut` on real footage; Remotion scenes |
| Word-by-word captions | `brainrot-for-good` `/subtitle-generation` (Remotion `createTikTokStyleCaptions`) | `video-cut` burned subtitles |

Captions sit in the 9:16 caption band, not where Reels draws the username and
caption UI.

### 6 · QC

```bash
python3 ../content-engine/scripts/check_vertical_layout.py video runs/<date>/final-<n>.mp4 --expect-captions --expect-title
```

Fix and re-render until the check passes. Then write the post card,
`runs/<date>/card-<n>.json`, using the schema in
[references/post-card.md](references/post-card.md). It records:

- the source reel and its ratio;
- the script path;
- which media are synthetic;
- the voice-consent reference;
- the caption;
- `trial: null` for a normal post.

### 7 · Approve (a person)

Put one approval in front of the person. A Maestro ask, an `AskUserQuestion` or a
chat message are all fine. It must show:

- the render;
- the source reel next to it, with its ratio;
- the script;
- the caption;
- what is synthetic;
- the cost.

On "yes", record the decision in the card:

```json
"approval": {"by": "<person>", "at": "<ISO time>", "video_sha256": "<sha256 of final-n.mp4>"}
```

The agent writes this block only after a yes, and only with the hash of the file the
person saw. **Never write an approval the person did not give.** An agent that
approves its own post has removed the only gate the loop has.

### 8 · Publish

```bash
python3 scripts/reel_loop.py payload runs/<date>/card-<n>.json --video runs/<date>/final-<n>.mp4 --video-url "$PUBLIC_URL"
```

The script exits 2 and lists every reason when:

- there is no approval;
- the approval names other bytes (a re-render needs a new approval);
- a voice is cloned with no consent record;
- the caption is over 2,200 characters, 30 hashtags or 20 @ tags;
- the codec, fps, duration or size breaks the Reels spec;
- the trial strategy is invalid.

`is_ai_generated` is forced to true whenever anything synthetic is declared. On
exit 0, post the printed parameters through the Graph API:

1. `POST /<IG_ID>/media`;
2. poll the container until `FINISHED`;
3. `POST /<IG_ID>/media_publish`.

A thin publishing layer such as Postiz, Upload-Post or Blotato also works if it
passes the same fields. Append the post to `posts.tsv`. Plan for 50 posts per 24 h.

### 9 · Measure

At 48 h and again at 7 d, pull the media insights: `views`, `reach`, `shares`,
`saved`, `reels_skip_rate` and `ig_reels_avg_watch_time`. Never use `plays` or
`impressions`, which were removed in 2025. Insights can lag up to 48 h, so a younger
post is reported as pending, not judged.

### 10 · Trial: push variants of winners to non-followers

```bash
python3 scripts/reel_loop.py winners posts.tsv > runs/<date>/winners.json
#   --bar 2 (x our trailing-30-day median)  --min-age-hours 48  --graduation SS_PERFORMANCE
```

For each winner, the script plans three variants:

- **hook:** a new first line and first frame;
- **color:** a new grade;
- **framing:** a new crop or layout.

Each variant goes back through stages 5–8 with `"trial": {"graduation_strategy":
"SS_PERFORMANCE"}`, so Instagram graduates it to followers only if it performs.
`MANUAL` graduation exists only in the app. Trial posts are left out of the
baseline.

Changing the variant is contested. One school reposts the proven winner unchanged
with a new caption (ericosiu's `trial-reel-distribution`). Treat that as a
registered experiment, not a default. Pick the arm before posting, write the
prediction down, and judge it at 7 d.

### 11 · Learn

Once a week, not after every post, compare outcomes with predictions:

- promote a hook pattern into `rules/hooks.md` only after it has won at least 2 of 3
  times;
- retire seed accounts that stop producing outliers.

Inside agentic-media-studio, this is the L2 playbook review: the account's
playbook changes by PR, and the evaluator is never edited in the same PR.

## Running it on a schedule

Schedule it only when the person asks: through the host's scheduler (T3
`schedule_task`, `/schedule`, or `/loop` for a session). A scheduled run does stages
1–6 and stops at stage 7 with one approval request, plus any due measurements
(stage 9). Nothing scheduled ever publishes.

## Hard rules

- Copy structure, never wording, footage, audio or a person's likeness. Credit the
  reference in the run note, not in the post.
- Clone a voice only with that person's dated consent on file. Declare synthetic
  media with `is_ai_generated`.
- Collect only from public professional accounts, at a human pace, without the
  publishing account's session. No likes, follows, comments or DMs from collection.
- No engagement pods, bought views or accounts posing as independent people.
- Comment-keyword DMs are out of scope here. If added, Meta allows one private reply
  per comment within 7 days.
- Every number in a run note comes from `reel_loop.py` output or a platform
  response, never from the agent's own arithmetic.

## Self-test

```bash
cd skills/video/reel-loop && python3 -m pytest tests/ -q
python3 scripts/reel_loop.py outliers references/example-niche.tsv --now 2026-11-16
# expect exactly one outlier: @alpha /p/A6/, about 114x; @beta's 2.6M reel is not one
```
