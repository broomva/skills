/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          artifact-publish-upload (v1)
 * minted from: .github/workflows/publish.yml#50-publish
 * minted at:   2026-07-25T03:00:30.787Z
 * shape:
 * A pipeline step or script command whose body only ships an already-built artefact to a registry — pypi-publish, twine upload, npm publish, cargo publish, poetry publish, gem push, docker push, gh release upload. Keyed on the publishing command or action, never on the file it lives in. Abstains when the same step also exercises the published thing (a smoke request, a health probe, a test run), because then the step is doing something other than promotion and the agent must judge it.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      a release/upload command handing a already-built artefact to a package registry
 *   actorCanWrite: null
 *   The step's entire effect is promotion: it takes distributions an earlier step produced and uploads them to an index (PyPI, npm, crates.io, a container registry, a GitHub release). It evaluates nothing about the artefact — a failure means the upload was rejected (duplicate version, bad credentials, registry outage), not that the code is wrong. Whatever verification exists lives in the job's `needs:` / environment condition, which is a different edge, so this one must not enter the ratio in either direction.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = [];
const ANY_OF = ["pypi-publish","twine upload","npm publish","cargo publish","poetry publish","gem push","docker push","gh release upload"];
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
const ASSERT_ANY = ["pypi-publish","twine upload","npm publish","cargo publish","poetry publish","gem push","docker push","gh release upload"];
const ASSERT_NONE = ["pytest","curl","smoke","health","assert","--check"];

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
  id: "artifact-publish-upload",
  version: 1,
  mintedAt: "2026-07-25T03:00:30.787Z",
  mintedFrom: ".github/workflows/publish.yml#50-publish",
  description: "A pipeline step or script command whose body only ships an already-built artefact to a registry — pypi-publish, twine upload, npm publish, cargo publish, poetry publish, gem push, docker push, gh release upload. Keyed on the publishing command or action, never on the file it lives in. Abstains when the same step also exercises the published thing (a smoke request, a health probe, a test run), because then the step is doing something other than promotion and the agent must judge it.",
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
      writeBoundary: {"producer":"a release/upload command handing a already-built artefact to a package registry","actorCanWrite":null,"argument":"The step's entire effect is promotion: it takes distributions an earlier step produced and uploads them to an index (PyPI, npm, crates.io, a container registry, a GitHub release). It evaluates nothing about the artefact — a failure means the upload was rejected (duplicate version, bad credentials, registry outage), not that the code is wrong. Whatever verification exists lives in the job's `needs:` / environment condition, which is a different edge, so this one must not enter the ratio in either direction."},
      evidence: [".github/workflows/publish.yml:50-51"],
      confidence: 0.8,
    };
  },
};

export default probe;
export { probe };
