# Capture recipe — measured style extraction (agent-browser)

The load-bearing mechanism of `design-distill`: extract **ground-truth** palette
and type from live references, and validate the generated specimen — all via the
`agent-browser` headless CLI. Nothing here infers a colour; everything is measured.

## 0. Setup

```bash
agent-browser set viewport 1440 900
```

## 1. The computed-style extractor (the core eval)

Run this against each reference after it loads. Returns measured tokens — no guessing.

```bash
agent-browser eval '(() => {
  const cs = getComputedStyle(document.body);
  const h1 = document.querySelector("h1");
  const pick = el => el ? getComputedStyle(el) : null;
  const btns = [...document.querySelectorAll("button,a[class*=button],a[class*=btn],[role=button]")].slice(0,12);
  const btnStyles = [...new Set(btns.map(b=>{const s=getComputedStyle(b);return s.backgroundColor+" / "+s.color}))];
  const links = [...document.querySelectorAll("a")].slice(0,30);
  const linkColors = [...new Set(links.map(a=>getComputedStyle(a).color))].slice(0,6);
  return JSON.stringify({
    bodyBg: cs.backgroundColor, bodyColor: cs.color, bodyFont: cs.fontFamily,
    h1Font: pick(h1)?.fontFamily, h1Size: pick(h1)?.fontSize, h1Weight: pick(h1)?.fontWeight,
    h1Text: h1?.textContent.trim().slice(0,80),
    buttonStyles: btnStyles, linkColors, title: document.title
  }, null, 2);
})()'
```

Convert `rgb()/rgba()` to hex for the tokens. Record surfaces (cards/panels) by
sampling representative elements if body doesn't expose them.

## 2. The three site classes (dual-mode capture)

Sites behave in exactly three ways. Detect and handle each:

### A. Respects `prefers-color-scheme` → capture both modes directly
```bash
for mode in dark light; do
  agent-browser set media "$mode"
  agent-browser open "$URL"; agent-browser wait 3200
  agent-browser screenshot "ref-${name}-${mode}.png"
  # …run the extractor…
done
```

### B. Manual toggle (ignores `set media`) → click the theme button
Symptom: after `set media light`, `getComputedStyle(document.body).backgroundColor`
is unchanged. Find and click the toggle, then re-measure:
```bash
agent-browser eval '(() => {
  const c=[...document.querySelectorAll("button,[role=button],a,[class*=theme],[class*=toggle]")];
  const m=c.find(el=>/theme|dark|light|mode|appearance/i.test(
    (el.getAttribute("aria-label")||"")+" "+(el.getAttribute("title")||"")+" "+(el.className||"")));
  if(m){m.click();return "clicked:"+((m.getAttribute("aria-label")||m.className||"").slice(0,50));}
  return "no toggle";
})()'
agent-browser wait 1000
agent-browser eval '(()=>getComputedStyle(document.body).backgroundColor)()'   # confirm it flipped
```
⚠️ Some "toggles" are **dropdown triggers** (open a menu, don't flip directly).
If bg didn't change, the click opened a menu — the site is effectively class C
for headless purposes. Don't capture a menu-open screenshot as "light mode".

### C. Single-mode (pins its theme) → record as a one-mode anchor
Symptom: neither `set media` nor a toggle flips it (e.g. marketing sites that
hard-code dark or light). **Do not fabricate the other mode.** Record it as a
dark-only or light-only *anchor* and source the missing mode from another ref.

## 3. View the screenshots

Measurement covers quantitative tokens. **Read the PNGs** to catalogue what only
the eye gets: hero/illustration style, layout (sidebar/main/detail), card
treatment, motion hints, chrome density. Tag these observations; tag measured
values as measured.

## 4. Dogfood validation (P11) — the generated specimen

After generating `design-system.html`, prove it renders in **both** modes:
```bash
agent-browser set viewport 1200 1500
agent-browser open "file://$ABS/design-system.html"; agent-browser wait 1000
agent-browser screenshot /tmp/ds-dark.png
agent-browser eval 'document.querySelector(".toggle").click()'; agent-browser wait 600
agent-browser eval '(()=>JSON.stringify({theme:document.documentElement.dataset.theme,bg:getComputedStyle(document.body).backgroundColor}))()'
agent-browser screenshot /tmp/ds-light.png
agent-browser errors        # must be empty
agent-browser close
```
Then **Read** both PNGs and confirm every component inverts correctly.

## Gotchas (observed 2026-06, agents-dashboard run)

- agent-browser `eval` output is shell-quoted (`"rgb(...)"` includes the quotes) —
  don't string-compare raw; parse or strip quotes.
- `set media light` is silently ignored by sites with a JS/localStorage theme
  (Paperclip) and by theme-pinned marketing sites (Linear dark-only, Attio
  light-only) — always confirm the flip by re-reading `body` bg.
- Cofounder-class sites are light-only; Paperclip's *own* light mode was cool
  pure-white, not its warm dark — a ref's off-direction mode may be the wrong
  anchor. Pick anchors by measured warmth, not by which site it came from.
