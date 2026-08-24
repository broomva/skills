import type { TableSpec } from "../core/ontology";
import { DEFAULT_DOMAIN, DOMAIN_KEYS } from "./domains";
import type { AnyErrorCode, ParallaxError } from "./errors";
import * as handlers from "./handlers";
import {
  type JsonSchemaObject,
  type ObjectSpec,
  toJsonSchema,
  toZod,
  validate,
  type ZodLike,
  type ZodTypeLike,
} from "./schemas";
import { WorkspaceNotWritableError } from "./state";

/**
 * Parallax as a set of tools an agent calls.
 *
 * The agent is a USER, not a client library. Everything a person can reach from
 * a phone or a terminal is reachable here, with the same codes and the same
 * values -- `src/tools/handlers.ts` is the single implementation and this file
 * is an adapter over it. If a capability existed only behind one of these
 * surfaces it would be a feature of the surface, not of the product.
 *
 * THREE CONSTRAINTS ARE ENCODED HERE RATHER THAN DOCUMENTED ELSEWHERE:
 *
 * 1. `proposeOntology` takes NO PATH. `root` falls back to `process.cwd()`,
 *    which is the directory the session was given. There is deliberately no
 *    `root` field and no `filesystem` kind in any schema below: in a confined
 *    session a derived absolute path is DENIED, and a denied read surfaces as
 *    an EMPTY DIRECTORY rather than an error. So a wrong path does not fail --
 *    it reads back as "your workspace has nothing in it", which is the failure
 *    that does not announce itself. Arbitrary roots stay on the CLI, where the
 *    person typing the path is the confinement.
 *
 * 2. An `ActiveOntology` CANNOT CROSS A PROCESS BOUNDARY. It is branded with a
 *    module-private symbol that `worldOf` checks at runtime, and it does not
 *    survive a JSON round-trip on purpose: trust cannot be serialised. On top of
 *    that, a session that answers a message is a NEW OS PROCESS each turn. So an
 *    acceptance round-trips as DATA -- an acceptance receipt -- and the ontology
 *    is re-minted, in-process, on every run. There is no handle cache here and
 *    there must never be one: a `Map<ontologyId, ActiveOntology>` passes every
 *    single-process test and evaporates in production.
 *
 * 3. NOTHING THROWS TO THE CALLER. Every `execute` returns
 *    `{ok:true,value}` or `{ok:false,error:{code,reason,detail?}}` -- the shape
 *    `src/core/result.ts` returns, unchanged. The `try/catch` in `runTool` is a
 *    backstop that should never fire, not the error mechanism.
 */

export type ToolEnvelope<T> =
  | { ok: true; value: T }
  | { ok: false; error: ParallaxError<AnyErrorCode> };

export interface ParallaxToolSpec {
  readonly name: string;
  readonly description: string;
  readonly input: ObjectSpec;
  readonly execute: (raw: unknown) => Promise<ToolEnvelope<unknown>>;
}

const REF_FIELD = {
  kind: "string",
  description:
    'The 12-hex ref printed at the bottom of a rendered proposal ("ref 9c41f0..."). Omit to use the most recent proposal in this workspace.',
  optional: true,
} as const;

const CHUNK_FIELD = {
  kind: "number",
  description:
    "Maximum characters per rendered message part. WhatsApp buffers and re-splits at 3900, so this only matters on a channel that does not buffer.",
  int: true,
  min: 200,
  max: 4096,
  default: 3900,
} as const;

const ANSWER_ROW = {
  n: { kind: "number", description: "The question number, starting at 1.", int: true, min: 1 },
  text: { kind: "string", description: "The human's answer, verbatim.", minLength: 1 },
} as const;

const ANSWERS_DESCRIPTION =
  "Answers keyed by the question NUMBER the human was shown. The stored proposal is the numbering authority; never renumber the questions yourself.";

const ANSWERS_FIELD = {
  kind: "objects",
  description: ANSWERS_DESCRIPTION,
  optional: true,
  fields: ANSWER_ROW,
} as const;

const ANSWERS_FIELD_REQUIRED = {
  kind: "objects",
  description: ANSWERS_DESCRIPTION,
  fields: ANSWER_ROW,
} as const;

/**
 * The tools, in the order a thread uses them.
 *
 * Descriptions carry the rules a model cannot infer from the values -- that a
 * path must not be derived, that reject beats accept, that a stored proposal's
 * numbering binds. A rule stated only in a design document is a rule the caller
 * never reads.
 */
const SPECS: ParallaxToolSpec[] = [
  spec(
    "parallax_status",
    [
      "Where this thread's Parallax flow currently stands, read from disk.",
      "Call this FIRST on any turn that mentions accepting, running, answering, or a previous proposal.",
      "Never infer the state from the conversation history: the state lives in the workspace, not in the messages, and a session is a new process every turn.",
    ].join(" "),
    { fields: {} },
    async () => handlers.status(),
  ),

  spec(
    "parallax_propose_ontology",
    [
      "Read this workspace and propose an ontology from what is actually in it: state fields with the evidence they were read from, actions, and the questions a human must answer before anything can run.",
      "Nothing runs as a result of calling this. Send the returned `text` to the human VERBATIM.",
      "DO NOT PASS A PATH. There is no path argument on purpose: the sandbox keys off the working directory, and a path you derive is DENIED, which comes back as an EMPTY DIRECTORY rather than an error -- so a wrong path looks exactly like an empty workspace.",
    ].join(" "),
    {
      fields: {
        kind: {
          kind: "string",
          description:
            'What kind of context this is. "agent-workspace" reads the working directory. "business-data" reads a table list you supply.',
          enum: ["agent-workspace", "business-data"],
          default: "agent-workspace",
        },
        within: {
          kind: "string",
          description:
            'Optional RELATIVE sub-path inside this workspace, e.g. "ledger". Never absolute, never containing "..". Omit for the workspace root.',
          optional: true,
        },
        tables: {
          kind: "objects",
          description: 'Required when kind is "business-data"; ignored otherwise.',
          optional: true,
          fields: {
            name: { kind: "string", description: "Table name.", minLength: 1 },
            columns: {
              kind: "objects",
              description:
                "The columns in that table. At least one is required. Declare a type where you know it; an undeclared column is left untyped and raises a blocking question rather than being guessed at.",
              fields: {
                name: { kind: "string", description: "Column name.", minLength: 1 },
                type: {
                  kind: "string",
                  description:
                    "What the column holds. Omit if you genuinely do not know -- that becomes a question a human answers, which is better than a wrong type that runs.",
                  enum: ["string", "number", "boolean", "date"],
                  optional: true,
                },
                origin: {
                  kind: "string",
                  description:
                    'Where this column\'s VALUES came from. "observed" means read from an artifact you can produce; "simulated" means concluded, matched or estimated. REQUIRED once rowCount claims rows exist -- provenance is assigned at birth and nothing downstream can recover it, so guessing here is permanent.',
                  enum: ["observed", "simulated"],
                  optional: true,
                },
              },
            },
            rowCount: {
              kind: "number",
              description:
                "How many rows you actually have. Omit for a schema with no data yet. Supplying it also answers the units question the proposer would otherwise have to ask.",
              optional: true,
            },
          },
        },
        chunkChars: CHUNK_FIELD,
      },
    },
    async (input) =>
      handlers.propose({
        kind: input.kind as "agent-workspace" | "business-data",
        ...(typeof input.within === "string" ? { within: input.within } : {}),
        ...(Array.isArray(input.tables) ? { tables: input.tables as TableSpec[] } : {}),
        chunkChars: input.chunkChars as number,
      }),
  ),

  spec(
    "parallax_render_proposal",
    [
      "Re-render a proposal that was already made, byte-for-byte, for a human who lost the message.",
      'This exists so that "send it again" is a re-render and never a re-summary: a paraphrased proposal that a human then accepts is an acceptance of the paraphrase.',
    ].join(" "),
    { fields: { ref: REF_FIELD, chunkChars: CHUNK_FIELD } },
    async (input) =>
      handlers.render({
        ...(typeof input.ref === "string" ? { ref: input.ref } : {}),
        chunkChars: input.chunkChars as number,
      }),
  ),

  spec(
    "parallax_parse_reply",
    [
      "Classify a human's reply against the pending proposal. Read-only: it records nothing, so calling it twice is never destructive.",
      "ALWAYS call this instead of deciding yourself whether a message means yes.",
      'The rules are not the ones a reader would apply: a reply containing ANY rejection word is a REJECTION even when it also contains an acceptance word, and a bare "no" anywhere in the message is a rejection word.',
      "If the classification looks wrong to you, ask the human rather than overriding it.",
    ].join(" "),
    {
      fields: {
        text: { kind: "string", description: "The human's message, verbatim.", minLength: 1 },
        ref: REF_FIELD,
      },
    },
    async (input) =>
      handlers.classifyReply({
        text: input.text as string,
        ...(typeof input.ref === "string" ? { ref: input.ref } : {}),
      }),
  ),

  spec(
    "parallax_answer_questions",
    [
      "Record answers to a proposal's blocking questions WITHOUT accepting it.",
      "Answers accumulate across turns, so a person can answer question 2 today and question 1 on Thursday.",
      "`n` indexes the questions as they were shown to the human; the stored proposal is the numbering authority.",
    ].join(" "),
    {
      fields: {
        ref: REF_FIELD,
        answers: ANSWERS_FIELD_REQUIRED,
      },
    },
    async (input) =>
      handlers.answer({
        ...(typeof input.ref === "string" ? { ref: input.ref } : {}),
        answers: input.answers as Array<{ n: number; text: string }>,
      }),
  ),

  spec(
    "parallax_accept_ontology",
    [
      "Accept a proposal so it can run. This is the gate the whole product is built around: nothing simulates until a human has accepted a model of their own context.",
      "Refuses while any blocking question is open, and refuses again if the executable domain ignores fields the human was shown as read from their context -- in that case relay the `unmappedFromContext` list to the human and only then call again with acknowledgeUnmapped set to true.",
      "`acceptedBy` is recorded as a CLAIM, not an authentication. The receipt says so.",
    ].join(" "),
    {
      fields: {
        ref: REF_FIELD,
        acceptedBy: {
          kind: "string",
          description:
            "The human accepting, as they identify themselves in this thread. Recorded as a claim; Parallax cannot authenticate it.",
          minLength: 1,
        },
        domain: {
          kind: "string",
          description:
            "Which registered domain supplies the executable transition and invariants. Those are CODE and never serialise, so acceptance references them by name.",
          enum: DOMAIN_KEYS,
          default: DEFAULT_DOMAIN,
        },
        answers: ANSWERS_FIELD,
        acknowledgeUnmapped: {
          kind: "boolean",
          description:
            "Set only after you have told the human which context fields the executable domain ignores.",
          default: false,
        },
      },
    },
    async (input) =>
      handlers.accept({
        ...(typeof input.ref === "string" ? { ref: input.ref } : {}),
        acceptedBy: input.acceptedBy as string,
        domain: input.domain as string,
        ...(Array.isArray(input.answers)
          ? { answers: input.answers as Array<{ n: number; text: string }> }
          : {}),
        acknowledgeUnmapped: input.acknowledgeUnmapped as boolean,
      }),
  ),

  spec(
    "parallax_reject_proposal",
    "Archive a proposal the human refused. Rejections are kept, never deleted: what was refused is part of the record.",
    {
      fields: {
        ref: REF_FIELD,
        reason: {
          kind: "string",
          description: "Why it was refused, in the human's own words where possible.",
          minLength: 1,
        },
      },
    },
    async (input) =>
      handlers.reject({
        ...(typeof input.ref === "string" ? { ref: input.ref } : {}),
        reason: input.reason as string,
      }),
  ),

  spec(
    "parallax_run",
    [
      "Roll an accepted ontology forward under a candidate policy and write a run receipt.",
      "The ontology is re-minted from its acceptance receipt on every call; if the workspace, the proposer or the domain moved since acceptance, this REFUSES rather than re-deriving silently.",
      "Relay the returned `text` verbatim. Do not restate any number from this result in your own words: a restated number is an invented number the moment it is wrong.",
      "The receipt itself is never returned here, only its path and URL.",
    ].join(" "),
    {
      fields: {
        ontologyId: {
          kind: "string",
          description: "Which accepted ontology to run. Omit for the most recent acceptance.",
          optional: true,
        },
        horizon: {
          kind: "number",
          description: "How many steps to project forward.",
          int: true,
          min: 1,
          max: 500,
          default: 12,
        },
        seed: {
          kind: "number",
          description: "The seed. Determinism is the product, so randomness is never ambient.",
          int: true,
          min: 0,
          default: 42,
        },
        governed: {
          kind: "boolean",
          description:
            "Fork the history at 0 and re-run under a shield that refuses any action whose post-state would violate an invariant.",
          default: true,
        },
        trials: {
          kind: "number",
          description:
            "How many identical probes the policy must reproduce before its declared reproducibility class is believed. A policy that passes has not been proven pure -- it has only failed to be caught.",
          int: true,
          min: 2,
          max: 20,
          default: 3,
        },
      },
    },
    async (input) =>
      handlers.run({
        ...(typeof input.ontologyId === "string" ? { ontologyId: input.ontologyId } : {}),
        horizon: input.horizon as number,
        seed: input.seed as number,
        governed: input.governed as boolean,
        trials: input.trials as number,
      }),
  ),

  spec(
    "parallax_receipt",
    [
      "Locate the receipt for a run. Returns paths and sizes, never the page itself -- a receipt is tens of kilobytes and belongs in a browser, not in a context window.",
      "If the rendered page is gone, it is regenerated deterministically from the recorded parameters.",
    ].join(" "),
    {
      fields: {
        runId: {
          kind: "string",
          description: "Which run. Omit for the most recent one in this workspace.",
          optional: true,
        },
      },
    },
    async (input) => {
      const r = await handlers.receipt(
        typeof input.runId === "string" ? { runId: input.runId } : {},
      );
      if (!r.ok) return r;
      const v = r.value;
      return {
        ok: true as const,
        value: {
          runId: v.runId,
          url: v.url,
          receiptPath: v.receiptPath,
          bytes: v.bytes,
          regenerated: v.regenerated,
          writtenTo: v.writtenTo,
        },
      };
    },
  ),
];

function spec(
  name: string,
  description: string,
  input: ObjectSpec,
  handler: (input: Record<string, unknown>) => Promise<ToolEnvelope<unknown>>,
): ParallaxToolSpec {
  return { name, description, input, execute: (raw) => runTool(name, input, handler, raw) };
}

/**
 * The one place a throw could reach a caller, and the place it is converted.
 *
 * An `execute` that throws produces a tool-error part whose text a model reads
 * as prose, and prose is not something a caller can branch on. So every failure
 * leaves here as a value, including the ones that were never supposed to happen.
 */
async function runTool(
  name: string,
  input: ObjectSpec,
  handler: (input: Record<string, unknown>) => Promise<ToolEnvelope<unknown>>,
  raw: unknown,
): Promise<ToolEnvelope<unknown>> {
  try {
    const checked = validate(input, raw ?? {});
    if (!checked.ok) return checked;
    return await handler(checked.value);
  } catch (e) {
    // Same mapping as the CLI backstop, for the same reason: a workspace that
    // cannot be written to is an expectable condition, not a defect in this
    // program. Both surfaces must name it identically -- a condition that is a
    // typed refusal on one surface and a crash on the other is exactly the
    // divergence the "agent is a user" claim rules out.
    if (e instanceof WorkspaceNotWritableError) {
      return {
        ok: false,
        error: {
          code: "WORKSPACE_NOT_WRITABLE",
          reason:
            "Parallax needs to write its thread state to .parallax/ in this directory, and the directory is not writable",
          detail: { root: e.root, cause: e.cause },
        },
      };
    }
    return {
      ok: false,
      error: {
        code: "UNEXPECTED",
        reason: `${name} threw instead of returning a typed error`,
        detail: { cause: e instanceof Error ? e.message : String(e) },
      },
    };
  }
}

/** Every tool, as data. Useful for an MCP adapter, a doc generator, or a test. */
export function toolSpecs(): readonly ParallaxToolSpec[] {
  return SPECS;
}

/** The JSON Schema for one tool's input, by name. */
export function toolJsonSchema(name: string): JsonSchemaObject | null {
  const found = SPECS.find((s) => s.name === name);
  return found === undefined ? null : toJsonSchema(found.input);
}

// ---------------------------------------------------------------------------
// AI SDK v6 adapters
// ---------------------------------------------------------------------------

/**
 * The AI SDK's marker for "this object is a schema".
 *
 * `Symbol.for` puts it in the cross-realm global registry, which is what lets a
 * schema built here be recognised by a copy of the SDK this package never
 * imported. Verified against ai@6.0.213, whose `isSchema` reads:
 *
 *   typeof value === "object" && value !== null && schemaSymbol in value &&
 *   value[schemaSymbol] === true && "jsonSchema" in value && "validate" in value
 *
 * -- so `validate` has to be PRESENT as a key, and `jsonSchema` is read directly.
 * This is how `parallaxTools()` produces genuine AI SDK tools with no dependency
 * on the `ai` package. A caller who would rather not rely on that marker should
 * use `createParallaxTools(z)` instead, which hands the SDK a Zod schema by the
 * documented route.
 */
const AI_SDK_SCHEMA_MARKER = Symbol.for("vercel.ai.schema");

export interface AiSdkSchema {
  readonly _type: unknown;
  readonly jsonSchema: JsonSchemaObject;
  readonly validate: (
    value: unknown,
  ) => { success: true; value: unknown } | { success: false; error: Error };
}

export interface AiSdkTool {
  readonly description: string;
  readonly inputSchema: unknown;
  readonly execute: (input: unknown) => Promise<ToolEnvelope<unknown>>;
}

function aiSdkSchema(input: ObjectSpec): AiSdkSchema {
  const schema: AiSdkSchema = {
    _type: undefined,
    jsonSchema: toJsonSchema(input),
    // The SDK rejects bad input before `execute` runs, so a schema failure
    // surfaces as the SDK's own tool-error rather than as our envelope. Every
    // `execute` re-validates anyway, which is the path a direct caller takes.
    validate: (value: unknown) => {
      const r = validate(input, value ?? {});
      return r.ok
        ? { success: true as const, value: r.value }
        : { success: false as const, error: new Error(`${r.error.code}: ${r.error.reason}`) };
    },
  };
  // Attached rather than written inline so the marker's key stays a plain symbol
  // instead of forcing a `unique symbol` declaration into the exported type.
  return Object.defineProperty(schema, AI_SDK_SCHEMA_MARKER, {
    value: true,
    enumerable: true,
  });
}

/**
 * The tools, ready to hand to `generateText`/`streamText` as `tools`.
 *
 *     import { generateText } from "ai";
 *     import { parallaxTools } from "./src/tools";
 *
 *     await generateText({ model, tools: parallaxTools(), prompt });
 *
 * No dependency on `ai` or `zod`. See `AI_SDK_SCHEMA_MARKER` for exactly which
 * part of the SDK's contract this leans on and how it was verified.
 */
export function parallaxTools(): Record<string, AiSdkTool> {
  const out: Record<string, AiSdkTool> = {};
  for (const s of SPECS) {
    out[s.name] = {
      description: s.description,
      inputSchema: aiSdkSchema(s.input),
      execute: s.execute,
    };
  }
  return out;
}

/**
 * `tool()` in the AI SDK is an identity function whose only job is type
 * inference -- verified in ai@6.0.213, where it is literally
 * `function tool(t) { return t; }`. Passing it changes nothing at runtime and
 * gives the caller the SDK's own inferred types; omitting it is safe.
 */
export type ToolHelper = (definition: Record<string, unknown>) => unknown;

/**
 * The same tools, with Zod input schemas.
 *
 *     import { tool } from "ai";
 *     import { z } from "zod";
 *     import { createParallaxTools } from "./src/tools";
 *
 *     const tools = createParallaxTools(z);
 *     // or, to get the SDK's inference:
 *     const tools = createParallaxTools(z, (d) => tool(d as never));
 *
 * `z` is typed structurally (see `ZodLike`), so neither `zod` nor `ai` is a
 * dependency of this package. Both routes call the SAME handlers and return the
 * SAME envelope; they differ only in how the input shape reaches the model.
 */
export function createParallaxTools(
  z: ZodLike,
  helper?: ToolHelper,
): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {};
  for (const s of SPECS) {
    const definition = {
      description: s.description,
      inputSchema: toZod(z, s.input) as ZodTypeLike,
      execute: s.execute,
    };
    out[s.name] = (helper === undefined ? definition : helper(definition)) as Record<
      string,
      unknown
    >;
  }
  return out;
}

export { DEFAULT_DOMAIN, DOMAIN_KEYS } from "./domains";
export type { AnyErrorCode, ParallaxError, Result, ToolErrorCode } from "./errors";
export * as handlers from "./handlers";
export { type Field, type ObjectSpec, toJsonSchema, validate, type ZodLike } from "./schemas";
