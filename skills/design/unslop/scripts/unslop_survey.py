#!/usr/bin/env python3
"""unslop_survey — full-repo UI-surface inventory with root-cause attribution.

Walks an arbitrary frontend codebase (Next.js / Vite+React / SvelteKit / Astro /
Nuxt / plain HTML) and emits ONE JSON manifest describing:

  * framework + routes + UI surfaces (pages, components, styles, copy files)
  * the *sources of the defaults* — fonts, icon libraries, component libraries,
    hard-coded colors / radii / shadows — attributed to the file that declares
    them, so a fix lands ONCE at the root instead of at every call site
  * copy tells (em dashes, emoji, "it's not X, it's Y", checkmark bullets)
  * SUBSTANCE tells the impeccable detector does not cover: legal routes
    (terms + privacy), loading / empty / error state coverage on async
    surfaces, placeholder or fake content, product-evidence (real screenshots,
    video) vs stock imagery, testimonial + pricing scaffolds
  * optionally (`--detect`) the impeccable detector's JSON findings, if the
    detector is installed — unslop composes it, never re-implements it

Stdlib only. Never edits the repo. Exit 0 on success, 2 on usage error.

    python3 unslop_survey.py <repo> [--detect] [--json OUT] [--md OUT] [--quiet]

The manifest is the input to unslop_gate.py (the crafted-floor gate) and to the
latent root-cause plan in SKILL.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

SCHEMA = "unslop-survey/1"

# skipped at ANY depth — never source
SKIP_DIRS = {
    ".git", "node_modules", ".next", ".nuxt", ".svelte-kit", ".astro", ".output", "coverage", ".turbo",
    ".vercel", ".cache", "vendor", "target", "venv", ".venv", "__pycache__", ".pytest_cache",
    "storybook-static", ".impeccable", ".unslop", "playwright-report", "test-results", ".playwright",
    "__snapshots__", ".nyc_output", ".lighthouseci", ".parcel-cache", ".angular", ".expo",
}
# skipped only as a TOP-LEVEL child of the repo — `src/app/reports/page.tsx` and `app/build/` are routes,
# `<root>/reports/` and `<root>/build/` are artefacts (a real app lost its /reports route to this list once)
SKIP_TOP_LEVEL_DIRS = {"dist", "build", "out", "reports", "lighthouse", "cypress", "tmp", "temp"}
# .ts/.js modules that carry landing/marketing copy — scanned for copy + substance tells like UI files
RE_COPY_MODULE = re.compile(r"^(content|copy|site(-?config)?|marketing|landing|messages|i18n|locales?|testimonials?|pricing|faq|hero|strings|seo)(\.(?!test|spec|stories|d)[a-z]+)*\.[cm]?[jt]s$", re.I)
# server-side / non-surface files that can never carry a loading state
RE_SERVER_SIDE_UI = re.compile(r"(^|/)(api|server|middleware|workers?)(/|$)|(^|/)route\.[jt]sx?$|\.server\.[jt]sx?$|middleware\.[jt]sx?$", re.I)
RE_SERVER_SIDE = re.compile(r"(^|/)(api|server|db|lib|utils?|hooks?|middleware|workers?|scripts?)(/|$)|(^|/)route\.[jt]sx?$|\.server\.[jt]sx?$|middleware\.[jt]s$|(^|/)use-[a-z-]+\.[jt]sx?$", re.I)
UI_EXT = {".tsx", ".jsx", ".vue", ".svelte", ".astro", ".html", ".htm", ".mdx"}
SCRIPT_EXT = {".ts", ".js", ".mjs", ".cjs"}
STYLE_EXT = {".css", ".scss", ".sass", ".less", ".pcss"}
COPY_EXT = {".md", ".mdx", ".txt", ".json"}
MAX_FILE_BYTES = 1_500_000

# ---------------------------------------------------------------------------
# Regexes (kept simple and explainable; every one is a *signal*, not a verdict)
# ---------------------------------------------------------------------------
RE_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
RE_NEXT_FONT = re.compile(r"from\s+['\"]next/font/(google|local)['\"]")
RE_NEXT_FONT_NAMES = re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]next/font/google['\"]")
# next/font/local: `import localFont from "next/font/local"` then `const brand = localFont({ src: …, variable: "--font-brand" })`
RE_NEXT_FONT_LOCAL_IMPORT = re.compile(r"import\s+(\w+)\s+from\s*['\"]next/font/local['\"]")
RE_NEXT_FONT_LOCAL_CALL_START = re.compile(r"(?:const|let|var)\s+(\w+)\s*=\s*(\w+)\(")
# any font file path inside the call — `src: "./x.woff2"`, `src: [{ path: "../fonts/X-Regular.woff2" }]`, `url(...)`
RE_FONT_FILE = re.compile(r"([A-Za-z0-9_-]+)\.(?:woff2?|otf|ttf)\b", re.I)


def _balanced_call(txt: str, open_idx: int) -> str:
    """Return the text inside the parentheses that open at txt[open_idx] ('('), honouring nesting and quotes."""
    depth = 0
    i = open_idx
    quote = None
    while i < len(txt):
        c = txt[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return txt[open_idx + 1:i]
        i += 1
    return txt[open_idx + 1:]
RE_GOOGLE_FONTS = re.compile(r"""fonts\.googleapis\.com/css2?\?([^"'\s)>]+)""")   # whole query: every family= param
RE_FONT_FACE = re.compile(r"@font-face\s*\{[^}]*font-family\s*:\s*['\"]?([^;'\"}]+)", re.I | re.S)
RE_TW_FONT = re.compile(r"fontFamily\s*:\s*\{([^}]*)\}", re.S)
# `--font-sans: Inter, …` is a family; `--font-size-lg: 1.25rem` / `--font-weight-bold: 700` are not.
RE_CSS_VAR_FONT = re.compile(r"--font-(?!size|weight|style|feature|variant|stretch|smoothing|synthesis|kerning|optical|leading|tracking|line)[a-z0-9-]*\s*:\s*([^;{}]+);", re.I)
RE_FONT_VALUE_LOOKS_LIKE_FAMILY = re.compile(r"^-?[a-z][a-z0-9 .'\"-]*$", re.I)     # -apple-system is a family
FONT_KEYWORDS = {"inherit", "initial", "unset", "revert", "revert-layer"}
# object-style CSS-in-JS / MUI createTheme: fontFamily: "Inter, sans-serif"
RE_OBJ_FONT_FAMILY = re.compile(r"""fontFamily\s*:\s*['"`]([^'"`]+)['"`]""")

ICON_LIBS = {
    "lucide-react": "lucide", "lucide": "lucide", "lucide-vue-next": "lucide", "lucide-svelte": "lucide",
    "@heroicons/react": "heroicons", "react-icons": "react-icons", "@tabler/icons-react": "tabler",
    "@phosphor-icons/react": "phosphor", "@radix-ui/react-icons": "radix-icons", "@iconify/react": "iconify",
    "@fortawesome/react-fontawesome": "fontawesome", "@mui/icons-material": "mui-icons",
}
COMPONENT_LIBS = {
    "@radix-ui": "radix", "class-variance-authority": "shadcn(cva)", "@mui/material": "mui",
    "@chakra-ui/react": "chakra", "@mantine/core": "mantine", "daisyui": "daisyui", "flowbite": "flowbite",
    "antd": "antd", "@headlessui/react": "headlessui", "@nextui-org/react": "nextui", "@heroui/react": "heroui",
    "primereact": "primereact", "@shadcn/ui": "shadcn", "shadcn": "shadcn", "@base-ui-components/react": "base-ui",
}
RE_IMPORT_FROM = re.compile(r"""(?:from|require\()\s*['"]([^'"]+)['"]""")

RE_EM_DASH = re.compile(r"—|&mdash;|&#8212;|\\u2014")   # the character, the HTML entity, the JS escape
# a standalone em dash is a typographic empty-value marker (`?? "—"`, `<td>—</td>`), not the prose tell
RE_EM_DASH_MARKER = re.compile(r"""(["'`])\s*—\s*\1|>\s*—\s*<|\{\s*"—"\s*\}""")   # incl. " — " separator args (.split/.join)
RE_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U00002B50\U00002B55\U0001F900-\U0001F9FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\U0001F1E6-\U0001F1FF✅✨⚡⭐\U0001F525\U0001F680\U0001F4A1\U0001F389]"
)
RE_CHECKMARK = re.compile("[✓✔✅☑]")
# comma/dash-separated contrasts stay loose; PERIOD-separated ones require an article after not/isn't —
# "It's not a chatbot. It's a teammate." is the tell, "It's not available on iPad. It's available on
# desktop." is a factual compatibility note (codex r1 blocker).
RE_NOT_X_BUT_Y = re.compile(
    r"\b(?:it'?s|it is|this is|we'?re|that'?s)\s+not\s+(?:just\s+|about\s+|a\s+|an\s+|another\s+)?[^.;:\n]{2,60}?[,;—–-]+\s*(?:it'?s|this is|we'?re|that'?s|but)\b"
    r"|\b(?:it|this|that|the [a-z]{2,12}) isn'?t (?:just |about )?(?:a|an|another|the) [^.;:\n]{2,60}?[,;—–-]+\s*(?:it'?s|this is|that'?s|but)\b"
    r"|\b(?:it'?s|it is|this is|we'?re|that'?s)\s+not\s+(?:just\s+)?(?:a|an|another)\s+[^.;:\n]{2,40}?\.\s+(?:it'?s|this is|we'?re|that'?s)\s"
    r"|\b(?:it|this|that|the [a-z]{2,12}) isn'?t (?:just )?(?:a|an|another|the) [^.;:\n]{2,40}?\.\s+(?:it'?s|this is|that'?s)\s",
    re.I,
)

# sentence-level prose slop on product surfaces — after petergyang/no-ai-slop (github.com/petergyang/no-ai-slop,
# read verbatim 2026-08-20), curated to the forms that recur on UI/marketing surfaces with low false-positive
# risk. Stance kept from that skill: a named pattern is evidence a human can check — never a claim of AI
# authorship. Single-sentence shapes match per stripped line; multi-sentence shapes match on the whole file.
PROSE_KEYS = ("faux_insight", "throat_clearing", "colon_reveal", "fake_profound", "importance_puffery",
              "weasel_attribution", "rhetorical_setup", "dramatic_simple", "superficial_ing", "negative_listing")
PROSE_PATTERNS = {
    "faux_insight": re.compile(r"what nobody tells you|what no one tells you|what most people (?:get wrong|miss|don'?t)|the part everyone misses|nobody (?:talks|is talking) about|here'?s what nobody", re.I),
    "throat_clearing": re.compile(r"here'?s the thing|let me be clear|let'?s be (?:honest|real|clear)|let'?s face it|i'?ll be honest|the uncomfortable truth|truth be told", re.I),
    "colon_reveal": re.compile(r"\b(?:the best part|the kicker|the catch|the twist|the magic|the secret|plot twist)\s*:", re.I),
    "fake_profound": re.compile(r"\bthe future (?:of [\w .'-]{1,40})?is (?:already\s+)?(?:here|now)\b|welcome to the future", re.I),
    "importance_puffery": re.compile(r"a testament to|marks? a pivotal|pivotal moment|plays? a vital role|stands? as a testament|solidif(?:ies|y|ying) (?:its|our|their)|underscor(?:es|ing) (?:its|our|the)", re.I),
    "weasel_attribution": re.compile(r"experts (?:agree|say)|studies (?:show|suggest)|research shows|science says|scientists (?:agree|say)|industry (?:leaders|reports) (?:agree|suggest|say)|widely regarded as", re.I),
    "rhetorical_setup": re.compile(r"what if i told you|think about it[.:]|imagine a world|in a world where|picture this[.:]", re.I),
    "dramatic_simple": re.compile(r"it'?s that (?:simple|easy)\b|it really is that (?:simple|easy)|that'?s it\.\s+that'?s the", re.I),
    "superficial_ing": re.compile(r",\s*(?:highlighting|underscoring|showcasing|signaling|cementing|reinforcing|demonstrating|reflecting) (?:our|its|their|the) (?:commitment|dedication|passion|mission|importance|significance|value|power|expertise|focus)", re.I),
}
RE_CITATION = re.compile(r"\[\d{1,3}\]|https?://|\bdoi\.org|<(?:a|cite|sup)\b", re.I)
RE_HTML_TAG = re.compile(
    r"</?(?:div|span|p|a|b|i|u|em|strong|small|li|ul|ol|h[1-6]|section|main|aside|img|br|hr|table|thead"
    r"|tbody|td|th|tr|button|input|label|form|select|option|textarea|header|footer|nav|article|figure"
    r"|figcaption|blockquote|cite|sup|sub|code|pre|video|audio|source|iframe|svg|path|dialog|details"
    r"|summary|mark|time|address|dl|dt|dd|fieldset|legend|picture|canvas|template|slot)\b[^<>]*>", re.I)
PROSE_PATTERNS_MULTI = {
    "fake_profound": re.compile(r"isn'?t coming[.!]\s+it'?s already here", re.I),
    "negative_listing": re.compile(r"\bno (?:more )?\w[\w' -]{0,24}\.\s+no \w[\w' -]{0,24}\.\s+(?:no|just|only)\b|\bnot (?:a|an|your) [\w' -]{2,30}\.\s+not (?:a|an|your)\b", re.I),
}
BUZZWORDS = [
    r"supercharg(?:e|ed|es|ing)", r"unleash(?:ed|es|ing)?", r"revolutioni[sz](?:e|ed|es|ing)", r"seamless(?:ly)?",
    r"effortless(?:ly)?", r"next-gen", r"10x", r"game[- ]chang(?:er|ers|ing)", r"cutting-edge", r"state-of-the-art",
    r"empower(?:s|ed|ing|ment)?", r"unlock(?:s|ed|ing)?", r"elevat(?:e|es|ed|ing)", r"streamlin(?:e|es|ed|ing)",
    r"harness the power",
    # no-ai-slop banned-word deltas that read as slop on a product surface (2026-08)
    r"delv(?:e|es|ed|ing)", r"foster(?:s|ed|ing)?", r"tapestry", r"transformative", r"transform(?:s|ing)? your",
    r"ever-evolving", r"embark(?:s|ed|ing)?", r"multifaceted", r"meticulous(?:ly)?", r"paramount",
    r"paradigm[- ]shift(?:s|ing)?", r"this changes everything", r"this is huge",
]
RE_BUZZ = re.compile(r"(?<![\w-])(?:" + "|".join(BUZZWORDS) + r")(?![\w-])", re.I)
RE_CSS_TOKENS = re.compile(r"var\([^)]*\)|--[\w-]+")   # var(--x) and --x custom properties only — hyphenated PROSE ("next-gen") stays
RE_CODE_ONLY_LINE = re.compile(r"^\s*(import\s|//|/\*|\*|\{/\*|@apply|[.#@][\w-]+\s*\{)")
# `<h1 className="text-xl">Supercharge…</h1>` must still be scanned: strip attribute payloads, keep the text
RE_JSX_ATTR = re.compile(r"""\b[\w:-]+\s*=\s*(?:"[^"]*"|'[^']*'|\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})""")


# quoted literals only — `alt={"…"}` / `alt={t("key")}` JSX-expression copy is a known gap (i18n keys are not copy anyway)
RE_COPY_ATTR_VALUES = re.compile(r"""\b(?:title|alt|placeholder|aria-label|label|description|subtitle|heading|tagline|caption)\s*=\s*(?:"([^"]*)"|'([^']*)'|\{\s*"([^"]*)"\s*\}|\{\s*'([^']*)'\s*\})""", re.I)
RE_TAG = re.compile(r"<[^<>]*>")


def _strip_attrs(line: str) -> str:
    """Keep the copy, drop the markup: copy-bearing attribute values are kept, every other attribute payload,
    bare boolean attributes (`<iframe seamless>`) and tag names are removed."""
    kept = " ".join(v for pair in RE_COPY_ATTR_VALUES.findall(line) for v in pair if v)
    body = RE_JSX_ATTR.sub(" ", line)
    body = RE_TAG.sub(" ", body)
    body = RE_CSS_TOKENS.sub(" ", body)     # backgroundColor: "var(--color-surface-elevated)" is not copy; "next-gen" prose survives
    return f"{body} {kept}"

# --- substance -------------------------------------------------------------
LEGAL_TERMS = re.compile(r"(^|/)(terms(-of-(service|use))?|tos|terms-and-conditions|legal/terms|conditions)(/|\.|$)", re.I)
LEGAL_PRIVACY = re.compile(r"(^|/)(privacy(-policy)?|legal/privacy|datenschutz|privacidad)(/|\.|$)", re.I)
RE_HREF_TERMS = re.compile(r"""href\s*=\s*['"{]?[^'">}]*?(terms|tos|conditions)[^'">}]*""", re.I)
RE_HREF_PRIVACY = re.compile(r"""href\s*=\s*['"{]?[^'">}]*?(privacy|privacidad|datenschutz)[^'">}]*""", re.I)

RE_ASYNC = re.compile(
    r"\bfetch\(|useQuery\(|useSWR\(|useInfiniteQuery\(|useMutation\(|createResource\(|\$fetch\(|useFetch\(|useAsyncData\(|await\s+(?:prisma|db|supabase|client|api|sql|fetch|getServerSession)\b|axios\.(get|post)|graphql\(|trpc\.",
)
RE_LOADING_STATE = re.compile(
    r"Skeleton|animate-pulse|aria-busy|isLoading|isPending|isFetching|loading\s*[?&]|<Spinner|<Loader|status\s*===?\s*['\"]loading['\"]|\{#await|v-if=\"(loading|pending)\"|Suspense|fallback=",
)
RE_ERROR_STATE = re.compile(r"""ErrorBoundary|isError|error\.tsx|<Alert\b|role=["']alert["']|status\s*===?\s*['"]error['"]|onError=|\berror\s*&&|\{#if error|v-if=["']error["']""")
RE_EMPTY_STATE = re.compile(r"length\s*===?\s*0|\.length\s*\?|No\s+(results|items|data|projects|messages|orders)|Nothing\s+(here|yet|to show)|empty[-_ ]?state|EmptyState", re.I)

PLACEHOLDER_PATTERNS = {
    "lorem-ipsum": re.compile(r"lorem ipsum(?:\s+dolor sit amet)?|dolor sit amet", re.I),
    "john-jane-doe": re.compile(r"\b(john|jane)\s+doe\b", re.I),
    "acme": re.compile(r"\bAcme(\s+(Inc|Corp|Co)\.?)?\b"),
    "your-company": re.compile(r"\b(your|the)\s+company\s+name\b|\[?your\s+(company|name|product|brand)\]?", re.I),
    # "Coming soon" is the honest label for an unshipped feature (the arc recommends it over a fake demo) — not counted
    "insert-here": re.compile(r"\[(?:insert|add|your|placeholder)\s+[a-z][^\]]{2,}\]|\bTBD\b", re.I),
    "todo-in-copy": re.compile(r">\s*(TODO|FIXME|XXX)\b|['\"](TODO|FIXME)[:\s]"),
    "stock-image-host": re.compile(r"(images\.unsplash\.com|source\.unsplash\.com|picsum\.photos|placehold\.co|placeholder\.com|via\.placeholder|placekitten|dummyimage\.com|loremflickr|pravatar\.cc|randomuser\.me|ui-avatars\.com|i\.pravatar)", re.I),
    "example-domain": re.compile(r"\b[a-z0-9.-]*example\.(com|org|net)\b", re.I),
    "fake-metrics": re.compile(r"\b(99\.9+%|10,?000\+|1M\+|500\+|10x)\s*(uptime|users|customers|teams|companies|developers|faster)?\b", re.I),
}
RE_LANDING = re.compile(r"<Hero|className=\"hero|id=\"hero|Get started( free)?|Start (for )?free|Sign up free|Book a demo|Request (a )?demo|Join the waitlist|Start your free trial", re.I)
RE_TESTIMONIAL = re.compile(r"testimonial|what (our )?(customers|users|clients) (say|are saying)|<Quote|Reviews?Section|CustomerQuote", re.I)
RE_PRICING = re.compile(r"pricing|PricingTier|PricingCard|PricingTable|/pricing", re.I)
RE_TIER_WORDS = re.compile(r"\b(Free|Starter|Basic|Hobby|Pro|Team|Business|Enterprise|Premium|Plus|Growth|Scale)\b")
# real product video: a <video> element, a media src, or a known video embed — never a bare <iframe> or an accept=".mp4"
RE_VIDEO = re.compile(r"""<video\b|src\s*=\s*['"{][^'"}]*\.(?:mp4|webm|mov)\b|youtube(?:-nocookie)?\.com/embed|player\.vimeo\.com|loom\.com/embed|<mux-player|<MuxPlayer""", re.I)
RE_LOCAL_IMG = re.compile(r"""(?:src|href|url)\s*[=(:]\s*['"(]?(/?(?:public/|assets/|images?/|img/|screenshots?/|static/|media/)[^'"\s)]+\.(?:png|jpe?g|webp|avif|gif|svg))""", re.I)
# A local raster counts as *product evidence* only if it is not obviously decorative (logo, icon, favicon, avatar,
# og image, illustration, pattern, background) — svg never counts; a screenshots|demo|product|app path always does.
RE_IMG_DECORATIVE = re.compile(r"(logo|icon|favicon|avatar|og[-_.]|opengraph|illustration|pattern|bg[-_.]|background|badge|sprite|placeholder)", re.I)
RE_IMG_EVIDENCE_PATH = re.compile(r"(screenshot|screen|demo|product|app[-_./]|dashboard|ui[-_./]|preview|capture)", re.I)
RE_STOCK_IMG = PLACEHOLDER_PATTERNS["stock-image-host"]

# a hex colour literal in a style/attribute/CSS context — not `// issue #123`, not `href="#add-item"`, not `/docs#123456`
RE_HEX = re.compile(r"""(?<![\w/#&?=-])(?<!href=["'])(?<!href=\{["'])#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b(?![\w-])""")
RE_HREF_HASH_ATTR = re.compile(r"""href\s*=\s*(?:"#[^"]*"|'#[^']*'|\{[^}]*\})""")
TOKEN_BASENAMES = {"globals.css", "global.css", "app.css", "index.css", "styles.css", "variables.css", "main.css", "tokens.css", "theme.css", "tokens.ts", "tokens.js", "theme.ts", "theme.js"}
TOKEN_SEGMENTS = {"tokens", "theme", "themes", "design-system", "design-tokens", "styles"}


def is_token_file(rp: str) -> bool:
    parts = rp.replace("\\", "/").split("/")
    name = parts[-1].lower()
    return name in TOKEN_BASENAMES or name.startswith("tailwind.config") or any(seg.lower() in TOKEN_SEGMENTS for seg in parts[:-1])
RE_RADIUS_TW = re.compile(r"(?<![\w-])rounded(?:-(?:[trbl]{1,2}|ss|se|ee|es))?(?:-(?:none|xs|sm|md|lg|xl|2xl|3xl|4xl|full|\[[^\]]+\]))?(?![\w-])")
RE_RADIUS_CSS = re.compile(r"(?<![\w-])border-radius\s*:\s*([^;}{]+)", re.I)
RE_SHADOW_TW = re.compile(r"(?<![\w-])(?<!drop-)shadow(?:-(?:xs|sm|md|lg|xl|2xl|inner|none|\[[^\]]+\]))?(?![\w-])")
RE_SHADOW_CSS = re.compile(r"(?<![\w-])box-shadow\s*:\s*([^;}{]+)", re.I)
RE_TOKEN_DECL_LINE = re.compile(r"^\s*--[a-z0-9-]+\s*:", re.I)


def _norm_radius_class(cls: str) -> str:
    """rounded-t-md → rounded-md; rounded-ss-lg → rounded-lg (the *value* is the vocabulary, not the side)."""
    return re.sub(r"^rounded-(?:[trbl]{1,2}|ss|se|ee|es)(?=-|$)", "rounded", cls)
RE_GRADIENT_TW = re.compile(r"\bbg-gradient-to-[trbl]{1,2}\b|\bfrom-(?:purple|violet|fuchsia|pink|indigo)-\d{3}\b")
RE_GRADIENT_CSS = re.compile(r"(?:linear|radial|conic)-gradient\(", re.I)
RE_BACKDROP = re.compile(r"backdrop-filter|backdrop-blur", re.I)
# authored motion (keyframes, framer/motion, transition-all, decorative animate-* utilities) needs a reduced-motion
# story; essential utilities (spin/pulse/ping — spinners, skeletons) do not by themselves
RE_KEYFRAMES = re.compile(r"@keyframes|framer-motion|from\s+['\"]motion(?:/react)?['\"]|<motion\.\w+|transition-all|animate-(?!spin\b|pulse\b|ping\b|none\b|in\b|out\b)[a-z-]+", re.I)
# essential utilities (spinners, skeletons) and component-library presets (tw-animate-css `animate-in/out`,
# `fade-in-0`, `zoom-in-95`, `slide-in-from-*` — every shadcn dialog/tooltip) are library motion: WARN, not FAIL
RE_MOTION_ESSENTIAL = re.compile(r"animate-(?:spin|pulse|ping|in|out)\b|\b(?:fade|zoom|slide)-(?:in|out)(?:-|\b)")
RE_REDUCED_MOTION = re.compile(r"prefers-reduced-motion|useReducedMotion|motion-reduce:", re.I)

# The faces every AI-generated UI converges on (impeccable's overused-font list ∪ the reel's #10 ∪ common LLM picks).
# Dated: 2026-08 — a face leaves this list when it stops being the default, not when it stops being good.
AI_DEFAULT_WEB_FONTS = {
    "inter", "geist", "geist sans", "space grotesk", "roboto", "plus jakarta sans", "fraunces", "poppins",
    "manrope", "dm sans", "sora", "outfit", "montserrat", "open sans",
}
# The platform stack — a legitimate, deliberate choice (broomva-design uses it) but only when *stated*.
SYSTEM_STACK = {"system-ui", "-apple-system", "blinkmacsystemfont", "segoe ui", "arial", "helvetica", "helvetica neue", "sans-serif", "ui-sans-serif"}
DEFAULT_FONTS = AI_DEFAULT_WEB_FONTS | SYSTEM_STACK


SKIPPED: dict = {"oversized": [], "unreadable": []}


def _read(p: Path) -> str:
    """Read a text file; oversized (> MAX_FILE_BYTES) and unreadable files are recorded in SKIPPED,
    never silently dropped — the manifest reports them under counts.skipped."""
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            SKIPPED["oversized"].append(str(p))
            return ""
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        SKIPPED["unreadable"].append(str(p))
        return ""


def _git_files(root: Path) -> list[Path] | None:
    """Tracked + untracked-but-not-ignored files when `root` is inside a git work tree; None otherwise.
    Honouring .gitignore is what keeps generated artefacts (reports, build output) out of the survey."""
    if not shutil.which("git"):
        return None
    try:
        proc = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                              capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    out = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        rel_ = raw.decode("utf-8", errors="ignore")
        parts = rel_.split("/")
        dirs = parts[:-1]
        if any(seg in SKIP_DIRS for seg in dirs):
            continue
        if dirs and dirs[0] in SKIP_TOP_LEVEL_DIRS:
            continue
        if any(seg.startswith(".") for seg in dirs):       # same dot-dir rule as walk mode (src/.storybook)
            continue
        p = root / rel_
        if p.is_file() and not p.is_symlink():
            out.append(p)
    return out


WALK_MODE = {"mode": "walk"}


def walk(root: Path):
    git = _git_files(root)
    # git inventory with no UI/style file at all (nested .git, submodule, sparse checkout) → fall back to a walk
    if git and any(p.suffix.lower() in UI_EXT | STYLE_EXT for p in git):
        WALK_MODE["mode"] = "git"
        yield from git
        return
    WALK_MODE["mode"] = "walk"
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        if dirpath == str(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and d not in SKIP_TOP_LEVEL_DIRS]
        else:
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if not p.is_symlink():
                yield p


def rel(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------------------
# Framework + routes
# ---------------------------------------------------------------------------
def load_package_json(root: Path) -> dict:
    for cand in (root / "package.json",):
        if cand.exists():
            try:
                return json.loads(_read(cand) or "{}")
            except json.JSONDecodeError:
                return {}
    return {}


def detect_framework(root: Path, pkg: dict) -> dict:
    deps = {}
    for k in ("dependencies", "devDependencies", "peerDependencies"):
        deps.update(pkg.get(k, {}) or {})
    fw = "unknown"
    router = None
    if "next" in deps:
        fw = "next"
        if (root / "app").is_dir() or (root / "src" / "app").is_dir():
            router = "app"
        elif (root / "pages").is_dir() or (root / "src" / "pages").is_dir():
            router = "pages"
    elif "@sveltejs/kit" in deps:
        fw, router = "sveltekit", "routes"
    elif "svelte" in deps:
        fw = "svelte"
    elif "nuxt" in deps:
        fw, router = "nuxt", "pages"
    elif "astro" in deps:
        fw, router = "astro", "pages"
    elif "@remix-run/react" in deps or "react-router" in deps and "@react-router/dev" in deps:
        fw, router = "remix", "routes"
    elif "@angular/core" in deps:
        fw = "angular"
    elif "vue" in deps:
        fw = "vue"
    elif "react" in deps:
        fw = "react"
    elif any((root / f).exists() for f in ("index.html",)):
        fw = "static-html"
    return {"name": fw, "router": router, "deps": sorted(deps.keys())[:400], "tailwind": "tailwindcss" in deps or bool(list(root.glob("tailwind.config.*"))), "typescript": "typescript" in deps}


def derive_routes(root: Path, fw: dict, ui_files: list[Path]) -> list[dict]:
    routes = []
    name, router = fw["name"], fw["router"]
    for f in ui_files:
        r = rel(root, f).replace("\\", "/")
        route = None
        if name == "next" and router == "app":
            m2 = re.match(r"^(?:src/)?app/(.*/)?(page|loading|error|not-found)\.(tsx|jsx|js|ts|mdx)$", r)
            if m2:
                seg = (m2.group(1) or "").rstrip("/")
                seg = re.sub(r"\(([^)]+)\)/?", "", seg)  # route groups
                seg = re.sub(r"@[^/]+/?", "", seg)  # parallel routes
                route = "/" + seg if seg else "/"
                routes.append({"route": route, "file": r, "kind": m2.group(2)})
            continue
        if name == "next" and router == "pages":
            m = re.match(r"^(?:src/)?pages/(.*)\.(tsx|jsx|js|ts|mdx)$", r)
            if m and not m.group(1).startswith(("_app", "_document", "api/")):
                seg = re.sub(r"/?index$", "", m.group(1))
                routes.append({"route": "/" + seg if seg else "/", "file": r, "kind": "page"})
            continue
        if name == "sveltekit":
            m = re.match(r"^src/routes/(.*/)?\+(page|layout|error)\.svelte$", r)
            if m:
                seg = (m.group(1) or "").rstrip("/")
                seg = re.sub(r"\(([^)]+)\)/?", "", seg)
                routes.append({"route": "/" + seg if seg else "/", "file": r, "kind": m.group(2)})
            continue
        if name in ("astro", "nuxt") or (name in ("react", "vue") and "/pages/" in "/" + r):
            m = re.match(r"^(?:src/)?pages/(.*)\.(astro|vue|tsx|jsx|md|mdx)$", r)
            if m:
                seg = re.sub(r"/?index$", "", m.group(1))
                routes.append({"route": "/" + seg if seg else "/", "file": r, "kind": "page"})
            continue
        if name == "remix":
            m = re.match(r"^app/routes/(.*)\.(tsx|jsx)$", r)
            if m:
                seg = m.group(1).replace(".", "/").replace("_index", "")
                routes.append({"route": "/" + seg.strip("/"), "file": r, "kind": "page"})
            continue
        if f.suffix in (".html", ".htm"):
            seg = re.sub(r"/?index\.html?$", "", r)
            seg = re.sub(r"\.html?$", "", seg)
            routes.append({"route": "/" + seg if seg else "/", "file": r, "kind": "page"})
    # dedupe by (route, kind)
    seen = set()
    out = []
    for x in routes:
        k = (x["route"], x["kind"], x["file"])
        if k not in seen:
            seen.add(k)
            out.append(x)
    return sorted(out, key=lambda x: (x["route"], x["kind"]))


# ---------------------------------------------------------------------------
# Main survey
# ---------------------------------------------------------------------------
def git_toplevel(root: Path) -> Path | None:
    if not shutil.which("git"):
        return None
    try:
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(proc.stdout.strip()) if proc.returncode == 0 and proc.stdout.strip() else None


def find_design_docs(root: Path) -> dict:
    """DESIGN.md / PRODUCT.md at the app root, or in a parent up to the git toplevel (monorepos keep the
    design contract at the repo root — apps/web/ must not read as 'no direction')."""
    top = git_toplevel(root)
    out = {"DESIGN.md": False, "PRODUCT.md": False, "paths": {}}
    cur = root
    for _ in range(6):
        for name in ("DESIGN.md", "PRODUCT.md"):
            if not out[name] and (cur / name).is_file():
                out[name] = True
                out["paths"][name] = str(cur / name)
        if (top and cur == top) or cur.parent == cur:
            break
        cur = cur.parent
    return out


def find_app_root(root: Path) -> Path:
    """If `root` has no package.json but exactly one nested app (depth ≤ 2) does and declares a known
    framework, survey that app instead — monorepos with `app/` or `apps/web/` are the common shape."""
    if (root / "package.json").exists():
        root_fw = detect_framework(root, load_package_json(root))
        if root_fw["name"] not in ("unknown", "static-html"):
            return root                       # the root IS the app
        # a workspace root with its own manifest (tooling only) — look for the single nested frontend app
    def has_ui(d: Path, limit: int = 3) -> bool:
        n = 0
        for dp, dn, fns in os.walk(d):
            dn[:] = [x for x in dn if x not in SKIP_DIRS and not x.startswith(".")]
            if dp[len(str(d)):].count(os.sep) > limit:
                dn[:] = []
            if any(Path(f).suffix.lower() in UI_EXT for f in fns):
                return True
            n += 1
            if n > 400:
                break
        return False
    if any((root / f).exists() for f in ("index.html",)) or has_ui(root, limit=1):
        return root                                       # the root itself carries UI — never re-root away from it
    cands = []
    for depth in (1, 2):
        for pj in root.glob("/".join(["*"] * depth) + "/package.json"):
            parts = pj.relative_to(root).parts
            if any(seg in SKIP_DIRS for seg in parts) or parts[0] in SKIP_TOP_LEVEL_DIRS:
                continue
            fw = detect_framework(pj.parent, load_package_json(pj.parent))
            if fw["name"] not in ("unknown", "static-html") and has_ui(pj.parent):
                cands.append(pj.parent)
        if cands:
            break
    return cands[0] if len(cands) == 1 else root


def survey(root: Path, detect: bool = False, detector_cmd: str | None = None, detector_timeout: int = 600) -> dict:
    root = root.resolve()
    survey_root_arg = root
    root = find_app_root(root)
    SKIPPED["oversized"].clear()
    SKIPPED["unreadable"].clear()
    pkg = load_package_json(root)
    fw = detect_framework(root, pkg)

    ui_files: list[Path] = []
    style_files: list[Path] = []
    script_files: list[Path] = []
    copy_files: list[Path] = []
    for p in walk(root):
        ext = p.suffix.lower()
        if ext in UI_EXT:
            ui_files.append(p)
        elif ext in STYLE_EXT:
            style_files.append(p)
        elif ext in SCRIPT_EXT:
            script_files.append(p)
        elif ext in COPY_EXT:
            copy_files.append(p)

    routes = derive_routes(root, fw, ui_files)
    deps_all = set(fw.get("deps", []))

    # --- accumulators ------------------------------------------------------
    font_sites: dict[str, list[str]] = defaultdict(list)     # primary family -> [file:line]
    font_fallbacks: Counter = Counter()                       # families that only appear as fallbacks
    landing_hints: list[str] = []
    font_face_selfhosted: set[str] = set()
    next_font_imports: list[str] = []
    google_font_links: list[str] = []
    icon_imports: dict[str, list[str]] = defaultdict(list)
    component_libs: set[str] = set()
    for dep in deps_all:
        for lib, tag in COMPONENT_LIBS.items():
            if dep == lib or dep.startswith(lib + "/"):
                component_libs.add(tag)
    copy_tells = {"em_dash": [], "emoji": [], "not_x_but_y": [], "checkmark_bullets": [], "buzzwords": [],
                  **{k: [] for k in PROSE_KEYS}}
    legal = {"terms_route": None, "privacy_route": None, "terms_link_sites": [], "privacy_link_sites": []}
    async_files: dict[str, dict] = {}
    placeholders: dict[str, list[str]] = defaultdict(list)
    testimonials: list[str] = []
    pricing: dict = {"files": [], "tier_word_hits": Counter()}
    evidence = {"video_sites": [], "local_image_sites": [], "evidence_image_sites": [], "stock_image_sites": []}
    hex_sites: dict[str, list[str]] = defaultdict(list)
    radius_values: Counter = Counter()
    radius_sites: dict[str, list[str]] = defaultdict(list)
    shadow_values: Counter = Counter()
    gradient_sites: list[str] = []
    backdrop_sites: list[str] = []
    motion_sites: list[str] = []
    motion_essential_sites: list[str] = []
    reduced_motion_sites: list[str] = []
    loading_files_next: list[str] = []
    error_files_next: list[str] = []
    design_docs = find_design_docs(root)

    def site(p: Path, ln: int) -> str:
        return f"{rel(root, p)}:{ln}"

    for r_ in routes:
        if r_["kind"] == "loading":
            loading_files_next.append(r_["file"])
        if r_["kind"] == "error":
            error_files_next.append(r_["file"])
        if LEGAL_TERMS.search(r_["route"]) and not legal["terms_route"]:
            legal["terms_route"] = r_["route"]
        if LEGAL_PRIVACY.search(r_["route"]) and not legal["privacy_route"]:
            legal["privacy_route"] = r_["route"]

    text_files = ui_files + style_files + script_files
    for p in text_files:
        txt = _read(p)
        if not txt:
            continue
        rp = rel(root, p)
        is_style = p.suffix.lower() in STYLE_EXT
        is_ui = p.suffix.lower() in UI_EXT
        # tests, stories, scripts and generated-image routes are code, not the product's copy or token surface
        is_non_surface = bool(re.search(r"(\.(test|spec|stories|e2e)\.[cm]?[jt]sx?$)|(^|/)(__tests__|tests?|e2e|scripts?|__mocks__|fixtures?)(/|$)|(^|/)(opengraph-image|twitter-image|apple-icon|icon)\.[jt]sx?$", rp, re.I))
        if is_ui and is_non_surface:
            is_ui = False
        is_config = "tailwind.config" in p.name or p.name in ("postcss.config.js", "postcss.config.mjs")
        lines = txt.splitlines()

        # fonts
        for m in RE_FONT_FAMILY.finditer(txt):
            ln = txt.count("\n", 0, m.start()) + 1
            fams = [f.strip().strip("'\"").lower() for f in m.group(1).split(",")]
            fams = [f for f in fams if f and not f.startswith("var(") and f not in FONT_KEYWORDS]
            if not fams:
                continue
            font_sites[fams[0]].append(site(p, ln))          # primary face
            for fam in fams[1:]:
                font_fallbacks[fam] += 1                       # fallback stack only
        for m in RE_FONT_FACE.finditer(txt):
            font_face_selfhosted.add(m.group(1).strip().strip("'\"").lower())
        lf = RE_NEXT_FONT_LOCAL_IMPORT.search(txt)
        if lf:
            fn = lf.group(1)
            for m in RE_NEXT_FONT_LOCAL_CALL_START.finditer(txt):
                if m.group(2) != fn:
                    continue
                var = m.group(1)
                body = _balanced_call(txt, m.end() - 1)          # nested {…[{ path: … }]…} handled
                srcm = RE_FONT_FILE.search(body)
                raw = srcm.group(1) if srcm else var
                fam = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw)          # GeistMono → Geist Mono
                fam = re.sub(r"[_-]+", " ", fam).strip().lower()         # Signifier-Regular → signifier regular
                fam = re.sub(r"(\s+(regular|variable|vf|bold|medium|light|italic|semibold|black|thin|display))+$", "", fam).strip() or var.lower()
                ln = txt.count("\n", 0, m.start()) + 1
                font_sites[fam].append(site(p, ln))
                font_face_selfhosted.add(fam)
                next_font_imports.append(f"local:{var}={fam}@{rp}")
        for m in RE_NEXT_FONT_NAMES.finditer(txt):
            for name in m.group(1).split(","):
                n = name.strip().split(" as ")[0].strip()
                if n:
                    next_font_imports.append(f"{n}@{rp}")
                    fam = re.sub(r"_", " ", n).lower()
                    font_sites[fam].append(site(p, txt.count("\n", 0, m.start()) + 1))
        for m in RE_GOOGLE_FONTS.finditer(txt):
            query = m.group(1).replace("&amp;", "&")
            fams_ = [q[len("family="):] for q in query.split("&") if q.startswith("family=")]
            google_font_links.append(f"{'+'.join(fams_)}@{rp}")
            for fam in fams_:
                fam = fam.split(":")[0].replace("+", " ").replace("%20", " ").strip().lower()
                if fam:
                    font_sites[fam].append(site(p, txt.count("\n", 0, m.start()) + 1))
        if is_config:
            for m in RE_TW_FONT.finditer(txt):
                for fm in re.finditer(r"['\"]([A-Za-z][A-Za-z0-9 ]+)['\"]", m.group(1)):
                    font_sites[fm.group(1).lower()].append(site(p, txt.count("\n", 0, m.start()) + 1))
        if is_style:
            for m in RE_CSS_VAR_FONT.finditer(txt):
                fams = [f.strip().strip("'\"").lower() for f in m.group(1).split(",")]
                fams = [f for f in fams if f and not f.startswith("var(") and f not in FONT_KEYWORDS and RE_FONT_VALUE_LOOKS_LIKE_FAMILY.match(f) and not re.search(r"\d", f)]
                if fams:
                    font_sites[fams[0]].append(site(p, txt.count("\n", 0, m.start()) + 1))
                    for fam in fams[1:]:
                        font_fallbacks[fam] += 1
        if is_ui or p.suffix.lower() in SCRIPT_EXT:
            for m in RE_OBJ_FONT_FAMILY.finditer(txt):
                fams = [f.strip().strip("'\"").lower() for f in m.group(1).split(",")]
                fams = [f for f in fams if f and not f.startswith("var(") and f not in FONT_KEYWORDS]
                if fams:
                    font_sites[fams[0]].append(site(p, txt.count("\n", 0, m.start()) + 1))
                    for fam in fams[1:]:
                        font_fallbacks[fam] += 1

        # icons + component libs
        for m in RE_IMPORT_FROM.finditer(txt):
            mod = m.group(1)
            for lib, tag in ICON_LIBS.items():
                if mod == lib or mod.startswith(lib + "/"):
                    icon_imports[tag].append(rp)
            for lib, tag in COMPONENT_LIBS.items():
                if mod == lib or mod.startswith(lib + "/"):
                    component_libs.add(tag)
        if "/components/ui/" in ("/" + rp) or rp.startswith("components/ui/"):
            component_libs.add("shadcn?(components/ui)")

        # copy tells — UI files and .ts/.js *copy modules* (content/site/marketing/i18n…, incl. src/lib/content.ts); never api/server/hook code
        # a .ts/.js module is a *copy module* when its basename (content.ts, site.ts, testimonials.ts, locales.ts…)
        # or a path segment (content/ data/ copy/ locales/ i18n/ messages/ marketing/) says so. `src/lib/content.ts`
        # IS scanned — lib/ is where this copy usually lives. API routes, server modules, middleware and hooks are
        # never copy modules, whatever they are named.
        _segs = rp.replace("\\", "/").split("/")
        is_copy_module = (
            not is_non_surface
            and p.suffix.lower() in SCRIPT_EXT
            and (bool(RE_COPY_MODULE.match(_segs[-1])) or any(seg.lower() in ("content", "data", "copy", "locales", "locale", "i18n", "messages", "marketing") for seg in _segs[:-1]))
            and not re.search(r"(^|/)(api|server|middleware|hooks?)(/|$)|(^|/)route\.[jt]sx?$|\.server\.[jt]sx?$|(^|/)use-[a-z-]+\.[jt]sx?$", rp, re.I)
        )
        is_prose_mdx = p.suffix.lower() == ".mdx" and re.search(r"(^|/)(content|docs?|blog|posts?|articles?)(/|$)", rp, re.I)
        if (is_ui and not is_prose_mdx) or is_copy_module:
            # blank block comments with newlines preserved: a continuation line of a multi-line
            # /* … */ or {/* … */} comment carries no marker prefix and read as UI copy otherwise
            comment_free = re.sub(r"/\*.*?\*/", lambda mm: "\n" * mm.group(0).count("\n"), txt, flags=re.S)
            for i, line in enumerate(comment_free.splitlines(), 1):
                st = line.lstrip()
                if st.startswith(("//", "/*", "*", "{/*", "<!--", "import ")):
                    continue
                code_free = re.sub(r"//.*$|\{/\*.*?\*/\}|/\*.*?\*/", "", line)  # strip trailing comments
                if RE_EM_DASH.search(RE_EM_DASH_MARKER.sub(" ", code_free)):
                    copy_tells["em_dash"].append(site(p, i))
                if RE_EMOJI.search(code_free):
                    copy_tells["emoji"].append(site(p, i))
                if RE_CHECKMARK.search(code_free):
                    copy_tells["checkmark_bullets"].append(site(p, i))
                if not RE_CODE_ONLY_LINE.search(line):
                    # three stripping paths (codex r1–r3):
                    #  markup files → full JSX stripper (keeps copy-bearing attrs, drops payloads/tags);
                    #  plain copy module WITH a known HTML tag (template string) → strip TAGS FIRST — the
                    #    attrs ride inside the tag, and _strip_attrs would let RE_JSX_ATTR eat the whole
                    #    `tip = '<div …>inner</div>'` assignment before tag removal, losing the inner text;
                    #  plain assignment line → scan as-is, or `pitch = "Delve…"` parses as an attr payload.
                    if is_ui or p.suffix.lower() in (".tsx", ".jsx"):
                        prose = _strip_attrs(code_free)
                    elif RE_HTML_TAG.search(code_free):
                        prose = RE_CSS_TOKENS.sub(" ", RE_TAG.sub(" ", code_free))
                    else:
                        prose = RE_CSS_TOKENS.sub(" ", code_free)
                    if RE_BUZZ.search(prose):
                        copy_tells["buzzwords"].append(site(p, i))
                    for k, rx in PROSE_PATTERNS.items():
                        if rx.search(prose):
                            # "Research shows …[1]" / "…(see study)" names its source — the weasel tell is the UNcited claim
                            if k == "weasel_attribution" and RE_CITATION.search(code_free):
                                continue
                            copy_tells[k].append(site(p, i))
            for m in RE_NOT_X_BUT_Y.finditer(txt):
                copy_tells["not_x_but_y"].append(site(p, txt.count("\n", 0, m.start()) + 1))
            for k, rx in PROSE_PATTERNS_MULTI.items():
                for m in rx.finditer(txt):
                    copy_tells[k].append(site(p, txt.count("\n", 0, m.start()) + 1))

        if is_ui or is_copy_module:
            # legal links
            for m in RE_HREF_TERMS.finditer(txt):
                legal["terms_link_sites"].append(site(p, txt.count("\n", 0, m.start()) + 1))
            for m in RE_HREF_PRIVACY.finditer(txt):
                legal["privacy_link_sites"].append(site(p, txt.count("\n", 0, m.start()) + 1))

            # substance: landing / testimonials / pricing / evidence
            if RE_LANDING.search(txt):
                landing_hints.append(rp)
            if RE_TESTIMONIAL.search(txt) and not is_prose_mdx:
                testimonials.append(rp)
            if (RE_PRICING.search(txt) or "pricing" in rp.lower()) and not is_prose_mdx:
                pricing["files"].append(rp)
                for m in RE_TIER_WORDS.finditer(txt):
                    pricing["tier_word_hits"][m.group(1)] += 1
            if RE_VIDEO.search(txt):
                evidence["video_sites"].append(rp)
            for m in RE_LOCAL_IMG.finditer(txt):
                path_ = m.group(1)
                evidence["local_image_sites"].append(f"{path_}@{rp}")
                is_raster = not path_.lower().endswith(".svg")
                if is_raster and (RE_IMG_EVIDENCE_PATH.search(path_) or not RE_IMG_DECORATIVE.search(path_)):
                    evidence["evidence_image_sites"].append(f"{path_}@{rp}")
            for m in RE_STOCK_IMG.finditer(txt):
                evidence["stock_image_sites"].append(site(p, txt.count("\n", 0, m.start()) + 1))

        # async *surfaces* — UI files only; API routes / server modules / middleware cannot carry a skeleton
        # (a .tsx under lib/ or hooks/ is still a component and still counts)
        if is_ui and not RE_SERVER_SIDE_UI.search(rp):
            if RE_ASYNC.search(txt):
                async_files[rp] = {
                    "loading": bool(RE_LOADING_STATE.search(txt)),
                    "error": bool(RE_ERROR_STATE.search(txt)),
                    "empty": bool(RE_EMPTY_STATE.search(txt)),
                }

        # placeholders (UI + copy modules). `placeholder="you@example.com"` / "Acme Labs" on an input is an example
        # value, not fake content; prose MDX (articles) only counts lorem / John Doe.
        if is_ui or is_copy_module:
            for key, rx in PLACEHOLDER_PATTERNS.items():
                if is_prose_mdx and key not in ("lorem-ipsum", "john-jane-doe"):
                    continue
                for m in rx.finditer(txt):
                    ln = txt.count("\n", 0, m.start()) + 1
                    if key in ("example-domain", "acme", "your-company") and re.search(r"placeholder\s*=", lines[ln - 1] if ln - 1 < len(lines) else ""):
                        continue
                    placeholders[key].append(site(p, ln))

        # visual vocabulary — the product's token surface; prose MDX (embedded article figures) is content
        if (is_ui and not is_prose_mdx) or is_style:
            token_file = is_token_file(rp)
            if not token_file:
                for i, line in enumerate(lines, 1):
                    st = line.lstrip()
                    if st.startswith(("//", "/*", "*", "{/*", "<!--")):
                        continue
                    scan = RE_HREF_HASH_ATTR.sub(" ", line)   # drop href="#anchor" payloads, keep the rest of the line
                    for m in RE_HEX.finditer(scan):
                        hex_sites[m.group(0).lower()].append(site(p, i))
            for m in RE_RADIUS_TW.finditer(txt):
                k = _norm_radius_class(m.group(0))
                radius_values[k] += 1
                radius_sites[k].append(rp)
            in_keyframes = 0
            for i, line in enumerate(lines, 1):
                # values inside @keyframes are animation states (pulse rings), not vocabulary
                if "@keyframes" in line:
                    in_keyframes = max(0, line.count("{") - line.count("}"))   # 0 when the block closes on the same line
                    continue
                if in_keyframes:
                    in_keyframes += line.count("{") - line.count("}")
                    if in_keyframes <= 0:
                        in_keyframes = 0
                    continue
                if RE_TOKEN_DECL_LINE.match(line):
                    continue  # `--radius-md: 0.5rem;` is the vocabulary itself, not drift
                for m in RE_RADIUS_CSS.finditer(line):
                    v = m.group(1).strip()
                    if v.startswith("var("):
                        continue  # a token reference is the fix, not a value
                    radius_values[f"css:{v}"] += 1
                    radius_sites[f"css:{v}"].append(rp)
                for m in RE_SHADOW_CSS.finditer(line):
                    v = m.group(1).strip()
                    if v.startswith("var(") or v == "none":
                        continue
                    shadow_values[f"css:{v[:60]}"] += 1
            for m in RE_SHADOW_TW.finditer(txt):
                shadow_values[m.group(0)] += 1
            for m in RE_GRADIENT_TW.finditer(txt):
                gradient_sites.append(site(p, txt.count("\n", 0, m.start()) + 1))
            for m in RE_GRADIENT_CSS.finditer(txt):
                gradient_sites.append(site(p, txt.count("\n", 0, m.start()) + 1))
            if RE_BACKDROP.search(txt):
                backdrop_sites.append(rp)
            if RE_KEYFRAMES.search(txt):
                motion_sites.append(rp)
            elif RE_MOTION_ESSENTIAL.search(txt):
                motion_essential_sites.append(rp)
            if RE_REDUCED_MOTION.search(txt):
                reduced_motion_sites.append(rp)

    # copy files (md/mdx/json content) — placeholders + em dashes only
    for p in copy_files:
        if p.name in ("package.json", "package-lock.json", "tsconfig.json", "bun.lock", "pnpm-lock.yaml") or p.suffix == ".json" and "lock" in p.name:
            continue
        if re.search(r"(^|/)(docs?|_drafts?|drafts?|specs?|plans?|adrs?|handoffs?|\.github|node_modules)(/|$)", rel(root, p), re.I):
            continue  # internal documentation / drafts are not shipped copy
        if p.suffix == ".json" and not any(k in rel(root, p).lower() for k in ("content", "copy", "locale", "messages", "i18n", "data")):
            continue
        txt = _read(p)
        if not txt:
            continue
        for key in ("lorem-ipsum", "john-jane-doe", "insert-here"):
            for m in PLACEHOLDER_PATTERNS[key].finditer(txt):
                placeholders[key].append(site(p, txt.count("\n", 0, m.start()) + 1))

    # --- legal: also accept html/md pages named terms/privacy ----------------
    for p in ui_files + copy_files:
        rp = rel(root, p)
        if not legal["terms_route"] and LEGAL_TERMS.search("/" + rp.rsplit(".", 1)[0]):
            legal["terms_route"] = "/" + rp.rsplit(".", 1)[0]
        if not legal["privacy_route"] and LEGAL_PRIVACY.search("/" + rp.rsplit(".", 1)[0]):
            legal["privacy_route"] = "/" + rp.rsplit(".", 1)[0]

    # --- roots (root-cause attribution) --------------------------------------
    roots: list[dict] = []
    for fam, sites in sorted(font_sites.items(), key=lambda kv: -len(kv[1])):
        is_default = fam in AI_DEFAULT_WEB_FONTS
        declared_in = Counter(s.split(":")[0] for s in sites)
        root_file = declared_in.most_common(1)[0][0]
        # prefer a token/config file as the root if any site is one
        for f in declared_in:
            if is_token_file(f) or "layout." in f or "_app." in f or "+layout" in f:
                root_file = f
                break
        roots.append({
            "kind": "font",
            "value": fam,
            "default": is_default,
            "system_stack": fam in SYSTEM_STACK,
            "self_hosted": fam in font_face_selfhosted,
            "sites": len(sites),
            "root_file": root_file,
            "example_sites": sites[:5],
            "fix": (
                "Decide the typeface once (PRODUCT/DESIGN.md), self-host it via @font-face or next/font/local, "
                f"and change the declaration in {root_file}; do not touch call sites."
                if is_default else "Deliberate face — keep; ensure it is self-hosted and declared once."
            ),
        })
    if icon_imports:
        total = sum(len(v) for v in icon_imports.values())
        for tag, files in sorted(icon_imports.items(), key=lambda kv: -len(kv[1])):
            roots.append({
                "kind": "icons", "value": tag, "default": tag == "lucide", "sites": len(files),
                "root_file": None, "example_sites": sorted(set(files))[:5],
                "fix": ("One icon system, one stroke weight; if lucide is a deliberate choice, say so in DESIGN.md — "
                        "it is the shadcn default and reads as such by itself." if tag == "lucide" else "Keep to one library; remove mixed sets."),
                "mixed_libraries": len(icon_imports) > 1, "share": round(len(files) / total, 2),
            })
    hardcoded = {k: v for k, v in hex_sites.items()}
    if hardcoded:
        roots.append({
            "kind": "color", "value": f"{len(hardcoded)} distinct hex literals outside token files",
            "default": len(hardcoded) >= 8, "sites": sum(len(v) for v in hardcoded.values()), "root_file": None,
            "example_sites": [s for v in list(hardcoded.values())[:5] for s in v[:1]],
            "top_values": [k for k, _ in sorted(hardcoded.items(), key=lambda kv: -len(kv[1]))[:12]],
            "fix": "Introduce/extend semantic tokens (CSS vars or tailwind theme) and replace literals at the token layer; a palette lives in one file.",
        })
    if radius_values:
        distinct = [k for k in radius_values if radius_values[k] > 0]
        arbitrary = [k for k in distinct if (k.startswith("css:") or "[" in k) and "var(" not in k and "[inherit]" not in k]   # rounded-[13px] / raw px; var()/inherit are refs
        roots.append({
            "kind": "radius", "value": f"{len(distinct)} distinct radius values", "default": len(distinct) > 4,
            "arbitrary": len(arbitrary),
            "sites": sum(radius_values.values()), "root_file": None,
            "top_values": [f"{k}×{v}" for k, v in radius_values.most_common(8)],
            "fix": "One radius vocabulary (e.g. control / card / dialog) declared as tokens; arbitrary values are drift, many scale steps are a decision to make.",
        })
    if shadow_values:
        arbitrary_s = [k for k in shadow_values if (k.startswith("css:") or "[" in k) and "var(" not in k and "[inherit]" not in k]
        roots.append({
            "kind": "shadow", "value": f"{len(shadow_values)} distinct shadow values", "default": len(shadow_values) > 4,
            "arbitrary": len(arbitrary_s),
            "sites": sum(shadow_values.values()), "root_file": None,
            "top_values": [f"{k}×{v}" for k, v in shadow_values.most_common(8)],
            "fix": "Declare elevation once (border OR shadow per level); shadows carry offset + soft blur; no glow halos.",
        })
    if gradient_sites:
        roots.append({"kind": "gradient", "value": f"{len(gradient_sites)} gradient sites", "default": True,
                      "sites": len(gradient_sites), "root_file": None, "example_sites": gradient_sites[:5],
                      "fix": "Gradients only where the committed visual world earns them; never as hero/background/text default."})
    if backdrop_sites:
        roots.append({"kind": "glass", "value": f"{len(backdrop_sites)} files use backdrop-filter", "default": len(backdrop_sites) > 2,
                      "sites": len(backdrop_sites), "root_file": None, "example_sites": backdrop_sites[:5],
                      "fix": "Glass marks a surface that actually floats (dialog, command palette); cards and chrome stay matte."})

    # --- substance summary -----------------------------------------------------
    async_n = len(async_files)
    substance = {
        "legal": {
            "terms_route": legal["terms_route"], "privacy_route": legal["privacy_route"],
            "terms_linked": len(legal["terms_link_sites"]) > 0, "privacy_linked": len(legal["privacy_link_sites"]) > 0,
            "terms_link_sites": legal["terms_link_sites"][:5], "privacy_link_sites": legal["privacy_link_sites"][:5],
        },
        "async_surfaces": {
            "count": async_n,
            "with_loading_state": sum(1 for v in async_files.values() if v["loading"]),
            "with_error_state": sum(1 for v in async_files.values() if v["error"]),
            "with_empty_state": sum(1 for v in async_files.values() if v["empty"]),
            "route_level_loading_files": loading_files_next,
            "route_level_error_files": error_files_next,
            "files": async_files,
        },
        "placeholders": {k: v for k, v in placeholders.items() if v},
        "testimonials": {"files": testimonials, "verify_real": bool(testimonials)},
        "pricing": {"files": pricing["files"], "tier_words": dict(pricing["tier_word_hits"].most_common(6)),
                    "three_tier_scaffold_suspected": len(set(pricing["tier_word_hits"])) >= 3 and bool(pricing["files"])},
        "product_evidence": {
            "video_sites": evidence["video_sites"][:10],
            "local_images": len(evidence["local_image_sites"]),
            "local_image_examples": evidence["local_image_sites"][:8],
            "evidence_images": len(evidence["evidence_image_sites"]),
            "evidence_image_examples": evidence["evidence_image_sites"][:8],
            "stock_image_sites": evidence["stock_image_sites"][:10],
            # svg / logos / icons / og images never count; a video or a non-decorative local raster does
            "has_real_evidence": bool(evidence["video_sites"]) or len(evidence["evidence_image_sites"]) > 0,
        },
        "motion": {"files_with_motion": len(motion_sites), "files_with_essential_motion_only": len(motion_essential_sites),
                    "files_with_reduced_motion": len(reduced_motion_sites),
                    "reduced_motion_respected": (not motion_sites) or bool(reduced_motion_sites)},
        "design_docs": design_docs,
    }

    manifest = {
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo": str(root),
        "app_root_rerooted_from": str(survey_root_arg) if survey_root_arg != root else None,
        "framework": fw,
        "counts": {"ui_files": len(ui_files), "style_files": len(style_files), "script_files": len(script_files), "copy_files": len(copy_files), "routes": len(routes),
                   "walk_mode": WALK_MODE["mode"],
                   "skipped": {"oversized": len(SKIPPED["oversized"]), "unreadable": len(SKIPPED["unreadable"]),
                               "examples": [rel(root, Path(x)) for x in (SKIPPED["oversized"] + SKIPPED["unreadable"])[:6]]}},
        "routes": routes,
        "profile_hint": ("persuade" if (landing_hints or pricing["files"] or testimonials) else ("operate" if async_n or len(routes) > 3 else "unknown")),
        "landing_hint_files": landing_hints[:8],
        "fonts": {
            "families": {k: len(v) for k, v in font_sites.items()},
            "fallback_only": dict(font_fallbacks.most_common(12)),
            "default_families_in_use": sorted(f for f in font_sites if f in AI_DEFAULT_WEB_FONTS),
            "system_stack_primary": sorted(f for f in font_sites if f in SYSTEM_STACK),
            "self_hosted": sorted(font_face_selfhosted),
            "next_font_imports": next_font_imports,
            "google_font_links": google_font_links,
        },
        "icons": {k: len(v) for k, v in icon_imports.items()},
        "component_libs": sorted(component_libs),
        "copy_tells": {k: {"count": len(v), "sites": v[:200]} for k, v in copy_tells.items()},
        "substance": substance,
        "roots": roots,
        "detector": {"status": "not-run", "findings": [], "by_rule": {}, "primary_count": 0, "advisory_count": 0},
    }

    if detect:
        manifest["detector"] = run_detector(root, detector_cmd, timeout=detector_timeout)
    return manifest


# ---------------------------------------------------------------------------
# impeccable detector (composed, optional)
# ---------------------------------------------------------------------------
def find_detector() -> list[str] | None:
    """Locate the impeccable detector: env override → installed skill dirs → npx."""
    env = os.environ.get("UNSLOP_DETECTOR")
    if env:
        return env.split()
    home = Path.home()
    for cand in (
        home / ".claude/skills/impeccable/scripts/detect.mjs",
        home / ".agents/skills/impeccable/scripts/detect.mjs",
        home / ".codex/skills/impeccable/scripts/detect.mjs",
        Path(".agents/skills/impeccable/scripts/detect.mjs"),
        Path(".claude/skills/impeccable/scripts/detect.mjs"),
    ):
        if cand.exists() and shutil.which("node"):
            return ["node", str(cand)]
    if shutil.which("npx"):
        return ["npx", "-y", "impeccable", "detect"]
    return None


def run_detector(root: Path, detector_cmd: str | None = None, timeout: int = 600) -> dict:
    cmd = detector_cmd.split() if detector_cmd else find_detector()
    if not cmd:
        return {"status": "unavailable", "findings": [], "by_rule": {}, "primary_count": 0, "advisory_count": 0,
                "note": "impeccable detector not found (install the impeccable skill or set UNSLOP_DETECTOR)"}
    try:
        proc = subprocess.run(cmd + ["--json", str(root)], capture_output=True, text=True, timeout=timeout, cwd=str(root))
    except subprocess.TimeoutExpired:
        return {"status": "error", "findings": [], "by_rule": {}, "primary_count": 0, "advisory_count": 0,
                "note": f"detector timed out after {timeout}s (raise --detector-timeout)"}
    except OSError as e:
        return {"status": "error", "findings": [], "by_rule": {}, "primary_count": 0, "advisory_count": 0, "note": str(e)}
    out = proc.stdout.strip()
    # impeccable exits 0 (clean) or 2 (primary findings present); anything else is a crash, and an
    # empty stdout is never "no findings" — a JSON array is the only acceptable clean signal.
    start = out.find("[")
    if start < 0:
        return {"status": "error", "findings": [], "by_rule": {}, "primary_count": 0, "advisory_count": 0,
                "note": f"detector produced no JSON array (exit {proc.returncode})", "stderr": proc.stderr[-800:]}
    try:
        findings = json.loads(out[start:])
    except json.JSONDecodeError:
        return {"status": "error", "findings": [], "by_rule": {}, "primary_count": 0, "advisory_count": 0,
                "note": f"detector output was not JSON (exit {proc.returncode})", "stderr": proc.stderr[-800:]}
    if not isinstance(findings, list) or proc.returncode not in (0, 2):
        return {"status": "error", "findings": [], "by_rule": {}, "primary_count": 0, "advisory_count": 0,
                "note": f"detector exit {proc.returncode} with unexpected payload", "stderr": proc.stderr[-800:]}
    d = summarize_detector(findings, cmd)
    d["exit_code"] = proc.returncode
    return d


def summarize_detector(findings: list, cmd: list[str] | None = None) -> dict:
    by_rule: Counter = Counter()
    primary = 0
    advisory = 0
    slim = []
    for f in findings:
        rule = f.get("antipattern") or f.get("rule") or f.get("id") or "unknown"
        sev = (f.get("severity") or "warning").lower()
        adv = bool(f.get("advisory")) or sev in ("advisory", "info")
        by_rule[rule] += 1
        if adv:
            advisory += 1
        else:
            primary += 1
        slim.append({"rule": rule, "severity": sev, "advisory": adv, "file": f.get("file"), "line": f.get("line"),
                     "snippet": (f.get("snippet") or "")[:120], "importedBy": f.get("importedBy")})
    return {"status": "ok", "command": " ".join(cmd) if cmd else None, "findings": slim,
            "by_rule": dict(by_rule.most_common()), "primary_count": primary, "advisory_count": advisory}


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------
def to_markdown(m: dict) -> str:
    fw = m["framework"]
    s = m["substance"]
    lines = [
        f"# unslop survey — {m['repo']}",
        "",
        f"framework: **{fw['name']}**{' / ' + fw['router'] if fw.get('router') else ''} · tailwind: {fw['tailwind']} · "
        f"routes: {m['counts']['routes']} · ui files: {m['counts']['ui_files']} · styles: {m['counts']['style_files']}",
        "",
        "## Roots (fix once, here)",
        "",
        "| kind | value | default? | sites | root file |",
        "|---|---|---|---|---|",
    ]
    for r in m["roots"]:
        lines.append(f"| {r['kind']} | {r['value']} | {'**yes**' if r.get('default') else 'no'} | {r.get('sites', '')} | {r.get('root_file') or '—'} |")
    lines += ["", "## Copy tells", ""]
    for k, v in m["copy_tells"].items():
        lines.append(f"- {k}: {v['count']}")
    lines += ["", "## Substance", ""]
    lg = s["legal"]
    lines.append(f"- legal: terms={lg['terms_route'] or 'MISSING'} privacy={lg['privacy_route'] or 'MISSING'} (linked: {lg['terms_linked']}/{lg['privacy_linked']})")
    a = s["async_surfaces"]
    lines.append(f"- async surfaces: {a['count']} · loading {a['with_loading_state']} · error {a['with_error_state']} · empty {a['with_empty_state']} · route-level loading files {len(a['route_level_loading_files'])}")
    lines.append(f"- placeholders: " + (", ".join(f"{k}×{len(v)}" for k, v in s['placeholders'].items()) or "none"))
    lines.append(f"- testimonials: {len(s['testimonials']['files'])} file(s) — verify real: {s['testimonials']['verify_real']}")
    lines.append(f"- pricing: {len(s['pricing']['files'])} file(s) · three-tier scaffold suspected: {s['pricing']['three_tier_scaffold_suspected']}")
    pe = s["product_evidence"]
    lines.append(f"- product evidence: video {len(pe['video_sites'])} · local images {pe['local_images']} · stock images {len(pe['stock_image_sites'])} → real evidence: {pe['has_real_evidence']}")
    mo = s["motion"]
    lines.append(f"- motion: {mo['files_with_motion']} files · reduced-motion respected: {mo['reduced_motion_respected']}")
    lines.append(f"- design docs: DESIGN.md={s['design_docs']['DESIGN.md']} PRODUCT.md={s['design_docs']['PRODUCT.md']}")
    d = m["detector"]
    lines += ["", f"## Detector (impeccable) — {d['status']}", ""]
    if d.get("by_rule"):
        for k, v in list(d["by_rule"].items())[:20]:
            lines.append(f"- {k}: {v}")
        lines.append(f"- primary: {d['primary_count']} · advisory: {d['advisory_count']}")
    elif d.get("note"):
        lines.append(f"- {d['note']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("repo", help="path to the frontend repo (or a subdir)")
    ap.add_argument("--detect", action="store_true", help="also run the impeccable detector (composed; optional)")
    ap.add_argument("--detector-cmd", default=None, help="override detector command, e.g. 'node /path/detect.mjs'")
    ap.add_argument("--detector-timeout", type=int, default=600, help="seconds before the detector subprocess is abandoned (default 600)")
    ap.add_argument("--json", dest="json_out", default=None, help="write manifest JSON here (default: stdout)")
    ap.add_argument("--md", dest="md_out", default=None, help="also write a markdown summary here")
    ap.add_argument("--quiet", action="store_true", help="suppress the markdown summary on stderr")
    args = ap.parse_args(argv)

    root = Path(args.repo)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    m = survey(root, detect=args.detect, detector_cmd=args.detector_cmd, detector_timeout=args.detector_timeout)
    payload = json.dumps(m, indent=2, ensure_ascii=False)
    md = to_markdown(m)
    try:
        if args.json_out:
            Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.json_out).write_text(payload + "\n", encoding="utf-8")
        else:
            print(payload)
        if args.md_out:
            Path(args.md_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.md_out).write_text(md, encoding="utf-8")
    except OSError as e:
        print(f"error: cannot write output: {e}", file=sys.stderr)
        return 2
    if not args.quiet:
        print(md, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
