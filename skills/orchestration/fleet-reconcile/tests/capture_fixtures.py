#!/usr/bin/env python3
"""Capture the surfaces fleet-reconcile parses, anonymized, as test fixtures.

    python3 tests/capture_fixtures.py [--out tests/fixtures/cc-<version>]

Run by hand on the owner's machine when Claude Code changes version; the
parsers are pinned to the version captured (parsers.PINNED_CC_VERSION). This
repo is public, so everything is anonymized before it is written:

- kept: every key, every type, the enum values (kind, state, status,
  waitingFor, lastStatus, archive state, label keys), timestamps, each
  transcript's mtime and last timestamped entry, and Claude Code's usage-limit
  text verbatim;
- replaced: session ids (fixed fake UUIDs), names, titles, job details and
  questions, prompts, run outputs, label values, and paths. A path is replaced
  by a template ({HOME}/broomva, {HOME}/client/sri, {HOME}/wt/<scope>-<n>,
  {HOME}/gone/<n>, {HOME}/other/<n>) chosen by the scope the path was in at
  capture time; tests/conftest.py builds matching repos in a scratch HOME;
- never copied: a Paseo record's persistence.metadata (the MCP bearer lives
  there). The fixture record carries a FAKE bearer in the same place instead,
  so a test can prove the parsers never read it into a snapshot or report.

The script refuses to write if the output still holds a credential-shaped
string (other than the planted fake) or a crm/ path.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parent.parent / "ctx-core" / "scripts"))

import ctx  # noqa: E402
import ctx_compare  # noqa: E402

from fleetlib import parsers  # noqa: E402

FAKE_BEARER = "Bearer FIXTURE-FAKE-BEARER-NOT-A-SECRET"
HOME = str(Path.home())
LIMIT_CANON = "You've hit your session limit · resets 10am (America/Bogota)"


class Anon:
    def __init__(self) -> None:
        self.sids, self.paths, self.names = {}, {}, {}
        self.counters = {}
        self.scopes = ctx.load_scopes().by_repo

    def n(self, kind: str) -> int:
        self.counters[kind] = self.counters.get(kind, 0) + 1
        return self.counters[kind]

    def sid(self, real: str) -> str:
        if real not in self.sids:
            n = len(self.sids) + 1
            self.sids[real] = "%08d-f1ee-4000-8000-%012d" % (n, n)
        return self.sids[real]

    def short(self, real8: str) -> str:
        for r, f in self.sids.items():
            if r.startswith(real8):
                return f[:8]
        return self.sid(real8 + "-unknown")[:8]

    def path(self, real: str) -> str:
        if not real:
            return real
        if real in self.paths:
            return self.paths[real]
        w = ctx.locate(real, timeout=2.0) if os.path.isdir(real) else None
        if w is None:
            out = "{HOME}/gone/%d" % self.n("gone")
        else:
            scope = self.scopes.get(w.common_dir)
            main = w.toplevel == os.path.dirname(w.common_dir)
            if scope == "broomva" and main and w.toplevel == os.path.realpath(os.path.join(HOME, "broomva")):
                out = "{HOME}/broomva" + ("" if real == w.toplevel else "/sub")
            elif scope == "broomva" and main:
                out = "{HOME}/broomva/skills"
            elif scope == "sri" and main:
                out = "{HOME}/client/sri"
            elif scope:
                out = "{HOME}/wt/%s-%d" % (scope, self.n("wt-" + scope))
            else:
                out = "{HOME}/other/%d" % self.n("other")
        self.paths[real] = out
        return out

    def name(self, real: str, kind: str) -> str:
        if real not in self.names:
            if real.startswith("/"):
                self.names[real] = "/cmd-%d" % self.n("cmd")
            elif re.fullmatch(r"[a-z]+-[a-z]+-[0-9a-f]{2}", real):
                self.names[real] = "auto-name-%d-%02x" % (self.n("auto"), self.n("hex") % 256)
            else:
                self.names[real] = "%s-session-%d" % (kind, self.n("name"))
        return self.names[real]


def free(text: str, label: str, a: Anon) -> str:
    if not text:
        return text
    if parsers.LIMIT_RE.search(text):
        return text  # Claude Code's own limit text: its reset form is what the parser reads
    return "%s %d%s" % (label, a.n(label), "?" if text.rstrip().endswith("?") else "")


def capture(out: Path) -> None:
    a = Anon()
    now = time.time()
    version = subprocess.run(["claude", "--version"], capture_output=True, text=True, check=True).stdout.strip()
    listing = json.loads(subprocess.run(["claude", "agents", "--json", "--all"], capture_output=True, text=True,
                                        check=True).stdout)
    files = {}
    rows = []
    for r in listing:
        r = dict(r)
        real = r["sessionId"]
        r["sessionId"] = a.sid(real)
        if "id" in r:
            r["id"] = r["sessionId"][:8]
        r["cwd"] = a.path(r["cwd"])
        r["name"] = a.name(r["name"], r.get("kind", "x"))
        if "pid" in r:
            r["pid"] = 10000 + len(rows)
        rows.append(r)
    files["claude/version.txt"] = version + "\n"
    files["claude/agents.json"] = json.dumps(rows, indent=1) + "\n"

    jobs_root = Path.home() / ".claude" / "jobs"
    for d in sorted(jobs_root.iterdir()):
        p = d / "state.json"
        if not p.is_file():
            continue
        j = json.loads(p.read_text())
        sid = a.sid(j["sessionId"])
        keep = {
            "state": j.get("state"), "detail": free(j.get("detail", ""), "detail", a),
            "tempo": j.get("tempo"), "sessionId": sid, "resumeSessionId": sid,
            "cwd": a.path(j.get("cwd", "")), "createdAt": j.get("createdAt"), "updatedAt": j.get("updatedAt"),
            "cliVersion": j.get("cliVersion"), "output": None, "providerEnv": {"FIXTURE_ENV": "not-read"},
            "respawnFlags": ["--name", "bg-flag-name", "--settings", '{"crossSessionInbound":"accept"}'],
        }
        for k in ("needs", "suggestedReply"):
            if j.get(k):
                keep[k] = free(j[k], k, a)
        for k in ("worktreePath",):
            if j.get(k):
                keep[k] = a.path(j[k])
        if j.get("worktreeBranch"):
            keep["worktreeBranch"] = "worktree-branch-%d" % a.n("wtb")
        if j.get("name"):
            keep["name"] = a.name(j["name"], "background")
        files["claude/jobs/%s/state.json" % sid[:8]] = json.dumps(keep, indent=1) + "\n"

    # Transcript times of listed sessions, and every subagent time
    idx = {}
    proj = Path.home() / ".claude" / "projects"
    wanted = {r: f for r, f in a.sids.items()}
    for pdir in proj.iterdir():
        for real, fake in wanted.items():
            t = pdir / (real + ".jsonl")
            if t.is_file() and t.stat().st_mtime >= idx.get(fake, {}).get("mtime", 0):
                idx.setdefault(fake, {})["mtime"] = t.stat().st_mtime
                # The last timestamped entry: Claude Code appends untimestamped
                # records (last-prompt, cost-state) about an hour after a turn.
                idx[fake]["last_entry"] = ctx_compare.last_entry_ts(str(t))
            sub = pdir / real / "subagents"
            if sub.is_dir():
                m = max((f.stat().st_mtime for f in sub.glob("*.jsonl")), default=None)
                if m:
                    idx.setdefault(fake, {})["sub"] = m
    files["claude/transcripts.json"] = json.dumps(idx, indent=1, sort_keys=True) + "\n"

    # Paseo: every not-archived record plus three archived ones
    recs = []
    for p in sorted((Path.home() / ".paseo" / "agents").glob("*/*.json")):
        j = json.loads(p.read_text())
        recs.append(j)
    chosen = [j for j in recs if not j.get("archivedAt")] + [j for j in recs if j.get("archivedAt")][:3]
    for j in chosen:
        rt = j.get("runtimeInfo") or {}
        ps = j.get("persistence") or {}
        fake_id = "agent-%04d" % a.n("agent")
        rec = {
            "id": fake_id, "provider": j.get("provider"), "cwd": a.path(j.get("cwd", "")),
            "workspaceId": "ws-%d" % a.n("ws"), "createdAt": j.get("createdAt"), "updatedAt": j.get("updatedAt"),
            "lastActivityAt": j.get("lastActivityAt"), "lastUserMessageAt": j.get("lastUserMessageAt"),
            "title": "title %d" % a.n("title"),
            "labels": {k: "v-%d" % a.n("label") for k in (j.get("labels") or {})
                       if not k.startswith("paseo.open-agent-tab.")},
            "lastStatus": j.get("lastStatus"), "lastModeId": j.get("lastModeId"),
            "config": {"modeId": (j.get("config") or {}).get("modeId")},
            "runtimeInfo": {"provider": rt.get("provider"),
                            "sessionId": a.sid(rt["sessionId"]) if rt.get("sessionId") else None},
            "features": [],
            "persistence": {"provider": ps.get("provider"),
                            "sessionId": a.sid(ps["sessionId"]) if ps.get("sessionId") else None,
                            "metadata": {"mcpServers": {"paseo": {
                                "type": "http", "url": "http://127.0.0.1:6767/mcp?fixture=1",
                                "headers": {"Authorization": FAKE_BEARER}}}}},
            "requiresAttention": j.get("requiresAttention"), "attentionReason": j.get("attentionReason"),
            "attentionTimestamp": None, "internal": j.get("internal"),
        }
        if j.get("archivedAt"):
            rec["archivedAt"] = j["archivedAt"]
        files["paseo/agents/project-1/%s.json" % fake_id] = json.dumps(rec, indent=1) + "\n"

    for p in sorted((Path.home() / ".paseo" / "schedules").glob("*.json")):
        j = json.loads(p.read_text())
        tc = (j.get("target") or {}).get("config") or {}
        rec = {
            "id": "sch%05d" % a.n("sch"), "name": "schedule %d" % a.n("schname"), "prompt": "prompt (not read)",
            "cadence": j.get("cadence"), "target": {"type": (j.get("target") or {}).get("type"),
                                                    "config": {"provider": tc.get("provider"),
                                                               "cwd": a.path(tc.get("cwd", ""))}},
            "status": j.get("status"), "createdAt": j.get("createdAt"), "updatedAt": j.get("updatedAt"),
            "nextRunAt": j.get("nextRunAt"), "lastRunAt": j.get("lastRunAt"), "pausedAt": j.get("pausedAt"),
            "expiresAt": j.get("expiresAt"), "maxRuns": j.get("maxRuns"),
            "runs": [{"id": "run-%d" % a.n("run"), "scheduledFor": r.get("scheduledFor"),
                      "startedAt": r.get("startedAt"), "endedAt": r.get("endedAt"), "status": r.get("status"),
                      "agentId": "agent-x", "workspaceId": "ws-x", "output": "output (not read)",
                      "error": None} for r in j.get("runs") or []],
        }
        files["paseo/schedules/%s.json" % rec["id"]] = json.dumps(rec, indent=1) + "\n"

    # GitHub: the rules and PR list shapes of the public broomva repos
    for slug in ("broomva/workspace", "broomva/skills", "broomva/bstack", "broomva/broomva.tech"):
        key = slug.replace("/", "__")
        db = subprocess.run(["gh", "api", "repos/" + slug, "--jq", ".default_branch"], capture_output=True,
                            text=True, check=True).stdout.strip()
        rules = json.loads(subprocess.run(["gh", "api", "repos/%s/rules/branches/%s" % (slug, db)],
                                          capture_output=True, text=True, check=True).stdout)
        prs = json.loads(subprocess.run(["gh", "pr", "list", "-R", slug, "--state", "open", "--limit", "200",
                                         "--json", parsers.PR_FIELDS], capture_output=True, text=True,
                                        check=True).stdout)
        for i, pr in enumerate(prs, 1):
            pr["title"] = "PR title %d" % i
            pr["headRefName"] = "branch-%d" % i
            pr["url"] = "https://github.com/%s/pull/%d" % (slug, pr["number"])
            au = pr.get("author") or {}
            pr["author"] = {"login": "app/dependabot" if "dependabot" in (au.get("login") or "") else "owner",
                            "is_bot": bool(au.get("is_bot"))}
            pr["labels"] = [{"name": lb.get("name")} for lb in pr.get("labels") or [] if lb.get("name") == "hold"]
        files["gh/%s/default_branch.txt" % key] = db + "\n"
        files["gh/%s/rules.json" % key] = json.dumps(rules, indent=1) + "\n"
        files["gh/%s/prs.json" % key] = json.dumps(prs, indent=1) + "\n"

    # launchd: two plists (as plutil JSON) and their launchctl print
    for label in ("com.broomva.kg-compile", "com.broomva.moltbook-loop"):
        plist = Path.home() / "Library" / "LaunchAgents" / (label + ".plist")
        if not plist.is_file():
            continue
        pj = json.loads(subprocess.run(["plutil", "-convert", "json", "-o", "-", str(plist)], capture_output=True,
                                       text=True, check=True).stdout)
        pj = {k: pj[k] for k in ("Label", "StartInterval", "StartCalendarInterval", "RunAtLoad",
                                 "StandardOutPath", "StandardErrorPath") if k in pj}
        pj["ProgramArguments"] = ["/bin/bash", "{HOME}/job.sh"]
        files["launchd/%s.json" % label] = json.dumps(pj, indent=1) + "\n"
        pr = subprocess.run(["launchctl", "print", "gui/%d/%s" % (os.getuid(), label)], capture_output=True,
                            text=True)
        keep = [ln for ln in pr.stdout.splitlines() if re.match(r"^\t[a-z ]+ = ", ln) and not ln.startswith("\t\t")
                and ln.split(" = ")[0].strip() in ("state", "runs", "last exit code", "pid", "run interval",
                                                     "spawn type")]
        files["launchd/%s.print.txt" % label] = "\n".join(["gui/501/%s = {" % label] + keep + ["}"]) + "\n"

    # The core's event logs, with the same session and path maps
    repo_tpl = {}
    for common_dir, scope in a.scopes.items():
        top = os.path.dirname(common_dir)
        if scope == "sri":
            repo_tpl[common_dir] = "{HOME}/client/sri/.git"
        elif top == os.path.realpath(os.path.join(HOME, "broomva", "skills")):
            repo_tpl[common_dir] = "{HOME}/broomva/skills/.git"
        else:
            repo_tpl[common_dir] = "{HOME}/broomva/.git"
    branches = {}
    for scope in ("broomva", "sri"):
        log = ctx.state_root() / scope / "events.jsonl"
        if not log.is_file():
            continue
        out_lines = []
        for raw in log.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            if ev.get("repo") not in repo_tpl:
                continue
            ev["session_id"] = a.sid(ev["session_id"])
            ev["cwd"] = a.path(ev["cwd"])
            ev["repo"] = repo_tpl[ev["repo"]]
            if ev.get("branch"):
                ev["branch"] = branches.setdefault(ev["branch"], "branch-%d" % (len(branches) + 1))
            if "paseo_agent_id" in ev:
                ev["paseo_agent_id"] = "agent-x"
            ev.get("payload", {}).pop("arc_line", None)
            out_lines.append(json.dumps(ev, sort_keys=True, separators=(",", ":")))
        files["ctx/%s/events.jsonl" % scope] = "\n".join(out_lines) + "\n"

    meta = {"captured_at": now, "claude_version": parsers.cc_version(version),
            "note": "anonymized by tests/capture_fixtures.py; see its docstring"}
    files["meta.json"] = json.dumps(meta, indent=1) + "\n"

    blob = "\n".join(files.values())
    leaks = [pat for pat in ("ghp_", "gho_", "github_pat_", "crm/", HOME + "/")
             if pat in blob]
    if blob.count("Bearer ") != blob.count(FAKE_BEARER):
        leaks.append("a Bearer value other than the planted fake")
    if leaks:
        raise SystemExit("capture_fixtures: refusing to write; found %s" % ", ".join(leaks))
    for rel, text in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    print("wrote %d files to %s" % (len(files), out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    v = parsers.cc_version(subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout)
    out = Path(args.out) if args.out else HERE / "fixtures" / ("cc-%s" % v)
    capture(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
