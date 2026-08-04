/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          ci-artifact-transport (v1)
 * minted from: .github/workflows/python-version-review.yml#162-upload-the-action-required-assessment
 * minted at:   2026-07-25T01:41:46.746Z
 * shape:
 * A CI step whose entire body is a `uses:` of an artifact transport action — upload-artifact or download-artifact. Keyed on the action reference (what the step DOES), never on the workflow file it sits in. Abstains when the step also carries its own `run:` command or an `if-no-files-found` other than the transport defaults, because a step that both moves an artifact and executes something can genuinely fail on a property of the repo.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      a GitHub Actions artifact transport action (upload-artifact / download-artifact) moving files between jobs
 *   actorCanWrite: null
 *   The step's whole effect is to move a file the pipeline itself produced from one job to another. Nothing about the repository is evaluated: with `if-no-files-found: error` the worst it can report is that an earlier step in the same run did not leave the file it claimed to leave, which is a fact about the plumbing, not about whether the code is correct. Whatever assertion exists in such a job is made by the step that produced the artifact or the step that consumes it, so this edge must not enter the ratio in either direction.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step"];
const ALL_OF = ["uses:"];
const ANY_OF = ["upload-artifact@","download-artifact@"];
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

const ASSERT_ALL = ["uses:"];
const ASSERT_ANY = ["upload-artifact@","download-artifact@"];
const ASSERT_NONE = ["run:","continue-on-error"];

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
  id: "ci-artifact-transport",
  version: 1,
  mintedAt: "2026-07-25T01:41:46.746Z",
  mintedFrom: ".github/workflows/python-version-review.yml#162-upload-the-action-required-assessment",
  description: "A CI step whose entire body is a `uses:` of an artifact transport action — upload-artifact or download-artifact. Keyed on the action reference (what the step DOES), never on the workflow file it sits in. Abstains when the step also carries its own `run:` command or an `if-no-files-found` other than the transport defaults, because a step that both moves an artifact and executes something can genuinely fail on a property of the repo.",
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
      writeBoundary: {"producer":"a GitHub Actions artifact transport action (upload-artifact / download-artifact) moving files between jobs","actorCanWrite":null,"argument":"The step's whole effect is to move a file the pipeline itself produced from one job to another. Nothing about the repository is evaluated: with `if-no-files-found: error` the worst it can report is that an earlier step in the same run did not leave the file it claimed to leave, which is a fact about the plumbing, not about whether the code is correct. Whatever assertion exists in such a job is made by the step that produced the artifact or the step that consumes it, so this edge must not enter the ratio in either direction."},
      evidence: ["the step body is a bare `uses:` of an artifact upload/download action with no command of its own"],
      confidence: 0.7,
    };
  },
};

export default probe;
export { probe };
