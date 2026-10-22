# When a render breaks — symptom, cause, the prompt that fixes it

| Symptom | Cause | Paste this fix |
|---|---|---|
| flicker or jitter | `Math.random`, timers, a clock | Make every value a pure function of t. Replace Math.random with a seeded generator reseeded inside renderAt. Remove timers and CSS transitions. |
| wrong or fallback font | captured before the font loaded | Load the font with display=block and wait for document.fonts.ready before the first frame. |
| hiccup at the loop seam | frame N rendered (it is frame 0) | Render frames 0 to N-1 only. Drive the loop from phase = frame / N with whole cycles. |
| audio drifts off the beat | beats added as rounded frames | Compute each beat as n x 60 / BPM and round per beat. Never add a rounded frame count. |
| jank or dropped frames | animating layout | Animate only transform and opacity. No width, height, top or left. |
| banding in the GIF | gradients squeezed into a palette | No gradients. Flat colours only, or dither the palette. |
| blurry or shimmering text | sub-pixel resting positions | Snap resting text to whole pixels. Render at 2x and scale down (`--scale 2`). |
| text moves before it can be read | hold too short | Hold every text state 0.3 s per word plus 0.5 s before it moves. |
| everything moves at once | no hierarchy | One hero move at a time. Others start 150 ms later at 60% of its travel. |
| `render.mjs` exits 3 | renderAt depends on something besides t, or creates an animation by toggling a class | Derive mutated or read state from t. Do not start keyframes in renderAt: create the animation at load, pause and seek it, or set the pose directly. |

## Review prompts that point at frames, not feelings

Pick one or two per round.

```text
Render stills at frames 0, 24, 48, 72 and 96. Describe each in one sentence as a viewer would. Does that match the shot list? Fix what does not.
Make a contact sheet of every 12th frame. Mark every frame where two things move at once, then fix the hierarchy.
Onion-skin frames 24 to 47 at 25% opacity. Spacing should tighten near the keys. Adjust the easing until it does.
Plot the hero's x position and scale per frame as a PNG chart. Show where the motion is linear or stops dead, then fix it with our tokens.
Review this like a senior motion designer: 10 notes ordered by impact, each with a frame number and the exact code change. Apply the top 5.
It is too busy. Remove 30% of the motion and keep only the moves that guide the eye.
The ending is abrupt. Add a 36-frame hold with a 2% push, then let it settle on a spring at damping ratio 0.8.
```

## When a fix does not hold

```text
The fix at frame 84 did not hold. Render frames 83 and 85 as PNGs, put them side by side and list every difference you can see. Find the line of code that causes it, fix only that line, then render both frames again.
```

When a fix works, add its line to the render contract.
