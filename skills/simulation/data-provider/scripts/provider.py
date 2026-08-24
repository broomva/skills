#!/usr/bin/env python3
"""The data provider layer: turn a question about the world into a table Parallax can accept.

WHAT IS DETERMINISTIC HERE, AND WHAT IS NOT

The searching is the agent's job -- it has WebSearch and WebFetch and a model.
This file deliberately does none of it. What it owns is everything that must be
the same every time and checkable afterwards:

    record   a finding, with the artifact it was read from and a hash of that
             artifact's bytes
    judge    each column observed or simulated, by a rule rather than a vibe
    emit     the exact `parallax propose` invocation, as a string
    status   what a run is doing, in numbers that cannot lie about work done

Splitting it this way is the point. A model that both gathers evidence AND
decides whether the evidence is good is grading its own homework; a model that
gathers, and a function that grades against a stated rule, is not.

WHY THERE IS NO SERVER

This was written after examining a prospecting service that failed in five
specific ways, and the shape of this file is the response to each:

  * Its `progress` tracked the STAGE INDEX, not work done -- it read 22% at t+2s
    and 22% at t+67s while the honest counter underneath said 0 of 11 complete.
    Here progress is `done / total` over real units and nothing else can set it.
  * Its completion counter went BACKWARDS, 6 -> 2, because the orchestrator
    restarted rather than resumed. Here `advance` refuses to decrease.
  * It never left `orchestrating`. No run was ever observed reaching a terminal
    state, so "found nothing" and "still working" were indistinguishable forever.
    Here `complete` with zero candidates is a NORMAL, terminal outcome.
  * Its status page returned HTTP 200 with identical bytes whether the backend
    was alive or dead. Here a missing run is an ERROR, not a reassuring 0%.
  * A started run could not be stopped by its caller. Here `cancel` is terminal.

The last two of the seven rules -- a required credential, and cancellation --
exist because that thing was a long-running remote service. This is a script the
agent runs inside its own turn: there is no endpoint to authenticate and nothing
that keeps running after the turn ends. `cancel` is implemented anyway, because a
run's directory outlives the turn and a human may want to close one out. Saying
which rules do not apply, and why, is better than implementing theatre to satisfy
a checklist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

# Parallax keeps its own thread state in `.parallax/`; provider runs live beside
# it rather than in a second top-level directory, so one gitignore rule covers
# both and `parallax status` and this share a home.
STATE_DIR = Path(".parallax") / "provider"

Origin = Literal["observed", "simulated"]
ColumnType = Literal["string", "number", "boolean", "date"]
COLUMN_TYPES: tuple[str, ...] = ("string", "number", "boolean", "date")

# Terminal states. A run in any of these is finished and will not change again.
# `complete` covers the zero-result case on purpose -- see the module docstring.
TERMINAL = ("complete", "failed", "cancelled")


class ProviderError(Exception):
    """A typed refusal. Mirrors Parallax's own {code, reason} shape."""

    def __init__(self, code: str, reason: str, **detail: Any) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "reason": self.reason}
        if self.detail:
            out["detail"] = self.detail
        return out


# ---------------------------------------------------------------------------
# R1 + R2 -- classification at birth, and a citation that resolves
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    """The artifact a value was read from.

    `sha256` is over the bytes actually read, not over the URL. A citation
    without it decays silently: the page changes, the reference still resolves,
    and nothing anywhere reports that the sentence it supported is gone.
    """

    url: str
    sha256: str
    retrieved_at: str
    snapshot: str  # path, relative to the run directory

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "sha256": self.sha256,
            "retrieved_at": self.retrieved_at,
            "snapshot": self.snapshot,
        }


@dataclass(frozen=True)
class Field:
    """One field of one record, and how it came to be known."""

    name: str
    value: Any
    #: Present iff this was READ. Absent means it was concluded, matched or estimated.
    evidence: Evidence | None = None
    #: Why, when there is no evidence. Required for a simulated field, so that
    #: "we guessed" is never the silent default explanation.
    inferred_from: str | None = None

    @property
    def origin(self) -> Origin:
        return "observed" if self.evidence is not None else "simulated"


@dataclass
class Record:
    fields: list[Field] = field(default_factory=list)

    def column_names(self) -> list[str]:
        return [f.name for f in self.fields]


def make_field(
    name: str,
    value: Any,
    *,
    evidence: Evidence | None = None,
    inferred_from: str | None = None,
) -> Field:
    """Build a field, refusing the two ways provenance gets destroyed.

    Both refusals are here rather than at the point of use because this is the
    only constructor: a field cannot come into existence unclassified, which is
    the whole of R1. Parallax types values at birth and has no operator that adds
    provenance later, so a field that gets past this point untagged is
    unrecoverable no matter what anything downstream does.
    """
    if not name or not name.strip():
        raise ProviderError("FIELD_NAME_REQUIRED", "a field needs a name")
    if evidence is not None and inferred_from is not None:
        raise ProviderError(
            "AMBIGUOUS_ORIGIN",
            f"field {name!r} carries both an artifact and an inference note; it is one or the other",
            field=name,
        )
    if evidence is None and not inferred_from:
        # The default that is refused. "Unclassified" silently becoming
        # "simulated" would read as caution and is in fact a fabrication: it
        # asserts we know the value was produced, when we do not know anything.
        raise ProviderError(
            "UNCLASSIFIED_FIELD",
            f"field {name!r} has neither an artifact it was read from nor a note saying what it was inferred from",
            field=name,
        )
    return Field(name=name, value=value, evidence=evidence, inferred_from=inferred_from)


def sha256_of(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# judging -- per-column Origin, by the same meet Parallax uses
# ---------------------------------------------------------------------------


def judge_columns(records: Iterable[Record]) -> dict[str, Origin]:
    """A column is observed only if EVERY value in it was read from an artifact.

    This is `meetOrigin` from Parallax's provenance.ts, applied one column at a
    time: contamination flows one way, so a column with nine cited values and one
    guess is a simulated column. Reporting it as observed because most of it was
    read is exactly the overclaim the type exists to prevent.

    A column absent from a record counts as missing, not as observed -- a gap is
    not evidence.
    """
    rows = list(records)
    names: list[str] = []
    for r in rows:
        for n in r.column_names():
            if n not in names:
                names.append(n)

    out: dict[str, Origin] = {}
    for n in names:
        seen = [f for r in rows for f in r.fields if f.name == n]
        complete = len(seen) == len(rows)
        out[n] = "observed" if complete and all(f.origin == "observed" for f in seen) else "simulated"
    return out


def infer_type(values: Iterable[Any]) -> ColumnType | None:
    """The declared type, or None when the values do not agree on one.

    None is a real answer and becomes a blocking question in Parallax rather than
    a guess. Mixed columns are common in scraped data and quietly calling them
    `string` is how a number stops being addable three layers downstream.
    """
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    if all(isinstance(v, bool) for v in vals):
        return "boolean"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return "number"
    if all(isinstance(v, str) for v in vals):
        return "date" if all(_looks_like_date(v) for v in vals) else "string"
    return None


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]|$)")


def _looks_like_date(s: str) -> bool:
    return bool(_DATE.match(s))


# ---------------------------------------------------------------------------
# emit -- the exact Parallax invocation
# ---------------------------------------------------------------------------


def emit_table_arg(table: str, records: list[Record]) -> str:
    """Build the `--table` value Parallax's CLI grammar expects.

    `<name>#<rows>:<col>:<type>:<origin>,...` -- and the row count is len(records),
    not a number anyone typed. This function is what makes the handoff
    type-preserving rather than lossy: the observed/simulated distinction the
    provider established survives into the proposal a human accepts.
    """
    if not table or not table.strip():
        raise ProviderError("TABLE_NAME_REQUIRED", "a table needs a name")
    if not records:
        # Legal and meaningful: a schema with no rows. It is the caller's job to
        # decide whether zero results is worth proposing at all; it is not this
        # function's job to pretend it cannot be expressed.
        raise ProviderError(
            "NO_RECORDS",
            f"no records to emit for {table!r}; a run that found nothing is complete, not a table",
            table=table,
        )

    origins = judge_columns(records)
    parts: list[str] = []
    for name in origins:
        values = [f.value for r in records for f in r.fields if f.name == name]
        col_type = infer_type(values)
        # A column whose type could not be inferred is emitted WITHOUT one, so
        # that Parallax raises the blocking question. Emitting `string` to keep
        # the string tidy would answer a question nobody asked us.
        segments = [name]
        if col_type is not None:
            segments.append(col_type)
            segments.append(origins[name])
        else:
            # The grammar is positional, so an origin cannot be supplied without a
            # type. An untyped column blocks acceptance anyway, which is the
            # correct outcome and not something to work around here.
            pass
        parts.append(":".join(segments))
    return f"{table}#{len(records)}:{','.join(parts)}"


def emit_command(table: str, records: list[Record]) -> list[str]:
    """The argv a caller runs. Returned as a list so nothing has to be shell-quoted."""
    return ["parallax", "propose", "--kind", "business-data", "--table", emit_table_arg(table, records)]


# ---------------------------------------------------------------------------
# R3 + R4 -- progress that is work done, and a terminal empty state
# ---------------------------------------------------------------------------


@dataclass
class Run:
    run_id: str
    question: str
    total_units: int
    done_units: int = 0
    status: str = "running"
    candidates: int = 0
    started_at: str = ""
    ended_at: str | None = None
    note: str | None = None

    @property
    def progress(self) -> float:
        """Work completed over work planned. Never a stage index.

        The service this rule came from reported 22% twice, sixty-five seconds
        apart, while its own honest counter said zero of eleven strategies had
        finished. The bar looked alive because it was measuring how far through
        its own pipeline it had walked, not how much of the job was done.
        """
        if self.total_units <= 0:
            return 0.0
        return round(self.done_units / self.total_units, 4)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "question": self.question,
            "status": self.status,
            "terminal": self.is_terminal,
            "progress": self.progress,
            "done_units": self.done_units,
            "total_units": self.total_units,
            "candidates": self.candidates,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "note": self.note,
        }


def advance(run: Run, done_units: int, *, candidates: int | None = None) -> Run:
    """Move a run forward. Refuses to move it backwards.

    A completion counter that can decrease is not progress, it is a restart being
    reported as one. The service this came from went 6 -> 2 and the caller had no
    way to tell that from real work.
    """
    if run.is_terminal:
        raise ProviderError(
            "RUN_TERMINAL",
            f"run {run.run_id} is {run.status} and cannot be advanced",
            run_id=run.run_id,
            status=run.status,
        )
    if done_units < run.done_units:
        raise ProviderError(
            "PROGRESS_WENT_BACKWARDS",
            f"run {run.run_id} reported {done_units} done after {run.done_units}; a counter that decreases is a restart, not progress",
            run_id=run.run_id,
            was=run.done_units,
            got=done_units,
        )
    if done_units > run.total_units:
        raise ProviderError(
            "PROGRESS_EXCEEDS_TOTAL",
            f"run {run.run_id} reported {done_units} of {run.total_units} done",
            run_id=run.run_id,
            total=run.total_units,
            got=done_units,
        )
    run.done_units = done_units
    if candidates is not None:
        run.candidates = candidates
    return run


def finish(run: Run, *, candidates: int, note: str | None = None) -> Run:
    """Complete a run. Zero candidates is a normal, terminal outcome.

    This is the case the studied service never reached: no run was observed
    leaving `orchestrating`, so "we looked and there is nothing" was
    indistinguishable from "still going" for as long as anyone was willing to
    wait. Finding nothing is an answer and it terminates.
    """
    if run.is_terminal:
        raise ProviderError(
            "RUN_TERMINAL", f"run {run.run_id} is already {run.status}", run_id=run.run_id
        )
    run.status = "complete"
    run.candidates = candidates
    run.done_units = run.total_units
    run.ended_at = _now()
    run.note = note or ("found nothing" if candidates == 0 else None)
    return run


def cancel(run: Run, *, reason: str) -> Run:
    """Terminal, and available to whoever started the run."""
    if run.is_terminal:
        raise ProviderError(
            "RUN_TERMINAL", f"run {run.run_id} is already {run.status}", run_id=run.run_id
        )
    run.status = "cancelled"
    run.ended_at = _now()
    run.note = reason
    return run


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# R7 -- a missing run is an error, not a reassuring zero
# ---------------------------------------------------------------------------


def load_run(root: Path, run_id: str) -> Run:
    """Read a run, or refuse.

    The rule this enforces is the one that cost an earlier verification its
    credibility: a status surface that answers identically whether the thing it
    reports on exists or not has told you nothing, and reads as if it has. A
    missing run raises; it does not return a run at 0%.
    """
    path = root / STATE_DIR / run_id / "run.json"
    if not path.exists():
        raise ProviderError(
            "RUN_NOT_FOUND",
            f"no run {run_id} under {root / STATE_DIR}; this is not a run at 0%, it is an absent run",
            run_id=run_id,
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return Run(
        run_id=data["run_id"],
        question=data["question"],
        total_units=data["total_units"],
        done_units=data.get("done_units", 0),
        status=data.get("status", "running"),
        candidates=data.get("candidates", 0),
        started_at=data.get("started_at", ""),
        ended_at=data.get("ended_at"),
        note=data.get("note"),
    )


def save_run(root: Path, run: Run) -> Path:
    d = root / STATE_DIR / run.run_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / "run.json"
    path.write_text(json.dumps(run.as_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def save_snapshot(root: Path, run_id: str, url: str, payload: bytes) -> Evidence:
    """Store what was actually read, next to the run that read it."""
    digest = sha256_of(payload)
    d = root / STATE_DIR / run_id / "evidence"
    d.mkdir(parents=True, exist_ok=True)
    rel = f"evidence/{digest}.snapshot"
    (root / STATE_DIR / run_id / rel).write_bytes(payload)
    return Evidence(url=url, sha256=digest, retrieved_at=_now(), snapshot=rel)


def verify_snapshot(root: Path, run_id: str, ev: Evidence) -> bool:
    """Does the stored artifact still hash to what the citation claims?

    Cheap, and the only way a citation can be checked rather than trusted.
    """
    p = root / STATE_DIR / run_id / ev.snapshot
    if not p.exists():
        return False
    return sha256_of(p.read_bytes()) == ev.sha256


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.records).read_text(encoding="utf-8"))
    records: list[Record] = []
    for raw in payload:
        fields = []
        for name, spec in raw.items():
            ev = None
            if isinstance(spec, dict) and "evidence" in spec and spec["evidence"]:
                e = spec["evidence"]
                ev = Evidence(
                    url=e["url"],
                    sha256=e["sha256"],
                    retrieved_at=e.get("retrieved_at", ""),
                    snapshot=e.get("snapshot", ""),
                )
            value = spec.get("value") if isinstance(spec, dict) else spec
            inferred = spec.get("inferred_from") if isinstance(spec, dict) else None
            fields.append(make_field(name, value, evidence=ev, inferred_from=inferred))
        records.append(Record(fields=fields))
    print(" ".join(emit_command(args.table, records)))
    return 0


def _status(args: argparse.Namespace) -> int:
    run = load_run(Path(args.root), args.run)
    print(json.dumps(run.as_dict(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    # __doc__ is None under `python -OO`, so this does not reach into it blindly.
    summary = (__doc__ or "The data provider layer.").splitlines()[0]
    ap = argparse.ArgumentParser(prog="provider", description=summary)
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("emit", help="Turn judged records into a parallax propose invocation.")
    e.add_argument("--table", required=True)
    e.add_argument("--records", required=True, help="JSON file: a list of {column: {value, evidence?, inferred_from?}}")
    e.set_defaults(fn=_emit)

    s = sub.add_parser("status", help="Report a run. A missing run is an error, not 0%%.")
    s.add_argument("--run", required=True)
    s.add_argument("--root", default=".")
    s.set_defaults(fn=_status)

    args = ap.parse_args(argv)
    try:
        return int(args.fn(args))
    except ProviderError as exc:
        print(json.dumps(exc.as_dict(), indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
