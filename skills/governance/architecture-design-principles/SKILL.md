---
name: architecture-design-principles
category: governance
description: >
  Distilled architecture & design principles for building self-service developer platforms,
  control-plane / data-plane separation, and edge-centralized cross-cutting concerns —
  drawn from a senior platform engineer's 8-year retrospective on building Atlassian's
  Envoy-based load-balancing platform (Open Service Broker + Sovereign xDS control plane
  + AWS infra + sidecar model). Covers the three IaC layers (image / infra / runtime),
  the template+context pattern for dynamic proxy configuration, forced-migration as an
  adoption tool, long-term maintenance discipline (churn as a smell, build vs maintain
  as distinct skills), and the non-technical engineering skills (diplomacy, mentoring
  vs teaching). Use when: (1) designing a self-service internal developer platform,
  (2) deciding between native proxy features vs sidecars, (3) introducing or migrating
  to Envoy / xDS / service mesh, (4) implementing the Open Service Broker spec or any
  resource-provisioning API, (5) abstracting cloud complexity (AWS CloudFormation,
  Packer, SaltStack/Ansible/Puppet) behind a developer-friendly API, (6) centralizing
  cross-cutting concerns (auth, authz, rate limiting, DDoS, access logs) at the edge,
  (7) planning a fleet-wide migration to new infrastructure, (8) auditing a long-lived
  codebase for churn / coupling / maintenance burden, (9) onboarding engineers to an
  existing platform, (10) deciding when to mentor vs train, (11) user says "platform
  engineering", "control plane", "data plane", "xDS", "Envoy", "service broker",
  "edge compute", "sidecar", "cross-cutting concerns", "self-service", "internal
  developer platform", "IDP", "platform migration", "code churn", "long-term
  maintenance", "mentoring vs teaching".
metadata:
  source:
    talk: "I was laid off by Atlassian"
    speaker: Vasilios Syrakis
    date: 2026-05-10
    duration: 40:05
    url: https://www.youtube.com/watch?v=55pTFVoclvE
  type: distillation
  domain: platform-engineering
---

# Architecture & Design Principles — Platform Engineering at Scale

A field-tested distillation of how to build a developer platform that serves
~1000 services across ~13 regions on ~2000 long-lived proxies, derived from
an 8-year platform-engineering retrospective (Atlassian, 2017-2025).

The talk is structured as a chronological build-up; this skill re-organises
it as a **principle map** plus deep-dive references.

## Why this skill exists

Platform-engineering content online tends toward two failure modes:

1. **Vendor demos** that show the happy path of a tool without the failure
   modes that emerged at year three.
2. **Conference talks** that describe a finished system without the
   sequence of decisions that produced it.

This talk is unusual because it walks chronologically through *how* a small
team built a self-service load-balancing platform, *which choices compounded*,
and *which non-technical skills mattered most over eight years*. The
principles below are the durable shape of that experience.

## Principle Map (with canonical grounding)

Each principle is anchored to its canonical name in the established
literature. Use the canonical name in PRs and code review; reviewers can
verify against the cited source. Detailed grounding lives in
[`references/06-canon-and-citations.md`](references/06-canon-and-citations.md);
the canonical/novel/controversial breakdown lives in
[`references/07-contrasts.md`](references/07-contrasts.md).

| # | Principle | Canonical name | Source |
|---|-----------|----------------|--------|
| 1 | **Abstract the complexity, not the power** | Thinnest Viable Platform (TVP) | Skelton & Pais 2019 *Team Topologies* |
| 2 | **Three IaC layers: image, infra, runtime** | Build / Release / Run (Factor V) | Wiggins 2011 *12-Factor App* §V |
| 3 | **Control plane / data plane split** | Control plane / data plane (Istio) | Envoy xDS protocol; Istio architecture |
| 4 | **Template + Context separation** | Helm/Kustomize templating (primary); Open Host Service (DDD analogy) | Helm/Kustomize docs; Evans 2003 DDD p. 374 |
| 5 | **Async task orchestration** | Parallel Saga (async-eventual-orchestrated) | Ford et al 2021 *Hard Parts* Ch. 12; Richardson saga pattern |
| 6 | **Validate at the boundary** | Anti-Corruption Layer (semantic-translation form) | Evans 2003 DDD p. 364 |
| 7 | **Centralize cross-cutting concerns at the edge** | Gateway pattern + edge-centric architecture | Fowler PoEAA p. 466; microservices.io |
| 8 | **Sidecar for what the proxy can't do natively** ⚠ | Sidecar pattern *(now a choice, not default — see ambient mesh)* | Istio 1.24 (Nov 2024) Ambient GA; Buoyant Linkerd benchmarks |
| 9 | **Forced migration via removed alternatives** | Strangler Fig + specific forcing function | Fowler 2004 Strangler Fig; Microsoft Learn |
| 10 | **Build for the operator, not just the user** | SRE runbook/playbook discipline | Google SRE Workbook Ch. 8 |
| 11 | **Churn is a smell** | Atomic, triggered, dynamic fitness function | Ford et al 2023 *Building Evolutionary Architectures* 2e |
| 12 | **Building ≠ Maintaining ≠ Operating** | Toil discipline (50/25/25 cap) + DORA throughput-vs-stability | Rau, Google SRE Book Ch. 5; Forsgren et al 2018 *Accelerate* |
| 13 | **Diplomacy is an engineering skill** | Care Personally (Scott); leverage equation (Grove) | Scott 2017 *Radical Candor*; Grove 1983 *High Output Management* |
| 14 | **Mentoring ≠ Teaching** | Career vs psychosocial functions (Kram); Alpha Geek anti-pattern | Kram 1985 + Allen et al 2004 meta-analysis; Fournier 2017 *Manager's Path* Ch. 2 |

⚠ **2026 freshness flag — sidecars**: the talk's sidecar pattern is now
a deliberate architecture *choice*, not the default. Istio Ambient
(GA November 7, 2024, v1.24) replaces per-pod sidecars with per-node
ztunnel + per-namespace waypoint proxies; published savings ~90%+
proxy resources. Linkerd doubles down on sidecars with its Rust micro-
proxy and disputes the resource claims. Pick a side deliberately; cite
your reasoning. See [`references/07-contrasts.md`](references/07-contrasts.md#sidecars-in-2026).

For each principle, the columns "When to apply" and "Anti-pattern it
prevents" live in the numbered reference files (`01-self-service-platforms.md` … `07-contrasts.md`) and in
[`references/07-contrasts.md`](references/07-contrasts.md), which is
the canonical place to look for the operational guidance.

## The Reference Architecture (from the talk)

The talk's central diagram, reconstructed:

```
   ┌─────────────────────────────────────────────────────────────────────┐
   │  DEVELOPER                                                          │
   │     │                                                               │
   │     │  "pls provision a load balancer" (JSON in version control)    │
   │     ▼                                                               │
   │  ┌────────┐    ┌─────┐    ┌────────┐    ┌──────────┐               │
   │  │FastAPI │───▶│ SQS │───▶│ Worker │───▶│ DynamoDB │               │
   │  │ (OSB)  │◀───┴─────┘    │        │───▶│Route53,  │               │
   │  └────────┘                └────────┘    │CloudFront│               │
   │                                          │API calls │               │
   │  ── Open Service Broker (Tier 1) ─────────────────                  │
   │                                                                     │
   │  ┌─────────────────────┐                                            │
   │  │ Sovereign (xDS)     │   reads DB + S3 → renders templates        │
   │  │ ┌─────────────────┐ │                                            │
   │  │ │ Templates       │ │   xDS API ──▶┌──────────┐                  │
   │  │ │ + Context       │─┼──────────────▶│ 2000     │                  │
   │  │ │ → Clusters      │ │              │ Envoy    │ 13 regions       │
   │  │ │ → Routes        │ │              │ proxies  │                  │
   │  │ │ → Listeners     │ │              │ (EC2)    │                  │
   │  │ └─────────────────┘ │              └──────────┘                  │
   │  └─────────────────────┘                   ▲                        │
   │                                            │                        │
   │  ┌──────────────────────┐                  │                        │
   │  │ AWS CloudFormation   │  provisions ─────┘                        │
   │  │ Parameters, VPC,     │                                           │
   │  │ Subnet, IGW, SG,     │                                           │
   │  │ ASG, NLB, IAM, ACM,  │                                           │
   │  │ Route53, KeyPair     │                                           │
   │  │      │               │                                           │
   │  │      ▼               │                                           │
   │  │     AMI ◀──── Packer + SaltStack (image build)                   │
   │  └──────────────────────┘                                           │
   └─────────────────────────────────────────────────────────────────────┘
```

Three IaC layers map onto three different products in this stack:

- **Image** — Packer + SaltStack. Cadence: weeks. Risk: high (every proxy rebakes).
- **Infrastructure** — CloudFormation. Cadence: months. Risk: medium (regional).
- **Runtime config** — Sovereign / xDS. Cadence: seconds. Risk: per-tenant.

This separation is what lets a small platform team ship features daily without
restarting customer traffic. Most platform-team failures come from collapsing
these layers (e.g., redeploying proxies to ship a routing change).

## Edge-Centralized Cross-Cutting Concerns

The second half of the talk reconstructs the "what is the proxy *for*" question:

```
                    Customer (the outside world)
                          │  ▲
                          ▼  │
                     ┌─────────────┐
                     │ CloudFront  │  ←── DDoS protection
                     └─────────────┘
                          │  ▲
                          ▼  │
                     ┌─────────────┐
                     │     NLB     │
                     └─────────────┘
                          │  ▲
                          ▼  │
                     ┌───────────────────┐     ┌─────────────────┐
                     │      Envoy        │ ←──▶│ Sidecars        │
                     │ (Access logs,     │     │ • Authentication│ (Rust)
                     │  routing,         │     │ • Authorization │
                     │  HTTP filters)    │     │ • Rate Limiting │
                     └───────────────────┘     └─────────────────┘
                          │  ▲
                          ▼  │
              ┌───────┐ ┌───────┐ ┌───────┐ ... (a "bazillion" backends)
              │backend│ │backend│ │backend│
              └───────┘ └───────┘ └───────┘
```

**The rule**: the further left a concern is solved, the cheaper it gets per
backend. Solving DDoS at CloudFront protects all 1000 services. Solving auth
at the Envoy + sidecar pair means 1000 backend teams don't each implement OAuth.

**The cost**: cross-cutting concerns at the edge belong to the platform team.
Backend teams lose some autonomy in exchange for not having to think about
those concerns.

## When to Use This Skill

Invoke this skill explicitly when:

- Designing an **internal developer platform** (IDP) from scratch or evaluating one
- Choosing between **native proxy features and sidecars**
- Implementing an **Open Service Broker** or any resource-provisioning API
- Planning a **fleet-wide migration** to new infrastructure
- Auditing a long-lived codebase for **churn / coupling / maintenance burden**
- Onboarding engineers to an existing platform
- Mentoring vs training a junior engineer
- Justifying time spent on **diplomacy / conflict resolution** as engineering work

## Reference Map

For depth on each principle group:

- [Self-Service Platforms](references/01-self-service-platforms.md) — OSB, xDS,
  3-layer IaC, template+context, async task, boundary validation
- [Edge Compute & Sidecars](references/02-edge-compute-sidecars.md) — cross-cutting
  concerns, sidecar tradeoffs, multi-team contribution
- [Platform Migration](references/03-platform-migration.md) — forced migration,
  removing the old path, migration cost calculus
- [Long-Term Maintenance](references/04-long-term-maintenance.md) — churn as
  smell, build vs maintain, operator-centric design, AI-coupling risk
- [Non-Technical Engineering Skills](references/05-non-technical.md) — diplomacy,
  mentoring vs teaching, conflict anticipation, curse of knowledge
- [Canon and Citations](references/06-canon-and-citations.md) — master
  citation index across Platform Engineering, SRE/DORA, Architecture
  Patterns, Modern Tooling (2026), and Staff+ Engineering canon, with
  full bibliographies
- [Contrasts (canonical / novel / controversial)](references/07-contrasts.md) —
  for each principle, whether it matches canon, extends canon, or
  diverges from the 2026 canon; how to cite each in code review
- [Source: talk transcript & diagrams](references/source/talk.md) — full attribution,
  timestamps, key visual frames

## Grounded Best Practices — TL;DR

Every principle in this skill has a canonical name and a named source.
The full grounding is in [`references/06-canon-and-citations.md`](references/06-canon-and-citations.md).
The five canon clusters and what they ground:

- **Platform Engineering canon** (Skelton & Pais *Team Topologies* 2019;
  Conway 1968; *Accelerate* 2018; Humanitec State of Platform
  Engineering Reports 2022-2024; Hohpe *Architect Elevator* 2020;
  Backstage v1.50 / Crossplane 2.0) → grounds principles 1, 7, 9 and
  the "platform team" framing throughout.

- **SRE & DORA canon** (Google SRE Book 2016; SRE Workbook 2018;
  *Accelerate* 2018; DORA 2024 J-curve finding; DORA 2025 AI-as-amplifier
  finding) → grounds principles 10, 11, 12 and the AI-coupling-risk
  framing in `04-long-term-maintenance.md`.

- **Architecture Patterns canon** (Evans *DDD* 2003 — ACL, Open Host
  Service; Fowler *PoEAA* 2002 — Gateway; Fowler 2004 — Strangler Fig;
  Ford/Parsons/Kua 2017 + 2nd ed 2023 — fitness functions;
  Ford/Richards/Sadalage/Dehghani 2021 — saga patterns; Wiggins 2011 —
  12-Factor V; AWS Well-Architected; Nygard 2011 — ADRs; Brown — C4)
  → grounds principles 2, 3, 4, 5, 6, 7, 9, 11.

- **Modern Tooling 2026 reality check** (Envoy v1.38 + go-control-plane;
  OSB v2.17 not deprecated but Crossplane 2.0 is the 2026 substrate;
  Istio Ambient GA Nov 2024 / Linkerd micro-proxy debate; SMI archived
  Sept 2023; Backstage v1.50 + Spotify Portal GA; SaltStack in decline;
  Terraform Stacks GA HashiConf 2025) → grounds the freshness flags
  on principles 3, 8, and the tooling notes throughout.

- **Staff+ Engineering canon** (Reilly *Staff Engineer's Path* 2022 —
  three pillars + "You're a Role Model Now"; Fournier *Manager's Path*
  2017 — Alpha Geek anti-pattern; Larson *Staff Engineer* 2021 — Tech
  Lead archetype; Camerer/Loewenstein/Weber 1989 + Heath brothers 2007
  — curse of knowledge; Scott *Radical Candor* 2017 — Ruinous Empathy;
  Grove *High Output Management* 1983 — leverage equation; Kram 1985 +
  Allen et al 2004 — mentoring research; Edmondson 1999/2018 —
  psychological safety; Hogan *Resilient Management* 2019) → grounds
  principles 13, 14 and `05-non-technical.md` throughout.

The contrast matrix at [`references/07-contrasts.md`](references/07-contrasts.md)
catalogs **where** each principle is canonical, novel, or controversial
against the 2026 canon — useful when defending a design in code review.

## Anti-Heuristics (when NOT to apply)

- **Greenfield project, no compounding cost yet.** The three-IaC-layer split, the
  control-plane separation, and the template+context pattern are *amortizations*
  of cost over many tenants. A single-team service doesn't need them.
- **Cross-cutting concerns of a single team.** Edge centralization is correct
  when N teams need the same thing. For one team's auth, just put it in the app.
- **Forced migration without an actually-better target.** The talk's forced
  migration worked because the new platform was strictly better. Forcing
  migration to a not-yet-better platform burns trust.
- **Churn-as-smell on actively-developed code.** Churn is a smell on *finished*
  features that won't stop changing — not on features that are still being built.

## Talk Attribution

> "I was laid off by Atlassian" — Vasilios Syrakis, 2026-05-10
> https://www.youtube.com/watch?v=55pTFVoclvE  (40m05s)
>
> Despite the click-bait title, this is one of the densest first-person
> retrospectives on platform engineering at scale published in recent memory.
> Vasilios built and open-sourced Sovereign (the Envoy xDS control plane)
> while at Atlassian; the talk reconstructs the system from memory on Excalidraw.

Open-source artifact mentioned in the talk: **Sovereign** (Envoy xDS management
server in Python/FastAPI) — see talk for Bitbucket link; the design is what
matters here, not the specific repo.
