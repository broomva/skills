/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          dependency-pin-update-target (v1)
 * minted from: pyproject.toml#tool-tox-env-update-actions
 * minted at:   2026-07-25T03:33:38.140Z
 * shape:
 * A maintenance target or step whose body only BUMPS pinned versions and writes them back into the tree -- `pre-commit autoupdate`, `gha-update`, `npm update`, `poetry update`, `cargo update`, `bundle update`. Keyed on the update command itself, never on the file or target name it lives in, so it fires the same way in a Makefile recipe, a tox/nox environment and a workflow step. Abstains -- hands the node back to the agent -- whenever a verifying flag is present (`--check`, `--locked`, `--frozen`, `--dry-run`) or the body also asserts on the result (`git diff --exit-code`, `exit 1`, a test runner), because in those forms the same command becomes a real falsifiable claim that the committed pins are current.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      a pin-bumping tool whose effect is to REWRITE version pins in the tree (and whose exit status therefore reports network reachability, not any property of the code)
 *   actorCanWrite: null
 *   The target's whole body is a command that resolves the newest upstream versions and writes them back into the repository -- `pre-commit autoupdate`, `gha-update`, `npm/poetry/cargo update`. It evaluates nothing: it succeeds by mutating files, so it returns the same status on a broken tree as on a healthy one and cannot go red because of a defect. The contrast that defines the boundary is the same tool in verifying mode -- `--check`, `--locked`, `--frozen`, `--dry-run` -- which IS a falsifiable assertion that the committed pins are already current; this shape hands any such node back to the agent rather than classifying it.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script","test_target","other"];
const ALL_OF = [];
const ANY_OF = ["autoupdate","gha-update","npm update","poetry update","cargo update","bundle update","ncu -u"];
const NONE_OF = ["uses:"];

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
const ASSERT_ANY = ["autoupdate","gha-update","npm update","poetry update","cargo update","bundle update","ncu -u"];
const ASSERT_NONE = ["--check","--locked","--frozen","--dry-run","exit-code","exit 1","pytest","git diff"];

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
  id: "dependency-pin-update-target",
  version: 1,
  mintedAt: "2026-07-25T03:33:38.140Z",
  mintedFrom: "pyproject.toml#tool-tox-env-update-actions",
  description: "A maintenance target or step whose body only BUMPS pinned versions and writes them back into the tree -- `pre-commit autoupdate`, `gha-update`, `npm update`, `poetry update`, `cargo update`, `bundle update`. Keyed on the update command itself, never on the file or target name it lives in, so it fires the same way in a Makefile recipe, a tox/nox environment and a workflow step. Abstains -- hands the node back to the agent -- whenever a verifying flag is present (`--check`, `--locked`, `--frozen`, `--dry-run`) or the body also asserts on the result (`git diff --exit-code`, `exit 1`, a test runner), because in those forms the same command becomes a real falsifiable claim that the committed pins are current.",
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
      writeBoundary: {"producer":"a pin-bumping tool whose effect is to REWRITE version pins in the tree (and whose exit status therefore reports network reachability, not any property of the code)","actorCanWrite":null,"argument":"The target's whole body is a command that resolves the newest upstream versions and writes them back into the repository -- `pre-commit autoupdate`, `gha-update`, `npm/poetry/cargo update`. It evaluates nothing: it succeeds by mutating files, so it returns the same status on a broken tree as on a healthy one and cannot go red because of a defect. The contrast that defines the boundary is the same tool in verifying mode -- `--check`, `--locked`, `--frozen`, `--dry-run` -- which IS a falsifiable assertion that the committed pins are already current; this shape hands any such node back to the agent rather than classifying it."},
      evidence: ["a target whose command body is a version-pin update command with no verifying flag"],
      confidence: 0.85,
    };
  },
};

export default probe;
export { probe };
