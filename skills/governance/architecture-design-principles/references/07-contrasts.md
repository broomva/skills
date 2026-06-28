# Contrasts — Where the Atlassian Patterns Sit Against Canon

For each principle the skill teaches, this file sorts the claim into one
of three buckets vs the established canon:

- **CANONICAL** — the talk's pattern has a named, dated source in the
  canon. Use the canonical name in code review and PRs.
- **NOVEL** — the talk extends or sharpens canonical patterns in a way
  worth keeping.
- **CONTROVERSIAL** — the canon disagrees, or the canon's 2026 position
  diverges. The talk's pattern may still be right for some contexts;
  the controversy is part of the design conversation.

The canonical sources cited below are detailed in
[`06-canon-and-citations.md`](06-canon-and-citations.md).

## Contrast matrix

| # | Skill principle | Bucket | Canonical name (if any) | Canonical source | Where canon diverges (if so) |
|---|-----------------|--------|-------------------------|------------------|------------------------------|
| 1 | Abstract the complexity, not the power | **CANONICAL** | Thinnest Viable Platform (TVP) | Skelton & Pais 2019 | — |
| 2 | Three IaC layers: image / infra / runtime | **CANONICAL** | 12-Factor V (Build, Release, Run) | Wiggins 2011 §V | Naming: 12-Factor calls them stages, talk calls them layers — same idea |
| 3 | Control plane / data plane split (xDS) | **CANONICAL** | Control plane / data plane (Istio docs) | Istio architecture page; Envoy xDS protocol | xDS v3 is final; custom xDS server is now go-control-plane, not bespoke |
| 4 | Template + Context separation | **CANONICAL** | Helm/Kustomize/Kapitan templating (primary anchor); Open Host Service (Evans p. 374, integration-pattern analogy) | Helm docs, Kustomize docs; Evans 2003 DDD | Typed-construct equivalents (CDK, Pulumi, cdk8s) are the modern upgrade; OHS is a boundary-integration pattern not strictly a templating one |
| 5 | Async task orchestration (FastAPI→SQS→Worker→DB) | **CANONICAL** | Parallel Saga *shape* (async-eventual-orchestrated) | Ford et al 2021 *Hard Parts* Ch. 12; Richardson saga pattern | Pattern matches the Parallel Saga *shape*; full transactional saga semantics (compensation on failure) depend on worker design and aren't described in the talk |
| 6 | Validate at the boundary | **CANONICAL (partial)** | Anti-Corruption Layer (Evans p. 364) for the semantic-translation form; schema/input validation for the type-narrowing form | Evans 2003 DDD; Microsoft Learn ACL pattern | ACL is specifically the *semantic-translation* form (when upstream and downstream have different models); plain schema validation is the complementary form |
| 7 | Centralize cross-cutting concerns at the edge | **CANONICAL** | Gateway pattern + edge-centric architecture | Fowler PoEAA p. 466; Fowler-Lewis microservices article | — |
| 8 | Sidecar for what the proxy can't do natively | **CONTROVERSIAL (in 2026)** | Sidecar pattern (still in Istio docs) | Istio dataplane-modes; Buoyant's Linkerd benchmarks | Istio Ambient (GA Nov 2024, v1.24) reduces ~90% proxy resources; Linkerd disagrees, Buoyant claims Ambient uses *more*. Sidecar is now a *choice* not the default. |
| 9 | Forced migration via removed alternatives | **NOVEL extension of CANONICAL Strangler Fig** | Strangler Fig Application (Fowler 2004) | Fowler bliki; Microsoft Learn; *AssetCapture* + *Event Interception* (Fowler) | Humanitec's "Platform-as-a-Product" thesis prefers voluntary adoption via quality, not forced migration. Forced migration works in high-authority platform teams; in low-authority orgs, it backfires. |
| 10 | Build for the operator, not just the user | **CANONICAL** | SRE runbook/playbook discipline | Google SRE Workbook Ch. 8 (On-Call) | — |
| 11 | Churn is a smell | **CANONICAL via NOVEL framing** | Atomic, triggered, dynamic fitness function | Ford/Parsons/Kua 2017; 2nd ed 2023 (*Automated Software Governance*) | The talk identifies the symptom; canon adds the mechanism (encode commit-frequency-per-file as a CI gate) |
| 12 | Building ≠ Maintaining ≠ Operating | **CANONICAL** | Toil discipline (50% / 25% / 25% cap) | Rau, SRE Book Ch. 5; *Accelerate* throughput vs stability | The talk's 50-70/20-30/10-20 ratio rebalances slightly toward building vs Google's 50/25/25 |
| 13 | Diplomacy is an engineering skill | **CANONICAL** | Care Personally (Scott 2017); Grove's leverage equation | Scott *Radical Candor*; Grove *High Output Management* | The talk's diplomacy maps cleanly onto Care Personally; under-care produces Ruinous Empathy ("by far the most common quadrant") |
| 14 | Mentoring ≠ Teaching | **CANONICAL** | Career vs psychosocial mentoring functions (Kram); Alpha Geek anti-pattern (Fournier) | Kram 1985 *Mentoring at Work*; Allen et al 2004 meta-analysis; Fournier *Manager's Path* Ch. 2 | Allen et al find psychosocial benefits dominate compensation/promotion outcomes |

## Where the talk extends canon

### Forced migration as a refinement of Strangler Fig

Strangler Fig (Fowler 2004) describes the *gradual replacement* shape: a
new system grows around the edges of the old until the old is fully
strangled. The talk's contribution is the **specific forcing function**:
*"you can no longer expose your service publicly through the [old] load
balancer."* The old system kept working — for internal traffic. The
forcing function was specific (public exposure) rather than total
(delete the old thing).

This is a refinement worth keeping in the canonical lexicon: **a
specific forcing function is a wall, not a cliff**. Teams can choose
when to climb it; eventually they must. Total deprecation generates
escape-valve work; specific forcing functions don't.

The novel claim is that this forcing-function mechanism is what made
the migration feasible at all in a high-trust platform-team context. The
canon's preferred lever (Humanitec's "Platform-as-a-Product": build it
so good they migrate voluntarily) is more diplomatic but slower; the
talk's lever is faster but requires organizational backing.

### "Three IaC layers" as a 2026 update of 12-Factor V

12-Factor's Build/Release/Run was 2011-era guidance written for
single-process apps deployed to Heroku-shaped PaaS. The talk's three-
IaC-layer pattern updates this for fleet-scale infrastructure:

- **Build** (12-Factor) → **Image layer** (Packer/SaltStack → AMI)
- **Release** (12-Factor) → **Infra layer** (CloudFormation/Terraform
  Stacks) + **Runtime config layer** (xDS / Sovereign / templates)
- **Run** (12-Factor) → **Running fleet** (the Envoy proxies receiving
  config)

The novel contribution: 12-Factor doesn't distinguish between
*infrastructure provisioning* and *runtime configuration*, because in
2011 those were the same thing (your env vars + your image = your
release). At fleet scale they're not — VPCs change once a year,
runtime config changes per pull request. The talk's three-layer split
is the durable shape for 2026.

### "Churn as smell" as an atomic fitness function

*Building Evolutionary Architectures* (Ford/Parsons/Kua 2017, 2nd ed
2023) introduces fitness functions but doesn't enumerate churn-rate as
a canonical one. The talk identifies the symptom; the canon's mechanism
(continuous testing, CI gating) provides the implementation:

```bash
# Atomic, triggered, dynamic fitness function: churn-as-CI-gate
git log --since="1 year ago" --name-only --pretty=format: \
  | sort | uniq -c | sort -rn | head -20 \
  | awk '{ if ($1 > THRESHOLD) print "CHURN: " $2 }' \
  | tee churn-violations.txt
test ! -s churn-violations.txt  # fail CI if any
```

This composes the talk's diagnosis with the canon's machinery. Neither
half exists in the published canon, but the combination is implied by
both.

## Where canon disagrees with the talk

### Sidecars in 2026

The talk's claim: *"When the proxy can't do something natively, run it
as a sidecar locally; same machine, low latency, contributable by
other teams."*

The 2026 canon's position is split:

- **Istio Ambient (GA November 7, 2024)** moves L4 to a per-node
  `ztunnel` and L7 to per-namespace waypoint proxies *outside*
  application pods. Resource savings of ~90% vs sidecars. Istio's
  position: *"most use cases will be best served with a mesh in
  ambient mode."* Sidecars not deprecated, but not the default either.
- **Linkerd doubles down on sidecars** — their Rust micro-proxy is
  ~20-30MB vs Envoy's 50+MB; Buoyant's published benchmarks claim
  Linkerd's sidecars use *less* total resource than Istio Ambient.
  Their argument: sidecars preserve a clean per-pod security boundary
  that node-shared ztunnels dilute.
- **The 2024 CNCF Annual Survey** shows overall service-mesh adoption
  *dropped from 50% to 42% YoY* — teams becoming more deliberate, not
  less.

The talk's sidecar claim is still valid in 2026, but **it is now a
deliberate architecture choice with explicit trade-offs**, not the
default. A 2026 design referencing "the Atlassian sidecar pattern"
should also say which side of the ambient debate it chooses and why.

### Open Service Broker vs Crossplane

The talk uses OSB as its consumer contract. In 2026:

- OSB v2.17 is **not deprecated** — the spec is still maintained at
  `github.com/openservicebrokerapi/servicebroker`, with ongoing
  community calls in the Cloud Foundry Service Management Working
  Group.
- BUT: OpenShift formally deprecated OSB in OpenShift 4 in favor of
  OLM (Operator Lifecycle Manager). The Kubernetes Service Catalog SIG
  is effectively dormant.
- **Crossplane Compositions** (Crossplane 2.0, August 12, 2025) are the
  2026 Kubernetes-native equivalent of "platform team defines a
  resource shape, consumer teams self-service it."

For a 2026 greenfield Kubernetes-native platform: choose Crossplane
XRDs + Compositions. For cross-platform federation or CloudFoundry
shops: OSB still works. The talk's *substance* (a typed contract
between platform team and consumers) survives; the specific OSB
encoding is no longer the default.

### Forced migration vs "Platform-as-a-Product"

Humanitec's *State of Platform Engineering Reports* (Volumes 1-3,
2022-2024; Vol 4 in 2025 by platformengineering.org / Broadcom) push
the explicit thesis: *"organizations that mandate
adoption by top-down decree underperform those that build a platform
so useful that teams choose it voluntarily."* The talk's "forced
migration via removed alternatives" cuts against this.

**The resolution**: both can be true depending on context.

- In a high-authority platform-team context (the talk's setting at
  Atlassian, with executive backing to enforce a forcing function),
  forced migration via removed alternatives is faster and produces
  cleaner end state.
- In a low-authority platform-team context (most companies), forcing
  functions generate revolt and destroy platform-team credibility.
  Voluntary adoption via product quality is the only path.

The talk's pattern is right *given its prerequisites*; the canon is
right *given other prerequisites*. The skill should be explicit about
which prerequisites apply.

### Custom xDS server vs go-control-plane

The talk built **Sovereign** as a custom xDS management server in Python/
FastAPI. In 2017 this was the right call — no mature open-source xDS
control plane existed.

In 2026, **the canonical recommendation is
`github.com/envoyproxy/go-control-plane`** — official envoyproxy org,
proto-synced upstream on every commit, V2 removed. Istio Pilot, Envoy
Gateway, Gloo, and Consul all build on it. Building a custom xDS server
from scratch in 2026 is *legitimate for narrow use cases* (e.g., a
stateful-backend fleet with high IP/port churn) but is no longer the
default.

If today's design calls for a "Sovereign-shaped" control plane, the
2026 starting point is go-control-plane + your own logic on top, not a
from-scratch xDS implementation.

## A note on age and freshness

The talk describes a system built **2017-2025**. The talk's tools have
aged differently:

| Tool | Era of recommendation | 2026 status |
|------|----------------------|-------------|
| Envoy proxy | 2017 → present | Current. v1.38 (April 2026). xDS v3 final. |
| Open Service Broker API | 2016 → 2020 | Maintained but orphaned; Crossplane Compositions are the 2026 substrate |
| FastAPI | 2018 → present | Current. Still the recommended Python web-API framework. |
| AWS CloudFormation | 2011 → present | Alive but Terraform Stacks (HashiConf 2025 GA) is winning new mindshare |
| Packer | 2013 → present | Current. v1.14 (2025). Canonical for image baking. |
| **SaltStack** | 2011 → 2020 | **Declining**. Acquired by VMware → Broadcom. OSS future contested. Prefer Ansible or immutable AMIs. |
| Custom xDS server (Sovereign) | 2017 → 2022 | Replaced. Use `envoyproxy/go-control-plane`. |
| Sidecar pattern (Envoy) | 2017 → 2024 | Now a choice, not default. Istio Ambient (Nov 2024) and Linkerd micro-proxy are the 2026 alternatives. |

This isn't a list of mistakes in the talk — it's a list of where the
talk's specific tooling choices show their age. The *patterns* the
talk teaches outlive any specific tool; the *implementations* don't.

## How to use this matrix in code review

When defending a design that uses one of the talk's patterns:

1. **Cite the canonical name** from the matrix above (e.g., "Anti-
   Corruption Layer" instead of "validate at the boundary").
2. **If the bucket is CANONICAL**, point at the canonical source —
   reviewers can verify on their own time.
3. **If the bucket is NOVEL**, name what's novel and why it's worth
   the extension (the talk's contribution).
4. **If the bucket is CONTROVERSIAL**, acknowledge the canon's
   counter-position and state why the talk's pattern still fits.

This is the operating discipline of grounded design: every pattern
has a canonical anchor, and where you depart from canon you do so
deliberately and with a stated reason.
