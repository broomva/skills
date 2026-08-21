"""Tests for unslop_survey.py — every signal in both polarities (sloppy vs crafted fixture)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import unslop_survey as us  # via conftest sys.path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "unslop_survey.py"


# ---------------------------------------------------------------- framework/routes
def test_detects_next_app_router_and_routes(sloppy_repo, crafted_repo):
    m = us.survey(sloppy_repo)
    assert m["schema"] == "unslop-survey/1"
    assert m["framework"]["name"] == "next" and m["framework"]["router"] == "app"
    assert m["framework"]["tailwind"] is True
    routes = {(r["route"], r["kind"]) for r in m["routes"]}
    assert ("/", "page") in routes

    m2 = us.survey(crafted_repo)
    routes2 = {(r["route"], r["kind"]) for r in m2["routes"]}
    assert {("/", "page"), ("/terms", "page"), ("/privacy", "page"), ("/ledger", "page"), ("/ledger", "loading"), ("/", "error")} <= routes2


def test_next_pages_router_and_sveltekit(tmp_path):
    root = tmp_path / "pages"
    (root / "pages" / "blog").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"next": "14", "react": "18"}}))
    (root / "pages" / "index.tsx").write_text("export default () => <h1>hi</h1>;")
    (root / "pages" / "blog" / "[slug].tsx").write_text("export default () => <h1>post</h1>;")
    (root / "pages" / "_app.tsx").write_text("export default ({Component}) => <Component/>;")
    m = us.survey(root)
    assert m["framework"]["router"] == "pages"
    assert {r["route"] for r in m["routes"]} == {"/", "/blog/[slug]"}

    sk = tmp_path / "sk"
    (sk / "src" / "routes" / "(marketing)" / "pricing").mkdir(parents=True)
    (sk / "package.json").write_text(json.dumps({"devDependencies": {"@sveltejs/kit": "2", "svelte": "5"}}))
    (sk / "src" / "routes" / "+page.svelte").write_text("<h1>home</h1>")
    (sk / "src" / "routes" / "(marketing)" / "pricing" / "+page.svelte").write_text("<h1>pricing</h1>")
    m = us.survey(sk)
    assert m["framework"]["name"] == "sveltekit"
    assert {r["route"] for r in m["routes"]} == {"/", "/pricing"}


def test_static_html_routes(tmp_path):
    root = tmp_path / "html"
    (root / "legal").mkdir(parents=True)
    (root / "index.html").write_text("<html><body style='font-family: Inter, sans-serif'><h1>Hi ✨</h1><a href='/legal/privacy.html'>Privacy</a></body></html>")
    (root / "legal" / "privacy.html").write_text("<h1>Privacy</h1>")
    m = us.survey(root)
    assert m["framework"]["name"] == "static-html"
    assert {r["route"] for r in m["routes"]} == {"/", "/legal/privacy"}
    assert m["substance"]["legal"]["privacy_route"] == "/legal/privacy"
    assert m["substance"]["legal"]["privacy_linked"] is True
    assert m["copy_tells"]["emoji"]["count"] == 1


# ---------------------------------------------------------------- fonts / roots
def test_fonts_primary_vs_fallback_and_root_attribution(sloppy_repo, crafted_repo):
    m = us.survey(sloppy_repo)
    fams = m["fonts"]["families"]
    assert "inter" in fams and "space grotesk" in fams
    assert "-apple-system" in m["fonts"]["fallback_only"] and "-apple-system" not in fams
    assert "inter" in m["fonts"]["default_families_in_use"]
    font_roots = [r for r in m["roots"] if r["kind"] == "font" and r["value"] == "inter"]
    assert font_roots and font_roots[0]["default"] is True
    assert font_roots[0]["root_file"].endswith(("layout.tsx", "globals.css"))
    assert "Decide the typeface once" in font_roots[0]["fix"]

    m2 = us.survey(crafted_repo)
    assert "signifier" in m2["fonts"]["self_hosted"]
    assert m2["fonts"]["default_families_in_use"] == []
    sig = [r for r in m2["roots"] if r["kind"] == "font" and r["value"] == "signifier"][0]
    assert sig["default"] is False and sig["self_hosted"] is True


def test_icons_component_libs_and_mixed_flag(sloppy_repo, crafted_repo):
    m = us.survey(sloppy_repo)
    assert m["icons"]["lucide"] >= 2 and m["icons"]["heroicons"] == 1
    icon_roots = [r for r in m["roots"] if r["kind"] == "icons"]
    assert any(r["mixed_libraries"] for r in icon_roots)
    assert "shadcn(cva)" in m["component_libs"]
    m2 = us.survey(crafted_repo)
    assert list(m2["icons"]) == ["lucide"]


def test_visual_vocabulary_roots(sloppy_repo, crafted_repo):
    m = us.survey(sloppy_repo)
    kinds = {r["kind"]: r for r in m["roots"]}
    assert kinds["color"]["default"] is True and kinds["color"]["sites"] >= 8
    assert kinds["radius"]["default"] is True  # > 4 distinct radii
    assert kinds["shadow"]["default"] is True  # > 4 distinct shadows
    assert kinds["gradient"]["sites"] >= 2
    assert kinds["glass"]["sites"] >= 1
    m2 = us.survey(crafted_repo)
    kinds2 = {r["kind"] for r in m2["roots"]}
    assert "color" not in kinds2  # hex only in the token file (globals.css)
    assert "gradient" not in kinds2 and "glass" not in kinds2


# ---------------------------------------------------------------- copy tells
def test_copy_tells(sloppy_repo, crafted_repo):
    m = us.survey(sloppy_repo)
    ct = m["copy_tells"]
    assert ct["em_dash"]["count"] >= 2
    assert ct["emoji"]["count"] >= 2
    assert ct["checkmark_bullets"]["count"] >= 1
    assert ct["not_x_but_y"]["count"] == 1
    assert ct["buzzwords"]["count"] >= 2
    assert all(":" in s for s in ct["em_dash"]["sites"])  # file:line provenance
    m2 = us.survey(crafted_repo)
    assert all(v["count"] == 0 for v in m2["copy_tells"].values())


# ---------------------------------------------------------------- substance
def test_substance_legal_async_placeholders(sloppy_repo, crafted_repo):
    s = us.survey(sloppy_repo)["substance"]
    assert s["legal"]["terms_route"] is None and s["legal"]["privacy_route"] is None
    assert s["async_surfaces"]["count"] >= 1 and s["async_surfaces"]["with_loading_state"] == 0
    assert "src/lib/api.ts" not in s["async_surfaces"]["files"]  # a lib module is not a surface
    ph = s["placeholders"]
    assert {"lorem-ipsum", "john-jane-doe", "acme", "stock-image-host", "fake-metrics"} <= set(ph)
    assert s["testimonials"]["verify_real"] is True
    assert s["pricing"]["three_tier_scaffold_suspected"] is True
    assert s["product_evidence"]["has_real_evidence"] is False
    assert s["motion"]["files_with_motion"] >= 1 and s["motion"]["reduced_motion_respected"] is False
    assert (s["design_docs"]["DESIGN.md"], s["design_docs"]["PRODUCT.md"]) == (False, False)

    s2 = us.survey(crafted_repo)["substance"]
    assert s2["legal"]["terms_route"] == "/terms" and s2["legal"]["privacy_route"] == "/privacy"
    assert s2["legal"]["terms_linked"] and s2["legal"]["privacy_linked"]
    a = s2["async_surfaces"]
    assert a["count"] >= 1 and a["with_loading_state"] == a["count"] and a["with_error_state"] >= 1 and a["with_empty_state"] >= 1
    assert a["route_level_loading_files"] and a["route_level_error_files"]
    assert s2["placeholders"] == {}
    assert s2["product_evidence"]["has_real_evidence"] is True
    assert s2["motion"]["reduced_motion_respected"] is True
    assert (s2["design_docs"]["DESIGN.md"], s2["design_docs"]["PRODUCT.md"]) == (True, True) and s2["design_docs"]["paths"]["DESIGN.md"].endswith("crafted/DESIGN.md")


def test_placeholder_regex_precision(tmp_path):
    """The dependency-array / data-attribute shapes that first false-positived must stay silent."""
    root = tmp_path / "p"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"react": "19"}}))
    (root / "src" / "A.tsx").write_text("""
useEffect(() => {}, [add, globalDrop]);
<div className="data-[placeholder]:text-muted-foreground" />
""")
    (root / "src" / "B.tsx").write_text("<p>[Insert your tagline here]</p>")
    s = us.survey(root)["substance"]["placeholders"]
    assert "insert-here" in s and len(s["insert-here"]) == 1 and "B.tsx" in s["insert-here"][0]


def test_profile_hint(sloppy_repo, crafted_repo, tmp_path):
    assert us.survey(sloppy_repo)["profile_hint"] == "persuade"  # hero + pricing + testimonials
    assert us.survey(crafted_repo)["profile_hint"] == "operate"  # async, no landing hints
    empty = tmp_path / "e"
    empty.mkdir()
    assert us.survey(empty)["profile_hint"] == "unknown"


# ---------------------------------------------------------------- detector composition
def test_summarize_detector_splits_primary_and_advisory():
    findings = [
        {"antipattern": "overused-font", "severity": "warning", "file": "a.css", "line": 3, "snippet": "font-family: Inter"},
        {"antipattern": "em-dash-overuse", "severity": "advisory", "advisory": True, "file": "b.tsx", "line": 9},
        {"antipattern": "gradient-text", "severity": "error", "file": "c.tsx", "line": 1},
    ]
    d = us.summarize_detector(findings, ["node", "detect.mjs"])
    assert d["status"] == "ok" and d["primary_count"] == 2 and d["advisory_count"] == 1
    assert d["by_rule"] == {"overused-font": 1, "em-dash-overuse": 1, "gradient-text": 1}
    assert d["findings"][1]["advisory"] is True


def test_run_detector_unavailable_is_reported_not_fatal(sloppy_repo, monkeypatch):
    monkeypatch.setattr(us, "find_detector", lambda: None)
    monkeypatch.delenv("UNSLOP_DETECTOR", raising=False)
    d = us.run_detector(sloppy_repo)
    assert d["status"] == "unavailable" and d["findings"] == []


def test_run_detector_with_fake_command(sloppy_repo, tmp_path):
    fake = tmp_path / "fake_detect.py"
    fake.write_text("import json,sys; print(json.dumps([{'antipattern':'gradient-text','severity':'warning','file':'x','line':1}])); sys.exit(2)")
    d = us.run_detector(sloppy_repo, detector_cmd=f"{sys.executable} {fake}")
    assert d["status"] == "ok" and d["primary_count"] == 1 and d["by_rule"] == {"gradient-text": 1} and d["exit_code"] == 2


def test_run_detector_crash_is_error_not_clean(sloppy_repo, tmp_path):
    """A crashing detector with empty stdout must never read as 'ok, 0 findings' (fail-open)."""
    crash = tmp_path / "crash.py"
    crash.write_text("import sys; sys.stderr.write('boom'); sys.exit(1)")
    d = us.run_detector(sloppy_repo, detector_cmd=f"{sys.executable} {crash}")
    assert d["status"] == "error" and d["findings"] == [] and "no JSON array" in d["note"]
    empty_ok = tmp_path / "empty.py"
    empty_ok.write_text("pass")  # exit 0, prints nothing — still not a clean signal
    d = us.run_detector(sloppy_repo, detector_cmd=f"{sys.executable} {empty_ok}")
    assert d["status"] == "error"
    garbage = tmp_path / "garbage.py"
    garbage.write_text("print('[not json')")
    d = us.run_detector(sloppy_repo, detector_cmd=f"{sys.executable} {garbage}")
    assert d["status"] == "error" and "not JSON" in d["note"]


def test_next_font_local_is_a_self_hosted_decision(tmp_path):
    root = tmp_path / "lf"
    (root / "src" / "app").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"next": "15", "react": "19"}}))
    (root / "src" / "app" / "layout.tsx").write_text("""
import localFont from "next/font/local";
const signifier = localFont({ src: [{ path: "../../public/fonts/Signifier-Regular.woff2", weight: "400" }], variable: "--font-signifier" });
export default function L({children}) { return <html className={signifier.variable}><body>{children}</body></html>; }
""")
    (root / "src" / "app" / "globals.css").write_text("body { font-family: var(--font-signifier), Georgia, serif; }")
    m = us.survey(root)
    assert "signifier" in m["fonts"]["families"] and "signifier" in m["fonts"]["self_hosted"]
    assert m["fonts"]["default_families_in_use"] == []
    assert any(x.startswith("local:signifier=signifier@") for x in m["fonts"]["next_font_imports"])
    r = [r for r in m["roots"] if r["kind"] == "font" and r["value"] == "signifier"][0]
    assert r["self_hosted"] is True and r["default"] is False and r["root_file"].endswith("layout.tsx")


def test_decorative_local_images_are_not_product_evidence(tmp_path):
    root = tmp_path / "ev"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"react": "19"}}))
    (root / "src" / "Hero.tsx").write_text('<header><img src="/images/logo.svg"/><img src="/assets/og-image.png"/><img src="/images/hero-illustration.png"/></header>')
    pe = us.survey(root)["substance"]["product_evidence"]
    assert pe["local_images"] == 3 and pe["evidence_images"] == 0 and pe["has_real_evidence"] is False
    (root / "src" / "Hero.tsx").write_text('<header><img src="/images/logo.svg"/><img src="/screenshots/ledger-march.png"/></header>')
    pe = us.survey(root)["substance"]["product_evidence"]
    assert pe["evidence_images"] == 1 and pe["has_real_evidence"] is True


def test_skipped_files_are_counted(tmp_path, monkeypatch):
    root = tmp_path / "big"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"react": "19"}}))
    (root / "src" / "A.tsx").write_text("<p>ok</p>")
    (root / "src" / "huge.tsx").write_text("x" * 10)
    monkeypatch.setattr(us, "MAX_FILE_BYTES", 5)
    m = us.survey(root)
    assert m["counts"]["skipped"]["oversized"] >= 1 and any("huge.tsx" in e for e in m["counts"]["skipped"]["examples"])


# ---------------------------------------------------------------- CLI
def test_cli_writes_json_and_md(sloppy_repo, tmp_path):
    out = tmp_path / "m.json"
    md = tmp_path / "m.md"
    r = subprocess.run([sys.executable, str(SCRIPT), str(sloppy_repo), "--json", str(out), "--md", str(md), "--quiet"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    m = json.loads(out.read_text())
    assert m["counts"]["ui_files"] >= 3
    text = md.read_text()
    assert "## Roots (fix once, here)" in text and "## Substance" in text


def test_cli_rejects_missing_dir(tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "nope")], capture_output=True, text=True)
    assert r.returncode == 2


# ------------------------------------------- prose-slop patterns (after no-ai-slop, BRO-2195)
def _prose_repo(tmp_path, name="prose"):
    root = tmp_path / name
    (root / "app").mkdir(parents=True)
    (root / "content").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"next": "15", "react": "19"}}))
    return root


def test_prose_patterns_fire_on_product_surfaces(tmp_path):
    root = _prose_repo(tmp_path)
    (root / "app" / "page.tsx").write_text("""
export default function Home() {
  return (
    <main>
      <h1>The future of shipping is here.</h1>
      <p>Here's what nobody tells you about scaling.</p>
      <p>Let me be clear: this is fast.</p>
      <li>The best part: it learns.</li>
      <p>This release marks a pivotal moment for the team.</p>
      <p>Experts agree that our approach works.</p>
      <p>Imagine a world where deploys are instant.</p>
      <p>Connect your repo. It's that simple.</p>
      <p>The launch adds file search, showcasing our commitment to better workflows.</p>
      <p>
        Ship without meetings. No setup. No config.
        Just code.
      </p>
    </main>
  );
}
""")
    (root / "content" / "landing.ts").write_text(
        'export const hero = "The future isn\'t coming. It\'s already here.";\n'
        'export const pitch = "Delve into a tapestry of transformative workflows — a real game changer.";\n'
    )
    ct = us.survey(root)["copy_tells"]
    for key in us.PROSE_KEYS:
        assert ct[key]["count"] >= 1, f"{key} did not fire"
    assert ct["fake_profound"]["count"] >= 2          # single-sentence hero + multi-sentence content string
    assert ct["buzzwords"]["count"] >= 1              # delve / tapestry / transformative / spaced "game changer"
    assert all(":" in s for s in ct["negative_listing"]["sites"])  # file:line provenance


def test_prose_patterns_stay_quiet_on_legit_ui(tmp_path):
    root = _prose_repo(tmp_path, "quiet")
    (root / "app" / "page.tsx").write_text("""
export default function Dashboard() {
  // here's the thing: comments are never copy
  return (
    <main>
      <span>Status: active</span>
      <span>Total: $42</span>
      <p>No results found.</p>
      <p>It is not possible to undo this action. Confirm to continue.</p>
      <address>1 Embarcadero Center</address>
      <button>Delete</button>
    </main>
  );
}
""")
    (root / "content" / "blog").mkdir(parents=True)
    (root / "content" / "blog" / "post.mdx").write_text(
        "# On writing\n\nHere's the thing: experts agree that authored prose keeps its own voice. "
        "The future of writing is here, and it's that simple.\n"
    )
    ct = us.survey(root)["copy_tells"]
    for key in us.PROSE_KEYS:
        assert ct[key]["count"] == 0, f"{key} false-positived: {ct[key]['sites']}"
    assert ct["buzzwords"]["count"] == 0


def test_not_x_but_y_period_and_isnt_forms(tmp_path):
    root = _prose_repo(tmp_path, "nxy")
    (root / "app" / "page.tsx").write_text("""
export default function Home() {
  return (
    <main>
      <p>It's not a chatbot. It's a teammate.</p>
      <p>The question isn't the model, it's the eval.</p>
    </main>
  );
}
""")
    ct = us.survey(root)["copy_tells"]
    assert ct["not_x_but_y"]["count"] == 2


# ---------------------------------------- codex r1 regressions (BRO-2195, one per finding)
def test_not_x_but_y_period_form_requires_an_article(tmp_path):
    root = _prose_repo(tmp_path, "nxy-fact")
    (root / "app" / "page.tsx").write_text("""
export default function Compat() {
  return (
    <main>
      <p>It's not available on iPad. It's available on desktop.</p>
      <p>The future isn't coming. It's already here.</p>
    </main>
  );
}
""")
    ct = us.survey(root)["copy_tells"]
    assert ct["not_x_but_y"]["count"] == 0        # factual note + article-less isn't → not the rhetorical tell
    assert ct["fake_profound"]["count"] == 1      # the kicker books ONCE, under the waivable aggregate


def test_template_strings_in_copy_modules_are_not_prose(tmp_path):
    root = _prose_repo(tmp_path, "tmpl")
    (root / "content" / "emails.ts").write_text(
        "export const template = '<div data-headline=\"What nobody tells you about billing\">Pay now</div>';\n"
        "export const cls = '<div class=\"game changer\">Pay now</div>';\n"
    )
    ct = us.survey(root)["copy_tells"]
    assert ct["faux_insight"]["count"] == 0
    assert ct["buzzwords"]["count"] == 0


def test_cited_claims_and_literal_bottom_line_stay_quiet(tmp_path):
    root = _prose_repo(tmp_path, "cited")
    (root / "app" / "page.tsx").write_text("""
export default function Docs() {
  return (
    <main>
      <p>Research shows that autocomplete reduces form errors.[1]</p>
      <p>The bottom line: annual billing only.</p>
      <p>Studies show onboarding drops by half.</p>
    </main>
  );
}
""")
    ct = us.survey(root)["copy_tells"]
    assert ct["weasel_attribution"]["count"] == 1  # only the UNcited "Studies show" line
    assert ct["colon_reveal"]["count"] == 0        # "the bottom line" is literal in finance copy


# ---------------------------------------- codex r2 regressions
def test_were_not_period_form_still_counts(tmp_path):
    root = _prose_repo(tmp_path, "were")
    (root / "app" / "page.tsx").write_text(
        "export default () => <p>We're not a chatbot. We're a teammate.</p>;\n"
    )
    assert us.survey(root)["copy_tells"]["not_x_but_y"]["count"] == 1


def test_keyboard_key_tokens_do_not_hide_copy_module_prose(tmp_path):
    root = _prose_repo(tmp_path, "kbd")
    (root / "content" / "help.ts").write_text(
        "export const tip = 'Use <Tab> to continue. What nobody tells you about billing';\n"
    )
    assert us.survey(root)["copy_tells"]["faux_insight"]["count"] == 1


# ---------------------------------------- codex r3 regression
def test_template_inner_text_in_copy_module_is_scanned(tmp_path):
    # attrs inside the tag stay invisible; the INNER text is rendered copy and must fire
    root = _prose_repo(tmp_path, "tmpl-inner")
    (root / "content" / "tips.ts").write_text(
        "export const tip = '<div data-headline=\"ignore\">What nobody tells you about billing</div>';\n"
    )
    ct = us.survey(root)["copy_tells"]
    assert ct["faux_insight"]["count"] == 1, ct["faux_insight"]


def test_dialog_template_attrs_stay_invisible(tmp_path):
    # codex r4 nit: less-common HTML elements route to the tag-first path too
    root = _prose_repo(tmp_path, "dlg")
    (root / "content" / "modal.ts").write_text(
        'export const tip = "<dialog data-headline=\\"What nobody tells you about billing\\">OK</dialog>";\n'
    )
    assert us.survey(root)["copy_tells"]["faux_insight"]["count"] == 0


# ---------------------------------------- genesis dogfood finding (BRO-2196)
def test_block_comment_continuation_lines_are_not_copy(tmp_path):
    # a multi-line {/* … */} comment's middle lines carry no marker prefix; they are not UI copy —
    # and blanking them must not shift the line numbers of real sites below
    root = _prose_repo(tmp_path, "blockcmt")
    (root / "app" / "page.tsx").write_text(
        "export default function Home() {\n"
        "  return (\n"
        "    <main>\n"
        "      {/* the scroller pins to the bottom while streaming and\n"
        "          returns toward the newest — translateY past the edge, a supercharged\n"
        "          trick — see BRO-1590 for the running signal */}\n"
        "      <p>Model locked — session running.</p>\n"
        "    </main>\n"
        "  );\n"
        "}\n"
    )
    ct = us.survey(root)["copy_tells"]
    assert ct["em_dash"]["count"] == 1                      # only the real UI string
    assert ct["em_dash"]["sites"][0].endswith(":7")          # line numbers preserved
    assert ct["buzzwords"]["count"] == 0                     # "supercharged" lived in the comment


def test_block_comment_edges_unterminated_and_whole_file_scans(tmp_path):
    # codex 0.2.1 blockers: unterminated /* at EOF; whole-file scans must read blanked text too
    root = _prose_repo(tmp_path, "blockedge")
    (root / "app" / "page.tsx").write_text(
        "export default function A() {\n"
        "  return (\n"
        "    <main>\n"
        "      {/* No setup.\n"
        "          No config.\n"
        "          Just code. */}\n"
        "      {/* It's not a chatbot. It's a teammate. */}\n"
        "      <p>No lock-in. No seats. Just usage.</p>\n"
        "    </main>\n"
        "  );\n"
        "}\n"
        "/*\nsupercharged\n"
    )
    ct = us.survey(root)["copy_tells"]
    assert ct["negative_listing"]["count"] == 1              # the real <p>, not the comment
    assert ct["negative_listing"]["sites"][0].endswith(":8")  # line math on blanked text
    assert ct["not_x_but_y"]["count"] == 0                    # comment-only contrast never counts
    assert ct["buzzwords"]["count"] == 0                      # unterminated trailing comment blanked


def test_template_literal_comment_markers_documented_tradeoff(tmp_path):
    # Lexical-blind blanking eats string CONTENT that contains literal /* */ markers — the accepted
    # false negative (preferred over counting comment prose as copy). This test pins the choice.
    root = _prose_repo(tmp_path, "tmpl-cmt")
    (root / "content" / "guide.ts").write_text(
        "export const tip = `\n/*\nWhat nobody tells you about billing\n*/\n`;\n"
    )
    assert us.survey(root)["copy_tells"]["faux_insight"]["count"] == 0
