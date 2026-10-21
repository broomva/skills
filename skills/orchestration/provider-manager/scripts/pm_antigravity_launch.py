"""Launch the registered Antigravity ACP binary in a thread's pinned account profile.

For T3 generic ACP providers only. Discovery probes without a caller context fail closed;
configure explicit custom models. The registered binary fingerprint must bind a verified
no-fork ACP release (official 1.3.0), because this launcher never proxies ACP messages.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pm_antigravity


class LaunchError(RuntimeError):
    pass


def _structured(result):
    if not isinstance(result, dict) or result.get("isError"):
        raise LaunchError("T3 rejected the launcher context request")
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    contents = result.get("content", [])
    if not isinstance(contents, list):
        raise LaunchError("T3 returned malformed launcher context content")
    for content in contents:
        if isinstance(content, dict) and content.get("type") == "text":
            try:
                value = json.loads(content["text"])
            except (KeyError, TypeError, ValueError):
                continue
            if isinstance(value, dict):
                return value
    return result


def t3_call(tool, arguments, environment):
    node = environment.get("T3_ACP_MCP_NODE")
    if not node or not environment.get("T3_ACP_MCP_ENDPOINT") or not environment.get("T3_ACP_MCP_AUTHORIZATION"):
        raise LaunchError("T3 thread MCP context is required; account selection was not changed")
    command = [node]
    if environment.get("T3_ACP_MCP_ENTRYPOINT"):
        command.append(environment["T3_ACP_MCP_ENTRYPOINT"])
    command.extend(["acp-mcp-call", tool, json.dumps(arguments)])
    try:
        completed = subprocess.run(command, env=dict(environment, ELECTRON_RUN_AS_NODE="1"),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if completed.returncode:
            raise LaunchError("T3 context request failed; account selection was not changed")
        return _structured(json.loads(completed.stdout))
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise LaunchError("Cannot verify the T3 thread context") from exc


def context(environment):
    capability = t3_call("orchestrator_capabilities", {}, environment)
    thread_id = capability.get("parentThreadId")
    model = capability.get("inheritedModel")
    provider = capability.get("inheritedProviderInstanceId")
    if not all(isinstance(value, str) and value.strip() for value in (thread_id, model, provider)):
        raise LaunchError("Launcher requires a bound T3 thread, provider and model")
    detail = t3_call("t3_thread_read", {"threadId": thread_id, "limit": 1,
                     "runLimit": 1, "maxCharsPerItem": 1}, environment)
    thread = detail.get("thread")
    if (not isinstance(thread, dict) or thread.get("threadId") != thread_id or
            thread.get("model") != model or thread.get("providerInstanceId") != provider):
        raise LaunchError("T3 thread identity or model changed during launch")
    count = thread.get("runCount")
    items = thread.get("itemCount")
    if (isinstance(count, bool) or not isinstance(count, int) or count < 1 or
            isinstance(items, bool) or not isinstance(items, int) or items < 0):
        raise LaunchError("Cannot determine whether the T3 thread is new")
    if thread.get("relationshipToParent") == "fork":
        raise LaunchError("Antigravity ACP 1.3.0 does not support session forks")
    # Imported/history-bearing threads can have only one local run. They still
    # require an explicit pin instead of silently receiving a different account.
    return "t3:%s:%s" % (provider, thread_id), model, count > 1 or items > 1


def child_environment(entry, environment):
    try:
        profile = Path(entry["profile"])
        binary = Path(entry["binary"])
        if (not profile.is_absolute() or profile.resolve(strict=True) != profile or
                not profile.is_dir() or not binary.is_absolute() or
                binary.resolve(strict=True) != binary or not binary.is_file() or
                not os.access(binary, os.X_OK) or binary == Path(__file__).resolve()):
            raise LaunchError("Pinned Antigravity executable or profile is unavailable")
        harness = binary.parent / "localharness_external"
        if (not harness.is_file() or harness.resolve(strict=True) != harness or
                not os.access(harness, os.X_OK)):
            raise LaunchError("The matching Antigravity ACP harness is unavailable")
        token = profile / "antigravity-acp" / "acp_token.json"
        if not token.is_file() or token.resolve(strict=True) != token:
            raise LaunchError("Pinned Antigravity profile has no private credential file")
        settings = json.loads((token.parent / "settings.json").read_text())
        if not isinstance(settings, dict) or settings.get("auth", {}).get("type") != "oauth-personal":
            raise LaunchError("Pinned Antigravity profile must use Google account authentication")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise LaunchError("Cannot validate the pinned Antigravity profile") from exc
    # Match T3's native Antigravity environment isolation; ambient API keys must
    # never replace a subscription account selected by provider-manager.
    removed = {"GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
               "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GOOGLE_CLOUD_QUOTA_PROJECT",
               "GOOGLE_GENAI_USE_VERTEXAI", "GCLOUD_PROJECT", "CLOUDSDK_CORE_PROJECT",
               "AGY_ACP_CCPA_PROJECT", "AGY_ACP_ENABLE_OAUTH", "GEMINI_HOME",
               "AGY_ACP_FORCE_FILE_STORAGE", "ANTIGRAVITY_HARNESS_PATH", "BROWSER"}
    env = {key: value for key, value in environment.items() if key.upper() not in removed}
    env.update(GEMINI_HOME=str(profile), AGY_ACP_FORCE_FILE_STORAGE="1",
               ANTIGRAVITY_HARNESS_PATH=str(harness), BROWSER="/usr/bin/false",
               PYTHONUNBUFFERED="1")
    return str(binary), env


def launch(arguments=(), environment=None):
    environment = dict(os.environ if environment is None else environment)
    key, model, existing = context(environment)
    entry = pm_antigravity.pin_session(key, model, require_existing=existing)
    binary, env = child_environment(entry, environment)
    os.execve(binary, [binary, *arguments], env)


def main():
    try:
        launch(sys.argv[1:])
    except (LaunchError, pm_antigravity.AntigravityError, OSError):
        # Native MCP replies and OAuth-related exception bodies stay private.
        print("antigravity-account: verified thread/account context unavailable; launch refused", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
