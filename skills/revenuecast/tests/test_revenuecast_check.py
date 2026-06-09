"""Unit tests for revenuecast_check — the deterministic Kleos doctor.

Each test pins one canon gate (G1-G7) so a regression in the gate logic is caught.
The example manifest must PASS; each FAIL case mutates exactly one field so the
gate that fires is unambiguous. Pure-stdlib (no pyyaml required — fixtures are
built as dicts and round-tripped through JSON, which load_manifest also accepts).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revenuecast_check as kc  # noqa: E402


# --- a minimal manifest that passes every required gate ----------------------

def _good() -> dict:
    return {
        "capability": "autonomous agentic dev under control-systems governance",
        "brand": {"name": "arcan-studio", "gloss": "watch agents ship safely, then run it yourself"},
        "distribute": {"owned_channel": "email + arcan-circle",
                       "surfaces": ["youtube-shorts", "reels", "tiktok", "x"]},
        "offer_ladder": [
            {"tier": "T0", "kind": "free", "price": "$0"},
            {"tier": "T1", "kind": "paid", "price": "$27 one-time"},
            {"tier": "spine", "kind": "recurring", "price": "$49/mo", "billing": "annual"},
        ],
        "moat": {"primary": "agency-proof"},
        "governance": {
            "disclosure_labeling": True,
            "likeness_firewall": True,
            "earnings_claims_substantiated": True,
            "spend_cap": "$25/day",
            "platform_diversification": 4,
        },
        "self_improvement": {"claimed": False, "mechanism_built": False, "measured": False},
        "kpis": {"validated": {}, "imported": {"ltv": "$1800 (unvalidated)"}},
    }


def _statuses(manifest: dict, strict: bool = False) -> dict[str, str]:
    return {r["gate"]: r["status"] for r in kc.run_gates(manifest, strict=strict)}


def _failed(manifest: dict, strict: bool = False) -> list[str]:
    return [r["gate"] for r in kc.run_gates(manifest, strict=strict)
            if r["required"] and r["status"] == kc.FAIL]


# --- the happy path ----------------------------------------------------------

def test_good_manifest_passes_all_required_gates():
    assert _failed(_good()) == []


def test_good_manifest_passes_under_strict():
    assert _failed(_good(), strict=True) == []


def test_shipped_example_manifest_passes():
    """The real template artifact must pass (it doubles as the L2 instance)."""
    example = Path(__file__).resolve().parents[1] / "templates" / "revenuecast.manifest.example.yaml"
    data, err = kc.load_manifest(example)
    assert err is None, err
    assert _failed(data) == [], "shipped example manifest must pass revenuecast_check"


# --- G1 identity -------------------------------------------------------------

def test_g1_missing_gloss_fails():
    m = _good()
    del m["brand"]["gloss"]
    assert "G1" in _failed(m)


def test_g1_missing_capability_fails():
    m = _good()
    del m["capability"]
    assert "G1" in _failed(m)


# --- G2 offer ladder ---------------------------------------------------------

def test_g2_no_recurring_tier_fails():
    m = _good()
    m["offer_ladder"] = [
        {"tier": "T0", "kind": "free", "price": "$0"},
        {"tier": "T1", "kind": "paid", "price": "$27"},
    ]
    assert "G2" in _failed(m)


def test_g2_recurring_detected_from_price_suffix():
    m = _good()
    # drop explicit kind/billing; rely on "/mo" detection
    m["offer_ladder"] = [
        {"tier": "T0", "price": "free"},
        {"tier": "T1", "price": "$27 one-time"},
        {"tier": "spine", "price": "$49/mo"},
    ]
    assert "G2" not in _failed(m)


def test_g2_empty_ladder_fails():
    m = _good()
    m["offer_ladder"] = []
    assert "G2" in _failed(m)


# --- G3 own-the-audience -----------------------------------------------------

def test_g3_missing_owned_channel_fails():
    m = _good()
    del m["distribute"]["owned_channel"]
    assert "G3" in _failed(m)


# --- G4 moat -----------------------------------------------------------------

def test_g4_prompts_moat_fails():
    m = _good()
    m["moat"]["primary"] = "prompts"
    assert "G4" in _failed(m)


def test_g4_templates_moat_fails():
    m = _good()
    m["moat"]["primary"] = "templates"
    assert "G4" in _failed(m)


def test_g4_noncanonical_moat_warns_not_fails():
    m = _good()
    m["moat"]["primary"] = "secret-sauce"
    st = _statuses(m)
    assert st["G4"] == kc.WARN
    assert "G4" not in _failed(m)


# --- G5 governance -----------------------------------------------------------

def test_g5_missing_likeness_firewall_fails():
    m = _good()
    del m["governance"]["likeness_firewall"]
    assert "G5" in _failed(m)


def test_g5_likeness_firewall_false_fails():
    m = _good()
    m["governance"]["likeness_firewall"] = False
    assert "G5" in _failed(m)


def test_g5_too_few_platforms_fails():
    m = _good()
    m["governance"]["platform_diversification"] = 2
    assert "G5" in _failed(m)


# --- G6 Ritual-vs-Substance (the load-bearing review fix) --------------------

def test_g6_self_improvement_claimed_without_mechanism_fails():
    m = _good()
    m["self_improvement"] = {"claimed": True, "mechanism_built": False, "measured": False}
    assert "G6" in _failed(m)


def test_g6_self_improvement_claimed_built_but_unmeasured_fails():
    m = _good()
    m["self_improvement"] = {"claimed": True, "mechanism_built": True, "measured": False}
    assert "G6" in _failed(m)


def test_g6_self_improvement_claimed_built_and_measured_passes():
    m = _good()
    m["self_improvement"] = {"claimed": True, "mechanism_built": True, "measured": True}
    assert "G6" not in _failed(m)


def test_g6_not_claimed_passes():
    m = _good()
    m["self_improvement"] = {"claimed": False}
    assert "G6" not in _failed(m)


# --- G7 KPI honesty ----------------------------------------------------------

def test_g7_benchmarks_without_imported_block_warns_then_fails_strict():
    m = _good()
    # remove the imported block but keep a benchmark-shaped number elsewhere
    m["kpis"] = {"validated": {"note": "target 70% completion and $1800 LTV"}}
    st = _statuses(m, strict=False)
    assert st["G7"] == kc.WARN
    assert "G7" not in _failed(m, strict=False)
    assert "G7" in _failed(m, strict=True)


def test_g7_imported_block_present_passes():
    m = _good()
    assert _statuses(m)["G7"] == kc.PASS


# --- loader ------------------------------------------------------------------

def test_load_manifest_accepts_json(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps(_good()), encoding="utf-8")
    data, err = kc.load_manifest(p)
    assert err is None
    assert data["brand"]["name"] == "arcan-studio"


def test_load_manifest_reports_missing_file(tmp_path):
    data, err = kc.load_manifest(tmp_path / "nope.yaml")
    assert data is None and err
