"""Unit tests for the fail-CLOSED config gate.

Each strict rule here is a real P20 finding from the reference build: the kill
switch that must be exactly "1", the DRY_RUN that fails toward observation, the
num_or that a config typo must not break, and the partition-seed guard.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import validate_config as vc  # noqa: E402


# ── num_or ───────────────────────────────────────────────────────────────────

def test_num_or_passes_valid_int():
    assert vc.num_or("5", 3) == 5


def test_num_or_falls_to_default_on_typo():
    assert vc.num_or("true", 3) == 3
    assert vc.num_or("01x", 3) == 3
    assert vc.num_or("", 3) == 3
    assert vc.num_or(None, 3) == 3


def test_num_or_clamps_to_minimum():
    assert vc.num_or("0", 45, minimum=1) == 1
    assert vc.num_or("3", 45, minimum=1) == 3


# ── kill switch (exactly "1") ────────────────────────────────────────────────

def test_kill_switch_enabled_exact_one():
    assert vc.kill_switch_enabled({"DISPATCH_ENABLED": "1"}) is True


def test_kill_switch_disabled_on_anything_else():
    assert vc.kill_switch_enabled({"DISPATCH_ENABLED": "0"}) is False
    assert vc.kill_switch_enabled({"DISPATCH_ENABLED": "true"}) is False
    assert vc.kill_switch_enabled({}) is False  # missing => disabled


def test_kill_switch_strips_whitespace():
    assert vc.kill_switch_enabled({"DISPATCH_ENABLED": " 1 "}) is True


# ── DRY_RUN (fails toward dry) ────────────────────────────────────────────────

def test_dry_run_live_only_on_exact_zero():
    assert vc.dry_run({"DRY_RUN": "0"}) is False


def test_dry_run_defaults_dry_and_rejects_typos():
    assert vc.dry_run({}) is True                 # unset => dry
    assert vc.dry_run({"DRY_RUN": "true"}) is True
    assert vc.dry_run({"DRY_RUN": "01"}) is True   # not exactly "0"
    assert vc.dry_run({"DRY_RUN": "1"}) is True


def test_resume_enabled_exact_one():
    assert vc.resume_enabled({"RESUME_ENABLED": "1"}) is True
    assert vc.resume_enabled({}) is False
    assert vc.resume_enabled({"RESUME_ENABLED": "0"}) is False


# ── env parsing ──────────────────────────────────────────────────────────────

def test_parse_env_basic_and_comments():
    text = "# a comment\nDISPATCH_ENABLED=1\nWIP_CAP=5  # inline comment\n\nLABEL=agent-ok\n"
    parsed = vc.parse_env(text)
    assert parsed["DISPATCH_ENABLED"] == "1"
    assert parsed["WIP_CAP"] == "5"
    assert parsed["LABEL"] == "agent-ok"


def test_parse_env_last_assignment_wins():
    assert vc.parse_env("DRY_RUN=1\nDRY_RUN=0\n")["DRY_RUN"] == "0"


def test_parse_env_skips_corrupt_key():
    # 'DISPATCH_ENABLED = 0' (spaces) is not a valid identifier assignment.
    parsed = vc.parse_env("DISPATCH ENABLED=0\n")
    assert "DISPATCH" not in parsed


def test_parse_env_quoted_value_keeps_hash():
    assert vc.parse_env('LABEL="a#b"\n')["LABEL"] == "a#b"


# ── partition-seed guard ─────────────────────────────────────────────────────

def test_partition_seed_ok_matching_tag():
    assert vc.partition_seed_ok(
        "/home/u/.config/loop-life", "/repo/config.env.life-vps.template", "life") is True


def test_partition_seed_rejects_mismatch():
    # a -life state dir seeded from the generic template = the double-dispatch footgun.
    assert vc.partition_seed_ok(
        "/home/u/.config/loop-life", "/repo/config.env.template", "life") is False


def test_partition_seed_unconstrained_without_tag():
    assert vc.partition_seed_ok("/home/u/.config/loop", "/repo/anything", "") is True


def test_partition_seed_nonpartitioned_dir_unconstrained():
    # a non -life dir is free to use any template even when a tag is configured.
    assert vc.partition_seed_ok("/home/u/.config/loop", "/repo/config.env.template", "life") is True


# ── validate() end-to-end ────────────────────────────────────────────────────

def test_validate_reports_coercion_warnings():
    raw = {"DISPATCH_ENABLED": "1", "WIP_CAP": "notanumber", "RUNNER_TIMEOUT_MIN": "0"}
    result = vc.validate(raw)
    assert result["enabled"] is True
    assert result["knobs"]["WIP_CAP"] == 3           # default
    assert result["knobs"]["RUNNER_TIMEOUT_MIN"] == 1  # clamped up from 0
    assert any("WIP_CAP" in w for w in result["warnings"])


def test_validate_flags_always_quiet_window():
    raw = {"DISPATCH_ENABLED": "1", "ACTIVE_START": "23", "ACTIVE_END": "7"}
    result = vc.validate(raw)
    assert any("quiet hours" in w for w in result["warnings"])


def test_validate_disabled_config():
    assert vc.validate({"DISPATCH_ENABLED": "0"})["enabled"] is False
