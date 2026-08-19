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
