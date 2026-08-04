/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          registry-auth-configuration-step (v1)
 * minted from: .github/workflows/release.yml#21-rubygems-configure-rubygems-credentials-v1-0-0
 * minted at:   2026-07-25T03:41:37.926Z
 * shape:
 * A CI step whose entire body is a `uses:` of a credential-configuration or registry-login action — cloud credential configuration, container/package registry login, OIDC trusted-publishing credential exchange. Keyed on the action reference (what the step DOES), never on the workflow file it lives in. Complements the checkout/setup/cache provisioning shape, which does not cover auth actions. Abstains when the step also carries its own `run:` body or a with-block that names a test, build, verify or check command, because such a step is doing something beyond authentication and the agent must judge it.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      a credential/registry-authentication action configuring tokens or a login on the runner
 *   actorCanWrite: null
 *   The step's entire effect is authentication setup for later steps: it exchanges an OIDC token, writes an API key, or logs the runner into a registry or cloud provider. Its exit status reports whether the credential exchange succeeded — misconfigured trusted publishing, an expired secret, a provider outage — and never evaluates any property of the checked-out tree. It is provisioning in the same family as checkout and toolchain setup, so it must not enter the ratio in either direction; whatever verification the job performs lives in the steps that run commands against the source.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step"];
const ALL_OF = ["uses:"];
const ANY_OF = ["configure-rubygems-credentials","configure-aws-credentials","login-action","google-github-actions/auth","azure/login","amazon-ecr-login","vault-action"];
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
const ASSERT_ANY = ["configure-rubygems-credentials","configure-aws-credentials","login-action","google-github-actions/auth","azure/login","amazon-ecr-login","vault-action"];
const ASSERT_NONE = ["run:","test","verify","assert","--check","lint","audit"];

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
  id: "registry-auth-configuration-step",
  version: 1,
  mintedAt: "2026-07-25T03:41:37.926Z",
  mintedFrom: ".github/workflows/release.yml#21-rubygems-configure-rubygems-credentials-v1-0-0",
  description: "A CI step whose entire body is a `uses:` of a credential-configuration or registry-login action — cloud credential configuration, container/package registry login, OIDC trusted-publishing credential exchange. Keyed on the action reference (what the step DOES), never on the workflow file it lives in. Complements the checkout/setup/cache provisioning shape, which does not cover auth actions. Abstains when the step also carries its own `run:` body or a with-block that names a test, build, verify or check command, because such a step is doing something beyond authentication and the agent must judge it.",
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
      writeBoundary: {"producer":"a credential/registry-authentication action configuring tokens or a login on the runner","actorCanWrite":null,"argument":"The step's entire effect is authentication setup for later steps: it exchanges an OIDC token, writes an API key, or logs the runner into a registry or cloud provider. Its exit status reports whether the credential exchange succeeded — misconfigured trusted publishing, an expired secret, a provider outage — and never evaluates any property of the checked-out tree. It is provisioning in the same family as checkout and toolchain setup, so it must not enter the ratio in either direction; whatever verification the job performs lives in the steps that run commands against the source."},
      evidence: [".github/workflows/release.yml:21",".github/workflows/release.yml:13-14"],
      confidence: 0.85,
    };
  },
};

export default probe;
export { probe };
