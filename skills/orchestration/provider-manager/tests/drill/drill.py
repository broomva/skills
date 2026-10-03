#!/usr/bin/env python3
"""Real-binary drill: a running Claude Code session versus a provider-manager switch.

The real `claude` binary runs a multi-request session in a scratch HOME, against a mitmproxy stub
of Anthropic's endpoints (stub_addon.py) and a scratch keychain (fake `security` first on PATH).
Between two of its requests, provider-manager (this branch, or an older copy) switches accounts.
The drill reports whether the session finished, which account served each request, and whether it
died with "OAuth session expired and could not be refreshed".

Isolation, all checked in preflight before the binary starts:
- `claude` and provider-manager run under sandbox-exec: no securityd (no keychain at all), no read
  of ~/Library/Keychains, ~/.claude or ~/.claude.json, and network only to localhost;
- PATH puts the fake `security` first; HOME is scratch; every token is minted by the stub.

    python drill.py --impl new --scenario stale-target
    python drill.py --impl /path/to/old/scripts --scenario rotation-back
    python drill.py --all --old-impl /path/to/old/scripts      # every scenario, both impls

Needs: the `claude` binary, mitmdump, sandbox-exec (macOS).
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAKEWORLD = HERE.parent / "fakeworld"
NEW_IMPL = HERE.parent.parent / "scripts"
sys.path.insert(0, str(FAKEWORLD))
os.environ.setdefault("FAKE_ANTHROPIC_STATE", "/nonexistent")  # replaced per run before any use

import fake_anthropic  # noqa: E402
import keychain_db  # noqa: E402

USER = "tester"
ORCA = "Orca Claude Code Managed Credentials"
STORE = "Claude Code-credentials"
A, B = "a@drill.test", "b@drill.test"
REAL_HOME = os.path.expanduser("~")

SCENARIOS = {
    # B's stored grant was consumed long ago (its Orca copy is stale). Switch A -> B mid-session.
    "stale-target": {"gates": [2], "calls": 4},
    # B's stored grant is live but its access token has expired. Switch A -> B mid-session.
    "healthy-target": {"gates": [2], "calls": 4},
    # The session rotates A's refresh token; switch A -> B, then back to A.
    "rotation-back": {"gates": [2, 3], "calls": 5},
    # No session: provider-manager's probe runs the REAL claude binary on the store, for three states
    # of the active account (healthy, exhausted, dead grant), to check its classification of the real
    # binary's output.
    "probe": {"gates": [], "calls": 1},
}


def sandbox_profile(path: Path) -> Path:
    path.write_text("""(version 1)
(allow default)
(deny mach-lookup (global-name "com.apple.SecurityServer") (global-name "com.apple.securityd")
                  (global-name "com.apple.security.agent"))
(deny file-read* file-write* (subpath "{home}/Library/Keychains"))
(deny file-read* file-write* (subpath "{home}/.claude") (literal "{home}/.claude.json") (literal "{home}/.claude.lock"))
(deny network-outbound)
(allow network-outbound (remote ip "localhost:*"))
(allow network-outbound (remote unix-socket))
""".format(home=REAL_HOME))
    return path


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Run:
    def __init__(self, impl: Path, scenario: str, keep: bool):
        self.impl = impl
        self.scenario = scenario
        self.keep = keep
        self.root = Path(tempfile.mkdtemp(prefix="pm-drill-", dir="/tmp"))
        self.home = self.root / "home"
        self.cfg = self.home / ".claude"
        self.bin = self.root / "bin"
        self.db = str(self.root / "keychain.json")
        self.api = str(self.root / "anthropic.json")
        self.sb = sandbox_profile(self.root / "drill.sb")
        self.port = free_port()
        self.accounts = {}
        self.mitm = None
        os.environ["FAKE_ANTHROPIC_STATE"] = self.api

    # -- world --------------------------------------------------------------------------------
    def build(self):
        for d in (self.cfg, self.bin, self.home / "Library/Application Support/orca/profiles/local-default",
                  self.home / ".cache", self.root / "mitm"):
            d.mkdir(parents=True, exist_ok=True)
        for name, target in (("security", "fake_security.py"), ("claude-fake", "fake_claude.py")):
            p = self.bin / name
            p.write_text("#!/bin/sh\nexec %s %s \"$@\"\n" % (sys.executable, FAKEWORLD / target))
            p.chmod(0o755)
        # pm's probe/auth-status calls `claude`: point it at the fake (the real binary is only the session)
        (self.bin / "claude").symlink_to(self.bin / "claude-fake")
        orca = {"settings": {"activeClaudeManagedAccountId": None, "claudeManagedAccounts": []}}
        for email in (A, B):
            acc_id, org = str(uuid.uuid4()), str(uuid.uuid4())
            fake_anthropic.add_account(email, str(uuid.uuid4()), org, 10.0, 20.0)
            creds = fake_anthropic.mint(email, 3600)
            keychain_db.write_json(self.db, ORCA, acc_id, {"claudeAiOauth": creds})
            orca["settings"]["claudeManagedAccounts"].append({"id": acc_id, "email": email, "organizationUuid": org,
                                                              "organizationName": email})
            self.accounts[email] = acc_id
        a = keychain_db.read_json(self.db, ORCA, self.accounts[A])
        mcp = {"linear-server|drill": {"serverName": "linear-server", "accessToken": "lin-live",
                                       "refreshToken": "lin-live-rt", "expiresAt": 1999999999999}}
        if self.scenario == "rotation-back":
            soon = fake_anthropic.now_ms() + 120_000  # inside Claude Code's 5-minute refresh window
            a["claudeAiOauth"]["expiresAt"] = soon
            keychain_db.write_json(self.db, ORCA, self.accounts[A], a)
            with fake_anthropic.state() as d:
                d["access"][a["claudeAiOauth"]["accessToken"]]["expires_at_ms"] = soon
        keychain_db.write_json(self.db, STORE, USER, {"claudeAiOauth": a["claudeAiOauth"], "mcpOAuth": mcp})
        orca["settings"]["activeClaudeManagedAccountId"] = self.accounts[A]
        orca_path = self.home / "Library/Application Support/orca/profiles/local-default/orca-data.json"
        orca_path.write_text(json.dumps(orca))
        (self.home / ".claude.json").write_text(json.dumps({
            "hasCompletedOnboarding": True, "oauthAccount": {"emailAddress": A}}))
        b = keychain_db.read_json(self.db, ORCA, self.accounts[B])["claudeAiOauth"]
        if self.scenario == "stale-target":
            fake_anthropic.consume(b["refreshToken"])
        if self.scenario in ("stale-target", "healthy-target"):
            fake_anthropic.expire_access(b["accessToken"])
            b["expiresAt"] = fake_anthropic.now_ms() - 60_000
            keychain_db.write_json(self.db, ORCA, self.accounts[B], {"claudeAiOauth": b})

    def env(self) -> dict:
        return {
            "HOME": str(self.home), "USER": USER, "LOGNAME": USER, "PATH": "%s:/usr/bin:/bin" % self.bin,
            "TMPDIR": str(self.root), "LANG": "en_US.UTF-8", "TERM": "dumb",
            "FAKE_SECURITY_DB": self.db, "FAKE_ANTHROPIC_STATE": self.api, "PYTHONPATH": str(FAKEWORLD),
            "HTTPS_PROXY": "http://127.0.0.1:%d" % self.port, "HTTP_PROXY": "http://127.0.0.1:%d" % self.port,
            "NODE_EXTRA_CA_CERTS": str(self.root / "mitm/mitmproxy-ca-cert.pem"),
            "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }

    def sandboxed(self, argv):
        return ["/usr/bin/sandbox-exec", "-f", str(self.sb)] + argv

    # -- preflight ----------------------------------------------------------------------------
    def preflight(self):
        env = self.env()
        r = subprocess.run(self.sandboxed(["/usr/bin/security", "find-generic-password", "-s", STORE]),
                           capture_output=True, text=True, env=env)
        assert r.returncode != 0, "sandbox does not block the login keychain; refusing to run"
        r = subprocess.run(self.sandboxed(["/bin/sh", "-c", "command -v security"]), capture_output=True, text=True, env=env)
        assert r.stdout.strip() == str(self.bin / "security"), "fake security is not first on PATH: %r" % r.stdout
        r = subprocess.run(self.sandboxed(["security", "find-generic-password", "-s", STORE, "-a", USER, "-w"]),
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0 and '"claudeAiOauth"' in r.stdout, "scratch store unreadable through the fake"
        r = subprocess.run(self.sandboxed(["/bin/cat", "%s/.claude.json" % REAL_HOME]), capture_output=True, env=env)
        assert r.returncode != 0, "sandbox does not hide the real ~/.claude.json; refusing to run"
        return True

    # -- processes ----------------------------------------------------------------------------
    def start_mitm(self):
        env = self.env()
        env.update({"DRILL_DIR": str(self.root), "DRILL_FAKEWORLD": str(FAKEWORLD),
                    "DRILL_GATES": ",".join(str(g) for g in SCENARIOS[self.scenario]["gates"]),
                    "DRILL_MAIN_CALLS": str(SCENARIOS[self.scenario]["calls"])})
        env.pop("HTTPS_PROXY")
        env.pop("HTTP_PROXY")
        mitmdump = shutil.which("mitmdump", path=os.environ.get("PATH")) or "mitmdump"
        self.mitm = subprocess.Popen(self.sandboxed([
            mitmdump, "--listen-host", "127.0.0.1", "--listen-port", str(self.port), "-q",
            "--set", "confdir=%s" % (self.root / "mitm"), "--set", "upstream_cert=false",
            "--set", "connection_strategy=lazy", "-s", str(HERE / "stub_addon.py")]),
            env=env, stdout=open(self.root / "mitm.log", "w"), stderr=subprocess.STDOUT)
        deadline = time.time() + 30
        while time.time() < deadline:
            if (self.root / "mitm/mitmproxy-ca-cert.pem").exists():
                try:
                    socket.create_connection(("127.0.0.1", self.port), timeout=0.5).close()
                    return
                except OSError:
                    pass
            time.sleep(0.2)
        raise RuntimeError("mitmdump did not start: %s" % (self.root / "mitm.log").read_text()[-800:])

    def switch(self, email):
        r = subprocess.run(self.sandboxed([sys.executable, str(self.impl / "provider_manager.py"), "switch", email, "--json"]),
                           capture_output=True, text=True, env=self.env(), timeout=120)
        out = (r.stdout or "").strip()
        try:
            res = json.loads(out.splitlines()[-1]) if out else {}
        except ValueError:
            res = {"raw": out[-300:]}
        res["rc"] = r.returncode
        if r.stderr.strip():
            res["stderr"] = r.stderr.strip()[-300:]
        return res

    def wait_for(self, name, timeout, proc):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if (self.root / name).exists():
                return True
            if proc.poll() is not None:
                return False
            time.sleep(0.1)
        return False

    def run_probe(self):
        """probe_active_account() with `claude` resolving to the real binary, inside the sandbox."""
        real = os.path.realpath(shutil.which("claude", path="%s/.local/bin:%s" % (REAL_HOME, os.environ.get("PATH", ""))))
        os.unlink(self.bin / "claude")
        (self.bin / "claude").symlink_to(real)
        code = ("import sys,json;sys.path.insert(0,%r);import provider_manager as pm;"
                "print(json.dumps(pm.probe_active_account()))" % str(self.impl))
        results = {}
        a = keychain_db.read_json(self.db, STORE, USER)["claudeAiOauth"]
        for state in ("healthy", "exhausted", "dead_grant"):
            if state == "exhausted":
                fake_anthropic.set_account(A, exhausted=True)
            if state == "dead_grant":
                fake_anthropic.set_account(A, exhausted=False)
                fake_anthropic.consume(a["refreshToken"])
                fake_anthropic.expire_access(a["accessToken"])
                a["expiresAt"] = fake_anthropic.now_ms() - 1000
                keychain_db.update_json(self.db, STORE, USER, lambda c: dict(c, claudeAiOauth=a))
            r = subprocess.run(self.sandboxed([sys.executable, "-c", code]), capture_output=True, text=True,
                               env=self.env(), timeout=240)
            try:
                results[state] = json.loads(r.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                results[state] = ["error", (r.stderr or r.stdout)[-300:]]
            raw = subprocess.run(self.sandboxed([real, "-p", "Reply with the single word OK.", "--tools", "",
                                                 "--strict-mcp-config", "--setting-sources", "project",
                                                 "--no-session-persistence", "--output-format", "json"]),
                                 capture_output=True, text=True, env=self.env(), timeout=240, cwd=str(self.root))
            results[state + "_raw"] = {"rc": raw.returncode, "stdout": raw.stdout[-600:], "stderr": raw.stderr[-300:]}
        expected = {"healthy": "ok", "exhausted": "limited", "dead_grant": "auth_dead"}
        ok = all(results[k][0] == v for k, v in expected.items())
        return {"scenario": "probe", "impl": "new" if self.impl == NEW_IMPL else str(self.impl),
                "verdict": "CLASSIFIED" if ok else "MISCLASSIFIED", "results": results, "expected": expected,
                "served_by": [], "scratch": str(self.root)}

    def run(self):
        self.build()
        self.preflight()
        self.start_mitm()
        if self.scenario == "probe":
            return self.run_probe()
        claude = os.path.realpath(shutil.which("claude", path="%s/.local/bin:%s" % (REAL_HOME, os.environ.get("PATH", ""))))
        prompt = "Drill: run the bash commands you are given until told you are done."
        out = open(self.root / "claude.out", "w")
        proc = subprocess.Popen(self.sandboxed([
            claude, "-p", prompt, "--model", "haiku", "--output-format", "stream-json", "--verbose",
            "--dangerously-skip-permissions", "--no-session-persistence", "--strict-mcp-config"]),
            cwd=str(self.root), env=self.env(), stdout=out, stderr=subprocess.STDOUT)
        actions = []
        gates = SCENARIOS[self.scenario]["gates"]
        plan = [B] if len(gates) == 1 else [B, A]
        for gate, target in zip(gates, plan):
            if not self.wait_for("gate-%d.reached" % gate, 120, proc):
                actions.append({"gate": gate, "error": "session ended before the gate"})
                break
            if self.scenario == "rotation-back" and gate == gates[0]:
                self._time_passes_for_a()
            actions.append({"gate": gate, "switchTo": target, "result": self.switch(target)})
            (self.root / ("gate-%d.release" % gate)).touch()
        try:
            proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            proc.kill()
        out.close()
        return self.report(proc.returncode, actions)

    def _time_passes_for_a(self):
        """By the first gate the session has refreshed A (its token was inside the 5-minute window).
        Let A's pre-refresh access token, which A's Orca copy still holds, expire."""
        a = keychain_db.read_json(self.db, ORCA, self.accounts[A])["claudeAiOauth"]
        fake_anthropic.expire_access(a["accessToken"])
        a["expiresAt"] = fake_anthropic.now_ms() - 1000
        keychain_db.write_json(self.db, ORCA, self.accounts[A], {"claudeAiOauth": a})

    def report(self, rc, actions):
        text = (self.root / "claude.out").read_text()
        served = [json.loads(l) for l in (self.root / "served.jsonl").read_text().splitlines()] \
            if (self.root / "served.jsonl").exists() else []
        tokens = [json.loads(l)["status"] for l in (self.root / "token.jsonl").read_text().splitlines()] \
            if (self.root / "token.jsonl").exists() else []
        store = keychain_db.read_json(self.db, STORE, USER) or {}
        result = None
        for line in text.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "result":
                result = ev
        killed = "OAuth session expired and could not be refreshed" in text
        finished = bool(result) and not result.get("is_error") and "DRILL-DONE" in str(result.get("result"))
        return {
            "scenario": self.scenario, "impl": "new" if self.impl == NEW_IMPL else str(self.impl),
            "verdict": "SURVIVED" if finished else ("KILLED" if killed else "FAILED"),
            "claude_rc": rc, "result": (result or {}).get("result"), "is_error": (result or {}).get("is_error"),
            "served_by": [(s["call"], s.get("email"), s["status"]) for s in served],
            "token_endpoint": tokens, "switches": actions,
            "store_mcp_intact": (store.get("mcpOAuth") or {}).get("linear-server|drill", {}).get("refreshToken") == "lin-live-rt",
            "scratch": str(self.root),
        }

    def cleanup(self):
        if self.mitm and self.mitm.poll() is None:
            self.mitm.terminate()
            try:
                self.mitm.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.mitm.kill()
        if not self.keep:
            trash = shutil.which("trash")
            if trash:
                subprocess.run([trash, str(self.root)], capture_output=True)
            else:
                shutil.rmtree(self.root, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", default="new", help="'new' or a scripts dir (e.g. origin/main's)")
    ap.add_argument("--scenario", choices=sorted(SCENARIOS), default="stale-target")
    ap.add_argument("--all", action="store_true", help="every scenario, new and --old-impl")
    ap.add_argument("--old-impl")
    ap.add_argument("--keep", action="store_true", help="keep the scratch dir")
    args = ap.parse_args()
    runs = []
    if args.all:
        impls = [NEW_IMPL] + ([Path(args.old_impl)] if args.old_impl else [])
        runs = [(i, s) for s in sorted(SCENARIOS) if s != "probe" for i in impls] + [(NEW_IMPL, "probe")]
    else:
        runs = [(NEW_IMPL if args.impl == "new" else Path(args.impl), args.scenario)]
    reports = []
    for impl, scenario in runs:
        r = Run(impl, scenario, args.keep)
        try:
            reports.append(r.run())
        finally:
            r.cleanup()
        print(json.dumps(reports[-1], indent=2), flush=True)
    print("\n%-16s %-6s %-9s %s" % ("SCENARIO", "IMPL", "VERDICT", "SERVED BY (call, account, status)"))
    for rep in reports:
        print("%-16s %-6s %-9s %s" % (rep["scenario"], "new" if rep["impl"] == "new" else "old", rep["verdict"],
                                     rep["served_by"]))


if __name__ == "__main__":
    main()
