---
name: "{scene_name}"
type: scene-brief
created: "{date}"
campaign_slug: "{campaign_slug}"
character_ref: "compiled/characters/{character_slug}.md"
brand_ref: "compiled/brands/{brand_slug}.md"
format: "{format}"
tool: "{tool_slug}"
status: "{status}"
---

# Scene Brief: {scene_name}

> Single-scene generation brief. References a compiled character and brand.
> The generation tool reads this brief + the referenced compiled files to
> produce the final asset.

## Scene Description

**One-line concept:** {one_line_concept -- e.g., "Founder at workstation, typing
code while holographic UI elements float in the foreground"}

**Narrative context:** {narrative_context -- e.g., "This scene establishes the
protagonist as a builder. It's the opening image for a blog post about
autonomous agent development. The viewer should feel: 'this person is deep
in the work, not performing for the camera.'"}

**Story beat:** {story_beat -- e.g., "Introduction / Establishing" or
"Climax / Reveal" or "Resolution / Call-to-Action"}

---

## Visual Direction

### Mood & Atmosphere

**Primary mood:** {primary_mood -- e.g., "Focused intensity"}

**Emotional tone:** {emotional_tone -- e.g., "Quiet determination. Not dramatic
or heroic -- intimate and real. The viewer is observing a private moment
of deep work."}

**Atmosphere keywords:** {atmosphere_keywords -- e.g., "moody, intimate,
cinematic, warm-cool contrast, volumetric, grain"}

**Reference touchstones:** {references -- e.g., "Blade Runner 2049 office
scenes. Mr. Robot terminal sequences. Apple 'Behind the Mac' campaign
tonality."}

### Lighting

**Key light:** {key_light -- e.g., "Screen glow from monitor bank, camera-left.
Cool white (5500K), soft edge. Acts as the primary illumination source."}

**Fill light:** {fill_light -- e.g., "Warm ambient from a desk lamp behind
subject, camera-right. 3200K, very low intensity (15% of key). Creates
subtle warm rim on far shoulder."}

**Backlight/Rim:** {back_light -- e.g., "None. The darkness behind the subject
is intentional -- it compresses the depth and focuses attention."}

**Practicals:** {practical_lights -- e.g., "Monitor screens (visible in frame,
showing terminal text). Small LED strip on desk edge (purple/amber).
Power indicator LEDs on hardware (subtle green dots)."}

**Lighting ratio:** {lighting_ratio -- e.g., "High contrast, approximately 8:1
key-to-fill. Deep shadows are permitted and encouraged."}

### Time of Day

**Setting:** {time_of_day -- e.g., "Late night (2-3 AM). The city outside the
window is dark except for distant building lights."}

**Natural light influence:** {natural_light -- e.g., "None. This is an entirely
artificially-lit scene. The time of day is communicated through context
clues (dark windows, desk lamp on, coffee cup) rather than sunlight."}

### Location

**Setting type:** {setting_type -- e.g., "Interior / Home office"}

**Location description:** {location_description -- e.g., "Personal workspace
in a modern apartment. Minimal furnishing. Standing desk with dual
ultrawide monitors. Mechanical keyboard with subtle RGB backlighting.
Dark walls (charcoal or dark wood paneling). No posters or decoration
except a small plant on a shelf behind."}

**Key props:**
- {prop_1 -- e.g., "Dual ultrawide monitors showing code (terminal/IDE, dark theme)"}
- {prop_2 -- e.g., "Mechanical keyboard (dark, low-profile)"}
- {prop_3 -- e.g., "Half-empty coffee mug (ceramic, dark)"}
- {prop_4 -- e.g., "Notebook with handwritten diagrams (open, in background)"}

**Props to avoid:**
- {anti_prop_1 -- e.g., "No brand-identifiable products (Apple logo, etc.)"}
- {anti_prop_2 -- e.g., "No food or snacks (keeps the scene clean)"}
- {anti_prop_3 -- e.g., "No phone visible (character is in deep work mode)"}

### Camera Style

**Shot type:** {shot_type -- e.g., "Medium close-up (waist up). Subject fills
approximately 60% of the frame width."}

**Camera angle:** {camera_angle -- e.g., "Eye level, positioned slightly to the
left of center. Creates an over-the-shoulder feeling without showing the
viewer's shoulder."}

**Lens simulation:** {lens -- e.g., "50mm equivalent on full frame. Natural
perspective, no wide-angle distortion. Aperture f/2.0 -- subject sharp,
background elements (monitors, desk lamp) slightly soft."}

**Camera motion (video only):** {camera_motion -- e.g., "Slow push-in over 4
seconds, starting at medium shot and ending at medium close-up. Imperceptible
to casual viewer but creates subconscious engagement."}

**Film stock/grade:** {film_grade -- e.g., "Fuji Pro 400H simulation. Slightly
lifted blacks, desaturated greens, warm skin tones. Visible grain at ISO
800 equivalent."}

---

## Character Direction

**Character:** {character_name} (see `{character_ref}`)

**Outfit for this scene:** {scene_outfit -- e.g., "Default (black crewneck tee)"
or "Tech Keynote (navy blazer over black tee)"}

**Expression:** {expression -- e.g., "Slight concentration furrow between brows.
Mouth relaxed, not smiling. Eyes focused on screen content. Natural,
unposed."}

**Pose/Action:** {pose_action -- e.g., "Seated at desk, hands on keyboard
mid-type. Body angled slightly toward camera (15 degrees) but gaze is on
the screen. Left hand may be transitioning from keyboard to mouse."}

**Eye direction:** {eye_direction -- e.g., "Looking at the primary monitor
(camera-left). NOT looking at camera."}

---

## Technical Specification

### Format

**Output type:** {format -- one of: "still", "video", "reel", "carousel_frame"}

**Dimensions:**
- Width: {width -- e.g., "1920"}
- Height: {height -- e.g., "1080"}
- Aspect ratio: {aspect_ratio -- e.g., "16:9"}

**Duration (video only):** {duration -- e.g., "4 seconds"}
**FPS (video only):** {fps -- e.g., "24"}

### Tool Selection

**Primary tool:** {tool_slug -- e.g., "nano-banana-pro"}

**Rationale:** {tool_rationale -- e.g., "Character consistency is critical for
this hero image. Nano Banana Pro's face embedding ensures the subject is
recognizable. Soul Cinema would be used if this were video."}

**Fallback tool:** {fallback_tool -- e.g., "comfyui (with LoRA + IP-Adapter
workflow if Nano Banana Pro produces artifacts)"}

### Post-Processing Pipeline

**Steps:**
1. {post_1 -- e.g., "Upscale 2x via Real-ESRGAN (if base resolution < target)"}
2. {post_2 -- e.g., "Color grade: apply brand LUT or manual grade to match palette"}
3. {post_3 -- e.g., "Add film grain overlay (if not present from generation)"}
4. {post_4 -- e.g., "Final crop and resize to target dimensions"}
5. {post_5 -- e.g., "Export: PNG for stills, MP4 (H.265, CRF 18) for video"}

---

## Acceptance Criteria

Before this scene is approved:

- [ ] Character matches reference (visual similarity check against character sheet)
- [ ] Color palette aligns with brand DNA (sample 3 dominant colors)
- [ ] Lighting matches the brief (key light direction, temperature, ratio)
- [ ] Mood matches emotional tone description
- [ ] No brand anti-pattern violations
- [ ] No character wardrobe anti-pattern violations
- [ ] Technical specs met (resolution, format, duration)
- [ ] Props present and correct (check key props list)
- [ ] Forbidden props absent (check anti-props list)
- [ ] Post-processing pipeline completed

---

## Generation Log

| Attempt | Tool | Seed/ID | Result | Notes |
|---|---|---|---|---|
| 1 | {tool} | {seed} | {pass/fail} | {notes -- e.g., "Good composition but skin tone too cool"} |
| 2 | {tool} | {seed} | {pass/fail} | {notes -- e.g., "Adjusted color temp in prompt, approved"} |
