# Reel Production — From Script to Published Reel

## The 3-Second Rule

Up to 50% of viewers drop off in the first 3 seconds. The hook determines everything. DM sends are the strongest algorithm signal for reach. Saves > Shares > Comments > Likes.

## Reel Structure (3-Act, 15-45s)

```
[0-3s]  HOOK — Pattern interrupt. Movement, bold text, surprising visual.
              Must answer: "Why should I stop scrolling?"
[3-Xs]  VALUE — Core content. One insight per beat. Fast pacing.
              B-roll every 5-12s. Text overlays reinforce audio.
[X-end] CTA — Clear action. "Follow", "Link in bio", "Save this".
              Keep under 3 seconds.
```

**Optimal length**: 15-45 seconds. A 15s reel with 80% retention beats a 60s reel with 30%.

## Hook Formulas (Proven)

| Type | Formula | When to Use |
|------|---------|-------------|
| Pattern interrupt | Unexpected visual + contrarian text | Technical content |
| Before/After | Show result first, then explain | Demos, transformations |
| Curiosity gap | "Nobody talks about this..." | Opinion, insider knowledge |
| Scale proof | "[Number] in [timeframe]" | Results, case studies |
| Direct challenge | "Stop doing X. Do this instead." | Tutorial, best practices |
| Motion hook | Camera movement toward subject in first frame | Any — visual hooks outperform text hooks |

**Rule**: Write the hook BEFORE the rest of the script. Spend 50% of creative effort here.

## Veo 3.1 Prompting (Cinematic Quality)

### 5-Part Prompt Formula

```
[Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance]
```

**Optimal length**: 3-6 sentences, 100-150 words.

### Camera Movement Vocabulary

Veo responds best to precise cinematographic terms:

| Movement | Prompt Language |
|----------|----------------|
| Push in | "Slow dolly forward" |
| Pull out | "Gentle dolly back revealing..." |
| Side track | "Tracking shot moving left-to-right at shoulder level" |
| Orbit | "Camera orbits 90 degrees clockwise around subject" |
| Crane | "Crane shot descending from overhead" |
| Handheld | "Handheld camera, subtle natural movement" |
| Static | "Locked-off tripod shot, no camera movement" |

### Shot Type Vocabulary

| Shot | Prompt Language |
|------|----------------|
| Close-up | "Extreme close-up on hands typing" |
| Medium | "Medium shot, waist up" |
| Wide | "Wide establishing shot" |
| Dutch angle | "Tilted Dutch angle shot" |
| POV | "First-person POV shot" |
| Over-shoulder | "Over-the-shoulder shot looking at screen" |

### Style Direction

Reference film genres, directors, or visual styles:
- "Film noir lighting, high contrast shadows"
- "Wes Anderson symmetrical framing, pastel palette"
- "Cyberpunk neon aesthetic, rain-slicked surfaces"
- "Clean minimal tech aesthetic, dark background, blue accent lighting"

### Key Rules

1. **One camera verb, one lighting motif, one action per clip** — avoid stacking
2. **Specify three motion layers**: primary (subject), camera-subject relationship, secondary (environment)
3. **Always specify aspect ratio**: "Vertical 9:16" for reels
4. **Don't over-prompt** — 100-150 words is the sweet spot
5. **Include audio direction** — Veo 3.1 generates native audio: "Ambient electronic hum", "Soft keyboard clicks"

### Example Prompts

**Tech terminal scene**:
> Medium shot, slow dolly forward. A developer's hands typing on a mechanical keyboard, screen reflecting in their glasses. Dark room, single monitor glow casting blue light. Shallow depth of field, focus on the screen showing code. Ambient electronic hum, soft keyboard clicks. Cyberpunk minimal aesthetic. Vertical 9:16.

**Data flow visualization**:
> Crane shot descending. Abstract luminous data streams flowing through a dark void, splitting into branching paths. Electric blue and cyan particle effects. Each branch terminates at a glowing node. No people. Futuristic, clean, technical. Subtle ambient synthesizer. Vertical 9:16.

**Platform success**:
> Locked-off tripod shot. A minimal dark interface showing four card elements. One by one, each card receives a bright green checkmark with a satisfying spring animation. Clean design, electric blue accents turning green. Soft chime on each checkmark. Vertical 9:16.

## Subtitle & Text Overlay Best Practices

### Design Rules

- **Font**: Sans-serif, high contrast (white on dark semi-transparent bg)
- **Placement**: Lower third, within safe zones (5-10% inside frame edges)
- **Duration**: Each text element on screen 1-2 seconds
- **Sync**: Frame-level precision with audio — never early, never late
- **Size**: Large enough for mobile viewing (minimum 40px equivalent)

### Subtitle Generation

```bash
# Generate SRT from audio using whisper
whisper media/mp3/narration.mp3 --output_format srt --output_dir media/

# Or use edge-tts subtitles
edge-tts --text "..." --write-subtitles media/subtitles.srt

# Burn subtitles into video with ffmpeg
ffmpeg -i input.mp4 -vf "subtitles=media/subtitles.srt:force_style='FontName=Arial,FontSize=24,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Alignment=2'" output.mp4
```

### Text Overlay in Remotion

```jsx
// Use <Sequence> for timed text overlays
<Sequence from={0} durationInFrames={72}>
  <AbsoluteFill style={{justifyContent: 'flex-end', padding: 40}}>
    <div style={{
      background: 'rgba(0,0,0,0.7)',
      padding: '12px 24px',
      borderRadius: 8,
      fontSize: 32,
      color: 'white',
      fontFamily: 'Inter, sans-serif',
    }}>
      One sentence. Nine phases. Seven platforms.
    </div>
  </AbsoluteFill>
</Sequence>
```

## Production Pipeline

### Option A: Pure Veo 3.1 (AI-native, fastest)

```
Script → Veo prompts (1 per scene) → Generate clips → ffmpeg concat → Burn subtitles → Host → Publish
```

1. Write scene prompts from reel script (use 5-part formula)
2. Generate clips sequentially (8s each, avoid rate limits)
3. Download with API key auth
4. Concatenate: `ffmpeg -f concat -i list.txt -c:v libx264 -movflags +faststart output.mp4`
5. Burn subtitles: `ffmpeg -i output.mp4 -vf subtitles=subs.srt final.mp4`
6. Push to broomva.tech for public hosting
7. Publish via Instagram API with `media_type=REELS`

### Option B: Veo + Remotion (hybrid, most control)

```
Script → Veo clips (B-roll) → Remotion composition (text, transitions, pacing) → Render → Host → Publish
```

1. Generate B-roll clips via Veo 3.1
2. Preprocess: `ffmpeg -i clip.mp4 -c:v libx264 -movflags +faststart -r 30 processed.mp4`
3. Build Remotion composition with `<OffthreadVideo>` + `<Sequence>` + text overlays
4. Render: `npx remotion render Reel --output reel.mp4`
5. Push + publish

### Option C: Screen Recording + Remotion (most authentic for dev content)

```
Screen recordings → Remotion composition → Text overlays + transitions → Render → Host → Publish
```

Best for: code demos, terminal walkthroughs, product showcases.

## Instagram Reel Publishing

```bash
IG_TOKEN=$(cat ~/.config/blog-post/instagram-token)
IG_USER=$(cat ~/.config/blog-post/instagram-user-id)

# Step 1: Create REELS container
CONTAINER=$(curl -s -X POST "https://graph.instagram.com/v19.0/$IG_USER/media" \
  --data-urlencode "media_type=REELS" \
  --data-urlencode "video_url=https://broomva.tech/videos/reel.mp4" \
  --data-urlencode "caption=Your caption" \
  --data-urlencode "share_to_feed=true" \
  --data-urlencode "access_token=$IG_TOKEN" | jq -r '.id')

# Step 2: Poll for FINISHED status
while true; do
  STATUS=$(curl -s "https://graph.instagram.com/v19.0/$CONTAINER?fields=status_code&access_token=$IG_TOKEN" | jq -r '.status_code')
  [ "$STATUS" = "FINISHED" ] && break
  sleep 10
done

# Step 3: Publish
curl -s -X POST "https://graph.instagram.com/v19.0/$IG_USER/media_publish" \
  -d "creation_id=$CONTAINER" -d "access_token=$IG_TOKEN"
```

## Video Requirements (Instagram Reels)

| Spec | Requirement |
|------|------------|
| Format | MP4 (H.264) |
| Aspect ratio | 9:16 (1080x1920 recommended) |
| Duration | 3-90 seconds (15-45s optimal) |
| Frame rate | 23-60 FPS (24 or 30 standard) |
| Audio | AAC, max 48kHz |
| Max file size | 100-300MB |
| Hosting | Must be publicly accessible URL |

## Quality Checklist (Reel-Specific)

- [ ] Hook grabs attention in first 3 seconds (visual OR text, not just narration)
- [ ] Subtitles burned in (80% watch on mute)
- [ ] Text overlays within safe zones
- [ ] Pacing: no static shot longer than 5 seconds
- [ ] Audio: voice narration OR trending music (never silence)
- [ ] CTA in final 3 seconds
- [ ] 9:16 vertical, minimum 720x1280
- [ ] Total duration 15-45 seconds
- [ ] File includes `-movflags +faststart` for streaming
