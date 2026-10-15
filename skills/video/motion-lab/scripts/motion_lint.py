#!/usr/bin/env python3
"""Render-contract linter for code-first motion (stdlib only).

A code-first animation is a program whose every frame must be a pure function
of time t, so a headless browser can freeze it at any frame and get the same
pixels every run. This checker finds the static violations of that contract in
an HTML file (or a bare .js/.mjs/.ts/.tsx module):

  MC01 clock        Date.now / new Date() / performance.now / requestAnimationFrame.
                    ERROR, unless the file defines renderAt AND a ?t= guard: that
                    is the live-preview pattern, and the guard keeps the clock out
                    of a frozen render. Then it is a WARN to confirm by eye.
  MC02 timer        setTimeout / setInterval (a timer start makes frame N differ
                    run to run).
  MC03 random       Math.random / crypto.getRandomValues (unseeded randomness
                    makes shapes jitter frame to frame).
  MC04 renderAt     JS-driven motion (canvas, WebGL, three.js, GSAP, rAF) with no
                    window.renderAt(t). CSS-only motion is exempt: the renderer
                    seeks document.getAnimations() directly.
  MC05 transition   a CSS `transition` (state-triggered, so not seekable by t).
  MC06 network      fetch / XMLHttpRequest / WebSocket / EventSource, or a remote
                    URL that is neither a font host nor pinned to MAJOR.MINOR.PATCH.
  MC07 local-file   a relative src/href (the contract asks for one self-contained
                    file). WARN.
  MC08 fonts        web fonts loaded with no document.fonts.ready wait. WARN.
  MC09 layout       @keyframes animating width/height/top/left/right/bottom
                    (jank; animate transform and opacity). WARN.

Exit 0 when no ERROR is found (WARNs allowed), 1 on any ERROR, 2 on a usage or
read error. --strict makes a WARN fail too. --json prints machine output.

What this cannot see: whether renderAt really reads only t, whether a seeded
generator is reseeded per frame, or whether frame N-1 flows into frame 0. Those
are runtime properties. `render.mjs --verify` re-renders frames and compares
bytes, which is the dynamic half of the same contract.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com", "use.typekit.net", "fonts.bunny.net")

# A full MAJOR.MINOR.PATCH pin, as `pkg@1.2.3` (jsDelivr, unpkg, esm.sh) or as a
# path segment `/1.2.3/` (cdnjs). `three@0.160` and `gsap@3` are NOT pins.
_PIN = re.compile(r"@v?\d+\.\d+\.\d+(?![\d.])|/v?\d+\.\d+\.\d+(?:/|$)")
_URL = re.compile(r"""(?:https?:)?//[A-Za-z0-9.-]+\.[A-Za-z]{2,}[^\s'"`)<>]*""")
_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)
_STYLE = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.I | re.S)
_TAG_ATTR = re.compile(r"""<(?:link|img|source|video|audio|iframe|script)\b[^>]*?\b(?:src|href)\s*=\s*["']([^"']+)["']""", re.I)


@dataclass
class Finding:
    rule: str
    severity: str  # "error" | "warn"
    line: int
    message: str


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def strip_js(code: str) -> tuple[str, str]:
    """Return (no_comments, no_comments_no_strings), both length-preserving.

    Comments become spaces in both views; string and template-literal bodies
    are kept in the first and blanked in the second, so a URL inside a string
    stays checkable while a quoted "Date.now" cannot trip an API rule.
    Newlines are always kept, so offsets map back to the original lines.
    Limitation: a regex literal containing a quote can desynchronise the
    scanner; that costs a missed or spurious finding on that line, never a crash.
    """
    keep = list(code)
    blank = list(code)
    i, n = 0, len(code)

    def wipe(buf: list[str], a: int, b: int) -> None:
        for k in range(a, b):
            if buf[k] != "\n":
                buf[k] = " "

    while i < n:
        c = code[i]
        nxt = code[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = code.find("\n", i)
            j = n if j == -1 else j
            wipe(keep, i, j)
            wipe(blank, i, j)
            i = j
        elif c == "/" and nxt == "*":
            j = code.find("*/", i + 2)
            j = n if j == -1 else j + 2
            wipe(keep, i, j)
            wipe(blank, i, j)
            i = j
        elif c in "'\"`":
            j = i + 1
            while j < n and code[j] != c:
                if code[j] == "\\":
                    j += 1
                elif code[j] == "\n" and c != "`":
                    break  # unterminated ordinary string: stop at the line end
                j += 1
            wipe(blank, i + 1, min(j, n))
            i = j + 1
        else:
            i += 1
    return "".join(keep), "".join(blank)


def strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), css, flags=re.S)


def is_pinned(url: str) -> bool:
    return bool(_PIN.search(url))


def is_font_host(url: str) -> bool:
    return any(h in url for h in FONT_HOSTS)


def check_url(url: str, line: int, out: list[Finding]) -> None:
    if is_font_host(url) or is_pinned(url):
        return
    out.append(Finding("MC06", "error", line, f"remote URL is not pinned to MAJOR.MINOR.PATCH: {url}"))


@dataclass
class Block:
    kind: str  # "script" | "style" | "importmap"
    start: int  # offset of the block body in the whole file
    body: str


def blocks_of(text: str, is_html: bool) -> list[Block]:
    if not is_html:
        return [Block("script", 0, text)]
    out: list[Block] = []
    for m in _SCRIPT.finditer(text):
        attrs = m.group(1)
        kind = "importmap" if re.search(r"type\s*=\s*['\"]importmap['\"]", attrs, re.I) else "script"
        if re.search(r"type\s*=\s*['\"](?:text/template|text/x-|application/json|x-shader)", attrs, re.I):
            continue  # inert data: shader source or JSON, not executed JS
        out.append(Block(kind, m.start(2), m.group(2)))
    for m in _STYLE.finditer(text):
        out.append(Block("style", m.start(1), m.group(1)))
    return out


JS_RULES = [
    ("MC01", re.compile(r"\bDate\.now\s*\(|\bnew\s+Date\s*\(|\bperformance\.now\s*\(|\brequestAnimationFrame\s*\("), "clock or frame loop"),
    ("MC02", re.compile(r"\bset(?:Timeout|Interval)\s*\("), "timer start"),
    ("MC03", re.compile(r"\bMath\.random\s*\(|\bgetRandomValues\s*\("), "unseeded randomness"),
    ("MC06", re.compile(r"\bfetch\s*\(|\bXMLHttpRequest\b|\bnew\s+WebSocket\s*\(|\bnew\s+EventSource\s*\("), "network request"),
]
MOTION_JS = re.compile(r"getContext\s*\(|\bTHREE\b|from\s*['\"]three|\bgsap\b|requestAnimationFrame|WebGLRenderer")
RENDER_AT = re.compile(r"\brenderAt\s*=|\bfunction\s+renderAt\b|\brenderAt\s*:")
T_GUARD = re.compile(r"URLSearchParams[\s\S]{0,400}?\.(?:has|get)\s*\(\s*['\"]t['\"]\s*\)")
FONTS_READY = re.compile(r"document\.fonts\.ready|document\.fonts\.load\s*\(")
TRANSITION = re.compile(r"(?<![-\w.#])transition(?:-[a-z-]+)?\s*:\s*([^;}{]*)", re.I)
KEYFRAMES = re.compile(r"@keyframes\s+[\w-]+\s*\{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}", re.I)
LAYOUT_PROP = re.compile(r"(?<![-\w])(width|height|top|left|right|bottom)\s*:", re.I)


def lint_text(text: str, is_html: bool = True) -> list[Finding]:
    findings: list[Finding] = []
    blocks = blocks_of(text, is_html)

    js_views: list[tuple[int, str, str]] = []
    for b in blocks:
        if b.kind == "script":
            keep, blank = strip_js(b.body)
            js_views.append((b.start, keep, blank))
    all_js_keep = "\n".join(k for _, k, _ in js_views)
    all_js_blank = "\n".join(bl for _, _, bl in js_views)

    has_render_at = bool(RENDER_AT.search(all_js_blank))
    has_guard = bool(T_GUARD.search(all_js_keep))
    preview_ok = has_render_at and has_guard

    for start, keep, blank in js_views:
        for rule, rx, label in JS_RULES:
            for m in rx.finditer(blank):
                line = line_of(text, start + m.start())
                if rule == "MC01" and preview_ok:
                    findings.append(Finding(rule, "warn", line,
                        f"{label} `{m.group(0).strip()}` with renderAt + ?t= guard: confirm it only drives the live preview"))
                else:
                    findings.append(Finding(rule, "error", line, f"{label} `{m.group(0).strip()}`"))
        for m in _URL.finditer(keep):
            check_url(m.group(0), line_of(text, start + m.start()), findings)

    # MC04 — JS-driven motion needs a renderAt(t) entry point (HTML only: a bare
    # module may legitimately be a Remotion component driven by useCurrentFrame).
    if is_html and MOTION_JS.search(all_js_blank) and not has_render_at:
        m = MOTION_JS.search(text)
        findings.append(Finding("MC04", "error", line_of(text, m.start()) if m else 1,
            "JS-driven motion but no window.renderAt(t): the renderer cannot freeze an exact frame"))

    for b in blocks:
        if b.kind == "importmap":
            for m in _URL.finditer(b.body):
                check_url(m.group(0), line_of(text, b.start + m.start()), findings)
        elif b.kind == "style":
            css = strip_css_comments(b.body)
            for m in TRANSITION.finditer(css):
                value = m.group(1).strip().lower()
                if value in ("none", "0s", "0", "initial", "unset") or value.startswith("none"):
                    continue
                findings.append(Finding("MC05", "error", line_of(text, b.start + m.start()),
                    f"CSS transition `{m.group(0).strip()}` is state-triggered, not seekable by t"))
            for km in KEYFRAMES.finditer(css):
                for pm in LAYOUT_PROP.finditer(km.group(1)):
                    findings.append(Finding("MC09", "warn", line_of(text, b.start + km.start(1) + pm.start()),
                        f"@keyframes animates layout property `{pm.group(1)}`: animate transform and opacity"))
            for m in re.finditer(r"url\(\s*['\"]?([^'\")]+)", css):
                if _URL.match(m.group(1)):
                    check_url(m.group(1), line_of(text, b.start + m.start()), findings)

    if is_html:
        for m in _TAG_ATTR.finditer(text):
            ref = m.group(1).strip()
            line = line_of(text, m.start())
            if ref.startswith(("data:", "#", "blob:")):
                continue
            if _URL.match(ref):
                check_url(ref, line, findings)
            else:
                findings.append(Finding("MC07", "warn", line, f"local reference `{ref}`: the contract asks for one self-contained file"))

    uses_webfont = bool(re.search(r"@font-face|fonts\.googleapis\.com|use\.typekit\.net|fonts\.bunny\.net", text))
    if uses_webfont and not FONTS_READY.search(all_js_blank + all_js_keep):
        findings.append(Finding("MC08", "warn", 1, "web fonts with no document.fonts.ready wait: frame 0 may capture the fallback font"))

    unique = {(f.rule, f.severity, f.line, f.message): f for f in findings}
    return sorted(unique.values(), key=lambda f: (f.line, f.rule))


def lint_path(path: Path) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    return lint_text(text, is_html=path.suffix.lower() in (".html", ".htm"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lint code-first motion against the render contract.")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="fail on WARN as well as ERROR")
    args = ap.parse_args(argv)

    report = {}
    failed = False
    for f in args.files:
        try:
            found = lint_path(f)
        except (OSError, UnicodeDecodeError) as e:
            print(f"motion_lint: cannot read {f}: {e}", file=sys.stderr)
            return 2
        report[str(f)] = found
        if any(x.severity == "error" or (args.strict and x.severity == "warn") for x in found):
            failed = True

    if args.json:
        print(json.dumps({k: [asdict(x) for x in v] for k, v in report.items()}, indent=2))
    else:
        for f, found in report.items():
            if not found:
                print(f"{f}: clean")
            for x in found:
                print(f"{f}:{x.line}: {x.severity.upper()} {x.rule} {x.message}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
