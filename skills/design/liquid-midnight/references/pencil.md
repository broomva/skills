# Building Liquid Midnight boards in Pencil (pen.dev)

## The trap: `filePath` falls back to the active tab

`mcp__pencil__execute` takes a `filePath`, but when that path is **not open in Pen** it does not create the file and does not error. It applies the operations to whatever document is **active**, often another session's canvas of record.
- Pen autosaves, so the damage lands on disk.
- `SetVariables` merges into the other document and **overwrites** same-named tokens. `blue`, `font-sans` and `surface` are common collisions.

It has happened three times, the last on 2026-10-28 while building this style's own boards.

## Safe procedure

1. **Create the file yourself.** A `.pen` is JSON:
   ```bash
   printf '{"version":"2.21","children":[]}' > design/<name>.pen && open design/<name>.pen
   ```
2. **Confirm with `get_app_state`** that the active editor is exactly your path and the document is empty.
3. **Guard every `execute`.** The first call refuses a non-empty document and sets a sentinel variable. Every later call throws unless the sentinel exists and every top-level board matches your naming. A throw rolls back the whole call.
   ```js
   // first call
   if (Get((x,c)=>{if(c.depth===0){c.skipChildren();return x.id}}).length || Object.keys(GetVariables().variables).length) throw new Error("guard: not empty");
   SetVariables({"lm-sentinel":{type:"string",value:"liquid-midnight"}, /* tokens… */});
   // every later call
   if (!GetVariables().variables["lm-sentinel"]) throw new Error("guard: not the liquid-midnight doc");
   ```
4. **Save.** Pen may not autosave a file created outside it. Check the size on disk. If it is still the 32-byte stub, ask the owner to press Cmd+S on that tab: scripted saves need accessibility permission. Strip the `fileToken` key Pen adds before committing to a public repository.
5. **If you did write into the wrong file:**
   - Stop writing.
   - Delete your boards.
   - Find your variables: names no node references and that the file's `git show HEAD:` lacks.
   - Restore overwritten values from HEAD, or from the same file open in a sibling worktree tab (`filePath` *does* route to any document that is open).
   - Remove your additions with `SetVariables(filtered, true)`, then compare the variable name set with the baseline.
   - On a 300-board file, scan in chunks of about 80 top-level frames; a full-document visitor gets `interrupted`.
   - Report it to the owner.

## Materials in Pencil

- **Themes:** register variables with `{value, theme:{mode:"night"|"day"}}` and set `theme:{mode:"day"}` on a frame for paper mode. Hex values come from `tokens/tokens.css` (the hex block).
- **Glass card:**
  - a linear gradient fill (rotation 180) `#313f4c4d → #0b172342 @.55 → #05101c57`;
  - effects: `background_blur` 9, outer shadow `0 30 80 #000001b0`, inner `0 1 0 #ffffff33` (top edge), inner `0 -22 34 #54cff538` (cyan caustic);
  - radius 22.
- **Liquid-metal rim:** a stroke with an `angular` gradient. Its rotation stands in for `--ua`, so vary it per board to show travel. Width 1.2–1.4. Stops, from the conic rim:
  ```json
  [{"color":"#43484e80","position":0},{"color":"#7f878e99","position":0.1333},{"color":"#eff6fbeb","position":0.1944},{"color":"#54d8f4cc","position":0.2139},{"color":"#7f878e8c","position":0.2722},{"color":"#2f333866","position":0.4667},{"color":"#6e767c8c","position":0.6333},{"color":"#dfe6ebd1","position":0.6944},{"color":"#efcc838c","position":0.7111},{"color":"#5d646b80","position":0.7722},{"color":"#43484e80","position":1}]
  ```
- **Chrome ring** (round buttons, 2.5 px, outer):
  ```json
  [{"color":"#3e4348","position":0},{"color":"#989fa6","position":0.1111},{"color":"#f7fdff","position":0.1778},{"color":"#4ae0ff","position":0.1944},{"color":"#65bdff","position":0.2056},{"color":"#f5cb70","position":0.2167},{"color":"#8c9399","position":0.2667},{"color":"#2a2e33","position":0.4722},{"color":"#757b81","position":0.6556},{"color":"#eaeff3","position":0.7111},{"color":"#6c7278","position":0.7778},{"color":"#3e4348","position":1}]
  ```
- **Capsule:** gradient `#232c36a8 → #0a131dbd`, `background_blur` 26, outer `0 22 60 #000000eb`, inner top `#ffffff29`, radius 999, metal rim stroke 1.2.
- **Orb:** a **square** rectangle with a shader fill `./shaders/orb.glsl`. The side is 3.4 × the sphere radius you want. The defaults derive from `--lm-blue`; for other tokens pass A = the colour lifted 40% toward cyan and B = the colour × .8, with `uViolet` .45 for blue and .08 otherwise.
- **ASCII field:** a rectangle with shader fill `./shaders/ascii.glsl`, uniforms `u_atlas: "./shaders/ascii-atlas.png"`, `u_color #a8c4e8`, `u_ground #040d18`, `u_alpha .15`, `u_cell 15`.
- **Ambient:** ellipses at 900–1000 px, radial gradient `colour@45% → transparent @.62`, `blur` 90, opacity .45.
- **Safe zones:** Pencil strokes have no dash option, so tint the unsafe margins coral at about 15% and outline the safe rect in blue.

## Review

Export each board at scale 1 (`Export([id], "png", dir, {scale:1})`) and **Read the PNG**. `TakeScreenshot` previews are too small to judge rims or type. The reference board set (cover, palette, typography, materials, components, orb/ASCII, motion, formats) is in the source repo: `design/liquid-midnight.pen` and `docs/renders/pen/`.
