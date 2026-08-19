#!/usr/bin/env python3
"""unslop_gate — the crafted-floor gate. Exit 0 iff the repo clears the floor.

Reads an unslop_survey manifest (or runs the survey), optionally the impeccable
detector findings embedded in it, a render-evidence directory, and a waivers
file, and emits PASS / WARN / FAIL / SKIP per check.

The gate checks PROPERTIES, not a ban-list:

  direction.authored        a DESIGN.md / PRODUCT.md exists — the root was decided
  detector.clean            impeccable primary findings == 0 (or each waived with a reason)
  fonts.deliberate          no AI-default web face as the primary face; system stack only if declared deliberate
  icons.single-system       one icon library; lucide-only needs a stated decision
  tokens.color/radius/shadow  a vocabulary, not drift (distinct-value thresholds)
  copy.em-dash / emoji / checkmark-bullets / not-x-but-y / buzzwords
  substance.legal           terms + privacy routes exist AND are linked (persuade profile: FAIL; operate: WARN)
  substance.loading-states  async surfaces carry loading state (coverage ≥ 0.8)
  substance.error-states    async surfaces carry error handling (coverage ≥ 0.5, WARN)
  substance.placeholders    no lorem / John Doe / Acme / TODO-in-copy / stock imagery on a persuade surface
  substance.testimonials    testimonials present → human must verify real (WARN until waived "verified real")
  substance.pricing         three-tier scaffold suspected → WARN
  substance.product-evidence  persuade surface shows the real product (video / local screenshots)
  motion.reduced-motion     motion present → prefers-reduced-motion respected
  evidence.render           screenshots at desktop + mobile widths exist and are non-blank (P11)

Waivers (JSON): {"waivers": [{"check": "copy.em-dash", "reason": "≥20 chars", "value": "optional"}]}
A waiver without a real reason is rejected — the floor is waivable, not silent.

    python3 unslop_gate.py <repo> [--manifest M | --detect] [--evidence DIR] [--waivers FILE]
                           [--profile auto|persuade|operate] [--strict] [--no-render] [--json OUT]

Exit codes: 0 clear · 1 one or more FAIL · 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    import unslop_survey  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover
    unslop_survey = None  # type: ignore


def _lead_int(value: str) -> int:
    m = re.match(r"(\d+)", value or "")
    return int(m.group(1)) if m else 0

# Single source of truth for the face lists lives in unslop_survey (dated there); fall back only if it is missing.
AI_DEFAULT_WEB_FONTS = getattr(unslop_survey, "AI_DEFAULT_WEB_FONTS", {"inter", "geist", "space grotesk", "roboto"})
SYSTEM_STACK = getattr(unslop_survey, "SYSTEM_STACK", {"system-ui", "-apple-system", "arial", "helvetica", "sans-serif"})
MIN_REASON = 20
MIN_SCREENSHOT_BYTES = 8_000


@dataclass
class Result:
    check: str
    status: str            # PASS | WARN | FAIL | SKIP
    detail: str
    waived: bool = False
    evidence: list = field(default_factory=list)


class Gate:
    def __init__(self, manifest: dict, repo: Path, waivers: dict, profile: str, strict: bool, evidence_dir: Path | None, no_render: bool):
        self.m = manifest
        self.repo = repo
        self.waivers = waivers
        self.profile = profile
        self.strict = strict
        self.evidence_dir = evidence_dir
        self.no_render = no_render
        self.results: list[Result] = []
        self.design_text = self._read_design_docs()

    # ------------------------------------------------------------------ utils
    def _read_design_docs(self) -> str:
        out = []
        for name in ("DESIGN.md", "PRODUCT.md"):
            p = self.repo / name
            if p.exists():
                try:
                    out.append(p.read_text(encoding="utf-8", errors="ignore").lower())
                except OSError:
                    pass
        return "\n".join(out)

    def waiver_for(self, check: str, value: str | None = None) -> dict | None:
        for w in self.waivers.get("waivers", []):
            if w.get("check") != check:
                continue
            if value is not None and w.get("value") not in (None, "*", value):
                continue
            return w
        return None

    def add(self, check: str, status: str, detail: str, evidence: list | None = None, value: str | None = None, waivable: bool = True):
        w = self.waiver_for(check, value) if waivable and status in ("FAIL", "WARN") else None
        waived = False
        if w:
            status = "PASS"
            waived = True
            detail = f"{detail} — WAIVED: {w.get('reason')}"
        if self.strict and status == "WARN" and not waived:
            status = "FAIL"
        self.results.append(Result(check, status, detail, waived, evidence or []))

    # ----------------------------------------------------------------- checks
    def run(self) -> list[Result]:
        m = self.m
        s = m.get("substance", {})
        profile = self.profile if self.profile != "auto" else m.get("profile_hint", "unknown")
        persuade = profile == "persuade"

        # direction.authored
        dd = s.get("design_docs", {})
        if dd.get("DESIGN.md") or dd.get("PRODUCT.md"):
            self.add("direction.authored", "PASS", f"design docs present: {', '.join(k for k, v in dd.items() if v)}")
        else:
            self.add("direction.authored", "FAIL", "no DESIGN.md / PRODUCT.md — the direction was never decided; author it (impeccable `document`/`init`) before fixing surfaces")

        # detector.clean
        d = m.get("detector", {})
        st = d.get("status")
        if st == "ok":
            primaries = [f for f in d.get("findings", []) if not f.get("advisory")]
            unwaived = [f for f in primaries if not self.waiver_for("detector.rule", f.get("rule"))]
            if not primaries:
                self.add("detector.clean", "PASS", f"impeccable detector: 0 primary findings ({d.get('advisory_count', 0)} advisory)")
            elif not unwaived:
                self.add("detector.clean", "PASS", f"{len(primaries)} primary findings, all waived by rule", waivable=False)
                self.results[-1].waived = True
            else:
                by = {}
                for f in unwaived:
                    by[f["rule"]] = by.get(f["rule"], 0) + 1
                self.add("detector.clean", "FAIL", f"{len(unwaived)} unwaived primary findings: " + ", ".join(f"{k}×{v}" for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:10]),
                         evidence=[f"{f.get('file')}:{f.get('line')} {f['rule']}" for f in unwaived[:15]], waivable=False)
        elif st in ("unavailable", "error"):
            self.add("detector.clean", "WARN", f"impeccable detector {st}: {d.get('note', '')} — classes A–C were not machine-checked")
        else:
            self.add("detector.clean", "WARN", "detector not run (pass --detect or a manifest produced with --detect)")

        # fonts.deliberate
        fam = m.get("fonts", {}).get("families", {})
        selfhosted = set(m.get("fonts", {}).get("self_hosted", []))
        ai_defaults = [f for f in fam if f in AI_DEFAULT_WEB_FONTS]
        sys_primary = [f for f in fam if f in SYSTEM_STACK]
        if ai_defaults:
            unw = [f for f in ai_defaults if not self.waiver_for("fonts.deliberate", f)]
            if unw:
                self.add("fonts.deliberate", "FAIL", f"AI-default web face(s) as primary: {', '.join(unw)} — decide a face once and declare it at the root (see roots)", value=None, waivable=False)
            else:
                self.add("fonts.deliberate", "PASS", f"default faces waived with reasons: {', '.join(ai_defaults)}", waivable=False)
                self.results[-1].waived = True
        elif sys_primary and not any(k in self.design_text for k in ("system font", "system-ui", "system typography", "system stack", "platform sans", "native font")):
            self.add("fonts.deliberate", "WARN", f"system stack as primary ({', '.join(sys_primary)}) with no stated decision in DESIGN.md/PRODUCT.md — deliberate or default?")
        elif not fam:
            self.add("fonts.deliberate", "WARN", "no font-family declaration found — the browser default is not a decision")
        else:
            note = " (self-hosted)" if selfhosted & set(fam) else ""
            self.add("fonts.deliberate", "PASS", f"primary faces: {', '.join(list(fam)[:4])}{note}")

        # icons.single-system
        icons = m.get("icons", {})
        if len(icons) > 1:
            self.add("icons.single-system", "FAIL", f"mixed icon libraries: {', '.join(f'{k}×{v}' for k, v in icons.items())} — one system, one stroke weight")
        elif icons == {} :
            self.add("icons.single-system", "SKIP", "no icon library imports detected")
        elif "lucide" in icons and "lucide" not in self.design_text:
            self.add("icons.single-system", "WARN", f"lucide only ({icons['lucide']} files) — the shadcn default; state the decision in DESIGN.md or pick a face with character")
        else:
            self.add("icons.single-system", "PASS", f"single icon system: {list(icons)[0]}")

        # tokens.*
        for r in m.get("roots", []):
            if r["kind"] == "color":
                n = _lead_int(r["value"])
                if n > 12:
                    self.add("tokens.color", "FAIL", f"{n} distinct hex literals outside token files ({r['sites']} sites) — palette must live in tokens", evidence=r.get("top_values", []))
                elif n > 0:
                    self.add("tokens.color", "WARN", f"{n} distinct hex literals outside token files ({r['sites']} sites)", evidence=r.get("top_values", []))
                else:
                    self.add("tokens.color", "PASS", "no hard-coded colors outside token files")
            if r["kind"] == "radius":
                n = _lead_int(r["value"])
                self.add("tokens.radius", "FAIL" if n > 8 else ("WARN" if n > 5 else "PASS"), f"{n} distinct radius values — {', '.join(r.get('top_values', [])[:6])}")
            if r["kind"] == "shadow":
                n = _lead_int(r["value"])
                self.add("tokens.shadow", "FAIL" if n > 8 else ("WARN" if n > 5 else "PASS"), f"{n} distinct shadow values — {', '.join(r.get('top_values', [])[:6])}")
        if not any(r["kind"] == "color" for r in m.get("roots", [])):
            self.add("tokens.color", "PASS", "no hard-coded colors outside token files")

        # copy.*
        ct = m.get("copy_tells", {})
        em = ct.get("em_dash", {}).get("count", 0)
        self.add("copy.em-dash", "FAIL" if em >= 3 else ("WARN" if em > 0 else "PASS"), f"{em} em dash line(s) in UI files", evidence=ct.get("em_dash", {}).get("sites", []))
        emo = ct.get("emoji", {}).get("count", 0)
        self.add("copy.emoji", "FAIL" if emo > 0 else "PASS", f"{emo} emoji line(s) in UI files (icons are drawn, not typed)", evidence=ct.get("emoji", {}).get("sites", []))
        ck = ct.get("checkmark_bullets", {}).get("count", 0)
        self.add("copy.checkmark-bullets", "FAIL" if ck > 0 else "PASS", f"{ck} checkmark-bullet line(s)", evidence=ct.get("checkmark_bullets", {}).get("sites", []))
        nx = ct.get("not_x_but_y", {}).get("count", 0)
        self.add("copy.not-x-but-y", "FAIL" if nx > 0 else "PASS", f"{nx} “it's not X, it's Y” construction(s)", evidence=ct.get("not_x_but_y", {}).get("sites", []))
        bz = ct.get("buzzwords", {}).get("count", 0)
        self.add("copy.buzzwords", "WARN" if bz > 2 else "PASS", f"{bz} buzzword line(s)", evidence=ct.get("buzzwords", {}).get("sites", []))

        # substance.legal
        lg = s.get("legal", {})
        have = bool(lg.get("terms_route")) and bool(lg.get("privacy_route"))
        linked = bool(lg.get("terms_linked")) and bool(lg.get("privacy_linked"))
        if have and linked:
            self.add("substance.legal", "PASS", f"terms {lg['terms_route']} + privacy {lg['privacy_route']} exist and are linked")
        else:
            missing = [k for k, v in (("terms", lg.get("terms_route")), ("privacy", lg.get("privacy_route"))) if not v]
            unlinked = [k for k, v in (("terms", lg.get("terms_linked")), ("privacy", lg.get("privacy_linked"))) if not v]
            detail = (f"missing routes: {', '.join(missing)}; " if missing else "") + (f"not linked from UI: {', '.join(unlinked)}" if unlinked else "")
            self.add("substance.legal", "FAIL" if persuade else "WARN", f"[{profile}] {detail} — a real product has a real legal footer (this needs a human/legal owner, not generated text)")

        # substance.loading / error states
        a = s.get("async_surfaces", {})
        n = a.get("count", 0)
        if n == 0:
            self.add("substance.loading-states", "SKIP", "no async surfaces detected")
            self.add("substance.error-states", "SKIP", "no async surfaces detected")
        else:
            cov = a.get("with_loading_state", 0) / n
            route_level = len(a.get("route_level_loading_files", [])) > 0
            missing = [f for f, v in a.get("files", {}).items() if not v.get("loading")]
            if cov >= 0.8:
                self.add("substance.loading-states", "PASS", f"loading state on {a['with_loading_state']}/{n} async surfaces")
            elif cov >= 0.5 or route_level:
                self.add("substance.loading-states", "WARN", f"loading state on {a['with_loading_state']}/{n} async surfaces{' (+ route-level loading files)' if route_level else ''}", evidence=missing[:10])
            else:
                self.add("substance.loading-states", "FAIL", f"loading state on only {a['with_loading_state']}/{n} async surfaces — skeletons/aria-busy/Suspense fallbacks are where care shows", evidence=missing[:10])
            ecov = a.get("with_error_state", 0) / n
            self.add("substance.error-states", "PASS" if ecov >= 0.5 else "WARN", f"error handling on {a['with_error_state']}/{n} async surfaces")

        # substance.placeholders
        ph = s.get("placeholders", {})
        hard = {k: v for k, v in ph.items() if k in ("lorem-ipsum", "john-jane-doe", "acme", "your-company", "insert-here", "todo-in-copy")}
        soft = {k: v for k, v in ph.items() if k in ("example-domain", "fake-metrics")}
        stock = ph.get("stock-image-host", [])
        if hard:
            self.add("substance.placeholders", "FAIL", "placeholder/fake content: " + ", ".join(f"{k}×{len(v)}" for k, v in hard.items()), evidence=[x for v in hard.values() for x in v[:4]])
        else:
            self.add("substance.placeholders", "PASS", "no lorem / John Doe / Acme / TODO-in-copy")
        if stock:
            self.add("substance.stock-imagery", "FAIL" if persuade else "WARN", f"{len(stock)} stock/placeholder image host reference(s) — the real product, or nothing", evidence=stock[:8])
        if soft:
            self.add("substance.claims", "WARN", "verify claims/metrics are real: " + ", ".join(f"{k}×{len(v)}" for k, v in soft.items()), evidence=[x for v in soft.values() for x in v[:4]])

        # substance.testimonials / pricing / evidence
        t = s.get("testimonials", {})
        if t.get("files"):
            self.add("substance.testimonials", "WARN", f"testimonials in {len(t['files'])} file(s) — a human must confirm each is real (name, role, permission); waive with reason 'verified real …' once done", evidence=t["files"][:6])
        pr = s.get("pricing", {})
        if pr.get("three_tier_scaffold_suspected"):
            self.add("substance.pricing", "WARN", f"three-tier pricing scaffold suspected ({', '.join(pr.get('tier_words', {}).keys())}) — tiers come from the business, not the template", evidence=pr.get("files", [])[:4])
        pe = s.get("product_evidence", {})
        if persuade:
            if pe.get("has_real_evidence"):
                self.add("substance.product-evidence", "PASS", f"real product evidence: video {len(pe.get('video_sites', []))}, local images {pe.get('local_images', 0)}")
            else:
                self.add("substance.product-evidence", "FAIL", "[persuade] no real product evidence (no video, no local screenshots) — this cannot be generated; capture the real product")
        else:
            self.add("substance.product-evidence", "SKIP", f"[{profile}] not a persuade surface")

        # motion
        mo = s.get("motion", {})
        if mo.get("files_with_motion", 0) == 0:
            self.add("motion.reduced-motion", "SKIP", "no motion detected")
        elif mo.get("reduced_motion_respected"):
            self.add("motion.reduced-motion", "PASS", f"motion in {mo['files_with_motion']} file(s); prefers-reduced-motion respected")
        else:
            self.add("motion.reduced-motion", "FAIL", f"motion in {mo['files_with_motion']} file(s) and no prefers-reduced-motion / useReducedMotion anywhere")

        # evidence.render
        self._check_render_evidence(m)
        return self.results

    def _check_render_evidence(self, m: dict):
        if self.evidence_dir is None:
            if self.no_render:
                self.add("evidence.render", "WARN", "--no-render: render evidence explicitly skipped (reasoning is not validation)")
            else:
                self.add("evidence.render", "FAIL", "no --evidence DIR: the crafted floor requires rendered screenshots at desktop + mobile widths (P11)")
            return
        if not self.evidence_dir.is_dir():
            self.add("evidence.render", "FAIL", f"evidence dir {self.evidence_dir} does not exist")
            return
        shots = [p for p in self.evidence_dir.rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
        ok = [p for p in shots if p.stat().st_size >= MIN_SCREENSHOT_BYTES]
        blank = [p.name for p in shots if p.stat().st_size < MIN_SCREENSHOT_BYTES]
        desktop = [p for p in ok if re.search(r"(1280|1440|1920|desktop|wide)", p.name, re.I)]
        mobile = [p for p in ok if re.search(r"(390|375|412|mobile|narrow)", p.name, re.I)]
        pages = [r for r in m.get("routes", []) if r.get("kind") == "page"]
        uncovered = []
        for r in pages:
            slug = r["route"].strip("/").replace("/", "-") or "index"
            if not any(slug in p.name for p in ok):
                uncovered.append(r["route"])
        if not ok:
            self.add("evidence.render", "FAIL", f"no non-blank screenshots in {self.evidence_dir}", evidence=blank[:6])
        elif not desktop or not mobile:
            self.add("evidence.render", "FAIL", f"need both widths: desktop={len(desktop)} mobile={len(mobile)} (name files with 1280/390 or desktop/mobile)")
        elif uncovered and len(uncovered) > max(2, len(pages) // 2):
            self.add("evidence.render", "WARN", f"{len(ok)} screenshots; {len(uncovered)}/{len(pages)} page routes have no matching screenshot", evidence=uncovered[:8])
        else:
            self.add("evidence.render", "PASS", f"{len(ok)} screenshots (desktop {len(desktop)}, mobile {len(mobile)}); {len(pages) - len(uncovered)}/{len(pages)} page routes covered")


# ---------------------------------------------------------------------------
def load_waivers(path: Path | None) -> dict:
    if not path:
        return {"waivers": []}
    if not path.exists():
        raise SystemExit(f"error: waivers file {path} not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    bad = [w for w in data.get("waivers", []) if len((w.get("reason") or "").strip()) < MIN_REASON or not w.get("check")]
    if bad:
        raise SystemExit(f"error: {len(bad)} waiver(s) lack a check or a reason ≥{MIN_REASON} chars — a silent waiver is not a waiver: {bad[:3]}")
    return data


def render_table(results: list[Result]) -> str:
    w = max(len(r.check) for r in results) if results else 10
    lines = [f"{'CHECK'.ljust(w)}  STATUS  DETAIL"]
    for r in results:
        tag = r.status + ("*" if r.waived else "")
        lines.append(f"{r.check.ljust(w)}  {tag.ljust(6)}  {r.detail}")
        for e in r.evidence[:5]:
            lines.append(f"{''.ljust(w)}          · {e}")
    fails = sum(1 for r in results if r.status == "FAIL")
    warns = sum(1 for r in results if r.status == "WARN")
    passes = sum(1 for r in results if r.status == "PASS")
    lines.append("")
    lines.append(f"unslop gate: {passes} PASS · {warns} WARN · {fails} FAIL · {'CLEAR' if fails == 0 else 'NOT CLEAR'}  (* = waived with reason)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("repo")
    ap.add_argument("--manifest", help="unslop_survey JSON (default: run the survey now)")
    ap.add_argument("--detect", action="store_true", help="when running the survey, also run the impeccable detector")
    ap.add_argument("--evidence", help="directory of rendered screenshots (desktop + mobile)")
    ap.add_argument("--waivers", help="JSON waivers file")
    ap.add_argument("--profile", choices=["auto", "persuade", "operate"], default="auto")
    ap.add_argument("--strict", action="store_true", help="WARN counts as FAIL")
    ap.add_argument("--no-render", action="store_true", help="explicitly skip render evidence (downgrades to WARN)")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: {repo} is not a directory", file=sys.stderr)
        return 2
    if args.manifest:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    else:
        if unslop_survey is None:
            print("error: unslop_survey.py not importable and no --manifest given", file=sys.stderr)
            return 2
        manifest = unslop_survey.survey(repo, detect=args.detect)
    waivers = load_waivers(Path(args.waivers) if args.waivers else None)
    gate = Gate(manifest, repo, waivers, args.profile, args.strict, Path(args.evidence) if args.evidence else None, args.no_render)
    results = gate.run()
    table = render_table(results)
    if not args.quiet:
        print(table)
    if args.json_out:
        out = {"schema": "unslop-gate/1", "repo": str(repo), "profile": args.profile if args.profile != "auto" else manifest.get("profile_hint"),
               "strict": args.strict, "results": [asdict(r) for r in results],
               "clear": all(r.status != "FAIL" for r in results)}
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if all(r.status != "FAIL" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
