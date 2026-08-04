/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          failure-suppressed-edge (v1)
 * minted from: Makefile#test-readme
 * minted at:   2026-07-25T03:13:19.581Z
 * shape:
 * A pipeline step or build-tool target whose own exit status is thrown away — the command chain falls through to `|| true` or `|| echo "..."`, or the step declares `continue-on-error: true`. Keyed on the suppression construct itself, never on the file it lives in, so it fires the same way in a workflow step, a Makefile recipe and a package script. Abstains — hands the node back to the agent — when the same body also runs a real check (a test runner or a static analyser) or explicitly re-raises failure (`exit 1`, `set -e`), because there the suppression may cover only one command in a longer chain and only the agent can read which one it covers.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      the shell (or the CI runner's step-result logic) — the suppressing construct is the last thing to run, so a zero exit status is handed up regardless of what the underlying command decided
 *   actorCanWrite: false
 *   The body's exit status is discarded by construction: a trailing `|| true` or `|| echo "..."` runs a command that always succeeds on the failure branch, and `continue-on-error: true` tells the runner to record the step green whatever it returns. The underlying tool may still compute an honest verdict, but nothing downstream can ever observe it — the edge reports the same value on a broken tree as on a healthy one, and a signal that cannot vary carries no information. Falsifiability is structural, so this is `not_a_check` rather than a statement about the producer's independence; the failure mode is that such a step still renders green in the checks list and reads to a reviewer like a passing gate.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script","test_target","deploy_gate"];
const ALL_OF = [];
const ANY_OF = ["|| true","|| echo","continue-on-error: true"];
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
const ASSERT_ANY = ["|| true","|| echo","continue-on-error: true"];
const ASSERT_NONE = ["exit 1","set -e","pytest","cargo test","go test","npm test","ruff check","mypy","pyright","eslint","tsc"];

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
  id: "failure-suppressed-edge",
  version: 1,
  mintedAt: "2026-07-25T03:13:19.581Z",
  mintedFrom: "Makefile#test-readme",
  description: "A pipeline step or build-tool target whose own exit status is thrown away — the command chain falls through to `|| true` or `|| echo \"...\"`, or the step declares `continue-on-error: true`. Keyed on the suppression construct itself, never on the file it lives in, so it fires the same way in a workflow step, a Makefile recipe and a package script. Abstains — hands the node back to the agent — when the same body also runs a real check (a test runner or a static analyser) or explicitly re-raises failure (`exit 1`, `set -e`), because there the suppression may cover only one command in a longer chain and only the agent can read which one it covers.",
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
      writeBoundary: {"producer":"the shell (or the CI runner's step-result logic) — the suppressing construct is the last thing to run, so a zero exit status is handed up regardless of what the underlying command decided","actorCanWrite":false,"argument":"The body's exit status is discarded by construction: a trailing `|| true` or `|| echo \"...\"` runs a command that always succeeds on the failure branch, and `continue-on-error: true` tells the runner to record the step green whatever it returns. The underlying tool may still compute an honest verdict, but nothing downstream can ever observe it — the edge reports the same value on a broken tree as on a healthy one, and a signal that cannot vary carries no information. Falsifiability is structural, so this is `not_a_check` rather than a statement about the producer's independence; the failure mode is that such a step still renders green in the checks list and reads to a reviewer like a passing gate."},
      evidence: ["the body's command chain terminates in a construct that forces success (`|| true`, `|| echo ...`) or the step declares `continue-on-error: true`"],
      confidence: 0.82,
    };
  },
};

export default probe;
export { probe };
