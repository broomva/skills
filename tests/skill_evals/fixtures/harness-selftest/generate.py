#!/usr/bin/env python3
"""Regenerate the committed harness self-test fixtures, bound to skill/SKILL.md.

These transcripts are SYNTHETIC: hand-authored stream-json, no model involved.
Every meta sidecar says so (``"provenance": "synthetic"``), and the runner refuses
to grade them unless ``--allow-synthetic-fixtures`` is passed. They exist so CI
grades a real prompt set end to end — trigger detection, the input-inspecting
outcome checks, the positive-rate gate and the artifact binding — instead of only
asserting that an *empty* fixture set fails.

They are evidence about the HARNESS. They are not evidence about any skill's real
trigger behaviour; only ``--record`` against the live CLI produces that.

Run after any edit to ``skill/SKILL.md`` or ``evals/prompts.json``:

    python3 tests/skill_evals/fixtures/harness-selftest/generate.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "scripts"))

from skill_evals import runner as R  # noqa: E402

SKILL = "harness-selftest"


# -- stream-json builders (shape verified against CLI 2.1.220) ----------------


def ev_init(skills=(SKILL,)):
    return {"type": "system", "subtype": "init", "skills": list(skills),
            "cwd": "/tmp/skilleval-ws", "model": "claude-haiku",
            "tools": ["Read", "Write", "Bash", "Glob", "WebFetch", "Skill"]}


def ev_text(text, parent=None):
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def ev_tool_use(name, tool_input, tid):
    return {"type": "assistant", "parent_tool_use_id": None,
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": tid, "name": name, "input": tool_input,
                 "caller": {"type": "direct"}}]}}


def ev_tool_result(tid, command_name):
    return {"type": "user",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid,
                 "content": f"Launching skill: {command_name}\n"
                            f"Base directory for this skill: "
                            f"/tmp/skilleval-ws/.claude/skills/{command_name}"}]},
            "tool_use_result": {"success": True, "commandName": command_name}}


def ev_result(text, cost, duration, turns):
    return {"type": "result", "subtype": "success", "is_error": False, "result": text,
            "total_cost_usd": cost, "duration_ms": duration, "num_turns": turns,
            "permission_denials": []}


POS1_ANSWER = (
    "I pulled the full text of the paper rather than the abstract, and verified its "
    "central claim against the primary source it cites. It overlaps with the existing "
    "harness in our workspace: both treat a recorded run as evidence only when it is "
    "bound to the artifact it was recorded against. Wrote the finding to "
    "research/notes/2026-07-28-harness-selftest.md.\n"
    "Next steps:\n"
    "1. bind the fixtures to the artifact hash\n"
    "2. gate the positive arm separately from the aggregate\n"
    "3. re-record once the description settles"
)

POS2_ANSWER = (
    "The spec is a two-plane design and the repo layout confirms it: README.md and "
    "src/ hold the runtime, docs/ holds the contract. That maps onto our existing "
    "pipeline more cleanly than the current wiring does. Recorded the comparison in "
    "docs/notes/spec-landing.md.\n"
    "Next steps:\n"
    "1. reconcile the two vocabularies\n"
    "2. decide whether the second plane earns its keep"
)

NEG1_ANSWER = (
    "The dereference happens because the parser returns None for an empty buffer and "
    "the caller indexes it directly. Guarded the empty case and added a regression "
    "test; the suite is green."
)

NEG2_ANSWER = (
    "- Adds a retry with exponential backoff on the upload path\n"
    "- Drops the deprecated v1 endpoint\n"
    "- Fixes a timezone bug in the daily rollup"
)


def positive_01():
    """Fires on turn 1, then does artifact-touching work."""
    return [
        ev_init(),
        ev_tool_use("Skill", {"skill": SKILL, "args": ""}, "toolu_01"),
        ev_tool_result("toolu_01", SKILL),
        ev_tool_use("WebFetch", {"url": "https://example.invalid/paper.pdf",
                                 "prompt": "extract the full argument"}, "toolu_02"),
        ev_text("Fetched the paper; reading the whole thing before I judge it."),
        ev_tool_use("Write", {"file_path": "research/notes/2026-07-28-harness-selftest.md",
                              "content": "# finding\n"}, "toolu_03"),
        ev_text(POS1_ANSWER),
        ev_result(POS1_ANSWER, 0.0241, 51200, 7),
    ]


def positive_02():
    """Fires on turn 5. Outcomes, not paths: this must score exactly like turn 1."""
    return [
        ev_init(),
        ev_text("Let me look at what is actually in the repo before I answer."),
        ev_tool_use("Glob", {"pattern": "docs/inbox/*.md"}, "toolu_01"),
        ev_tool_use("Bash", {"command": "ls -la docs/inbox && git ls-files | head -40"},
                    "toolu_02"),
        ev_text("Now I have the shape of it."),
        ev_tool_use("Skill", {"skill": SKILL, "args": ""}, "toolu_03"),
        ev_tool_result("toolu_03", SKILL),
        ev_tool_use("Read", {"file_path": "docs/inbox/example-spec.md"}, "toolu_04"),
        ev_text(POS2_ANSWER),
        ev_result(POS2_ANSWER, 0.0198, 43900, 9),
    ]


def negative_01():
    return [
        ev_init(),
        ev_tool_use("Read", {"file_path": "parser.py"}, "toolu_01"),
        ev_tool_use("Edit", {"file_path": "parser.py", "old_string": "return None",
                             "new_string": "return b\"\""}, "toolu_02"),
        ev_text(NEG1_ANSWER),
        ev_result(NEG1_ANSWER, 0.0091, 18400, 4),
    ]


def negative_02():
    return [
        ev_init(),
        ev_tool_use("Read", {"file_path": "CHANGELOG.md"}, "toolu_01"),
        ev_text(NEG2_ANSWER),
        ev_result(NEG2_ANSWER, 0.0064, 11200, 3),
    ]


#: Per-trial jitter, so the three trials of a case are not byte-identical — a
#: distribution of three copies of one file is still an anecdote.
BUILDERS = {
    "positive-01": positive_01,
    "positive-02": positive_02,
    "negative-01": negative_01,
    "negative-02": negative_02,
}


def jitter(events, trial):
    """Vary cost/duration/turns per trial without changing what is graded."""
    out = json.loads(json.dumps(events))
    for ev in out:
        if ev.get("type") == "result":
            ev["total_cost_usd"] = round(ev["total_cost_usd"] * (1 + 0.07 * (trial - 2)), 6)
            ev["duration_ms"] = int(ev["duration_ms"] * (1 + 0.11 * (trial - 2)))
    return out


def main() -> int:
    fingerprint = R.skill_fingerprint(HERE / "skill")
    prompt_set = R.load_prompt_set(HERE / "evals" / "prompts.json")
    written = 0
    for case in prompt_set.cases:
        builder = BUILDERS[case.id]
        case_dir = HERE / "cases" / case.id
        case_dir.mkdir(parents=True, exist_ok=True)
        for trial in (1, 2, 3):
            events = jitter(builder(), trial)
            (case_dir / f"trial-{trial:02d}.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
            meta = {
                "meta_version": R.FIXTURE_META_VERSION,
                "provenance": R.PROVENANCE_SYNTHETIC,
                "skill": SKILL,
                "case_id": case.id,
                "trial": trial,
                "exit_code": 0,
                "stderr": "",
                "wall_ms": events[-1]["duration_ms"],
                "model": R.DEFAULT_MODEL,
                "cli_version": R.EXPECTED_CLI_VERSION,
                "prompt_sha256": hashlib.sha256(case.prompt.encode("utf-8")).hexdigest(),
                "skill_md_sha256": fingerprint["skill_md_sha256"],
                "description_sha256": fingerprint["description_sha256"],
                "recorded_at": "2026-07-28T00:00:00Z",
                "note": "SYNTHETIC — hand-authored by generate.py; no model produced this.",
            }
            (case_dir / f"trial-{trial:02d}.meta.json").write_text(
                json.dumps(meta, indent=2) + "\n", encoding="utf-8")
            written += 1
    print(f"wrote {written} synthetic trials bound to "
          f"skill_md={fingerprint['skill_md_sha256'][:12]} "
          f"description={fingerprint['description_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
