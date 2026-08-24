/**
 * CONTRACT REFERENCE — the one probe that ships with Keel.
 *
 * It exists so a human can see the shape of a probe before minting one, not to
 * seed a library. Probes are meant to be *crystallized agent judgment*; a
 * hand-written set of them shipped in the box would be a rule table in costume,
 * and it would flatter the crystallization curve by pre-paying its cost.
 *
 * It is deliberately a probe that can only ever move a grounding ratio DOWN:
 * it asserts `self_referential`, never `anchored`. A shipped probe that could
 * hand out cheap greens is exactly the artifact this project argues against.
 *
 * Shape: a pipeline step or review gate whose verdict is produced by a language
 * model reading the work. The write boundary fails because the producer of the
 * signal is the same class of system that produced the thing being checked —
 * the fork point never leaves the model's own output distribution.
 *
 * ---------------------------------------------------------------------------
 * FIXED DEFECT, recorded here because it is the exact failure this project
 * exists to name. This probe used to include `node.source` in its haystack, so
 * the workflow FILE NAME participated in matching. In a repo containing
 * `.github/workflows/claude-review.yml` — a common name — the steps
 *
 *     - run: pytest -q --exitfirst
 *     - run: cargo build --release --locked
 *
 * were both decided `self_referential` at 0.75 and never reached the agent,
 * because the PATH contained "claude" and "review". Those are textbook anchored
 * signals, and they were handed a confident write-boundary argument that was
 * false about them. Matching on a location is precisely what `mint-probe.ts`'s
 * `rejectRepoLiterals()` forbids for minted probes; this one bypassed that guard
 * only because it was hand-written rather than minted.
 *
 * The fix is not just "drop the path". A CI step is now matched on WHAT IT DOES
 * — its `uses:` action reference, its `run:` command, the `with:` inputs that
 * configure them — and on nothing else. See `haystack()`.
 * ---------------------------------------------------------------------------
 *
 * Minted probes live in `~/.config/keel/probes/` as `<id>.v<n>.ts`; the loader
 * takes the highest version per id. See ./README.md.
 */

import type { Node, Probe } from '../schemas/keel.ts';

/** A model is doing the reading. */
const MODELS = ['claude', 'gpt-', 'openai', 'anthropic', 'gemini', 'llm', 'ai review'];
/** …and the reading is a review of the work, not an unrelated model call. */
const REVIEWING = ['review', 'critique', 'judge', 'assess the diff'];
/** …and it is not a human gate that merely happens to mention a model. */
const NOT_THIS = ['required_approving_review_count', 'reviewers:', 'codeowners'];
/**
 * The CONFIRMING stage's negative signals: the model's reading cannot fail
 * anything here, so this step is advisory. Whether an advisory model review is
 * `not_a_check` (it gates nothing) or a weak `self_referential` (it gates
 * socially) is a judgment about the repo, not a shape — so the probe abstains
 * and the agent decides. This is what makes `null` in `assess` REACHABLE.
 */
const ADVISORY = ['continue-on-error: true', '|| true', 'mode: comment', 'comment-only'];

/**
 * WHAT THE STEP DOES. For a CI step that is the `uses:` action reference, the
 * `run:` command, and the `with:` inputs that configure them. Two things are
 * deliberately excluded, for two different reasons:
 *
 *  - `node.source` is a LOCATION. A path says where a check lives, never what
 *    produces its signal, and it is attacker-adjacent input: naming a workflow
 *    file `claude-review.yml` would otherwise make every step inside it match.
 *    See the FIXED DEFECT note above; this is not a stylistic choice.
 *
 *  - the `name:` label is an ASSERTION ABOUT the step, written by the same
 *    author as the step. Keel's whole thesis is that a claim about a check is
 *    not the check, so trusting the label here would commit the `doc_claim`
 *    mistake inside a probe. A step labelled "Claude review" that runs
 *    `pytest -q` runs pytest.
 *
 * For kinds that are not YAML steps the whole snippet plus the name is the
 * honest text: a `review_gate` is a configuration object, and the gate's own
 * identity is part of what is configured rather than a label on top of it.
 */
/**
 * Step keys that describe WHAT THE STEP DOES. Everything else in a step block —
 * `env:`, `if:`, `id:`, `name:`, `timeout-minutes:`, YAML comments — is context
 * or commentary ABOUT the step, and letting it into the matched text reproduces
 * the FIXED DEFECT above through a different field: a step carrying
 * `OPENAI_API_KEY` in `env:` and `if: ... pull_request_review ...` while running
 * `pytest -q` would match a probe about LLM review gates and be confidently
 * called self_referential, which is false about pytest.
 *
 * The header of this file claims the probe reads "the `uses:` reference, the
 * `run:` command, the `with:` inputs — and nothing else". This is that sentence
 * implemented, rather than asserted.
 */
const DOING_KEYS = /^(uses|run|with|entrypoint|args)$/;
/** `[1]` = text before the key, `[2]` = the key. In `- name: x` the dash is in [1]. */
const KEY_LINE = /^(\s*(?:-\s+)?)([A-Za-z][\w-]*)\s*:/;

/** The column the key itself starts at — NOT the line's indent. In a YAML list
 *  item the first key sits after `- `, and its siblings align with it, so keying
 *  off the raw indent would read every sibling as a child of the first key. */
function keyColumn(line: string): { col: number; key: string } | null {
  const m = KEY_LINE.exec(line);
  return m ? { col: m[1].length, key: m[2].toLowerCase() } : null;
}

function haystack(node: Node): string {
  if (node.kind !== 'ci_step') return [node.name, node.raw].join('\n').toLowerCase();

  const lines = node.raw.split('\n');
  // The column this step's own keys sit at. A block key's children are indented
  // deeper, so a key's block runs until the next key at or left of that column.
  let base: number | null = null;
  for (const line of lines) {
    const k = keyColumn(line);
    if (k) {
      base = k.col;
      break;
    }
  }
  if (base === null) return node.raw.toLowerCase();

  const kept: string[] = [];
  let keeping = false;
  for (const line of lines) {
    if (!line.trim() || /^\s*#/.test(line)) continue; // blank or YAML comment
    const k = keyColumn(line);
    if (k && k.col <= base) {
      // A key of the step itself: does its block describe what the step DOES?
      keeping = DOING_KEYS.test(k.key);
      if (keeping) kept.push(line);
      continue;
    }
    if (keeping) kept.push(line); // continuation of a kept block
  }
  return kept.join('\n').toLowerCase();
}

function signature(node: Node): boolean {
  if (node.kind !== 'ci_step' && node.kind !== 'review_gate') return false;
  const hay = haystack(node);
  if (!MODELS.some((t) => hay.includes(t))) return false;
  if (!REVIEWING.some((t) => hay.includes(t))) return false;
  if (NOT_THIS.some((t) => hay.includes(t))) return false;
  return true;
}

const probe: Probe = {
  id: 'example-llm-review-gate',
  version: 1,
  mintedAt: '2026-07-24T00:00:00.000Z',
  // Honest provenance. Nothing minted this — it was hand-written as an
  // illustration, and `mintedFrom` must not imply a judgment no agent made.
  mintedFrom: 'example#hand-written-illustration-not-minted',
  description:
    'A CI step or review gate whose pass/fail signal is a language model reading the work — an LLM reviewing what an LLM (or the same team) wrote.',
  // `match` is the cheap STRUCTURAL filter the dispatcher uses to decide whether
  // to call `assess` at all.
  match(node) {
    return signature(node);
  },
  assess(node) {
    // …and `assess` is strictly NARROWER, which is the point. The dispatcher only
    // calls `assess` after `match` returned true, so an `assess` that re-ran
    // `match`'s predicate would have an unreachable `return null` and would
    // assert on 100% of what it matched — the "probes abstain, never assert
    // ignorance" invariant would be decoration. The second guard below is the
    // real one: a matched-but-advisory step falls through to the agent. Abstain,
    // never guess, and never say `unknown` — that claim belongs to the agent.
    if (!signature(node)) return null;
    if (ADVISORY.some((t) => haystack(node).includes(t))) return null;
    return {
      class: 'self_referential',
      writeBoundary: {
        producer: 'a language model reading the work and emitting a verdict',
        actorCanWrite: true,
        argument:
          "The signal is a model's assessment of text a model produced. The actor can change the assessment by changing the input it feeds the reviewer, and nothing outside the model's own output decides pass or fail, so the fork point stays inside the write boundary.",
      },
      evidence: [node.source, node.raw.split('\n')[0] ?? node.name],
      confidence: 0.75,
    };
  },
};

export default probe;
export { probe };
