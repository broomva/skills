/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          ci-env-export-step (v1)
 * minted from: .github/workflows/tests.yaml#39-echo-pwd-venv-bin-github-path
 * minted at:   2026-07-25T03:57:47.098Z
 * shape:
 * A CI step whose body only appends a variable or a PATH entry to the runner's GITHUB_ENV / GITHUB_PATH file via echo. Its effect is to hand state to a later step; it reads no property of the committed source and performs no comparison, so its exit status varies with the runner, never with whether the code is correct. Keyed on the export mechanism, not on the workflow file it appears in. Abstains whenever the same body also contains a test, lint, check, curl, diff or explicit `exit 1` token, since a step that exports AND asserts can fail on the repo and belongs to the agent.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      the runner's `echo` builtin appending a directory string to the GITHUB_PATH file
 *   actorCanWrite: null
 *   The step's whole effect is to prepend the virtualenv's bin directory to PATH so the following pyright/pytest step resolves the installed tools. It reads no property of the committed source and performs no comparison — a string append to a runner-managed file succeeds regardless of whether the code is correct. Any assertion in this job is made by the step that runs afterwards.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = ["echo"];
const ANY_OF = ["github_path","github_env"];
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

const ASSERT_ALL = ["echo"];
const ASSERT_ANY = ["github_path","github_env"];
const ASSERT_NONE = ["pytest","exit 1","curl","diff","lint","check","test","tsc"];

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
  id: "ci-env-export-step",
  version: 1,
  mintedAt: "2026-07-25T03:57:47.098Z",
  mintedFrom: ".github/workflows/tests.yaml#39-echo-pwd-venv-bin-github-path",
  description: "A CI step whose body only appends a variable or a PATH entry to the runner's GITHUB_ENV / GITHUB_PATH file via echo. Its effect is to hand state to a later step; it reads no property of the committed source and performs no comparison, so its exit status varies with the runner, never with whether the code is correct. Keyed on the export mechanism, not on the workflow file it appears in. Abstains whenever the same body also contains a test, lint, check, curl, diff or explicit `exit 1` token, since a step that exports AND asserts can fail on the repo and belongs to the agent.",
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
      writeBoundary: {"producer":"the runner's `echo` builtin appending a directory string to the GITHUB_PATH file","actorCanWrite":null,"argument":"The step's whole effect is to prepend the virtualenv's bin directory to PATH so the following pyright/pytest step resolves the installed tools. It reads no property of the committed source and performs no comparison — a string append to a runner-managed file succeeds regardless of whether the code is correct. Any assertion in this job is made by the step that runs afterwards."},
      evidence: [".github/workflows/tests.yaml:39",".github/workflows/tests.yaml:35-38 (the venv it is pointing at)",".github/workflows/tests.yaml:40 (the step that consumes the PATH)"],
      confidence: 0.9,
    };
  },
};

export default probe;
export { probe };
