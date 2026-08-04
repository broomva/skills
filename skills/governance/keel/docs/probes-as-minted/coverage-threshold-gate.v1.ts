/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          coverage-threshold-gate (v1)
 * minted from: pyproject.toml#tool-coverage-report
 * minted at:   2026-07-25T02:54:59.085Z
 * shape:
 * A declared minimum-coverage threshold that a coverage tool enforces by exit code -- `fail_under` in a coverage config table, `--fail-under=N` on a report command, jest's `coverageThreshold`, `minimum_coverage`. Keyed on the threshold declaration itself, never on the file it lives in, so it fires the same way in pyproject.toml, .coveragerc, setup.cfg, a package script or a CI step. Abstains -- hands the node back to the agent -- when the threshold is zero (a `--fail-under=0` scoping run asserts nothing) or when the surrounding command suppresses its own failure (`|| true`, `continue-on-error`, `exit 0`), and it deliberately does not claim the reporting command runs on the merge path: that is the agent's to establish.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      a coverage tool's exit code, computed from the line/branch execution trace the language runtime recorded while the test suite actually ran
 *   actorCanWrite: false
 *   A minimum-coverage threshold (fail_under / --fail-under / jest coverageThreshold) is compared against a number no one in the repo writes: the coverage tool derives it from which lines and branch arcs the interpreter actually executed during the run. An author cannot make an unexecuted line report covered without executing it, so the producer of the failing condition is the runtime's trace, outside the write boundary. Three limits, and they must travel with this verdict: (1) coverage measures REACH, not correctness -- a fully covered line can still be wrong, and this says nothing about the quality of the assertions that reached it; (2) the threshold value and the omit/exclude lists sit inside the write boundary, so the SCOPE of the gate is author-controlled even though each measurement is not; (3) this shape reads a threshold declaration, not a pipeline, so whether the gate binds depends on the reporting command actually running on the merge path -- check that separately before treating it as a merge gate.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script","test_target","other"];
const ALL_OF = [];
const ANY_OF = ["fail_under","fail-under","coveragethreshold","minimum_coverage","min_coverage"];
const NONE_OF = [];

/**
 * The shape, keyed on structure. Not on a repo, not on a path.
 *
 * `node.source` is deliberately NOT in the haystack. A file path says where a
 * check lives, never what produces its signal, and a path is attacker-adjacent
 * input: a repo that names a workflow `claude-review.yml` would otherwise have
 * every step in it — `pytest`, `cargo build` — match a probe about LLM review
 * gates. `mint-probe`'s `rejectRepoLiterals()` refuses path literals as tokens;
 * excluding `source` from the text being searched is the other half of that.
 */
function signature(node) {
  if (KINDS.length && !KINDS.includes(node.kind)) return false;
  const hay = [node.name, node.raw].join('\n').toLowerCase();
  if (!ALL_OF.every((t) => hay.includes(t))) return false;
  if (ANY_OF.length && !ANY_OF.some((t) => hay.includes(t))) return false;
  if (NONE_OF.some((t) => hay.includes(t))) return false;
  return true;
}

const ASSERT_ALL = [];
const ASSERT_ANY = ["fail_under","fail-under","coveragethreshold","minimum_coverage","min_coverage"];
const ASSERT_NONE = ["fail_under = 0","fail_under=0","fail-under 0","fail-under=0","fail_under: 0","|| true","continue-on-error","exit 0"];

/**
 * The CONFIRMING stage — strictly narrower than `signature`, and reading
 * `node.raw` alone. `match` is a cheap structural filter; this is the check
 * that can fail, which is what makes the abstention below reachable. A node that
 * matches but does not confirm goes back to the agent.
 */
function confirms(node) {
  const raw = String(node.raw == null ? '' : node.raw).toLowerCase();
  if (!ASSERT_ALL.every((t) => raw.includes(t))) return false;
  if (ASSERT_ANY.length && !ASSERT_ANY.some((t) => raw.includes(t))) return false;
  if (ASSERT_NONE.some((t) => raw.includes(t))) return false;
  return true;
}

const probe = {
  id: "coverage-threshold-gate",
  version: 1,
  mintedAt: "2026-07-25T02:54:59.085Z",
  mintedFrom: "pyproject.toml#tool-coverage-report",
  description: "A declared minimum-coverage threshold that a coverage tool enforces by exit code -- `fail_under` in a coverage config table, `--fail-under=N` on a report command, jest's `coverageThreshold`, `minimum_coverage`. Keyed on the threshold declaration itself, never on the file it lives in, so it fires the same way in pyproject.toml, .coveragerc, setup.cfg, a package script or a CI step. Abstains -- hands the node back to the agent -- when the threshold is zero (a `--fail-under=0` scoping run asserts nothing) or when the surrounding command suppresses its own failure (`|| true`, `continue-on-error`, `exit 0`), and it deliberately does not claim the reporting command runs on the merge path: that is the agent's to establish.",
  match(node) {
    return signature(node);
  },
  assess(node) {
    // Two-stage: `match` filtered on structure, this confirms on the literal
    // text. Abstention (`null`) is REACHABLE here — a node this probe matched
    // can still fail `confirms` and fall through to the agent. Abstention is
    // the ONLY way a probe says "I cannot tell"; it may never say 'unknown'.
    if (!signature(node)) return null;
    if (!confirms(node)) return null;
    return {
      class: "anchored",
      writeBoundary: {"producer":"a coverage tool's exit code, computed from the line/branch execution trace the language runtime recorded while the test suite actually ran","actorCanWrite":false,"argument":"A minimum-coverage threshold (fail_under / --fail-under / jest coverageThreshold) is compared against a number no one in the repo writes: the coverage tool derives it from which lines and branch arcs the interpreter actually executed during the run. An author cannot make an unexecuted line report covered without executing it, so the producer of the failing condition is the runtime's trace, outside the write boundary. Three limits, and they must travel with this verdict: (1) coverage measures REACH, not correctness -- a fully covered line can still be wrong, and this says nothing about the quality of the assertions that reached it; (2) the threshold value and the omit/exclude lists sit inside the write boundary, so the SCOPE of the gate is author-controlled even though each measurement is not; (3) this shape reads a threshold declaration, not a pipeline, so whether the gate binds depends on the reporting command actually running on the merge path -- check that separately before treating it as a merge gate."},
      evidence: ["a coverage threshold declaration (fail_under / --fail-under / coverageThreshold) with a non-zero minimum"],
      confidence: 0.6,
    };
  },
};

export default probe;
export { probe };
