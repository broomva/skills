"""Tests for unslop_gate.py — the crafted floor in both polarities, waivers, strict, evidence."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import unslop_gate as ug
import unslop_survey as us
from helpers import png_bytes

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "unslop_gate.py"


def _run(repo: Path, **kw) -> dict:
    manifest = kw.pop("manifest", None) or us.survey(repo)
    gate = ug.Gate(manifest, repo, kw.pop("waivers", {"waivers": []}), kw.pop("profile", "auto"), kw.pop("strict", False), kw.pop("evidence_dir", None), kw.pop("no_render", False))
    res = gate.run()
    return {r.check: r for r in res}


# ---------------------------------------------------------------- polarity
def test_sloppy_repo_fails_on_the_named_checks(sloppy_repo):
    r = _run(sloppy_repo, no_render=True)
    fails = {k for k, v in r.items() if v.status == "FAIL"}
    assert {"direction.authored", "fonts.deliberate", "icons.single-system", "tokens.color", "copy.em-dash",
            "copy.emoji", "copy.checkmark-bullets", "copy.not-x-but-y", "substance.legal", "substance.loading-states",
            "substance.placeholders", "substance.stock-imagery", "substance.product-evidence", "motion.reduced-motion"} <= fails
    assert r["substance.legal"].detail.startswith("[persuade]")
    assert r["substance.testimonials"].status == "WARN" and r["substance.pricing"].status == "WARN"
    assert r["evidence.render"].status == "WARN"  # --no-render is explicit, not silent
    assert r["detector.clean"].status == "WARN"   # detector not run → WARN, never silent PASS


def test_crafted_repo_clears_the_floor(crafted_repo, evidence_dir):
    r = _run(crafted_repo, evidence_dir=evidence_dir)
    fails = {k: v.detail for k, v in r.items() if v.status == "FAIL"}
    assert fails == {}, fails
    assert r["direction.authored"].status == "PASS"
    assert r["fonts.deliberate"].status == "PASS"           # self-hosted primary; system stack declared in DESIGN.md
    assert r["icons.single-system"].status == "PASS"        # lucide is a stated decision in DESIGN.md
    assert r["substance.legal"].status == "PASS"
    assert r["substance.loading-states"].status == "PASS"
    assert r["substance.placeholders"].status == "PASS"
    assert r["motion.reduced-motion"].status == "PASS"
    assert r["evidence.render"].status == "PASS" and "4/4 page routes" in r["evidence.render"].detail
    assert r["substance.product-evidence"].status == "SKIP"  # operate profile


def test_crafted_repo_as_persuade_requires_product_evidence(crafted_repo, evidence_dir):
    r = _run(crafted_repo, evidence_dir=evidence_dir, profile="persuade")
    assert r["substance.product-evidence"].status == "PASS"  # video + local screenshot present


# ---------------------------------------------------------------- waivers
def test_waiver_flips_fail_to_pass_and_is_marked(sloppy_repo):
    waivers = {"waivers": [
        {"check": "copy.emoji", "reason": "brand voice uses one emoji in the hero, approved by the founder"},
        {"check": "fonts.deliberate", "value": "inter", "reason": "Inter chosen for the docs surface after review; self-hosted"},
    ]}
    r = _run(sloppy_repo, waivers=waivers, no_render=True)
    assert r["copy.emoji"].status == "PASS" and r["copy.emoji"].waived and "WAIVED" in r["copy.emoji"].detail
    # inter waived but space grotesk is not → still FAIL and names the unwaived face
    assert r["fonts.deliberate"].status == "FAIL" and "space grotesk" in r["fonts.deliberate"].detail and "inter" not in r["fonts.deliberate"].detail.split("primary:")[1].split("—")[0]


def test_waiver_without_reason_is_rejected(tmp_path):
    w = tmp_path / "w.json"
    w.write_text(json.dumps({"waivers": [{"check": "copy.emoji", "reason": "ok"}]}))
    with pytest.raises(SystemExit):
        ug.load_waivers(w)


def test_detector_rule_waiver(sloppy_repo):
    manifest = us.survey(sloppy_repo)
    manifest["detector"] = us.summarize_detector([
        {"antipattern": "overused-font", "severity": "warning", "file": "a", "line": 1},
        {"antipattern": "gradient-text", "severity": "warning", "file": "b", "line": 2},
    ])
    r = _run(sloppy_repo, manifest=manifest, no_render=True)
    assert r["detector.clean"].status == "FAIL" and "overused-font" in r["detector.clean"].detail
    r2 = _run(sloppy_repo, manifest=manifest, no_render=True, waivers={"waivers": [
        {"check": "detector.rule", "value": "overused-font", "reason": "font decision recorded in DESIGN.md, self-hosted"},
        {"check": "detector.rule", "value": "gradient-text", "reason": "single hero gradient is the committed visual world"},
    ]})
    assert r2["detector.clean"].status == "PASS" and r2["detector.clean"].waived


def test_detector_clean_passes_with_only_advisory(crafted_repo, evidence_dir):
    manifest = us.survey(crafted_repo)
    manifest["detector"] = us.summarize_detector([{"antipattern": "em-dash-overuse", "severity": "advisory", "advisory": True, "file": "a", "line": 1}])
    r = _run(crafted_repo, manifest=manifest, evidence_dir=evidence_dir)
    assert r["detector.clean"].status == "PASS" and "1 advisory" in r["detector.clean"].detail


# ---------------------------------------------------------------- strict / evidence
def test_strict_promotes_warn_to_fail(crafted_repo, evidence_dir):
    manifest = us.survey(crafted_repo)  # detector not run → WARN
    r = _run(crafted_repo, manifest=manifest, evidence_dir=evidence_dir, strict=True)
    assert r["detector.clean"].status == "FAIL"


def test_render_evidence_requires_both_widths_and_non_blank(crafted_repo, tmp_path):
    ev = tmp_path / "ev"
    ev.mkdir()
    (ev / "index-1280.png").write_bytes(png_bytes(1280))
    r = _run(crafted_repo, evidence_dir=ev)
    assert r["evidence.render"].status == "FAIL" and "mobile=0" in r["evidence.render"].detail
    (ev / "index-390.png").write_bytes(b"\x89PNG")  # blank/too small
    r = _run(crafted_repo, evidence_dir=ev)
    assert r["evidence.render"].status == "FAIL"
    (ev / "index-390.png").write_bytes(png_bytes(390))
    r = _run(crafted_repo, evidence_dir=ev)
    assert r["evidence.render"].status == "WARN"  # index covered at both widths; ledger/terms/privacy are not
    assert "1/4 page routes" in r["evidence.render"].detail
    # a width present globally but never for the same route as the other width → FAIL (no route has both)
    ev2 = tmp_path / "ev2"
    ev2.mkdir()
    (ev2 / "index-1280.png").write_bytes(png_bytes(1280))
    (ev2 / "ledger-390.png").write_bytes(png_bytes(390))
    r = _run(crafted_repo, evidence_dir=ev2)
    assert r["evidence.render"].status == "FAIL" and "no page route has both widths" in r["evidence.render"].detail


def test_missing_evidence_dir_is_fail_unless_no_render(crafted_repo):
    r = _run(crafted_repo)
    assert r["evidence.render"].status == "FAIL"
    r = _run(crafted_repo, no_render=True)
    assert r["evidence.render"].status == "WARN"


# ---------------------------------------------------------------- CLI
def test_cli_exit_codes_and_json(sloppy_repo, crafted_repo, evidence_dir, tmp_path):
    out = tmp_path / "gate.json"
    r = subprocess.run([sys.executable, str(SCRIPT), str(sloppy_repo), "--no-render", "--json", str(out), "--quiet"], capture_output=True, text=True)
    assert r.returncode == 1
    j = json.loads(out.read_text())
    assert j["schema"] == "unslop-gate/1" and j["clear"] is False and j["profile"] == "persuade"

    r = subprocess.run([sys.executable, str(SCRIPT), str(crafted_repo), "--evidence", str(evidence_dir)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "CLEAR" in r.stdout and "NOT CLEAR" not in r.stdout


def test_cli_manifest_roundtrip(sloppy_repo, tmp_path):
    m = tmp_path / "m.json"
    m.write_text(json.dumps(us.survey(sloppy_repo)))
    r = subprocess.run([sys.executable, str(SCRIPT), str(sloppy_repo), "--manifest", str(m), "--no-render", "--quiet"], capture_output=True, text=True)
    assert r.returncode == 1


def test_cli_bad_json_inputs_exit_2(sloppy_repo, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    r = subprocess.run([sys.executable, str(SCRIPT), str(sloppy_repo), "--manifest", str(bad), "--no-render", "--quiet"], capture_output=True, text=True)
    assert r.returncode == 2 and "not readable JSON" in r.stderr
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"schema": "something-else/9"}))
    r = subprocess.run([sys.executable, str(SCRIPT), str(sloppy_repo), "--manifest", str(wrong), "--no-render", "--quiet"], capture_output=True, text=True)
    assert r.returncode == 2 and "unslop-survey/1" in r.stderr
    w = tmp_path / "w.json"
    w.write_text("[]")
    r = subprocess.run([sys.executable, str(SCRIPT), str(sloppy_repo), "--waivers", str(w), "--no-render", "--quiet"], capture_output=True, text=True)
    assert r.returncode == 2 and "waivers" in r.stderr
    w.write_text(json.dumps({"waivers": [{"check": "copy.emoji", "reason": "short"}]}))
    r = subprocess.run([sys.executable, str(SCRIPT), str(sloppy_repo), "--waivers", str(w), "--no-render", "--quiet"], capture_output=True, text=True)
    assert r.returncode == 2 and "reason" in r.stderr


# ------------------------------------------- copy.slop-patterns (after no-ai-slop, BRO-2195)
def _slop_pattern_repo(tmp_path):
    root = tmp_path / "prose-gate"
    (root / "app").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"next": "15", "react": "19"}}))
    (root / "app" / "page.tsx").write_text("""
export default function Home() {
  return (
    <main>
      <h1>The future of shipping is here.</h1>
      <p>Here's what nobody tells you about scaling.</p>
      <p>Experts agree that our approach works.</p>
    </main>
  );
}
""")
    return root


def test_gate_slop_patterns_fails_at_three_sites(tmp_path):
    r = _run(_slop_pattern_repo(tmp_path), no_render=True)
    res = r["copy.slop-patterns"]
    assert res.status == "FAIL"
    assert "fake_profound" in res.detail and "weasel_attribution" in res.detail
    assert any(e.startswith("[faux_insight] ") and ":" in e for e in res.evidence)  # pattern-tagged file:line


def test_gate_slop_patterns_warn_waiver_and_backcompat(tmp_path, sloppy_repo, crafted_repo):
    # sloppy fixture carries exactly one prose-pattern site ("the future is here") → WARN, never silent
    assert _run(sloppy_repo, no_render=True)["copy.slop-patterns"].status == "WARN"
    # crafted fixture is clean → PASS
    assert _run(crafted_repo, no_render=True)["copy.slop-patterns"].status == "PASS"
    # a reasoned waiver turns the FAIL into a waived PASS
    w = {"waivers": [{"check": "copy.slop-patterns", "reason": "editorial voice reviewed by a human, kept deliberately"}]}
    res = _run(_slop_pattern_repo(tmp_path), no_render=True, waivers=w)["copy.slop-patterns"]
    assert res.status == "PASS" and res.waived
    # a 0.1.x manifest (no prose keys) still gates: PASS "none", not a crash
    m = us.survey(crafted_repo)
    m["copy_tells"] = {k: m["copy_tells"][k] for k in ("em_dash", "emoji", "not_x_but_y", "checkmark_bullets", "buzzwords")}
    assert _run(crafted_repo, no_render=True, manifest=m)["copy.slop-patterns"].status == "PASS"


def test_gate_slop_patterns_counts_distinct_sites_not_key_hits(tmp_path):
    # one line matching three patterns is ONE site → WARN, never FAIL (codex r1 blocker)
    root = tmp_path / "one-line"
    (root / "app").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"next": "15", "react": "19"}}))
    (root / "app" / "page.tsx").write_text(
        "export default () => <p>Here's the thing: the best part: it's that simple.</p>;\n"
    )
    res = _run(root, no_render=True)["copy.slop-patterns"]
    assert res.status == "WARN", res.detail
    assert res.detail.startswith("1 prose-slop site(s)")
