import type { OntologyProposal, OpenQuestion } from "../core/ontology";
import { fail, ok, type ParallaxError, type Result } from "../core/result";

/**
 * The accept gate, as a conversation.
 *
 * The interaction plane is WhatsApp: a message routes to a runtime that
 * operates on that sender's own workspace, articulates an ontology from what is
 * in it, and asks the human to accept it before anything runs. So the product's
 * central gate -- propose, then accept -- is not a form in a console. It is a
 * thread.
 *
 * Everything here is a PURE FUNCTION over a proposal. No I/O, no transport, no
 * Kapso import. That is deliberate and it is the same claim the rest of the
 * system makes: the agent is a user, not a client library, so the capability
 * has to exist independently of the surface that reaches it. The channel calls
 * these; a CLI calls the same ones; an HTTP handler calls the same ones. A
 * capability only reachable by one transport is a feature of the transport.
 */

/**
 * WhatsApp's body limit is 4096; the Kapso channel buffers a whole agent reply
 * and re-splits it at 3900 on paragraph-then-line boundaries. So chunking
 * shorter than that accomplishes nothing on this transport -- the parts are
 * reassembled into one buffer before delivery. The split here exists for
 * channels that do NOT buffer, and the size is a parameter because the limit
 * belongs to the transport, not to the proposal.
 */
export const WHATSAPP_CHUNK_CHARS = 3900;

export interface ChannelMessage {
  readonly text: string;
  readonly part: number;
  readonly of: number;
}

/**
 * Render a proposal for a channel that cannot edit a sent message.
 *
 * WhatsApp has no edit. Anything that streams by posting a placeholder and
 * revising it will appear to work in development and then throw in production
 * after the agent has already finished, so the whole message is composed first
 * and chunked, never progressively revised.
 */
export function renderProposal(
  p: OntologyProposal,
  chunkChars: number = WHATSAPP_CHUNK_CHARS,
): ChannelMessage[] {
  const lines: string[] = [];
  lines.push(`*${p.title}*`);
  lines.push(`Read from your workspace. Nothing runs until you accept it.`);
  lines.push("");

  lines.push(`*State* (${Object.keys(p.initial).length} fields)`);
  for (const [k, v] of Object.entries(p.initial)) {
    const from = p.evidence.find((e) => e.slot === `state.${k}`)?.from;
    lines.push(`  ${k} = ${JSON.stringify(v)}${from ? `  <- ${from}` : ""}`);
  }
  lines.push("");

  lines.push(`*Actions* (${p.actions.length})`);
  for (const a of p.actions) {
    lines.push(`  ${a.name}(${Object.keys(a.params).join(", ")})  by ${a.actor}`);
  }
  lines.push("");

  const blocking = p.openQuestions.filter((q) => q.blocking);
  const advisory = p.openQuestions.filter((q) => !q.blocking);

  if (blocking.length > 0) {
    lines.push(`*Before this can run* (${blocking.length})`);
    for (const [i, q] of blocking.entries()) lines.push(`  ${i + 1}. ${q.question}`);
    lines.push("");
  }
  if (advisory.length > 0) {
    lines.push(`*Worth answering*`);
    for (const q of advisory) lines.push(`  - ${q.question}`);
    lines.push("");
  }

  lines.push(
    blocking.length > 0
      ? `Reply with the numbered answers, then ACCEPT. Reply REJECT to discard.`
      : `Reply ACCEPT to activate, or REJECT to discard.`,
  );
  lines.push(`ref ${p.id.slice(0, 12)}`);

  return chunk(lines.join("\n"), chunkChars);
}

function chunk(text: string, limit: number): ChannelMessage[] {
  const paras = text.split("\n");
  const parts: string[] = [];
  let cur = "";
  for (const line of paras) {
    if (cur.length + line.length + 1 > limit && cur.length > 0) {
      parts.push(cur);
      cur = "";
    }
    cur += (cur ? "\n" : "") + line;
  }
  if (cur) parts.push(cur);
  return parts.map((text, i) => ({ text, part: i + 1, of: parts.length }));
}

export type ReplyIntent =
  | { kind: "accept"; answers: Map<string, string> }
  | { kind: "reject"; reason: string }
  | { kind: "answers"; answers: Map<string, string> }
  | { kind: "unclear" };

export type ReplyError = ParallaxError<"UNANSWERED_BLOCKING" | "UNKNOWN_QUESTION" | "EMPTY_REPLY">;

/**
 * Read a human reply into an intent.
 *
 * Tolerant of how people actually type on a phone: numbered answers with any of
 * `1.` `1)` `1:` `1 -`, accept spelled in English or Spanish, mixed case,
 * trailing chatter. Intolerant of ambiguity -- an unparseable reply returns
 * `unclear` rather than guessing, because guessing here silently activates an
 * ontology nobody agreed to.
 */
export function parseReply(raw: string, questions: OpenQuestion[]): ReplyIntent {
  const text = raw.trim();
  if (text.length === 0) return { kind: "unclear" };

  const blocking = questions.filter((q) => q.blocking);
  const answers = new Map<string, string>();

  for (const line of text.split("\n")) {
    const m = line.match(/^\s*(\d+)\s*[.):-]\s*(.+)$/);
    if (!m) continue;
    const idx = Number.parseInt(m[1] ?? "", 10) - 1;
    const body = (m[2] ?? "").trim();
    const q = blocking[idx];
    if (q && body.length > 0) answers.set(q.slot, body);
  }

  // \b is not reliable next to accented characters -- "sí" ends on a codepoint
  // JS regex does not class as a word character, so \bsí\b never matches. This
  // is the kind of thing that silently drops one language's acceptance word.
  const word = (alts: string) => new RegExp(`(?:^|[^\\p{L}])(?:${alts})(?![\\p{L}])`, "iu");
  const rejected = word("reject\\w*|rechaz\\w*|discard|no|cancel\\w*").test(text);
  const accepted = word("accept|acepto|aceptar|ok|yes|si|s\u00ed|dale|listo").test(text);

  // Reject wins over accept: if a reply contains both, the safe reading is the
  // one that does not start running things.
  if (rejected) return { kind: "reject", reason: text.slice(0, 200) };
  if (accepted) return { kind: "accept", answers };
  if (answers.size > 0) return { kind: "answers", answers };
  return { kind: "unclear" };
}

/**
 * Check an accept intent against the proposal before anything is activated.
 * Returns the slots to pass to `activate`, or names exactly what is missing --
 * so the bot can ask again for the one thing it lacks rather than restarting.
 */
export function resolveAccept(
  intent: ReplyIntent,
  p: OntologyProposal,
): Result<{ answered: string[]; answers: Map<string, string> }, ReplyError> {
  if (intent.kind !== "accept") {
    return fail("EMPTY_REPLY", "this reply did not accept the proposal");
  }
  const blocking = p.openQuestions.filter((q) => q.blocking);
  const missing = blocking.filter((q) => !intent.answers.has(q.slot));
  if (missing.length > 0) {
    return fail(
      "UNANSWERED_BLOCKING",
      `${missing.length} question(s) still need an answer before this can run`,
      { slots: missing.map((q) => q.slot), questions: missing.map((q) => q.question) },
    );
  }
  for (const slot of intent.answers.keys()) {
    if (!blocking.some((q) => q.slot === slot)) {
      return fail("UNKNOWN_QUESTION", `no open question at ${slot}`, { slot });
    }
  }
  return ok({ answered: [...intent.answers.keys()], answers: intent.answers });
}
