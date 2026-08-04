/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          chat-webhook-notification (v1)
 * minted from: .github/workflows/slack-workflow-failure-notification.yml#31-send-slack-notification
 * minted at:   2026-07-25T02:25:18.503Z
 * shape:
 * A step that posts a message to a chat webhook (Slack/Discord/Teams) — either by curling a webhook URL held in a secret, or through a dedicated notification action. It transports a verdict some other job already reached; it evaluates nothing itself.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      curl POSTing a jq-built JSON payload to a Slack webhook URL held in secrets
 *   actorCanWrite: null
 *   The step is a transport for a verdict already reached elsewhere: the job only runs at all under `if: github.event.workflow_run.conclusion == 'failure'`, and the payload is just the failed workflow's name and html_url. It re-states someone else's result and makes no claim of its own. It also cannot report a problem — `curl` is invoked without `-f`, so an HTTP 4xx/5xx from Slack still exits zero, meaning even the delivery is unverified.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = [];
const ANY_OF = ["slack","discord.com/api/webhooks","webhook.office.com","mattermost","pagerduty"];
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
const ASSERT_ANY = ["curl","uses:","webhook"];
const ASSERT_NONE = ["pytest","vitest","go test","cargo test","exit 1","--check","npm test","assert"];

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
  id: "chat-webhook-notification",
  version: 1,
  mintedAt: "2026-07-25T02:25:18.503Z",
  mintedFrom: ".github/workflows/slack-workflow-failure-notification.yml#31-send-slack-notification",
  description: "A step that posts a message to a chat webhook (Slack/Discord/Teams) — either by curling a webhook URL held in a secret, or through a dedicated notification action. It transports a verdict some other job already reached; it evaluates nothing itself.",
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
      writeBoundary: {"producer":"curl POSTing a jq-built JSON payload to a Slack webhook URL held in secrets","actorCanWrite":null,"argument":"The step is a transport for a verdict already reached elsewhere: the job only runs at all under `if: github.event.workflow_run.conclusion == 'failure'`, and the payload is just the failed workflow's name and html_url. It re-states someone else's result and makes no claim of its own. It also cannot report a problem — `curl` is invoked without `-f`, so an HTTP 4xx/5xx from Slack still exits zero, meaning even the delivery is unverified."},
      evidence: [".github/workflows/slack-workflow-failure-notification.yml:20-29 (job-level if: conclusion == 'failure')",".github/workflows/slack-workflow-failure-notification.yml:31-45 (curl \"$SLACK_WORKFLOW_FAILURE_URL\" -X POST, no -f/--fail)"],
      confidence: 0.85,
    };
  },
};

export default probe;
export { probe };
