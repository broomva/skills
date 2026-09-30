#!/usr/bin/env python3
"""``gh`` inside a context-ablation case: fixture pull requests, and a log of every call.

Two jobs. It gives a task that needs GitHub (merge a PR, check CI) a PR to act on,
defined in the case's ``stubs.json``. And it records every argv, which is what the
graders assert on (``gh pr merge 42 --squash --match-head-commit <sha>``): the
command line the agent composed is the outcome, not what the agent said it did.

It also keeps the trials off real GitHub. The jail links the login keychain in so
the CLI can authenticate, and the real ``gh`` reads its token from that keychain;
this stub sits first on PATH so a bypassPermissions trial cannot merge a real PR.
Anything it does not model exits 1 with a plain error, never a guess.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common  # noqa: E402

NAME = "gh"


def _out(text: str = "", code: int = 0, err: str = "") -> int:
    if text:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    if err:
        sys.stderr.write(err if err.endswith("\n") else err + "\n")
    return code


def _take(args: list[str], *names: str, flag: bool = False) -> str | bool | None:
    """Remove ``--name value`` (or ``--name=value``, or a bare flag) from *args*."""
    for i, a in enumerate(list(args)):
        for n in names:
            if a == n:
                if flag:
                    del args[i]
                    return True
                if i + 1 < len(args):
                    val = args[i + 1]
                    del args[i : i + 2]
                    return val
            if not flag and a.startswith(n + "="):
                del args[i]
                return a.split("=", 1)[1]
    return False if flag else None


def _prs(cfg: dict) -> dict[str, dict]:
    prs = cfg.get("prs") or {}
    state = _common.load_state(NAME)
    merged = state.get("merged") or {}
    out = {}
    for num, pr in prs.items():
        pr = dict(pr)
        if str(num) in merged:
            pr["state"] = "MERGED"
            pr["mergedAt"] = merged[str(num)]
        out[str(num)] = pr
    return out


def _current_branch() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _select(prs: dict[str, dict], args: list[str]) -> dict | None:
    sel = next((a for a in args if not a.startswith("-")), None)
    if sel is not None:
        sel = sel.lstrip("#").rsplit("/", 1)[-1]
        if sel in prs:
            return prs[sel]
        return next((p for p in prs.values() if p.get("headRefName") == sel), None)
    branch = _current_branch()
    return next((p for p in prs.values() if p.get("headRefName") == branch), None)


def _emit_json(value, fields: str | None, jq: str | None) -> int:
    if fields and isinstance(value, dict):
        value = {f: value.get(f) for f in fields.split(",") if f}
    elif fields and isinstance(value, list):
        keys = [f for f in fields.split(",") if f]
        value = [{f: v.get(f) for f in keys} for v in value]
    text = json.dumps(value)
    if jq:
        jq_bin = shutil.which("jq")
        if not jq_bin:
            return _out(code=1, err="gh: --jq needs jq on PATH in this environment")
        proc = subprocess.run([jq_bin, "-r", jq], input=text, capture_output=True, text=True)
        return _out(proc.stdout.rstrip("\n"), proc.returncode, proc.stderr)
    return _out(text)


def _checks(pr: dict) -> list[dict]:
    return list(pr.get("statusCheckRollup") or [])


def cmd_pr(cfg: dict, args: list[str]) -> int:
    if not args:
        return _out(code=1, err="gh pr: a subcommand is required")
    sub, args = args[0], args[1:]
    prs = _prs(cfg)
    fields = _take(args, "--json")
    jq = _take(args, "--jq", "-q")
    repo = cfg.get("repo", "example/repo")

    if sub == "list":
        head = _take(args, "--head", "-H")
        rows = [p for p in prs.values() if not head or p.get("headRefName") == head]
        state = _take(args, "--state", "-s") or "open"
        if state != "all":
            rows = [p for p in rows if str(p.get("state", "OPEN")).lower() == state]
        if fields:
            return _emit_json(rows, fields, jq)
        return _out("\n".join(f"{p['number']}\t{p.get('title','')}\t{p.get('headRefName','')}\t{p.get('state','OPEN')}" for p in rows))

    if sub == "create":
        n = int(cfg.get("next_pr", 100))
        return _out(f"https://github.com/{repo}/pull/{n}")

    # Value-taking flags come off before the selector is read, or `--subject "x" 42`
    # would select a PR named "x".
    pin = _take(args, "--match-head-commit")
    for value_flag in (("--subject", "-t"), ("--body", "-b"), ("--body-file", "-F"),
                       ("--author-email", "-A"), ("--template", "-T"), ("--interval", "-i")):
        _take(args, *value_flag)
    pr = _select(prs, args)
    if pr is None:
        return _out(code=1, err=f"no pull requests found for branch \"{_current_branch()}\"")

    if sub == "view":
        if fields:
            return _emit_json(pr, fields, jq)
        checks = _checks(pr)
        ok = sum(1 for c in checks if c.get("conclusion") == "SUCCESS")
        return _out(
            f"{pr.get('title','')} {repo}#{pr['number']}\n"
            f"{pr.get('state','OPEN').title()} • {pr.get('author','fixture')} wants to merge into "
            f"{pr.get('baseRefName','main')} from {pr.get('headRefName','')}\n"
            f"Checks: {ok}/{len(checks)} passing\n\n{pr.get('body','')}\n\n"
            f"View this pull request on GitHub: {pr.get('url','')}"
        )

    if sub == "checks":
        _take(args, "--watch", flag=True)
        _take(args, "--required", flag=True)
        _take(args, "--fail-fast", flag=True)
        rows = [
            {
                "name": c.get("name"),
                "state": c.get("conclusion") or c.get("status"),
                "bucket": ("pass" if c.get("conclusion") == "SUCCESS" else
                           "pending" if not c.get("conclusion") else "fail"),
                "link": c.get("detailsUrl", ""),
            }
            for c in _checks(pr)
        ]
        if fields:
            return _emit_json(rows, fields, jq)
        text = "\n".join(f"{r['name']}\t{r['bucket']}\t1m2s\t{r['link']}" for r in rows)
        if any(r["bucket"] == "fail" for r in rows):
            return _out(text, 1)
        return _out(text, 8 if any(r["bucket"] == "pending" for r in rows) else 0)

    if sub == "diff":
        return _out(pr.get("diff", ""))

    if sub == "merge":
        if pr.get("state") == "MERGED":
            return _out(code=1, err=f"X Pull request {repo}#{pr['number']} was already merged")
        if pin and pin != pr.get("headRefOid"):
            return _out(code=1, err="GraphQL: Head branch was modified. Review and try the merge again. (mergePullRequest)")
        state = _common.load_state(NAME)
        state.setdefault("merged", {})[str(pr["number"])] = "2026-09-29T12:00:00Z"
        _common.save_state(NAME, state)
        how = "Squashed and merged" if "--squash" in args or "-s" in args else (
            "Rebased and merged" if "--rebase" in args or "-r" in args else "Merged")
        return _out(f"✓ {how} pull request {repo}#{pr['number']} ({pr.get('title','')})")

    if sub in ("status", "ready", "comment", "edit", "review"):
        return _out(f"{repo}#{pr['number']}: {sub} ok")

    return _out(code=1, err=f"gh pr {sub}: not available in this environment")


def cmd_api(cfg: dict, args: list[str]) -> int:
    jq = _take(args, "--jq", "-q")
    path = next((a for a in args if not a.startswith("-")), "")
    prs = _prs(cfg)
    for num, pr in prs.items():
        if path.rstrip("/").endswith(f"/pulls/{num}"):
            rest = {
                "number": pr["number"], "title": pr.get("title"), "state": str(pr.get("state", "OPEN")).lower(),
                "merged": pr.get("state") == "MERGED", "head": {"ref": pr.get("headRefName"), "sha": pr.get("headRefOid")},
                "base": {"ref": pr.get("baseRefName", "main")}, "html_url": pr.get("url"),
            }
            return _emit_json(rest, None, jq)
        if pr.get("headRefOid") and f"/commits/{pr['headRefOid']}/check-runs" in path:
            runs = {"total_count": len(_checks(pr)), "check_runs": [
                {"name": c.get("name"), "status": "completed", "conclusion": str(c.get("conclusion", "")).lower()}
                for c in _checks(pr)]}
            return _emit_json(runs, None, jq)
    return _out(code=1, err="gh: Not Found (HTTP 404)")


def main(argv: list[str]) -> int:
    args = list(argv)
    cfg = _common.config(NAME)
    _take(args, "--repo", "-R")
    if not args:
        code = _out("Work seamlessly with GitHub from the command line.")
    elif args[0] == "auth":
        code = _out(err="github.com\n  ✓ Logged in to github.com account eval-fixture (keyring)")
    elif args[0] == "pr":
        code = cmd_pr(cfg, args[1:])
    elif args[0] == "api":
        code = cmd_api(cfg, args[1:])
    elif args[0] == "repo" and args[1:2] == ["view"]:
        code = _emit_json({"nameWithOwner": cfg.get("repo", "example/repo")}, None, _take(args, "--jq", "-q"))
    elif args[0] == "run" and args[1:2] == ["list"]:
        code = _out("")
    else:
        code = _out(code=1, err=f"gh {' '.join(args[:2])}: not available in this environment")
    _common.log(NAME, {"argv": list(argv), "rc": code})
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
