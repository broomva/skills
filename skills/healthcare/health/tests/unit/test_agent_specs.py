"""Authored-agent spec guard.

The skill ships its reasoning layer as data — `agents/<name>.md` with Claude
Code subagent frontmatter — and `install.sh` links those files into
`~/.claude/agents/`. A malformed spec fails silently at the harness (the agent
just never appears), so the contract is pinned here instead.

Frontmatter is parsed with the stdlib: PyYAML is not a runtime or dev
dependency of this package (only `types-PyYAML`, for mypy).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parents[2]  # skills/healthcare/health/
_AGENTS_DIR = _SKILL_ROOT / "agents"

# `health` is the CLI the agents are built to wield; without Bash they cannot
# reach it and the whole "skill as substrate, agent as reasoning layer" split
# collapses.
_REQUIRED_TOOL = "Bash"


def _agent_files() -> list[Path]:
    return sorted(_AGENTS_DIR.glob("*.md"))


def _frontmatter(text: str) -> dict[str, str]:
    """Parse a `---` fenced YAML frontmatter block into {key: raw_value}.

    Handles inline values (`name: x`) and folded/indented continuations
    (`description: >` + indented lines), which is all these specs use.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]

    fields: dict[str, list[str]] = {}
    current: str | None = None
    for line in block.splitlines():
        if not line.strip():
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if match and not line.startswith((" ", "\t")):
            key: str = match.group(1)
            inline = match.group(2).strip()
            current = key
            # `>` / `|` introduce a folded block; the value is the continuation.
            fields[key] = [] if inline in {">", "|", ">-", "|-"} else [inline]
        elif current is not None:
            fields[current].append(line.strip())
    return {key: " ".join(parts).strip() for key, parts in fields.items()}


def test_agents_dir_is_present_and_populated() -> None:
    """The skill must ship at least one agent — that is the healthOS keystone."""
    assert _AGENTS_DIR.is_dir(), f"missing agents dir at {_AGENTS_DIR}"
    assert _agent_files(), "agents/ contains no *.md specs"


def test_health_analyst_is_shipped() -> None:
    """The workhorse agent is a blessed name — install.sh + docs reference it."""
    names = {p.stem for p in _agent_files()}
    assert "health-analyst" in names, f"health-analyst missing; found {sorted(names)}"


@pytest.mark.parametrize("agent_path", _agent_files(), ids=lambda p: p.stem)
def test_agent_spec_is_valid(agent_path: Path) -> None:
    """Each spec parses and satisfies the Claude Code subagent contract."""
    text = agent_path.read_text(encoding="utf-8")
    fm = _frontmatter(text)
    assert fm, f"{agent_path.name}: missing or unclosed `---` frontmatter"

    # `name` is the invocation handle (subagent_type) and MUST match the
    # filename, since the file is linked into ~/.claude/agents/ by basename.
    assert fm.get("name") == agent_path.stem, (
        f"{agent_path.name}: frontmatter name={fm.get('name')!r} "
        f"does not match filename stem {agent_path.stem!r}"
    )

    # `description` drives auto-delegation — an empty one means the agent is
    # effectively unreachable without being named explicitly.
    description = fm.get("description", "")
    assert len(description) >= 40, (
        f"{agent_path.name}: description too short to route on ({len(description)} chars)"
    )

    tools = fm.get("tools", "")
    assert _REQUIRED_TOOL in tools, (
        f"{agent_path.name}: tools={tools!r} must include {_REQUIRED_TOOL} "
        "(the agent reaches data through the `health` CLI)"
    )

    # The body after the frontmatter becomes the system prompt.
    body = text[text.find("\n---", 3) + 4 :].strip()
    assert len(body) >= 200, f"{agent_path.name}: instructions body is too thin"


@pytest.mark.parametrize("agent_path", _agent_files(), ids=lambda p: p.stem)
def test_agent_reaches_data_only_through_the_cli(agent_path: Path) -> None:
    """Agents must not be told to bypass the skill (direct DB/Garmin access).

    The architecture is: skill = retrieval substrate, agent = reasoning layer.
    An agent instructed to read the SQLite store or call Garmin directly would
    duplicate ingest and skip the typed/raw contracts.
    """
    body = agent_path.read_text(encoding="utf-8").lower()
    for forbidden in ("sqlite3 ", "connectapi", "garth.", "garmin.com"):
        assert forbidden not in body, (
            f"{agent_path.name}: instructs direct access via {forbidden!r}; "
            "agents must go through the `health` CLI"
        )
