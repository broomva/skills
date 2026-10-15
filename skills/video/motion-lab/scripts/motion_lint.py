#!/usr/bin/env python3
"""Render-contract linter for code-first motion (stdlib only).

A code-first animation is a program whose every frame must be a pure function
of time t, so a headless browser can freeze it at any frame and get the same
pixels every run. This checker finds the static violations of that contract in
an HTML file (or a bare .js/.mjs/.ts/.tsx module):

  MC01 clock        Date.now / Date() / new Date / performance.now / rAF / a
                    three.js Clock / getElapsedTime / getDelta / document.timeline.
                    ERROR, unless the file defines renderAt AND a ?t= guard: that
                    is the live-preview pattern, and the guard keeps the clock out
                    of a frozen render. Then it is a WARN to confirm by eye. A clock
                    inside renderAt's own body is always an ERROR.
  MC02 timer        setTimeout / setInterval (a timer start makes frame N differ
                    run to run).
  MC03 random       Math.random (also via Math["random"] or destructuring) /
                    crypto.getRandomValues: unseeded randomness makes shapes
                    jitter frame to frame.
  MC04 renderAt     JS-driven motion (canvas, WebGL, three.js, GSAP, rAF) with no
                    window.renderAt(t). CSS-only motion is exempt: the renderer
                    seeks document.getAnimations() directly.
  MC05 transition   a CSS transition with a non-zero duration, in a <style> block,
                    a style="" attribute or set from JS (state-triggered, so not
                    seekable by t).
  MC06 network      fetch / XMLHttpRequest / WebSocket / EventSource, or a loaded
                    remote URL (src/href, importmap, CSS url(), a JS import, or a JS
                    string naming a loadable file) that is neither a font host nor
                    pinned to MAJOR.MINOR.PATCH. A URL that is only text, such as the
                    SVG namespace, is not a load and is not checked.
  MC07 local-file   a relative src/href (the contract asks for one self-contained
                    file). WARN.
  MC08 fonts        web fonts loaded with no document.fonts.ready wait. WARN.
  MC09 layout       @keyframes animating width/height/top/left/right/bottom
                    (jank; animate transform and opacity). WARN.
  MC10 ext-clock    something that plays on its own clock: GSAP with no paused
                    timeline or seek, or an autoplaying <video>/<audio>. WARN:
                    drive it from renderAt (tl.seek(t), el.currentTime = t).

Exit 0 when no ERROR is found (WARNs allowed), 1 on any ERROR, 2 on a usage or
read error. --strict makes a WARN fail too. --json prints machine output.

What this cannot see: whether renderAt really reads only t, whether a seeded
generator is reseeded per frame, a clock reached through an alias it does not
know, or whether frame N-1 flows into frame 0. Those are runtime properties. `render.mjs --verify` re-renders frames and compares
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


CLOCK = re.compile(
    r"\bDate\.now\b|\bnew\s+Date\b|(?<!new )(?<![\w.$])Date\s*\(|\bperformance\.now\b"
    r"|\brequestAnimationFrame\s*\(|\bClock\s*\(|\bgetElapsedTime\s*\(|\bgetDelta\s*\(|\bdocument\.timeline\b")
# Rules over the string-blanked view (a quoted name cannot trip them).
JS_RULES = [
    ("MC01", CLOCK, "clock or frame loop"),
    ("MC02", re.compile(r"\bset(?:Timeout|Interval)\s*\("), "timer start"),
    ("MC03", re.compile(r"\bMath\.random\s*\(|\bgetRandomValues\s*\("), "unseeded randomness"),
    ("MC05", re.compile(r"\.style\.transition\w*\s*=(?!=)"), "CSS transition set from JS"),
    ("MC06", re.compile(r"\bfetch\s*\(|\bXMLHttpRequest\b|\bnew\s+WebSocket\s*\(|\bnew\s+EventSource\s*\("), "network request"),
]
# Rules that need string contents (the view with comments stripped, strings kept).
JS_KEEP_RULES = [
    ("MC03", re.compile(r"\bMath\s*\[\s*['\"`]random['\"`]\s*\]|\{[^{}]*\brandom\b[^{}]*\}\s*=\s*Math\b"), "unseeded randomness"),
    ("MC05", re.compile(r"\.style\.setProperty\s*\(\s*['\"`]transition"), "CSS transition set from JS"),
]
MOTION_JS = re.compile(r"getContext\s*\(|\bTHREE\b|from\s*['\"]three|\bgsap\b|requestAnimationFrame|WebGLRenderer")
RENDER_AT = re.compile(r"\brenderAt\s*=|\bfunction\s+renderAt\b|\brenderAt\s*:")
T_PARAM = re.compile(r"\.(?:has|get)\s*\(\s*['\"`]t['\"`]\s*\)")
T_SEARCH = re.compile(r"location\.search[^\n]{0,160}\bt=")
LOAD_EXT = re.compile(r"\.(?:m?js|cjs|css|json|wasm|glb|gltf|bin|hdr|exr|ktx2|png|jpe?g|webp|avif|gif|svg|mp[34]|webm|wav|ogg|woff2?|ttf|otf)(?:[?#]|$)", re.I)
IMPORT_CTX = re.compile(r"(?:\bimport\s*\(\s*|\bfrom\s*|\bimport\s+)['\"`]$")
RENDER_AT_DEF = re.compile(
    r"\brenderAt\s*[=:]\s*(?:async\s+)?function\b[^{]*\{"
    r"|\bfunction\s+renderAt\s*\([^)]*\)\s*\{"
    r"|\brenderAt\s*[=:]\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*")
GSAP_SEEKED = re.compile(r"paused\s*:\s*true|\.seek\s*\(|\.progress\s*\(|\.totalTime\s*\(|\.time\s*\(|\.pause\s*\(")
MEDIA_AUTOPLAY = re.compile(r"<(video|audio)\b[^>]*\bautoplay\b", re.I)
STYLE_ATTR = re.compile(r"""\bstyle\s*=\s*(["'])(.*?)\1""", re.I | re.S)
DURATION = re.compile(r"(\d*\.?\d+)\s*(ms|s)\b", re.I)
FONTS_READY = re.compile(r"document\.fonts\.ready|document\.fonts\.load\s*\(")
TRANSITION = re.compile(r"(?<![-\w.#])transition(-[a-z-]+)?\s*:\s*([^;}{\"']*)", re.I)
KEYFRAMES = re.compile(r"@keyframes\s+[\w-]+\s*\{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}", re.I)
LAYOUT_PROP = re.compile(r"(?<![-\w])(width|height|top|left|right|bottom)\s*:", re.I)


def transition_is_live(longhand: str | None, value: str) -> bool:
    """A transition matters only if it can run: some duration must be above zero.

    `transition: transform` (0s by default), `transition: all 0s`,
    `transition-behavior: allow-discrete` and `transition-delay: 1s` alone
    animate nothing, so they are not findings.
    """
    value = value.strip().lower()  # none / initial / 0s carry no positive duration
    if longhand not in (None, "-duration"):
        return False
    for num, unit in DURATION.findall(value):
        if float(num) > 0:
            # in the shorthand the FIRST time is the duration, the second the delay
            return True if longhand == "-duration" else _first_time_positive(value)
    return False


def _first_time_positive(value: str) -> bool:
    for part in value.split(","):
        times = DURATION.findall(part)
        if times and float(times[0][0]) > 0:
            return True
    return False


def render_at_spans(blank: str) -> list[tuple[int, int]]:
    """Character spans of every renderAt body, found on the string-blanked view."""
    spans = []
    for m in RENDER_AT_DEF.finditer(blank):
        i = m.end()
        if blank[i - 1] == "{" or (i < len(blank) and blank[i] == "{"):
            i = i if blank[i - 1] == "{" else i + 1
            depth, j = 1, i
            while j < len(blank) and depth:
                depth += {"{": 1, "}": -1}.get(blank[j], 0)
                j += 1
            spans.append((i, j))
        else:  # expression-bodied arrow: up to the statement end at depth 0
            depth, j = 0, i
            while j < len(blank):
                c = blank[j]
                if c in "([{":
                    depth += 1
                elif c in ")]}":
                    if depth == 0:
                        break
                    depth -= 1
                elif c in ";\n" and depth == 0:
                    break
                j += 1
            spans.append((i, j))
    return spans


def is_load(keep: str, m: re.Match) -> bool:
    url = m.group(0)
    if "www.w3.org/" in url:
        return False  # XML/SVG/MathML namespace identifiers are never fetched
    return bool(LOAD_EXT.search(url) or IMPORT_CTX.search(keep[max(0, m.start() - 24):m.start()]))


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
    has_guard = bool(("URLSearchParams" in all_js_blank and T_PARAM.search(all_js_keep))
                     or T_SEARCH.search(all_js_keep))
    preview_ok = has_render_at and has_guard

    for start, keep, blank in js_views:
        spans = render_at_spans(blank)
        for rule, rx, label in JS_RULES:
            for m in rx.finditer(blank):
                line = line_of(text, start + m.start())
                in_render_at = any(a <= m.start() < b for a, b in spans)
                if rule == "MC01" and in_render_at:
                    findings.append(Finding(rule, "error", line,
                        f"{label} `{m.group(0).strip()}` inside renderAt: the frame then depends on more than t"))
                elif rule == "MC01" and preview_ok:
                    findings.append(Finding(rule, "warn", line,
                        f"{label} `{m.group(0).strip()}` with renderAt + ?t= guard: confirm it only drives the live preview"))
                else:
                    findings.append(Finding(rule, "error", line, f"{label} `{m.group(0).strip()}`"))
        for rule, rx, label in JS_KEEP_RULES:
            for m in rx.finditer(keep):
                findings.append(Finding(rule, "error", line_of(text, start + m.start()), f"{label} `{m.group(0).strip()}`"))
        for m in _URL.finditer(keep):
            if is_load(keep, m):
                check_url(m.group(0), line_of(text, start + m.start()), findings)

    # MC10 — motion that runs on its own clock
    if re.search(r"\bgsap\b", all_js_blank) and not GSAP_SEEKED.search(all_js_blank):
        m = re.search(r"\bgsap\b", text)
        findings.append(Finding("MC10", "warn", line_of(text, m.start()) if m else 1,
            "GSAP plays on its own ticker: create timelines with paused: true and seek them from renderAt"))
    if is_html:
        for m in MEDIA_AUTOPLAY.finditer(text):
            findings.append(Finding("MC10", "warn", line_of(text, m.start()),
                f"autoplaying <{m.group(1).lower()}> plays on the wall clock: pause it and set currentTime = t in renderAt"))

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
                if not transition_is_live(m.group(1), m.group(2)):
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
        for sm in STYLE_ATTR.finditer(text):
            for m in TRANSITION.finditer(sm.group(2)):
                if transition_is_live(m.group(1), m.group(2)):
                    findings.append(Finding("MC05", "error", line_of(text, sm.start()),
                        f"inline CSS transition `{m.group(0).strip()}` is state-triggered, not seekable by t"))
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
