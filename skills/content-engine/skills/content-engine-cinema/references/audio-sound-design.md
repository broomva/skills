# Audio, Sound Design, and Edit Craft

> Distilled from the AI Video Creators course (BRO-1525) — see broomva/workspace docs/reference/ai-video-creators-course/.

The audio and editing layer is where AI-generated video stops looking like a tech demo and starts feeling like a story. The generation pipeline (see [cinematic-prompting.md](cinematic-prompting.md), [motion-animation.md](motion-animation.md), [upscaling-grading.md](upscaling-grading.md)) gets you clean, sharp, animated frames. This stage makes them *felt*. It is the most under-built part of most AI-video workflows and the cheapest one to do well.

## Why AI Video Feels Fake

There is exactly one reason raw AI video reads as synthetic: **it is silent and too perfectly smooth.** Real footage carries micro-pauses, environmental texture, handheld jitter, and a constant bed of ambient sound the brain expects but never consciously registers. AI output has none of that — every frame is clean, every motion is even, and there is no soundscape underneath. The viewer can't articulate what's wrong, but the brain flags it as unreal.

The cure is two disciplines applied in order:

1. **Rhythm** — cut the edit tight to a beat before you touch a single sound effect.
2. **A layered soundscape** — a 3-to-5-layer stack where voice dominates and everything else supports.

> The thesis to internalize: *visuals show; audio makes people feel.* A prompt gives you a pretty image. Editing and sound give it weight, rhythm, and emotion. Sound is not decoration — it is the moment AI output becomes a story.

## The Audio Trailer Arc

Every strong audio track follows the same four-beat structure as a movie trailer. Map your soundscape onto this arc and align the audio peak with the visual high point.

```
HOOK → BUILD → CLIMAX → RESOLUTION
```

| Beat | Job | Audio move |
|------|-----|------------|
| **Hook** | Grab attention instantly | A dramatic SFX, a powerful voice statement, or a memorable musical cue in the first second |
| **Build** | Develop tension / intensify emotional connection | Gradually layer in more sound; rising music; introduce ambience and foley |
| **Climax** | Emotional peak | Audio peak aligns with the visual high point — the loudest, fullest moment |
| **Resolution** | Land softly, leave them intrigued | Smooth ending that satisfies but leads into the call to action |

**Why this works:** the brain reads audio dynamics as narrative shape. A track that just plays flat under the visuals feels like a slideshow; a track that builds and releases feels like a film. The arc is content-agnostic — it works for a luxury commercial, a UGC skit, or a 15-second product reel.

## The Layer Stack (3–5 Layers)

Professional audio is 3 to 5 layers working together. Build them in priority order. **The hard rule that governs the whole stack: voice always dominates.** Music and effects support; they never overpower.

```
1. VOICE / VOICEOVER   (MAIN — the narrative spine; ALWAYS dominates)
2. MUSIC               (mood + pace)
3. SFX                 (impact + emphasis + transitions)
4. AMBIENCE            (realism — crowd, city, nature, room tone)
```

For short-form especially, the same idea collapses into a **3-layer build** with named roles — this is the version you reach for on a 20–30 second clip:

| Layer | Role name | What it is | What it does |
|-------|-----------|-----------|--------------|
| 1 | **Ambience** ("World Glue") | Room tone, street noise, wind, low hum | Continuity + realism across cuts |
| 2 | **Foley** ("Human Details") | Footsteps, cloth, hand taps, object contact | Human presence; "someone is actually there" |
| 3 | **Impact & Transitions** | Whooshes, hits, UI clicks, risers, glitches | Makes cuts feel deliberate, not accidental |

**Build sequence:** start with a low ambience bed → add foley *only when contact happens* on screen → use impacts *only when a cut carries meaning*. Layering up from ambience prevents the two most common failures (see Common Mistakes below).

**Why this works:** ambience is the missing layer that makes AI video feel real — without a continuous background tone, every shot sounds like it was recorded in a different universe, which is exactly the "too smooth / disconnected" tell. Foley supplies the human micro-detail the model can't generate. Impacts are punctuation, not decoration.

### Supporting mappings

The stack gets richer once you map sound character and genre to emotional intent.

**Sound character → emotional response:**

| Sound character | Emotional response |
|---|---|
| Fast / high-pitched / rapid | Excitement, urgency |
| Slow / low / steady | Trust, seriousness |
| Sharp / sudden | Grabs attention instantly |
| Soft / smooth / gentle | Calm, soothing |

**Genre → sonic direction:**

| Vertical | Sound direction |
|---|---|
| Tech | Synthetic / glitchy |
| Luxury | Cinematic strings / ambient textures (or minimalist electronic for modern sophistication) |
| Sport | Energetic, percussive |

**Voice type → perception (the trust layer):**

| Content type | Voice choice |
|---|---|
| Professional / corporate | Clear, authoritative — confidence + credibility |
| Youthful / entertaining | Energetic, vibrant — enthusiasm + playfulness |
| Serious / dramatic | Deeper, slower-paced — emotional resonance |
| International audience | Regional accents / multilingual VO — boosts relatability |

## SFX as Punctuation

Sound effects are punctuation marks. They add rhythm, emphasis, and clarity to a cut the same way commas and exclamation points do to a sentence. There are four core types:

| SFX | Use case |
|---|---|
| **Whoosh** | Scene transitions / camera movements |
| **Swish** | A subtler whoosh — light text animations, light motion |
| **Riser** | Builds anticipation; great before a punchline, reveal, or CTA |
| **Hit** | Impact / emphasis on a beat |

**The trim rule: keep every SFX under 0.5 seconds.** A punctuation mark is short by definition. Long, lingering effects stop being punctuation and start being noise. Trim tight; let the sound land and get out of the way.

**The volume rule: SFX support the voice, they never fight it.** Drop each effect on the exact action frame, set it well below the voice, soften the harsh attack (the hard "wall" at the start of a sound) with a short fade-in, and move on.

### Verbatim ElevenLabs SFX prompts

ElevenLabs has a text-to-SFX tab (Sound Effects). The rule that frames every prompt: **be specific and short — precision equals cleaner results.** State the sound, the character, and an explicit duration. These are the exact prompts from the course:

```
airy whoosh, 0.3s
```

```
crisp UI click, 0.1s
```

```
cinematic hit, low bass, 0.2s
```

**Why this works:** the duration in the prompt does double duty — it tells the model how long to generate *and* it forces you to commit to a sub-0.5s punctuation mark before you generate. "Specific and short" beats "epic, dramatic whoosh transition with rising tension" every time; the model has less room to add unwanted texture, so the output is clean and trimmed-to-fit on arrival. Pattern: `<character> <sound type>, <duration>`. Extend it the same way for your own library — `deep rumbling riser, 0.8s`, `glitchy digital swish, 0.2s`, `wooden footstep on concrete, 0.15s`.

ElevenLabs returns **4 versions** per SFX prompt — generate, audition all four, pick the cleanest. Regeneration is unlimited, so iterate until it fits.

## The Named-Role Discipline

This is the single rule that separates intentional sound design from slop:

> **Every sound must have a named role. If you can't name it as Ambience, Foley, or Impact — cut it.**

The workflow that enforces it:

1. Build a rough cut with **no sound effects at all**.
2. Play it once and drop a **marker** on every moment you want the viewer to *feel* — a reveal, a transition, a punchline, a zoom, a text pop.
3. For each marker, assign **exactly one** sound role (Ambience / Foley / Impact). If you cannot name the role, do not add a sound there.
4. Generate or source the SFX for each named marker.
5. Trim tight (under 0.5s), level carefully (under the voice).

**Why this works:** the default failure mode of every beginner is to add sounds because they *can*, not because the moment *needs* one. Requiring a named role per sound makes you justify each effect before it goes in. It also caps density automatically — **one cut = one intention = at most one SFX.** Stacking three loud effects on a single cut is how you get the "wall of noise" problem.

## The A/B Mute Test — The Quality Gate

The objective, repeatable validation move for sound design. It is the audio equivalent of running the app to verify a code change — you judge by *listening*, not by reasoning about whether the mix is good.

```
1. Pick a 5-second span of the edit.
2. Watch it with ALL SFX muted.
3. Watch the same 5 seconds with SFX unmuted.
4. If version B (with sound) feels more real / more emotional → it works. Done.
   If it feels the same or worse → the sound isn't earning its place. Cut or rework it.
```

**Why this works:** the picture is identical in both passes, so the only variable is sound. Your brain will believe version B even though nothing visual changed — that belief gap *is* the value the sound layer adds, made measurable. Run this test on every span. "Compare before/after every time" is the discipline; the mute test is the mechanism. If you can't feel the difference, the sound is noise.

## Voice Generation — ElevenLabs

The voiceover is the dominant layer, so it gets the most care. Use **ElevenLabs V3** for the actual voiceover — it delivers "truly emotional and high-quality" output, with control over pacing, intonation, and (in the latest version) emotion. Note: model versions rotate; V3 is the current high-emotion tier, but the discipline (use the highest-emotion tier available, audition multiple options, regenerate weak lines) outlives any version number.

**Predictable option counts** — useful because regeneration is free and unlimited, so iterate until it's right:

| ElevenLabs flow | Options returned |
|---|---|
| Create a New Voice | **3** voice options |
| Text-to-Speech (TTS) | **2** generated versions |
| Sound Effects (SFX) | **4** versions |

### Voice workflow

1. **Generate the voice prompt** from your script — many course workflows have the script-engine GPT produce a tailored ElevenLabs voice prompt automatically ("create a prompt specifically for this script"). The exact auto-generated prompt isn't fixed text; it's derived per script.
2. **Create the voice** — ElevenLabs → "Create a New Voice" → paste the voice prompt → paste a portion of the script into the "text to preview" field → Generate. Pick the best of 3. Regenerate if none fit.
3. **Save the voice** — give it a name and **assign a language tag** (e.g. "English"). Saving without a language tag is a common miss.
4. **Generate the voiceover (TTS)** — Text-to-Speech → select your saved voice → paste the **full script** → **set version to V3** → Generate. Pick the best of 2. Regenerate the whole thing, or just a single line/section, for more emotion. Download.

**Why this works:** generating the voice first (with a short preview) and *then* running the full script as TTS lets you lock the timbre before committing the full read — and per-line regeneration means one flat sentence doesn't force you to redo the entire narration.

## Editing: Rhythm Before Sound

The cardinal rule of the edit: **tight rhythm first, sound second.** Get the cut tight before you add a single effect. A perfectly sound-designed edit on top of sloppy timing still feels amateur; a tightly timed edit feels professional even before sound goes on.

### Cut to the beat

```
1. Choose your tempo:
   - a music track / metronome beat, OR
   - (no music) the voiceover pulse — cut on stressed words.
2. Cut shots TO the beat (or to stressed words).
3. Shift each cut 1–2 frames EARLIER than feels natural.
4. Remove dead air aggressively.
```

**The beat math: one beat ≈ 4 bars / 4 kick drums** ("boom — boom — boom — boom"). Land your key actions on the kicks: a head crash hits on the drop, a tennis swing lands at the end of the bar pattern. For AI clips that generate in slow-motion by default (Kling and similar always do), retime each clip — often ~2× faster — so the key action lands on a kick.

**Why the 1–2 frame early shift matters:** even a 2-frame-earlier cut reads as "pro." Cutting slightly before the action completes keeps the edit feeling propulsive and removes the hesitation/dead space that makes amateur edits drag. This single move — shift cuts earlier, kill dead air — does more for perceived quality than any effect.

### Cut craft heuristics

- **Cut on motion** — start the next shot while something is already moving (mid-action), so the cut hides in the movement.
- **J-cuts and L-cuts** — let audio lead the visual (J) or trail it (L) so cuts feel seamless rather than abrupt.
- **Vary visual rhythm** — alternate background colors / settings between consecutive shots (don't run orange-floor → orange-floor → orange-floor; drop a green-grass shot between).
- **Duck the music under important phrases** — auto-dip music volume under the voice. Premiere and Descript can automate this (ducking); in CapCut do it with volume keyframes.
- **Silence is a tool, not a gap to fill** — well-placed pauses create tension and focus. Confident creators embrace quiet; most beginners rush to fill every second with noise, which is itself a tell.

### Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| **Too many whooshes** | Every cut has a loud transition → it all becomes noise | One cut = one intention = max one SFX |
| **No ambience bed** | Every shot feels like a different universe | Start with a low continuous ambience layer |
| **Music overpowering the voice** | Can't make out the narration | The #1 thing to fix first — lower music until voice clearly dominates |
| **Overloading with SFX** | Wall of sound, no impact lands | Embrace quiet; cut anything without a named role |

## CapCut Export Discipline

CapCut is the editor for this whole stage — free tier ships everything core (timeline, keyframes, animation presets, transitions, basic color, masks, freeze, copy-attributes). Export settings are where most people lose quality without realizing it.

| Setting | Value | Why |
|---|---|---|
| **Resolution** | **1080p (HD)** | The sweet spot for Reels/TikTok/Shorts. AI Ultra HD export is paid. |
| **Format** | **MP4** | Universal |
| **Codec** | **H.264** | Most-used, recommended, universally compatible |
| **Frame rate** | Same as project (24 or 30 fps; 24 = cinematic) | Match the timeline |
| **Bitrate** | Recommended / highest available | — |
| **Optical flow** | Optional ON | Smoother motion/transitions |
| **Separate audio track** | Uncheck | Rarely needed |

**The counterintuitive export rule: bigger files look *worse* after platform recompression.** Social platforms recompress every upload. A clean 1080p file survives that recompression better than an over-exported 4K/oversized file, which the platform mangles. Don't over-export. (Bonus: use scheduled publishing so the platform has time to compress at higher quality.)

> Scope: this is the **final social-delivery export** (Reels/TikTok/Shorts). It does **not** contradict producing high-res 4K *masters* upstream — grade and upscale the master (see [`upscaling-grading.md`](./upscaling-grading.md)), then render a clean 1080p for the platform from it.

**The hard blocking rule: if you used *any* paid feature anywhere in the project, CapCut refuses to render.** Paid features that block export include auto-captions, auto/custom background removal, most filters, the Enhance suite (noise reduction, stabilization, upscale), and AI Ultra HD export. Check before you render — discovering a single paid filter at export time after a full edit is the classic time-sink.

**Captions are mandatory for social** — a large share of viewers watch muted. CapCut's auto-captions are a *paid* feature (and will block export), so either upgrade, type captions manually with the free Text tool, or budget for Pro if captions are non-negotiable.

**Plan aspect ratio at generation time, not in the edit.** A 16:9 clip forced into a 9:16 project requires ~3× scale, shows only ~1/3 of the frame vertically, and drops quality. Generate in the target ratio (9:16 for shorts, 16:9 for YouTube) from the start. Fixing ratio in the edit always costs quality and time.

### CapCut free vs Pro

| Feature | Free | Pro (blocks export if used) |
|---|---|---|
| Timeline editing, split, trim | ✅ | |
| Keyframes (position, scale, rotation, opacity, color) | ✅ | |
| Animation presets (In / Out / Combo) | ✅ | |
| Transitions, effects (limited subset) | ✅ | |
| Basic color (temp, tint, saturation, exposure, contrast, highlights, shadows, HSL) | ✅ | |
| Masks, crop, freeze frame, reverse, mirror, rotate | ✅ | |
| Sound-effects library, text, stickers, shapes | ✅ | |
| Copy/paste attributes, speed (normal + curve) | ✅ | |
| **Auto captions / subtitles** | | 🔒 Pro |
| **Auto background removal (people)** + **Custom Removal** (rotobrush) | | 🔒 Pro |
| Most filters, the Enhance suite (denoise, stabilize, upscale, beauty) | | 🔒 Pro |
| **AI Ultra HD export** | | 🔒 Pro |
| Cloud "Space" collaboration, some voice-changer presets | | 🔒 Pro |

**The takeaway: the free tier is enough to ship.** Generate clean, high-quality clips upstream and you sidestep the entire Enhance paywall. The only features you genuinely have to decide on are auto-captions and advanced masking.

## Two Signature CapCut Techniques

### Keyframe zoom-in (manual)

A punch-in on an impact moment, done with two keyframes instead of an animation preset:

```
1. Keyframe 1 at the clip start — no change (scale 100%, default position).
2. Move the playhead to the action moment (e.g. the frame of impact).
3. Keyframe 2 there — increase scale (zoom in) and reposition onto the subject
   (e.g. zoom to the head on a crash).
→ CapCut animates the zoom linearly between the two keyframes.
```

**Gotcha:** the second keyframe must **not** sit on the very last frame of the clip, or the motion won't render — pull it one frame in. Keyframing works on position, scale, rotation, opacity, *and* color-correction values, so the same technique drives DIY fades and grade ramps.

**Why this works:** a zoom that lands exactly on the beat (paired with a hit SFX and a cut shifted 1–2 frames early) is the core "this feels designed" move — three cheap techniques stacking into one perceived-quality jump.

### Swipe-screen effect (hand swipes the frame)

Reverse-engineered in the course Q&A — and notably, it is **not a mask**. It's an image overlay with lowered opacity plus a movement animation:

```
1. Drop the overlay image on a layer above the clip; Crop it smaller to fit over the frame.
2. Animate the position: either
   - keyframe position (off-left → center → off-right), OR
   - simpler: In = slide left/right, Out = slide right (set X position to 0/center).
3. Lower the overlay's opacity so the screen reads semi-transparent.
→ Looks like a swiped phone screen passing across the shot.
```

**Why this works:** the brain reads a semi-transparent layer sliding across the frame as a physical screen being swiped — opacity sells the "glass," the slide animation sells the motion. No masking, rotobrushing, or paid features required.

## End-to-End Audio + Edit Workflow

The full sequence from finished clips to export-ready video:

```
1. ROUGH CUT (no sound)   → assemble clips on the timeline, no SFX yet.
2. RHYTHM                 → cut to the beat (4 bars / 4 kicks) or voiceover pulse;
                            retime AI slow-mo clips (~2×); shift cuts 1–2 frames early;
                            kill dead air.
3. MARKERS                → play once, drop a marker on every feel-it moment.
4. NAMED ROLES            → assign each marker exactly one role: Ambience / Foley / Impact.
                            Can't name it → no sound there.
5. VOICE                  → ElevenLabs V3 TTS (dominant layer); regenerate weak lines.
6. MUSIC                  → lay the bed; lower it until voice clearly dominates; duck under VO.
7. AMBIENCE               → low continuous bed for continuity (World Glue).
8. FOLEY                  → add only where on-screen contact happens (Human Details).
9. SFX / IMPACTS          → generate from verbatim prompts (under 0.5s); place on action frames;
                            soften attack; level under the voice.
10. A/B MUTE TEST         → for each span, mute vs unmute. If B feels more real, keep it. Else cut.
11. CAPTIONS              → mandatory for social (most watch muted).
12. EXPORT                → 1080p / MP4 / H.264 / project fps / recommended bitrate.
                            Verify NO paid feature is in use (or it won't render).
```

## Decision Rules (Quick Reference)

- **Voice always dominates.** Music sits under it; SFX stay short, quiet, controlled.
- **Every sound has a named role** (Ambience / Foley / Impact) — or it's cut.
- **One cut = one intention = max one SFX.** Never stack loud effects on a single cut.
- **Rhythm first, sound second.** Get the edit tight before any SFX.
- **Cut 1–2 frames earlier than comfortable.** Kill dead air aggressively.
- **SFX under 0.5s**, soften the attack, level under the voice.
- **Be specific and short** in SFX prompts — precision = cleaner results.
- **A/B mute test every span** — it's the objective quality gate.
- **Plan aspect ratio + quality at generation time**, never in the edit.
- **1080p / H.264 / MP4** — bigger files look worse after platform recompression.
- **Captions mandatory** for social; check no paid feature blocks export.
- **Silence is a tool** — confident creators embrace quiet over a wall of noise.
- **Repetition builds memory** — reuse a 1-second "sound logo" (a sting, or whoosh+click) before every video for brand recognition (cf. Netflix "ta-dum," McDonald's jingle).

> **Version note:** model names and tiers rotate fast — ElevenLabs V3, CapCut Pro's feature boundary, and the AI generators feeding this stage (Kling 3.0, Nano Banana Pro, Seedance 2.0) are all named at a specific moment. The *disciplines* here — the trailer arc, the named-role stack, rhythm-before-sound, the A/B mute test, export-for-recompression — are durable. The version numbers are not; re-verify the current tier before relying on a specific feature or free allotment.
