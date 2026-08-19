"""P20 regressions — every case here is a false positive / fail-open found by a reviewer on a REAL repo.

Strata A (codex): next/font/local unparsed · detector fail-open · decorative images as evidence · per-route
evidence matrix · JSON error handling. Strata B (fresh context): generated report dirs surveyed · server-side
files as async surfaces · --font-size-* as families · buzzwords without boundaries · <iframe> as video ·
copy modules invisible · token declarations as drift · hex in comments/hrefs · em dash in trailing comment ·
nested app root · theme-toggle as a token file · junk bytes as screenshots · valueless / unknown / non-waivable
waivers · essential motion utilities failing reduced-motion.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

import unslop_gate as ug
import unslop_survey as us
from helpers import png_bytes


def _repo(tmp_path, name, files: dict, deps=None):
    root = tmp_path / name
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (root / "package.json").write_text(json.dumps({"dependencies": deps or {"next": "15", "react": "19"}}))
    return root


def _gate(repo, **kw):
    manifest = kw.pop("manifest", None) or us.survey(repo)
    g = ug.Gate(manifest, repo, kw.pop("waivers", {"waivers": []}), kw.pop("profile", "auto"), kw.pop("strict", False), kw.pop("evidence_dir", None), kw.pop("no_render", False))
    return {r.check: r for r in g.run()}


# ---------------------------------------------------------------- survey: real-repo false positives
def test_generated_report_dirs_are_not_surveyed(tmp_path):
    root = _repo(tmp_path, "gen", {
        "src/app/page.tsx": "<main>hi</main>",
        "playwright-report/index.html": "<html><body style='color:#111111;background:#222222;border:#333333;font-family: Inter'>— ✨ Supercharge <script>fetch('/x')</script></body></html>",
        "test-results/a/trace.html": "<div style='color:#abcdef'>—</div>",
    })
    m = us.survey(root)
    assert "color" not in {r["kind"] for r in m["roots"]}
    assert m["copy_tells"]["em_dash"]["count"] == 0 and m["copy_tells"]["emoji"]["count"] == 0
    assert "inter" not in m["fonts"]["families"] and m["substance"]["async_surfaces"]["count"] == 0


def test_gitignored_files_are_skipped_when_in_a_git_repo(tmp_path):
    root = _repo(tmp_path, "gitrepo", {
        "src/app/page.tsx": "<main>hi</main>",
        "generated/report.html": "<div style='color:#111111;background:#222222;border:#333333;outline:#444444;fill:#555555;stroke:#666666;color:#777777;color:#888888;color:#999999;color:#aaaaaa;color:#bbbbbb;color:#cccccc;color:#dddddd'>—</div>",
        ".gitignore": "generated/\n",
    })
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    m = us.survey(root)
    assert "color" not in {r["kind"] for r in m["roots"]} and m["copy_tells"]["em_dash"]["count"] == 0


def test_server_side_files_are_not_async_surfaces(tmp_path):
    root = _repo(tmp_path, "srv", {
        "src/app/api/chat/route.ts": "export async function POST() { const r = await fetch('/x'); return r; }",
        "src/lib/db/queries.ts": "export const q = () => fetch('/api/q');",
        "src/hooks/use-chat.ts": "export function useChat() { return useQuery({ queryKey: ['c'], queryFn: () => fetch('/c') }); }",
        "src/app/inbox/page.tsx": "export default async function Inbox() { const d = await fetch('/api/inbox'); return <ul />; }",
    })
    a = us.survey(root)["substance"]["async_surfaces"]
    assert set(a["files"]) == {"src/app/inbox/page.tsx"}


def test_font_size_and_weight_vars_are_not_families(tmp_path):
    root = _repo(tmp_path, "vars", {
        "src/styles/vars.css": ":root { --font-size-lg: 1.25rem; --font-weight-bold: 700; --font-sans: 'Space Grotesk', system-ui, sans-serif; --font-mono: var(--font-geist-mono); }",
    })
    fams = us.survey(root)["fonts"]["families"]
    assert set(fams) == {"space grotesk"}


def test_mui_object_style_font_family_is_detected(tmp_path):
    root = _repo(tmp_path, "mui", {"src/theme.tsx": 'export const theme = createTheme({ typography: { fontFamily: "Inter, sans-serif" } });'})
    m = us.survey(root)
    assert "inter" in m["fonts"]["families"] and "inter" in m["fonts"]["default_families_in_use"]


def test_next_font_local_family_comes_from_the_file_not_the_const(tmp_path):
    root = _repo(tmp_path, "lf2", {"src/app/layout.tsx": '''
import localFont from "next/font/local";
const brandFace = localFont({
  src: [
    { path: "../../public/fonts/Signifier-Regular.woff2", weight: "400", style: "normal" },
    { path: "../../public/fonts/Signifier-Bold.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-brand",
  display: "swap",
});
const mono = localFont({ src: "./GeistMono-Variable.woff2" });
'''})
    m = us.survey(root)
    fams = m["fonts"]["families"]
    assert "signifier" in fams and "brandface" not in fams
    assert "geist mono" in fams
    assert {"signifier", "geist mono"} <= set(m["fonts"]["self_hosted"])
    assert any(x.startswith("local:brandFace=signifier@") for x in m["fonts"]["next_font_imports"])


def test_buzzwords_need_word_boundaries_and_copy_context(tmp_path):
    root = _repo(tmp_path, "buzz", {
        "src/components/Timeline.tsx": 'export const T = () => <div style={{ backgroundColor: "var(--color-surface-elevated)" }} className="unlockScroll"><iframe seamless src="/e" /></div>;',
        "src/components/Hero.tsx": "<h1>Supercharge your team and unlock seamless growth</h1>",
    })
    ct = us.survey(root)["copy_tells"]["buzzwords"]
    assert ct["count"] == 1 and "Hero.tsx" in ct["sites"][0]


def test_iframe_and_accept_attr_are_not_video_evidence(tmp_path):
    root = _repo(tmp_path, "vid", {"src/app/page.tsx": '<section className="hero"><iframe seamless src="/embed" /><input accept=".mp4,.webm" /></section>'})
    pe = us.survey(root)["substance"]["product_evidence"]
    assert pe["video_sites"] == [] and pe["has_real_evidence"] is False
    root2 = _repo(tmp_path, "vid2", {"src/app/page.tsx": '<section className="hero"><video src="/media/demo.mp4" /></section>'})
    assert us.survey(root2)["substance"]["product_evidence"]["has_real_evidence"] is True


def test_copy_modules_are_scanned(tmp_path):
    root = _repo(tmp_path, "copymod", {
        "src/app/page.tsx": "<main>{siteCopy.hero}</main>",
        "src/lib/content.ts": 'export const siteCopy = { hero: "It\'s not a tool, it\'s a movement — ✨ Supercharge", stats: "10,000+ users", quote: "Amazing — John Doe, Acme Inc. Lorem ipsum" }; export const testimonials = [];',
    })
    m = us.survey(root)
    ph = m["substance"]["placeholders"]
    assert {"lorem-ipsum", "john-jane-doe", "acme", "fake-metrics"} <= set(ph)
    assert m["copy_tells"]["em_dash"]["count"] >= 1 and m["copy_tells"]["not_x_but_y"]["count"] == 1
    assert m["substance"]["testimonials"]["files"] == ["src/lib/content.ts"]


def test_token_declarations_and_refs_are_not_vocabulary_drift(tmp_path):
    root = _repo(tmp_path, "tok", {
        "src/styles/tokens.css": ":root { --shadow-xs: 0 1px 2px #0001; --shadow-sm: 0 1px 3px #0002; --shadow-md: 0 4px 8px #0002; --shadow-lg: 0 8px 24px #0003; --shadow-xl: 0 16px 40px #0003; --shadow-inner: inset 0 1px 2px #0001; --radius-sm: 4px; --radius-md: 8px; --radius-lg: 12px; }",
        "src/components/Card.tsx": "<div style={{ borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-sm)' }} className='rounded-md rounded-t-md rounded-ss-md shadow-sm drop-shadow-lg' />",
        "src/components/Panel.css": ".p { border-radius: var(--radius-lg); box-shadow: var(--shadow-md); }",
    })
    m = us.survey(root)
    kinds = {r["kind"]: r for r in m["roots"]}
    assert "shadow" not in kinds or int(kinds["shadow"]["value"].split()[0]) <= 1
    assert int(kinds["radius"]["value"].split()[0]) == 1  # rounded-md, rounded-t-md, rounded-ss-md → one value


def test_hex_in_comments_hrefs_and_urls_is_not_a_color(tmp_path):
    root = _repo(tmp_path, "hex", {"src/components/Nav.tsx": (
        '// see issue #123 and #abcdef in the tracker\n'
        'export const Nav = () => <a href="#add-item" data-x="/docs#123456">go</a>;\n'
        'export const Dot = () => <span style={{ color: "#c0ffee" }} />;\n'
    )})
    kinds = {r["kind"]: r for r in us.survey(root)["roots"]}
    assert kinds["color"]["top_values"] == ["#c0ffee"]


def test_em_dash_in_trailing_comment_is_ignored(tmp_path):
    root = _repo(tmp_path, "emd", {"src/app/page.tsx": 'const x = 1; // see — note\nexport default () => <p>Real copy — with a dash</p>;'})
    assert us.survey(root)["copy_tells"]["em_dash"]["count"] == 1


def test_nested_app_root_is_found(tmp_path):
    root = tmp_path / "mono"
    (root / "app" / "src" / "pages").mkdir(parents=True)
    (root / "app" / "package.json").write_text(json.dumps({"dependencies": {"astro": "5"}}))
    (root / "app" / "src" / "pages" / "index.astro").write_text("<h1>hi</h1>")
    (root / "README.md").write_text("# mono")
    m = us.survey(root)
    assert m["framework"]["name"] == "astro" and m["app_root_rerooted_from"] == str(root.resolve())
    assert {r["route"] for r in m["routes"]} == {"/"}


def test_theme_toggle_component_is_not_a_token_file(tmp_path):
    root = _repo(tmp_path, "tt", {"src/components/theme-toggle.tsx": '<button style={{ color: "#123abc" }} />', "src/styles/theme/tokens.css": ":root{--x:#111111}"})
    kinds = {r["kind"]: r for r in us.survey(root)["roots"]}
    assert kinds["color"]["top_values"] == ["#123abc"]


# ---------------------------------------------------------------- gate: hardening
def test_render_evidence_rejects_junk_bytes_and_mislabeled_widths(tmp_path):
    root = _repo(tmp_path, "g1", {"src/app/page.tsx": "<main/>", "DESIGN.md": "x"})
    ev = tmp_path / "junk"
    ev.mkdir()
    (ev / "index-1280.png").write_bytes(b"\x00" * 9000)
    (ev / "index-390.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 9000)  # JPEG magic, no SOF
    r = _gate(root, evidence_dir=ev)
    assert r["evidence.render"].status == "FAIL" and "no valid screenshots" in r["evidence.render"].detail
    ev2 = tmp_path / "mislabel"
    ev2.mkdir()
    (ev2 / "index-1280.png").write_bytes(png_bytes(1280))
    (ev2 / "index-390.png").write_bytes(png_bytes(1280))  # says mobile, is desktop-wide
    r = _gate(root, evidence_dir=ev2)
    assert r["evidence.render"].status == "FAIL" and "mobile=0" in r["evidence.render"].detail
    ev3 = tmp_path / "good"
    ev3.mkdir()
    (ev3 / "index-1280.png").write_bytes(png_bytes(1280))
    (ev3 / "index-390.png").write_bytes(png_bytes(390))
    assert _gate(root, evidence_dir=ev3)["evidence.render"].status == "PASS"


def test_waiver_hardening_unknown_nonwaivable_valueless(tmp_path):
    w = tmp_path / "w.json"
    w.write_text(json.dumps({"waivers": [{"check": "nonexistent.check", "reason": "x" * 30}]}))
    with pytest.raises(SystemExit, match="unknown waiver check"):
        ug.load_waivers(w)
    w.write_text(json.dumps({"waivers": [{"check": "evidence.render", "reason": "we do not need screenshots, trust me bro"}]}))
    with pytest.raises(SystemExit, match="cannot be waived"):
        ug.load_waivers(w)
    w.write_text(json.dumps({"waivers": [{"check": "detector.rule", "reason": "x" * 30}]}))
    with pytest.raises(SystemExit, match="must name a `value`"):
        ug.load_waivers(w)
    w.write_text(json.dumps({"waivers": [{"check": "fonts.deliberate", "reason": "x" * 30}]}))
    with pytest.raises(SystemExit, match="must name a `value`"):
        ug.load_waivers(w)


def test_evidence_and_direction_cannot_be_waived_even_in_memory(tmp_path):
    root = _repo(tmp_path, "g2", {"src/app/page.tsx": "<main/>"})
    r = _gate(root, waivers={"waivers": [
        {"check": "evidence.render", "reason": "we do not need screenshots, trust me bro"},
        {"check": "direction.authored", "reason": "direction lives in the founder's head, honestly"},
    ]})
    assert r["evidence.render"].status == "FAIL" and not r["evidence.render"].waived
    assert r["direction.authored"].status == "FAIL" and not r["direction.authored"].waived


def test_motion_essential_utilities_warn_not_fail(tmp_path):
    root = _repo(tmp_path, "spin", {"src/Loader.tsx": '<div className="animate-spin" />'})
    r = _gate(root, no_render=True)
    assert r["motion.reduced-motion"].status == "WARN"
    (root / "src" / "Hero.tsx").write_text('<div className="animate-bounce" />')
    r = _gate(root, no_render=True)
    assert r["motion.reduced-motion"].status == "FAIL"


def test_unwritable_json_output_exits_2(tmp_path):
    root = _repo(tmp_path, "g3", {"src/app/page.tsx": "<main/>"})
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    from pathlib import Path
    scripts = Path(us.__file__).resolve().parent
    try:
        r = subprocess.run([sys.executable, str(scripts / "unslop_gate.py"), str(root), "--no-render", "--quiet", "--json", str(ro / "sub" / "g.json")], capture_output=True, text=True)
        assert r.returncode == 2 and "cannot write" in r.stderr
        r = subprocess.run([sys.executable, str(scripts / "unslop_survey.py"), str(root), "--quiet", "--json", str(ro / "sub" / "s.json")], capture_output=True, text=True)
        assert r.returncode == 2 and "cannot write" in r.stderr
    finally:
        ro.chmod(0o700)


# ---------------------------------------------------------------- round-3 (codex r3): edges the round-2 fixes opened
def test_buzzwords_on_styled_jsx_lines_are_still_caught(tmp_path):
    """Round-2 skipped any line with className= — that lost real copy on styled elements."""
    root = _repo(tmp_path, "styled", {
        "src/components/Hero.tsx": '<h1 className="text-5xl font-bold">Supercharge your workflow</h1><img alt="Effortless onboarding" className="w-full" /><div style={{ color: "var(--color-surface-elevated)" }} className="unlockScroll"><iframe seamless src="/e" /></div>',
    })
    ct = us.survey(root)["copy_tells"]["buzzwords"]
    assert ct["count"] == 1  # 'Supercharge' (h1) — the alt copy is on the same line so it is one line; markup words do not count
    root2 = _repo(tmp_path, "styled2", {"src/components/Hero.tsx": '<div className="elevate-card unlockScroll" data-x="seamless" />'})
    assert us.survey(root2)["copy_tells"]["buzzwords"]["count"] == 0


def test_ui_components_under_lib_or_hooks_are_still_surfaces(tmp_path):
    root = _repo(tmp_path, "libui", {
        "src/lib/components/Feed.tsx": "export function Feed() { const { data, isLoading } = useQuery({ queryFn: () => fetch('/f') }); return isLoading ? <Skeleton/> : <ul/>; }",
        "src/app/api/feed/route.ts": "export async function GET() { return fetch('/x'); }",
    })
    a = us.survey(root)["substance"]["async_surfaces"]
    assert set(a["files"]) == {"src/lib/components/Feed.tsx"} and a["with_loading_state"] == 1


def test_copy_module_predicate_is_honest(tmp_path):
    """lib/content.ts is a copy module; lib/constants.ts and lib/features.ts (feature flags) are not."""
    root = _repo(tmp_path, "cm2", {
        "src/lib/content.ts": 'export const hero = "Lorem ipsum — supercharge";',
        "src/lib/constants.ts": 'export const NAME = "John Doe"; // fixture author',
        "src/lib/features.ts": 'export const flags = { acme: true }; // Acme tenant flag',
        "src/config/site.ts": 'export const siteConfig = { name: "Acme Inc.", tagline: "It\'s not a tool, it\'s a movement" };',
    })
    m = us.survey(root)
    ph = m["substance"]["placeholders"]
    assert "lorem-ipsum" in ph and any("content.ts" in x for x in ph["lorem-ipsum"])
    assert "acme" in ph and all("site.ts" in x for x in ph["acme"])           # not features.ts
    assert "john-jane-doe" not in ph                                          # constants.ts is not scanned
    assert m["copy_tells"]["not_x_but_y"]["count"] == 1


def test_workspace_root_with_tooling_manifest_still_finds_the_app(tmp_path):
    root = tmp_path / "ws"
    (root / "apps" / "web" / "src" / "app").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": "ws", "private": True, "devDependencies": {"turbo": "2", "biome": "1"}}))
    (root / "apps" / "web" / "package.json").write_text(json.dumps({"dependencies": {"next": "15", "react": "19"}}))
    (root / "apps" / "web" / "src" / "app" / "page.tsx").write_text("<main/>")
    m = us.survey(root)
    assert m["framework"]["name"] == "next" and m["app_root_rerooted_from"] == str(root.resolve())
    # a root that IS the app is never re-rooted even if it has a nested app
    root2 = tmp_path / "isapp"
    (root2 / "src" / "app").mkdir(parents=True)
    (root2 / "docs-site").mkdir()
    (root2 / "package.json").write_text(json.dumps({"dependencies": {"next": "15", "react": "19"}}))
    (root2 / "docs-site" / "package.json").write_text(json.dumps({"dependencies": {"astro": "5"}}))
    (root2 / "src" / "app" / "page.tsx").write_text("<main/>")
    m2 = us.survey(root2)
    assert m2["framework"]["name"] == "next" and m2["app_root_rerooted_from"] is None


def test_hex_on_a_line_with_an_anchor_href_is_still_counted(tmp_path):
    root = _repo(tmp_path, "hex2", {"src/Nav.tsx": '<a href="#add-item" style={{ color: "#c0ffee" }}>go</a>'})
    kinds = {r["kind"]: r for r in us.survey(root)["roots"]}
    assert kinds["color"]["top_values"] == ["#c0ffee"]


def test_webp_evidence_needs_parseable_dimensions(tmp_path):
    root = _repo(tmp_path, "webp", {"src/app/page.tsx": "<main/>", "DESIGN.md": "x"})
    ev = tmp_path / "ev"
    ev.mkdir()
    # a RIFF/WEBP header with an unknown chunk → not an image → FAIL
    (ev / "index-1280.webp").write_bytes(b"RIFF" + (9000).to_bytes(4, "little") + b"WEBPXXXX" + b"\x00" * 9000)
    (ev / "index-390.png").write_bytes(png_bytes(390))
    r = _gate(root, evidence_dir=ev)
    assert r["evidence.render"].status == "FAIL"
    # a VP8X WebP with a 1280×800 canvas → accepted
    vp8x = b"RIFF" + (9000).to_bytes(4, "little") + b"WEBPVP8X" + (10).to_bytes(4, "little") + b"\x00" * 4 + (1279).to_bytes(3, "little") + (799).to_bytes(3, "little")
    (ev / "index-1280.webp").write_bytes(vp8x + b"\x00" * 9000)
    r = _gate(root, evidence_dir=ev)
    assert r["evidence.render"].status == "PASS", r["evidence.render"].detail
    # …and a VP8X claiming 390 wide but named -1280 → mislabeled → FAIL
    vp8x_small = b"RIFF" + (9000).to_bytes(4, "little") + b"WEBPVP8X" + (10).to_bytes(4, "little") + b"\x00" * 4 + (389).to_bytes(3, "little") + (799).to_bytes(3, "little")
    (ev / "index-1280.webp").write_bytes(vp8x_small + b"\x00" * 9000)
    assert _gate(root, evidence_dir=ev)["evidence.render"].status == "FAIL"


def test_copy_module_predicate_ignores_test_and_story_files(tmp_path):
    root = _repo(tmp_path, "cmtest", {
        "src/content.test.ts": 'expect(x).toBe("Lorem ipsum John Doe");',
        "src/content.stories.ts": 'export const Default = { args: { name: "Acme Inc." } };',
        "src/content.ts": 'export const hero = "Lorem ipsum";',
    })
    ph = us.survey(root)["substance"]["placeholders"]
    assert "john-jane-doe" not in ph and "acme" not in ph
    assert "lorem-ipsum" in ph and all("content.ts" in x for x in ph["lorem-ipsum"])


def test_jsx_expression_string_attrs_count_as_copy(tmp_path):
    root = _repo(tmp_path, "attrx", {"src/Hero.tsx": '<img alt={"Effortless onboarding"} className="w-full" />'})
    assert us.survey(root)["copy_tells"]["buzzwords"]["count"] == 1


# ---------------------------------------------------------------- round-5 (Strata B r2 residuals)
def test_reports_route_dir_is_surveyed_but_top_level_reports_is_not(tmp_path):
    root = _repo(tmp_path, "rep", {
        "src/app/reports/page.tsx": "<h1>Lorem ipsum —</h1>",
        "reports/lighthouse.html": "<div style='color:#111111;background:#222222;border:#333333;outline:#444444;fill:#555555;stroke:#666666;color:#777777;color:#888888;color:#999999;color:#aaaaaa;color:#bbbbbb;color:#cccccc;color:#dddddd'>—</div>",
        "src/app/page.tsx": "<main/>",
    })
    m = us.survey(root)
    assert "/reports" in {r["route"] for r in m["routes"]}
    assert "lorem-ipsum" in m["substance"]["placeholders"] and m["copy_tells"]["em_dash"]["count"] == 1
    assert "color" not in {r["kind"] for r in m["roots"]}


def test_nested_git_repo_falls_back_to_walk(tmp_path):
    root = tmp_path / "ws"
    (root / "web" / "src" / "app").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": "ws", "workspaces": ["web"], "dependencies": {"next": "15"}}))
    (root / "web" / "package.json").write_text(json.dumps({"dependencies": {"next": "15", "react": "19"}}))
    (root / "web" / "src" / "app" / "page.tsx").write_text("<h1>hello —</h1>")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "init", "-q"], cwd=root / "web", check=True)   # nested repo: root ls-files sees nothing under web/
    m = us.survey(root)
    assert m["counts"]["walk_mode"] == "walk" and m["counts"]["ui_files"] == 1 and m["copy_tells"]["em_dash"]["count"] == 1


def test_git_mode_and_walk_mode_agree_on_dot_dirs(tmp_path):
    files = {"src/app/page.tsx": "<main/>", "src/.storybook/preview.tsx": "<p>— story</p>"}
    a = _repo(tmp_path, "nogit", files)
    b = _repo(tmp_path, "git", files)
    subprocess.run(["git", "init", "-q"], cwd=b, check=True)
    ma, mb = us.survey(a), us.survey(b)
    assert ma["counts"]["walk_mode"] == "walk" and mb["counts"]["walk_mode"] == "git"
    assert ma["copy_tells"]["em_dash"]["count"] == mb["copy_tells"]["em_dash"]["count"] == 0


def test_buzzwords_css_tokens_camelcase_and_inline_script_identifiers(tmp_path):
    root = _repo(tmp_path, "buzz2", {
        "src/A.tsx": 'const s = { backgroundColor: "var(--color-surface-elevated)" };',
        "src/B.tsx": '<div className="elevate-card unlockScroll" />',
        "src/index.html": "<script>if (!unlockedFired) { go(); }</script><p>Unlock seamless growth</p>",
        "src/C.tsx": '<iframe seamless src="/e" />',
    })
    ct = us.survey(root)["copy_tells"]["buzzwords"]
    assert ct["count"] == 1 and "index.html" in ct["sites"][0]


def test_apple_system_is_a_family_and_inherit_is_not(tmp_path):
    root = _repo(tmp_path, "fam", {
        "src/styles/a.css": ":root { --font-body: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }",
        "src/theme.tsx": 'createTheme({ typography: { fontFamily: "inherit" } })',
    })
    fams = us.survey(root)["fonts"]["families"]
    assert "-apple-system" in fams and "inherit" not in fams and "blinkmacsystemfont" not in fams


def test_google_fonts_link_yields_every_family(tmp_path):
    root = _repo(tmp_path, "gf", {
        "src/app/layout.tsx": '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=Space+Grotesk&display=swap" rel="stylesheet" />',
        "src/styles/g.css": "@import url('https://fonts.googleapis.com/css?family=Poppins&family=DM+Sans');",
    })
    fams = us.survey(root)["fonts"]["families"]
    assert {"inter", "space grotesk", "poppins", "dm sans"} <= set(fams)


def test_shadcn_animate_in_out_is_library_motion_warn(tmp_path):
    root = _repo(tmp_path, "shad", {"src/components/ui/dialog.tsx": '<div className="animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out" />'})
    r = _gate(root, no_render=True)
    assert r["motion.reduced-motion"].status == "WARN"


def test_static_site_root_is_never_rerooted_into_a_tooling_app(tmp_path):
    root = tmp_path / "static"
    (root / "tools" / "gen" / "src").mkdir(parents=True)
    (root / "index.html").write_text("<html><body><h1>Real site —</h1></body></html>")
    (root / "tools" / "gen" / "package.json").write_text(json.dumps({"dependencies": {"react": "19"}}))
    (root / "tools" / "gen" / "src" / "index.tsx").write_text("<b/>")
    m = us.survey(root)
    assert m["framework"]["name"] == "static-html" and m["app_root_rerooted_from"] is None and m["copy_tells"]["em_dash"]["count"] == 1


def test_ui_arrows_are_not_emoji_but_star_is(tmp_path):
    root = _repo(tmp_path, "arrows", {"src/T.tsx": "<span>Split Right ⬌</span><span>Split Down ⬍</span>", "src/S.tsx": "<span>⭐⭐⭐⭐⭐</span>"})
    ct = us.survey(root)["copy_tells"]["emoji"]
    assert ct["count"] == 1 and "S.tsx" in ct["sites"][0]


def test_star_waiver_value_does_not_wildcard(tmp_path):
    w = tmp_path / "w.json"
    w.write_text(json.dumps({"waivers": [{"check": "detector.rule", "value": "*", "reason": "x" * 30}]}))
    with pytest.raises(SystemExit, match="must name a `value`"):
        ug.load_waivers(w)
    root = _repo(tmp_path, "starw", {"src/app/page.tsx": "<main/>"})
    manifest = us.survey(root)
    manifest["detector"] = us.summarize_detector([{"antipattern": "gradient-text", "severity": "warning", "file": "a", "line": 1}])
    r = _gate(root, manifest=manifest, no_render=True, waivers={"waivers": [{"check": "detector.rule", "value": "*", "reason": "x" * 30}]})
    assert r["detector.clean"].status == "FAIL"   # in-memory "*" ignored too


# ---------------------------------------------------------------- gate-level assertions that were missing
def test_gate_tokens_radius_shadow_buzz_claims_error_states_both_polarities(tmp_path):
    bad = _repo(tmp_path, "tokbad", {
        "src/A.tsx": '<div className="rounded-[13px] rounded-[7px] rounded-[21px] shadow-[0_0_40px_#f0f] shadow-[0_2px_4px_#000] shadow-[0_8px_30px_#0af]">\n<p>Supercharge your team</p>\n<p>Unleash and empower</p>\n<p>Elevate the game-changing next-gen 99.9% uptime for 10,000+ users</p>\n</div>',
        "src/B.tsx": "export default async function P() { const d = await fetch('/x'); return <ul/>; }",
    })
    r = _gate(bad, no_render=True)
    assert r["tokens.radius"].status == "FAIL" and "3 arbitrary" in r["tokens.radius"].detail
    assert r["tokens.shadow"].status == "FAIL"
    assert r["copy.buzzwords"].status == "WARN"
    assert r["substance.claims"].status == "WARN" and "fake-metrics" in r["substance.claims"].detail
    assert r["substance.error-states"].status == "WARN"
    good = _repo(tmp_path, "tokgood", {
        "src/A.tsx": '<div className="rounded-md shadow-sm">Bookkeeping for two-person studios</div>',
        "src/B.tsx": "export default function P() { const { data, isError } = useQuery({ queryFn: () => fetch('/x') }); if (isError) return <p role=\"alert\">Could not load</p>; return <ul/>; }",
    })
    r = _gate(good, no_render=True)
    assert r["tokens.radius"].status == "PASS" and r["tokens.shadow"].status == "PASS"
    assert r["copy.buzzwords"].status == "PASS" and "substance.claims" not in r
    assert r["substance.error-states"].status == "PASS"


def test_manifest_is_actually_used_by_the_gate(tmp_path, sloppy_repo):
    """A tampered manifest must change the verdict — proves --manifest is read, not the survey re-run."""
    from pathlib import Path
    scripts = Path(us.__file__).resolve().parent
    m = us.survey(sloppy_repo)
    m["copy_tells"]["emoji"] = {"count": 0, "sites": []}
    m["substance"]["design_docs"] = {"DESIGN.md": True, "PRODUCT.md": True}
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    out = tmp_path / "g.json"
    subprocess.run([sys.executable, str(scripts / "unslop_gate.py"), str(sloppy_repo), "--manifest", str(mp), "--no-render", "--quiet", "--json", str(out)], capture_output=True, text=True)
    res = {x["check"]: x["status"] for x in json.loads(out.read_text())["results"]}
    assert res["copy.emoji"] == "PASS" and res["direction.authored"] == "PASS"   # only true if the tampered manifest was used


# ---------------------------------------------------------------- round-6 (codex r5): edges round 5 opened
def test_hyphenated_buzzword_prose_still_counts(tmp_path):
    root = _repo(tmp_path, "hy", {
        "src/Hero.tsx": "<p>A next-gen, state-of-the-art, cutting-edge, game-changing platform</p>",
        "src/Card.tsx": 'const s = { backgroundColor: "var(--color-surface-elevated)" }; <div className="elevate-card next-gen-badge" />',
    })
    ct = us.survey(root)["copy_tells"]["buzzwords"]
    assert ct["count"] == 1 and "Hero.tsx" in ct["sites"][0]


def test_tailwind_var_arbitrary_values_are_token_refs_not_drift(tmp_path):
    root = _repo(tmp_path, "tvar", {"src/A.tsx": '<div className="rounded-[var(--radius)] rounded-[var(--radius-lg)] shadow-[var(--shadow-card)] rounded-[13px]" />'})
    kinds = {r["kind"]: r for r in us.survey(root)["roots"]}
    assert kinds["radius"]["arbitrary"] == 1 and kinds["shadow"]["arbitrary"] == 0


def test_css_var_font_keywords_are_not_families(tmp_path):
    root = _repo(tmp_path, "fk", {"src/styles/a.css": ":root { --font-body: inherit; --font-display: unset; --font-sans: 'Fraunces', serif; }"})
    fams = us.survey(root)["fonts"]["families"]
    assert set(fams) == {"fraunces"}


def test_reroot_candidate_under_nested_build_dir_is_allowed(tmp_path):
    """SKIP_TOP_LEVEL_DIRS applies to the ROOT child only when choosing a candidate app."""
    root = tmp_path / "ws2"
    (root / "packages" / "build" / "src" / "app").mkdir(parents=True)     # 'build' is a package name here, not an artefact
    (root / "package.json").write_text(json.dumps({"name": "ws2", "devDependencies": {"turbo": "2"}}))
    (root / "packages" / "build" / "package.json").write_text(json.dumps({"dependencies": {"next": "15", "react": "19"}}))
    (root / "packages" / "build" / "src" / "app" / "page.tsx").write_text("<main/>")
    m = us.survey(root)
    assert m["framework"]["name"] == "next" and m["app_root_rerooted_from"] == str(root.resolve())


# ---------------------------------------------------------------- dogfood (broomva.tech): DESIGN.md at the repo root of a monorepo
def test_design_docs_found_at_git_toplevel_above_the_app(tmp_path):
    root = tmp_path / "mono"
    (root / "apps" / "web" / "src" / "app").mkdir(parents=True)
    (root / "DESIGN.md").write_text("# House\nIcons: Lucide, deliberate. Body uses the system stack deliberately.\n")
    (root / "apps" / "web" / "package.json").write_text(json.dumps({"dependencies": {"next": "15", "react": "19", "lucide-react": "1"}}))
    (root / "apps" / "web" / "src" / "app" / "page.tsx").write_text('import { X } from "lucide-react"; export default () => <main style={{fontFamily: "system-ui"}}/>;')
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    m = us.survey(root / "apps" / "web")
    dd = m["substance"]["design_docs"]
    assert dd["DESIGN.md"] is True and dd["paths"]["DESIGN.md"].endswith("mono/DESIGN.md")
    r = _gate(root / "apps" / "web", manifest=m, no_render=True)
    assert r["direction.authored"].status == "PASS" and "mono/DESIGN.md" in r["direction.authored"].detail
    assert r["icons.single-system"].status == "PASS"      # the repo-root DESIGN.md states the Lucide decision
    # …but never above the git toplevel: a DESIGN.md in tmp_path (outside the repo) is not the app's
    (tmp_path / "DESIGN.md").write_text("# not yours")
    root2 = tmp_path / "mono2"
    (root2 / "src").mkdir(parents=True)
    (root2 / "package.json").write_text(json.dumps({"dependencies": {"react": "19"}}))
    (root2 / "src" / "A.tsx").write_text("<b/>")
    subprocess.run(["git", "init", "-q"], cwd=root2, check=True)
    assert us.survey(root2)["substance"]["design_docs"]["DESIGN.md"] is False


def test_input_placeholder_examples_and_prose_mdx_are_not_fake_content(tmp_path):
    root = _repo(tmp_path, "ph2", {
        "src/components/login-form.tsx": '<input placeholder="you@example.com" /><input placeholder="Acme Labs" />',
        "content/writing/essay.mdx": "As I told your company last year, testimonials matter. Pricing: Free, Pro, Enterprise. 99.9% of the time. Lorem ipsum.",
        "src/app/page.tsx": "<main/>",
    })
    s = us.survey(root)["substance"]
    assert "example-domain" not in s["placeholders"] and "acme" not in s["placeholders"]
    assert "your-company" not in s["placeholders"] and "fake-metrics" not in s["placeholders"]
    assert "lorem-ipsum" in s["placeholders"]                    # prose still counts lorem
    assert s["testimonials"]["files"] == [] and s["pricing"]["files"] == []


def test_tests_scripts_and_og_image_routes_are_not_ui_surfaces(tmp_path):
    root = _repo(tmp_path, "nonsurf", {
        "src/app/page.tsx": "<main>Real copy</main>",
        "src/app/opengraph-image.tsx": 'export default () => <div style={{ color: "#111111", background: "#222222", border: "#333333 #444444 #555555 #666666 #777777 #888888 #999999 #aaaaaa #bbbbbb #cccccc #dddddd" }}>— ✨</div>;',
        "src/components/Foo.test.tsx": "expect(<p>— ✨ ✓ Lorem ipsum</p>)",
        "scripts/gen.ts": 'console.log("✓ done — supercharge")',
        "tests/e2e/home.spec.ts": 'test("—", () => {})',
    })
    m = us.survey(root)
    assert all(v["count"] == 0 for v in m["copy_tells"].values())
    assert "color" not in {r["kind"] for r in m["roots"]}
    assert "lorem-ipsum" not in m["substance"]["placeholders"]


def test_ai_default_face_stated_in_design_md_passes(tmp_path):
    root = _repo(tmp_path, "geist", {
        "DESIGN.md": "# Brand\n\nBody: Geist (Google Fonts, via next/font) — deliberate; Monospace: Geist Mono.\n",
        "src/app/layout.tsx": 'import { Geist, Geist_Mono } from "next/font/google";\nconst g = Geist({ subsets: ["latin"] });',
    })
    r = _gate(root, no_render=True)
    assert r["fonts.deliberate"].status == "PASS" and "stated as the decision" in r["fonts.deliberate"].detail
    root2 = _repo(tmp_path, "inter", {"DESIGN.md": "# Brand\nBody: Geist.\n", "src/app/layout.tsx": 'import { Inter } from "next/font/google";\nconst i = Inter({ subsets: ["latin"] });'})
    r2 = _gate(root2, no_render=True)
    assert r2["fonts.deliberate"].status == "FAIL" and "inter" in r2["fonts.deliberate"].detail


def test_coming_soon_and_internal_docs_are_not_placeholders(tmp_path):
    root = _repo(tmp_path, "cs", {
        "src/app/lago/page.tsx": "<div>Coming soon</div>",
        "docs/specs/plan.md": "[Insert your plan here] lorem ipsum",
        "content/writing/_drafts/x.md": "[Insert tagline here]",
        "src/app/page.tsx": "<p>[Insert your tagline here]</p>",
    })
    ph = us.survey(root)["substance"]["placeholders"]
    assert ph.get("insert-here") and all("src/app/page.tsx" in x for x in ph["insert-here"])
    assert "lorem-ipsum" not in ph


def test_standalone_em_dash_markers_are_not_copy_tells(tmp_path):
    root = _repo(tmp_path, "emm", {"src/A.tsx": '''
const a = loading ? "—" : String(n);
return <td>—</td>;
const b = x ?? "—";
<p>Real prose — with a dash</p>
'''})
    ct = us.survey(root)["copy_tells"]["em_dash"]
    assert ct["count"] == 1 and ct["sites"][0].endswith(":5")


def test_keyframe_frames_are_not_shadow_or_radius_drift(tmp_path):
    root = _repo(tmp_path, "kf", {"src/styles/x.css": '''
@keyframes ring { 0% { box-shadow: 0 0 0 0 oklch(0.6 0.12 260 / 0.7); } 70% { box-shadow: 0 0 0 8px oklch(0.6 0.12 260 / 0); } 100% { box-shadow: 0 0 0 0 oklch(0.6 0.12 260 / 0); } }
@keyframes grow {
  from { border-radius: 2px; }
  to { border-radius: 9px; }
}
.card { box-shadow: 0 4px 8px oklch(0 0 0 / 0.4); border-radius: 12px; }
'''})
    kinds = {r["kind"]: r for r in us.survey(root)["roots"]}
    assert int(kinds["shadow"]["value"].split()[0]) == 1 and int(kinds["radius"]["value"].split()[0]) == 1


def test_em_dash_entities_and_escapes_count(tmp_path):
    root = _repo(tmp_path, "ent", {"src/A.tsx": '<p>Four services &mdash; Arcan</p>\n<p>{"a \\u2014 b"}</p>\n<p>x &#8212; y</p>'})
    assert us.survey(root)["copy_tells"]["em_dash"]["count"] == 3
