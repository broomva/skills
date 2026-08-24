/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          ci-artifact-merge (v1)
 * minted from: .github/workflows/build_wheels.yml#91-merge-artifacts
 * minted at:   2026-07-25T03:05:59.326Z
 * shape:
 * A CI step whose entire body is a `uses:` of the artifact MERGE sub-action (actions/upload-artifact/merge), which folds artifacts an earlier job in the same run uploaded into a single bundle. Keyed on the action reference, never on the workflow file it sits in. Deliberately narrower than plain upload/download transport: it matches only the merge sub-path. Abstains — hands the node back to the agent — when the step also carries its own `run:` command or an `if:` condition, because a step that both merges and executes or gates on something can genuinely assert a property of the run.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      actions/upload-artifact/merge, a GitHub Actions aggregation action folding artifacts the same workflow run already uploaded into one bundle
 *   actorCanWrite: null
 *   The step's whole effect is to re-pack files the pipeline itself produced under a single artifact name. It reads none of the repository's source and evaluates no property of it, so its failure modes are 'no artifact matched the pattern' or 'the artifact API errored' — facts about run plumbing, not about whether the code is correct. The assertion in such a job is made by the jobs listed in `needs:` that produced the artifacts, and is classified where those signals are emitted; counting this edge in the ratio in either direction would credit or penalize the score for a file copy.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step"];
const ALL_OF = ["uses:"];
const ANY_OF = ["upload-artifact/merge@"];
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

const ASSERT_ALL = ["upload-artifact/merge@"];
const ASSERT_ANY = [];
const ASSERT_NONE = ["run:","if:","|| true"];

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
  id: "ci-artifact-merge",
  version: 1,
  mintedAt: "2026-07-25T03:05:59.326Z",
  mintedFrom: ".github/workflows/build_wheels.yml#91-merge-artifacts",
  description: "A CI step whose entire body is a `uses:` of the artifact MERGE sub-action (actions/upload-artifact/merge), which folds artifacts an earlier job in the same run uploaded into a single bundle. Keyed on the action reference, never on the workflow file it sits in. Deliberately narrower than plain upload/download transport: it matches only the merge sub-path. Abstains — hands the node back to the agent — when the step also carries its own `run:` command or an `if:` condition, because a step that both merges and executes or gates on something can genuinely assert a property of the run.",
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
      writeBoundary: {"producer":"actions/upload-artifact/merge, a GitHub Actions aggregation action folding artifacts the same workflow run already uploaded into one bundle","actorCanWrite":null,"argument":"The step's whole effect is to re-pack files the pipeline itself produced under a single artifact name. It reads none of the repository's source and evaluates no property of it, so its failure modes are 'no artifact matched the pattern' or 'the artifact API errored' — facts about run plumbing, not about whether the code is correct. The assertion in such a job is made by the jobs listed in `needs:` that produced the artifacts, and is classified where those signals are emitted; counting this edge in the ratio in either direction would credit or penalize the score for a file copy."},
      evidence: ["the step body is a bare `uses:` of the upload-artifact merge sub-action with no command of its own"],
      confidence: 0.8,
    };
  },
};

export default probe;
export { probe };
