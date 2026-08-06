#!/usr/bin/env python3
"""Read Antigravity quota windows from a local process or JSON export.

Antigravity does not expose trace-level token or cost history through this
interface. This module deliberately returns quota windows only. Local probes
are pinned to 127.0.0.1, never start a process, and never emit CSRF tokens or
account identity.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable


UTC = dt.timezone.utc
QUOTA_SUMMARY_PATH = "/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary"
USER_STATUS_PATH = "/exa.language_server_pb.LanguageServerService/GetUserStatus"
MODEL_CONFIG_PATH = "/exa.language_server_pb.LanguageServerService/GetCommandModelConfigs"


@dataclasses.dataclass(slots=True)
class ProcessInfo:
    pid: int
    kind: str
    csrf_token: str
    extension_port: int | None = None
    extension_csrf_token: str | None = None


@dataclasses.dataclass(slots=True, frozen=True)
class Endpoint:
    scheme: str
    port: int
    csrf_token: str
    source: str


@dataclasses.dataclass(slots=True)
class ProbeResult:
    windows: list[dict[str, Any]]
    backend: str
    warnings: list[str] = dataclasses.field(default_factory=list)
    files_discovered: int = 0


def _safe_identifier(value: Any, fallback: str) -> str:
    candidate = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+ -]{0,95}", candidate):
        return candidate
    return fallback


def _fraction(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) and 0 <= parsed <= 1 else None


def _reset_time(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) or re.fullmatch(r"\d+(?:\.\d+)?", str(value)):
            parsed = dt.datetime.fromtimestamp(float(value), tz=UTC)
        else:
            parsed = dt.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
            parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (OSError, OverflowError, TypeError, ValueError):
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def _family(label: str) -> str:
    lower = label.lower()
    if "gemini" in lower:
        return "gemini"
    if "claude" in lower or "gpt" in lower:
        return "claude-gpt"
    return "other"


def _cadence(bucket_id: str, display_name: str) -> tuple[str, int | None]:
    aliases = {"session", "5h", "5-hour", "five hour", "five-hour"}
    candidates: set[str] = set()
    for raw in (bucket_id, display_name):
        normalized = raw.strip().lower().replace("_", "-")
        if not normalized:
            continue
        values = [normalized]
        if normalized.endswith(" limit"):
            values.append(normalized[: -len(" limit")])
        for value in values:
            candidates.add(value)
            for alias in aliases | {"weekly"}:
                if value.endswith(f"-{alias}"):
                    candidates.add(alias)
    if not candidates.isdisjoint(aliases):
        return "5-hour", 300
    if "weekly" in candidates:
        return "weekly", 10080
    return "quota", None


def _remaining_value(bucket: dict[str, Any]) -> Any:
    if bucket.get("remainingFraction") is not None:
        return bucket["remainingFraction"]
    remaining = bucket.get("remaining")
    if not isinstance(remaining, dict):
        return None
    if remaining.get("remainingFraction") is not None:
        return remaining["remainingFraction"]
    if remaining.get("case") == "remainingFraction":
        return remaining.get("value")
    return None


def _valid_code(payload: dict[str, Any]) -> bool:
    code = payload.get("code")
    return code in (None, 0, "0", "OK", "ok")


def parse_quota_summary(payload: Any, source: str = "export") -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize RetrieveUserQuotaSummary response shapes."""
    if not isinstance(payload, dict) or not _valid_code(payload):
        return [], ["Antigravity quota summary returned a non-success response."]
    root = payload.get("response") or payload.get("summary") or payload
    groups = root.get("groups") if isinstance(root, dict) else None
    if not isinstance(groups, list):
        return [], []
    windows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict) or not isinstance(group.get("buckets"), list):
            continue
        raw_group_name = str(group.get("displayName") or "")
        family = _family(raw_group_name)
        family_title = "Gemini" if family == "gemini" else "Claude/GPT" if family == "claude-gpt" else "Quota"
        for bucket_index, bucket in enumerate(group["buckets"]):
            if not isinstance(bucket, dict):
                continue
            bucket_id = _safe_identifier(bucket.get("bucketId"), "")
            if not bucket_id:
                warnings.append("Ignored an Antigravity quota bucket without a safe id.")
                continue
            bucket_name = str(bucket.get("displayName") or "")
            title, minutes = _cadence(bucket_id, bucket_name)
            raw_remaining = _remaining_value(bucket)
            remaining = _fraction(raw_remaining)
            if raw_remaining is not None and remaining is None:
                warnings.append(f"Ignored an invalid Antigravity remaining fraction for {bucket_id}.")
            disabled = bucket.get("disabled") is True
            reset_raw = bucket.get("resetTime")
            resets_at = _reset_time(reset_raw)
            if reset_raw is not None and resets_at is None:
                warnings.append(f"Ignored an invalid Antigravity reset time for {bucket_id}.")
            windows.append({
                "provider": "antigravity",
                "quota_id": f"antigravity-quota-summary-{bucket_id}",
                "family": family,
                "title": f"{family_title} {title}",
                "window_minutes": minutes,
                "used_fraction": 1 - remaining if remaining is not None and not disabled else None,
                "remaining_fraction": remaining if not disabled else None,
                "resets_at": resets_at,
                # Provider prose is not required for accounting and can carry
                # identity in crafted exports. Reset timestamps are sufficient.
                "reset_description": None,
                "usage_known": remaining is not None and not disabled,
                "source": source,
                "sort_key": (0 if family == "gemini" else 1 if family == "claude-gpt" else 2, 0 if minutes == 300 else 1 if minutes == 10080 else 2, group_index, bucket_index),
            })
    windows.sort(key=lambda item: item.pop("sort_key"))
    return windows, warnings


def _model_configs(payload: dict[str, Any]) -> list[Any]:
    if isinstance(payload.get("clientModelConfigs"), list):
        return payload["clientModelConfigs"]
    status = payload.get("userStatus")
    cascade = status.get("cascadeModelConfigData") if isinstance(status, dict) else None
    return cascade.get("clientModelConfigs", []) if isinstance(cascade, dict) else []


def parse_model_quotas(payload: Any, source: str = "export") -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize GetUserStatus/GetCommandModelConfigs fallback responses."""
    if not isinstance(payload, dict) or not _valid_code(payload):
        return [], ["Antigravity model quota endpoint returned a non-success response."]
    windows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, config in enumerate(_model_configs(payload)):
        if not isinstance(config, dict) or not isinstance(config.get("quotaInfo"), dict):
            continue
        quota = config["quotaInfo"]
        model_or_alias = config.get("modelOrAlias")
        model = model_or_alias.get("model") if isinstance(model_or_alias, dict) else None
        model_id = _safe_identifier(model, f"model-{index + 1}")
        label = model_id
        raw_remaining = quota.get("remainingFraction")
        remaining = _fraction(raw_remaining)
        if raw_remaining is not None and remaining is None:
            warnings.append(f"Ignored an invalid Antigravity remaining fraction for {model_id}.")
        reset_raw = quota.get("resetTime")
        resets_at = _reset_time(reset_raw)
        if reset_raw is not None and resets_at is None:
            warnings.append(f"Ignored an invalid Antigravity reset time for {model_id}.")
        windows.append({
            "provider": "antigravity",
            "quota_id": f"antigravity-model-{model_id}",
            "family": _family(f"{label} {model_id}"),
            "title": label,
            "window_minutes": None,
            "used_fraction": 1 - remaining if remaining is not None else None,
            "remaining_fraction": remaining,
            "resets_at": resets_at,
            "reset_description": None,
            "usage_known": remaining is not None,
            "source": source,
        })
    return windows, warnings


def parse_export(payload: Any, source: str = "export") -> tuple[list[dict[str, Any]], list[str]]:
    windows, warnings = parse_quota_summary(payload, source)
    if windows:
        return windows, warnings
    fallback, fallback_warnings = parse_model_quotas(payload, source)
    return fallback, warnings + fallback_warnings


def load_exports(paths: Iterable[Path], max_files: int | None = None) -> ProbeResult:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("*.json"))
    readable: list[tuple[float, Path]] = []
    for path in set(files):
        try:
            readable.append((path.stat().st_mtime, path))
        except OSError:
            continue
    files = [path for _, path in sorted(readable, reverse=True)]
    if max_files:
        files = files[:max_files]
    windows: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            warnings.append("Skipped one malformed or unreadable Antigravity quota export.")
            continue
        parsed, parsed_warnings = parse_export(payload)
        warnings.extend(parsed_warnings)
        for window in parsed:
            # Files are newest-first: preserve the freshest observation when a
            # directory contains several snapshots of the same quota bucket.
            windows.setdefault(window["quota_id"], window)
    if not files:
        warnings.append("No Antigravity JSON quota export was found at the explicit path.")
    elif not windows:
        warnings.append("Antigravity export contained no recognized quota windows.")
    return ProbeResult(list(windows.values()), "export", list(dict.fromkeys(warnings)), len(files))


def _extract_flag(command: str, flag: str) -> str | None:
    match = re.search(rf"{re.escape(flag)}(?:=|\s+)([^\s]+)", command, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _process_kind(command: str) -> str | None:
    lower = command.lower()
    language_server = re.search(r"(^|[/\\])language(?:_|-)server(?:[_-][a-z0-9]+)*(?:\.exe)?(?:\s|$)", lower)
    antigravity = (
        ("--app_data_dir" in lower and "antigravity" in lower)
        or "antigravity.app/" in lower
        or "antigravity.app\\" in lower
        or "antigravity ide.app/" in lower
        or "antigravity ide.app\\" in lower
        or "/antigravity/" in lower
        or "\\antigravity\\" in lower
    )
    if language_server and antigravity:
        ide_markers = (
            "antigravity ide.app/", "antigravity ide.app\\", "--app_data_dir antigravity-ide",
            "--app_data_dir=antigravity-ide", "/extensions/antigravity/bin/language_server",
            "\\extensions\\antigravity\\bin\\language_server",
        )
        return "ide" if any(marker in lower for marker in ide_markers) else "app"
    if re.search(r"(^|[/\\])(antigravity-cli|antigravity_cli)(?:[\s/\\]|$)", lower):
        return "cli"
    if re.search(r"(^|[/\\])agy(?:\s|$)", lower):
        return "cli"
    return None


def parse_process_list(output: str) -> list[ProcessInfo]:
    results: list[ProcessInfo] = []
    for line in output.splitlines():
        match = re.match(r"\s*(\d+)\s+(.+)$", line)
        if not match:
            continue
        pid, command = int(match.group(1)), match.group(2)
        kind = _process_kind(command)
        if not kind:
            continue
        token = _extract_flag(command, "--csrf_token")
        if kind != "cli" and not token:
            continue
        extension_port_raw = _extract_flag(command, "--extension_server_port")
        extension_port = int(extension_port_raw) if extension_port_raw and extension_port_raw.isdigit() else None
        results.append(ProcessInfo(
            pid=pid,
            kind=kind,
            csrf_token=token or "",
            extension_port=extension_port,
            extension_csrf_token=_extract_flag(command, "--extension_server_csrf_token"),
        ))
    return results


def running_processes(timeout: float) -> list[ProcessInfo]:
    try:
        proc = subprocess.run(
            ["/bin/ps", "-ax", "-o", "pid=,command="],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_process_list(proc.stdout)


def listening_ports(pid: int, timeout: float) -> list[int]:
    lsof = next((path for path in ("/usr/sbin/lsof", "/usr/bin/lsof", shutil.which("lsof")) if path and Path(path).is_file()), None)
    if not lsof:
        return _proc_listening_ports(pid) if sys.platform.startswith("linux") else []
    try:
        proc = subprocess.run(
            [lsof, "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({int(value) for value in re.findall(r":(\d+)\s+\(LISTEN\)", proc.stdout) if 0 < int(value) <= 65535})


def _proc_listening_ports(pid: int, proc_root: Path = Path("/proc")) -> list[int]:
    """Linux fallback matching process socket inodes to its TCP tables."""
    process_root = proc_root / str(pid)
    inodes: set[str] = set()
    try:
        descriptors = list((process_root / "fd").iterdir())
    except OSError:
        return []
    for descriptor in descriptors:
        try:
            target = descriptor.readlink().as_posix()
        except OSError:
            continue
        match = re.fullmatch(r"socket:\[(\d+)\]", target)
        if match:
            inodes.add(match.group(1))
    ports: set[int] = set()
    for table in (process_root / "net" / "tcp", process_root / "net" / "tcp6"):
        try:
            lines = table.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            columns = line.split()
            if len(columns) <= 9 or columns[3] != "0A" or columns[9] not in inodes:
                continue
            try:
                port = int(columns[1].rsplit(":", 1)[1], 16)
            except (IndexError, ValueError):
                continue
            if 0 < port <= 65535:
                ports.add(port)
    return sorted(ports)


def endpoints(process: ProcessInfo, ports: Iterable[int]) -> list[Endpoint]:
    candidates: list[Endpoint] = []
    schemes = ("https", "http") if sys.platform.startswith("linux") else ("https",)
    if process.kind == "cli":
        candidates.extend(Endpoint(scheme, port, "", "local-cli") for port in ports for scheme in schemes)
    else:
        candidates.extend(Endpoint(scheme, port, process.csrf_token, f"local-{process.kind}") for port in ports for scheme in schemes)
        if process.extension_port:
            for token in (process.extension_csrf_token, process.csrf_token):
                if token:
                    candidates.append(Endpoint("http", process.extension_port, token, f"local-{process.kind}"))
    unique: list[Endpoint] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def request_json(endpoint: Endpoint, path: str, body: dict[str, Any], timeout: float) -> Any:
    if endpoint.scheme not in {"http", "https"} or not 0 < endpoint.port <= 65535:
        raise ValueError("invalid local endpoint")
    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        f"{endpoint.scheme}://127.0.0.1:{endpoint.port}{path}",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
            **({"X-Codeium-Csrf-Token": endpoint.csrf_token} if endpoint.csrf_token else {}),
        },
    )
    class RefuseRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
            return None

    handlers: list[Any] = [urllib.request.ProxyHandler({}), RefuseRedirects()]
    if endpoint.scheme == "https":
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        handlers.append(urllib.request.HTTPSHandler(context=context))
    opener = urllib.request.build_opener(*handlers)
    with opener.open(request, timeout=timeout) as response:
        if response.status != 200:
            raise urllib.error.HTTPError(request.full_url, response.status, "non-success", response.headers, None)
        if response.geturl() != request.full_url:
            raise ValueError("local endpoint redirected")
        return json.loads(response.read().decode("utf-8"))


def probe_local(
    timeout: float = 2.0,
    *,
    process_reader: Callable[[float], list[ProcessInfo]] = running_processes,
    port_reader: Callable[[int, float], list[int]] = listening_ports,
    requester: Callable[[Endpoint, str, dict[str, Any], float], Any] = request_json,
    clock: Callable[[], float] = time.monotonic,
) -> ProbeResult:
    """Probe already-running Antigravity processes; never start or authenticate one."""
    deadline = clock() + timeout
    processes = process_reader(timeout)
    if not processes:
        return ProbeResult([], "unavailable")
    last_warning = "Antigravity was running, but no recognized local quota endpoint responded."
    for process in processes:
        remaining = deadline - clock()
        if remaining <= 0:
            return ProbeResult([], "unavailable", ["Antigravity local quota probe timed out."])
        candidates = endpoints(process, port_reader(process.pid, remaining))
        for endpoint in candidates:
            requests = (
                (QUOTA_SUMMARY_PATH, {"forceRefresh": True}, parse_quota_summary),
                (USER_STATUS_PATH, {"metadata": {"ideName": "antigravity", "extensionName": "antigravity", "ideVersion": "unknown", "locale": "en"}}, parse_model_quotas),
                (MODEL_CONFIG_PATH, {"metadata": {"ideName": "antigravity", "extensionName": "antigravity", "ideVersion": "unknown", "locale": "en"}}, parse_model_quotas),
            )
            for path, body, parser in requests:
                remaining = deadline - clock()
                if remaining <= 0:
                    return ProbeResult([], "unavailable", ["Antigravity local quota probe timed out."])
                try:
                    payload = requester(endpoint, path, body, remaining)
                    windows, warnings = parser(payload, endpoint.source)
                except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
                    continue
                if windows:
                    return ProbeResult(windows, endpoint.source, warnings)
    return ProbeResult([], "unavailable", [last_warning])
