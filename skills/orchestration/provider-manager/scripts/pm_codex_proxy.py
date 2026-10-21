"""Pin native Codex threads to their account home across app-server restarts."""
import hashlib
import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pm_codex_homes
import pm_store

DISCOVERY_DRAIN_SECONDS = 15
DISCOVERY_METHODS = frozenset({"account/read", "account/rateLimits/read", "model/list",
                              "skills/list", "config/read", "configRequirements/read",
                              "app/list", "experimentalFeature/list", "mcpServerStatus/list"})


def _identity(home, expected=None):
    home = Path(home)
    if not home.is_absolute() or home.resolve(strict=True) != home or not home.is_dir():
        raise pm_store.StoreError("Codex thread home must be a concrete absolute directory")
    if (home / "auth.json").is_symlink():
        raise pm_store.StoreError("Codex thread auth must not be a symlink")
    auth = pm_store.read_codex_auth(home / "auth.json")
    tokens = (auth.data or {}).get("tokens")
    if not isinstance(tokens, dict):
        raise pm_store.StoreError("Codex thread home account cannot be verified")
    email = pm_store.extract_codex_identity(tokens).get("email")
    if auth.status != "ok" or not email or (expected and email != expected):
        raise pm_store.StoreError("Codex thread home account cannot be verified")
    return {"home": str(home), "email": email}


def _mapping_path(thread_id):
    if not isinstance(thread_id, str) or not thread_id:
        raise pm_store.StoreError("Codex thread ID is missing")
    directory = pm_codex_homes.root() / "threads"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise pm_store.StoreError("Codex thread registry must not be a symlink")
    return directory / (hashlib.sha256(thread_id.encode()).hexdigest() + ".json")


def _read_mapping(path):
    if path.is_symlink():
        raise pm_store.StoreError("Codex thread mapping must not be a symlink")
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not isinstance(data.get("email"), str):
            raise ValueError()
        return _identity(data["home"], data["email"])
    except (KeyError, ValueError, TypeError) as exc:
        raise pm_store.StoreError("Codex thread mapping is invalid") from exc


def thread_home(thread_id):
    path = _mapping_path(thread_id)
    if path.exists() or path.is_symlink():
        return _read_mapping(path)
    return _identity(pm_store.CODEX_AUTH_PATH.parent)


def remember_thread(thread_id, account):
    path = _mapping_path(thread_id)
    fd, temporary = tempfile.mkstemp(prefix=".thread-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(account, out)
            out.flush()
            os.fsync(out.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if _read_mapping(path) != account:
                raise pm_store.StoreError("Codex thread already belongs to another account home")
    finally:
        os.unlink(temporary)


class Proxy:
    def __init__(self, binary, args, home, account, input_stream=None, output_stream=None):
        self.binary, self.args = str(binary), list(args)
        self.account = _identity(home, account.get("email"))
        self.input = input_stream or sys.stdin.buffer
        self.output = output_stream or sys.stdout.buffer
        self.events = queue.Queue()
        self.child = None
        self.epoch = 0
        self.pending = {}
        self.initialize = None
        self.initialized = None
        self.replay = None
        self.waiting = None
        self.deferred = []
        self.active = False

    def emit(self, message):
        self.output.write((json.dumps(message) + "\n").encode())
        self.output.flush()

    def error(self, request, message):
        if "id" in request:
            self.emit({"id": request["id"], "error": {"code": -32001, "message": message}})

    def send(self, message):
        self.child.stdin.write((json.dumps(message) + "\n").encode())
        self.child.stdin.flush()

    def reader(self, stream, source, epoch):
        try:
            for line in stream:
                self.events.put((source, epoch, line))
        except (OSError, ValueError):
            pass
        finally:
            self.events.put((source, epoch, None))

    def spawn(self):
        self.epoch += 1
        self.child = subprocess.Popen([self.binary, *self.args, "-c", 'cli_auth_credentials_store="file"'], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, env=dict(os.environ, CODEX_HOME=self.account["home"]))
        threading.Thread(target=self.reader, args=(self.child.stdout, "child", self.epoch), daemon=True).start()

    def stop(self):
        if self.child is None:
            return
        self.child.stdin.close()
        if self.child.poll() is None:
            self.child.terminate()
        try:
            self.child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.child.kill()
            self.child.wait()
        self.child.stdout.close()

    def receive(self, request):
        if not isinstance(request, dict):
            self.emit({"id": None, "error": {"code": -32600, "message": "Expected JSON-RPC object"}})
            return
        method = request.get("method")
        if method in ("account/login/start", "account/logout"):
            self.error(request, "Use provider-manager reauthorization; login/logout cannot replace a pinned Codex home's grant")
            return
        if self.replay is not None or self.waiting is not None:
            self.deferred.append(request)
            return
        if method in ("thread/resume", "thread/fork"):
            try:
                target = thread_home(request.get("params", {}).get("threadId"))
                if target != self.account:
                    if self.active:
                        raise pm_store.StoreError("A running Codex session cannot move to another account home")
                    if self.initialize is None:
                        raise pm_store.StoreError("Codex account switch requires completed initialization and no pending requests")
                    if self.pending:
                        if all(value in DISCOVERY_METHODS for value in self.pending.values()):
                            self.waiting = (request, time.monotonic() + DISCOVERY_DRAIN_SECONDS)
                            return
                        raise pm_store.StoreError("Codex account switch cannot interrupt pending non-discovery requests")
                    self.stop()
                    self.account = target
                    self.spawn()
                    replay_id = "provider-manager-initialize-%s" % self.epoch
                    self.replay = (replay_id, request)
                    self.send(dict(self.initialize, id=replay_id))
                    return
            except (OSError, pm_store.StoreError, AttributeError) as exc:
                self.error(request, str(exc))
                return
        if method == "initialize":
            self.initialize = request
        elif method == "initialized":
            self.initialized = request
        if method and "id" in request:
            self.pending[request["id"]] = method
        self.send(request)

    def response(self, message):
        if not isinstance(message, dict):
            raise pm_store.StoreError("Codex app-server returned a non-object message")
        if self.replay and message.get("id") == self.replay[0]:
            request = self.replay[1]
            self.replay = None
            if "error" in message or "result" not in message:
                self.error(request, "Codex initialization failed in the thread's account home")
                raise pm_store.StoreError("Codex initialization replay failed")
            else:
                if self.initialized:
                    self.send(self.initialized)
                self.receive(request)
            deferred, self.deferred = self.deferred, []
            for queued in deferred:
                self.receive(queued)
            return
        method = (self.pending.pop(message.get("id"), None)
                  if "id" in message and "method" not in message else None)
        if method in ("thread/start", "thread/resume", "thread/fork") and "result" in message:
            try:
                thread_id = message["result"]["thread"]["id"]
                remember_thread(thread_id, self.account)
                self.active = True
            except (KeyError, TypeError, OSError, pm_store.StoreError):
                self.error(message, "Could not persist the Codex thread's account home")
                return
        self.emit(message)
        if self.waiting is not None and not self.pending:
            request = self.waiting[0]
            self.waiting = None
            self.receive(request)
            if self.replay is None:
                self.flush_deferred()

    def flush_deferred(self):
        deferred, self.deferred = self.deferred, []
        for queued in deferred:
            self.receive(queued)

    def run(self):
        self.spawn()
        threading.Thread(target=self.reader, args=(self.input, "input", 0), daemon=True).start()
        try:
            while True:
                timeout = max(0, self.waiting[1] - time.monotonic()) if self.waiting else None
                try:
                    if timeout == 0:
                        raise queue.Empty
                    source, epoch, line = self.events.get(timeout=timeout)
                except queue.Empty:
                    request = self.waiting[0]
                    self.waiting = None
                    self.error(request, "Codex discovery did not finish before account-switch timeout; retry resume")
                    self.flush_deferred()
                    continue
                if source == "child" and epoch != self.epoch:
                    continue
                if line is None:
                    return 0 if source == "input" else self.child.wait()
                try:
                    message = json.loads(line)
                except (ValueError, UnicodeError):
                    if source == "child":
                        raise pm_store.StoreError("Codex app-server returned invalid JSON")
                    self.emit({"id": None, "error": {"code": -32700, "message": "Invalid JSON"}})
                    continue
                if source == "input":
                    self.receive(message)
                else:
                    self.response(message)
        finally:
            self.stop()


def run(binary, args, home, account):
    proxy = Proxy(binary, args, home, account)
    handlers = {}
    def forward(signum, _frame):
        if proxy.child and proxy.child.poll() is None:
            proxy.child.send_signal(signum)
        raise SystemExit(128 + signum)
    try:
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            handlers[signum] = signal.signal(signum, forward)
        return proxy.run()
    except (OSError, pm_store.StoreError):
        print("codex-account: app-server proxy failed; credentials were not changed", file=sys.stderr)
        return 1
    finally:
        proxy.stop()
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
