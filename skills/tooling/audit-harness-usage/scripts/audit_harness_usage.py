#!/usr/bin/env python3
"""Read local agent-harness traces and report normalized token usage.

The runtime is intentionally standard-library only and read-only. It never
copies prompt, response, or tool payloads into its report.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import io
import json
import math
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator

import antigravity_quota
import codex_lineage
import html_report


PROVIDERS = ("codex", "claude", "gemini", "cursor", "antigravity")
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PRICING = SCRIPT_DIR.parent / "references" / "pricing.v1.json"
UTC = dt.timezone.utc


def as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def as_nonnegative_float(value: Any) -> float | None:
    """Parse an external numeric value without admitting NaN or credits."""
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def token_count(value: Any, diagnostics: "Diagnostics", provider: str, field: str) -> int:
    """Validate an untrusted trace counter and make rejection visible."""
    if value is None:
        return 0
    try:
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
            raise ValueError
        parsed = int(value)
        if parsed < 0:
            raise ValueError
        return parsed
    except (TypeError, ValueError, OverflowError):
        diagnostics.warn(f"Ignored an invalid {provider} {field} token counter.")
        return 0


def safe_model(value: Any, diagnostics: "Diagnostics", provider: str) -> str:
    """Keep model labels useful while preventing content/path/CSV injection."""
    model = str(value or "unknown").strip()
    if model.startswith("models/") and model.count("/") == 1:
        model = model.removeprefix("models/")
    if (
        not model
        or len(model) > 128
        or model[0] in "=+-@"
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+\-]*", model)
    ):
        diagnostics.warn(f"Replaced an unsafe {provider} model label with unknown.")
        return "unknown"
    return model


def first(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def parse_timestamp(value: Any, fallback: float | None = None) -> dt.datetime:
    if isinstance(value, (int, float)):
        numeric = float(value)
        if math.isfinite(numeric):
            seconds = numeric / 1000 if numeric > 10_000_000_000 else numeric
            try:
                return dt.datetime.fromtimestamp(seconds, tz=UTC)
            except (OSError, OverflowError, ValueError):
                pass
    if isinstance(value, str) and value:
        candidate = value.strip().replace("Z", "+00:00")
        try:
            parsed = dt.datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except ValueError:
            pass
    try:
        return dt.datetime.fromtimestamp(fallback or 0, tz=UTC)
    except (OSError, OverflowError, TypeError, ValueError):
        return dt.datetime.fromtimestamp(0, tz=UTC)


@dataclasses.dataclass(slots=True)
class UsageEvent:
    provider: str
    model: str
    timestamp: dt.datetime
    event_id: str
    input_uncached: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    output: int = 0
    reasoning: int = 0
    tool: int = 0
    reported_list_cost_usd: float | None = None
    charged_cost_usd: float | None = None
    quality: tuple[str, ...] = ()

    @property
    def total_tokens(self) -> int:
        return (
            self.input_uncached
            + self.cache_read
            + self.cache_write_5m
            + self.cache_write_1h
            + self.output
            + self.reasoning
            + self.tool
        )

    @property
    def total_input(self) -> int:
        return self.input_uncached + self.cache_read + self.cache_write_5m + self.cache_write_1h


@dataclasses.dataclass
class Diagnostics:
    files_discovered: dict[str, int] = dataclasses.field(default_factory=lambda: defaultdict(int))
    files_scanned: dict[str, int] = dataclasses.field(default_factory=lambda: defaultdict(int))
    rows_seen: dict[str, int] = dataclasses.field(default_factory=lambda: defaultdict(int))
    rows_used: dict[str, int] = dataclasses.field(default_factory=lambda: defaultdict(int))
    malformed_rows: dict[str, int] = dataclasses.field(default_factory=lambda: defaultdict(int))
    unattributed_tokens: dict[str, int] = dataclasses.field(default_factory=lambda: defaultdict(int))
    fork_prefix_tokens_suppressed: dict[str, int] = dataclasses.field(default_factory=lambda: defaultdict(int))
    codex_unresolved_forks: int = 0
    codex_unresolved_total_only_rows: int = 0
    codex_invalid_parent_timestamps: int = 0
    codex_ambiguous_copied_prefixes: int = 0
    codex_owned_suffixes: int = 0
    codex_interleaved_files: set[str] = dataclasses.field(default_factory=set)
    backends: dict[str, str] = dataclasses.field(default_factory=dict)
    quota_backends: dict[str, str] = dataclasses.field(default_factory=dict)
    quota_windows: dict[str, int] = dataclasses.field(default_factory=lambda: defaultdict(int))
    warnings: list[str] = dataclasses.field(default_factory=list)

    def warn(self, message: str) -> None:
        if message not in self.warnings and len(self.warnings) < 30:
            self.warnings.append(message)

    def serializable(self) -> dict[str, Any]:
        return {
            "files_discovered": dict(self.files_discovered),
            "files_scanned": dict(self.files_scanned),
            "rows_seen": dict(self.rows_seen),
            "rows_used": dict(self.rows_used),
            "malformed_rows": dict(self.malformed_rows),
            "unattributed_tokens": dict(self.unattributed_tokens),
            "fork_prefix_tokens_suppressed": dict(self.fork_prefix_tokens_suppressed),
            "codex_unresolved_forks": self.codex_unresolved_forks,
            "codex_unresolved_total_only_rows": self.codex_unresolved_total_only_rows,
            "codex_invalid_parent_timestamps": self.codex_invalid_parent_timestamps,
            "codex_ambiguous_copied_prefixes": self.codex_ambiguous_copied_prefixes,
            "codex_owned_suffixes": self.codex_owned_suffixes,
            "codex_interleaved_files": len(self.codex_interleaved_files),
            "backends": dict(self.backends),
            "quota_backends": dict(self.quota_backends),
            "quota_windows": dict(self.quota_windows),
            "warnings": self.warnings,
        }


class RateCard:
    def __init__(self, path: Path):
        self.path = path
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or "as_of" not in payload
            or not isinstance(payload.get("models"), dict)
        ):
            raise ValueError(
                f"pricing file must be an object with 'as_of' and 'models': {path}"
            )
        self.as_of = payload["as_of"]
        self.provenance = payload.get("provenance", {})
        self.models: dict[str, dict[str, Any]] = payload["models"]

    def resolve(self, provider: str, model: str) -> tuple[str, dict[str, Any]] | None:
        direct = self.models.get(model)
        if direct and direct.get("provider") == provider:
            return model, direct
        for name, rate in self.models.items():
            if rate.get("provider") != provider:
                continue
            if any(re.search(pattern, model, flags=re.IGNORECASE) for pattern in rate.get("aliases", [])):
                return name, rate
        return None

    def price(self, event: UsageEvent) -> tuple[float, str] | None:
        resolved = self.resolve(event.provider, event.model)
        if not resolved:
            return None
        name, rate = resolved
        active = rate
        long_context = rate.get("long_context")
        if long_context and event.total_input > as_int(long_context.get("threshold")):
            active = {**rate, **long_context}
            name += ":long-context"
        units = {
            "input": event.input_uncached,
            "cache_read": event.cache_read,
            "cache_write": event.cache_write_5m,
            "cache_write_1h": event.cache_write_1h,
            "output": event.output + event.reasoning + event.tool,
        }
        # A missing rate is unknown, never an invitation to substitute the input
        # rate for a semantically different component such as output or cache.
        if any(tokens and kind not in active for kind, tokens in units.items()):
            return None
        cost = sum(tokens * float(active[kind]) for kind, tokens in units.items() if tokens)
        return cost / 1_000_000, name


def mtime_or_epoch(path: Path) -> float:
    """Return a trace mtime, degrading safely when a live file disappears."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def iter_jsonl(path: Path, provider: str, diagnostics: Diagnostics) -> Iterator[tuple[int, dict[str, Any]]]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, 1):
                diagnostics.rows_seen[provider] += 1
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    diagnostics.malformed_rows[provider] += 1
                    continue
                if isinstance(value, dict):
                    yield line_no, value
    except OSError as exc:
        diagnostics.warn(f"Could not read one {provider} trace: {exc.__class__.__name__}")


def parse_claude(path: Path, diagnostics: Diagnostics) -> Iterator[UsageEvent]:
    fallback = mtime_or_epoch(path)
    for line_no, row in iter_jsonl(path, "claude", diagnostics):
        if row.get("type") != "assistant":
            continue
        message = row.get("message") if isinstance(row.get("message"), dict) else {}
        usage = message.get("usage") if isinstance(message.get("usage"), dict) else None
        if not usage:
            continue
        cache_creation = usage.get("cache_creation") if isinstance(usage.get("cache_creation"), dict) else {}
        cache_write = token_count(first(usage, "cache_creation_input_tokens", "cacheCreationInputTokens"), diagnostics, "claude", "cache write")
        one_hour = min(
            cache_write,
            token_count(first(cache_creation, "ephemeral_1h_input_tokens", "ephemeral1hInputTokens"), diagnostics, "claude", "1h cache write"),
        )
        request_id = str(first(row, "requestId", "request_id", default=""))
        message_id = str(message.get("id") or "")
        # The provider pair is a stable streaming identity only when both
        # halves exist. Older rows with one missing half remain line-distinct.
        event_id = (
            f"claude:{message_id}:{request_id}"
            if message_id and request_id
            else f"{path}:{line_no}"
        )
        diagnostics.rows_used["claude"] += 1
        yield UsageEvent(
            provider="claude",
            model=safe_model(message.get("model") or row.get("model") or "unknown", diagnostics, "claude"),
            timestamp=parse_timestamp(first(row, "timestamp", "createdAt"), fallback),
            event_id=event_id,
            input_uncached=token_count(first(usage, "input_tokens", "inputTokens"), diagnostics, "claude", "input"),
            cache_read=token_count(first(usage, "cache_read_input_tokens", "cacheReadInputTokens"), diagnostics, "claude", "cache read"),
            cache_write_5m=cache_write - one_hour,
            cache_write_1h=one_hour,
            output=token_count(first(usage, "output_tokens", "outputTokens"), diagnostics, "claude", "output"),
        )


def gemini_event(message: dict[str, Any], event_id: str, fallback: float, diagnostics: Diagnostics) -> UsageEvent | None:
    tokens = message.get("tokens") if isinstance(message.get("tokens"), dict) else None
    if not tokens:
        return None
    input_total = token_count(tokens.get("input"), diagnostics, "gemini", "input")
    cached = min(input_total, token_count(tokens.get("cached"), diagnostics, "gemini", "cached input"))
    return UsageEvent(
        provider="gemini",
        model=safe_model(message.get("model") or "unknown", diagnostics, "gemini"),
        timestamp=parse_timestamp(first(message, "timestamp", "createdAt"), fallback),
        event_id=event_id,
        input_uncached=input_total - cached,
        cache_read=cached,
        output=token_count(tokens.get("output"), diagnostics, "gemini", "output"),
        reasoning=token_count(tokens.get("thoughts"), diagnostics, "gemini", "thoughts"),
        tool=token_count(tokens.get("tool"), diagnostics, "gemini", "tool"),
    )


def gemini_event_id(path: Path, message: dict[str, Any], index: int) -> str:
    """Return an identity stable across Gemini JSONL append/patch snapshots."""
    message_id = first(message, "id", "messageId", "message_id")
    if message_id is not None:
        return f"gemini:{message_id}"
    # Some Gemini CLI revisions omit message ids. A patch commonly re-emits the
    # same message array; timestamp/model/position remain stable while the final
    # cumulative token counters grow. The global scanner then keeps the largest
    # version for this identity.
    timestamp = first(message, "timestamp", "createdAt", default="")
    model = str(message.get("model") or "unknown")
    return f"{path}:{timestamp}:{model}:{index}"


def parse_gemini(path: Path, diagnostics: Diagnostics) -> Iterator[UsageEvent]:
    fallback = mtime_or_epoch(path)
    if path.suffix == ".jsonl":
        for line_no, row in iter_jsonl(path, "gemini", diagnostics):
            candidates: list[tuple[int, dict[str, Any]]] = []
            if isinstance(row.get("message"), dict):
                candidates.append((0, row["message"]))
            if isinstance(row.get("messages"), list):
                candidates.extend((index, item) for index, item in enumerate(row["messages"]) if isinstance(item, dict))
            patch = row.get("$set") if isinstance(row.get("$set"), dict) else {}
            if isinstance(patch.get("messages"), list):
                candidates.extend((index, item) for index, item in enumerate(patch["messages"]) if isinstance(item, dict))
            if row.get("tokens"):
                candidates.append((0, row))
            for index, message in candidates:
                event = gemini_event(message, gemini_event_id(path, message, index), fallback, diagnostics)
                if event:
                    diagnostics.rows_used["gemini"] += 1
                    yield event
        return
    diagnostics.rows_seen["gemini"] += 1
    try:
        root = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        diagnostics.malformed_rows["gemini"] += 1
        return
    messages = root.get("messages", []) if isinstance(root, dict) else []
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("type") not in (None, "gemini"):
            continue
        event = gemini_event(message, f"{root.get('sessionId', path.stem)}:{index}", fallback, diagnostics)
        if event:
            diagnostics.rows_used["gemini"] += 1
            yield event


def cursor_records(root: Any) -> Iterable[dict[str, Any]]:
    if isinstance(root, list):
        return [item for item in root if isinstance(item, dict)]
    if not isinstance(root, dict):
        return []
    for key in ("usageEvents", "usageEventsDisplay", "events", "data"):
        if isinstance(root.get(key), list):
            return [item for item in root[key] if isinstance(item, dict)]
        if isinstance(root.get(key), dict):
            nested = cursor_records(root[key])
            if nested:
                return nested
    return [root] if root.get("tokenUsage") else []


def parse_cursor(path: Path, diagnostics: Diagnostics) -> Iterator[UsageEvent]:
    fallback = mtime_or_epoch(path)
    roots: list[Any] = []
    if path.suffix == ".jsonl":
        roots.extend(row for _, row in iter_jsonl(path, "cursor", diagnostics))
    else:
        diagnostics.rows_seen["cursor"] += 1
        try:
            roots.append(json.loads(path.read_text(encoding="utf-8", errors="replace")))
        except (OSError, json.JSONDecodeError):
            diagnostics.malformed_rows["cursor"] += 1
            return
    index = 0
    for root in roots:
        for row in cursor_records(root):
            token_usage = row.get("tokenUsage") if isinstance(row.get("tokenUsage"), dict) else {}
            if not token_usage:
                continue
            input_tokens = token_count(first(token_usage, "inputTokens", "input_tokens", "input"), diagnostics, "cursor", "input")
            # Cursor's four counters are disjoint. This differs from Codex and
            # Gemini, where cached input is a subset of input.
            cache_read = token_count(first(token_usage, "cacheReadTokens", "cache_read_tokens", "cacheRead"), diagnostics, "cursor", "cache read")
            total_cents = first(token_usage, "totalCents", "total_cents")
            charged_cents = first(row, "chargedCents", "charged_cents")
            if charged_cents is None:
                charged_cents = first(token_usage, "chargedCents", "charged_cents")
            parsed_total_cents = as_nonnegative_float(total_cents)
            parsed_charged_cents = as_nonnegative_float(charged_cents)
            if total_cents is not None and parsed_total_cents is None:
                diagnostics.warn("Ignored an invalid Cursor totalCents value.")
            if charged_cents is not None and parsed_charged_cents is None:
                diagnostics.warn("Ignored an invalid Cursor chargedCents value.")
            diagnostics.rows_used["cursor"] += 1
            index += 1
            yield UsageEvent(
                provider="cursor",
                model=safe_model(row.get("model") or token_usage.get("model") or "unknown", diagnostics, "cursor"),
                timestamp=parse_timestamp(first(row, "timestamp", "createdAt", "date"), fallback),
                event_id=str(first(row, "id", "eventId", default=f"{path}:{index}")),
                input_uncached=input_tokens,
                cache_read=cache_read,
                cache_write_5m=token_count(first(token_usage, "cacheWriteTokens", "cache_write_tokens", "cacheWrite"), diagnostics, "cursor", "cache write"),
                output=token_count(first(token_usage, "outputTokens", "output_tokens", "output"), diagnostics, "cursor", "output"),
                reported_list_cost_usd=(parsed_total_cents / 100 if parsed_total_cents is not None else None),
                charged_cost_usd=(parsed_charged_cents / 100 if parsed_charged_cents is not None else None),
            )


PARSERS = {
    "claude": parse_claude,
    "gemini": parse_gemini,
    "cursor": parse_cursor,
}


def default_roots() -> dict[str, list[Path]]:
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    claude_env = os.environ.get("CLAUDE_CONFIG_DIR")
    claude_roots = [Path(claude_env) / "projects"] if claude_env else [home / ".claude" / "projects", home / ".config" / "claude" / "projects"]
    return {
        "codex": [codex_home / "sessions", codex_home / "archived_sessions"],
        "claude": claude_roots,
        "gemini": [home / ".gemini" / "tmp"],
        "cursor": [],
        "antigravity": [],
    }


def parse_overrides(values: list[str]) -> dict[str, list[Path]]:
    parsed: dict[str, list[Path]] = defaultdict(list)
    for value in values:
        provider, separator, raw_path = value.partition("=")
        if not separator or provider not in PROVIDERS:
            raise ValueError(f"--path must be PROVIDER=PATH; got {value!r}")
        parsed[provider].append(Path(raw_path).expanduser())
    return parsed


def discover(
    provider: str,
    roots: list[Path],
    cutoff: dt.datetime,
    max_files: int | None,
    *,
    prefilter_mtime: bool = True,
) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            if provider == "gemini":
                candidates = list(root.glob("**/chats/session-*.json")) + list(root.glob("**/chats/*.jsonl"))
            else:
                candidates = list(root.rglob("*.jsonl")) + (list(root.rglob("*.json")) if provider == "cursor" else [])
        else:
            continue
        for path in candidates:
            try:
                if not prefilter_mtime or dt.datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) >= cutoff:
                    found.append(path)
            except OSError:
                continue
    found = sorted(set(found), key=mtime_or_epoch, reverse=True)
    return found[:max_files] if max_files else found


def build_insights(rows: list[dict[str, Any]], overall: dict[str, Any], diagnostics: Diagnostics) -> list[dict[str, str]]:
    input_basis = overall["input_uncached"] + overall["cache_read"] + overall["cache_write_5m"] + overall["cache_write_1h"]
    insights: list[dict[str, str]] = []
    if input_basis:
        insights.append({"kind": "cache", "message": f"Cache reads account for {overall['cache_read'] / input_basis:.1%} of normalized input tokens."})
    if rows:
        insights.append({"kind": "concentration", "message": f"{rows[0]['provider']}/{rows[0]['model']} is the largest model bucket at {rows[0]['total_tokens']:,} tokens."})
    unpriced = [
        f"{row['provider']}/{row['model']}"
        for row in rows
        if row["pricing_coverage"] is None or row["pricing_coverage"] < 1.0
    ]
    if unpriced:
        insights.append({"kind": "pricing-gap", "message": "Unpriced model buckets: " + ", ".join(unpriced[:8])})
    if diagnostics.malformed_rows and sum(diagnostics.malformed_rows.values()):
        insights.append({"kind": "quality", "message": f"Skipped {sum(diagnostics.malformed_rows.values())} malformed trace rows."})
    if diagnostics.codex_unresolved_forks:
        insights.append({
            "kind": "quality",
            "message": f"{diagnostics.codex_unresolved_forks} Codex fork(s) had no resolvable parent baseline; first cumulative snapshots were skipped and later growth was contained.",
        })
    if diagnostics.codex_unresolved_total_only_rows:
        insights.append({
            "kind": "quality",
            "message": f"Skipped {diagnostics.codex_unresolved_total_only_rows} unresolved-fork row(s) that had cumulative totals but no safe last-usage cap.",
        })
    if diagnostics.codex_ambiguous_copied_prefixes:
        insights.append({
            "kind": "quality",
            "message": f"Suppressed {diagnostics.codex_ambiguous_copied_prefixes} ambiguous copied-prefix Codex file(s) whose parent and owned suffix could not be identified.",
        })
    if diagnostics.codex_interleaved_files:
        insights.append({
            "kind": "quality",
            "message": f"Contained interleaved cumulative counters in {len(diagnostics.codex_interleaved_files)} Codex file(s) using monotonic watermarks.",
        })
    return insights


def aggregate(events: list[UsageEvent], rate_card: RateCard, since: dt.datetime, diagnostics: Diagnostics) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    token_fields = ("input_uncached", "cache_read", "cache_write_5m", "cache_write_1h", "output", "reasoning", "tool")
    for event in events:
        key = (event.provider, event.model)
        row = groups.setdefault(key, {
            "provider": event.provider,
            "model": event.model,
            "events": 0,
            **{field: 0 for field in token_fields},
            "total_tokens": 0,
            "priced_tokens": 0,
            "estimated_cost_usd_priced_portion": 0.0,
            "reported_list_cost_usd": 0.0,
            "charged_cost_usd": 0.0,
            "reported_cost_events": 0,
            "charged_cost_events": 0,
            "reported_cost_missing": 0,
            "charged_cost_missing": 0,
            "rate_names": set(),
            "quality": set(),
        })
        row["events"] += 1
        for field in token_fields:
            row[field] += getattr(event, field)
        row["total_tokens"] += event.total_tokens
        price = rate_card.price(event)
        if price:
            cost, rate_name = price
            row["priced_tokens"] += event.total_tokens
            row["estimated_cost_usd_priced_portion"] += cost
            row["rate_names"].add(rate_name)
        if event.reported_list_cost_usd is not None:
            row["reported_list_cost_usd"] += event.reported_list_cost_usd
            row["reported_cost_events"] += 1
        elif event.provider == "cursor":
            row["reported_cost_missing"] += 1
        if event.charged_cost_usd is not None:
            row["charged_cost_usd"] += event.charged_cost_usd
            row["charged_cost_events"] += 1
        elif event.provider == "cursor":
            row["charged_cost_missing"] += 1
        row["quality"].update(event.quality)

    rows: list[dict[str, Any]] = []
    for row in groups.values():
        total = row["total_tokens"]
        coverage = row["priced_tokens"] / total if total else 0.0
        row["pricing_coverage"] = coverage
        row["estimated_cost_usd"] = row["estimated_cost_usd_priced_portion"] if coverage == 1.0 else None
        reported_events = row.pop("reported_cost_events")
        charged_events = row.pop("charged_cost_events")
        if not reported_events or row.pop("reported_cost_missing"):
            row["reported_list_cost_usd"] = None
        if not charged_events or row.pop("charged_cost_missing"):
            row["charged_cost_usd"] = None
        row["rate_names"] = sorted(row["rate_names"])
        row["quality"] = sorted(row["quality"])
        rows.append(row)
    rows.sort(key=lambda item: item["total_tokens"], reverse=True)

    overall = {field: sum(row[field] for row in rows) for field in token_fields}
    overall["events"] = sum(row["events"] for row in rows)
    overall["total_tokens"] = sum(row["total_tokens"] for row in rows)
    overall["priced_tokens"] = sum(row["priced_tokens"] for row in rows)
    overall["pricing_coverage"] = overall["priced_tokens"] / overall["total_tokens"] if overall["total_tokens"] else 0.0
    partial_cost = sum(row["estimated_cost_usd_priced_portion"] for row in rows)
    overall["estimated_cost_usd_priced_portion"] = partial_cost
    overall["estimated_cost_usd"] = partial_cost if overall["pricing_coverage"] == 1.0 else None
    cursor_rows = [row for row in rows if row["provider"] == "cursor"]
    reported = [row["reported_list_cost_usd"] for row in cursor_rows]
    charged = [row["charged_cost_usd"] for row in cursor_rows]
    overall["reported_list_cost_usd"] = sum(reported) if reported and all(value is not None for value in reported) else None
    overall["charged_cost_usd"] = sum(charged) if charged and all(value is not None for value in charged) else None

    insights = build_insights(rows, overall, diagnostics)

    return {
        "schema_version": 1,
        "generated_at": dt.datetime.now(tz=UTC).isoformat(),
        "since": since.isoformat(),
        "cost_semantics": "Public API list-price estimate for trace usage; not a subscription invoice. Cursor-reported list and charged costs are separate fields. Antigravity quota windows are status signals and do not expose token usage or cost.",
        "pricing": {
            "source": "bundled-snapshot" if rate_card.path.resolve() == DEFAULT_PRICING.resolve() else "custom-snapshot",
            "as_of": rate_card.as_of,
            "provenance": rate_card.provenance,
        },
        "overall": overall,
        "by_model": rows,
        "insights": insights,
        "diagnostics": diagnostics.serializable(),
    }


def scan(args: argparse.Namespace) -> dict[str, Any]:
    # Match CodexBar/ccusage calendar-day semantics: --days 1 means today,
    # while --days 30 means today plus the preceding 29 local dates.
    local_midnight = dt.datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    since = (local_midnight - dt.timedelta(days=args.days - 1)).astimezone(UTC)
    roots = default_roots()
    overrides = parse_overrides(args.path)
    diagnostics = Diagnostics()
    providers = list(PROVIDERS) if args.provider == "all" else [args.provider]
    deduped: dict[str, UsageEvent] = {}
    quota_windows: list[dict[str, Any]] = []
    for provider in providers:
        provider_roots = overrides.get(provider, roots[provider])
        if provider == "antigravity":
            if provider in overrides:
                quota_result = antigravity_quota.load_exports(provider_roots, args.max_files)
                diagnostics.files_discovered[provider] = quota_result.files_discovered
            else:
                quota_result = antigravity_quota.probe_local(getattr(args, "quota_timeout", 2.0))
            quota_windows.extend(quota_result.windows)
            diagnostics.backends[provider] = "quota-only"
            diagnostics.quota_backends[provider] = quota_result.backend
            diagnostics.quota_windows[provider] = len(quota_result.windows)
            for warning in quota_result.warnings:
                diagnostics.warn(warning)
            if args.provider == "antigravity" and not quota_result.windows and not quota_result.warnings:
                diagnostics.warn("Antigravity is not running; pass --path antigravity=<quota-export.json> for offline parsing.")
            continue
        diagnostics.backends[provider] = "native-lineage" if provider == "codex" else "native"
        # Auto-discovery uses mtime as a performance hint. Explicit exports do
        # not: copying/restoring an export can preserve an old filesystem time
        # even when its event timestamps fall inside the requested window.
        paths = discover(
            provider,
            provider_roots,
            since,
            args.max_files,
            prefilter_mtime=provider not in overrides and provider != "codex",
        )
        diagnostics.files_discovered[provider] = len(paths)
        if provider == "cursor" and not provider_roots:
            diagnostics.warn("Cursor has no trustworthy default local trace; pass --path cursor=<export.json>.")
        if provider == "codex":
            provider_events = (
                UsageEvent(
                    provider="codex",
                    model=safe_model(delta.model, diagnostics, "codex"),
                    timestamp=delta.timestamp,
                    event_id=f"{delta.session_id}:{delta.turn_id or ''}:{delta.event_index}",
                    input_uncached=max(0, delta.usage.input - min(delta.usage.input, delta.usage.cached)),
                    cache_read=min(delta.usage.input, delta.usage.cached),
                    output=delta.usage.output,
                    quality=delta.quality,
                )
                for delta in codex_lineage.scan(paths, provider_roots, diagnostics)
            )
        else:
            def native_events() -> Iterator[UsageEvent]:
                for path in paths:
                    diagnostics.files_scanned[provider] += 1
                    yield from PARSERS[provider](path, diagnostics)
            provider_events = native_events()
        for event in provider_events:
                if event.timestamp < since:
                    continue
                if event.total_tokens <= 0:
                    continue
                key = f"{provider}:{event.event_id}"
                prior = deduped.get(key)
                if prior is None or event.total_tokens >= prior.total_tokens:
                    deduped[key] = event
    report = aggregate(list(deduped.values()), RateCard(Path(args.pricing).expanduser()), since, diagnostics)
    report["window_days"] = args.days
    report["quota_windows"] = quota_windows
    if "antigravity" in providers:
        report["insights"].append({
            "kind": "quota-semantics",
            "message": "Antigravity exposes quota-window status here, not trace-level token counts or cost; its windows are excluded from token and cost totals.",
        })
    if "codex" in providers:
        report["pricing"]["codex_backend"] = "native-lineage"
    return report


def format_tokens(value: int) -> str:
    for suffix, divisor in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if value >= divisor:
            return f"{value / divisor:.2f}{suffix}"
    return str(value)


def render_text(report: dict[str, Any]) -> str:
    overall = report["overall"]
    coverage = overall["pricing_coverage"]
    quota_windows = report.get("quota_windows", [])
    if overall["estimated_cost_usd"] is not None:
        cost = f"${overall['estimated_cost_usd']:.2f}"
    elif overall["estimated_cost_usd_priced_portion"]:
        coverage_text = f"{coverage:.1%} priced" if coverage is not None else "pricing coverage unknown"
        cost = f"${overall['estimated_cost_usd_priced_portion']:.2f} partial ({coverage_text})"
    elif quota_windows and not overall["events"]:
        cost = "not exposed by quota provider"
    else:
        cost = "unpriced"
    event_count = f"{overall['events']:,}" if overall["events"] is not None else "unavailable"
    lines = [
        "Harness usage",
        f"Since: {report['since']}",
        f"Events: {event_count}  Tokens: {format_tokens(overall['total_tokens'])}  Estimated API cost: {cost}",
        f"Input: {format_tokens(overall['input_uncached'])}  Cache read: {format_tokens(overall['cache_read'])}  Cache write: {format_tokens(overall['cache_write_5m'] + overall['cache_write_1h'])}  Output+reasoning+tool: {format_tokens(overall['output'] + overall['reasoning'] + overall['tool'])}",
    ]
    if report["by_model"]:
        lines += ["", "By model"]
        for row in report["by_model"]:
            if row["estimated_cost_usd"] is not None:
                row_cost = f"${row['estimated_cost_usd']:.2f}"
            elif row["priced_tokens"]:
                row_cost = f"${row['estimated_cost_usd_priced_portion']:.2f} partial"
            else:
                row_cost = "unpriced"
            row_events = f"{row['events']:,} events" if row["events"] is not None else "aggregated event count unavailable"
            lines.append(f"- {row['provider']}/{row['model']}: {format_tokens(row['total_tokens'])}, {row_cost}, {row_events}")
    if quota_windows:
        lines += ["", "Quota windows"]
        for window in quota_windows:
            remaining = window.get("remaining_fraction")
            remaining_text = f"{remaining:.1%} remaining" if remaining is not None else "usage unavailable"
            reset = f", resets {window['resets_at']}" if window.get("resets_at") else ""
            lines.append(f"- {window['provider']}/{window['title']}: {remaining_text}{reset}")
    if report["insights"]:
        lines += ["", "Insights"] + [f"- {item['message']}" for item in report["insights"]]
    warnings = report["diagnostics"]["warnings"]
    if warnings:
        lines += ["", "Warnings"] + [f"- {warning}" for warning in warnings]
    if overall["reported_list_cost_usd"] is not None or overall["charged_cost_usd"] is not None:
        lines += ["", "Provider-reported cost"]
        if overall["reported_list_cost_usd"] is not None:
            lines.append(f"- Vendor list cost: ${overall['reported_list_cost_usd']:.2f}")
        if overall["charged_cost_usd"] is not None:
            lines.append(f"- Plan-deducted cost: ${overall['charged_cost_usd']:.2f}")
    lines += ["", "Cost note: public API list-price estimate, not proof of subscription billing."]
    return "\n".join(lines)


def render_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    rows = report["by_model"]
    fields = [
        "provider", "model", "events", "total_tokens", "input_uncached", "cache_read",
        "cache_write_5m", "cache_write_1h", "output", "reasoning", "tool",
        "estimated_cost_usd", "estimated_cost_usd_priced_portion", "pricing_coverage",
        "reported_list_cost_usd", "charged_cost_usd", "record_type", "quota_id",
        "family", "title", "window_minutes", "used_fraction", "remaining_fraction",
        "resets_at", "usage_known", "source",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows({**row, "record_type": "trace-usage"} for row in rows)
    writer.writerows({**row, "record_type": "quota-window"} for row in report.get("quota_windows", []))
    return output.getvalue()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("all",) + PROVIDERS, default="all")
    parser.add_argument("--days", type=int, default=30, help="local calendar days including today (default: 30)")
    parser.add_argument("--path", action="append", default=[], metavar="PROVIDER=PATH", help="replace one provider's auto-discovery root; repeatable")
    parser.add_argument("--pricing", default=str(DEFAULT_PRICING), help="versioned pricing JSON")
    parser.add_argument("--format", choices=("text", "json", "csv", "html"), default="text")
    parser.add_argument("--output", help="write the rendered report to this file instead of stdout")
    parser.add_argument("--force", action="store_true", help="allow --output to replace an existing file")
    parser.add_argument("--max-files", type=int, help="diagnostic cap per provider; newest files first")
    parser.add_argument("--quota-timeout", type=float, default=2.0, help="seconds allowed for the read-only Antigravity localhost probe (default: 2)")
    return parser


def write_output(path: Path, rendered: str, *, force: bool) -> None:
    """Write a private report without following links or exposing partial replacements."""
    if path.is_symlink():
        raise ValueError("refusing to write report through a symlink")
    if path.exists() and not path.is_file():
        raise ValueError("output exists and is not a regular file")

    if not force:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = -1
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        return

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        # Re-check after rendering the replacement. os.replace swaps the path
        # atomically and never writes through a link introduced after this test.
        if path.is_symlink():
            raise ValueError("refusing to replace a symlink")
        if path.exists() and not path.is_file():
            raise ValueError("output exists and is not a regular file")
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.days < 1:
        parser.error("--days must be at least 1")
    if args.quota_timeout <= 0:
        parser.error("--quota-timeout must be greater than 0")
    if args.force and not args.output:
        parser.error("--force requires --output")
    try:
        report = scan(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if args.format == "json":
        rendered = json.dumps(report, indent=2, sort_keys=True)
    elif args.format == "csv":
        rendered = render_csv(report)
    elif args.format == "html":
        rendered = html_report.render_html(report)
    else:
        rendered = render_text(report)
    if not rendered.endswith("\n"):
        rendered += "\n"
    if args.output:
        output = Path(args.output).expanduser()
        try:
            write_output(output, rendered, force=args.force)
        except FileExistsError:
            parser.error("output already exists; pass --force to replace it")
        except ValueError as exc:
            parser.error(str(exc))
        except OSError as exc:
            parser.error(f"could not write output: {exc.__class__.__name__}")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
