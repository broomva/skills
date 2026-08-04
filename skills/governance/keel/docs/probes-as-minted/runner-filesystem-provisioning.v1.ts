/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          runner-filesystem-provisioning (v1)
 * minted from: .github/workflows/python-version-review.yml#94-grant-the-codex-user-controlled-workspace-access
 * minted at:   2026-07-25T01:41:59.160Z
 * shape:
 * A run step or script whose body is machine preparation — mkdir / chmod / chown / adduser / usermod. Keyed on the commands, never on the file it lives in. Abstains whenever the same body also contains an assertion surface (an explicit `exit 1` branch, a test/lint/typecheck invocation, a diff, a curl fetch, or the word verify/assert), because a step that provisions AND asserts can fail on a property of the repo and belongs to the agent.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      shell filesystem/account provisioning commands (mkdir, chmod, chown, adduser, usermod) executed on the runner
 *   actorCanWrite: null
 *   The step arranges the machine — creates directories, sets ownership and permission bits, or adds a user — so that later steps have somewhere to work. No property of the committed source is read and no comparison is performed, so its exit code varies with the runner's state, never with whether the code is correct. Any assertion in such a job is made by whatever executes against the prepared environment afterwards.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = [];
const ANY_OF = ["mkdir","chmod","chown","adduser","usermod"];
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
const ASSERT_ANY = ["mkdir","chmod","chown","adduser","usermod"];
const ASSERT_NONE = ["exit 1","pytest","test","lint","check","diff","curl","verify","assert","compile"];

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
  id: "runner-filesystem-provisioning",
  version: 1,
  mintedAt: "2026-07-25T01:41:59.160Z",
  mintedFrom: ".github/workflows/python-version-review.yml#94-grant-the-codex-user-controlled-workspace-access",
  description: "A run step or script whose body is machine preparation — mkdir / chmod / chown / adduser / usermod. Keyed on the commands, never on the file it lives in. Abstains whenever the same body also contains an assertion surface (an explicit `exit 1` branch, a test/lint/typecheck invocation, a diff, a curl fetch, or the word verify/assert), because a step that provisions AND asserts can fail on a property of the repo and belongs to the agent.",
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
      writeBoundary: {"producer":"shell filesystem/account provisioning commands (mkdir, chmod, chown, adduser, usermod) executed on the runner","actorCanWrite":null,"argument":"The step arranges the machine — creates directories, sets ownership and permission bits, or adds a user — so that later steps have somewhere to work. No property of the committed source is read and no comparison is performed, so its exit code varies with the runner's state, never with whether the code is correct. Any assertion in such a job is made by whatever executes against the prepared environment afterwards."},
      evidence: ["the run body consists of filesystem/account provisioning commands with no assertion, comparison, or explicit failure branch"],
      confidence: 0.75,
    };
  },
};

export default probe;
export { probe };
