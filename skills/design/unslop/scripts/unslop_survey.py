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

SKIP_DIRS = {
    ".git", "node_modules", ".next", ".nuxt", ".svelte-kit", ".astro", ".output",
    "dist", "build", "out", "coverage", ".turbo", ".vercel", ".cache", "vendor",
    "target", "venv", ".venv", "__pycache__", ".pytest_cache", "storybook-static",
    ".impeccable", ".unslop",
}
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
RE_GOOGLE_FONTS = re.compile(r"fonts\.googleapis\.com/css2?\?family=([^&\"'\s>]+)")
RE_FONT_FACE = re.compile(r"@font-face\s*\{[^}]*font-family\s*:\s*['\"]?([^;'\"}]+)", re.I | re.S)
RE_TW_FONT = re.compile(r"fontFamily\s*:\s*\{([^}]*)\}", re.S)
RE_CSS_VAR_FONT = re.compile(r"--font-[a-z0-9-]+\s*:\s*([^;]+);", re.I)

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

RE_EM_DASH = re.compile("—")
RE_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF✅✨⚡\U0001F525\U0001F680\U0001F4A1\U0001F389]"
)
RE_CHECKMARK = re.compile("[✓✔✅☑]")
RE_NOT_X_BUT_Y = re.compile(
    r"\b(?:it'?s|this is|we'?re|that'?s)\s+not\s+(?:just\s+|about\s+|a\s+|an\s+|another\s+)?[^.;:\n]{2,60}?[,;—–-]+\s*(?:it'?s|this is|we'?re|that'?s|but)\b",
    re.I,
)
BUZZWORDS = [
    "supercharge", "unleash", "revolutioni", "seamless", "effortless", "next-gen", "10x", "game-chang",
    "cutting-edge", "state-of-the-art", "empower", "unlock", "elevate", "streamline", "harness the power",
]
RE_BUZZ = re.compile("|".join(re.escape(b) for b in BUZZWORDS), re.I)

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
RE_ERROR_STATE = re.compile(r"ErrorBoundary|isError|error\s*\?\s*|error\.tsx|<Alert|catch\s*\(|status\s*===?\s*['\"]error['\"]|onError")
RE_EMPTY_STATE = re.compile(r"length\s*===?\s*0|\.length\s*\?|No\s+(results|items|data|projects|messages|orders)|Nothing\s+(here|yet|to show)|empty[-_ ]?state|EmptyState", re.I)

PLACEHOLDER_PATTERNS = {
    "lorem-ipsum": re.compile(r"lorem ipsum|dolor sit amet", re.I),
    "john-jane-doe": re.compile(r"\b(john|jane)\s+doe\b", re.I),
    "acme": re.compile(r"\bAcme(\s+(Inc|Corp|Co)\.?)?\b"),
    "your-company": re.compile(r"\b(your|the)\s+company\s+name\b|\[?your\s+(company|name|product|brand)\]?", re.I),
    "insert-here": re.compile(r"\[(?:insert|add|your|placeholder)\s+[a-z][^\]]{2,}\]|\bcoming soon\b|\bTBD\b", re.I),
    "todo-in-copy": re.compile(r">\s*(TODO|FIXME|XXX)\b|['\"](TODO|FIXME)[:\s]"),
    "stock-image-host": re.compile(r"(images\.unsplash\.com|source\.unsplash\.com|picsum\.photos|placehold\.co|placeholder\.com|via\.placeholder|placekitten|dummyimage\.com|loremflickr|pravatar\.cc|randomuser\.me|ui-avatars\.com|i\.pravatar)", re.I),
    "example-domain": re.compile(r"\b[a-z0-9.-]*example\.(com|org|net)\b", re.I),
    "fake-metrics": re.compile(r"\b(99\.9+%|10,?000\+|1M\+|500\+|10x)\s*(uptime|users|customers|teams|companies|developers|faster)?\b", re.I),
}
RE_LANDING = re.compile(r"<Hero|className=\"hero|id=\"hero|Get started( free)?|Start (for )?free|Sign up free|Book a demo|Request (a )?demo|Join the waitlist|Start your free trial", re.I)
RE_TESTIMONIAL = re.compile(r"testimonial|what (our )?(customers|users|clients) (say|are saying)|<Quote|Reviews?Section|CustomerQuote", re.I)
RE_PRICING = re.compile(r"pricing|PricingTier|PricingCard|PricingTable|/pricing", re.I)
RE_TIER_WORDS = re.compile(r"\b(Free|Starter|Basic|Hobby|Pro|Team|Business|Enterprise|Premium|Plus|Growth|Scale)\b")
RE_VIDEO = re.compile(r"<video|\.mp4\b|\.webm\b|youtube\.com/embed|player\.vimeo|loom\.com/embed|<iframe", re.I)
RE_LOCAL_IMG = re.compile(r"""(?:src|href|url)\s*[=(:]\s*['"(]?(/?(?:public/|assets/|images?/|img/|screenshots?/|static/|media/)[^'"\s)]+\.(?:png|jpe?g|webp|avif|gif|svg))""", re.I)
RE_STOCK_IMG = PLACEHOLDER_PATTERNS["stock-image-host"]

RE_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}\b")
RE_RADIUS_TW = re.compile(r"\brounded(?:-(?:none|sm|md|lg|xl|2xl|3xl|full|\[[^\]]+\]))?\b")
RE_RADIUS_CSS = re.compile(r"border-radius\s*:\s*([^;}{]+)", re.I)
RE_SHADOW_TW = re.compile(r"\bshadow(?:-(?:sm|md|lg|xl|2xl|inner|none|\[[^\]]+\]))?\b")
RE_SHADOW_CSS = re.compile(r"box-shadow\s*:\s*([^;}{]+)", re.I)
RE_GRADIENT_TW = re.compile(r"\bbg-gradient-to-[trbl]{1,2}\b|\bfrom-(?:purple|violet|fuchsia|pink|indigo)-\d{3}\b")
RE_GRADIENT_CSS = re.compile(r"(?:linear|radial|conic)-gradient\(", re.I)
RE_BACKDROP = re.compile(r"backdrop-filter|backdrop-blur", re.I)
RE_KEYFRAMES = re.compile(r"@keyframes|animate-\w+|framer-motion|motion\.\w+|transition-all", re.I)
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
TOKEN_FILE_HINTS = ("globals.css", "global.css", "app.css", "index.css", "tokens", "theme", "tailwind.config", "design-system", "styles.css", "variables.css", "main.css")


def _read(p: Path) -> str:
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            return ""
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")] if dirpath != str(root) else [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            yield Path(dirpath) / fn


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
            m = re.match(r"^(?:src/)?app/(.*?)(?:^|/)?(page|layout|loading|error|not-found|template|route)\.(tsx|jsx|js|ts|mdx)$", r)
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
def survey(root: Path, detect: bool = False, detector_cmd: str | None = None) -> dict:
    root = root.resolve()
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
            if dep == lib or dep.startswith(lib + "/") or dep.startswith(lib):
                component_libs.add(tag)
    copy_tells = {"em_dash": [], "emoji": [], "not_x_but_y": [], "checkmark_bullets": [], "buzzwords": []}
    legal = {"terms_route": None, "privacy_route": None, "terms_link_sites": [], "privacy_link_sites": []}
    async_files: dict[str, dict] = {}
    placeholders: dict[str, list[str]] = defaultdict(list)
    testimonials: list[str] = []
    pricing: dict = {"files": [], "tier_word_hits": Counter()}
    evidence = {"video_sites": [], "local_image_sites": [], "stock_image_sites": []}
    hex_sites: dict[str, list[str]] = defaultdict(list)
    radius_values: Counter = Counter()
    radius_sites: dict[str, list[str]] = defaultdict(list)
    shadow_values: Counter = Counter()
    gradient_sites: list[str] = []
    backdrop_sites: list[str] = []
    motion_sites: list[str] = []
    reduced_motion_sites: list[str] = []
    loading_files_next: list[str] = []
    error_files_next: list[str] = []
    design_docs = {"DESIGN.md": (root / "DESIGN.md").exists(), "PRODUCT.md": (root / "PRODUCT.md").exists()}

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
        is_config = "tailwind.config" in p.name or p.name in ("postcss.config.js", "postcss.config.mjs")
        lines = txt.splitlines()

        # fonts
        for m in RE_FONT_FAMILY.finditer(txt):
            ln = txt.count("\n", 0, m.start()) + 1
            fams = [f.strip().strip("'\"").lower() for f in m.group(1).split(",")]
            fams = [f for f in fams if f and not f.startswith("var(") and f not in ("inherit", "initial", "unset")]
            if not fams:
                continue
            font_sites[fams[0]].append(site(p, ln))          # primary face
            for fam in fams[1:]:
                font_fallbacks[fam] += 1                       # fallback stack only
        for m in RE_FONT_FACE.finditer(txt):
            font_face_selfhosted.add(m.group(1).strip().strip("'\"").lower())
        for m in RE_NEXT_FONT_NAMES.finditer(txt):
            for name in m.group(1).split(","):
                n = name.strip().split(" as ")[0].strip()
                if n:
                    next_font_imports.append(f"{n}@{rp}")
                    fam = re.sub(r"_", " ", n).lower()
                    font_sites[fam].append(site(p, txt.count("\n", 0, m.start()) + 1))
        for m in RE_GOOGLE_FONTS.finditer(txt):
            google_font_links.append(f"{m.group(1)}@{rp}")
            for fam in m.group(1).split("&family="):
                fam = fam.split(":")[0].replace("+", " ").lower()
                if fam:
                    font_sites[fam].append(site(p, txt.count("\n", 0, m.start()) + 1))
        if is_config:
            for m in RE_TW_FONT.finditer(txt):
                for fm in re.finditer(r"['\"]([A-Za-z][A-Za-z0-9 ]+)['\"]", m.group(1)):
                    font_sites[fm.group(1).lower()].append(site(p, txt.count("\n", 0, m.start()) + 1))
        if is_style:
            for m in RE_CSS_VAR_FONT.finditer(txt):
                for fam in m.group(1).split(","):
                    fam = fam.strip().strip("'\"").lower()
                    if fam and not fam.startswith("var("):
                        font_sites[fam].append(site(p, txt.count("\n", 0, m.start()) + 1))

        # icons + component libs
        for m in RE_IMPORT_FROM.finditer(txt):
            mod = m.group(1)
            for lib, tag in ICON_LIBS.items():
                if mod == lib or mod.startswith(lib + "/"):
                    icon_imports[tag].append(rp)
            for lib, tag in COMPONENT_LIBS.items():
                if mod == lib or mod.startswith(lib + "/") or mod.startswith(lib):
                    component_libs.add(tag)
        if "/components/ui/" in ("/" + rp) or rp.startswith("components/ui/"):
            component_libs.add("shadcn(components/ui)")

        # copy tells (UI files only, skip pure scripts/styles)
        if is_ui:
            for i, line in enumerate(lines, 1):
                if RE_EM_DASH.search(line) and not line.lstrip().startswith(("//", "/*", "*", "{/*", "<!--")):
                    copy_tells["em_dash"].append(site(p, i))
                if RE_EMOJI.search(line):
                    copy_tells["emoji"].append(site(p, i))
                if RE_CHECKMARK.search(line):
                    copy_tells["checkmark_bullets"].append(site(p, i))
                if RE_BUZZ.search(line):
                    copy_tells["buzzwords"].append(site(p, i))
            for m in RE_NOT_X_BUT_Y.finditer(txt):
                copy_tells["not_x_but_y"].append(site(p, txt.count("\n", 0, m.start()) + 1))

            # legal links
            for m in RE_HREF_TERMS.finditer(txt):
                legal["terms_link_sites"].append(site(p, txt.count("\n", 0, m.start()) + 1))
            for m in RE_HREF_PRIVACY.finditer(txt):
                legal["privacy_link_sites"].append(site(p, txt.count("\n", 0, m.start()) + 1))

            # substance: landing / testimonials / pricing / evidence
            if RE_LANDING.search(txt):
                landing_hints.append(rp)
            if RE_TESTIMONIAL.search(txt):
                testimonials.append(rp)
            if RE_PRICING.search(txt) or "pricing" in rp.lower():
                pricing["files"].append(rp)
                for m in RE_TIER_WORDS.finditer(txt):
                    pricing["tier_word_hits"][m.group(1)] += 1
            if RE_VIDEO.search(txt):
                evidence["video_sites"].append(rp)
            for m in RE_LOCAL_IMG.finditer(txt):
                evidence["local_image_sites"].append(f"{m.group(1)}@{rp}")
            for m in RE_STOCK_IMG.finditer(txt):
                evidence["stock_image_sites"].append(site(p, txt.count("\n", 0, m.start()) + 1))

        # async surfaces + states (UI + scripts)
        if is_ui or (p.suffix.lower() in SCRIPT_EXT and not is_config):
            if RE_ASYNC.search(txt):
                async_files[rp] = {
                    "loading": bool(RE_LOADING_STATE.search(txt)),
                    "error": bool(RE_ERROR_STATE.search(txt)),
                    "empty": bool(RE_EMPTY_STATE.search(txt)),
                }

        # placeholders (UI + copy)
        if is_ui:
            for key, rx in PLACEHOLDER_PATTERNS.items():
                for m in rx.finditer(txt):
                    placeholders[key].append(site(p, txt.count("\n", 0, m.start()) + 1))

        # visual vocabulary
        if is_ui or is_style:
            is_token_file = any(h in rp.lower() for h in TOKEN_FILE_HINTS)
            for m in RE_HEX.finditer(txt):
                if not is_token_file:
                    hex_sites[m.group(0).lower()].append(site(p, txt.count("\n", 0, m.start()) + 1))
            for m in RE_RADIUS_TW.finditer(txt):
                radius_values[m.group(0)] += 1
                radius_sites[m.group(0)].append(rp)
            for m in RE_RADIUS_CSS.finditer(txt):
                v = m.group(1).strip()
                radius_values[f"css:{v}"] += 1
                radius_sites[f"css:{v}"].append(rp)
            for m in RE_SHADOW_TW.finditer(txt):
                shadow_values[m.group(0)] += 1
            for m in RE_SHADOW_CSS.finditer(txt):
                shadow_values[f"css:{m.group(1).strip()[:60]}"] += 1
            for m in RE_GRADIENT_TW.finditer(txt):
                gradient_sites.append(site(p, txt.count("\n", 0, m.start()) + 1))
            for m in RE_GRADIENT_CSS.finditer(txt):
                gradient_sites.append(site(p, txt.count("\n", 0, m.start()) + 1))
            if RE_BACKDROP.search(txt):
                backdrop_sites.append(rp)
            if RE_KEYFRAMES.search(txt):
                motion_sites.append(rp)
            if RE_REDUCED_MOTION.search(txt):
                reduced_motion_sites.append(rp)

    # copy files (md/mdx/json content) — placeholders + em dashes only
    for p in copy_files:
        if p.name in ("package.json", "package-lock.json", "tsconfig.json", "bun.lock", "pnpm-lock.yaml") or p.suffix == ".json" and "lock" in p.name:
            continue
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
            if any(h in f.lower() for h in TOKEN_FILE_HINTS) or "layout." in f or "_app." in f or "+layout" in f:
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
        roots.append({
            "kind": "radius", "value": f"{len(distinct)} distinct radius values", "default": len(distinct) > 4,
            "sites": sum(radius_values.values()), "root_file": None,
            "top_values": [f"{k}×{v}" for k, v in radius_values.most_common(8)],
            "fix": "One radius vocabulary (e.g. control / card / dialog) declared as tokens; more than ~4 distinct radii is drift.",
        })
    if shadow_values:
        roots.append({
            "kind": "shadow", "value": f"{len(shadow_values)} distinct shadow values", "default": len(shadow_values) > 4,
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
                    "three_tier_scaffold_suspected": len(set(pricing["tier_word_hits"])) == 3 and bool(pricing["files"])},
        "product_evidence": {
            "video_sites": evidence["video_sites"][:10],
            "local_images": len(evidence["local_image_sites"]),
            "local_image_examples": evidence["local_image_sites"][:8],
            "stock_image_sites": evidence["stock_image_sites"][:10],
            "has_real_evidence": bool(evidence["video_sites"]) or len(evidence["local_image_sites"]) > 0,
        },
        "motion": {"files_with_motion": len(motion_sites), "files_with_reduced_motion": len(reduced_motion_sites),
                    "reduced_motion_respected": (not motion_sites) or bool(reduced_motion_sites)},
        "design_docs": design_docs,
    }

    manifest = {
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo": str(root),
        "framework": fw,
        "counts": {"ui_files": len(ui_files), "style_files": len(style_files), "script_files": len(script_files), "copy_files": len(copy_files), "routes": len(routes)},
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
        "copy_tells": {k: {"count": len(v), "sites": v[:12]} for k, v in copy_tells.items()},
        "substance": substance,
        "roots": roots,
        "detector": {"status": "not-run", "findings": [], "by_rule": {}, "primary_count": 0, "advisory_count": 0},
    }

    if detect:
        manifest["detector"] = run_detector(root, detector_cmd)
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
        Path(".agents/skills/impeccable/scripts/detect.mjs"),
        Path(".claude/skills/impeccable/scripts/detect.mjs"),
    ):
        if cand.exists() and shutil.which("node"):
            return ["node", str(cand)]
    if shutil.which("npx"):
        return ["npx", "-y", "impeccable", "detect"]
    return None


def run_detector(root: Path, detector_cmd: str | None = None) -> dict:
    cmd = detector_cmd.split() if detector_cmd else find_detector()
    if not cmd:
        return {"status": "unavailable", "findings": [], "by_rule": {}, "primary_count": 0, "advisory_count": 0,
                "note": "impeccable detector not found (install the impeccable skill or set UNSLOP_DETECTOR)"}
    try:
        proc = subprocess.run(cmd + ["--json", str(root)], capture_output=True, text=True, timeout=600, cwd=str(root))
    except (subprocess.TimeoutExpired, OSError) as e:  # pragma: no cover - environment
        return {"status": "error", "findings": [], "by_rule": {}, "primary_count": 0, "advisory_count": 0, "note": str(e)}
    out = proc.stdout.strip()
    findings: list = []
    if out:
        try:
            start = out.find("[")
            findings = json.loads(out[start:]) if start >= 0 else []
        except json.JSONDecodeError:
            return {"status": "error", "findings": [], "by_rule": {}, "primary_count": 0, "advisory_count": 0,
                    "note": "detector output was not JSON", "stderr": proc.stderr[-800:]}
    return summarize_detector(findings, cmd)


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
    ap.add_argument("--json", dest="json_out", default=None, help="write manifest JSON here (default: stdout)")
    ap.add_argument("--md", dest="md_out", default=None, help="also write a markdown summary here")
    ap.add_argument("--quiet", action="store_true", help="suppress the markdown summary on stderr")
    args = ap.parse_args(argv)

    root = Path(args.repo)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    m = survey(root, detect=args.detect, detector_cmd=args.detector_cmd)
    payload = json.dumps(m, indent=2, ensure_ascii=False)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    md = to_markdown(m)
    if args.md_out:
        Path(args.md_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md_out).write_text(md, encoding="utf-8")
    if not args.quiet:
        print(md, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
