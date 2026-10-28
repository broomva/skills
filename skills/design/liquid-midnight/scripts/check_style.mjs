#!/usr/bin/env node
// Lint HTML/CSS/JS/JSX/TSX for the looks the owner rejected in Liquid Midnight work (DESIGN.md §3).
//   node check_style.mjs <file|dir>... [--json]
// errors (exit 1):  LM001 purple cast (OKLCH or hex hue 275-335 with real chroma)   LM002 arcan-glass reference
// warnings (exit 0): LM003 backdrop-filter glass with no conic metal rim in the same file
//                    LM004 radial-gradient "glow orb" rule (use the WebGL orb)        LM005 italic emphasis
// Suppress a finding with `lm-ignore` on its line; lines containing ✕ (prohibition lists) are skipped.
// Heuristics, not proof: a clean run means none of these patterns appear, not that the work is on-style.
// Always render and look (scripts/render.mjs).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const EXT = new Set([".html", ".htm", ".css", ".scss", ".js", ".mjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".md"]);
const SKIP_DIRS = new Set(["node_modules", ".git", "dist", "build", ".next", "fonts"]);
/** hues that read as purple/violet. The magenta metal fringe sits at 350 and is allowed. */
export const PURPLE = [275, 335];
const MIN_CHROMA = { oklch: 0.06, hex: 0.08 };

export function hexToOklch(hex) {
  let h = hex.replace("#", "");
  if (h.length === 3 || h.length === 4) h = [...h].map((x) => x + x).join("");
  const [r, g, b] = [0, 2, 4].map((i) => {
    const v = Number.parseInt(h.slice(i, i + 2), 16) / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return { L, C: Math.hypot(A, B), H: ((Math.atan2(B, A) * 180) / Math.PI + 360) % 360 };
}

const inPurple = (H, C, min) => C >= min && H >= PURPLE[0] && H <= PURPLE[1];

export function lint(text, file = "<input>") {
  const out = [];
  const lineOf = (i) => text.slice(0, i).split("\n").length;
  const lines = text.split("\n");
  // a line can opt out with `lm-ignore`; lines marked ✕ are prohibitions (do/don't lists) and never findings
  const add = (code, level, i, msg) => {
    const line = lineOf(i);
    if (/lm-ignore|✕/.test(lines[line - 1] ?? "")) return;
    out.push({ file, line, code, level, msg });
  };
  for (const m of text.matchAll(/oklch\(\s*([\d.]+%?)\s+([\d.]+)\s+([\d.]+)(?:deg)?/gi)) {
    const C = Number(m[2]);
    const H = Number(m[3]);
    if (inPurple(H, C, MIN_CHROMA.oklch)) add("LM001", "error", m.index, `purple cast: ${m[0]}) (hue ${H}, chroma ${C}); Midnight grounds and accents stay at hue 225-262`);
  }
  for (const m of text.matchAll(/#([0-9a-f]{6}|[0-9a-f]{3})\b(?![0-9a-f])/gi)) {
    const prev = text.slice(Math.max(0, m.index - 6), m.index);
    if (/&$|url\($/i.test(prev)) continue; // entities, fragment links
    const { C, H } = hexToOklch(m[0]);
    if (inPurple(H, C, MIN_CHROMA.hex)) add("LM001", "error", m.index, `purple cast: ${m[0]} (OKLCH hue ${H.toFixed(0)}, chroma ${C.toFixed(3)})`);
  }
  for (const m of text.matchAll(/arcan[-_ ]?glass/gi)) add("LM002", "error", m.index, "arcan-glass look/skill referenced; it was rejected for this style");
  const hasBlur = /backdrop-filter\s*:\s*[^;]*blur/i.test(text);
  const hasRim = /conic-gradient\(\s*from\s+var\(--ua/i.test(text) || /\blm-(glass|capsule|ring)\b/.test(text) || /materials\.css/.test(text);
  if (hasBlur && !hasRim) add("LM003", "warning", text.search(/backdrop-filter/i), "glass without the travelling metal rim (.lm-glass / conic-gradient(from var(--ua))); a flat glass panel was rejected");
  for (const m of text.matchAll(/([^{}]*orb[^{}]*)\{([^}]*)\}/gi)) {
    if (/lm-orb-button|lm-orb-layer/.test(m[1])) continue;
    if (/radial-gradient/i.test(m[2])) add("LM004", "warning", m.index, "radial-gradient glow orb; use the WebGL glass plasma orb (kit/orb.js) instead");
  }
  for (const m of text.matchAll(/(?:\bem|h[1-3])[^{}]*\{[^}]*font-style\s*:\s*italic/gi)) add("LM005", "warning", m.index, "italic emphasis; emphasis is Raleway 400 in --lm-blue, never italic");
  return out;
}

export function files(paths) {
  const out = [];
  for (const p of paths) {
    const st = statSync(p);
    if (st.isDirectory()) {
      for (const name of readdirSync(p).sort()) if (!SKIP_DIRS.has(name) && !name.startsWith(".")) out.push(...files([join(p, name)]));
    } else if (EXT.has(extname(p))) out.push(p);
  }
  return out;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const json = args.includes("--json");
  const paths = args.filter((a) => a !== "--json");
  if (!paths.length) {
    console.error("usage: check_style.mjs <file|dir>... [--json]");
    process.exit(2);
  }
  const findings = files(paths).flatMap((f) => lint(readFileSync(f, "utf8"), f));
  if (json) console.log(JSON.stringify(findings, null, 2));
  else for (const f of findings) console.log(`${f.file}:${f.line}  ${f.level.toUpperCase()} ${f.code}  ${f.msg}`);
  const errors = findings.filter((f) => f.level === "error").length;
  if (!json) console.log(`${errors} error(s), ${findings.length - errors} warning(s)`);
  process.exit(errors ? 1 : 0);
}
