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

INITIALIZE_TIMEOUT = 15
# Requests without thread identity may only observe the currently selected account.
READ_ONLY_METHODS = frozenset({
    "account/read", "account/rateLimits/read", "account/usage/read", "account/workspaceMessages/read",
    "model/list", "modelProvider/capabilities/read", "skills/list", "hooks/list", "config/read",
    "configRequirements/read", "app/list", "app/read", "experimentalFeature/list",
    "permissionProfile/list", "mcpServerStatus/list", "thread/list", "thread/loaded/list",
    "threadSection/list", "plugin/list", "plugin/read", "plugin/skill/read",
    "collaborationMode/list", "getUserSavedConfig",
})
THREAD_METHODS = frozenset({
    "thread/resume", "thread/fork", "thread/archive", "thread/delete", "thread/unsubscribe",
    "thread/name/set", "thread/goal/set", "thread/goal/get", "thread/goal/clear",
    "thread/metadata/update", "thread/attachment/add", "thread/attachment/list",
    "thread/attachment/remove", "thread/section/move", "thread/unarchive", "thread/compact/start",
    "thread/shellCommand", "thread/approveGuardianDeniedAction", "thread/revert", "thread/read",
    "thread/turns/list", "thread/items/list", "thread/inject_items", "turn/start", "turn/steer",
    "turn/interrupt", "review/start", "feedback/upload", "mcpServerStatus/list",
    "mcpServer/tool/call", "mcpServer/resource/read",
    "thread/rollback", "thread/backgroundTerminals/list", "thread/backgroundTerminals/terminate",
})


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
    """One initialized child per concrete home; JSON-RPC IDs never cross children unqualified."""
    def __init__(self, binary, args, home, account, input_stream=None, output_stream=None):
        self.binary, self.args = str(binary), list(args)
        self.initial_account = _identity(home, account.get("email"))
        self.input = input_stream or sys.stdin.buffer
        self.output = output_stream or sys.stdout.buffer
        self.events = queue.Queue()
        self.children = {}
        self.server_requests = {}
        self.server_sequence = 0
        self.sequence = 0
        self.initialize = None
        self.initialized = None

    def next_id(self, prefix):
        self.sequence += 1
        return "provider-manager-%s-%s" % (prefix, self.sequence)

    def server_id(self):
        # Paseo accepts numeric IDs only. Never recycle one while this proxy lives.
        if self.server_sequence >= 2**53 - 1:
            raise pm_store.StoreError("Codex server request ID space exhausted")
        self.server_sequence += 1
        return self.server_sequence

    def resolve_server_request(self, child, native_id):
        for host_id, (origin, ident, _) in list(self.server_requests.items()):
            if origin is child and ident == native_id:
                del self.server_requests[host_id]
                return host_id
        return None

    def emit(self, message):
        self.output.write((json.dumps(message) + "\n").encode())
        self.output.flush()

    def error(self, request, message, code=-32001):
        if "id" in request:
            self.emit({"id": request["id"], "error": {"code": code, "message": message}})

    def reader(self, stream, source, child=None):
        try:
            for line in stream:
                self.events.put((source, child, line))
        except (OSError, ValueError):
            pass
        finally:
            self.events.put((source, child, None))

    def selected(self):
        account = pm_codex_homes.selected()
        if not isinstance(account, dict):
            raise pm_store.StoreError("No Codex account selected")
        return _identity(account["home"], account.get("email"))

    def send(self, child, message):
        try:
            child["process"].stdin.write((json.dumps(message) + "\n").encode())
            child["process"].stdin.flush()
        except (OSError, ValueError):
            self.fail_child(child, "Codex account app-server disconnected")

    def spawn(self, account, initial_request=None):
        key = account["home"]
        if key in self.children:
            return self.children[key]
        process = subprocess.Popen(
            [self.binary, *self.args, "-c", 'cli_auth_credentials_store="file"'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            env=dict(os.environ, CODEX_HOME=key))
        child = {"account": account, "process": process, "ready": False, "failed": False,
                 "pending": {}, "queued": [], "turns": {},
                 "deadline": time.monotonic() + INITIALIZE_TIMEOUT,
                 "initial_request": initial_request}
        self.children[key] = child
        threading.Thread(target=self.reader, args=(process.stdout, "child", child), daemon=True).start()
        ident = self.next_id("initialize")
        child["init_id"] = ident
        self.send(child, dict(self.initialize, id=ident))
        return child

    def stop_child(self, child):
        process = child["process"]
        try:
            process.stdin.close()
        except (OSError, ValueError):
            pass
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdout.close()

    def stop(self):
        for child in list(self.children.values()):
            self.stop_child(child)

    def fail_child(self, child, message):
        if child["failed"]:
            return
        child["failed"] = True
        if child["initial_request"] is not None:
            self.error(child["initial_request"], message)
            child["initial_request"] = None
        for request in list(child["pending"].values()) + child["queued"]:
            self.error(request, message)
        child["pending"].clear()
        child["queued"].clear()
        for thread_id, turn_id in child["turns"].items():
            self.emit({"method": "error", "params": {"threadId": thread_id, "turnId": turn_id,
                       "willRetry": False, "error": {"message": message}}})
            self.emit({"method": "turn/completed", "params": {"threadId": thread_id,
                       "turn": {"id": turn_id, "items": [], "status": "failed",
                                "error": {"message": message}, "completedAt": int(time.time())}}})
        child["turns"].clear()
        for ident, (origin, _, thread_id) in list(self.server_requests.items()):
            if origin is child:
                del self.server_requests[ident]
                self.emit({"method": "serverRequest/resolved", "params": {"requestId": ident, "threadId": thread_id}})
        self.stop_child(child)

    def flush(self, child):
        if child["ready"] and not child["failed"]:
            queued, child["queued"] = child["queued"], []
            for request in queued:
                self.forward(child, request)

    def forward(self, child, request):
        if child["failed"]:
            self.error(request, "This Codex account app-server failed; restart the client to reconnect to the same home")
        elif not child["ready"]:
            child["queued"].append(request)
        elif "id" in request:
            ident = self.next_id("request")
            child["pending"][ident] = request
            self.send(child, dict(request, id=ident))
        else:
            self.send(child, request)

    def receive(self, request):
        if not isinstance(request, dict):
            self.error({"id": None}, "Expected JSON-RPC object", -32600)
            return
        if "id" in request and (isinstance(request["id"], bool) or not isinstance(request["id"], (str, int))):
            self.error({"id": None}, "Invalid JSON-RPC ID", -32600)
            return
        method = request.get("method")
        if method is None:
            binding = self.server_requests.pop(request.get("id"), None)
            if binding:
                child, ident, _ = binding
                if not child["failed"]:
                    self.send(child, dict(request, id=ident))
            return
        if method in ("account/login/start", "account/login/cancel", "account/logout"):
            self.error(request, "Use provider-manager reauthorization; login/logout cannot replace a pinned Codex home's grant")
            return
        if method == "initialize":
            if self.initialize is not None:
                self.error(request, "Already initialized", -32600)
                return
            self.initialize = request
            try:
                self.spawn(self.initial_account, request)
            except OSError:
                self.error(request, "Could not start the selected Codex account app-server")
            return
        if self.initialize is None:
            self.error(request, "Initialize Codex before sending requests", -32600)
            return
        if method == "initialized":
            self.initialized = request
            for child in self.children.values():
                if child.get("init_complete") and not child["ready"] and not child["failed"]:
                    self.send(child, request)
                    child["ready"] = True
                    self.flush(child)
            return
        try:
            params = request.get("params") or {}
            if not isinstance(params, dict):
                raise pm_store.StoreError("JSON-RPC params must be an object")
            if method == "thread/start":
                account = self.selected()
            elif method in (THREAD_METHODS | READ_ONLY_METHODS) and params.get("threadId"):
                account = thread_home(params["threadId"])
            elif method in READ_ONLY_METHODS and not params.get("threadId"):
                account = self.selected()
            else:
                raise pm_store.StoreError("Unsupported account-global or unscoped RPC: %s" % method)
            self.forward(self.spawn(account), request)
        except (OSError, KeyError, TypeError, pm_store.StoreError) as exc:
            self.error(request, str(exc))

    def response(self, child, message):
        if child["failed"]:
            return
        if not isinstance(message, dict):
            self.fail_child(child, "Codex app-server returned an invalid message")
            return
        ident = message.get("id")
        if "id" in message and not isinstance(ident, (str, int)):
            self.fail_child(child, "Codex app-server returned an invalid request ID")
            return
        if message.get("method"):
            params = message.get("params") or {}
            if not isinstance(params, dict):
                self.fail_child(child, "Codex app-server returned invalid notification params")
                return
            method = message["method"]
            if "id" not in message and method in ("account/updated", "account/rateLimits/updated"):
                # The host exposes one provider account display; keep it on the selected account.
                # Thread/turn notifications from every account must still reach their own thread.
                try:
                    if child["account"] != self.selected():
                        return
                except (OSError, pm_store.StoreError):
                    return
            if method == "thread/started":
                try:
                    remember_thread(params["thread"]["id"], child["account"])
                except (KeyError, TypeError, OSError, pm_store.StoreError):
                    self.fail_child(child, "Could not persist native Codex thread ownership")
                    return
            if method in ("turn/started", "turn/completed"):
                thread_id = params.get("threadId")
                turn = params.get("turn") or {}
                if isinstance(thread_id, str) and isinstance(turn, dict) and isinstance(turn.get("id"), str):
                    if method == "turn/started":
                        child["turns"][thread_id] = turn["id"]
                    else:
                        child["turns"].pop(thread_id, None)
            if "id" in message:
                if method == "account/chatgptAuthTokens/refresh":
                    self.send(child, {"id": ident, "error": {"code": -32001,
                              "message": "Use provider-manager reauthorization for this account home"}})
                    return
                try:
                    proxy_id = self.server_id()
                except pm_store.StoreError as exc:
                    self.fail_child(child, str(exc))
                    return
                self.server_requests[proxy_id] = (child, ident, params.get("threadId", ""))
                self.emit(dict(message, id=proxy_id))
            elif method == "serverRequest/resolved":
                host_id = self.resolve_server_request(child, params.get("requestId"))
                if host_id is not None:
                    self.emit(dict(message, params=dict(params, requestId=host_id)))
            else:
                self.emit(message)
            return
        if ident == child["init_id"]:
            initial = child["initial_request"]
            child["initial_request"] = None
            if "error" in message or "result" not in message:
                if initial is not None:
                    self.error(initial, "Codex initialization failed in the account home")
                self.fail_child(child, "Codex initialization failed in the account home")
                return
            child["init_complete"] = True
            if initial is not None:
                self.emit(dict(message, id=initial["id"]))
            if self.initialized is not None:
                self.send(child, self.initialized)
                child["ready"] = True
                self.flush(child)
            return
        request = child["pending"].pop(ident, None)
        if request is None:
            return
        method = request["method"]
        if method in ("thread/start", "thread/resume", "thread/fork") and "result" in message:
            try:
                remember_thread(message["result"]["thread"]["id"], child["account"])
            except (KeyError, TypeError, OSError, pm_store.StoreError):
                self.error(request, "Could not persist native Codex thread ownership")
                self.fail_child(child, "Codex thread ownership failed; account home unchanged")
                return
        if method == "turn/start" and "result" in message:
            turn = message["result"].get("turn", {})
            if isinstance(turn, dict) and isinstance(turn.get("id"), str):
                child["turns"][request["params"]["threadId"]] = turn["id"]
        self.emit(dict(message, id=request["id"]))

    def run(self):
        threading.Thread(target=self.reader, args=(self.input, "input"), daemon=True).start()
        try:
            while True:
                now = time.monotonic()
                deadlines = [child["deadline"] for child in self.children.values()
                             if not child["ready"] and not child["failed"]]
                for child in list(self.children.values()):
                    if not child["ready"] and not child["failed"] and now >= child["deadline"]:
                        self.fail_child(child, "Codex initialization timed out in the account home")
                timeout = max(0, min(deadlines) - now) if deadlines else None
                try:
                    source, child, line = self.events.get(timeout=timeout)
                except queue.Empty:
                    continue
                if source == "input" and line is None:
                    return 0
                if source == "child" and child["failed"]:
                    continue
                if source == "child" and line is None:
                    self.fail_child(child, "Codex account app-server exited; its threads remain pinned")
                    continue
                try:
                    message = json.loads(line)
                except (ValueError, UnicodeError):
                    if source == "child":
                        self.fail_child(child, "Codex account app-server returned invalid JSON")
                    else:
                        self.error({"id": None}, "Invalid JSON", -32700)
                    continue
                if source == "input":
                    self.receive(message)
                else:
                    self.response(child, message)
        finally:
            self.stop()


def run(binary, args, home, account):
    proxy = Proxy(binary, args, home, account)
    handlers = {}
    def forward(signum, _frame):
        for child in proxy.children.values():
            if child["process"].poll() is None:
                child["process"].send_signal(signum)
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
