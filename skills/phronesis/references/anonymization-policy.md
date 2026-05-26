# Anonymization Policy (M7)

This is the canonical reference for `core/anonymize.py::AnonymizationPolicy`
and the 14×3 canary release gate that backs it.

## Why this exists

Engagement extracts flow back into the workspace knowledge graph
(`research/entities/`) as Bloomberg-style "industry color" — the
learning survives, the tenant identity does not. The
`AnonymizationPolicy` is the single source of truth for what counts as
"identifying" and gets stripped.

The 14-canary-token release gate
(`tests/integration/test_anonymization_canary.py::TestM7CanaryReleaseGate`)
is the proof. 14 tokens × 3 fixtures = 42 release-gate tokens. If any
token leaks through any deliverable on any fixture, the push is blocked.

See also: ADR 0005 (anonymization-strict-by-default), ADR 0007
(canary-test-as-release-gate), design spec §7.2.

## What gets stripped (default policy)

`AnonymizationPolicy()` enables every transform. The default policy is
the bias for safety — opt-out is explicit, never the absence of
opt-in.

| Transform | What it does | Token replacement |
|---|---|---|
| `strip_tenant_slug` | Literal `tenant.tenant_slug` substring removal | `<tenant>` |
| `strip_tenant_name` | Literal `tenant.name` substring removal | `<tenant>` |
| `strip_personal_names` | Sponsor name + regex-detected `(Mr.|Mrs.|Sr.|Sra.|Dr.|Dra.) Capitalized Words` + multi-word capitalized phrases | `<person>` (allowlisted frameworks + roles + regions pass through) |
| `replace_currency_with_bands` | `$\d[\d,]*` → magnitude band | `low-6-figures USD` etc. — see currency bands below |
| `replace_dates_with_relative` | ISO date / `YYYY-Q[1-4]` / 4-digit year | `<engagement-date>`, `<engagement-quarter>`, `<engagement-year>` |
| `replace_locations_with_regions` | Specific CO + LATAM city/country names | `<latam-region>` |
| `redact_terms` (caller-supplied) | Literal substring removal | `<redacted>` |

## Currency bands

```
< $1,000       → sub-low-4-figures USD
< $10,000      → low-4-figures USD
< $100,000     → mid-5-figures USD
< $1,000,000   → low-6-figures USD
< $10,000,000  → low-7-figures USD
< $100,000,000 → low-8-figures USD
< $1B          → low-9-figures USD
≥ $1B          → 9+-figures USD
```

A deliverable that names `$640,000` ends up with `low-6-figures USD` —
the *order of magnitude* of the lever survives, the exact figure does
not.

## Name allowlist

`core/anonymize.py::_NAME_ALLOWLIST` keeps tokens that LOOK like
names but are domain language (frameworks, roles, regions). Expanding
the allowlist is a deliberate decision; never add a tenant-specific
token there.

## Engagement-derived redact terms

`core/extraction/anonymizer.py::_collect_engagement_redact_terms()`
walks the journal and surfaces additional terms that the strict policy
might miss:

1. Every `INTERVIEW_LOGGED.interviewee` value (modulo the sponsor —
   `anonymize()` already strips that). The interviewee name with any
   `(Role)` suffix removed.
2. (Phase 2) Project codenames from `ROADMAP_STEP_PROPOSED.title`.

These get appended to `policy.redact_terms` before redaction.

## Canary token convention (M7)

Each fixture in `tests/fixtures/` declares EXACTLY **14 canary tokens**
in a `<FIXTURE>_CANARY_TOKENS` list:

- `tropico_renovables.py::TROPICO_CANARY_TOKENS` — 5 tenant variants + 3 sponsor variants + 6 currency amounts
- `acme_bank.py::ACME_BANK_CANARY_TOKENS` — tenant + sponsor + 4 interviewees + 3 products + 3 cities + 1 currency
- `nova_construction.py::NOVA_CONSTRUCTION_CANARY_TOKENS` — 3 tenant variants + sponsor + interviewees + 2 projects + 1 city + 3 currency amounts

Total release-gate corpus: **14 × 3 = 42 tokens**.

The `TestM7CanaryReleaseGate::test_release_gate_14x3_tokens_zero_leaks`
test asserts:
1. Each fixture declares exactly 14 tokens.
2. Every fixture renders 7 deliverables.
3. Every (fixture × deliverable × token) combination shows zero leaks.

A leak in any single cell of the 42-token × 21-file matrix blocks the
push.

## When to extend the policy

Failures arrive as canary-test failures. Workflow:

1. Canary fires → diff the failing deliverable to find the leaking
   string.
2. Decide: is it tenant-identifying? If yes, strengthen the policy.
   If no, the token shouldn't be in the canary list — fix the
   fixture.
3. Strengthen the policy:
   - **Tenant-name variant**: nothing to do — `strip_tenant_name` is
     literal-substring; if it's not catching, the variant isn't in
     `tenant.name`. Check the fixture.
   - **Personal name**: extend `_NAME_RE` regex coverage OR add an
     explicit `redact_terms` entry on the engagement.
   - **Location**: append to `_LOCATIONS` in `core/anonymize.py`.
   - **Currency**: should already bucket; if a verbatim amount
     survived, the regex didn't match — check for non-`$` prefixes
     (e.g. `USD 640,000`).
4. Re-run canary; commit when green.

## When to opt-out

Almost never. Opt-out (passing a permissive `AnonymizationPolicy` with
flags `False`) is reserved for:

- Tenant-private archive snapshots (where the tenant explicitly wants
  raw content stored).
- Per-engagement compliance review where the operator needs to verify
  what's NOT being stripped.

Never opt-out for knowledge-graph extraction. Use the strict default.
