"""Unit tests for the agentic-vps verification gate (pure core)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import verify  # noqa: E402


def _good_facts():
    return {
        "agent_uid": 1000,
        "agent_passwordless_sudo": True,
        "slice_memory_max": "7516192768",
        "slice_tasks_max": "8192",
        "tailscale_ip": "100.82.195.109",
        "public_ssh_open": False,
        "secrets_in_env": [],
        "snapshot_exists": True,
        "claude_default_mode": "bypassPermissions",
    }


def test_fully_compliant_box_passes():
    res = verify.evaluate(_good_facts())
    assert res["ok"] is True
    assert res["failed_required"] == []


def test_root_agent_fails_required():
    f = _good_facts(); f["agent_uid"] = 0
    res = verify.evaluate(f)
    assert res["ok"] is False
    assert "agent_nonroot" in res["failed_required"]


def test_public_ssh_open_fails():
    f = _good_facts(); f["public_ssh_open"] = True
    res = verify.evaluate(f)
    assert res["ok"] is False
    assert "public_ssh_closed" in res["failed_required"]


def test_unknown_public_ssh_state_fails_required():
    # None (couldn't probe) must NOT pass the closed gate
    f = _good_facts(); f["public_ssh_open"] = None
    res = verify.evaluate(f)
    assert "public_ssh_closed" in res["failed_required"]


def test_secret_in_env_fails():
    f = _good_facts(); f["secrets_in_env"] = ["ANTHROPIC_API_KEY"]
    res = verify.evaluate(f)
    assert res["ok"] is False
    assert "no_secrets_in_env" in res["failed_required"]


def test_missing_tailscale_fails():
    f = _good_facts(); f["tailscale_ip"] = ""
    res = verify.evaluate(f)
    assert "tailscale_up" in res["failed_required"]


def test_missing_caps_fails():
    f = _good_facts(); f["slice_tasks_max"] = ""
    res = verify.evaluate(f)
    assert "resource_caps" in res["failed_required"]


def test_recommended_gate_does_not_fail_overall():
    # missing snapshot + claude config are recommended -> overall still ok
    f = _good_facts(); f["snapshot_exists"] = False; f["claude_default_mode"] = ""
    res = verify.evaluate(f)
    assert res["ok"] is True
    keys = {g["key"]: g["ok"] for g in res["gates"]}
    assert keys["snapshot_exists"] is False
    assert keys["claude_config"] is False


# ---- find_secrets_in_env ----

def test_find_secrets_detects_export_and_plain():
    dump = "PATH=/usr/bin\nexport GITHUB_TOKEN=ghp_xxx\nANTHROPIC_API_KEY=sk-ant-yyy\n"
    found = verify.find_secrets_in_env(dump)
    assert "GITHUB_TOKEN" in found
    assert "ANTHROPIC_API_KEY" in found


def test_find_secrets_ignores_comments():
    dump = "# ANTHROPIC_API_KEY=not-real-just-a-comment\nPATH=/usr/bin\n"
    assert verify.find_secrets_in_env(dump) == []


def test_find_secrets_clean_env():
    assert verify.find_secrets_in_env("PATH=/usr/bin\nHOME=/home/agent\n") == []


# ---- classify_public_ssh: the perimeter probe must FAIL CLOSED ----

def test_classify_rc0_is_open():
    assert verify.classify_public_ssh(0, "") is True


def test_classify_timeout_macos_is_closed():
    assert verify.classify_public_ssh(255, "ssh: connect to host 1.2.3.4 port 22: Operation timed out") is False


def test_classify_timeout_linux_is_closed():
    assert verify.classify_public_ssh(255, "ssh: connect to host 1.2.3.4 port 22: Connection timed out") is False


def test_classify_refused_is_closed():
    assert verify.classify_public_ssh(255, "ssh: connect to host 1.2.3.4 port 22: Connection refused") is False


def test_classify_no_route_is_closed():
    assert verify.classify_public_ssh(255, "ssh: connect to host 1.2.3.4 port 22: No route to host") is False


def test_classify_permission_denied_is_open():
    # auth reached -> TCP connected -> port OPEN
    assert verify.classify_public_ssh(255, "agent@1.2.3.4: Permission denied (publickey).") is True


def test_classify_host_key_changed_is_open():
    # reviewer's false-negative case: reachable but host key mismatch -> must be OPEN
    assert verify.classify_public_ssh(255, "Host key verification failed.") is True


def test_classify_connection_closed_by_remote_is_open():
    assert verify.classify_public_ssh(255, "Connection closed by remote host") is True


def test_classify_kex_error_is_open():
    assert verify.classify_public_ssh(255, "kex_exchange_identification: read: Connection reset") is True


def test_classify_too_many_auth_is_open():
    assert verify.classify_public_ssh(255, "Received disconnect: Too many authentication failures") is True


def test_classify_unknown_defaults_open():
    # unknown stderr with nonzero rc -> assume OPEN (fail closed for a security gate)
    assert verify.classify_public_ssh(255, "some unexpected ssh error") is True
