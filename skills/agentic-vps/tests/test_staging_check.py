"""Unit tests for the agentic-vps lockout-safety staging checker (pure core)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import staging_check as sc  # noqa: E402


SAFE_PLAN = [
    "snapshot",
    "oob_console_confirmed",
    "vpn_up",
    "vpn_ssh_verified",
    "allow_vpn_ssh",
    "close_public_ssh",
]


def test_safe_plan_passes():
    res = sc.check_sequence(SAFE_PLAN)
    assert res["ok"] is True
    assert res["violations"] == []


def test_close_before_vpn_verified_fails():
    plan = ["snapshot", "oob_console_confirmed", "vpn_up", "allow_vpn_ssh",
            "close_public_ssh", "vpn_ssh_verified"]
    res = sc.check_sequence(plan)
    assert res["ok"] is False
    assert any("VERIFIED before closing" in v for v in res["violations"])


def test_close_without_snapshot_fails():
    plan = ["vpn_up", "vpn_ssh_verified", "allow_vpn_ssh",
            "oob_console_confirmed", "close_public_ssh"]
    res = sc.check_sequence(plan)
    assert res["ok"] is False
    assert any("snapshot must precede" in v for v in res["violations"])


def test_close_without_oob_console_fails():
    plan = ["snapshot", "vpn_up", "vpn_ssh_verified", "allow_vpn_ssh", "close_public_ssh"]
    res = sc.check_sequence(plan)
    assert res["ok"] is False
    assert any("out-of-band console" in v for v in res["violations"])


def test_verify_before_vpn_up_fails():
    plan = ["snapshot", "oob_console_confirmed", "vpn_ssh_verified", "vpn_up",
            "allow_vpn_ssh", "close_public_ssh"]
    res = sc.check_sequence(plan)
    assert res["ok"] is False
    assert any("AFTER it is brought up" in v for v in res["violations"])


def test_plan_without_closing_public_is_safe():
    # provisioning that never closes public SSH has no lockout risk
    res = sc.check_sequence(["snapshot", "vpn_up", "vpn_ssh_verified"])
    assert res["ok"] is True


def test_unknown_step_flagged():
    res = sc.check_sequence(["snapshot", "frobnicate", "vpn_up"])
    assert res["ok"] is False
    assert "frobnicate" in res["unknown_steps"]


def test_free_text_after_colon_ignored():
    res = sc.check_sequence([
        "snapshot: hostinger VPS_createSnapshotV1",
        "oob_console_confirmed: browser terminal",
        "vpn_up: tailscale up --hostname=box",
        "vpn_ssh_verified: ssh agent@100.x in 2nd session",
        "allow_vpn_ssh: ufw allow in on tailscale0",
        "close_public_ssh: ufw delete allow OpenSSH + edge fw",
    ])
    assert res["ok"] is True
