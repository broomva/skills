# Changelog

All notable changes to **swapit** are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [0.4.0] — 2026-06-25

### Added — M4 geo-scaled procurement commons + taxonomy growth
- **`procurement_option` fact kind** — a public "where to buy" offer: a safer `alternative`
  sold by a `retailer` in a `region` (ISO-3166-1 alpha-2), with optional `url`, `price_min`/
  `price_max` + `currency` + `as_of`, `area`, `availability`. The commons becomes an open,
  detailed, organically-grown where-to-buy dataset anyone can use, scoped by geography.
  - **Hash key is identity-only `(alternative, retailer, region)`** — the same offer corroborates
    across users; a different region/retailer is a different fact (the scale axis). Price/url/area
    are refinable market data, not identity.
  - **Forward-only price freshening** — a corroboration carrying a strictly newer `as_of` updates
    the price/url/availability; an older one never regresses fresher data. The single bounded
    exception to payload-immutability, and it never touches the key.
- **`item_class` fact kind** — taxonomy growth: the community can propose a *new* item-class
  (corroboration-gated, ≥2 distinct contributors). Merge **ADDS** a new category but never
  overwrites a seed/known class.
- `swapit procure <item> --region <CC>` now surfaces known commons offers (where to buy, with
  links) and, given `--retailer`/`--url`/`--price-*`, **records** a found offer to the commons
  queue (gated by `sync --dry-run`) — the organic-growth loop.
- `swapit contribute procurement|item-class` CLI subcommands.
- Seed `seed/procurement.jsonl` — 14 durable retailer+region+URL offers across US/CO/DE/GB
  (prices left to grow organically; reference-grade `verified:false`).
- `selfheal` validates offer region codes (ISO-3166-1 alpha-2), alternative refs, and price ordering.
- **Cross-language hash parity** locked by pinned vectors (`tests/parity_vectors.json`) asserted
  in both the Python suite and broomva.tech's `content-hash` test — covers the two new kinds
  (incl. unicode + null fields) so corroboration can never silently break across the client/server.
- Tests: +16 (`tests/test_procurement.py`) → **88 skill tests**; privacy fuzz confirms a
  procurement fact can never carry `vendor`/`cost`/purchase data.

### Privacy seam (binding, unchanged set)
- The public procurement fact uses **`retailer`** + **`price_min`/`price_max`** — never the
  private **`vendor`**/**`cost`** (the Realm-2 record of where *you* bought and what *you* paid).
  `vendor`/`cost`/`procurer_report_ref` stay on the forbidden list; the new public fields
  (`retailer`, `region`, `price_*`, `currency`, `as_of`, `area`, `url`) are not private.

### Fixed (doc drift)
- SKILL.md + `commons/app/store.py` corrected to **corroboration-only** moderation (matching the
  0.3.1 code fix) — the stale "OR confidence ≥ 0.7" wording is gone.

## [0.3.1] — 2026-06-24

### Changed
- Graduated to the `broomva/skills` monorepo (Tier-3 → Tier-2): `npx skills add broomva/skills --skill swapit`.
- `swapit sync --configure --broomva` points the commons client at the hosted
  broomva.tech commons (Postgres + Better Auth); the standalone `commons/` FastAPI service
  remains the self-host option.

### Fixed (review hardening)
- **Commons moderation is corroboration-gated, not confidence-gated** — `confidence` is
  caller-supplied, so a single submitter could self-approve; a fact is now served only after a
  second independent contributor corroborates it.
- **`sync --configure` refuses a plaintext `http://` endpoint** for non-local hosts
  (contributions would otherwise be sent unencrypted); localhost http stays allowed for self-host.
- **A non-JSON commons response is treated as a transport failure** (no crash; best-effort retry).
- **An empty alternative selection no longer advances a swap** (the dashboard "choose a swap…"
  placeholder posted `""`).
- **`selfheal` tolerates a knowledge record missing `id`** (flags it instead of crashing).
- **Private-realm directories are chmod 0700** (inventory / photos / sync hold what you own).
- **Commons container runs as a non-root user.**

## [0.3.0] — 2026-06-24

### Added — M3 anonymized collaboration + networked commons
- `scripts/anonymize.py` — the **privacy gate**: allowlist fact builders (product /
  item-class→hazard / alternative) + a deep `scan_for_forbidden` that rejects any
  inventory-structural field. Content-addressed ids so identical facts corroborate.
- `scripts/sync.py` — commons client: contribution queue, `sync --dry-run` privacy preview,
  opt-in `--configure`, push/pull, and confidence+corroboration merge into local knowledge.
- `swapit contribute product|hazard|alternative` and `swapit sync` CLI modes.
- `commons/` — the networked **reference server** (FastAPI + SQLite): `POST /facts`
  (content-address + corroborate), `GET /facts?since=` (serve approved facts), `/health`.
  Moderation gate (corroboration ≥ 2 OR confidence ≥ 0.7); contributor tokens hashed, never
  stored raw; **server-side privacy backstop** mirrors the client gate. Dockerfile + Procfile
  for broomva.tech infra (Hostinger VPS) / Railway — **deploy gated on explicit go**.
- Tests: +15 skill tests (privacy fuzz — every inventory item is rejected by the gate; sync
  queue/merge/round-trip) and +7 commons API tests → **64 skill + 7 commons**.

### Privacy invariant (now enforced end to end)
- The contribution denylist is the *inventory-structural* fields (`room`, `quantity`, `usage`,
  `photos`, `cost`, `checklist`, …). `name`/`brand`/`url`/`title` carry legitimate public
  meaning on a knowledge fact and are admitted only via the allowlist builders — never copied
  from an owned item. Verified by a fuzz test asserting every real inventory item leaks a
  forbidden field (so the gate would always reject it).

## [0.2.0] — 2026-06-24

### Added — M2 live dashboard
- `swapit serve` (`scripts/server.py`) — stdlib `http.server`, localhost-only live dashboard.
  GET renders; `POST /api/*` writes back through `ops.py`. The browser is a thin view —
  the skill's filesystem state stays authoritative ("the agent is the app").
- `templates/dashboard.html` — self-contained Category-C dashboard (inline CSS/JS, no build):
  SVG band donut, summary cards, swap **kanban** by status, hazard chips, alternative chooser,
  live **checklist** toggles, **bookmark** add, status moves, and an add-item form.
- `scripts/ops.py` — extracted the single state-mutation write path so the CLI and the
  dashboard never diverge (DRY): `add_item`, `set_item_status`, `choose_alternative`,
  `add_task`, `toggle_task`, `update_procurement`, `complete_swap`, bookmark helpers.
  `cmd_add`/`cmd_swap`/`cmd_bookmark` refactored to delegate to it.
- Tests: +6 server tests (HTTP round-trip, persistence, choose/toggle/status, 404) → **43 total**.

### Changed
- CLI `add`/`swap`/`bookmark` now route mutations through `ops.py` (behavior unchanged; 37 M1
  tests still green).

## [0.1.0] — 2026-06-24

### Added — M1 foundation
- Two-realm, local-first state layer at `~/.config/swapit/` (`scripts/state.py`):
  shareable **knowledge** vs private **inventory**; event-sourced audit log + materialized JSON.
- Grounded, cited seed knowledge graph (`seed/*.jsonl`): 20 hazards, 40 item-classes,
  40 alternatives — sourced to NIEHS, ATSDR/CDC, EPA, FDA, ECHA, CA OEHHA, WHO, EWG.
- Exposure-risk engine (`scripts/risk.py`): `severity × presence × evidence × exposure ×
  frequency × condition` → high/medium/low bands + a swap-first ranking.
- CLI (`scripts/swapit.py`): `init · add · assess · list · swap · score · report · procure ·
  knowledge · rooms · bookmark · selfheal`.
- Self-contained Category-C HTML report (`scripts/report.py`): SVG band donut, per-room
  cards, swap-first table with risk bars and exposure-reduction percentages.
- Integrity validator (`scripts/selfheal.py`): knowledge edge + inventory ref + grounding
  checks; exits non-zero on errors.
- `procurer` handoff: `swapit procure <item>` emits a ready procurement brief.
- Privacy boundary contract (`state.PRIVATE_FIELDS` denylist + `SHAREABLE_*` allowlist) that
  the M3 anonymizer is built against — `name` and swap-side fields (checklist, bookmark
  url/title, cost/vendor) are private; `usage` sub-keys are the shareable risk signal.
- Robustness: corrupt inventory/knowledge files exit with a `selfheal` hint instead of a
  traceback; `selfheal` detects corrupt materialized inventory; atomic writes for state.
- Test suite (`tests/`): 37 tests — risk ranking, knowledge edges, self-heal, end-to-end CLI,
  privacy contract, HTML escaping, empty/corrupt-state handling.

### Reviewed
- Passed a cross-model adversarial review gate (P20, fresh-context devil's-advocate brief):
  7/10 → fixes applied (privacy contract inversion, `knowledge show --type`, negative-quantity
  guard, first-match checklist toggle, corrupt-file handling) → all findings resolved.

[Unreleased]: https://github.com/broomva/swapit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/broomva/swapit/releases/tag/v0.1.0
