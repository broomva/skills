# Kleos — Design Canon (v1, post-review)

> Single source of truth for the Kleos engine. Agent-readable (Category A · P18).
> Derived from research workflow `wf_d25abca6-6bf` (2026-06-08) + its P20 adversarial
> review (5.5/10 REVISE). Every correction the review surfaced is **baked in here**,
> not papered over. Provenance: `research/notes/2026-06-08-revenuecast-*` + BRO-1429.

---

## 0. What Kleos is

**Kleos turns a real-world capability into a self-demonstrating, high-throughput
gen-AI revenue engine.** It is `/skillify` for revenue: `skillify` turns a working
*workflow* into a permanent skill; **Kleos turns a *capability* into a permanent
revenue engine.**

The name (κλέος — Homeric *renown that propagates precisely by being shown and
re-told*) names the mechanism, not the artifact: the **showcase propagates the
demand** because the output's desirability is what spreads. The bard broadcasts the
hero's deed → renown spreads → demand for the method → you teach others to win their
own revenuecast. It slots into the Broomva Greek-named stack (Pneuma, Anima, Haima,
Prosopon, Krisis). **Caveat (from review):** low decode-rate outside classically
literate audiences — every surface must carry a one-line gloss:
*"Kleos — your work, made famous by showing it."* The content brand is separate:
**`arcan-studio`** (already compiled in `content-engine`).

Kleos is a **composition skill** (like `/checkit`, `/autonomous`, `/skillify`). It
fires existing primitives and skills in sequence. **It reimplements nothing.**

---

## 1. The thesis (validated) and its one hard correction

**Thesis:** Define a distinctive brand + aesthetic → use gen-AI to produce
high-volume content showcasing the *output* of a capability → the content IS the
advertisement (desirability + accessibility-via-AI = demand) → monetize by selling
the **method/system** that reproduces it for someone else's brand.

**The correction that makes it true (review, HIGH):** the scarce, non-leakable input
is **not the method** — it is the **SHOW step** (distribution + taste + a *running*
engine). Proof: Whop's own data — of 191,654 products, **88% earn $0**, median earner
**$74/mo**, top 1% capture 57% of revenue. The power-law graveyard exists *because*
everyone has the same prompts and the same models (one API call away via aggregators;
quality leadership rotates quarterly). What failing creators lack is a running engine
that reliably produces on-brand, retention-clearing output at volume.

> **Kleos therefore sells the self-demonstrating ENGINE that produces the SHOW —
> never "the method" generically.** The prompts are not the moat; they leak in days.

---

## 2. The flywheel (6 stages, each composing an existing skill)

```
0 BRAND LOCK → 1 SHOW → 2 DISTRIBUTE → 3 HOOK → 4 SELL → 5 MOAT ↻ (feeds 0)
```

| # | Stage | What | Composes |
|---|-------|------|----------|
| 0 | **Brand Lock** | distinctive, defensible visual+verbal identity (brand DNA, synthetic persona sheet, fixed color/lighting/upscale signature, 4-layer prompt skeleton). The thing that makes the example "sell itself by style" and survives the IG ~80% generic-AI throttle. | `content-engine` (compile + `content-engine-dna`) · `arcan-glass` (brand web) |
| 1 | **Show** | high-volume, on-brand output AS the ad. Target machine-checkable retention gates (TikTok ~70% completion · Reels ~70% + 60% 3-sec hold · Shorts ~85% / swipe <30%). Volume is the strategy: ~1 viral per ~100 shots; AI makes the denominator cheap (~$0.50–3.00/asset, ~24 min/asset in a 2-hr batch → 5 publish-ready). | `content-engine` (generate/cinema/autopilot) · `brainrot-for-good` · `launch-video` · `content-creation` (Remotion + TTS via `omnivoice`/ElevenLabs) |
| 2 | **Distribute** | fan out raw-per-platform to ≥3 video surfaces + 1 **owned** channel. De-watermark (never download-with-watermark) + ≥30% transform + native 9:16 + burned-in captions. **X is the AUTHORITY layer (text/threads), not a video dump.** Blog + LLMEO seed AI-answer-engine discovery. | `content-engine` (loop) · `blog-post` · `seo-llmeo` · `social-intelligence` (`x-outreach-strategy.md`) |
| 3 | **Hook** | convert passive viewers into a captured, re-marketable list. Two devices: (a) Zeigarnik incompleteness (publish the 30-min cut, gate the full); (b) comment-to-DM keyword CTA → 90s auto-DM → email capture. The DM is the only clickable path off public comments — that's why it exists. | `social-intelligence` · ManyChat-class SaaS (external rail) |
| 4 | **Sell** | run the captured list up the ladder (§4). Anchor with a **paid challenge** (manufactures public proof + bridges to recurring). Bias recurring to **annual** (≈10× churn cut). Stack offers, don't raise base price. | `strategy-skills` · `Sales` · `finance-substrate` (unit economics) |
| 5 | **Moat** | sell the **non-leakable** layers (§3), not the prompts. Crystallize what worked back into the sellable system; measured behavior feeds Stage 0. | `bookkeeping` (P6 measure→refine→crystallize) · `symphony`+`arcan` (agency-proof runtime, L3) |

---

## 3. The Moat Picker (Kleos's defensible-layer selector)

Tell the user explicitly: **prompts/templates are NOT the moat (they leak in days).**
The engine must pick ≥1 defensible layer. `revenuecast_check.py` FAILs a manifest whose
`moat.primary` is `prompts` or `templates`.

| Moat | Why defensible | Best when |
|------|----------------|-----------|
| **Operational sequencing** | upload order, posting cadence, per-shot model-routing table, attach-rate stacking — invisible in the free content (Osias's "upload order" system). | any niche; the default operational core |
| **Recency-as-service** | a living, version-dated community re-teaching each model within days of release beats any static PDF (stale in 90 days). Converts one-time → recurring (68–74% 90-day retention *in consumer education* — see §6 KPI honesty). | fast-churning tool stacks |
| **Community + accountability** | live cohort, member showcase wall, client-getting module. | audience wants belonging/outcomes |
| **Agency-proof** | the reference implementation IS a running portfolio of viral output (Genre.ai's 300M+ views de-risks the course). Proof and product are the same artifact — a copycat without the engine cannot fake it. | you actually run the engine at scale |
| **Compliance / survival** | "the only AI-revenue method that won't get you banned or sued." See §5. Most competitors are pump-and-dump that teach growth, not survival. | regulated/hardening environment (2026) |
| **Closed-execution** | (Capafy model) sell the engine as a per-use black box; the governance loop runs server-side, never forked → defeats prompt-commoditization. | the engine itself is the IP |

---

## 4. The offer ladder — corrected to a **validated wedge**, not a 6-tier deck

The research produced a canonical T0–T6 ladder. **The review's correct objection:**
designing T5 (closed-execution) / T6 (affiliate-license-recursion) **before T1
converts a single dollar is info-product self-flattery.** So the canon splits the
ladder into **v1 (build now)** and **earned (design only after measured numbers)**.

### v1 — the two-step wedge (the only thing you build first)
- **T0 · Free showcase + lead magnet ($0)** — the high-volume on-brand output IS the
  ad; a free mini-kit (one template + the 4-layer skeleton + the retention-threshold
  card) delivered via the capture rail → **email** (the owned asset no algorithm can
  throttle). `revenuecast_check.py` requires an `owned_channel`.
- **T1 · Tripwire ($17–29 one-time)** — 40–60 prompts = a full workflow + the
  model-routing cheat-sheet + the sequencing order + caption/hook vault. Synthetic
  personas only (likeness firewall, §5). The first dollar that converts viewer→buyer.
- **T-spine · One recurring community ($39–99/mo, push annual)** — the durable spine:
  recency re-teaching + member showcase + the client-getting module. **Recurring
  out-earns one-time by ~89%.** This is the asset that compounds.

`revenuecast_check.py` requires the ladder to contain **≥1 free + ≥1 paid + ≥1 recurring**.

### earned — design only after >0 paying customers + measured conversion
- **T3 · Paid challenge ($49–97)** — 70–80% completion vs sub-5% course *(consumer
  benchmark — re-baseline for your buyer)*. Manufactures the public proof.
- **T5 · VIP / done-with-you / closed-execution ($497–7.5K)** — LTV ceiling +
  moat-protection (Capafy hosted tier).
- **T6 · Affiliate / license-recursion (20–29%)** — the outermost loop; the literal
  Kleos recursion (sell the engine to people who run it for *their* vertical).

> Tiers are a **hypothesis to be earned, not a blueprint to be built** (review).

---

## 5. The Compliance / Survival pillar (first-class — and a standalone wedge)

The review's sharpest upgrade: **the compliance module is the most defensible part of
the offer AND a sharper standalone product than "learn to make AI content."** It
targets a dated, urgent pain (EU AI Act Art. 50 live **Aug 2 2026**; Cursor FastRender
"shoddy code at scale") with deadline-driven urgency. `revenuecast_check.py` makes it
**mandatory** — a manifest missing any governance field FAILs.

| Risk (2026, HIGH unless noted) | Guardrail (machine-checked where possible) |
|---|---|
| **FTC v. Air AI** (Mar 2026): lifetime biz-opp ban + $18M for false earnings + fake guarantee | `earnings_claims_substantiated: true` — every income claim has written proof + "results not typical"; sell the *capability*, never guaranteed income; honor a **real** money-back guarantee; never chargeback-waiver clauses. **Note: the SELLER (Kleos) is the entity in scope** — harden Kleos's own sales page first. |
| **NO FAKES Act / TN ELVIS Act / right-of-publicity** (Johansson; Swift+Kimmel voice marks Apr 2026) | `likeness_firewall: true` — owned synthetic personas / fictional brand characters / cleared talent only. **Never** a real identifiable person without written consent + license. Teach the firewall as a feature. |
| **EU AI Act Art. 50** (live Aug 2 2026; €15M / 3% turnover) | `disclosure_labeling: true` — C2PA Content Credentials + imperceptible watermark + platform AI-label baked in as a **build step**, not an afterthought. |
| **YouTube "inauthentic content" sweep** (Jan 2026: ~16 channels / 4.7B views / ~$10M/yr wiped) | keep human editorial commentary >30%; vary templates >20% script-to-script; `platform_diversification: ≥3 + owned`. |
| **AI-slop demand reversal** (preference 60%→26%, 2023→2026) | reposition moat from **volume** to **distinctive aesthetic + craft + human fingerprint**: "the system that survives the algorithm," not "the system that makes a lot of content." |
| **Prompt/template commoditization** | sell the non-leakable layers (§3) + offer closed-execution. |

---

## 6. The Ritual-vs-Substance gate (the review's #1 must-fix, made machine-checkable)

The L3 draft claimed self-improvement was a **fork of `symphony-egri/batch.rs`**. The
reviewer read the file: it computes one scalar (`completed/(completed+retrying)`) and
increments `promoted_count`/`discarded_count` as a **pass/fail tally** — it is **not a
variant selector**. Real self-improvement (multi-armed bandit + per-variant retention
attribution + brand-DNA parameter fold-back) is **unbuilt NEW code**. Claiming it as
reuse is exactly the **incantation-vs-control** failure CLAUDE.md §Ritual-vs-Substance
warns against (a verbal claim with no causally-independent mechanism behind it).

> **Binding rule:** no Kleos surface (buyer-facing OR internal) may claim
> "self-improving" / "the loop rewrites tomorrow's content" unless the mechanism is
> **built AND measured**. `revenuecast_check.py` enforces:
> `self_improvement.claimed == true` ⟹ `mechanism_built == true && measured == true`,
> else FAIL.

### KPI honesty (same gate family)
All the conversion benchmarks (comment-DM 25–55% trigger, 70–80% challenge completion,
$112 blended/member, $1,800 LTV, 235× CAC) are **imported from the consumer
AI-celebrity niche** and are **unvalidated for any other buyer** — especially the
high-trust technical (B2D) buyer. The manifest must separate `kpis.validated`
(measured from *this* instance) from `kpis.imported` (borrowed; labeled). Presenting
imported numbers as validated targets is a slop tell and a (real) FTC risk.

---

## 7. The three layers (with L3 honestly deferred)

| Layer | What | Status this session |
|-------|------|---------------------|
| **L1 — Core system + playbook** | the `/revenuecast` skill (composition + `revenuecast_check.py` gate + tests) + the Category-C HTML playbook. The meta-engine applicable to any niche. | **BUILT** |
| **L2 — Applied wedge (dogfood)** | Kleos applied to Broomva's own niche: autonomous agentic dev under control-systems governance. **Authority-rail-first**; the FastRender-counter as the single Day-1 cornerstone proof; honest measure-from-zero KPIs. The first real instance. | **ARTICULATED** (HTML) |
| **L3 — Autonomous runtime** | the runtime spec at `references/runtime-spec.html` (+ `references/runtime-status.md`) — the daemon that generates + publishes + self-improves under `.control/policy.yaml`. | **SPEC'd, DEFERRED** — bundled here as a spec; graduates to its own Rust deploy repo only after L2 validates demand (review must-fix). |

### L2 — why the agentic-dev wedge is the strongest niche
- The market **named the problem in 2026**: "harness engineering" (Hashimoto → OpenAI/Lopopolo Feb 11 2026 → Thoughtworks/Böckeler: a literal *"cybernetic governor combining feed-forward and feedback to regulate the codebase"*) = Carlos's RCS control-metalayer, described two layers shallower.
- **Generation is commoditized; governance is the scarce input.** Cursor FastRender (Jan 2026) proved ~2,000 agents write 3M+ lines/week — and The Register + SIG confirmed "shoddy code at scale." The wedge: making a swarm *shippable* (safe, reviewed, self-improving, un-sue-able).
- **The slop reversal INVERTS into an advantage**: when consumers distrust AI volume, "it actually shipped and passed CI" is an authenticity signal volume-slop cannot manufacture.
- **Dogfood-as-proof is physically real** (review verified the substrate: `crates/symphony-orchestrator` scheduler, `symphony-egri` eval ledger, `content-engine` live Gemini + rendered `.mp4`). The engine that ships the content IS the product.
- **Lead with the authority rail** (X threads + technical blog + GitHub + LLMEO + "harness engineering is control theory" cornerstone). Treat IG/TikTok keyword-DM as a *secondary* experiment — the dev buyer converts on credibility → community, not Reel → DM → tripwire.
- **The single Day-1 cornerstone bet**: run a small bstack-**governed** multi-agent build of one real, fully-ownable feature; publish the measured quality delta (CI pass-rate, review-catch count, LOC churn) vs an **ungoverned** swarm doing the same task. One numbers-backed artifact > 20 stylized terminal Shorts, and platforms structurally cannot reproduce it.
- **Reframe the product**: from "sell the method" → "**sell a seat in the running self-improving org**" (recency-as-service community whose curriculum IS the measured dogfood behavior). Collapses T2+spine into one hard-to-copy thing.

### L3 — honest scoping (corrected from the draft)
- It is a **thin vertical** (a "social content plant") on runtimes Broomva already ships — NOT a new orchestrator. The flywheel IS an observe→decide→act→judge loop; symphony already runs that shape for code tickets; Kleos swaps the plant.
- **Corrected repo paths**: `core/symphony/crates/symphony-orchestrator/src/scheduler.rs`, `core/symphony/crates/symphony-egri/...` (NOT `symphony-orchestrator/src/`). Lago/Anima/Haima live in `core/life/`, are **in-flight (many open worktrees), NOT M1-ready** — wiring `revenuecast-store` onto them is a cross-subsystem integration budgeted at *weeks*, not the draft's "DAY 2-5."
- **The only genuinely-new code is the publisher** + the **self-improvement loop** (the bandit/attribution/fold-back the review correctly flagged as unbuilt). Publishing transports are dictated by hard 2026 API reality: YouTube Data API v3 (~100 units/call, 100/day on free 10k quota) · IG Graph (3-step, **25 published/24h** cap, App Review) · TikTok Content Posting (**SELF_ONLY until audit**) · X v2 pay-per-use ($0.20 URL-write penalty *enforces* the "X = authority, never lead with a link" rule for free).
- **Governance**: `.control/policy.yaml` extended with S-K1 spend-cap/day · S-K2 per-platform ceilings (≤ each API's hard limit) · S-K3 disclosure=100% · S-K4 likeness-firewall=0 real persons · S-K5 brand-safety. Enforced by a PreToolUse-style shield BEFORE any generate/publish.
- **Deploy target: Railway** (workspace default; Colombian-only tax, no US entity).
- **DO NOT BUILD speculatively.** The repo ships as a scaffold with the spec + an explicit `STATUS: DEFERRED` gate.

---

## 8. Composition map (Kleos reimplements nothing)

| Kleos stage / need | Existing asset it fires |
|---|---|
| Brand lock | `content-engine` + `content-engine-dna` (`arcan-studio.md` compiled) · `arcan-glass` |
| Generate at volume | `content-engine` (cinema/autopilot) · `brainrot-for-good` · `content-creation` · `Remotion` · `omnivoice`/ElevenLabs |
| Distribute / repurpose | `content-engine-loop` · `blog-post` · `seo-llmeo` |
| Authority / X | `social-intelligence` + `docs/launch/social/x-outreach-strategy.md` |
| Offer / pricing / economics | `strategy-skills` · `Sales` · `finance-substrate` |
| Measure / crystallize | `bookkeeping` (P6) · `agent-consciousness` |
| L3 autonomous runtime | `symphony` + `arcan` + `agentic-control-kernel` + `.control/policy.yaml` + `persist` (P12) + `bstack wave` (P19) |
| Skill gate | `skillify` 10-step + `revenuecast_check.py` (this skill's deterministic core) |

---

## 9. What "done" means (the deterministic gate)

A Kleos engine instance is real iff `revenuecast_check.py revenuecast.manifest.yaml` passes:
1. `capability`, `brand.name`, `brand.gloss` present.
2. `offer_ladder` has ≥1 free + ≥1 paid + ≥1 recurring tier.
3. `distribute.owned_channel` present (own-the-audience mandate).
4. `moat.primary` ∈ {sequencing, recency, community, agency-proof, compliance, closed-execution} — **never** prompts/templates.
5. `governance` has all of: `disclosure_labeling`, `likeness_firewall`, `earnings_claims_substantiated`, `spend_cap`, `platform_diversification (≥3 + owned)`.
6. `self_improvement.claimed` ⟹ `mechanism_built && measured` (Ritual-vs-Substance gate).
7. `kpis.imported` block present whenever benchmark numbers appear (KPI honesty gate).

> A capability that doesn't pass all gates is not a revenue engine. It's just
> content that happens to exist today.
