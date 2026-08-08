# Report schema v1

The JSON output is stable at `schema_version: 1`.

## Top level

| Field | Meaning |
|---|---|
| `generated_at`, `since`, `window_days` | UTC report time, start boundary, and selected count of local calendar days |
| `cost_semantics` | mandatory list-price/subscription disclaimer |
| `pricing` | bundled/custom source label, `as_of`, and source URLs; never a local path |
| `overall` | aggregate token and cost fields |
| `by_model[]` | provider/model buckets, descending by tokens |
| `quota_windows[]` | quota status records, currently Antigravity; excluded from token/cost aggregates |
| `insights[]` | deterministic observations, never causal claims |
| `diagnostics` | files, rows, malformed input, attribution and fork gaps |

## Token fields

Provider-level token fields are integers and disjoint after normalization:

- `input_uncached`
- `cache_read`
- `cache_write_5m`
- `cache_write_1h`
- `output`
- `reasoning`
- `tool`
- `total_tokens`

The bundled Codex lineage engine emits event-level deltas after parent-baseline
subtraction and interleave containment, so Codex `by_model[]` rows retain
input/cache/output components and event counts. `quality[]` records the applied
mechanisms, including `codex-lineage-aware`,
`codex-parent-baseline-resolved`, and `codex-interleaved-watermark`.

## Cost fields

| Field | Contract |
|---|---|
| `estimated_cost_usd` | complete public-rate estimate, otherwise `null` |
| `estimated_cost_usd_priced_portion` | sum for fully priced events or buckets only; disclosed lower bound |
| `pricing_coverage` | tokens in fully priced events or buckets divided by total tokens, 0–1; any nonzero component without a rate leaves that event unpriced, and coverage is `null` when an aggregate backend omits enough detail to prove it |
| `reported_list_cost_usd` | provider-supplied vendor list cost, currently Cursor |
| `charged_cost_usd` | provider-supplied metered deduction, currently Cursor |

Never replace `null` with zero. Never add `reported_list_cost_usd` to
`estimated_cost_usd`; they are two measurements of the same model work.

## Quota fields

Antigravity quota records are status observations, not usage events:

| Field | Contract |
|---|---|
| `quota_id`, `provider`, `family`, `title` | stable bucket identity and display labels |
| `window_minutes` | 300 for 5-hour, 10080 for weekly, otherwise `null` |
| `remaining_fraction`, `used_fraction` | disjoint complements in the range 0–1, or `null` when unknown/disabled |
| `resets_at` | validated provider reset timestamp, if supplied |
| `reset_description` | reserved and currently `null`; free-form provider prose is omitted for privacy |
| `usage_known` | whether a valid, enabled remaining fraction was present |
| `source` | `local-app`, `local-ide`, `local-cli`, or `export` |

Quota rows never enter `overall`, `by_model[]`, `priced_tokens`, or cost fields.
The CSV renderer identifies them with `record_type: quota-window`; token rows
use `record_type: trace-usage`.

## HTML projection

`--format html` renders schema v1 into a self-contained native dashboard. It
does not change JSON semantics or add inferred usage. Dynamic values are HTML
escaped; CSS is inline; there are no remote assets or executable scripts.
An HTML-comment metadata block records the report type, slug, schema version,
and generation time without embedding local source paths.

The “Improvement opportunities” section is derived at render time from bounded,
visible conditions: incomplete or unknown pricing coverage, cache-read share
below 20%, a model bucket at or above 50% of tokens,
output/reasoning/tool share at or above 40%, unresolved Codex lineage gaps that
can affect normalized totals, or a known quota at or below 20% remaining. A
report with no trace events or quota windows gets an explicit no-data state.
Malformed-row counts remain scanner-quality diagnostics rather than optimization
advice. These are review signals, not productivity judgments or causal claims.

`--output PATH` writes any selected format to a file and uses exclusive-create
semantics. `--force` is required to replace an existing regular file and swaps
a fully-written sibling temporary file into place atomically. New reports use
mode `0600`, and symlink outputs are refused rather than followed.

## Quality fields

`quality[]` names any event-level approximation used by a bucket. Diagnostics
include:

- `malformed_rows`
- `unattributed_tokens`
- `fork_prefix_tokens_suppressed`
- `backends` (`native-lineage` for Codex, `native` for trace adapters, and
  `quota-only` for Antigravity)
- `quota_backends` and `quota_windows`
- `codex_unresolved_forks`, `codex_unresolved_total_only_rows`,
  `codex_invalid_parent_timestamps`,
  `codex_ambiguous_copied_prefixes`, `codex_owned_suffixes`, and
  `codex_interleaved_files`
- human-readable `warnings`

Any non-zero diagnostic that could change the headline belongs in the final
human summary.
