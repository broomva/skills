"""Every CLI surface must be documented where an agent will actually find it.

An undocumented flag is a flag no agent ever uses, and the failure is silent in
both directions: the code works, the docs are clean, and the capability simply
never gets reached. That is not something review catches reliably — it catches
what is *written*, not what is missing — so it is asserted here instead.

Two surfaces, because an agent reaches the tool two ways:

  SKILL.md   what it reads when the skill loads, without shelling out
  USAGE      what `--help` prints when it does

The extractors below read the real source, so adding a flag fails this file
until it is documented. `test_the_extractors_can_fail` is the positive control:
without it, a broken extractor that returns nothing reports a clean pass, which
is indistinguishable from full coverage.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_HOOK = _ROOT / "scripts" / "talkback-hook.py"
_TALKBACK = _ROOT / "scripts" / "talkback.py"
_SKILL = _ROOT / "SKILL.md"

#: `-h` is universal and needs no prose; everything else earns its line.
EXEMPT = {"-h"}


def _hook_commands(source: str) -> set[str]:
    """Flags the hook's own dispatcher branches on."""
    return set(re.findall(r'cmd == "(--[a-z][\w-]*)"', source))


def _hook_options(source: str) -> set[str]:
    """Flags read as options or booleans out of argv."""
    return set(re.findall(r'_opt\(argv, "(--[a-z][\w-]*)"\)', source)) | set(
        re.findall(r'_flag\(argv, "(--[a-z][\w-]*)"\)', source)
    )


def _argparse_flags(source: str) -> set[str]:
    """Every option string of every add_argument call, long and short."""
    flags: set[str] = set()
    for block in re.findall(r"add_argument\((.*?)\)\n", source, re.S):
        flags |= set(re.findall(r'"(-{1,2}[a-z][\w-]*)"', block))
    return flags


def _env_vars(source: str) -> set[str]:
    return set(re.findall(r'environ\.get\("([A-Z][A-Z_]*)"', source))


@pytest.fixture(scope="module")
def sources():
    return {
        "hook": _HOOK.read_text(),
        "talkback": _TALKBACK.read_text(),
        "skill": _SKILL.read_text(),
    }


@pytest.fixture(scope="module")
def usage():
    spec = importlib.util.spec_from_file_location("talkback_hook_for_docs", _HOOK)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["talkback_hook_for_docs"] = mod
    spec.loader.exec_module(mod)
    return mod.USAGE


# --------------------------------------------------------------------------
# the extractors must be capable of finding something
# --------------------------------------------------------------------------

def test_the_extractors_can_fail(sources):
    """Control: an extractor that always returns nothing would pass everything."""
    assert _hook_commands(sources["hook"]) >= {"--on", "--off", "--status", "--install"}
    assert _hook_options(sources["hook"]) >= {"--global", "--all", "--backend"}
    assert _argparse_flags(sources["talkback"]) >= {"-b", "--backend", "--fast", "--quota"}
    assert _env_vars(sources["hook"] + sources["talkback"]) >= {"TALKBACK_HOME"}

    # ...and an undocumented flag must actually be reported as missing.
    fake = 'if cmd == "--undocumented-flag":\n    pass\n'
    assert "--undocumented-flag" in _hook_commands(fake)
    assert "--undocumented-flag" not in sources["skill"]


# --------------------------------------------------------------------------
# SKILL.md — what the agent reads without shelling out
# --------------------------------------------------------------------------

def test_every_hook_command_is_in_skill_md(sources):
    missing = sorted(
        f for f in _hook_commands(sources["hook"]) - EXEMPT if f not in sources["skill"]
    )
    assert not missing, f"undocumented in SKILL.md: {missing}"


def test_every_hook_option_is_in_skill_md(sources):
    missing = sorted(
        f for f in _hook_options(sources["hook"]) - EXEMPT if f not in sources["skill"]
    )
    assert not missing, f"undocumented in SKILL.md: {missing}"


def test_every_talkback_flag_is_in_skill_md(sources):
    missing = sorted(
        f for f in _argparse_flags(sources["talkback"]) - EXEMPT if f not in sources["skill"]
    )
    assert not missing, f"undocumented in SKILL.md: {missing}"


def test_every_env_var_is_in_skill_md(sources):
    envs = _env_vars(sources["hook"] + sources["talkback"])
    missing = sorted(e for e in envs if e not in sources["skill"])
    assert not missing, f"undocumented in SKILL.md: {missing}"


# --------------------------------------------------------------------------
# --help — what the agent gets when it does shell out
# --------------------------------------------------------------------------

def test_every_hook_command_is_in_usage(sources, usage):
    missing = sorted(f for f in _hook_commands(sources["hook"]) if f not in usage)
    assert not missing, f"missing from --help: {missing}"


def test_every_hook_option_is_in_usage(sources, usage):
    missing = sorted(f for f in _hook_options(sources["hook"]) - EXEMPT if f not in usage)
    assert not missing, f"missing from --help: {missing}"


def test_usage_points_at_the_sibling_cli(usage):
    """The two scripts do different jobs; --help must not be a dead end."""
    assert "talkback.py" in usage


def test_help_prints_both_the_rationale_and_the_usage(sources):
    """`--help` is the docstring plus USAGE, not one or the other."""
    assert "print(__doc__)" in sources["hook"]
    assert "print(USAGE)" in sources["hook"]


# --------------------------------------------------------------------------
# the parts an agent gets wrong without being told
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "phrase",
    [
        "talk mode on",          # the trigger -> command table exists
        "stop talking",
        "--off --all",
        "restart",               # registration takes effect next session
        "does not survive",      # talk mode is per session, re-enable after /clear
    ],
)
def test_skill_md_tells_the_agent_how_to_drive_it(sources, phrase):
    assert phrase in sources["skill"].lower(), f"agent guidance missing: {phrase!r}"
