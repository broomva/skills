# Real-sound craft

Start with a cue list. Give each cue a picture timestamp, an audible event, a material and a purpose. Mark which cuts will carry neither a transition nor an impact. Leaving roughly 85% without a cut-specific effect gives important actions room and leaves music, dialogue or room tone free to continue across an edit.

| Decision | What to inspect |
|---|---|
| Recordings | Choose licensed close-miked takes with a clean attack and natural decay. Keep a source URL, author, license and trim range for each cue. |
| Material | Choose one palette, such as paper and soft felt or glass and machined metal. Remove cues that suggest a different physical world. |
| Sync | Put a contact sound at the physical contact, shape a pass-by around the motion's fastest point, and check the onset against the visual timecode. |
| Drop | End the build just ahead of the drop. Leave a brief gap for contrast, then place the strongest accent at about 30–60% of runtime. |
| Logo | Give the logo space and use a restrained resolved tone when useful. Listen for a late musical impact that competes with the mark. |
| Dialogue | Listen to soft syllables over the ducked music. Hold voice and bed stems on the same timeline, including leading silence and pauses. |

A sheet exposes static cut timing, gaps, hard edges and spectral concentration. Check suspected cues in isolation and against picture. Use the end-to-end gate on the encoded deliverable, where resampling and encoding can alter peaks and sample counts. For a stem cut short by sidechain processing, pad the bed before compression and extend the sidechain key with a short silence margin beyond the target length. Verify the post-compression stem. A correctly padded bed can still produce a short output when the sidechain key ends.

Record the sourcing and listening status when handing off. For example, write “Interface clicks were synthesized. I checked their timing and levels with the sheet and deterministic gates. Human audition pending.” A person can assess material, balance and emotional fit by auditioning the full render.

Inspired by [real-sound](https://github.com/Leonxlnx/earshot/tree/main/skills/real-sound), MIT License, Copyright (c) 2026 Leon Lin. [Upstream license](https://github.com/Leonxlnx/earshot/blob/main/LICENSE).
