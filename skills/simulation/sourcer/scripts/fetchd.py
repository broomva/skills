"""The fetch daemon -- the only thing in sourcer that may put bytes on disk.

This module exists because of a measurement, not a preference. `verify_snapshot`
in data-provider returns True for a zero-byte payload, True when the cited url is
swapped for an unrelated one, and True for bytes that were authored rather than
fetched. It never reads the url at all. That is not a bug: its docstring claims
storage integrity and delivers exactly that. But it means **hashing is not
custody**, and no stricter assertion can fix it, because every integrity check
sits downstream of a producer that could have written the bytes itself.

So the repair is architectural. Crawl agents get no network tool and no write
access to `snapshots/` or `fetchlog.jsonl`; this daemon is the only writer, and
it runs under a different uid. Fabricating evidence stops being something a gate
must detect and becomes a path that is not callable.

That split is also what makes a second signature worth anything. A second signer
adds evidence only if its claim has a different upstream, and two agents reading
one snapshot would otherwise be one claim signed twice. Here the daemon attests
*these bytes came from this URL* and the extractor attests *this claim came from
these bytes* -- different propositions, genuinely disjoint custody.

WHAT THIS MODULE CANNOT VERIFY ABOUT ITSELF. The uid separation and the absent
network tool are deployment properties. A crawl agent sharing a uid with the
daemon can rewrite the log and recompute the chain -- which is precisely why the
chain is keyed with a secret held in the daemon's environment and never written
into the run directory. Tamper-evidence against an accident is a plain hash;
tamper-evidence against a process that can read the log requires a key it cannot.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

CHAIN_KEY_ENV = "SOURCER_CHAIN_KEY"
USER_AGENT = "sourcer/0.1 (+https://github.com/broomva/skills)"
DEFAULT_INTERVAL = 1.0
MAX_BYTES = 8 * 1024 * 1024


class FetchError(Exception):
    """A refusal. Never a fallback -- a fetch that did not happen is not bytes."""


class RobotsRefusal(FetchError):
    """The host's robots.txt disallows this path."""


class ChainBroken(FetchError):
    """The fetch log does not verify, so nothing in it may be attested.

    Deliberately fatal rather than falsy. A broken chain does not mean "this
    pair was not fetched"; it means the log is not evidence about any pair, and
    a caller that reads a False here would draw the smaller conclusion.
    """


def sha256_of(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class FetchResult:
    url: str
    sha256: str
    snapshot: str
    status: int
    tool: str
    retrieved_at: float
    n_bytes: int

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "sha256": self.sha256,
            "snapshot": self.snapshot,
            "status": self.status,
            "tool": self.tool,
            "retrieved_at": self.retrieved_at,
            "n_bytes": self.n_bytes,
        }


# --------------------------------------------------------------------------
# The keyed chain
# --------------------------------------------------------------------------


def _chain_key() -> bytes:
    """The per-run secret. Absent key is a hard refusal, never a default.

    Falling back to an empty key would produce a chain that verifies and proves
    nothing -- the exact shape of a gate that passes while measuring nothing.
    """
    key = os.environ.get(CHAIN_KEY_ENV)
    if not key:
        raise FetchError(
            f"{CHAIN_KEY_ENV} is unset. The fetch log's chain is keyed so that a "
            "process which can READ the log cannot recompute it after editing. "
            "Without the key there is no custody, so this refuses rather than "
            "writing an unkeyed chain that would look identical to a real one."
        )
    return key.encode("utf-8")


def _row_mac(prev_mac: str, row: dict, key: bytes) -> str:
    """MAC over the predecessor and this row's canonical bytes."""
    body = json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, prev_mac.encode("utf-8") + body, hashlib.sha256).hexdigest()


def genesis_row(plan_digest: str, key: Optional[bytes] = None) -> dict:
    """The chain's first row, committing to the sealed plan.

    Binding the plan digest here is what stops a run growing its own denominator:
    a plan rewritten afterwards no longer matches the genesis the chain is
    anchored to, and every later MAC depends on that anchor.
    """
    key = key or _chain_key()
    row = {"kind": "genesis", "plan_digest": plan_digest, "at": time.time()}
    row["mac"] = _row_mac("", row, key)
    return row


def append_row(log_path: Path, row: dict, key: Optional[bytes] = None) -> dict:
    """Append one row, chained to its predecessor. Append-only by construction."""
    key = key or _chain_key()
    prev_mac = ""
    if log_path.exists():
        lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
        if lines:
            prev_mac = json.loads(lines[-1])["mac"]
    body = dict(row)
    body.pop("mac", None)
    body["mac"] = _row_mac(prev_mac, {k: v for k, v in body.items() if k != "mac"}, key)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(body, sort_keys=True) + "\n")
    return body


def verify_chain(log_path: Path, key: Optional[bytes] = None) -> tuple[bool, str]:
    """Recompute every MAC. Returns (ok, reason).

    Returns a reason rather than raising so the gate suite can report which row
    broke: "the log is bad" is not actionable, "row 412 was edited" is.
    """
    key = key or _chain_key()
    if not log_path.exists():
        return False, "fetch log does not exist"
    prev_mac = ""
    n = 0
    for i, line in enumerate(log_path.read_text().splitlines()):
        if not line.strip():
            continue
        n += 1
        row = json.loads(line)
        claimed = row.get("mac")
        recomputed = _row_mac(prev_mac, {k: v for k, v in row.items() if k != "mac"}, key)
        if claimed != recomputed:
            return False, f"row {i}: mac mismatch (row edited, reordered or forged)"
        prev_mac = claimed
    if n == 0:
        return False, "fetch log is empty -- an empty chain verifies vacuously"
    return True, f"{n} rows chained"


# --------------------------------------------------------------------------
# Politeness
# --------------------------------------------------------------------------


class Politeness:
    """robots.txt and a per-host floor between requests.

    robots is fetched once per host and itself snapshotted, so the claim "robots
    allowed this" is checkable after the fact against the bytes that were read
    rather than against the daemon's memory of them.
    """

    def __init__(self, interval: float = DEFAULT_INTERVAL) -> None:
        self.interval = interval
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}

    def host_of(self, url: str) -> str:
        return urllib.parse.urlsplit(url).netloc

    def allows(self, url: str) -> bool:
        host = self.host_of(url)
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            parts = urllib.parse.urlsplit(url)
            rp.set_url(f"{parts.scheme}://{host}/robots.txt")
            try:
                rp.read()
            except Exception:
                # A host with no reachable robots.txt is treated as permitting.
                # This is the documented convention, and stating it matters:
                # silence here is an inference, not a permission granted.
                self._robots[host] = rp
                return True
            self._robots[host] = rp
        return self._robots[host].can_fetch(USER_AGENT, url)

    def wait(self, url: str, sleeper=time.sleep, clock=time.monotonic) -> float:
        host = self.host_of(url)
        now = clock()
        last = self._last.get(host)
        waited = 0.0
        if last is not None:
            gap = now - last
            if gap < self.interval:
                waited = self.interval - gap
                sleeper(waited)
        self._last[host] = clock()
        return waited


# --------------------------------------------------------------------------
# The daemon
# --------------------------------------------------------------------------


class FetchDaemon:
    """Puts bytes on disk and records that it did. Nothing else may.

    `transport` is injectable so the invariants can be tested without a network,
    but note what that does NOT weaken: the daemon still content-addresses what
    it is handed, still refuses non-2xx as evidence, and still chains the row.
    A test transport can return bad bytes; it cannot make the daemon record them
    as good.
    """

    def __init__(
        self,
        root: Path,
        run_id: str,
        politeness: Optional[Politeness] = None,
        transport=None,
        key: Optional[bytes] = None,
    ) -> None:
        self.root = Path(root)
        self.run_id = run_id
        self.dir = self.root / run_id
        self.snapshots = self.dir / "snapshots"
        self.log = self.dir / "fetchlog.jsonl"
        self.politeness = politeness or Politeness()
        self.transport = transport or self._http
        self.key = key or _chain_key()
        self._chain_cache: Optional[tuple] = None

    # -- transport ---------------------------------------------------------

    @staticmethod
    def _http(url: str) -> tuple[int, bytes]:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read(MAX_BYTES)
        except urllib.error.HTTPError as exc:
            # The error body is NOT evidence, but the status is a fact worth
            # recording -- a 404 body stored and read as a page is a defect this
            # daemon is meant to make impossible, so the status travels with it.
            return exc.code, exc.read(MAX_BYTES)

    # -- api ---------------------------------------------------------------

    def seal_plan(self, plan: dict) -> str:
        """Write the plan once, and anchor the chain to its digest."""
        self.dir.mkdir(parents=True, exist_ok=True)
        plan_path = self.dir / "plan.json"
        if plan_path.exists():
            raise FetchError(
                "plan.json already exists -- the plan is sealed before the first "
                "fetch and never rewritten, because a plan edited afterwards makes "
                "what was found look like what was planned."
            )
        body = json.dumps(plan, sort_keys=True, indent=2) + "\n"
        plan_path.write_text(body, encoding="utf-8")
        digest = sha256_of(body.encode("utf-8"))
        row = genesis_row(digest, self.key)
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        return digest

    def fetch(self, url: str) -> FetchResult:
        """Fetch, store content-addressed, and chain the row. The only writer."""
        if not self.politeness.allows(url):
            raise RobotsRefusal(f"robots.txt disallows {url}")
        self.politeness.wait(url)

        status, payload = self.transport(url)
        digest = sha256_of(payload)
        self.snapshots.mkdir(parents=True, exist_ok=True)

        # Content-addressed: the filename IS the digest, so a collision means
        # the bytes are identical and two agents fetching one page is
        # deduplication rather than a race. This is what lets the store be
        # written by many workers without a lock on this path.
        target = self.snapshots / digest
        if not target.exists():
            target.write_bytes(payload)

        result = FetchResult(
            url=url,
            sha256=digest,
            snapshot=f"snapshots/{digest}",
            status=status,
            tool="urllib",
            retrieved_at=time.time(),
            n_bytes=len(payload),
        )
        append_row(self.log, {"kind": "fetch", **result.as_dict()}, self.key)
        return result

    # -- checks ------------------------------------------------------------

    def usable_as_evidence(self, res: FetchResult) -> tuple[bool, str]:
        """May a claim cite this fetch as `observed`?

        Separate from `fetch` on purpose. Recording what happened and deciding
        what it licenses are different jobs, and a daemon that silently dropped
        non-2xx responses would erase the evidence that a page was missing.
        """
        if not (200 <= res.status < 300):
            return False, f"status {res.status} is not a page"
        if res.n_bytes == 0:
            return False, "zero bytes -- an empty payload hashes and verifies fine"
        return True, "ok"

    def evidence_for(
        self, res: FetchResult, span_start: int, span_end: int
    ) -> dict:
        """The ONLY supported way to turn a fetch into a citable evidence record.

        Every precondition is checked here rather than left for the extractor to
        remember, because "remember to call usable_as_evidence first" is exactly
        the shape that already failed once in this module: a correct check with
        no caller. Routing construction through one function removes the case
        instead of documenting it.

        Returns a plain dict rather than a store.Evidence so this module stays
        below the store in the dependency order -- the daemon must not need to
        know what a record is.
        """
        ok, why = self.usable_as_evidence(res)
        if not ok:
            raise FetchError(f"{res.url}: not citable as evidence -- {why}")
        if not self.attests(res.url, res.sha256):
            raise ChainBroken(
                f"{res.url}: no chained log row pairs this url with {res.sha256[:12]}"
            )
        if span_start < 0 or span_end <= span_start:
            raise FetchError(
                f"span [{span_start},{span_end}) is empty or inverted -- a citation "
                "must point at bytes that exist"
            )
        payload = (self.dir / res.snapshot).read_bytes()
        if span_end > len(payload):
            raise FetchError(
                f"span [{span_start},{span_end}) runs past the artifact "
                f"({len(payload)} bytes)"
            )
        quote = payload[span_start:span_end]
        if not quote.strip():
            raise FetchError(
                f"span [{span_start},{span_end}) is whitespace -- a span that says "
                "nothing supports nothing"
            )
        return {
            "url": res.url,
            "sha256": res.sha256,
            "snapshot": res.snapshot,
            "span_start": span_start,
            "span_end": span_end,
            "quote": quote.decode("utf-8", errors="replace"),
        }

    def pairs(self) -> set[tuple[str, str]]:
        """Every (url, digest) this run actually fetched.

        VERIFIES THE CHAIN FIRST, and refuses if it does not hold. The first
        version of this method did not, and the omission voided the module's
        whole claim: `verify_chain` existed, was correct, and was called by
        nothing. A forged row appended without the key broke the chain AND was
        still reported by `attests` as a genuine fetch -- two checks that were
        each individually right and never composed.

        The lesson generalises past this bug: a check nobody calls is not a
        weaker check, it is an absent one, and the grep that finds zero callers
        is cheaper than the reasoning that assumes one.
        """
        ok, reason = self.chain_ok()
        if not ok:
            raise ChainBroken(
                f"refusing to attest anything from an unverifiable fetch log: "
                f"{reason}. Every (url, digest) pair in it is unusable, because "
                "a log that can be edited can be edited to contain any pair."
            )
        out: set[tuple[str, str]] = set()
        for line in self.log.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") == "fetch":
                out.add((row["url"], row["sha256"]))
        return out

    def chain_ok(self) -> tuple[bool, str]:
        """Verify the log's chain, memoised on the file's identity.

        Memoised because `attests` is called per claim and the log grows to
        thousands of rows; keyed on (size, mtime_ns) so that any write -- which
        is the only thing that can invalidate the result -- misses the cache.
        """
        try:
            st = self.log.stat()
        except FileNotFoundError:
            return False, "fetch log does not exist"
        stamp = (st.st_size, st.st_mtime_ns)
        if self._chain_cache is not None and self._chain_cache[0] == stamp:
            return self._chain_cache[1]
        result = verify_chain(self.log, self.key)
        self._chain_cache = (stamp, result)
        return result

    def attests(self, url: str, digest: str) -> bool:
        """Did THIS daemon fetch THESE bytes from THIS url?

        The question `verify_snapshot` cannot answer, and the reason this module
        exists. A snapshot whose digest matches its own content but whose pair is
        absent from the chained log was never fetched -- it was authored.

        Raises `ChainBroken` rather than returning False when the log does not
        verify. False would say "this was not fetched", which is a different and
        much less alarming fact than "this log cannot be trusted about anything".
        """
        return (url, digest) in self.pairs()
