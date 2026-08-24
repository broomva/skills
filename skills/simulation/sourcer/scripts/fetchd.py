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

import fcntl
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


class RedirectRefusal(FetchError):
    """The response came from a different url than the one requested."""


class NotAttested(FetchError):
    """No chained log row pairs this url with these bytes.

    Distinct from ChainBroken on purpose. "The log does not mention this" and
    "the log cannot be trusted about anything" are different facts with different
    consequences: the first refuses one record, the second refuses the run.
    """


class ChainBroken(FetchError):
    """The fetch log does not verify, so nothing in it may be attested.

    Deliberately fatal rather than falsy. A broken chain does not mean "this
    pair was not fetched"; it means the log is not evidence about any pair, and
    a caller that reads a False here would draw the smaller conclusion.
    """


def _canonical_url(url: str) -> str:
    """Compare urls by what identifies a resource, not by spelling."""
    p = urllib.parse.urlsplit(url)
    host = (p.hostname or "").lower()
    port = p.port
    default = {"http": 80, "https": 443}.get(p.scheme)
    netloc = host if port in (None, default) else f"{host}:{port}"
    return urllib.parse.urlunsplit((p.scheme.lower(), netloc, p.path or "/", p.query, ""))


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


def _head_path(log_path: Path) -> Path:
    return log_path.with_suffix(log_path.suffix + ".head")


def append_row(log_path: Path, row: dict, key: Optional[bytes] = None) -> dict:
    """Append one chained row, under an exclusive lock, updating the head.

    Three things beyond "write a line", each closing a demonstrated hole:

    * The whole read-predecessor-then-append is held under `flock`. Two fetches
      that read the same predecessor MAC produce sibling rows, and the second
      then fails verification forever -- a fork, not a tamper, but
      indistinguishable from one afterwards.
    * Each row carries a sequence number, so a row cannot be reordered or
      dropped from the middle without the count disagreeing.
    * The head (last MAC + row count) is written to a SIDECAR. Truncating the
      log is otherwise invisible: every surviving row still chains correctly to
      its predecessor, so a run that lost its tail verifies as a complete one.
      The head lives outside the file being truncated, which is the only place
      it can usefully live.
    """
    key = key or _chain_key()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = log_path.with_suffix(log_path.suffix + ".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            prev_mac, seq = "", 0
            if log_path.exists():
                lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
                if lines:
                    last = json.loads(lines[-1])
                    prev_mac = last["mac"]
                    seq = last.get("seq", len(lines) - 1) + 1
            body = {k: v for k, v in row.items() if k != "mac"}
            body["seq"] = seq
            body["mac"] = _row_mac(prev_mac, {k: v for k, v in body.items() if k != "mac"}, key)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(body, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            head = {"mac": body["mac"], "rows": seq + 1}
            # MAC the head itself. Without this it is plain metadata: an adversary
            # who truncates the log copies {mac, rows} from the last surviving row
            # and the sidecar agrees -- the one component of a deliberately keyed
            # chain that a keyless attacker could forge.
            head["hmac"] = hmac.new(
                key, json.dumps(head, sort_keys=True, separators=(",", ":")).encode(),
                hashlib.sha256,
            ).hexdigest()
            head_path = _head_path(log_path)
            with head_path.open("w", encoding="utf-8") as hf:
                hf.write(json.dumps(head, sort_keys=True) + "\n")
                hf.flush()
                os.fsync(hf.fileno())
            return body
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


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
    rows = []
    for i, line in enumerate(log_path.read_text().splitlines()):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            return False, (
                f"row {i}: unparseable -- a torn write or a truncated line. A "
                "malformed log is not a log that says nothing; it is one that "
                "cannot be trusted about anything."
            )
        rows.append(row)
        if n == 0 and row.get("kind") != "genesis":
            return False, (
                "row 0 is not the genesis row -- a log that starts mid-run has "
                "no anchor to the sealed plan, so it verifies without being about "
                "anything in particular"
            )
        if row.get("seq") != n:
            return False, f"row {i}: seq {row.get('seq')!r}, expected {n} (row dropped or reordered)"
        claimed = row.get("mac")
        recomputed = _row_mac(prev_mac, {k: v for k, v in row.items() if k != "mac"}, key)
        if claimed != recomputed:
            return False, f"row {i}: mac mismatch (row edited, reordered or forged)"
        prev_mac = claimed
        n += 1
    if n == 0:
        return False, "fetch log is empty -- an empty chain verifies vacuously"

    head_path = _head_path(log_path)
    if not head_path.exists():
        return False, "head sidecar missing -- truncation would be undetectable"
    head = json.loads(head_path.read_text())
    claimed_hmac = head.pop("hmac", None)
    expected_hmac = hmac.new(
        key, json.dumps(head, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    if claimed_hmac != expected_hmac:
        return False, "head sidecar is not authentic -- it was rewritten without the key"
    if head.get("rows") != n or head.get("mac") != prev_mac:
        return False, (
            f"head says {head.get('rows')} rows ending {str(head.get('mac'))[:12]}, "
            f"log has {n} ending {prev_mac[:12]} -- the log was truncated or replaced"
        )
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
        """The rate-limiting identity of a url.

        Raw netloc made example.com, EXAMPLE.com, example.com:443 and
        a@example.com four distinct hosts, so one server received four times the
        intended request rate while every per-host check still looked satisfied.
        """
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        port = parts.port
        default = {"http": 80, "https": 443}.get(parts.scheme, None)
        return host if port in (None, default) else f"{host}:{port}"

    def allows(self, url: str) -> bool:
        host = self.host_of(url)
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            parts = urllib.parse.urlsplit(url)
            rp.set_url(f"{parts.scheme}://{host}/robots.txt")
            try:
                rp.read()
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    # Explicitly withheld. The convention is that this forbids
                    # the whole site, and guessing otherwise is not ours to do.
                    self._robots[host] = None
                    return False
                if exc.code >= 400:
                    # An explicit absence (404 and friends) is the documented
                    # "no restrictions" case. Naming the codes matters: the
                    # earlier bare `except Exception` also converted parser
                    # defects, malformed urls and programming errors into
                    # permission, so the one branch nobody wanted was the
                    # default.
                    self._robots[host] = rp
                    return True
                self._robots[host] = None
                return False
            except Exception:
                # Network failure, timeout, parser defect, bug. None of these is
                # evidence that crawling is allowed, so fail closed.
                self._robots[host] = None
                return False
            self._robots[host] = rp
        rp = self._robots[host]
        if rp is None:
            return False
        return rp.can_fetch(USER_AGENT, url)

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

    # -- transport ---------------------------------------------------------

    @staticmethod
    def _http(url: str) -> tuple[int, bytes]:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                # urllib follows redirects silently. Attesting the bytes to the
                # url we ASKED for rather than the one that answered would let a
                # crawl cite example.com for content served by anywhere-else.
                final = resp.url
                if _canonical_url(final) != _canonical_url(url):
                    raise RedirectRefusal(
                        f"{url} redirected to {final} -- refetch the final url so "
                        "the attested pair names where the bytes actually came from"
                    )
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
        # Through append_row, not a raw write: genesis needs its seq and must
        # update the head like any other row, or verify_chain's own truncation
        # and ordering checks would refuse the very first line.
        append_row(self.log, {"kind": "genesis", "plan_digest": digest,
                              "at": time.time()}, self.key)
        return digest

    def fetch(self, url: str) -> FetchResult:
        """Fetch, store content-addressed, and chain the row. The only writer.

        Refuses before the plan is sealed. A fetch outside a sealed plan has no
        denominator to be measured against and no genesis row to anchor to, and
        a log that begins with a fetch verifies happily while being about
        nothing in particular.
        """
        if not (self.dir / "plan.json").exists():
            raise FetchError(
                "no sealed plan -- call seal_plan() before the first fetch. The "
                "plan fixes the denominator (seeds, depth bound, fetch budget) "
                "before anything is found, so the run cannot later grow the "
                "number it is measured against."
            )
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
        if target.exists() and sha256_of(target.read_bytes()) != digest:
            # A file already sitting at the content-addressed path whose content
            # does not hash to its own name was not written by this daemon --
            # it was planted, or a previous write was torn. Either way the
            # daemon must not record a digest for bytes it did not verify.
            target.unlink()
        if not target.exists():
            # Write via a temporary file and rename, so a crash mid-write cannot
            # leave a truncated snapshot sitting at a name that claims to be its
            # own hash.
            tmp = target.with_suffix(".partial")
            tmp.write_bytes(payload)
            os.replace(tmp, target)

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
        # Read the receipt back out of the chained log rather than trusting the
        # FetchResult handed in. A caller can construct a FetchResult with any
        # status and length it likes -- including a 200 for a pair that was
        # actually fetched as a 404 -- so validating the argument validates the
        # caller's assertion rather than what happened.
        receipt = self.receipt_for(res.url, res.sha256)
        if receipt is None:
            raise NotAttested(
                f"{res.url}: no chained log row pairs this url with {res.sha256[:12]}"
            )
        ok, why = self.usable_as_evidence(receipt)
        if not ok:
            raise FetchError(f"{res.url}: not citable as evidence -- {why}")
        if span_start < 0 or span_end <= span_start:
            raise FetchError(
                f"span [{span_start},{span_end}) is empty or inverted -- a citation "
                "must point at bytes that exist"
            )
        payload = self.open_attested(res.url, res.sha256)
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
            # From the digest, not from res.snapshot -- the caller does not get to
            # name the file its own citation is read out of.
            "snapshot": f"snapshots/{res.sha256}",
            "span_start": span_start,
            "span_end": span_end,
            "quote": quote.decode("utf-8", errors="replace"),
        }

    def open_attested(self, url: str, digest: str) -> bytes:
        """The bytes this daemon attested for (url, digest). The only reader.

        The path is derived from the DIGEST, never from a caller-supplied field.
        evidence_for previously re-read the receipt out of the chained log to
        defeat a forged status -- and then dereferenced `res.snapshot`, the very
        field it had just finished arguing must not be trusted. Handing it a real
        url, a real digest and `snapshot="authored.bin"` returned a quote from the
        caller's own file; `snapshot="../OUTSIDE.txt"` read outside the run
        directory entirely.

        Content addressing is what makes this safe: the digest IS the filename, so
        there is nothing left for a caller to point at. The re-hash is not
        paranoia -- it catches a snapshot replaced after the fetch.
        """
        if (url, digest) not in self.pairs():   # pairs() raises if the chain is broken
            raise NotAttested(
                f"{url}: no chained log row pairs this url with {digest[:12]} -- "
                "these bytes were never fetched"
            )
        target = self.snapshots / digest
        if not target.is_file():
            raise FetchError(f"{digest[:12]}: attested but its snapshot is missing")
        payload = target.read_bytes()
        actual = sha256_of(payload)
        if actual != digest:
            raise FetchError(
                f"{digest[:12]}: the stored snapshot now hashes to {actual[:12]} -- "
                "it was replaced after the fetch"
            )
        return payload

    def verifies(
        self, url: str, digest: str, span_start: int, span_end: int, quote: str
    ) -> bool:
        """Do the attested bytes at [span_start, span_end) actually say `quote`?

        The question the whole architecture exists to make answerable, and the one
        nothing asked. Custody proved a (url, digest) pair came off a wire and then
        never used those bytes to check the sentence a human reads -- so a
        fabricated quote entered the map carrying a genuine attestation, which is
        strictly worse than no custody, because the metadata is what makes the
        fabrication look verified.

        store.Evidence's own docstring argues for byte offsets over substring
        search: "an offset is a location it had to commit to before the check ran".
        This is where that commitment is finally redeemed.
        """
        try:
            payload = self.open_attested(url, digest)
        except ChainBroken:
            # Deliberately NOT swallowed. A broken chain is not "this quote does
            # not check out"; it is "this log is not evidence about anything", and
            # a caller reading False here would draw the smaller conclusion. Same
            # rule attests() follows -- and this method violated it on the first
            # pass by catching the base class.
            raise
        except FetchError:
            return False
        if span_start < 0 or span_end <= span_start or span_end > len(payload):
            return False
        return payload[span_start:span_end].decode("utf-8", errors="replace") == quote

    def receipt_for(self, url: str, digest: str) -> Optional[FetchResult]:
        """The daemon's own logged record of a fetch, or None.

        Verifies the chain first, via pairs(), so a receipt can never be read
        out of a log that does not hold together.
        """
        if (url, digest) not in self.pairs():
            return None
        for line in self.log.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") == "fetch" and row["url"] == url and row["sha256"] == digest:
                return FetchResult(
                    url=row["url"], sha256=row["sha256"], snapshot=row["snapshot"],
                    status=row["status"], tool=row["tool"],
                    retrieved_at=row["retrieved_at"], n_bytes=row["n_bytes"],
                )
        return None

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
        """Verify the log's chain. Not memoised, deliberately.

        The first version cached on (st_size, st_mtime_ns). Both are attacker-
        controlled: a same-length edit followed by `os.utime` restoring the
        original mtime hits the cache, and a broken chain then reads as verified.
        Cross-model review demonstrated it.

        Any cache key cheap enough to be worth having is derived from metadata an
        editor can restore; a key that is not -- hashing the file -- costs the
        same as the verification it was meant to skip. So the optimisation is
        removed rather than made subtler. Verification is one HMAC per row and
        the caller is doing network I/O.
        """
        return verify_chain(self.log, self.key)

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
