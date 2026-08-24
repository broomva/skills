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
import shlex
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
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


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# The characters the Parallax `--table` grammar uses as delimiters. A name
# containing one of them does not produce a bad column, it produces EXTRA
# columns -- `name` = "a,b:number:observed" injects a whole second typed column
# with a provenance nobody asserted. Refused at the boundary, not escaped.
_RESERVED = (",", ":", "#")


@dataclass(frozen=True)
class Evidence:
    """The artifact a value was read from.

    `sha256` is over the bytes actually read, not over the URL. A citation
    without it decays silently: the page changes, the reference still resolves,
    and nothing anywhere reports that the sentence it supported is gone.

    The digest is shape-checked on construction, because the failure it prevents
    is not a typo: a review found `sha256="aaaa"` sailing through as `observed`,
    which is a citation that cannot be checked wearing the word that means it was.
    """

    url: str
    sha256: str
    retrieved_at: str
    snapshot: str  # path, relative to the run directory

    def __post_init__(self) -> None:
        if not self.url or not self.url.strip():
            raise ProviderError("EVIDENCE_INCOMPLETE", "evidence needs the url it was read from")
        if not _SHA256.match(self.sha256 or ""):
            raise ProviderError(
                "EVIDENCE_INCOMPLETE",
                f"evidence sha256 must be 64 hex characters, got {self.sha256!r}",
                sha256=self.sha256,
            )
        if not self.snapshot or not self.snapshot.strip():
            raise ProviderError(
                "EVIDENCE_INCOMPLETE",
                "evidence needs the snapshot path of what was actually read",
            )
        # The snapshot path is joined onto the run directory, and `Path("a") /
        # "/etc/passwd"` in Python DISCARDS the left operand. So an absolute path
        # here does not point inside the run, it points anywhere on the disk --
        # and `verify_snapshot` would then happily confirm the digest of a file
        # the run never fetched. A citation that can be satisfied by an arbitrary
        # local file is not a citation.
        if PurePosixPath(self.snapshot).is_absolute() or self.snapshot.startswith("/"):
            raise ProviderError(
                "EVIDENCE_ESCAPES_RUN",
                f"snapshot path {self.snapshot!r} is absolute; it must be relative to the run directory",
                snapshot=self.snapshot,
            )
        if ".." in PurePosixPath(self.snapshot).parts:
            raise ProviderError(
                "EVIDENCE_ESCAPES_RUN",
                f"snapshot path {self.snapshot!r} climbs out of the run directory",
                snapshot=self.snapshot,
            )

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
    bad = [c for c in _RESERVED if c in name]
    if bad:
        raise ProviderError(
            "RESERVED_CHARACTER",
            f"field {name!r} contains {bad!r}, which the --table grammar uses as a delimiter; "
            "a name carrying one injects extra columns rather than producing a bad one",
            field=name,
            characters=bad,
        )
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
        # EXACTLY ONE occurrence in every record, not `len(seen) == len(rows)`.
        # The count was equal in a case it should not have been: two duplicate
        # fields in one record and none in a second gives 2 == 2, so a column
        # ABSENT from half the data reported as fully observed. Counting per
        # record removes the coincidence.
        per_record = [[f for f in r.fields if f.name == n] for r in rows]
        complete = all(len(fs) == 1 for fs in per_record)
        seen = [f for fs in per_record for f in fs]
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


def verify_records(root: Path, run_id: str, records: Iterable[Record]) -> None:
    """Every `observed` field must have an artifact that is THERE and still hashes.

    This is the check whose absence made R1 decorative. `make_field` asked for an
    Evidence object and believed it; nothing opened the snapshot or compared the
    digest, so a citation pointing at a file that was never written -- or at one
    whose contents had since changed -- was indistinguishable from a citation
    that held. The word `observed` was doing work no code backed.

    Raises rather than downgrading to `simulated`. Silently reclassifying would
    hide a broken pipeline behind a plausible-looking table, and the caller who
    believes their evidence is intact deserves to be told it is not.
    """
    broken: list[str] = []
    for r in records:
        for f in r.fields:
            if f.evidence is None:
                continue
            if not verify_snapshot(root, run_id, f.evidence):
                broken.append(f"{f.name} ({f.evidence.url})")
    if broken:
        raise ProviderError(
            "EVIDENCE_UNVERIFIED",
            f"{len(broken)} observed field(s) cite an artifact that is missing or no longer hashes to its digest",
            fields=broken,
        )


def emit_table_arg(table: str, records: list[Record], *, evidence_verified: bool = False) -> str:
    """Build the `--table` value Parallax's CLI grammar expects.

    `<name>#<rows>:<col>:<type>:<origin>,...` -- and the row count is len(records),
    not a number anyone typed. This function is what makes the handoff
    type-preserving rather than lossy: the observed/simulated distinction the
    provider established survives into the proposal a human accepts.
    """
    # The default is to REFUSE. `verify_records` is called by the CLI, and a
    # library caller reaching this function directly would otherwise skip it --
    # so the one check the whole layer rests on would be enforced by the entry
    # point a reviewer happened to look at, and absent from the one they did not.
    #
    # An unverified emit is still possible; it just has to be said out loud.
    if not evidence_verified and any(f.evidence is not None for r in records for f in r.fields):
        raise ProviderError(
            "EVIDENCE_UNVERIFIED",
            "records contain observed fields but their artifacts were not verified; "
            "call verify_records(root, run_id, records) first, or pass evidence_verified=True "
            "to state deliberately that they were checked some other way",
        )
    if not table or not table.strip():
        raise ProviderError("TABLE_NAME_REQUIRED", "a table needs a name")
    bad = [c for c in _RESERVED if c in table]
    if bad:
        raise ProviderError(
            "RESERVED_CHARACTER",
            f"table {table!r} contains {bad!r}, which the --table grammar uses as a delimiter",
            table=table,
            characters=bad,
        )
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
    # Checked HERE as well as in `make_field`. `Field` is a plain dataclass, so a
    # caller can build one directly and skip the constructor entirely -- and a
    # name of "a,b" then emits `leads#1:a,b:string:observed`, which parses as TWO
    # columns, the second carrying a provenance nobody asserted. Validating only
    # at the constructor protects the path that goes through the constructor.
    for name in origins:
        bad = [c for c in _RESERVED if c in name]
        if bad:
            raise ProviderError(
                "RESERVED_CHARACTER",
                f"column {name!r} contains {bad!r}, which the --table grammar uses as a delimiter",
                column=name,
                characters=bad,
            )
    parts: list[str] = []
    for name in origins:
        values = [f.value for r in records for f in r.fields if f.name == name]
        col_type = infer_type(values)
        # A column whose type could not be inferred is emitted WITHOUT one, so
        # that Parallax raises the blocking question. Emitting `string` to keep
        # the string tidy would answer a question nobody asked us.
        if col_type is not None:
            parts.append(f"{name}:{col_type}:{origins[name]}")
        else:
            # An untyped column still knows where its values came from, and the
            # grammar can say so: the type segment is left EMPTY rather than the
            # origin being dropped.
            #
            # An earlier version dropped it, on the stated grounds that "the
            # grammar is positional so an origin cannot be supplied without a
            # type". That was wrong about the grammar, and wrong in the direction
            # that costs the most: the column whose type we could not infer is
            # exactly the one whose provenance a reader most needs, and it was
            # the one where we threw it away. The blocking question about the
            # type is raised either way.
            parts.append(f"{name}::{origins[name]}")
        
    return f"{table}#{len(records)}:{','.join(parts)}"


def emit_command(table: str, records: list[Record], *, evidence_verified: bool = False) -> list[str]:
    """The argv a caller runs. A list, so nothing depends on shell quoting."""
    return [
        "parallax",
        "propose",
        "--kind",
        "business-data",
        "--table",
        emit_table_arg(table, records, evidence_verified=evidence_verified),
    ]


def emit_command_line(table: str, records: list[Record], *, evidence_verified: bool = False) -> str:
    """The same thing as a line a human can paste, quoted by shlex.

    Printing `" ".join(argv)` was fine only while every name was
    shell-innocuous. It is a list first and a string second on purpose: the
    string is a convenience, and the convenience is the part that can be made to
    execute something else.
    """
    return shlex.join(emit_command(table, records, evidence_verified=evidence_verified))


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


def _load_records(path: str) -> list[Record]:
    """Parse the records file into Records, or refuse with a typed error.

    Everything here used to escape as a traceback -- a missing file, malformed
    JSON, a record that is not an object, a field whose evidence is a string.
    The module promises that every failure is `{code, reason}` on stderr with
    exit 2, and a stack trace is not that. A caller cannot branch on a traceback.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProviderError("RECORDS_UNREADABLE", f"cannot read {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            "RECORDS_MALFORMED", f"{path} is not valid JSON: {exc.msg} at line {exc.lineno}"
        ) from exc
    if not isinstance(payload, list):
        raise ProviderError(
            "RECORDS_MALFORMED", f"{path} must be a LIST of records, got {type(payload).__name__}"
        )

    records: list[Record] = []
    for i, raw_record in enumerate(payload):
        if not isinstance(raw_record, dict):
            raise ProviderError(
                "RECORDS_MALFORMED", f"record {i} is not an object", index=i
            )
        fields: list[Field] = []
        for name, spec in raw_record.items():
            if not isinstance(spec, dict):
                # A bare value cannot say where it came from, and guessing on the
                # caller's behalf is the one thing this layer must not do.
                raise ProviderError(
                    "UNCLASSIFIED_FIELD",
                    f"record {i} field {name!r} is a bare value; it needs `evidence` or `inferred_from`",
                    index=i,
                    field=name,
                )
            ev_raw = spec.get("evidence")
            evidence = None
            if ev_raw is not None:
                if not isinstance(ev_raw, dict):
                    raise ProviderError(
                        "EVIDENCE_INCOMPLETE",
                        f"record {i} field {name!r}: evidence must be an object",
                        index=i,
                        field=name,
                    )
                missing = [k for k in ("url", "sha256", "snapshot") if not ev_raw.get(k)]
                if missing:
                    raise ProviderError(
                        "EVIDENCE_INCOMPLETE",
                        f"record {i} field {name!r}: evidence is missing {missing}",
                        index=i,
                        field=name,
                        missing=missing,
                    )
                evidence = Evidence(
                    url=str(ev_raw["url"]),
                    sha256=str(ev_raw["sha256"]),
                    retrieved_at=str(ev_raw.get("retrieved_at", "")),
                    snapshot=str(ev_raw["snapshot"]),
                )
            fields.append(
                make_field(
                    name,
                    spec.get("value"),
                    evidence=evidence,
                    inferred_from=spec.get("inferred_from"),
                )
            )
        records.append(Record(fields=fields))
    return records


def _emit(args: argparse.Namespace) -> int:
    records = _load_records(args.records)
    observed = any(f.evidence is not None for r in records for f in r.fields)
    verified = False
    if observed and not args.unverified:
        # The default is to CHECK. `--unverified` exists so that a caller who
        # genuinely has no run directory can still emit, and it is a flag rather
        # than a fallback so that skipping the check is a decision someone typed.
        verify_records(Path(args.root), args.run, records)
        verified = True
    print(emit_command_line(args.table, records, evidence_verified=verified or args.unverified))
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
    e.add_argument("--run", default="", help="Run id whose evidence/ directory holds the snapshots.")
    e.add_argument("--root", default=".", help="Directory containing .parallax/provider/<run>/.")
    e.add_argument(
        "--unverified",
        action="store_true",
        help="Emit WITHOUT opening the cited artifacts. Off by default: an unchecked citation is not evidence.",
    )
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
