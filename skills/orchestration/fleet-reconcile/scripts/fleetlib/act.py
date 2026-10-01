"""fleet act: the verbs mail, spawn, label and resume (spec §5.3, §5.5, §5.7).

Each verb, in order:

1. refuses what the config and the ledger rule out: a scope in report mode
   (every verb but ask, which lives in fleet_reconcile.py), a corrupt ledger
   (mail and spawn), an unanswered ask on the target;
2. observes afresh what it depends on and re-checks eligibility in code, so
   neither what the coordinator read earlier in the tick nor text any session
   can write (board statuses, PR titles, mail) decides it;
3. writes its intent, fsynced before anything happens;
4. under dry run closes spawn, label and resume at once with done and
   `would: true` plus the argv or API call it would have made (mail's dry
   intent is closed by the send gate's pre hook); live, it acts and closes the
   intent with done or failed.

A refusal before any intent is a failed record with `of: null`. Every verb
returns one dict, printed as a JSON line. Like every local mechanism here this
is a floor on the named route, not a boundary (§5.1): the coordinator's
unsandboxed Bash can do any of it itself.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ctx

from . import classify, common, config, ledger, observe, parsers, profile
from .sources import SourceError, Sources

SKILL = Path(__file__).resolve().parents[2]
TEMPLATES = SKILL / "templates"

#: §5.2: PRs under these paths merge only with the owner's approval, so they get no driver.
OWNER_MERGE_PREFIXES = ("research/entities/",)
HOLD_LABEL = "hold"
#: `claude --bg` prints "backgrounded · <bg id> · <name>" (probe 6, 2.1.280).
SPAWNED_RE = re.compile(r"backgrounded\s*\S\s*([0-9a-f]{8})\b")
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,49}$")
MAIL_TEMPLATES = ("stalled", "hung", "overlap")
#: The only values a template takes from the caller, each a shape and never
#: free text: §5.5's fixed templates "never name a merge or a removal", and a
#: value is text the coordinator chose. `hours` comes from the config.
TEMPLATE_VARS = {"other": re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"),
                 "paths": re.compile(r"^[A-Za-z0-9._/-]{1,120}(?:, [A-Za-z0-9._/-]{1,120}){0,4}$")}
#: Surfaces the driver rules read: a rule whose surface wasn't read can't pass.
SPAWN_SURFACES = ("listing", "jobs", "transcripts")
LIVE_POLL_S = 10.0


class Refused(Exception):
    """A refusal, with one of ledger.REASONS and at most 200 characters."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        assert reason in ledger.REASONS, reason
        self.reason = reason
        self.detail = detail


class ModeRefused(Exception):
    """The scope is in report mode: nothing is attempted, nothing recorded."""


def driver_key(scope_id: str, slug: str, number: int) -> str:
    """<scope>-<repo>-pr<N> (§5.3), the driver's --name and fleet.key."""
    repo = re.sub(r"[^a-z0-9._-]+", "-", slug.split("/")[-1].lower()).strip("-")
    return "%s-%s-pr%d" % (scope_id, repo, number)


def render_template(name: str, values: Dict[str, Any]) -> str:
    """A fixed template with its placeholders filled; every value passes the
    text guard first (it comes from observations other sessions can write)."""
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    return text.format(**{k: common.safe_text(v, 200) for k, v in values.items()}).strip()


class Act:
    """One verb's run in one scope: its ledger, the tick and dry run."""

    def __init__(self, sec: Dict[str, Any], src: Sources, tick: Optional[int], dry: bool,
                 now: Optional[float] = None) -> None:
        self.sec, self.src, self.tick, self.dry = sec, src, tick or None, dry
        self.sd = config.state_dir(sec)
        self.records, self.corrupt = ledger.read(self.sd)
        self.now = time.time() if now is None else now

    # -- the ledger --------------------------------------------------------
    def _base(self) -> Dict[str, Any]:
        return {"scope": self.sec["scope"], "tick": self.tick, "dry_run": self.dry, "by": "act"}

    def _refuse(self, verb: str, key: str, exc: Refused, of: Optional[str] = None) -> Dict[str, Any]:
        rec = ledger.append(self.sd, dict(self._base(), kind="failed", of=of, verb=verb, key=key,
                                          reason=exc.reason, detail=exc.detail))
        return {"ok": False, "verb": verb, "key": key, "reason": exc.reason, "detail": rec["detail"],
                "record": rec["id"]}

    def _intent(self, verb: str, key: str, target: Dict[str, Any]) -> Dict[str, Any]:
        return ledger.append(self.sd, dict(self._base(), kind="intent", verb=verb, key=key, target=target))

    def _close(self, it: Dict[str, Any], kind: str, **fields: Any) -> Dict[str, Any]:
        return ledger.append(self.sd, dict(self._base(), kind=kind, of=it["id"], verb=it["verb"], key=it["key"],
                                           **fields))

    def _done(self, it: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        rec = self._close(it, "done", result=result)
        return {"ok": True, "verb": it["verb"], "key": it["key"], "intent": it["id"], "record": rec["id"],
                "dry_run": self.dry, "result": result}

    def _failed(self, it: Dict[str, Any], reason: str, detail: str) -> Dict[str, Any]:
        rec = self._close(it, "failed", reason=reason, detail=detail)
        return {"ok": False, "verb": it["verb"], "key": it["key"], "intent": it["id"], "record": rec["id"],
                "reason": reason, "detail": rec["detail"]}

    # -- what every verb checks first ----------------------------------------
    def preflight(self, verb: str, needles: List[str]) -> None:
        if self.sec["mode"] != "act":
            raise ModeRefused("fleet act %s: refused: scope %s is in report mode (observe, classify and ask); "
                              "every other verb waits for mode: act (§5.7)" % (verb, self.sec["scope"]))
        if self.corrupt and verb in ("mail", "spawn"):
            raise Refused("ineligible", "the ledger has %d corrupt line(s); mail and spawn wait until it is "
                                        "repaired" % self.corrupt)
        for k in sorted(ledger.open_by_key(self.records)):
            if any(n and n in k for n in needles):
                raise Refused("ineligible", "an unanswered ask on this target (%s); the owner answers it with "
                                            "fleet ack first" % common.safe_text(k, 80))

    # -- sessions ------------------------------------------------------------
    def listing(self, timeout: float = 30) -> List[Dict[str, Any]]:
        try:
            rows, _ = parsers.parse_listing(self.src.agents_listing(timeout))
        except (SourceError, parsers.ParseError) as exc:
            raise Refused("not_live", "the session listing couldn't be read: %s" % common.safe_text(exc, 120))
        return rows

    def ours(self) -> Dict[str, Dict[str, Any]]:
        """{session id: {key, paseo_agent_id}}: live fleet spawns in the ledger
        and adopted sessions in the config, the only sessions mail and resume
        reach (§5.3)."""
        out: Dict[str, Dict[str, Any]] = {}
        for key, ids in ledger.spawned(self.records).items():
            for sid in ids:  # a session id, or a job id when the listing lagged the spawn
                out[sid] = {"key": key, "paseo_agent_id": None}
        for e in self.sec.get("adopted") or []:
            out[e["session_id"]] = {"key": "adopt:%s" % e["session_id"], "paseo_agent_id": e.get("paseo_agent_id")}
        return out

    def _paseo(self) -> List[Dict[str, Any]]:
        out = []
        try:
            for where, text in self.src.paseo_records():
                try:
                    out.append(parsers.parse_paseo_record(text, where))
                except parsers.ParseError:
                    continue
        except (SourceError, OSError):
            return []
        return out

    def resolve(self, rows: List[Dict[str, Any]], sid: str, agent_id: Optional[str]) -> Dict[str, Any]:
        """The live row to send to (§5.7 "Addressing a session"): the session
        id's row with a pid, else its Paseo agent's current session's; and its
        name must be carried by no other live row."""
        live = [r for r in rows if r["pid"] is not None]
        row = next((r for r in live if r["session_id"] == sid), None)
        if row is None and agent_id:
            cur = next((p["session_id"] for p in self._paseo() if p["agent_id"] == agent_id), None)
            row = next((r for r in live if r["session_id"] == cur), None) if cur else None
        if row is None:
            raise Refused("not_live", "no live process for session %s%s" % (
                sid[:8], " or its Paseo agent's current session" if agent_id else ""))
        same = sorted(r["session_id"] for r in live if r["name"] == row["name"])
        if len(same) > 1:
            raise Refused("ambiguous_name", "%s is carried by %d live sessions: %s" % (
                common.safe_text(row["name"], 60), len(same), ", ".join(s[:8] for s in same)))
        return row

    # -- mail ----------------------------------------------------------------
    def whose(self, sid: str) -> Optional[Dict[str, Any]]:
        ours = self.ours()
        return ours.get(sid) or ours.get(sid[:8])

    def mail(self, sid: str, template: str, values: Dict[str, str]) -> Dict[str, Any]:
        who = self.whose(sid)
        key = who["key"] if who else "session:%s" % sid
        try:
            self.preflight("mail", [sid])
            if who is None:
                raise Refused("ineligible", "session %s is neither a fleet spawn in the ledger nor adopted in the "
                                            "fleet config" % sid[:8])
            agent = who["paseo_agent_id"] or next(
                (p["agent_id"] for p in self._paseo() if p["session_id"] == sid), None)
            recipient = agent or sid
            row = self.resolve(self.listing(), sid, agent)
            prior = ledger.mail_recent(self.records, recipient, self.now, self.sec["mail_interval_h"], self.dry)
            if prior:
                raise Refused("ineligible", "a mail to this recipient within %d h (intent %s)" % (
                    self.sec["mail_interval_h"], prior["id"]))
            if template not in MAIL_TEMPLATES:
                raise Refused("ineligible", "no mail template %r" % template)
            for k, v in values.items():
                if k not in TEMPLATE_VARS or not TEMPLATE_VARS[k].match(v or ""):
                    raise Refused("ineligible", "template value %s is not one of the fixed shapes (other: a session "
                                                "name; paths: up to 5 plain paths)" % common.safe_text(k, 20))
            try:
                text = render_template("mail/%s.txt" % template, dict(values, name=row["name"],
                                                                       hours=str(self.sec["mail_interval_h"])))
            except KeyError as exc:
                raise Refused("ineligible", "template %s needs --var %s" % (template, exc.args[0]))
        except Refused as exc:
            return self._refuse("mail", key, exc)
        it = self._intent("mail", key, {"session_id": row["session_id"], "paseo_agent_id": agent,
                                        "recipient": recipient, "name": row["name"], "pid": row["pid"],
                                        "template": template, "text": text})
        return {"ok": True, "verb": "mail", "key": key, "intent": it["id"], "dry_run": self.dry,
                "send": {"to": row["name"], "message": text},
                "next": "send it with SendMessage exactly as given; the send gate checks it against this intent"}

    # -- spawn ---------------------------------------------------------------
    def driver_check(self, snap: Dict[str, Any], results: List[Dict[str, Any]], slug: str, number: int,
                     key: str, rows: Optional[List[Dict[str, Any]]] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """§5.5's rules for a driver, from a fresh observation (and the raw
        listing rows, for names). Raises Refused. A rule whose surface wasn't
        read refuses: the caps need transcripts, the pause needs the boards
        and job files, and nothing stands without the listing."""
        surf = snap["surfaces"]
        for name in SPAWN_SURFACES:
            if not (surf.get(name) or {}).get("ok"):
                raise Refused("ineligible", "the %s surface wasn't read: %s" % (name, (surf.get(name) or {}).get("error")))
        bad = sorted(s for s, b in (surf.get("board") or {}).items() if not b.get("ok"))
        if bad:
            raise Refused("ineligible", "the board of %s wasn't read" % ", ".join(bad))
        repo = next((r for r in snap["repos"] if r.get("slug") == slug), None)
        if repo is None:
            raise Refused("ineligible", "%s is not a repo of scope %s" % (slug, self.sec["scope"]))
        if not repo["ok"]:
            raise Refused("ineligible", "%s was not observed: %s" % (slug, repo.get("error")))
        rules = repo["rules"]
        if not rules["driver_eligible"]:
            raise Refused("ineligible", "%s gets no driver: %s" % (slug, "; ".join(rules["flags"])))
        pr = next((p for p in repo["prs"] if p["number"] == number), None)
        if pr is None:
            raise Refused("ineligible", "#%d is not an open PR of %s" % (number, slug))
        if pr["draft"]:
            raise Refused("ineligible", "%s#%d is a draft" % (slug, number))
        if pr["dependabot"]:
            raise Refused("ineligible", "%s#%d is Dependabot's (batched separately)" % (slug, number))
        if any(lb.lower() == HOLD_LABEL for lb in pr["labels"]):
            raise Refused("ineligible", "%s#%d is held (label %s)" % (slug, number, HOLD_LABEL))
        # Raw names: a snapshot's are guarded for display (clipped or withheld).
        named = rows if rows is not None else snap["sessions"]
        taken = sorted(s["session_id"][:8] for s in named if s["name"] == key)
        if taken:
            raise Refused("name_taken", "%s is already carried by %s (a stopped driver is resumed, not spawned "
                                        "again)" % (key, ", ".join(taken)))
        holders = sorted(s["session_id"][:8] for s in snap["sessions"]
                         if s.get("pid") is not None and s.get("repo") == repo["repo"] and s.get("branch_id")
                         and s["branch_id"] == pr.get("head_id"))
        if holders:
            raise Refused("ineligible", "%s#%d's branch is checked out by live session(s) %s" % (
                slug, number, ", ".join(holders)))
        if snap["claims"]["published"]:
            unknown = sorted(sid[:8] for sid, cl in snap["claims"]["by_session"].items()
                             if any(c.get("unknown") and c.get("repo") == repo["repo"] for c in cl))
            if unknown:
                raise Refused("ineligible", "unknown claims on %s by %s" % (slug, ", ".join(unknown)))
        caps = self.sec["caps"]
        fleet_live = [s for s in snap["sessions"] if s.get("pid") is not None and s.get("fleet_key")
                      and not s.get("adopted")]
        if len(fleet_live) >= caps["fleet_sessions"]:
            raise Refused("ineligible", "%d fleet sessions are live (cap %d)" % (len(fleet_live), caps["fleet_sessions"]))
        since = self.now - caps["active_window_min"] * 60
        active = [s for s in snap["sessions"] if (classify.activity(s) or 0.0) >= since]
        if len(active) > caps["active_sessions"]:
            raise Refused("ineligible", "%d sessions had activity in the last %d min (cap %d)" % (
                len(active), caps["active_window_min"], caps["active_sessions"]))
        pause = classify.spawn_pause(snap, results)
        if pause and pause["active"]:
            raise Refused("ineligible", "a usage-limit death pauses spawns until %s" % (
                common.ts(pause["until"]) if pause["until"] else "its reset is known"))
        return repo, pr

    def spawn(self, slug: str, number: int, role: str = "driver") -> Dict[str, Any]:
        key = driver_key(self.sec["scope"], slug, number)
        try:
            self.preflight("spawn", [key, "repo:%s" % slug, "rules:%s:" % slug])
            if role != "driver":
                raise Refused("ineligible", "janitor runs are report-only until the phase-2 janitor drill passes "
                                            "(§5.5); research spawns aren't built")
            pending = [r["id"] for r in ledger.open_intents(self.records, "spawn")
                       if r.get("key") == key and bool(r.get("dry_run")) == self.dry]
            if pending:
                raise Refused("ineligible", "a spawn of %s is still unconfirmed (intent %s)" % (key, pending[0]))
            snap = observe.observe(self.sec, self.src, self.tick or 0, now=self.now)
            repo, pr = self.driver_check(snap, classify.classify_all(snap), slug, number, key, self.listing())
            try:
                files = json.loads(self.src.pr_files(slug, number))
            except (SourceError, ValueError) as exc:
                raise Refused("ineligible", "%s#%d's files weren't read, so the owner-merge rule can't be checked: "
                                            "%s" % (slug, number, common.safe_text(exc, 80)))
            owner = sorted(f for f in files if isinstance(f, str) and f.startswith(OWNER_MERGE_PREFIXES))
            if owner or not isinstance(files, list):
                raise Refused("ineligible", "%s#%d touches %s: an owner-merge PR gets no driver (§5.2)" % (
                    slug, number, owner[0] if owner else "an unreadable file list"))
        except Refused as exc:
            return self._refuse("spawn", key, exc)
        workdir = str(Path(repo["repo"]).parent)
        prof = profile.path_for(self.sd, key)
        brief = render_template("driver-brief.md", {"key": key, "repo": slug, "pr": number, "branch": pr["head"],
                                                    "base": pr.get("base") or repo.get("default_branch") or "main"})
        argv = profile.driver_argv(self.sec, key, prof, brief)
        it = self._intent("spawn", key, {"role": role, "repo": slug, "pr": number, "name": key, "profile": str(prof),
                                         "cwd": workdir, "argv_sha256": hashlib.sha256(
                                             json.dumps(argv).encode()).hexdigest()})
        if self.dry:
            return self._done(it, {"would": True, "argv": argv[:-1] + ["<brief: %d chars>" % len(brief)],
                                   "cwd": workdir, "claims": "checked" if snap["claims"]["published"]
                                   else "not published yet (core phase 2)"})
        try:
            token = profile.read_token(self.sec)
            if not token:
                return self._failed(it, "spawn_error", "no fleet token file: a live spawn is refused without it")
            profile.write(prof, profile.driver_profile(self.sec, key, token, profile.gh_config_dir(self.sd, key)))
            out = self.src.run_claude(argv[1:], cwd=workdir)
        except (SourceError, OSError) as exc:
            return self._failed(it, "spawn_error", common.safe_text(exc, 160))
        m = SPAWNED_RE.search(out)
        if not m:
            return self._failed(it, "spawn_error", "claude --bg printed no background id: %s" % common.safe_text(out, 80))
        # It spawned: whatever the listing says next, this is done. The job id
        # (the session id's first 8 hex) keys it until the listing shows it.
        sid = self._poll_session(m.group(1))
        return self._done(it, dict({"job_id": m.group(1)}, **({"session_id": sid} if sid else {})))

    def _poll_session(self, job_id: str) -> Optional[str]:
        deadline = time.monotonic() + LIVE_POLL_S
        while True:
            try:
                row = next((r for r in self.listing(10) if r["bg_id"] == job_id), None)
            except Refused:
                row = None
            if row is not None or time.monotonic() > deadline:
                return row["session_id"] if row else None
            time.sleep(1.0)

    # -- label ---------------------------------------------------------------
    def label(self, slug: str, number: int, name: str, op: str) -> Dict[str, Any]:
        key = "%s#%d" % (slug, number)
        try:
            self.preflight("label", ["repo:%s" % slug])
            if not LABEL_RE.match(name or "") or op not in ("add", "remove"):
                raise Refused("ineligible", "a label is 1-50 plain characters and the op add or remove")
            if name.lower() == HOLD_LABEL:
                raise Refused("ineligible", "the %s label is the owner's: fleet act neither adds nor removes it"
                              % HOLD_LABEL)
            if not self.dry and not profile.read_token(self.sec):
                raise Refused("ineligible", "a live label needs the fleet token file (never the keyring)")
            repo = self._repo(slug)
            if not any(p["number"] == number for p in repo["prs"]):
                raise Refused("ineligible", "#%d is not an open PR of %s" % (number, slug))
        except Refused as exc:
            return self._refuse("label", key, exc)
        if op == "add":
            call = ["POST", "repos/%s/issues/%d/labels" % (slug, number), {"labels[]": name}]
        else:
            call = ["DELETE", "repos/%s/issues/%d/labels/%s" % (slug, number, urllib.parse.quote(name, safe="")), {}]
        it = self._intent("label", key, {"repo": slug, "pr": number, "label": name, "op": op})
        if self.dry:
            return self._done(it, {"would": True, "call": "gh api -X %s %s%s" % (
                call[0], call[1], "".join(" -f %s=%s" % kv for kv in call[2].items()))})
        try:
            self.src.use_token(profile.read_token(self.sec) or "")
            self.src.gh_api(call[0], call[1], call[2])
        except SourceError as exc:
            return self._failed(it, "harness_refused", common.safe_text(exc, 160))
        return self._done(it, {"label": name, "op": op})

    def _repo(self, slug: str) -> Dict[str, Any]:
        """One scope repo's fresh observation, found by its origin slug."""
        scopes = ctx.load_scopes()
        for cd in sorted(r for r, s in scopes.by_repo.items() if s == self.sec["scope"]):
            try:
                if parsers.parse_remote_slug(self.src.origin_url(cd)) != slug:
                    continue
            except SourceError:
                continue
            repo = observe.observe_repo(cd, self.sec, self.src)
            if not repo["ok"]:
                raise Refused("ineligible", "%s was not observed: %s" % (slug, repo.get("error")))
            return repo
        raise Refused("ineligible", "%s is not a repo of scope %s" % (slug, self.sec["scope"]))

    # -- resume --------------------------------------------------------------
    def resume(self, sid: str) -> Dict[str, Any]:
        who = self.whose(sid)
        key = who["key"] if who else "session:%s" % sid
        try:
            self.preflight("resume", [sid])
            if who is None:
                raise Refused("ineligible", "session %s is neither a fleet spawn in the ledger nor adopted" % sid[:8])
            self._resumable(sid)
            pending = [r["id"] for r in ledger.open_intents(self.records, "resume")
                       if (r.get("target") or {}).get("session_id") == sid and bool(r.get("dry_run")) == self.dry]
            if pending:
                raise Refused("ineligible", "a resume of it is still unconfirmed (intent %s)" % pending[0])
        except Refused as exc:
            return self._refuse("resume", key, exc)
        argv = ["--bg", "--resume", sid]  # no other flag: a flag starts a copy under a new id (§5.3)
        it = self._intent("resume", key, {"session_id": sid})
        if self.dry:
            return self._done(it, {"would": True, "argv": ["claude"] + argv})
        try:
            self._resumable(sid)  # re-checked just before
            self.src.run_claude(argv)
            row = next((r for r in self.listing() if r["session_id"] == sid), None)
        except Refused as exc:
            return self._failed(it, exc.reason, exc.detail)
        except SourceError as exc:
            return self._failed(it, "harness_refused", common.safe_text(exc, 160))
        if not row or row["pid"] is None:
            return self._failed(it, "harness_refused", "claude agents shows no process for it after the resume")
        return self._done(it, {"pid": row["pid"]})

    def _resumable(self, sid: str) -> None:
        row = next((r for r in self.listing() if r["session_id"] == sid), None)
        if row is None:
            raise Refused("not_live", "claude agents doesn't list session %s" % sid[:8])
        if row["kind"] != "background":
            raise Refused("ineligible", "%s is interactive: it gets a mail, not a resume" % sid[:8])
        if row["pid"] is not None:
            raise Refused("ineligible", "%s has a live process: it gets a mail, not a resume" % sid[:8])
