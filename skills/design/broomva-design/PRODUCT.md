# Product

<!-- impeccable:product-schema 1 -->

## Platform

adaptive

## Users

AI coding agents are the primary operators. They use the skill while creating, adapting, reviewing, or migrating Broomva-branded digital products. Human designers and engineers are co-designers and reviewers who authorize migrations, judge rendered outcomes, and maintain the canonical system.

The products served may be web, native mobile, desktop, embedded, transactional, editorial, analytical, collaborative, or agentic. Their users and domain language come from each target product rather than from this skill.

## Product Purpose

The skill makes the Broomva design system reliably usable across arbitrary digital-product domains without reducing it to one archived application or one implementation stack. It gives agents enough durable design truth, semantic tokens, reusable adapters, composition guidance, and verification tooling to produce interfaces that remain recognizably Broomva while fitting the target product's actual users and jobs.

Success means an agent can select the smallest appropriate profile, materialize it safely, build with semantic roles and reusable primitives, and verify a responsive, accessible result without leaking unrelated agentic-work concepts into the product.

## Positioning

Unlike a component dump or a fixed application template, Broomva Design separates a platform-neutral brand foundation from implementation adapters, domain composition guidance, optional extensions, and hash-pinned source evidence. The safe materializer preserves incumbent files by default, supports closed-world profile changes, and verifies both the canonical source bundle and each installed target.

## Operating Context

Agents invoke the skill inside an existing or new product repository. They inspect the target's platform, incumbent design authority, accessibility baseline, domain objects, and user jobs; ask the deterministic preflight to recommend `foundation`, `web`, or `agentic-work`; confirm any explicit agentic or maintainer intent; materialize or consult the relevant assets; implement through semantic roles; then inspect and interact with representative states and device classes. Compatibility and evidence profiles remain progressively disclosed for existing automation and system maintenance.

Human reviewers use `DESIGN.md`, rendered specimens, dogfood receipts, and target-product evidence to judge conformance. Maintainers use the `full` profile, provenance records, checksum inventories, unit tests, and source verification when evolving or auditing the design system itself.

## Capabilities and Constraints

- Provides a canonical platform-neutral `DESIGN.md`, machine-readable semantic tokens, standalone foundation CSS, product-pattern guidance, and platform-adaptation guidance.
- Provides a neutral web adapter with 22 public React exports and an optional agentic-work extension with 31 exports and canonical long-running-work semantics.
- Preserves the curated source archive as hash-pinned evidence in the `full` profile while keeping archive-era domain vocabulary out of neutral profiles.
- Supports target-aware profile recommendation, grouped dry-run summaries, safe deterministic materialization, target verification, source verification, idempotent reruns, and explicit broader-to-smaller profile pruning.
- Refuses to overwrite differing incumbent files unless replacement is explicitly authorized with `--force`.
- Treats CSS and React as adapters rather than the design system itself; native and constrained platforms translate semantic roles into their own conventions.
- Does not infer a target product's information architecture, terminology, claims, or domain objects from Broomva's agentic products.
- Does not claim visual fidelity from code or checks alone; rendered and interaction evidence is required.

## Brand Commitments

The Broomva name, blackhole mark, blue-axis identity, semantic restraint, platform-neutral foundation, and product-specific composition model are binding. The system remains calm, precise, matte by default, and deliberately sparse in elevation and emphasis. Agentic-work vocabulary, Undertow, receipts, and Maestro patterns are optional domain extensions rather than universal brand requirements.

Canonical design rules live in `DESIGN.md`. Source fidelity and curation decisions live in `references/provenance.md`.

## Evidence on Hand

- `DESIGN.md` defines the canonical cross-platform design contract.
- `assets/portable/` contains independently checksummed product-neutral tokens, CSS, manifests, public entry points, declarations, and prompt contracts.
- `assets/system/` contains the hash-pinned curated archive evidence, component specimens, guidelines, templates, and Maestro reference application.
- `references/dogfood-receipt.md` records rendered and interactive validation across commerce, editorial, and agentic-work designs, including light and dark themes at `375px`, `768px`, and `1440px`.
- `references/product-patterns.md` and `references/platform-adaptation.md` define domain and platform translation boundaries.
- `scripts/materialize.py`, `tests/test_materialize.py`, and `tests/smoke.sh` provide deterministic materialization and verification evidence.

The skill has no evidence that every possible product category or native platform adapter has already been implemented. Future work must not fabricate such coverage; it must preserve the semantic contract and produce target-specific rendered evidence.

## Product Principles

1. Preserve identity while letting product truth determine composition.
2. Keep the neutral foundation independent from optional domain extensions.
3. Materialize the smallest sufficient profile and protect incumbent work by default.
4. Translate semantic roles across platforms instead of copying web dimensions blindly.
5. Require accessible interaction and rendered evidence before claiming conformance.

## Accessibility & Inclusion

Conforming outputs target WCAG 2.2 AA on the web and equivalent native-platform accessibility behavior. They preserve visible focus, semantic structure, persistent labels, accessible names, keyboard or native-input operation, approximately `44px` primary mobile targets, text scaling, reduced motion, and non-color state cues. Platform adapters must also account for safe areas, software keyboards, right-to-left layout, high-contrast modes, and platform-native accessibility semantics where applicable.
