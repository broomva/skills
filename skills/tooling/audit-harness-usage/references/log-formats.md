# Log formats and accounting methodology

## What CodexBar calculates

CodexBar has two separate concepts. Its normal provider status probes retrieve
quota windows, plan state, or credits. Its `cost` command scans local traces
and prices token components. The latter is an API-list-price equivalent unless
the provider supplies an authoritative charged amount.

At CodexBar v0.45.0, the cost scanner:

- searches Codex `sessions` and `archived_sessions` JSONL under `$CODEX_HOME`;
- searches Claude project JSONL under the configured/default Claude roots;
- caches scan state under `~/Library/Caches/CodexBar/cost-usage/`;
- resolves current pricing from the [models.dev API](https://models.dev/api.json)
  with a local cache and bundled fallbacks;
- prices unknown models as unknown, not zero;
- handles Codex cumulative counters, copied fork prefixes, interleaved lineage
  totals, and model evidence; and
- deduplicates Claude stream chunks by message/request identity, keeping the
  final cumulative chunk.

Primary implementation: [CodexBar repository](https://github.com/steipete/CodexBar),
[CLI documentation](https://github.com/steipete/CodexBar/blob/main/docs/cli.md),
and [provider documentation](https://github.com/steipete/CodexBar/blob/main/docs/providers.md).
The Python port is pinned behaviorally to v0.45.0 commit
`3cf462b7256e4ddc2271b01707994f8b800125aa`, especially
[`CostUsageScanner.swift`](https://github.com/steipete/CodexBar/blob/3cf462b7256e4ddc2271b01707994f8b800125aa/Sources/CodexBarCore/Vendored/CostUsage/CostUsageScanner.swift)
and
[`CodexSubagentRolloutShape.swift`](https://github.com/steipete/CodexBar/blob/3cf462b7256e4ddc2271b01707994f8b800125aa/Sources/CodexBarCore/Vendored/CostUsage/CodexSubagentRolloutShape.swift).

## Normalized components

The script converts each provider record into disjoint buckets before summing:

| Provider | Source semantics | Normalization |
|---|---|---|
| Codex | cached input is a subset of input; output already includes reasoning | `input_uncached = input - cached`; retain provider output as one billable bucket |
| Claude | input, cache read, cache creation, and output are already separate | split cache creation into 5m and 1h when the nested breakdown exists |
| Gemini CLI | cached is a subset of input; thoughts/tool contribute to reported total | subtract cached from input; retain output, thoughts, and tool separately |
| Cursor | input, cache read, cache write, and output are separate | sum all four; preserve `totalCents` and `chargedCents` independently |
| Antigravity | current quota-window fractions; no supported token/cost trace | emit separate quota records; contribute nothing to normalized token totals |

Normalized total is therefore:

```text
input_uncached + cache_read + cache_write_5m + cache_write_1h
+ output + reasoning + tool
```

This equals each harness's logical total without double-counting subset fields.

## Cost formula

For a resolved rate card entry, prices are USD per one million tokens:

```text
estimate = (
  input_uncached * input_rate
  + cache_read * cache_read_rate
  + cache_write_5m * cache_write_rate
  + cache_write_1h * cache_write_1h_rate
  + (output + reasoning + tool) * output_rate
) / 1_000_000
```

If an event crosses a model's long-context input threshold, the alternate rates
apply to the entire event. Anthropic documents cache hits at 10% of base input,
5-minute writes at 1.25x, and 1-hour writes at 2x; long-context thresholds use
input plus cache reads/writes. See [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing).

Gemini output prices include thinking tokens, but the free and paid tiers differ.
The bundled snapshot represents paid API list price, not the caller's billing
arrangement. See [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing).

OpenAI cached-input and long-context prices are model-specific. See
[OpenAI API pricing](https://openai.com/api/pricing/). Cursor says selected
models consume usage at list API price and exposes token breakdowns in its
dashboard; see [Cursor pricing](https://docs.cursor.com/account/pricing) and
[Admin API](https://docs.cursor.com/en/account/teams/admin-api).

## Deduplication limits

### Claude

Streaming chunks can repeat cumulative usage for one assistant message. The
key `message.id + requestId` is stable enough to keep the largest/final record
across project/fork files only when both fields are present. Older rows missing
either half remain line-distinct, matching CodexBar v0.45; deduplicating on one
identifier alone can collapse unrelated usage.

The nested `ephemeral_1h_input_tokens` cache-creation component is clamped to
`cache_creation_input_tokens`. Older rows can contain a larger nested value;
without the clamp it would exceed and double-count the provider's total.

### Codex

Codex rollouts do not expose a globally stable token-event UUID. Fork files can
copy ancestor prefixes, and interleaved subagent counters can reflect overlapping
lineage state. The bundled `codex_lineage.py` ports the accounting state machine
from CodexBar v0.45 rather than invoking CodexBar:

1. index the first `session_meta` in every candidate file as the authoritative
   leaf identity;
2. resolve a fork parent's cumulative snapshot at or before the child's fork
   timestamp;
3. subtract that inherited baseline component-wise from the child's totals;
4. classify subagent counters as independent or copied-prefix based on embedded
   ancestor metadata;
5. detect a locally owned suffix at an adjacent `turn_context` plus
   `inter_agent_communication_metadata(trigger_turn=true)` boundary; and
6. latch interleaved mode when a cumulative component drops below its monotonic
   watermark, then count only contained growth.

If a referenced parent is missing, the scanner follows CodexBar's fail-visible
containment rule: skip the child's first cumulative snapshot, then count later
growth only when `last_token_usage` provides a safe cap. Total-only rows cannot
be attributed safely and remain uncounted; `codex_unresolved_total_only_rows`
makes that gap explicit. A copied-prefix subagent with neither a unique parent
nor a local owned-suffix boundary is likewise suppressed and reported through
`codex_ambiguous_copied_prefixes`. Neither case is presented as exact.

CodexBar remains an optional development oracle. The checked-in
`scripts/verify_codexbar_parity.py` compares the standalone implementation
against `codexbar cost` on an explicit `--codex-home` snapshot and emits a JSON
receipt. It is not part of normal execution or CI: production scanning has no
CodexBar binary, cache, subprocess, or Swift dependency. The implementation-time
30-day snapshot comparison matched exactly; that one-time result is recorded in
the repository plan and is not presented as a continuously enforced guarantee.

## Cursor boundary

Cursor's supported accounting surface is its dashboard/Admin API rather than a
portable, stable local trace. The script deliberately has no cookie scraper and
requires an explicit JSON/JSONL export. `tokenUsage.totalCents / 100` is the
vendor-list cost. `chargedCents / 100` is what the plan deducted. A missing
charged field is unknown, not zero.

## Gemini CLI boundary

Legacy sessions are objects with `messages[]`; Gemini messages carry `model`
and `tokens` (`input`, `output`, `cached`, `thoughts`, `tool`, `total`). Newer
JSONL stores are parsed when they expose message-like rows or `$set.messages`.
Gemini CLI's `/stats` command is the interactive source of the same model/token
class of information; sessions are project-scoped. See the
[Gemini CLI command reference](https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/commands.md).

## Antigravity boundary

Antigravity is not included in Gemini CLI accounting. It is a separate app/IDE
and local language-server provider. Following the pinned CodexBar v0.45
implementation, the scanner discovers an already-running Antigravity app, IDE,
or `agy`/`antigravity-cli` process, finds its listening localhost port, and
POSTs to `RetrieveUserQuotaSummary`. It falls back to `GetUserStatus`, then
`GetCommandModelConfigs`. Requests are pinned to `127.0.0.1`, use the process's
CSRF token only in memory when required, tolerate the local self-signed TLS
certificate, and never start a process or use OAuth. Port discovery uses `lsof`
on macOS/Linux, with a process-scoped `/proc` fallback on Linux. Redirects and
environment proxies are disabled so the in-memory CSRF header cannot leave the
exact localhost request target.

The preferred response contains grouped Gemini and Claude/GPT 5-hour and
weekly buckets. Older responses expose model-level `quotaInfo`. Both are
normalized into `quota_windows[]`. Account email and plan identity are ignored.
Free-form display/description text is reduced to canonical labels or omitted,
so a crafted export cannot smuggle identity into the report.
An explicit `--path antigravity=<response.json>` exercises the same parser
without a running app.

CodexBar's provider descriptor marks Antigravity token cost unsupported, and
its cost scanner returns no Antigravity usage report. This scanner preserves
that boundary: percentages and reset times are useful status signals but cannot
be reconstructed into historical tokens or USD. Primary source:
[`AntigravityStatusProbe.swift`](https://github.com/steipete/CodexBar/blob/3cf462b7256e4ddc2271b01707994f8b800125aa/Sources/CodexBarCore/Providers/Antigravity/AntigravityStatusProbe.swift)
and [CodexBar's Antigravity documentation](https://github.com/steipete/CodexBar/blob/3cf462b7256e4ddc2271b01707994f8b800125aa/docs/antigravity.md).

## Pricing freshness

`pricing.v1.json` is an offline, reviewable snapshot. Update it only by:

1. checking models.dev and the provider's primary pricing page;
2. changing `as_of` and affected rates/aliases;
3. adding a fixture for new matching or threshold behavior; and
4. rerunning the complete test and skillify gates.

Historical traces priced with today's card are a counterfactual at today's
rates, not necessarily the price effective when the request occurred. Preserve
the `as_of` field in every report.
