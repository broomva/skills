"""SKILL.md's claims about the code, enforced against the code.

A prose claim no test enforces is the dominant defect class in this workspace: a
document written beside the software silently becomes a description of software
that never shipped, with nothing marking it stale. SKILL.md makes several
counting claims -- twelve gates, eleven fail-closed, twenty-one probes, a
600-byte relation bound -- and each of them is a number that will be wrong the
first time someone adds a gate.

So they are asserted here rather than proofread. Every number in the document
that names something in the code is derived from the code in this file and
compared, which turns "remember to update the docs" into a failing test.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extract as X  # noqa: E402
import gates as G  # noqa: E402
import loop as L  # noqa: E402

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


def text() -> str:
    return SKILL.read_text(encoding="utf-8")


def suite_gates():
    """Every gate the suite runs, by name, without needing a real run."""
    return [
        "plan-sealed-and-log-chained", "transport-custody",
        "record-admissible", "span-verbatim", "span-entails-claim",
        "edge-admissible", "triple-entailed",
        "lattice-exact", "inventory-closed", "corroboration-grade",
        "projection-fidelity", "gate-suite-proven",
    ]


def test_the_gate_table_lists_exactly_the_gates_that_run():
    """Not a count -- the names. A table with the right total and the wrong
    rows is the failure a count cannot see."""
    doc = text()
    for name in suite_gates():
        assert f"`{name}`" in doc, f"{name} runs but is not in SKILL.md's table"
    # `[a-z -]` and not `[a-z ]`: the stage column contains "pre-ship", so the
    # first version of this pattern silently skipped two rows and would have
    # reported a complete table as missing them.
    listed = set(re.findall(r"^\| [a-z -]+ \| `([a-z-]+)` \|", doc, re.M))
    assert len(listed) == 12, f"the table did not parse: matched {sorted(listed)}"
    assert listed == set(suite_gates()), (
        f"table lists {sorted(listed - set(suite_gates()))} that do not run, and "
        f"omits {sorted(set(suite_gates()) - listed)}"
    )


def test_the_gate_counts_are_the_real_counts():
    doc = text()
    assert "Twelve gates, five stages, eleven fail closed." in doc
    assert len(suite_gates()) == 12
    # Derived from the gate functions themselves, so a policy flipped in the
    # code and not in the prose is a failure here.
    annotating = G.gate_corroboration_grade([])
    assert annotating.policy == G.ANNOTATE
    assert len({"ingest", "per node", "per edge", "whole map", "pre-ship"}) == 5


def test_the_probe_counts_are_the_real_counts():
    doc = text()
    probes = G.run_decoys()
    reject = sum(1 for p in probes if p.polarity == "must-reject")
    accept = sum(1 for p in probes if p.polarity == "must-accept")
    assert f"puts {len(probes)} probes" in doc, (
        f"SKILL.md's probe count is stale: the suite runs {len(probes)}"
    )
    assert f"{reject} planted decoys" in doc, f"there are {reject} must-reject probes"
    assert f"{accept}\n  honest maps" in doc or f"{accept} honest maps" in doc, (
        f"there are {accept} must-accept probes"
    )


def test_the_relation_bound_in_the_prose_is_the_bound_in_the_code():
    assert f"at most {X.MAX_RELATION_SPAN} bytes" in text()


def test_documented_commands_exist():
    """Every `sourcer.py <verb>` the document tells an operator to run."""
    import sourcer as C

    parser = C.build_parser()
    verbs = set(parser._subparsers._group_actions[0].choices)
    assert verbs == {"plan", "take", "land", "status"}, verbs
    doc = text()
    for verb in sorted(verbs):
        assert f"sourcer.py {verb}" in doc, f"`{verb}` exists but is undocumented"
        assert f"`{verb}`" in doc or f"`{verb} " in doc


def test_the_file_table_names_files_that_exist():
    """A table of what is in the box, checked against what is in the box."""
    root = SKILL.parent
    listed = set(re.findall(r"^\| `([^`]+\.(?:py|js))` \|", text(), re.M))
    assert listed, "the file table did not parse -- the test is measuring nothing"
    for rel in sorted(listed):
        assert (root / rel).is_file(), f"SKILL.md names {rel}, which does not exist"
    on_disk = {
        f"scripts/{p.name}" for p in (root / "scripts").glob("*.py")
    } | {f"workflows/{p.name}" for p in (root / "workflows").glob("*.js")}
    assert on_disk <= listed, f"undocumented: {sorted(on_disk - listed)}"


def test_the_expansion_route_described_is_the_one_implemented():
    """The document says a crawl moves only through a verified `profile` node."""
    doc = text()
    assert "`profile` node's name is a URL" in doc
    assert L.EXPANSION_PREDICATES == frozenset({"has_profile", "org_profile"})
    for p in L.EXPANSION_PREDICATES:
        assert X.PREDICATES[p][1] == "profile", (
            f"{p} is an expansion predicate but its range is not `profile`"
        )


def test_the_chain_key_requirement_is_documented_and_real():
    import fetchd as F
    import pytest

    doc = text()
    assert "SOURCER_CHAIN_KEY" in doc
    assert "refuses to construct without a key" in doc
    # And it does.
    import os

    saved = os.environ.pop(F.CHAIN_KEY_ENV, None)
    try:
        with pytest.raises(F.FetchError):
            F.FetchDaemon(root=Path("/tmp/nope"), run_id="r")
    finally:
        if saved is not None:
            os.environ[F.CHAIN_KEY_ENV] = saved


# --------------------------------------------------------------------------
# The workflow's invocations, checked against the real parser
# --------------------------------------------------------------------------


def _invocations(js: str, verb: str) -> list:
    """Every `<runner> <verb> ...` command line the workflow issues.

    The runner is a template variable (`${PY}`), not a literal path, which is
    why matching on `sourcer.py` found nothing at all.
    """
    return re.findall(rf"\$\{{PY\}}\s+{verb}\b([^`]*)", js, re.S)


def test_the_workflow_only_passes_flags_the_cli_accepts():
    """The regression this exists to prevent actually happened.

    `--depth` was removed from `land` because it was a security defect, and the
    workflow kept passing it — so `depth-loop.js` would have died on argument
    parsing at the first page. A JS syntax check does not catch that; nothing
    but comparing the two sides does. The workflow is a shell script written in
    another language, which is exactly the kind of seam that stays green on both
    sides while agreeing with neither.
    """
    import sourcer as C

    js = (SKILL.parent / "workflows" / "depth-loop.js").read_text()
    parser = C.build_parser()
    subs = parser._subparsers._group_actions[0].choices

    seen_any = False
    for verb, sub in subs.items():
        known = set()
        for action in sub._actions:
            known.update(action.option_strings)
        blocks = _invocations(js, verb)
        for block in blocks:
            seen_any = True
            for flag in set(re.findall(r"(--[a-z][a-z-]*)", block)):
                assert flag in known, (
                    f"depth-loop.js passes {flag} to `{verb}`, which does not "
                    f"accept it. Accepts: {sorted(known)}"
                )
    # The first version of this test used a pattern that matched NOTHING -- the
    # workflow invokes through a `${PY}` variable, not a literal `sourcer.py` --
    # so it passed while checking zero invocations.
    assert seen_any, "no invocations were found; the pattern is measuring nothing"


def test_the_workflow_names_every_required_flag_somewhere():
    """The other direction: a required argument the workflow forgets entirely.

    Checked against the WHOLE file rather than the invocation line, because
    some arguments are assembled into a variable first -- `--seed` is built by
    `SEEDS.map(...)` and reaches the command as `${seedArgs}`. That makes this
    the weaker half of the pair: it catches a flag the workflow never mentions,
    not one it drops from a particular call. The strong half is the test above,
    which catches a flag the CLI does not accept, and that is the direction the
    `--depth` regression actually broke.
    """
    import sourcer as C

    js = (SKILL.parent / "workflows" / "depth-loop.js").read_text()
    subs = C.build_parser()._subparsers._group_actions[0].choices
    for verb in ("plan", "take", "land"):
        assert _invocations(js, verb), f"the workflow never invokes `{verb}`"
        for action in subs[verb]._actions:
            if action.required and action.option_strings:
                assert action.option_strings[0] in js, (
                    f"depth-loop.js never mentions `{verb}`'s required "
                    f"{action.option_strings[0]}"
                )
