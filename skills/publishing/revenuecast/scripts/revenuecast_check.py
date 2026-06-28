#!/usr/bin/env python3
"""revenuecast_check — the deterministic "Kleos doctor".

Garry-Tan-for-revenue: *a capability that doesn't pass all gates is not a revenue
engine — it's just content that happens to exist today.* This script makes the
Kleos design canon (skills/revenuecast/references/design-canon.md §9) machine-checkable.

Given a Kleos engine-instance manifest (YAML or JSON), it runs the canon gates and
reports PASS / WARN / FAIL per gate, exiting non-zero when a required gate fails.

The gates are NOT bureaucratic presence-checks — each one encodes a load-bearing
lesson the research + P20 review surfaced, and each one closes a specific failure
mode the workspace's own CLAUDE.md cares about:

  G1 identity        capability + brand.name + brand.gloss  (the name must self-explain)
  G2 ladder          >=1 free + >=1 paid + >=1 recurring     (recurring = the durable spine)
  G3 owned-audience  distribute.owned_channel present        (platform reach is rented)
  G4 moat            moat.primary not in {prompts,templates} (prompts leak in days)
  G5 governance      disclosure + likeness-firewall +        (FTC v. Air AI / EU Art.50 /
                     earnings-substantiation + spend-cap +    NO FAKES — the seller is
                     platform-diversification>=3+owned         the entity in scope)
  G6 substance       self_improvement.claimed => built+measured  (Ritual-vs-Substance:
                                                                   no incantation claims)
  G7 kpi-honesty     benchmark numbers => kpis.imported block  (consumer benchmarks are
                                                                  unvalidated for B2D)

Required gates (gate the exit code): G1-G6. G7 is WARN-by-default and promoted to
required under --strict. Pure-stdlib + optional pyyaml; deterministic; zero network.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
LEAKABLE_MOATS = {"prompts", "prompt", "templates", "template", "prompt-pack", "promptpack"}
VALID_MOATS = {
    "sequencing", "operational-sequencing", "operational_sequencing",
    "recency", "recency-as-service", "recency_as_service",
    "community", "agency-proof", "agency_proof", "agencyproof",
    "compliance", "survival", "compliance-survival",
    "closed-execution", "closed_execution", "closedexecution",
}
GOV_FIELDS = (
    "disclosure_labeling", "likeness_firewall",
    "earnings_claims_substantiated", "spend_cap", "platform_diversification",
)
# Numbers that smell like imported conversion benchmarks (KPI-honesty trigger).
_BENCH_RE = re.compile(
    r"\b\d{1,3}\s?%|\$\s?\d|\bLTV\b|\bCAC\b|\bchurn\b|\bretention\b|\bconversion\b",
    re.IGNORECASE,
)


# --- manifest loading --------------------------------------------------------

def load_manifest(path: Path) -> tuple[dict | None, str | None]:
    """Load YAML (preferred) or JSON. Returns (data, error)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return None, f"cannot read {path}: {e}"
    # try YAML first (manifests are authored as YAML)
    try:
        import yaml  # optional
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data, None
    except Exception:
        pass
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data, None
        return None, "manifest top-level is not a mapping"
    except Exception as e:
        return None, (
            "could not parse as YAML or JSON "
            f"({e}); install pyyaml for YAML manifests"
        )


# --- helpers -----------------------------------------------------------------

def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1", "on")
    return False


def _present(v) -> bool:
    """Non-empty: a non-blank string, a non-zero number, True, or a non-empty list/dict."""
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, bool):
        return v
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def _ladder_tiers(manifest: dict) -> list[dict]:
    ladder = manifest.get("offer_ladder") or []
    return [t for t in ladder if isinstance(t, dict)]


def _tier_kinds(tiers: list[dict]) -> set[str]:
    """Classify each tier into {free, paid, recurring} from its price/cadence fields."""
    kinds: set[str] = set()
    for t in tiers:
        price = str(t.get("price") or t.get("price_band") or "").lower()
        cadence = str(t.get("cadence") or t.get("billing") or "").lower()
        kind = str(t.get("kind") or "").lower()
        is_recurring = (
            "recurring" in kind or "/mo" in price or "/yr" in price
            or "month" in price or "year" in price or "annual" in (price + cadence)
            or cadence in ("monthly", "yearly", "annual", "recurring")
        )
        is_free = (
            "free" in kind or price in ("", "$0", "0", "free")
            or "free" in price or "$0" in price
        )
        if is_recurring:
            kinds.add("recurring")
        elif is_free:
            kinds.add("free")
        else:
            kinds.add("paid")
    return kinds


def _platform_count(manifest: dict) -> int:
    gov = manifest.get("governance") or {}
    pd = gov.get("platform_diversification")
    if isinstance(pd, int):
        return pd
    # else count distribute.surfaces
    dist = manifest.get("distribute") or {}
    surfaces = dist.get("surfaces") or []
    if isinstance(surfaces, list):
        return len(surfaces)
    if isinstance(pd, str):
        m = re.search(r"\d+", pd)
        if m:
            return int(m.group())
    return 0


def _manifest_mentions_benchmarks(manifest: dict) -> bool:
    """Does the manifest contain benchmark-shaped numbers outside the imported block?"""
    probe = dict(manifest)
    probe.pop("kpis", None)
    blob = json.dumps(probe, default=str)
    return bool(_BENCH_RE.search(blob))


# --- the gates ---------------------------------------------------------------

def run_gates(manifest: dict, *, strict: bool) -> list[dict]:
    results: list[dict] = []

    def add(gate, label, status, detail, required=True):
        results.append({"gate": gate, "label": label, "status": status,
                        "detail": detail, "required": required})

    # G1 — identity (the name must self-explain)
    brand = manifest.get("brand") or {}
    missing = [k for k, v in (
        ("capability", manifest.get("capability")),
        ("brand.name", brand.get("name")),
        ("brand.gloss", brand.get("gloss")),
    ) if not _present(v)]
    if missing:
        add("G1", "Identity", FAIL, f"missing: {', '.join(missing)} (canon §0/§9.1)")
    else:
        add("G1", "Identity", PASS, f"brand={brand.get('name')} + gloss present")

    # G2 — ladder (free + paid + recurring; recurring is the durable spine)
    tiers = _ladder_tiers(manifest)
    kinds = _tier_kinds(tiers)
    need = {"free", "paid", "recurring"}
    if not tiers:
        add("G2", "Offer ladder", FAIL, "no offer_ladder (canon §4)")
    elif not need.issubset(kinds):
        add("G2", "Offer ladder", FAIL,
            f"ladder has {sorted(kinds) or 'none'}; needs free + paid + recurring "
            "(recurring = the durable spine, +89% LTV)")
    else:
        add("G2", "Offer ladder", PASS, f"{len(tiers)} tiers spanning free/paid/recurring")

    # G3 — own-the-audience (platform reach is rented and revocable)
    dist = manifest.get("distribute") or {}
    if _present(dist.get("owned_channel")):
        add("G3", "Own-the-audience", PASS, f"owned_channel={dist.get('owned_channel')}")
    else:
        add("G3", "Own-the-audience", FAIL,
            "distribute.owned_channel missing — platform reach is rented "
            "(YouTube wiped $10M/yr in one 2026 sweep). Canon §9.3")

    # G4 — moat (prompts/templates are not a moat)
    moat = manifest.get("moat") or {}
    primary = str(moat.get("primary") or "").strip().lower()
    if not primary:
        add("G4", "Moat", FAIL, "moat.primary missing (canon §3)")
    elif primary in LEAKABLE_MOATS:
        add("G4", "Moat", FAIL,
            f"moat.primary='{primary}' is leakable (clones in days). Pick a "
            "defensible layer: sequencing/recency/community/agency-proof/compliance/closed-execution")
    elif primary not in VALID_MOATS:
        add("G4", "Moat", WARN,
            f"moat.primary='{primary}' is non-canonical — verify it is genuinely "
            "non-leakable (canon §3)", required=False)
    else:
        add("G4", "Moat", PASS, f"moat.primary={primary} (defensible)")

    # G5 — governance / compliance pillar (the seller is the entity in scope)
    gov = manifest.get("governance") or {}
    gov_missing = [f for f in GOV_FIELDS if not _present(gov.get(f))]
    plat = _platform_count(manifest)
    gov_problems = list(gov_missing)
    # the three boolean guardrails must be affirmatively true
    for f in ("disclosure_labeling", "likeness_firewall", "earnings_claims_substantiated"):
        if _present(gov.get(f)) and not _truthy(gov.get(f)):
            gov_problems.append(f"{f}=false")
    if plat < 3:
        gov_problems.append(f"platform_diversification={plat} (<3 + owned)")
    if gov_problems:
        add("G5", "Governance/compliance", FAIL,
            f"{', '.join(gov_problems)} — FTC v. Air AI / EU Art.50 / NO FAKES. Canon §5")
    else:
        add("G5", "Governance/compliance", PASS,
            f"disclosure + likeness-firewall + earnings-substantiation + spend-cap + {plat} platforms")

    # G6 — Ritual-vs-Substance (no self-improving claim without built+measured mechanism)
    si = manifest.get("self_improvement") or {}
    claimed = _truthy(si.get("claimed"))
    if not claimed:
        add("G6", "Substance (RvS)", PASS, "no self-improvement claimed — honest")
    elif _truthy(si.get("mechanism_built")) and _truthy(si.get("measured")):
        add("G6", "Substance (RvS)", PASS, "self-improvement claimed AND built AND measured")
    else:
        gaps = []
        if not _truthy(si.get("mechanism_built")):
            gaps.append("mechanism_built=false")
        if not _truthy(si.get("measured")):
            gaps.append("measured=false")
        add("G6", "Substance (RvS)", FAIL,
            f"claims self-improvement but {', '.join(gaps)} — that is an incantation, "
            "not control (CLAUDE.md §Ritual-vs-Substance). Canon §6")

    # G7 — KPI honesty (benchmark numbers must be quarantined into kpis.imported)
    kpis = manifest.get("kpis") or {}
    has_imported_block = "imported" in kpis
    mentions_bench = _manifest_mentions_benchmarks(manifest)
    if not mentions_bench:
        add("G7", "KPI honesty", PASS, "no benchmark-shaped numbers to quarantine",
            required=strict)
    elif has_imported_block:
        add("G7", "KPI honesty", PASS, "benchmark numbers present + kpis.imported block declared",
            required=strict)
    else:
        add("G7", "KPI honesty",
            FAIL if strict else WARN,
            "benchmark numbers present but no kpis.imported block — consumer-niche "
            "benchmarks are UNVALIDATED for your buyer (canon §6 KPI honesty)",
            required=strict)

    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="revenuecast-check",
        description="Validate a Kleos engine-instance manifest against the design-canon gates.")
    ap.add_argument("manifest", help="path to revenuecast.manifest.yaml (or .json)")
    ap.add_argument("--strict", action="store_true",
                    help="promote G7 (KPI honesty) to a required gate")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    path = Path(args.manifest)
    manifest, err = load_manifest(path)
    if err:
        print(f"[revenuecast] {err}", file=sys.stderr)
        return 2

    results = run_gates(manifest, strict=args.strict)
    failed = [r for r in results if r["required"] and r["status"] == FAIL]
    warned = [r for r in results if r["status"] == WARN]
    disp = manifest.get("brand", {}).get("name") or path.name

    if args.json:
        print(json.dumps({"instance": disp, "results": results,
                          "failed": len(failed), "warned": len(warned)}, indent=2))
        return 1 if failed else 0

    glyph = {PASS: "✓", WARN: "▲", FAIL: "✗"}
    print(f"revenuecast engine-instance check — {disp}\n")
    for r in results:
        req = "" if r["required"] else " (advisory)"
        print(f"  {glyph[r['status']]} {r['gate']} {r['label']:<22} {r['status']:<4} {r['detail']}{req}")
    print()
    if failed:
        print(f"✗ FAIL — {len(failed)} required gate(s) failed; {len(warned)} warning(s). "
              "Not a revenue engine yet — just content that happens to exist today.")
        return 1
    print(f"✓ PASS — all required gates green ({len(warned)} advisory warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
