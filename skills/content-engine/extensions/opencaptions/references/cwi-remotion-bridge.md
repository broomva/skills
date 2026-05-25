# CWI-Remotion Bridge

This document specifies how CWI (Caption With Intent) document properties map to React components rendered by Remotion. The bridge translates the semantic CWI data model into visual CSS properties, animation timing, and layout constraints.

## CWI Spec Summary

CWI captions rest on three pillars:

### 1. Attribution

Every word is attributed to a speaker. Each speaker receives a unique color from a WCAG AA compliant palette. Attribution enables the audience to follow multi-speaker dialogue by sight alone.

### 2. Synchronization

Words appear precisely when spoken. Timestamps are word-level (not sentence-level). Animation follows a strict 600ms ease curve with 100ms delay. No gaps longer than 3 seconds during active speech. Maximum 42 characters per line (FCC compliant).

### 3. Intonation

The visual presentation encodes how something was said. Pitch maps to font weight (higher pitch = bolder text). Volume maps to font size (louder = larger). Emphasis words receive a 15% size bounce animation. At least 20% of words must have non-default weight to ensure the captions actually convey vocal variation.

### The 12 Rules

| ID | Pillar | Rule |
|---|---|---|
| ATT_001 | Attribution | Every caption has a speaker in the cast |
| ATT_002 | Attribution | Speakers have unique colors |
| ATT_003 | Attribution | Colors meet WCAG AA (4.5:1 contrast against #1a1a1a) |
| SYN_001 | Synchronization | All words have start/end timestamps |
| SYN_002 | Synchronization | Timestamps monotonically increasing |
| SYN_003 | Synchronization | Caption events do not overlap |
| SYN_004 | Synchronization | Animation duration 600ms |
| FCC_001 | Synchronization | No gaps > 3s during speech |
| FCC_002 | Synchronization | Max 42 chars per line |
| INT_001 | Intonation | Weight in valid range (100-900) |
| INT_002 | Intonation | Size in valid range (0.7-1.5) |
| INT_003 | Intonation | > 20% of words have non-default weight |

## CWIWord to React Component Mapping

Each `CWIWord` in a `CaptionEvent` becomes a `<CWIWordSpan>` React component. The mapping is deterministic: given the same CWI JSON, the visual output is identical across renders.

### Core Properties

```typescript
// CWI types (from @opencaptions/types)
type CWIWord = {
  text: string;
  start: number;        // seconds
  end: number;          // seconds
  weight: number;       // 100-900 (Roboto Flex wght axis)
  size: number;         // 0.7-1.5 (multiplier)
  emphasis: boolean;    // triggers bounce animation
  animation?: {
    duration_ms?: number; // default 600
    delay_ms?: number;    // default 100
    easing?: string;      // default "ease"
  };
};
```

### Property Mapping Table

| CWI Property | CSS/Remotion Property | Conversion |
|---|---|---|
| `weight` (100-900) | `fontWeight` | Direct: `fontWeight: word.weight` |
| `size` (0.7-1.5) | `fontSize` | Scaled: `fontSize: BASE_SIZE * word.size` |
| `emphasis` (boolean) | `textShadow` + scale animation | Glow: `textShadow: "0 0 20px {speakerColor}"` |
| `speaker_id` (from CaptionEvent) | `color` | Lookup: `color: cast.find(s => s.id === event.speaker_id).color` |
| `start` / `end` (seconds) | `useCurrentFrame()` visibility | Show word when `frame >= start * fps && frame <= end * fps` |

### Detailed Conversions

#### Font Weight (Pitch)

```typescript
// Direct mapping — CWI weight IS the CSS font-weight
// Requires Roboto Flex variable font loaded
const fontWeight = word.weight; // 100 (thin/whisper) to 900 (black/shout)
```

The weight axis maps perceptually: conversational speech clusters around 300-500, emotional peaks hit 600-800, and shouted words reach 900. Whispered words drop to 100-200.

#### Font Size (Volume)

```typescript
const BASE_SIZE = 48; // pixels at 1080p

// Size is a multiplier applied to base size
const fontSize = BASE_SIZE * word.size;
// Range: 48 * 0.7 = 33.6px (quiet) to 48 * 1.5 = 72px (loud)
```

The base size adjusts for resolution. At 720p use 32px, at 1080p use 48px, at 4K use 96px. The multiplier stays the same.

#### Emphasis (Glow + Bounce)

```typescript
const isEmphasis = word.emphasis;

// Glow effect via text-shadow
const textShadow = isEmphasis
  ? `0 0 20px ${speakerColor}, 0 0 40px ${speakerColor}40`
  : "none";

// Bounce animation via Remotion spring()
const emphasisScale = isEmphasis
  ? spring({
      frame: frame - wordStartFrame,
      fps,
      config: { damping: 12, stiffness: 200, mass: 0.8 },
    })
  : 1;

// The 15% bounce: scale peaks at 1.15, settles to 1.0
const scale = 1 + (emphasisScale > 1 ? 0 : emphasisScale * 0.15);
```

The glow uses a double text-shadow: an inner glow at full speaker color opacity and an outer glow at 25% opacity. This creates the characteristic CWI emphasis halo visible against dark backgrounds.

#### Speaker Color (Attribution)

```typescript
// Speaker color from the CWI document cast
const speaker = doc.cast.find(s => s.id === event.speaker_id);
const color = speaker?.color ?? "#FFFFFF";

// CSS application
const style = { color };
```

### Word Entrance Animation

Every word enters with a spring animation when its timestamp is reached. The CWI spec mandates: ease curve, 100ms delay, 600ms duration. In Remotion this translates to:

```typescript
import { spring, useCurrentFrame, useVideoConfig } from "remotion";

function CWIWordSpan({ word, speakerColor, eventStart }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const wordStartFrame = Math.round(word.start * fps);
  const wordEndFrame = Math.round(word.end * fps);
  const isVisible = frame >= wordStartFrame;
  const isActive = frame >= wordStartFrame && frame <= wordEndFrame;

  if (!isVisible) return null;

  // Entrance animation: 600ms duration, 100ms delay
  const delayFrames = Math.round(0.1 * fps); // 100ms
  const entrance = spring({
    frame: frame - wordStartFrame - delayFrames,
    fps,
    config: {
      damping: 15,
      stiffness: 120,
      mass: 1,
    },
  });

  // Color transition: white --> speaker color over 600ms
  const colorProgress = Math.min(1, (frame - wordStartFrame) / (0.6 * fps));
  const currentColor = isActive
    ? interpolateColor(colorProgress, "#FFFFFF", speakerColor)
    : speakerColor; // After active period, stays speaker color

  const opacity = entrance;
  const translateY = (1 - entrance) * 10; // Slide up 10px

  return (
    <span
      style={{
        fontFamily: "'Roboto Flex', sans-serif",
        fontWeight: word.weight,
        fontSize: BASE_SIZE * word.size,
        color: currentColor,
        textShadow: word.emphasis
          ? `0 0 20px ${speakerColor}, 0 0 40px ${speakerColor}40`
          : "none",
        opacity,
        transform: `translateY(${translateY}px) scale(${word.emphasis && isActive ? 1.15 : 1})`,
        transition: "transform 0.6s ease",
        display: "inline-block",
        marginRight: "0.3em",
      }}
    >
      {word.text}
    </span>
  );
}
```

## Speaker Color Palette

12 colors, all WCAG AA compliant (4.5:1 contrast ratio against #1a1a1a background). Colors are maximally distinct in CIE Lab space (deltaE >= 30 between any two).

| Index | Hex | Swatch | Perceptual Name |
|---|---|---|---|
| 0 | `#6B8AFF` | Blue | Cornflower Blue |
| 1 | `#FF6B6B` | Red | Coral Red |
| 2 | `#6BFFA3` | Green | Mint Green |
| 3 | `#FFD56B` | Yellow | Golden Yellow |
| 4 | `#D56BFF` | Purple | Orchid Purple |
| 5 | `#6BF0FF` | Cyan | Electric Cyan |
| 6 | `#FF6BC8` | Pink | Hot Pink |
| 7 | `#A3FF6B` | Lime | Lime Green |
| 8 | `#FF916B` | Orange | Salmon Orange |
| 9 | `#6BB4FF` | Light Blue | Sky Blue |
| 10 | `#FFB86B` | Amber | Warm Amber |
| 11 | `#8A6BFF` | Indigo | Deep Indigo |

Assignment: Speaker `S0` gets index 0 (`#6B8AFF`), `S1` gets index 1 (`#FF6B6B`), etc. Users can override via `cast_overrides` in the pipeline options or `speakers` in the extension config.

When brand identity is loaded from `compiled/brands/`, the extension checks if the brand palette overlaps with the speaker palette and adjusts to avoid collisions.

## CaptionOverlay Component

The top-level Remotion component that reads a CWI document and renders all caption events.

```typescript
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import type { CWIDocument, CaptionEvent, Speaker } from "@opencaptions/types";

type CaptionStyle = "word-by-word" | "narrative" | "minimal";

interface CaptionOverlayProps {
  cwiDocument: CWIDocument;
  style?: CaptionStyle;
  baseFontSize?: number;
  background?: "pill" | "shadow" | "gradient" | "none";
  backgroundOpacity?: number;
  position?: "top" | "center" | "bottom";
}

function CaptionOverlay({
  cwiDocument,
  style = "narrative",
  baseFontSize = 48,
  background = "pill",
  backgroundOpacity = 0.6,
  position = "bottom",
}: CaptionOverlayProps) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  // Find active caption events at the current time
  const activeEvents = cwiDocument.captions.filter(
    (e) => e.start <= currentTime && e.end >= currentTime
  );

  if (activeEvents.length === 0) return null;

  const positionStyle = {
    top: { top: "8%", bottom: "auto" },
    center: { top: "40%", bottom: "auto" },
    bottom: { top: "auto", bottom: "8%" },
  }[position];

  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: "5%",
          right: "5%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 12,
          ...positionStyle,
        }}
      >
        {activeEvents.map((event) => {
          const speaker = cwiDocument.cast.find(
            (s) => s.id === event.speaker_id
          );
          if (!speaker) return null;
          return (
            <CaptionEventRow
              key={event.id}
              event={event}
              speaker={speaker}
              style={style}
              baseFontSize={baseFontSize}
              background={background}
              backgroundOpacity={backgroundOpacity}
            />
          );
        })}
      </div>
    </AbsoluteFill>
  );
}
```

### Style Variants

**Word-by-word**: Only the currently active word is visible. Previous words fade. Next words are hidden. Maximum visual impact, one word at a time.

```typescript
// In word-by-word mode, only show the word whose time range includes currentTime
const visibleWords = event.words.filter(
  (w) => w.start <= currentTime && w.end >= currentTime
);
```

**Narrative**: All words in the caption event are visible. Active words are in speaker color, future words are dimmed, past words stay in speaker color.

```typescript
// In narrative mode, show all words but style them by timing state
const wordState = (w) => {
  if (w.start > currentTime) return "upcoming"; // dim gray
  if (w.end < currentTime) return "spoken";     // speaker color, no bold
  return "active";                               // speaker color, bold if emphasis
};
```

**Minimal**: Speaker name label followed by full text. Lower-third bar.

```typescript
// In minimal mode, render as: [Speaker Name]: full text
<div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
  <span style={{ color: speaker.color, fontWeight: 700 }}>
    {speaker.name}:
  </span>
  <span style={{ color: "#FFFFFF", fontWeight: 400 }}>
    {event.words.map(w => w.text).join(" ")}
  </span>
</div>
```

## Background Styles

The caption background ensures readability against any video content.

| Style | CSS | Use Case |
|---|---|---|
| `pill` | `borderRadius: 8px; padding: 8px 16px; background: rgba(0,0,0,{opacity})` | Default, works everywhere |
| `shadow` | `textShadow: "0 2px 8px rgba(0,0,0,0.8), 0 0 20px rgba(0,0,0,0.5)"` | Transparent, cinematic feel |
| `gradient` | `background: linear-gradient(transparent, rgba(0,0,0,{opacity}))` over bottom 20% | Documentary, lower-third |
| `none` | No background | Bold creative, requires high-contrast video |

## Layout Rules

### Line Breaking

- Maximum 42 characters per line (FCC_002 rule)
- Break at word boundaries only
- Prefer breaking at natural pause points (where `pause_after_ms > 200` in the IntentFrame)
- Center-align each line within the caption container

### Safe Zones

- Horizontal margin: 5% from each edge (90% usable width)
- Vertical position: 8% from top or bottom edge (avoids platform UI overlaps)
- For Instagram Reels: top position at 12% (below story bar), bottom position at 15% (above comments)

### Multi-Speaker Layout

When two speakers overlap (rare but possible in heated dialogue), stack caption events vertically with 12px gap. Most recent speaker's caption appears on top.

## Animation Spec

All timing values from the FCB Chicago CWI standard:

| Parameter | Value | Purpose |
|---|---|---|
| Entrance duration | 600ms | Word appears: opacity 0 -> 1, translateY 10px -> 0 |
| Entrance delay | 100ms | Stagger after timestamp to feel natural |
| Entrance easing | ease (cubic-bezier) | Smooth deceleration |
| Color transition | 600ms | White -> speaker color (attribution reveal) |
| Emphasis bounce | 600ms | Scale 1.0 -> 1.15 -> 1.0 (spring physics) |
| Emphasis bounce damping | 12 | Remotion spring config |
| Emphasis bounce stiffness | 200 | Remotion spring config |
| Exit | Instant at event.end | Caption disappears (no fade-out in CWI spec) |

### Remotion spring() Config

```typescript
// Entrance spring
const entranceConfig = {
  damping: 15,
  stiffness: 120,
  mass: 1,
};

// Emphasis bounce spring
const emphasisConfig = {
  damping: 12,
  stiffness: 200,
  mass: 0.8,
};
```

## Export Formats

The CWI-Remotion bridge is the primary rendering path. The extension also supports exporting CWI to other formats for professional editing workflows:

### WebVTT (Fallback)

Standard subtitle format supported by all video players. Includes `<v Speaker>` voice tags per WebVTT spec. Loses all intonation data (weight, size, emphasis) but preserves attribution and timing.

```
WEBVTT

1
00:00:00.500 --> 00:00:03.500
<v Narrator>This is a sample caption generated by OpenCaptions.
```

Generated by: `exportWebVTT(doc)` from `@opencaptions/renderer`.

### After Effects JSON (ExtendScript)

`.jsx` script that creates text layers in After Effects with:
- Keyframed opacity (fade in/out at event boundaries)
- Fill effect keyframes (white -> speaker color over 600ms with ease)
- Scale keyframes for emphasis bounce (100% -> 115% -> 100%)
- Roboto Flex font with weight encoding as comments
- Word timing reference as per-word comment markers

Generated by: `exportAfterEffectsScript(doc)` from `@opencaptions/renderer`.

### Premiere Pro XML

FCP XML v5 format importable into Premiere Pro. Creates a sequence with:
- One clip per caption event on a video track
- Text generator effect with speaker-colored text
- Clip-level markers for speaker info
- Word-level markers with weight/size/emphasis data
- Proper SMPTE timecode at the specified fps

Generated by: `exportPremiereXML(doc)` from `@opencaptions/renderer`.

## Font Loading

The CWI spec mandates Roboto Flex, a variable font supporting the `wght` axis from 100 to 900 in continuous steps. Load it in the Remotion composition:

```typescript
// In Root.tsx or the composition entry point
import "@fontsource-variable/roboto-flex";

// Or via Google Fonts CDN in the HTML template
<link href="https://fonts.googleapis.com/css2?family=Roboto+Flex:wght@100..900&display=swap" rel="stylesheet" />
```

Roboto Flex is critical. If it is not available, the browser falls back to the system sans-serif, which does not support continuous weight variation. The visual weight mapping degrades to discrete steps (400 normal, 700 bold), losing most of the intonation signal.

## Integration Checklist

When wiring the CaptionOverlay into a Content Engine Remotion composition:

1. Load the CWI JSON document as a static prop (`staticFile()` or `getInputProps()`)
2. Load Roboto Flex variable font (via `@fontsource-variable/roboto-flex` or CDN)
3. Add `<CaptionOverlay cwiDocument={doc} />` as the last layer in the composition (on top of video)
4. Match the composition fps and duration to the source video
5. Set `background` and `position` based on the content type (reels = no background + top, editorial = pill + bottom)
6. Render: `npx remotion render CaptionedVideo --props='{"cwiPath":"captions.cwi.json"}'`
