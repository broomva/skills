/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          coverage-config-without-threshold (v1)
 * minted from: pyproject.toml#tool-coverage-run
 * minted at:   2026-07-25T03:33:21.266Z
 * shape:
 * A coverage-tool CONFIGURATION table -- `[tool.coverage.*]` in pyproject, `[coverage:run]`/`[coverage:report]` in setup.cfg/.coveragerc, an `nyc`/`c8` config block -- that declares only measurement scope and NO minimum threshold. The exact complement of the coverage-threshold-gate shape: that one fires on a declared minimum and calls it anchored, this one fires when no minimum is present at all and the table therefore gates nothing. Keyed on the configuration table plus the ABSENCE of a threshold token, never on the file it lives in. Abstains -- hands the node back to the agent -- when the same body also carries a coverage INVOCATION (`coverage run`, `coverage report`, `--cov`, `nyc `), because a node that both configures and executes may fail for reasons this shape cannot see.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      nothing that can vary — a coverage tool's SCOPE configuration (which files to trace, which lines to exclude, how to remap paths) declares no threshold, so no process derives a pass/fail from it
 *   actorCanWrite: null
 *   A coverage configuration table with no minimum declared (`fail_under`, `--fail-under`, jest's `coverageThreshold`) parameterises measurement, not judgment: the tool prints a percentage and exits zero whether the number is 4% or 94%. The excludes and source lists only widen or narrow what gets counted, so the edge reports the same value on a broken tree as on a healthy one, and a signal that cannot vary carries no information. Falsifiability is structural, which is why this is `not_a_check` rather than a statement about the tool's independence — coverage measured by an actual execution trace IS anchored, but only once a threshold turns it into an exit code, and that is the sibling shape (a declared minimum), not this one. Two things this shape does NOT claim, and the agent must still check: whether a `--fail-under` lives on a reporting command elsewhere in the repo, and whether the coverage tool runs at all.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script","test_target","other"];
const ALL_OF = [];
const ANY_OF = ["[tool.coverage","[coverage:run]","[coverage:report]","[coverage:paths]"];
const NONE_OF = ["fail_under","fail-under","coveragethreshold","minimum_coverage","min_coverage"];

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
const ASSERT_ANY = ["branch","source","omit","exclude","include","relative_files","data_file"];
const ASSERT_NONE = ["fail_under","fail-under","coveragethreshold","minimum_coverage","min_coverage","--cov","coverage run","coverage report","coverage xml"];

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
  id: "coverage-config-without-threshold",
  version: 1,
  mintedAt: "2026-07-25T03:33:21.266Z",
  mintedFrom: "pyproject.toml#tool-coverage-run",
  description: "A coverage-tool CONFIGURATION table -- `[tool.coverage.*]` in pyproject, `[coverage:run]`/`[coverage:report]` in setup.cfg/.coveragerc, an `nyc`/`c8` config block -- that declares only measurement scope and NO minimum threshold. The exact complement of the coverage-threshold-gate shape: that one fires on a declared minimum and calls it anchored, this one fires when no minimum is present at all and the table therefore gates nothing. Keyed on the configuration table plus the ABSENCE of a threshold token, never on the file it lives in. Abstains -- hands the node back to the agent -- when the same body also carries a coverage INVOCATION (`coverage run`, `coverage report`, `--cov`, `nyc `), because a node that both configures and executes may fail for reasons this shape cannot see.",
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
      class: "not_a_check",
      writeBoundary: {"producer":"nothing that can vary — a coverage tool's SCOPE configuration (which files to trace, which lines to exclude, how to remap paths) declares no threshold, so no process derives a pass/fail from it","actorCanWrite":null,"argument":"A coverage configuration table with no minimum declared (`fail_under`, `--fail-under`, jest's `coverageThreshold`) parameterises measurement, not judgment: the tool prints a percentage and exits zero whether the number is 4% or 94%. The excludes and source lists only widen or narrow what gets counted, so the edge reports the same value on a broken tree as on a healthy one, and a signal that cannot vary carries no information. Falsifiability is structural, which is why this is `not_a_check` rather than a statement about the tool's independence — coverage measured by an actual execution trace IS anchored, but only once a threshold turns it into an exit code, and that is the sibling shape (a declared minimum), not this one. Two things this shape does NOT claim, and the agent must still check: whether a `--fail-under` lives on a reporting command elsewhere in the repo, and whether the coverage tool runs at all."},
      evidence: ["a coverage configuration table declaring scope (branch/source/omit/exclude/paths) with no minimum-coverage threshold anywhere in it"],
      confidence: 0.75,
    };
  },
};

export default probe;
export { probe };
