# Canon and Citations — Grounded Best Practices

This file grounds every principle in the skill against the **established
canon of platform engineering, SRE/DORA, software architecture, and
staff+ engineering literature** (as of May 2026). Every claim has a
named, dated source. No invented citations.

Five canon clusters, each with the named sources that ground the
corresponding skill claims:

1. [Platform Engineering canon](#1-platform-engineering-canon)
2. [SRE & DORA canon](#2-sre--dora-canon)
3. [Architecture Patterns canon](#3-architecture-patterns-canon)
4. [Modern Tooling (2026 reality check)](#4-modern-tooling-2026-reality-check)
5. [Staff+ Engineering canon](#5-staff-engineering-canon)

The companion file [`07-contrasts.md`](07-contrasts.md) sorts the
skill's claims into three buckets — **canonical / novel / controversial**
vs the canon — and is the place to look for where the Atlassian-talk's
patterns either align with, extend, or run against established practice.

---

## 1. Platform Engineering Canon

**The talk's "platform team" maps onto a canonical pattern.** Skelton &
Pais's *Team Topologies* (2019, IT Revolution) defines four canonical
team types — **stream-aligned**, **platform**, **enabling**, and
**complicated-subsystem** — and three interaction modes — **collaboration**,
**X-as-a-service**, and **facilitating**. The Atlassian load-balancing
team is a textbook platform team: small headcount, owning a self-service
contract (OSB) over a complicated subsystem (the Envoy fleet), serving
~1000 stream-aligned services as customers via X-as-a-service. The
book's "Thinnest Viable Platform" rule — *start with the minimum that
unblocks consumers, even if "just a wiki page"* — is the principle that
governs which features to build first.

**Conway's Law makes the architecture inevitable.** Melvin Conway's 1968
*Datamation* paper (after rejection by HBR for being "anecdotal") states:
*"Any organization that designs a system… will inevitably produce a
design whose structure is a copy of the organization's communication
structure."* The **Inverse Conway Maneuver** — deliberately designing
team boundaries to produce the desired architecture — was coined by
LeRoy & Simons in the December 2010 *Cutter IT Journal*. Forsgren,
Humble & Kim's *Accelerate* (2018) gives the empirical backing:
*"organizations should evolve their team and organizational structure
to achieve the desired architecture."* The Atlassian shape — one small
platform team producing one coherent control plane (Sovereign) — is an
Inverse-Conway construct.

**The 2026 Internal Developer Platform (IDP) canon.** Backstage (Spotify,
donated to CNCF September 2020, Incubating since March 2022, Apache-2.0)
is the dominant open-source framework — current stable **v1.50.0** (April
2026), 3,400+ adopting organizations, 2M+ developers. Backstage gives
what Sovereign+OSB didn't: a unified developer-facing portal (Software
Catalog + TechDocs + Software Templates + Scaffolder). Sovereign+OSB
had what Backstage still doesn't: an opinionated *runtime*. Humanitec's
**State of Platform Engineering Reports** (Volumes 1-3, 2022-2024;
Volume 4 in 2025 by platformengineering.org with Broadcom sponsorship)
push the **"Platform-as-a-Product"** thesis — *"organizations that mandate
adoption by top-down decree underperform those that build a platform so
useful that teams choose it voluntarily."* This is the canon's direct
challenge to the talk's "forced migration via removed alternatives".

**Anti-patterns.** Thoughtworks's Technology Radar marked
*"Miscellaneous platform teams"* as **Hold** (March 2022): platform
labels applied to "initiatives lacking clear outcomes or a well-defined
set of customers" produce ivory-tower teams. The antidote — *"Platform
engineering product teams"* — sits in **Adopt**. Gregor Hohpe's *The
Software Architect Elevator* (O'Reilly, 2020) names the deeper failure
mode: architects who don't ship code lose feedback on the consequences
of their decisions. The Atlassian team's structural protection was that
they got paged for what they shipped — a small platform team with deep
operational ownership *can't* go ivory-tower.

### Bibliography (Platform Engineering)

- Skelton, M., & Pais, M. (2019). *Team Topologies*. IT Revolution. ISBN 9781942788812.
- Conway, M. E. (1968, April). "How Do Committees Invent?" *Datamation*, pp. 28-31. https://www.melconway.com/Home/pdf/committees.pdf  (Issue number disputed in secondary citations — Wikipedia intro uses 14(4), references section uses 14(5); melconway.com itself lists only "April 1968".)
- LeRoy, J., & Simons, M. (2010, December). "Dealing with Creaky Legacy Platforms." *Cutter IT Journal*. (Origin of "Inverse Conway Maneuver".)
- Forsgren, N., Humble, J., & Kim, G. (2018). *Accelerate*. IT Revolution.
- Backstage (CNCF Incubating). https://backstage.io/ | CNCF page: https://www.cncf.io/projects/backstage/
- Humanitec. *State of Platform Engineering Reports* Vols 1-3 (2022-2024). https://humanitec.com/state-of-platform-engineering
- platformengineering.org / Broadcom. *State of Platform Engineering Report Vol 4* (2025). https://platformengineering.org/
- Thoughtworks Technology Radar: "Miscellaneous platform teams" (Hold, March 2022). https://www.thoughtworks.com/radar/techniques/miscellaneous-platform-teams
- Hohpe, G. (2020). *The Software Architect Elevator*. O'Reilly. Excerpted: https://martinfowler.com/articles/architect-elevator.html

---

## 2. SRE & DORA Canon

**Toil discipline.** The canonical definition lives in Chapter 5 of the
**Google SRE Book** (Beyer et al, 2016, O'Reilly), written by Vivek Rau:
toil is work that is *"manual, repetitive, automatable, tactical, devoid
of enduring value, and that scales linearly as a service grows."* The
talk's "churn is a smell" maps directly onto the *scales-linearly*
criterion. Google's structural commitment: **50% engineering minimum,
25% on-call maximum, 25% other ops maximum** — an explicit numeric cap
enforced at management level. The talk's "50-70% building / 20-30%
maintaining / 10-20% operating" ratio is the same shape, slightly
rebalanced toward building.

**Error budgets and the velocity/reliability control loop.** Chapter 3
of the 2016 SRE Book ("Embracing Risk") introduces the error-budget
mechanism: quantify reliability as a budget that can be spent on
velocity. When budget is healthy, product ships freely; when drained,
releases halt until recovery. This is the conceptual home of the talk's
implicit "stability + change" balance.

**Symptom-based alerting and runbook discipline.** The **Site Reliability
Workbook** (Beyer et al, 2018, O'Reilly) Chapter 5 ("Alerting on SLOs")
prescribes alerting on user-visible symptoms (SLO burn rate), not
internal causes. Chapter 8 ("On-Call") defines the canonical playbook
structure: one entry per alert, with severity/impact, debugging
suggestions, mitigation steps. The talk's *log message catalog + metric
catalog + failure mode catalog + recovery procedures* is this canonical
structure restated.

**DORA's four keys.** *Accelerate* (Forsgren/Humble/Kim, 2018) codifies
deployment frequency, lead time for changes (throughput) + change
failure rate, MTTR (stability). The book's central empirical finding:
*throughput and stability are not in tension; quality equals speed.*
Loosely-coupled architecture (which the Atlassian platform exemplifies)
correlates with elite performance on all four metrics.

**The platform-engineering J-curve.** The **2024 DORA Report** (Google
Cloud, ~39,000 respondents) studied platform engineering as a primary
theme. The headline finding: IDPs produce +8% individual productivity
and +10% team productivity — *but* −8% throughput and −14% stability in
the average implementation (the **J-curve effect**: temporary dip
before improvements manifest as the platform matures). The cure is
user-centricity — "platform as product" — with continuous developer-
customer feedback.

**AI as amplifier (the 2025 finding).** The **2025 DORA Report** —
*State of AI-Assisted Software Development* — is the canonical reference
for the talk's AI-coupling risk claim. 90% of respondents use AI at
work (median 2h/day). AI adoption now positively correlates with
throughput — *and* with higher instability, more change failures, more
rework. *"Individual productivity boosts are frequently lost to
'downstream disorder.'"* When platform quality is high, AI's effect is
strong and positive; when platform quality is low, AI's effect is
negligible. The talk's framing — AI amplifies maintenance burden — is
exactly this finding.

**The metrics debate.** Will Larson (*lethain.com*) argues write
strategy first, then measure. Gergely Orosz & Abi Noda's January 2024
survey of 17 tech companies found no company uses DORA or SPACE
wholesale; everyone uses context-specific blends. Lorin Hochstein
(resilience engineering, ex-Netflix): *"Resilience is about the stuff
that isn't visible through the metrics."* The talk's posture — name the
failure modes, catalog them, accept that maintenance is engineering
work — sits in exactly this debate.

### Bibliography (SRE / DORA)

- Beyer, B., Jones, C., Petoff, J., & Murphy, N. R. (Eds.). (2016). *Site Reliability Engineering*. O'Reilly. https://sre.google/books/
- Beyer, B., Murphy, N. R., Rensin, D. K., Kawahara, K., & Thorne, S. (Eds.). (2018). *The Site Reliability Workbook*. O'Reilly. https://sre.google/workbook/
- Forsgren, N., Humble, J., & Kim, G. (2018). *Accelerate*. IT Revolution.
- DORA / Google Cloud. (2024). *Accelerate State of DevOps Report 2024*. https://dora.dev/research/2024/dora-report/
- DORA / Google Cloud. (2025). *State of AI-Assisted Software Development (2025 DORA Report)*. https://cloud.google.com/resources/content/2025-dora-ai-assisted-software-development-report
- Larson, W. *Measuring an Engineering Organization*. https://lethain.com/measuring-engineering-organizations/
- Orosz, G., & Noda, A. (2024, January 16). *Measuring Developer Productivity: Real-World Examples*. The Pragmatic Engineer. https://newsletter.pragmaticengineer.com/p/measuring-developer-productivity-bae
- Hochstein, L. *Surfing Complexity* blog. https://surfingcomplexity.blog/

---

## 3. Architecture Patterns Canon

**Bounded Context and Anti-Corruption Layer (Evans 2003).** Evans's
*Domain-Driven Design* (Addison-Wesley) introduces the **Anti-Corruption
Layer** at p. 364: *"As a downstream client, you create an isolating
layer to provide your system with functionality of the upstream system
in terms of your own domain model. This layer talks to the other system
through its existing interface, requiring little or no modification to
the other system."* The talk's "validate at the boundary" is the
*semantic-translation* form of the ACL responsibility — ACL kicks in
when upstream and downstream have *different models that need
translation*; pure schema validation is a complementary boundary concern
(closer to defensive programming / type narrowing). The platform's edge
layer maps onto Evans's **Open Host Service** (p. 374) — the upstream
half of a context map, with a published interface multiple consumers
translate via their own ACLs.

**Gateway pattern + Strangler Fig (Fowler 2002, 2004).** Fowler's
**Gateway** pattern (PoEAA p. 466) is the parent of every API-gateway
and sidecar-proxy variant: *"a simple wrapper… construct an interface
that supports [what our code needs to do with the external system]
clearly and directly."* The talk's "centralize cross-cutting concerns
at the edge" is Fowler's argument that adapter code lives in one named
place. The **Strangler Fig Application** (Fowler, 2004; renamed
2019-04-29) **IS** the forced-migration pattern the talk describes:
*"gradually create a new system around the edges of the old, letting
it grow slowly over several years until the old system is strangled."*
Microsoft's Azure Architecture Center adopts the pattern verbatim
(learn.microsoft.com/en-us/azure/architecture/patterns/strangler-fig).

**Fitness functions (Ford, Parsons, Kua 2017; 2nd ed. 2023).** *Building
Evolutionary Architectures* formalizes architecture characteristics as
*continuously-tested constraints*. A fitness function is *"any
mechanism that provides an objective integrity assessment of some
architecture characteristic(s)"* — classified along axes: atomic vs
holistic, triggered vs continuous, static vs dynamic. The talk's "churn
is a smell" is a textbook **atomic, triggered, dynamic fitness function**:
commit-frequency-per-file over a rolling window, threshold-gated in
CI. "Coupling accretes silently" has a direct answer: ArchUnit-style
dependency rules + connascence audits, indexed in the 2nd edition's
subtitle *Automated Software Governance*.

**Sagas for async task orchestration (Richardson 2018; Ford et al
2021).** *Software Architecture: The Hard Parts* catalogs **eight saga
patterns** named by three binary axes — communication (sync/async),
consistency (atomic/eventual), coordination (orchestrated/choreographed).
The FastAPI→SQS→Worker→DynamoDB pattern matches **Parallel Saga**
(async-eventual-orchestrated) in *shape*; whether it implements full
*transactional* saga semantics (compensating transactions on failure)
depends on the worker's design — the talk doesn't describe compensation
explicitly, so the pattern is more precisely a workflow with the
Parallel Saga shape. Richardson's saga entry
(microservices.io/patterns/data/saga.html) is the canonical reference:
*"a sequence of local transactions… each transaction publishes a
message or event that triggers the next transaction"*, with compensating
transactions for rollback. The DynamoDB row is the orchestrator's
persisted state machine.

**12-Factor App, Factor V (Wiggins 2011).** Factor V — *"The twelve-
factor app uses strict separation between the build, release, and run
stages"* — defines three immutable stages: **build** (codebase →
executable bundle), **release** (build + config → tagged release), **run**
(execute selected release). *"Releases are an append-only ledger and a
release cannot be mutated once it is created."* The talk's three IaC
layers — image / infra / runtime — map 1:1 onto Factor V's three stages.

**AWS Well-Architected Framework.** Six pillars (Operational Excellence,
Security, Reliability, Performance Efficiency, Cost Optimization,
Sustainability). Operational Excellence prescribes async decoupling
("Implement loosely coupled dependencies", OPS-05) with SQS named
explicitly. Reliability (REL08, "Implement change") requires IaC and
immutable infrastructure as the named mechanism. Loosely coupled
dependencies + graceful degradation + bounded retries are the three
core distributed-systems patterns — all three present in the talk's
architecture.

**Architecture Decision Records (Nygard 2011).** The lightweight ADR
template — **Title** (numbered noun phrase), **Context** (forces at
play), **Decision** (active voice), **Status**, **Consequences** —
captures architectural decisions for future readers. Thoughtworks moved
ADRs to **Adopt** in 2018. The skill itself can be read as an
ADR-shaped archive: each principle is one decision with context and
consequences.

### Bibliography (Architecture Patterns)

- Evans, E. (2003). *Domain-Driven Design*. Addison-Wesley. ISBN 0-321-12521-5. Bounded Context p. 335; Anti-Corruption Layer p. 364; Open Host Service p. 374.
- Fowler, M. (2002). *Patterns of Enterprise Application Architecture*. Addison-Wesley. ISBN 0-321-12742-0.
- Fowler, M. (2004; renamed 2019). "Strangler Fig Application." https://martinfowler.com/bliki/StranglerFigApplication.html
- Fowler, M., & Lewis, J. (2014, March 25). "Microservices." https://martinfowler.com/articles/microservices.html
- Ford, N., Parsons, R., Kua, P., & Sadalage, P. (2023). *Building Evolutionary Architectures: Automated Software Governance* (2nd ed.). O'Reilly. ISBN 978-1-492-09754-9.
- Ford, N., Richards, M., Sadalage, P., & Dehghani, Z. (2021). *Software Architecture: The Hard Parts*. O'Reilly. ISBN 978-1-492-08689-5.
- Richardson, C. (2018). *Microservices Patterns*. Manning. ISBN 978-1-617-29454-9.
- Richardson, C. "Pattern: Saga." https://microservices.io/patterns/data/saga.html
- Wiggins, A. (2011). *The Twelve-Factor App*. https://12factor.net/ | Factor V: https://12factor.net/build-release-run
- AWS. *AWS Well-Architected Framework*. https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html
- Brown, S. *The C4 Model*. https://c4model.com/
- Nygard, M. (2011, November 15). "Documenting Architecture Decisions." https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- Microsoft Learn. "Strangler Fig Pattern." https://learn.microsoft.com/en-us/azure/architecture/patterns/strangler-fig

---

## 4. Modern Tooling (2026 Reality Check)

The Atlassian stack was built 2017-2025. The talk's tooling choices are
honest about their era; this section says which are still current and
which have rotated.

**Envoy v1.38 (April 2026); xDS v3 final.** Envoy's official versioning
policy: v3 is the final major API version, supported "forever" — no v4
on the roadmap. The Atlassian-era custom xDS server (FastAPI polling S3)
was a 2017 workaround; the **2026 canonical recommendation is
`github.com/envoyproxy/go-control-plane`** — official envoyproxy org,
proto-synced upstream, embeddable. Istio Pilot, Envoy Gateway, Gloo,
and Consul all build on it. Streaming gRPC + ADS (Aggregated Discovery
Service) with Delta-xDS (incremental updates) is the production default
for large fleets.

**OSB v2.17 not deprecated, but effectively orphaned.** The spec at
`github.com/openservicebrokerapi/servicebroker` is technically alive
(969 commits, low-volume issues, ongoing CF SMWG community calls), but
OpenShift formally deprecated OSB in OpenShift 4 in favor of OLM
(Operator Lifecycle Manager). For Kubernetes-native shops, **Crossplane
Compositions** are the 2026 idiomatic substrate.

**Crossplane 2.0 (August 12, 2025); v2.2 current.** Composite Resources
(XRs) and Composite Resource Definitions (XRDs) are the 2026 vendor-
neutral platform-API pattern. Key 2.0 shifts: (1) Compositions can
include any K8s resource (not just managed infrastructure); (2)
namespace-first by default; (3) composition functions are now the only
supported composition model; (4) new Operations type for one-off /
scheduled / event-driven workflows.

**Istio Ambient Mesh GA November 7, 2024 (Istio 1.24).** Architecture:
per-node `ztunnel` DaemonSet (Rust, L4 mTLS via HBONE) + waypoint
proxies (Envoy, L7, per-namespace/service). Published savings: **~90%+
proxy resource reduction** vs sidecars. *Sidecars not deprecated* —
Istio explicitly: *"Sidecars remain first-class citizens."* Linkerd
disagrees — their Rust micro-proxy (linkerd2-proxy) sidecars are so
light that Buoyant benchmarks claim Ambient uses more total resources;
they argue sidecars preserve a clean per-pod security boundary. The
talk's "Envoy as sidecar" assumption is now a *choice*, not the default.

**SMI archived September 25, 2023.** The Service Mesh Interface
consolidated effort into the Kubernetes Gateway API's **GAMMA**
initiative (SIG-Network). Any 2026 design citing SMI primitives is
using a dead spec; the canonical surface is now Gateway API HTTPRoute/
GRPCRoute/TLSRoute + GAMMA extensions.

**Backstage v1.50 (April 2026); Spotify Portal GA Oct 2025.** Build-vs-
buy has tilted to *buy or hybrid* for non-Spotify-scale orgs. Port.io's
published 3-year TCO for self-hosted Backstage at a 300-developer org:
**~$3.25M**. Gartner forecasts 80% of large engineering orgs will have
platform teams by 2026 (up from 45% in 2022). The 2026 question is no
longer "should we build this in-house?" but "what golden paths
differentiate our buy/hybrid platform?"

**SaltStack in decline.** Acquired by VMware (2020), then Broadcom
(2023). Now "VMware Cloud Foundation SaltStack" with commercial support
through **October 2028**; OSS community future is contested (GitHub
discussion #67028 documents the uncertainty). For new builds in 2026:
prefer **Ansible** (Red Hat / IBM, dominant), or move to **bake-don't-
configure** patterns (Packer + immutable AMIs).

**Terraform Stacks GA at HashiConf 2025; CDKTF deprecated Dec 2025.**
The modern IaC composition primitive coordinates deployment of
interdependent modules with linked Stacks for cross-stack outputs.
OpenTofu (Linux Foundation, MPL-2.0) is the BSL-relicensing fork.
Pulumi (typed IaC in TS/Python/Go/C#/Java) growing ~45% YoY in
developer-heavy orgs.

**WASM filters are orthogonal to the sidecar debate.** Envoy's WASM
filter chains (proxy-wasm ABI; V8/WAMR/Wasmtime runtimes) run *inside*
Envoy (sidecar or ambient waypoint) — they replace per-language custom
C++ filters, not the sidecar pattern itself. Istio formalized this
with `WasmPlugin` CRD. For the Atlassian-era pattern, WASM is the
natural place to land what used to be in-house Envoy filter forks.

**Edge moved beyond the CloudFront model.** Three architectural camps:
**Cloudflare Workers** (V8 isolates, 330+ PoPs, sub-5ms cold starts;
KV/R2/D1/Durable Objects/Queues/Hyperdrive on one bill); **Vercel Edge
Functions / Fluid Compute** (V8 isolates + Node.js-subset Edge Runtime,
19 regions, dominant for Next.js SSR); **Fastly Compute** (Wasmtime).
The 2026 convergence: placement (edge vs origin) is becoming a platform
optimization rather than a deployment decision. A meaningful slice of
what was sidecar-Envoy logic in 2017-2020 (auth, rate-limit, header
rewrite, A/B routing) now lives in Workers / Edge Functions.

### Bibliography (Modern Tooling)

- Envoy Project. *xDS REST and gRPC protocol* (1.39.0-dev docs). https://www.envoyproxy.io/docs/envoy/latest/api-docs/xds_protocol
- envoyproxy/envoy. *Releases* (v1.38.0 April 23, 2026). https://github.com/envoyproxy/envoy/releases
- envoyproxy/go-control-plane. https://github.com/envoyproxy/go-control-plane
- Open Service Broker API. https://github.com/openservicebrokerapi/servicebroker
- Red Hat. *OpenShift 4 OSB deprecation*. https://access.redhat.com/documentation/en-us/openshift_container_platform/4.1/html/applications/service-brokers
- Crossplane. *Announcing Crossplane 2.0* (Aug 12, 2025). https://blog.crossplane.io/announcing-crossplane-2-0/
- Istio. *Fast, Secure, and Simple: Istio's Ambient Mode Reaches GA in v1.24* (Nov 7, 2024). https://istio.io/latest/blog/2024/ambient-reaches-ga/
- CNCF. *CNCF Archives the Service Mesh Interface (SMI) Project* (Sept 25, 2023). https://www.cncf.io/blog/2023/10/03/cncf-archives-the-service-mesh-interface-smi-project/
- Backstage v1.50.0. https://github.com/backstage/backstage
- Spotify Portal. https://backstage.spotify.com/
- Tasrie IT Services. *Port vs Backstage vs Cortex (2026)*. https://tasrieit.com/blog/port-vs-backstage-vs-cortex-developer-portal-comparison-2026
- HashiCorp. *Packer 1.14*. https://developer.hashicorp.com/packer
- HashiCorp. *Terraform Stacks (HashiConf 2025 GA)*. https://www.hashicorp.com/en/blog/scale-infrastructure-with-new-terraform-and-packer-features-at-hashiconf-2025
- Broadcom. *VMware Cloud Foundation SaltStack support through Oct 2028*. https://knowledge.broadcom.com/external/article/413088
- Tetrate. *Wasm extensions and Envoy extensibility*. https://tetrate.io/blog/wasm-modules-and-envoy-extensibility-explained-part-1
- Buoyant. *Sidecars or Sharing*. https://www.buoyant.io/blog/sidecars-or-sharing-a-practical-guide-to-selecting-your-service-mesh

---

## 5. Staff+ Engineering Canon

**Three pillars of the staff role (Reilly 2022).** *The Staff Engineer's
Path* (O'Reilly) organizes the role around **Big Picture Thinking,
Execution, Leveling Up**. The third pillar (Part III) is the canonical
citation for the talk's **colleague-as-customer model**. Its opening
chapter is *"You're a Role Model Now (Sorry)"* (the parenthetical is
Reilly's, addressing the passive role-modelling dimension); the
companion chapter *"Good Influence at Scale"* covers the active form,
including her framing that influence at scale is *delegated through
systems*, not delivered through individual heroics — *"Creating robots,
policies, and processes that reinforce your message scales further than
being a guardrail for individual colleagues."* Her sponsorship reframe:
*"Opportunities can be much more valuable than advice. Share the
spotlight in your team."*

**Mentoring vs teaching (Fournier 2017).** *The Manager's Path*
Chapter 2 ("Mentoring") opens: *"An opportunity to mentor gives you a
chance to learn how to be a manager — in a safe environment, as people
rarely get fired for bad mentorship."* The chapter distinguishes career
mentoring from technical mentoring and warns against the **Alpha Geek
anti-pattern** — the senior engineer who answers questions instead of
growing the asker. The talk's "mentoring ≠ teaching" distinction is
Fournier's exact framing.

**Tech Lead archetype (Larson 2021).** *Staff Engineer* (staffeng.com)
defines **four archetypes**: Tech Lead, Architect, Solver, Right Hand.
The talk's speaker — long-tenured in one stack, owning a system over
many years, partnered with one or two managers — is unambiguously the
**Tech Lead archetype**: *"guides the approach and execution of a
particular team. Partners closely with a single manager…the most
accessible archetype to attain your first Staff engineering role."*
Tech Lead and Architect *"work with the same people on the same
problems for years, developing a tight sense of team"* — the talk's
exact pattern.

**Curse of knowledge (Camerer/Loewenstein/Weber 1989; Heath brothers
2007).** Coined in the **Journal of Political Economy** 97(5):1232-1254:
*"Better-informed agents are unable to ignore private information even
when it is in their interest to do so; more information is not always
better."* Market forces reduce the bias by ~50% but never eliminate it.
The Heath brothers' *Made to Stick* (2007) is the popularization
vector, naming Curse of Knowledge as the *"arch villain"* of
communication and illustrating with **Elizabeth Newton's 1990 Stanford
"tappers and listeners" experiment**: tappers predicted listeners would
identify their tapped songs 50% of the time; actual rate was 2.5%.

**Radical Candor (Scott 2017).** The 2×2: **Care Personally** ×
**Challenge Directly**. Four quadrants: Radical Candor (both high);
**Obnoxious Aggression** (challenge without care); **Ruinous Empathy**
(care without challenge — *"by far the most common quadrant"*);
Manipulative Insincerity (neither). The talk's "diplomacy is an
engineering skill" maps onto Care Personally; "anticipate conflict"
maps onto Challenge Directly. The most-cited operational guidance:
*solicit feedback before giving it.* Scott's prompt: *"What could I do
or stop doing that would make it easier to work with me?"*

**Andy Grove's leverage equation (1983).** *High Output Management*:
*"A manager's output = the output of his organization + the output of
the neighbouring organizations under his/her influence."* This **is**
the formal statement of the colleague-as-customer model. The senior
engineer who spends more time helping colleagues than typing code is
not deviating from output — they are maximizing it via Grove's
equation. *"If you gather and share information you're a manager.
More specifically, a know-how manager"* — the staff-IC equivalent.

**Mentoring research (Kram 1985; Allen et al 2004).** Kram's **two-
function model**: career functions (sponsorship, coaching, exposure,
protection, challenging assignments) + psychosocial functions (role-
modelling, acceptance, counselling, friendship). Allen et al's
**Journal of Applied Psychology** 89(1) meta-analysis: psychosocial
benefits and subjective career satisfaction show stronger effects than
compensation/promotion. The implication for "mentoring ≠ teaching":
the value senior engineers create through mentoring shows up most
reliably in the psychosocial dimension, not in API-tutorial outcomes.

**Psychological safety (Edmondson 1999, 2018).** *Administrative Science
Quarterly* 44(2):350-383: *"A shared belief held by members of a team
that the team is safe for interpersonal risk taking"* — safe to ask
questions, admit ignorance, raise concerns. Edmondson's 51-team
manufacturing study found psychological safety predicts learning
behaviour, which mediates team performance. The book-length treatment
is *The Fearless Organization* (Wiley, 2018). *Note*: the often-cited
"four stages of psychological safety" is Timothy R. Clark's, not
Edmondson's.

### Bibliography (Staff+ Engineering)

- Reilly, T. (2022). *The Staff Engineer's Path*. O'Reilly. ISBN 9781098118730.
- Fournier, C. (2017). *The Manager's Path*. O'Reilly. ISBN 9781491973899.
- Larson, W. (2021). *Staff Engineer: Leadership Beyond the Management Track*. Stripe Press. https://staffeng.com/ | Archetypes: https://staffeng.com/guides/staff-archetypes/
- Camerer, C., Loewenstein, G., & Weber, M. (1989). "The Curse of Knowledge in Economic Settings." *Journal of Political Economy* 97(5):1232-1254. DOI 10.1086/261651. https://www.cmu.edu/dietrich/sds/docs/loewenstein/CurseknowledgeEconSet.pdf
- Heath, C., & Heath, D. (2007). *Made to Stick*. Random House. ISBN 9781400064281.
- Newton, E. L. (1990). *The Rocky Road From Actions to Intentions* (Doctoral dissertation, Stanford). Source of the tappers-and-listeners experiment.
- Scott, K. (2017). *Radical Candor*. St. Martin's Press. https://www.radicalcandor.com/our-approach
- Grove, A. S. (1983). *High Output Management*. Random House. ISBN 9780679762881.
- Kram, K. E. (1985). *Mentoring at Work*. Scott Foresman. ISBN 9780673156174.
- Allen, T. D., Eby, L. T., Poteet, M. L., Lentz, E., & Lima, L. (2004). "Career Benefits Associated With Mentoring for Protégés: A Meta-Analysis." *Journal of Applied Psychology* 89(1):127-136. DOI 10.1037/0021-9010.89.1.127.
- Edmondson, A. C. (1999). "Psychological Safety and Learning Behavior in Work Teams." *Administrative Science Quarterly* 44(2):350-383. DOI 10.2307/2666999.
- Edmondson, A. C. (2018). *The Fearless Organization*. Wiley. ISBN 9781119477242.
- Hogan, L. (2019). *Resilient Management*. A Book Apart. https://resilient-management.com/ | Feedback Equation: https://larahogan.me/blog/feedback-equation/

---

## How to cite this skill (with grounding)

When the skill informs a design decision, cite both the talk source and
the canonical grounding:

> Pattern X applied per `architecture-design-principles` skill
> (`~/.agents/skills/architecture-design-principles/`), grounded in
> [canonical source] — see `references/06-canon-and-citations.md` §N.

The contrast matrix in [`07-contrasts.md`](07-contrasts.md) tracks
**where** each pattern is canonical, novel, or controversial — useful
when arguing the design in code review.
