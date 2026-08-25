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


def split_url(url: str):
    """`urlsplit` plus a port read that cannot explode. Returns (parts, port).

    `urlsplit` parses lazily: `https://example.com:bogus/a` splits happily and
    only raises when `.port` is read. Every function here that needed a port was
    therefore one malformed URL away from a `ValueError` its callers do not
    catch -- `host_of`, `origin_of`, `allows`, `wait` and `_canonical_url` all
    had it, and fixing only the copy in traverse.py left all five.

    A malformed authority is a refusal this module owns, so it raises
    `FetchError` and every existing caller already handles it.
    """
    parts = urllib.parse.urlsplit(url)
    try:
        return parts, parts.port
    except ValueError as exc:
        raise FetchError(f"{url}: malformed authority -- {exc}") from exc


def _canonical_url(url: str) -> str:
    """Compare urls by what identifies a resource, not by spelling."""
    p, port = split_url(url)
    host = (p.hostname or "").lower()
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


def verify_run(
    run_dir: Path, key: Optional[bytes] = None
) -> tuple[bool, str, list]:
    """Verify the chain AND that plan.json is still the plan genesis committed to.

    The fourth instance of this module's recurring failure: seal_plan hashed the
    plan into the genesis row, and nothing ever compared that digest to the file
    again. Rewriting plan.json after sealing -- max_depth 2 to 99, budget 50 to
    5000 -- left verify_chain returning True, so the sealed denominator, the whole
    point of sealing, was a check with no reader.

    A run is what its plan says it is. Checking the chain without checking the
    plan verifies that rows were not edited while saying nothing about what they
    were supposed to be rows OF.
    """
    key = key or _chain_key()
    log_path = run_dir / "fetchlog.jsonl"
    ok, reason, rows = verify_chain(log_path, key)
    if not ok:
        return False, reason, []

    plan_path = run_dir / "plan.json"
    if not plan_path.exists():
        return False, "plan.json is missing -- the run has no declared scope", []
    first = rows[0]
    if first.get("kind") != "genesis":
        return False, "no genesis row to anchor the plan to", []
    actual = sha256_of(plan_path.read_bytes())
    if actual != first.get("plan_digest"):
        return False, (
            f"plan.json hashes to {actual[:12]} but genesis committed to "
            f"{str(first.get('plan_digest'))[:12]} -- the plan was rewritten after "
            "the run began, so what was found is being measured against a "
            "denominator it did not start with"
        ), []
    # The rows are RETURNED, not merely blessed. A caller that receives a boolean
    # has to go and read the file again, and the second read is a different read
    # -- which is how an appended row was once consumed as verified. Handing back
    # the verified objects removes the window instead of checking it twice.
    return True, reason, rows


def _verify_rows(rows: list, key: bytes) -> tuple[bool, str]:
    """Verify an already-parsed row list. The single source of chain truth.

    Extracted so `verify_chain` (which reads the file) and `verified_rows` (which
    consumes what it read) run the SAME logic over the SAME objects. Two
    implementations of "is this chain valid" would be two things that can
    disagree, which is the defect this function exists to close, one level up.
    """
    prev_mac, n = "", 0
    for i, row in enumerate(rows):
        if n == 0 and row.get("kind") != "genesis":
            return False, (
                "row 0 is not the genesis row -- a log that starts mid-run has no "
                "anchor to the sealed plan, so it verifies without being about "
                "anything in particular"
            )
        if row.get("seq") != n:
            # Defence in depth, and honestly redundant: `seq` is inside the MAC,
            # so a row whose sequence is wrong already fails the MAC check below.
            # Kept because it names the failure precisely ("row dropped or
            # reordered") where a MAC mismatch says only "something changed", and
            # a reader chasing a broken run deserves the specific sentence.
            # A mutation sweep will report this line as survivable. That is true
            # and is not a reason to delete it -- but it IS a reason not to claim
            # it as load-bearing.
            return False, f"row {i}: seq {row.get('seq')!r}, expected {n} (row dropped or reordered)"
        claimed = row.get("mac")
        recomputed = _row_mac(prev_mac, {k: v for k, v in row.items() if k != "mac"}, key)
        if claimed != recomputed:
            return False, f"row {i}: mac mismatch (row edited, reordered or forged)"
        prev_mac = claimed
        n += 1
    if n == 0:
        return False, "fetch log is empty -- an empty chain verifies vacuously"
    return True, f"{n} rows chained"


def _read_rows(log_path: Path) -> tuple[Optional[list], str]:
    """Parse the log, or say why it cannot be parsed."""
    if not log_path.exists():
        return None, "fetch log does not exist"
    rows = []
    for i, line in enumerate(log_path.read_text().splitlines()):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            return None, (
                f"row {i}: unparseable -- a torn write or a truncated line. A "
                "malformed log is not a log that says nothing; it is one that "
                "cannot be trusted about anything."
            )
    return rows, ""


def _check_head(log_path: Path, rows: list, key: bytes) -> tuple[bool, str]:
    """The head sidecar: authentic, and agreeing with the log it describes."""
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
    last_mac = rows[-1].get("mac") if rows else ""
    if head.get("rows") != len(rows) or head.get("mac") != last_mac:
        return False, (
            f"head says {head.get('rows')} rows ending {str(head.get('mac'))[:12]}, "
            f"log has {len(rows)} ending {str(last_mac)[:12]} -- the log was "
            "truncated or replaced"
        )
    return True, ""


def verify_chain(
    log_path: Path, key: Optional[bytes] = None
) -> tuple[bool, str, list]:
    """Recompute every MAC, check the head, and RETURN the verified rows.

    Returning them is the point. A caller handed only a boolean must read the file
    again to use it, and the second read is a different read -- which is how a row
    appended between the two was once consumed as though it had been checked.
    """
    key = key or _chain_key()
    rows, err = _read_rows(log_path)
    if rows is None:
        return False, err, []
    ok, reason = _verify_rows(rows, key)
    if not ok:
        return False, reason, []
    head_ok, head_reason = _check_head(log_path, rows, key)
    if not head_ok:
        return False, head_reason, []
    return True, reason, rows


# --------------------------------------------------------------------------
# Politeness
# --------------------------------------------------------------------------


def _is_robots_url(url: str) -> bool:
    """Is this THE rules file for its origin?

    Path equality alone was not enough. `/robots.txt?anything` has that path, so
    it was exempted from the permission check AND installed as the origin's
    policy -- letting a page under the crawler's own control supply permissive
    rules. A query string means a different resource; the canonical rules file
    has none, and no fragment either.
    """
    parts = urllib.parse.urlsplit(url)
    return parts.path == "/robots.txt" and not parts.query and not parts.fragment


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
        parts, port = split_url(url)
        host = (parts.hostname or "").lower()
        default = {"http": 80, "https": 443}.get(parts.scheme, None)
        return host if port in (None, default) else f"{host}:{port}"

    def origin_of(self, url: str) -> str:
        """scheme://host[:port] -- the identity robots.txt rules belong to.

        NOT `host_of`. Rate limiting is per host, because that is what a server
        feels; permission is per ORIGIN, because http://x/robots.txt and
        https://x/robots.txt are two documents that may say different things.
        Keying rules by host let a permissive http policy authorise every https
        fetch on the same name, and the https rules were never read.
        """
        parts, _port = split_url(url)
        return f"{parts.scheme}://{self.host_of(url)}"

    def knows(self, origin: str) -> bool:
        """Have this origin's rules been loaded? Asked by the daemon, not a caller."""
        return origin in self._robots

    def load(self, origin: str, status: int, payload: bytes) -> None:
        """Install an ORIGIN's rules from bytes the DAEMON fetched. The only way in.

        This class used to read robots.txt itself, through
        `RobotFileParser.read()`, and that was an architectural hole rather than
        an inefficiency: those bytes never passed through the daemon, so they
        were never snapshotted and never chained. The run's claim "we honoured
        robots.txt" therefore rested on this object's memory of a request nobody
        can audit -- which is exactly the class of claim the whole custody split
        exists to abolish. `transport-custody` now demands that every fetched
        host have a snapshotted rules file, and it found this by failing.

        Status handling is unchanged, and each branch is a distinction worth
        keeping: 401/403 is permission explicitly withheld, other 4xx is the
        documented absence-means-no-restrictions case, and 5xx is the absence of
        an answer rather than the answer "yes".
        """
        rp = urllib.robotparser.RobotFileParser()
        if status in (401, 403):
            self._robots[origin] = None
        elif 400 <= status < 500:
            rp.parse([])
            self._robots[origin] = rp
        elif 200 <= status < 300:
            try:
                rp.parse(payload.decode("utf-8", errors="replace").splitlines())
            except Exception:
                # A parser defect is not evidence that crawling is allowed.
                self._robots[origin] = None
                return
            self._robots[origin] = rp
        else:
            self._robots[origin] = None

    def allows(self, url: str) -> bool:
        """May this url be fetched? Pure -- no network, no I/O.

        robots.txt itself is always fetchable. Asking robots.txt whether we may
        read robots.txt is circular, and it fails CLOSED -- so a crawl of a site
        whose rules we could not yet have read refuses every url including the
        rules. Found by running against a real host, not by a test.

        An unloaded host is refused rather than fetched-on-demand. The daemon
        loads rules before it asks, so reaching here without them is a defect in
        the caller, and the safe reading of "I have no idea what this site
        permits" is no.
        """
        if _is_robots_url(url):
            return True
        rp = self._robots.get(self.origin_of(url), "unloaded")
        if rp is None or rp == "unloaded":
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
    def _http(url: str) -> tuple[int, bytes, str]:
        """Transport contract: (status, bytes, final_url).

        `final_url` is returned rather than compared here on purpose. The redirect
        refusal used to live in this method, which every test replaces with a
        stub -- so the check sat on the one path no test could reach, coverage
        showed this function at 0%, and a mutation sweep found the refusal dead.
        A transport reports what happened; `fetch` decides what it means.
        """
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read(MAX_BYTES), resp.url
        except urllib.error.HTTPError as exc:
            # The error body is NOT evidence, but the status is a fact worth
            # recording -- a 404 body stored and read as a page is a defect this
            # daemon is meant to make impossible, so the status travels with it.
            return exc.code, exc.read(MAX_BYTES), exc.url if hasattr(exc, "url") else url

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
        self._ensure_robots(url)
        if not self.politeness.allows(url):
            raise RobotsRefusal(f"robots.txt disallows {url}")
        self.politeness.wait(url)

        result = self.transport(url)
        # Tolerate a 2-tuple transport (no redirect information) by treating the
        # requested url as final, so an older stub degrades to "no redirect" rather
        # than to "redirects unchecked".
        if len(result) == 3:
            status, payload, final_url = result
        else:
            status, payload = result
            final_url = url
        # urllib follows redirects silently. Attesting bytes to the url we ASKED
        # for rather than the one that ANSWERED would let a crawl cite
        # example.com for content served from anywhere else.
        if _canonical_url(final_url) != _canonical_url(url):
            raise RedirectRefusal(
                f"{url} redirected to {final_url} -- refetch the final url so the "
                "attested pair names where the bytes actually came from"
            )
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

        # A robots.txt this daemon fetched -- for whatever reason, including a
        # traversal asking for it directly -- installs that host's rules. Doing
        # it here rather than only in `_ensure_robots` means the file is never
        # fetched twice: whichever path reaches it first, the second path finds
        # the host already known.
        if _is_robots_url(url):
            self.politeness.load(self.politeness.origin_of(url), status, payload)
        return result

    def _ensure_robots(self, url: str) -> None:
        """Fetch this host's rules THROUGH the daemon, once, before asking them.

        The point is provenance, not politeness: fetching robots.txt here means
        it is content-addressed, chained and auditable like every other page, so
        "this crawl ran under these rules" is a checkable statement about bytes
        rather than a recollection. `transport-custody` asserts exactly that.

        Fails closed on anything that is not a clean answer -- a refusal, a
        redirect, a network error -- because none of those is evidence that
        crawling is allowed.
        """
        if _is_robots_url(url):
            return  # circular; `allows` exempts it and `fetch` loads it
        parts = urllib.parse.urlsplit(url)
        origin = self.politeness.origin_of(url)
        if self.politeness.knows(origin):
            return
        robots_url = urllib.parse.urlunsplit(
            (parts.scheme, self.politeness.host_of(url), "/robots.txt", "", "")
        )
        try:
            res = self.fetch(robots_url)
        except FetchError:
            self.politeness.load(origin, 0, b"")
            return
        # `fetch` has already called `load` for a robots.txt path, so there is
        # nothing to do here on success. The guard remains for the case where a
        # future change stops it doing so, which would otherwise silently leave
        # the host unloaded and every url on it refused.
        if not self.politeness.knows(origin):
            self.politeness.load(origin, res.status, b"")

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

    def admits(self, ev) -> bool:
        """The single admission decision. Everything the daemon knows, composed.

        `put_record` takes a `Callable[[Evidence], bool]` and NO method here had
        that shape, so every caller hand-wrote an adapter and the only adapter
        that existed wired to `verifies()` -- which checks quote-equality and
        nothing else. All three guarantees `evidence_for` uniquely owned were
        therefore bypassed at the door that decides what a human reads: the
        status/emptiness refusal, the whitespace-span refusal, and the rule that
        a snapshot path is derived from the digest rather than supplied.

        The previous fixes each lived at one site. This is the one place they all
        live, and it is the only thing the store is given.

        Returns False for "this evidence is not admissible" and RAISES
        ChainBroken for "the log cannot be trusted about anything" -- those are
        different facts and a caller must not collapse them.
        """
        receipt = self.receipt_for(ev.url, ev.sha256)      # raises if chain broken
        if receipt is None:
            return False
        ok, _why = self.usable_as_evidence(receipt)        # status, emptiness
        if not ok:
            return False
        if ev.snapshot != f"snapshots/{ev.sha256}":        # path derived, not given
            return False
        try:
            payload = self.open_attested(ev.url, ev.sha256)
        except ChainBroken:
            raise
        except FetchError:
            return False
        if ev.span_start < 0 or ev.span_end <= ev.span_start:
            return False
        if ev.span_end > len(payload):
            return False
        if not payload[ev.span_start:ev.span_end].strip():  # a span saying nothing
            return False
        # Delegate the comparison rather than repeating it. Two spellings of "do
        # these bytes say this" are two things that can drift, and this module's
        # whole failure history is checks that disagree with their consumers.
        return self.verifies(ev.url, ev.sha256, ev.span_start, ev.span_end, ev.quote)

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
        rows = self.verified_rows()
        return {
            (r["url"], r["sha256"]) for r in rows if r.get("kind") == "fetch"
        }

    def verified_rows(self) -> list[dict]:
        """Parse, verify, and return the rows -- one read, consumed as verified.

        The previous version called chain_ok() and then re-read the file. Codex
        drove a deterministic interleaving: an un-MACed row appended between the
        two reads was consumed as though verified, and a forged observed+entailed
        record reached expandable_ids(). Verifying one copy and using another is
        the same failure as verifying and using nothing.

        Also checks the plan, so nothing can be attested out of a run whose
        declared scope was rewritten underneath it.
        """
        ok, reason, rows = verify_run(self.dir, self.key)
        if not ok:
            raise ChainBroken(
                f"refusing to attest anything from an unverifiable run: {reason}. "
                "Every (url, digest) pair is unusable, because a log that can be "
                "edited can be edited to contain any pair."
            )
        return rows

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
