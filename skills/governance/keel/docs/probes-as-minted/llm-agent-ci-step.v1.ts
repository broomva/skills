/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          llm-agent-ci-step (v1)
 * minted from: .github/workflows/claude.yml#38-run-claude-code
 * minted at:   2026-07-25T01:34:55.486Z
 * shape:
 * A CI step that invokes an LLM coding or code-review agent (a `uses:` whose action reference is an AI agent/reviewer). Keyed on the action reference — what the step invokes — never on the workflow file name, so a workflow merely NAMED after a bot does not drag its unrelated pytest and build steps in. Abstains when the step is declared unable to fail (continue-on-error / `|| true`), since a signal that cannot vary is the agent's call, not this probe's.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      a large language model invoked by a CI step
 *   actorCanWrite: true
 *   The step hands the repository to a language model and takes back prose, a review, or commits. Whatever verdict it renders is produced by the same class of system that produces the code being judged, so the two share correlated blind spots and agreement between them is not evidence. In the common configuration the model is also granted repository write tools, which means the reviewer can edit the very state it is reporting on.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step"];
const ALL_OF = ["uses:"];
const ANY_OF = ["claude-code-action","coderabbit","copilot-code-review","codex-action","gemini-code-assist","ai-code-review","cursor-agent"];
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
const ASSERT_ANY = ["claude-code-action","coderabbit","copilot-code-review","codex-action","gemini-code-assist","ai-code-review","cursor-agent"];
const ASSERT_NONE = ["continue-on-error: true","|| true"];

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
  id: "llm-agent-ci-step",
  version: 1,
  mintedAt: "2026-07-25T01:34:55.486Z",
  mintedFrom: ".github/workflows/claude.yml#38-run-claude-code",
  description: "A CI step that invokes an LLM coding or code-review agent (a `uses:` whose action reference is an AI agent/reviewer). Keyed on the action reference — what the step invokes — never on the workflow file name, so a workflow merely NAMED after a bot does not drag its unrelated pytest and build steps in. Abstains when the step is declared unable to fail (continue-on-error / `|| true`), since a signal that cannot vary is the agent's call, not this probe's.",
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
      class: "self_referential",
      writeBoundary: {"producer":"a large language model invoked by a CI step","actorCanWrite":true,"argument":"The step hands the repository to a language model and takes back prose, a review, or commits. Whatever verdict it renders is produced by the same class of system that produces the code being judged, so the two share correlated blind spots and agreement between them is not evidence. In the common configuration the model is also granted repository write tools, which means the reviewer can edit the very state it is reporting on."},
      evidence: ["the step's `uses:` reference resolves to an LLM coding/review agent action"],
      confidence: 0.75,
    };
  },
};

export default probe;
export { probe };
