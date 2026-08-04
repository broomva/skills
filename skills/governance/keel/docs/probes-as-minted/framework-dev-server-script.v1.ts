/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          framework-dev-server-script (v1)
 * minted from: customer-support-agent/package.json#dev
 * minted at:   2026-07-25T03:57:46.971Z
 * shape:
 * A package-manager script whose command starts a long-running framework development or preview server (next dev / next start / nuxt dev / react-scripts start / webpack serve, or an alias that re-enters one via `npm|yarn|pnpm run dev`). Such a process runs until an operator interrupts it and never terminates with a verdict about the committed source, so it asserts nothing. Keyed on the command the script runs, never on the project or file it lives in. Abstains as soon as the same command line also contains a build, test, lint, typecheck or other check token, because a script that starts a server AND runs a check can fail on a property of the repo and belongs to the agent.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      the `next dev` development server process (a long-running HTTP server), plus two NEXT_PUBLIC_* env assignments
 *   actorCanWrite: null
 *   The script starts Next.js in development mode and blocks serving requests until interrupted; it never terminates with a pass/fail verdict about the committed source. The only variation in its exit status comes from how the operator kills it, so no property of the code can make it succeed or fail. Nothing in amplify.yml or the three workflow files invokes it either.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["script"];
const ALL_OF = [];
const ANY_OF = ["next dev","next start","nuxt dev","react-scripts start","webpack serve","npm run dev","yarn dev","pnpm dev"];
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
const ASSERT_ANY = ["next dev","next start","nuxt dev","react-scripts start","webpack serve","npm run dev","yarn dev","pnpm dev"];
const ASSERT_NONE = ["build","test","lint","tsc","typecheck","check","pytest","vitest","jest"];

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
  id: "framework-dev-server-script",
  version: 1,
  mintedAt: "2026-07-25T03:57:46.971Z",
  mintedFrom: "customer-support-agent/package.json#dev",
  description: "A package-manager script whose command starts a long-running framework development or preview server (next dev / next start / nuxt dev / react-scripts start / webpack serve, or an alias that re-enters one via `npm|yarn|pnpm run dev`). Such a process runs until an operator interrupts it and never terminates with a verdict about the committed source, so it asserts nothing. Keyed on the command the script runs, never on the project or file it lives in. Abstains as soon as the same command line also contains a build, test, lint, typecheck or other check token, because a script that starts a server AND runs a check can fail on a property of the repo and belongs to the agent.",
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
      writeBoundary: {"producer":"the `next dev` development server process (a long-running HTTP server), plus two NEXT_PUBLIC_* env assignments","actorCanWrite":null,"argument":"The script starts Next.js in development mode and blocks serving requests until interrupted; it never terminates with a pass/fail verdict about the committed source. The only variation in its exit status comes from how the operator kills it, so no property of the code can make it succeed or fail. Nothing in amplify.yml or the three workflow files invokes it either."},
      evidence: ["customer-support-agent/package.json:9","customer-support-agent/amplify.yml:6-13 (deploy runs `npm ci` then `npm run build`, never `dev`)"],
      confidence: 0.9,
    };
  },
};

export default probe;
export { probe };
