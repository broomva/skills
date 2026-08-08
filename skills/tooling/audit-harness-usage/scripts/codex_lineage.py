"""Lineage-aware Codex JSONL accounting derived from CodexBar's scanner.

This is an independent standard-library Python implementation of the accounting
rules in CodexBar v0.45's vendored CostUsage scanner. CodexBar is a development
oracle, not a runtime dependency. See references/CODEXBAR-NOTICE.md for pinned
source attribution and the upstream MIT license notice.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path
from typing import Any, Iterable, Iterator


UTC = dt.timezone.utc


@dataclasses.dataclass(frozen=True, slots=True)
class Totals:
    input: int = 0
    cached: int = 0
    output: int = 0

    def __add__(self, other: "Totals") -> "Totals":
        return Totals(self.input + other.input, self.cached + other.cached, self.output + other.output)

    @property
    def tokens(self) -> int:
        # Codex input includes cached input; cache is a subset, not additive.
        return self.input + self.output


ZERO = Totals()


def total_delta(baseline: Totals | None, current: Totals) -> Totals:
    base = baseline or ZERO
    return Totals(
        max(0, current.input - base.input),
        max(0, current.cached - base.cached),
        max(0, current.output - base.output),
    )


def min_totals(left: Totals, right: Totals) -> Totals:
    return Totals(min(left.input, right.input), min(left.cached, right.cached), min(left.output, right.output))


def max_totals(left: Totals | None, right: Totals) -> Totals:
    if left is None:
        return right
    return Totals(max(left.input, right.input), max(left.cached, right.cached), max(left.output, right.output))


def at_least(left: Totals, right: Totals) -> bool:
    return left.input >= right.input and left.cached >= right.cached and left.output >= right.output


def at_most(left: Totals, right: Totals) -> bool:
    return left.input <= right.input and left.cached <= right.cached and left.output <= right.output


def divergent_delta(raw_baseline: Totals | None, counted_baseline: Totals | None, current: Totals) -> Totals:
    raw = raw_baseline or ZERO
    counted = counted_baseline or ZERO

    def component(raw_value: int, counted_value: int, current_value: int) -> int:
        return max(0, current_value - (raw_value if current_value >= raw_value else counted_value))

    return Totals(
        component(raw.input, counted.input, current.input),
        component(raw.cached, counted.cached, current.cached),
        component(raw.output, counted.output, current.output),
    )


def contained_delta(watermark: Totals | None, counted: Totals | None, current: Totals) -> Totals:
    water = watermark or ZERO
    counted = counted or ZERO

    def component(water_value: int, counted_value: int, current_value: int) -> int:
        if current_value >= water_value:
            return max(0, current_value - max(water_value, counted_value))
        return max(0, current_value - counted_value)

    return Totals(
        component(water.input, counted.input, current.input),
        component(water.cached, counted.cached, current.cached),
        component(water.output, counted.output, current.output),
    )


def post_latch_delta(
    watermark: Totals | None,
    counted: Totals | None,
    current: Totals,
    adjusted_last: Totals | None,
) -> Totals:
    contained = contained_delta(watermark, counted, current)
    return min_totals(adjusted_last, contained) if adjusted_last is not None else contained


def prefer_total_delta(
    raw_baseline: Totals | None,
    current: Totals,
    delta: Totals,
    last: Totals,
    divergent: bool,
) -> bool:
    return (
        not divergent
        and raw_baseline is not None
        and at_least(current, raw_baseline)
        and at_most(delta, last)
    )


@dataclasses.dataclass(slots=True)
class Tracker:
    watermark: Totals | None = None
    seen: list[Totals] = dataclasses.field(default_factory=list)
    interleaved: bool = False

    def is_seen(self, totals: Totals) -> bool:
        return totals in self.seen

    def latch(self, totals: Totals) -> None:
        if self.watermark and not at_least(totals, self.watermark):
            self.interleaved = True

    def commit(self, totals: Totals) -> None:
        self.watermark = max_totals(self.watermark, totals)
        if totals not in self.seen:
            self.seen.append(totals)
            self.seen = self.seen[-64:]

    def raise_watermark(self, totals: Totals) -> None:
        self.watermark = max_totals(self.watermark, totals)


@dataclasses.dataclass(frozen=True, slots=True)
class Metadata:
    session_id: str | None
    parent_id: str | None
    fork_timestamp: str | None
    subagent: bool


@dataclasses.dataclass(frozen=True, slots=True)
class Record:
    line_index: int
    kind: str
    timestamp: str | None = None
    metadata: Metadata | None = None
    model: str | None = None
    last: Totals | None = None
    total: Totals | None = None
    turn_id: str | None = None
    trigger_turn: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class Delta:
    timestamp: dt.datetime
    model: str
    session_id: str
    event_index: int
    turn_id: str | None
    usage: Totals
    quality: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class Shape:
    copied_prefix: bool
    owned_suffix_start: int | None
    owned_suffix_baseline: Totals | None
    inferred_parent_id: str | None


def nonempty(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        candidate = value.strip().replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(candidate)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        return None


def counter(value: Any, diagnostics: Any, field: str) -> int:
    try:
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, float) and (not value.is_integer()):
            raise ValueError
        parsed = int(value or 0)
        if parsed < 0:
            raise ValueError
        return parsed
    except (TypeError, ValueError, OverflowError):
        diagnostics.warn(f"Ignored an invalid codex {field} token counter.")
        return 0


def parse_totals(value: Any, diagnostics: Any) -> Totals | None:
    if not isinstance(value, dict):
        return None
    return Totals(
        counter(value.get("input_tokens"), diagnostics, "input"),
        counter(value.get("cached_input_tokens", value.get("cache_read_input_tokens")), diagnostics, "cached input"),
        counter(value.get("output_tokens"), diagnostics, "output"),
    )


def metadata_from(row: dict[str, Any]) -> Metadata | None:
    if row.get("type") != "session_meta":
        return None
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    session_id = next((value for value in (
        nonempty(payload.get("id")), nonempty(row.get("id")),
        nonempty(payload.get("session_id")), nonempty(payload.get("sessionId")),
        nonempty(row.get("session_id")), nonempty(row.get("sessionId")),
    ) if value), None)
    parent_id = next((value for value in (
        nonempty(payload.get("forked_from_id")), nonempty(payload.get("forkedFromId")),
        nonempty(payload.get("parent_session_id")), nonempty(payload.get("parentSessionId")),
    ) if value), None)
    source = payload.get("source")
    subagent = (
        isinstance(source, str) and source.strip().lower() == "subagent"
    ) or (
        isinstance(source, dict) and isinstance(source.get("subagent"), (str, dict))
    )
    return Metadata(session_id, parent_id, nonempty(payload.get("timestamp")) or nonempty(row.get("timestamp")), subagent)


def turn_id_from(payload: dict[str, Any]) -> str | None:
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    return next((value for value in (
        nonempty(payload.get("turn_id")), nonempty(payload.get("turnId")), nonempty(payload.get("id")),
        nonempty(info.get("turn_id")), nonempty(info.get("turnId")), nonempty(info.get("id")),
    ) if value), None)


def relevant_record(row: dict[str, Any], line_index: int, diagnostics: Any) -> Record | None:
    row_type = row.get("type")
    if row_type == "session_meta":
        return Record(line_index, "metadata", metadata=metadata_from(row))
    timestamp = nonempty(row.get("timestamp"))
    if row_type == "turn_context":
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
        candidates = [payload.get("model"), payload.get("model_name"), info.get("model"), info.get("model_name")]
        present = [candidate for candidate in candidates if candidate is not None]
        model = next((nonempty(candidate) for candidate in present if nonempty(candidate)), "" if present else None)
        return Record(line_index, "context", timestamp=timestamp, model=model)
    if row_type == "inter_agent_communication_metadata":
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        return Record(line_index, "communication", timestamp=timestamp, trigger_turn=payload.get("trigger_turn") is True)
    if row_type != "event_msg":
        return None
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    if payload.get("type") == "task_started":
        return Record(line_index, "task", timestamp=timestamp, turn_id=turn_id_from(payload))
    if payload.get("type") != "token_count" or timestamp is None:
        return None
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    model = next((value for value in (
        nonempty(info.get("model")), nonempty(info.get("model_name")),
        nonempty(payload.get("model")), nonempty(row.get("model")),
    ) if value), None)
    return Record(
        line_index, "tokens", timestamp=timestamp, model=model,
        last=parse_totals(info.get("last_token_usage"), diagnostics),
        total=parse_totals(info.get("total_token_usage"), diagnostics),
        turn_id=turn_id_from(payload),
    )


def read_records(path: Path, diagnostics: Any, *, count_diagnostics: bool = True) -> list[Record]:
    records: list[Record] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_index, line in enumerate(handle):
                if count_diagnostics:
                    diagnostics.rows_seen["codex"] += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    if count_diagnostics:
                        diagnostics.malformed_rows["codex"] += 1
                    continue
                if not isinstance(row, dict):
                    continue
                record = relevant_record(row, line_index, diagnostics)
                if record is not None:
                    records.append(record)
    except OSError as exc:
        diagnostics.warn(f"Could not read one codex trace: {exc.__class__.__name__}")
    return records


def first_metadata(path: Path, diagnostics: Any) -> Metadata | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and (metadata := metadata_from(row)) is not None:
                    return metadata
    except OSError:
        return None
    return None


def classify_shape(leaf_id: str | None, records: list[Record]) -> Shape:
    metadata_ids = [record.metadata.session_id for record in records if record.kind == "metadata" and record.metadata]
    normalized_leaf = nonempty(leaf_id)
    has_ancestor = any(nonempty(value) != normalized_leaf for value in metadata_ids) if normalized_leaf else (
        len(metadata_ids) > 1 or any(nonempty(value) for value in metadata_ids)
    )
    ancestors = {value for value in map(nonempty, metadata_ids) if value and value != normalized_leaf}
    inferred = next(iter(ancestors)) if len(ancestors) == 1 else None
    if not has_ancestor:
        return Shape(False, None, None, inferred)

    last_raw: Totals | None = None
    pending_context: tuple[int, Totals] | None = None
    suffix_start: int | None = None
    suffix_baseline: Totals | None = None
    inspected_first_suffix_total = False
    saw_authoritative_metadata = False
    for record in records:
        if record.kind == "metadata" and record.metadata:
            current_id = nonempty(record.metadata.session_id)
            embedded = saw_authoritative_metadata and (current_id != normalized_leaf if normalized_leaf else True)
            saw_authoritative_metadata = True
            if embedded:
                suffix_start = None
                suffix_baseline = None
                inspected_first_suffix_total = False
            pending_context = None
        elif record.kind == "context":
            pending_context = (record.line_index, last_raw) if last_raw is not None else None
        elif record.kind == "communication":
            if suffix_start is None and record.trigger_turn and pending_context and record.line_index == pending_context[0] + 1:
                suffix_start, suffix_baseline = pending_context
                inspected_first_suffix_total = False
            pending_context = None
        elif record.kind == "tokens":
            if not inspected_first_suffix_total and suffix_start is not None and record.total is not None:
                inspected_first_suffix_total = True
                if record.last is not None and record.total == record.last and suffix_baseline and not at_least(record.total, suffix_baseline):
                    suffix_baseline = ZERO
            if record.total is not None:
                last_raw = record.total
            pending_context = None
    return Shape(True, suffix_start, suffix_baseline, inferred)


class SnapshotResolver:
    def __init__(self, paths: Iterable[Path], roots: Iterable[Path], diagnostics: Any):
        self.diagnostics = diagnostics
        candidates = set(paths)
        for root in roots:
            if root.is_file():
                candidates.add(root)
            elif root.is_dir():
                candidates.update(root.rglob("*.jsonl"))
        self.index: dict[str, Path] = {}
        for path in sorted(candidates):
            metadata = first_metadata(path, diagnostics)
            if metadata and metadata.session_id:
                self.index.setdefault(metadata.session_id, path)
        self.cache: dict[str, list[tuple[str, dt.datetime | None, Totals]] | None] = {}

    def snapshots(self, session_id: str) -> list[tuple[str, dt.datetime | None, Totals]] | None:
        if session_id in self.cache:
            return self.cache[session_id]
        path = self.index.get(session_id)
        if path is None:
            self.cache[session_id] = None
            return None
        records = read_records(path, self.diagnostics, count_diagnostics=False)
        token_records = [
            record for record in records
            if record.kind == "tokens" and record.timestamp and (record.last is not None or record.total is not None)
        ]
        if any(parse_time(record.timestamp) is None for record in token_records):
            # A malformed timestamp cannot safely participate in an ordered
            # parent snapshot. Reject the whole baseline rather than allowing
            # its counters to contaminate later valid snapshots.
            self.diagnostics.codex_invalid_parent_timestamps += 1
            self.diagnostics.warn(
                "One Codex parent trace had an unparseable token timestamp; "
                "treated its inherited baseline as unresolved."
            )
            self.cache[session_id] = None
            return None
        # Parent baselines are temporal facts. Codex JSONL is normally append-
        # ordered, but a restored/merged trace can be physically out of order.
        token_records.sort(
            key=lambda record: (
                parse_time(record.timestamp),
                record.line_index,
            )
        )
        accumulator = SnapshotAccumulator()
        snapshots: list[tuple[str, dt.datetime | None, Totals]] = []
        for record in token_records:
            snapshots.append((record.timestamp, parse_time(record.timestamp), accumulator.apply(record.last, record.total)))
        self.cache[session_id] = snapshots
        return snapshots

    def inherited(self, session_id: str, cutoff: str | None) -> tuple[bool, Totals | None]:
        if not cutoff:
            return False, None
        snapshots = self.snapshots(session_id)
        if snapshots is None:
            return False, None
        cutoff_date = parse_time(cutoff)
        if cutoff_date is None:
            return False, None
        inherited: Totals | None = None
        for _timestamp, timestamp_date, totals in snapshots:
            before = timestamp_date <= cutoff_date if timestamp_date is not None else False
            if before:
                inherited = totals
        return True, inherited


@dataclasses.dataclass(slots=True)
class SnapshotAccumulator:
    counted: Totals | None = None
    raw_baseline: Totals | None = None
    divergent: bool = False
    tracker: Tracker = dataclasses.field(default_factory=Tracker)

    def apply(self, last: Totals | None, total: Totals | None) -> Totals:
        base = self.counted or ZERO
        if total is not None:
            if self.tracker.is_seen(total):
                return base
            self.tracker.latch(total)
        water = self.tracker.watermark or self.raw_baseline
        if last is not None:
            delta = last
            if total is not None:
                if self.tracker.interleaved:
                    delta = post_latch_delta(water, self.counted, total, last)
                else:
                    candidate = total_delta(water, total)
                    if prefer_total_delta(water, total, candidate, last, self.divergent):
                        delta = candidate
                self.counted = base + delta
                self.raw_baseline = total
                if self.raw_baseline != self.counted:
                    self.divergent = True
                self.tracker.commit(total)
                return self.counted
            self.counted = base + delta
            self.raw_baseline = self.counted
            self.tracker.raise_watermark(self.counted)
            return self.counted
        if total is not None:
            if self.tracker.interleaved:
                delta = contained_delta(water, self.counted, total)
            elif self.divergent:
                delta = divergent_delta(water, self.counted, total)
            else:
                delta = total_delta(water, total)
            self.counted = base + delta
            self.raw_baseline = total
            if self.raw_baseline != self.counted:
                self.divergent = True
            self.tracker.commit(total)
        return self.counted or base


def normalize_model(raw: str | None) -> str:
    model = nonempty(raw) or "unknown"
    if model.startswith("openai/"):
        model = model.removeprefix("openai/")
    if model == "gpt-5.6":
        return "gpt-5.6-sol"
    return model


def parse_file(path: Path, resolver: SnapshotResolver, diagnostics: Any) -> Iterator[Delta]:
    records = read_records(path, diagnostics)
    leaf = next((record.metadata for record in records if record.kind == "metadata" and record.metadata), None)
    session_id = leaf.session_id if leaf and leaf.session_id else path.stem
    parent_id = leaf.parent_id if leaf else None
    fork_timestamp = leaf.fork_timestamp if leaf else None
    is_subagent = bool(leaf and leaf.subagent)
    shape = classify_shape(session_id, records) if is_subagent else Shape(False, None, None, None)
    parent_id = parent_id or shape.inferred_parent_id

    owned_boundary = shape.owned_suffix_start is not None
    independent = is_subagent and not shape.copied_prefix
    suppress_all = is_subagent and shape.copied_prefix and not owned_boundary and parent_id is None
    if suppress_all:
        diagnostics.codex_ambiguous_copied_prefixes += 1
        diagnostics.warn("One Codex copied-prefix subagent had no unique parent or owned-suffix boundary; suppressed the ambiguous file to avoid double counting.")
    inherited: Totals | None = None
    remaining_inherited: Totals | None = None
    unresolved = False
    if parent_id and not independent and not owned_boundary:
        resolved, inherited = resolver.inherited(parent_id, fork_timestamp)
        unresolved = not resolved
        remaining_inherited = inherited
        if resolved and inherited:
            diagnostics.fork_prefix_tokens_suppressed["codex"] += inherited.tokens
        elif unresolved:
            diagnostics.codex_unresolved_forks += 1
            diagnostics.warn("One Codex fork parent baseline could not be resolved; skipped its first cumulative snapshot and counted later contained growth.")
    if owned_boundary:
        diagnostics.codex_owned_suffixes += 1
        records = [record for record in records if record.line_index >= int(shape.owned_suffix_start)]

    previous: Totals | None = None
    raw_baseline = shape.owned_suffix_baseline if owned_boundary else None
    divergent = False
    tracker = Tracker(watermark=raw_baseline)
    unresolved_watermark: Totals | None = None
    current_model: str | None = None
    current_turn: str | None = None
    event_index = 0

    def adjust_last(raw: Totals) -> Totals:
        nonlocal remaining_inherited
        if remaining_inherited is None:
            return raw
        remaining = remaining_inherited
        adjusted = Totals(
            max(0, raw.input - remaining.input),
            max(0, raw.cached - remaining.cached),
            max(0, raw.output - remaining.output),
        )
        remaining = Totals(
            max(0, remaining.input - raw.input),
            max(0, remaining.cached - raw.cached),
            max(0, remaining.output - raw.output),
        )
        remaining_inherited = None if remaining == ZERO else remaining
        return adjusted

    for record in records:
        if record.kind == "context":
            if record.model is not None:
                current_model = record.model
            continue
        if record.kind == "task":
            current_turn = record.turn_id
            continue
        if record.kind != "tokens" or not record.timestamp or suppress_all:
            continue
        timestamp = parse_time(record.timestamp)
        if timestamp is None:
            continue
        adjusted_total = record.total
        if adjusted_total is not None and inherited is not None and not unresolved:
            adjusted_total = total_delta(inherited, adjusted_total)
        if adjusted_total is not None:
            if tracker.is_seen(adjusted_total):
                continue
            tracker.latch(adjusted_total)
        water = tracker.watermark or raw_baseline
        delta = ZERO
        handled_unresolved = unresolved and record.total is not None
        if handled_unresolved and record.total is not None:
            current_raw = record.total
            if record.last is not None and unresolved_watermark is not None:
                delta = min_totals(record.last, total_delta(water, current_raw))
                previous = (previous or ZERO) + delta
                raw_baseline = previous
            elif record.last is None:
                diagnostics.codex_unresolved_total_only_rows += 1
            unresolved_watermark = current_raw
        elif adjusted_total is not None and parent_id and not unresolved:
            delta = post_latch_delta(water, previous, adjusted_total, adjust_last(record.last) if record.last else None) \
                if tracker.interleaved else (
                    divergent_delta(water, previous, adjusted_total) if divergent else total_delta(water, adjusted_total)
                )
            previous = (previous or ZERO) + delta
            raw_baseline = adjusted_total
            divergent = divergent or raw_baseline != previous
            remaining_inherited = None
        elif record.last is not None:
            raw_delta = record.last
            had_remaining = remaining_inherited is not None
            delta = adjust_last(raw_delta)
            if adjusted_total is not None:
                if tracker.interleaved:
                    delta = post_latch_delta(water, previous, adjusted_total, delta)
                    remaining_inherited = None
                else:
                    candidate = total_delta(water, adjusted_total)
                    if not had_remaining and prefer_total_delta(water, adjusted_total, candidate, raw_delta, divergent):
                        delta = candidate
                        remaining_inherited = None
                previous = (previous or ZERO) + delta
                raw_baseline = adjusted_total
                divergent = divergent or raw_baseline != previous
            else:
                previous = (previous or ZERO) + delta
                raw_baseline = previous
                tracker.raise_watermark(previous)
        elif adjusted_total is not None:
            delta = contained_delta(water, previous, adjusted_total) if tracker.interleaved else (
                divergent_delta(water, previous, adjusted_total) if divergent else total_delta(water, adjusted_total)
            )
            previous = (previous or ZERO) + delta
            raw_baseline = adjusted_total
            divergent = divergent or raw_baseline != previous
            remaining_inherited = None
        if adjusted_total is not None:
            tracker.commit(adjusted_total)
        if delta == ZERO:
            continue
        if tracker.interleaved:
            diagnostics.codex_interleaved_files.add(str(path))
        model = normalize_model(current_model or record.model)
        diagnostics.rows_used["codex"] += 1
        if model == "unknown":
            diagnostics.unattributed_tokens["codex"] += delta.tokens
        quality = ["codex-lineage-aware"]
        if parent_id:
            quality.append("codex-parent-baseline-resolved" if not unresolved else "codex-parent-baseline-unresolved")
        if tracker.interleaved:
            quality.append("codex-interleaved-watermark")
        yield Delta(timestamp, model, session_id, event_index, record.turn_id or current_turn, delta, tuple(quality))
        event_index += 1


def scan(paths: Iterable[Path], roots: Iterable[Path], diagnostics: Any) -> Iterator[Delta]:
    paths = sorted(set(paths))
    resolver = SnapshotResolver(paths, roots, diagnostics)
    seen: set[tuple[Any, ...]] = set()
    for path in paths:
        diagnostics.files_scanned["codex"] += 1
        for event in parse_file(path, resolver, diagnostics):
            key = (
                event.session_id, event.turn_id, event.event_index,
                event.timestamp.date().isoformat(), event.model,
                event.usage.input, event.usage.cached, event.usage.output,
            )
            if key in seen:
                continue
            seen.add(key)
            yield event
