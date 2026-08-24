import type { ColumnSpec, ColumnType, TableSpec } from "./core/ontology";
import type { Origin } from "./core/provenance";
import { DEFAULT_DOMAIN, DOMAIN_KEYS } from "./tools/domains";
import { type AnyErrorCode, fail, ok, type ParallaxError, type Result } from "./tools/errors";
import * as handlers from "./tools/handlers";
import { WorkspaceNotWritableError } from "./tools/state";

/**
 * Parallax at a terminal.
 *
 * This file is the second proof of the same claim the tool surface makes: the
 * agent is a user, not a client library. It calls the SAME functions in
 * `src/tools/handlers.ts`, applies the SAME defaults, and prints the SAME error
 * codes -- so a capability is never something you can only reach one way, and a
 * refusal never depends on who asked.
 *
 * The one place the two surfaces deliberately DIVERGE is `--root`. An arbitrary
 * absolute root is safe here, because the person typing the path is the
 * confinement, and it is absent from every tool schema, because inside a
 * sandboxed session a derived path is denied and a denied read comes back as an
 * empty directory rather than an error. Same capability, different confinement.
 *
 * Exit codes:
 *   0  the command succeeded
 *   2  a typed refusal -- `{code, reason, detail?}` printed as JSON on stderr
 *   1  an unexpected throw -- also JSON on stderr, code UNEXPECTED
 *
 * 2 and 1 are different on purpose. A typed refusal is a NORMAL outcome of a
 * gate doing its job and a script can branch on the code; an unexpected throw is
 * a defect. Collapsing them into one non-zero code makes every refusal look like
 * a crash, which is how a fail-closed system gets described as flaky.
 */

type CliError = ParallaxError<AnyErrorCode>;

export interface Io {
  out(text: string): void;
  err(text: string): void;
}

const stdio: Io = {
  out: (t) => process.stdout.write(t),
  err: (t) => process.stderr.write(t),
};

// ---------------------------------------------------------------------------
// argument parsing
// ---------------------------------------------------------------------------

export interface Argv {
  readonly command: string;
  /** Every occurrence of every value flag, in order given. */
  readonly values: Readonly<Record<string, string[]>>;
  readonly flags: Readonly<Record<string, boolean>>;
}

/** Flags that never take a value. Anything else consumes the next token. */
const BOOLEAN_FLAGS = new Set(["json", "governed", "no-governed", "acknowledge-unmapped", "help"]);

export interface CommandSpec {
  readonly summary: string;
  readonly usage: string;
  readonly allowed: readonly string[];
  readonly required: readonly string[];
}

export const COMMANDS: Record<string, CommandSpec> = {
  propose: {
    summary: "Read a context and propose an ontology from what is actually in it.",
    usage:
      "parallax propose [--kind agent-workspace|filesystem|business-data] [--root <abs>] [--within <rel>] [--table <name>[#<rows>]:<col[:type[:origin]]>,...] [--json]",
    allowed: ["kind", "root", "within", "table", "chunk-chars", "json"],
    required: [],
  },
  render: {
    summary: "Re-render a proposal byte-for-byte for someone who lost it.",
    // A re-render, never a re-summary. A paraphrased proposal that a human then
    // accepts is an acceptance of the paraphrase, so this reads the STORED text
    // rather than recomputing one.
    usage: "parallax render [--proposal <id>] [--chunk-chars N] [--json]",
    allowed: ["proposal", "chunk-chars", "json"],
    required: [],
  },
  "parse-reply": {
    summary: "Classify a reply against the pending proposal. Records nothing.",
    usage: "parallax parse-reply --text <message> [--proposal <id>] [--json]",
    allowed: ["text", "proposal", "json"],
    required: ["text"],
  },
  answer: {
    summary: "Record answers to blocking questions WITHOUT accepting.",
    // The capability `accept --answer` cannot express: answers accumulate, so a
    // person can answer question 2 today and question 1 on Thursday. Folding
    // this into accept would make answering imply consent.
    usage: "parallax answer [--proposal <id>] --answer <slot|n>=<value> ... [--json]",
    allowed: ["proposal", "answer", "json"],
    required: ["answer"],
  },
  accept: {
    summary: "Accept a proposal so it can run. Nothing simulates before this.",
    usage:
      "parallax accept --proposal <id> [--answer <slot|n>=<value> ...] --by <who> [--domain <key>] [--acknowledge-unmapped] [--json]",
    allowed: ["proposal", "answer", "by", "domain", "acknowledge-unmapped", "json"],
    required: ["proposal", "by"],
  },
  run: {
    summary: "Roll an accepted ontology forward and write a run receipt.",
    // --ontology is optional here for the same reason `ontologyId` is optional
    // on parallax_run: omitted means the most recent acceptance. It was
    // required, which made "the agent is a user" false at the one place it is
    // cheapest to check, and left --root as the only DOCUMENTED divergence
    // while a second, undocumented one sat next to it.
    usage:
      "parallax run [--ontology <id>] [--horizon N] [--seed N] [--governed|--no-governed] [--trials N] [--json]",
    allowed: ["ontology", "horizon", "seed", "governed", "no-governed", "trials", "json"],
    required: [],
  },
  receipt: {
    summary: "Print or export the receipt for a run.",
    usage: "parallax receipt --run <id> [--out <path>] [--json]",
    allowed: ["run", "out", "json"],
    required: ["run"],
  },
  status: {
    summary: "Where this workspace's Parallax flow stands.",
    usage: "parallax status [--json]",
    allowed: ["json"],
    required: [],
  },
  reject: {
    summary: "Archive a proposal that was refused.",
    usage: "parallax reject [--proposal <id>] --reason <text> [--json]",
    allowed: ["proposal", "reason", "json"],
    required: ["reason"],
  },
  help: {
    summary: "This message.",
    usage: "parallax help",
    allowed: ["json"],
    required: [],
  },
};

/**
 * Tokenize, then check against the command's own flag list.
 *
 * An unknown flag is a refusal rather than something quietly ignored: a typo in
 * `--seed` that is silently dropped produces a run at a seed the caller did not
 * choose, and the report of that run is then wrong in a way nobody can see.
 */
export function parseArgs(argv: readonly string[]): Result<Argv, CliError> {
  const values: Record<string, string[]> = {};
  const flags: Record<string, boolean> = {};
  let command: string | null = null;

  for (let i = 0; i < argv.length; i++) {
    const token = argv[i] ?? "";
    if (token === "-h" || token === "--help") {
      flags.help = true;
      continue;
    }
    if (!token.startsWith("--")) {
      if (command === null) {
        command = token;
        continue;
      }
      return fail("BAD_FLAG_VALUE", `unexpected argument "${token}"`, { argument: token });
    }
    const body = token.slice(2);
    const eq = body.indexOf("=");
    const name = eq === -1 ? body : body.slice(0, eq);
    if (name.length === 0) {
      return fail("BAD_FLAG_VALUE", "a bare -- is not a flag", { argument: token });
    }
    if (BOOLEAN_FLAGS.has(name)) {
      if (eq !== -1) {
        return fail("BAD_FLAG_VALUE", `--${name} does not take a value`, { flag: name });
      }
      flags[name] = true;
      continue;
    }
    let value: string;
    if (eq !== -1) {
      value = body.slice(eq + 1);
    } else {
      const next = argv[i + 1];
      if (next === undefined || next.startsWith("--")) {
        return fail("BAD_FLAG_VALUE", `--${name} needs a value`, { flag: name });
      }
      value = next;
      i++;
    }
    const bucket = values[name];
    if (bucket === undefined) values[name] = [value];
    else bucket.push(value);
  }

  if (flags.help === true && command === null) command = "help";
  if (command === null) {
    return fail("NO_COMMAND", "no command given", { commands: Object.keys(COMMANDS) });
  }
  const spec = COMMANDS[command];
  if (spec === undefined) {
    return fail("UNKNOWN_COMMAND", `no command called "${command}"`, {
      given: command,
      commands: Object.keys(COMMANDS),
    });
  }
  if (flags.help === true) return ok({ command: "help", values: { for: [command] }, flags });

  for (const name of Object.keys(values)) {
    if (!spec.allowed.includes(name)) {
      return fail("UNKNOWN_FLAG", `${command} has no --${name}`, {
        command,
        flag: name,
        allowed: spec.allowed,
      });
    }
  }
  for (const name of Object.keys(flags)) {
    if (name !== "help" && !spec.allowed.includes(name)) {
      return fail("UNKNOWN_FLAG", `${command} has no --${name}`, {
        command,
        flag: name,
        allowed: spec.allowed,
      });
    }
  }
  for (const name of spec.required) {
    if ((values[name] ?? []).length === 0) {
      return fail("MISSING_FLAG", `${command} needs --${name}`, {
        command,
        flag: name,
        usage: spec.usage,
      });
    }
  }
  return ok({ command, values, flags });
}

function one(argv: Argv, name: string): string | undefined {
  return argv.values[name]?.[0];
}

function integer(argv: Argv, name: string): Result<number | undefined, CliError> {
  const raw = one(argv, name);
  if (raw === undefined) return ok(undefined);
  const n = Number(raw);
  if (!Number.isInteger(n)) {
    return fail("BAD_FLAG_VALUE", `--${name} must be a whole number`, { flag: name, given: raw });
  }
  return ok(n);
}

/**
 * `--answer <slot>=<value>`, where the left side is either the slot the proposal
 * named or the NUMBER the human was shown. Both address the same question; the
 * number is the one people actually have in front of them.
 */
function answers(argv: Argv): Result<Array<{ n?: number; slot?: string; text: string }>, CliError> {
  const out: Array<{ n?: number; slot?: string; text: string }> = [];
  for (const raw of argv.values.answer ?? []) {
    const eq = raw.indexOf("=");
    if (eq <= 0 || eq === raw.length - 1) {
      return fail("BAD_FLAG_VALUE", "--answer takes <slot>=<value> or <n>=<value>", {
        flag: "answer",
        given: raw,
      });
    }
    const key = raw.slice(0, eq);
    const text = raw.slice(eq + 1);
    out.push(/^\d+$/.test(key) ? { n: Number(key), text } : { slot: key, text });
  }
  return ok(out);
}

/** The declared column types, in one place. Mirrors the guard in src/hub/app.ts. */
const COLUMN_TYPES: readonly ColumnType[] = ["string", "number", "boolean", "date"];
function isColumnType(v: unknown): v is ColumnType {
  return typeof v === "string" && (COLUMN_TYPES as readonly string[]).includes(v);
}

/**
 * `--table <name>[#<rows>]:<col[:type[:origin]]>,...`, repeatable.
 *
 * Three shapes, in increasing order of what the caller is willing to claim:
 *
 *   --table leads:company,nit                      a schema. No data claimed.
 *   --table leads#40:company:string,nit:string     40 rows -- but see below.
 *   --table leads#40:company:string:observed,nit:string:observed
 *
 * The middle one is REFUSED, on purpose, by `proposeOntology`: claiming rows is
 * claiming knowledge of the world, and provenance is assigned at birth, so a row
 * count with untagged columns has already thrown the distinction away. It is
 * verbose to type -- that is the honest cost of asserting that forty records
 * exist.
 *
 * Everything after the first `:` is columns, and a column's own parts are split
 * on `:` too, which is why the row count hangs off the NAME with `#` rather than
 * adding a second delimiter to an already-overloaded one.
 */
function tables(argv: Argv): Result<TableSpec[], CliError> {
  const out: TableSpec[] = [];
  for (const raw of argv.values.table ?? []) {
    const colon = raw.indexOf(":");
    if (colon <= 0 || colon === raw.length - 1) {
      return fail("BAD_FLAG_VALUE", "--table takes <name>[#<rows>]:<col[:type[:origin]]>,...", {
        flag: "table",
        given: raw,
      });
    }

    let name = raw.slice(0, colon);
    let rowCount: number | undefined;
    const hash = name.indexOf("#");
    if (hash >= 0) {
      const digits = name.slice(hash + 1);
      name = name.slice(0, hash);
      if (!/^\d+$/.test(digits)) {
        return fail(
          "BAD_FLAG_VALUE",
          "--table row count must be a whole number, as <name>#<rows>",
          {
            flag: "table",
            given: raw,
          },
        );
      }
      rowCount = Number(digits);
    }
    if (name.length === 0) {
      return fail("BAD_FLAG_VALUE", "--table needs a table name before the colon", {
        flag: "table",
        given: raw,
      });
    }

    const columns: ColumnSpec[] = [];
    for (const chunk of raw.slice(colon + 1).split(",")) {
      const parts = chunk.split(":").map((s) => s.trim());
      const colName = parts[0] ?? "";
      // An empty segment is a REFUSAL, not a skip. `leads:company,,nit` used to
      // yield two columns and say nothing, so a typo silently produced a table
      // with a column missing -- and this file already refuses an unknown flag
      // for exactly that reason: something quietly dropped is a choice the
      // caller did not make and cannot see.
      if (colName.length === 0) {
        return fail("BAD_FLAG_VALUE", "--table has an empty column between commas", {
          flag: "table",
          given: raw,
        });
      }
      // Likewise a fourth positional part. `company:string:observed:GARBAGE`
      // parsed happily and threw GARBAGE away.
      if (parts.length > 3) {
        return fail(
          "BAD_FLAG_VALUE",
          `column "${colName}" has ${parts.length} parts; the grammar is <col>[:<type>[:<origin>]]`,
          { flag: "table", given: raw },
        );
      }
      const type = parts[1];
      const origin = parts[2];
      if (type !== undefined && type.length > 0 && !isColumnType(type)) {
        return fail(
          "BAD_FLAG_VALUE",
          `unknown column type "${type}"; use string, number, boolean or date`,
          {
            flag: "table",
            given: raw,
          },
        );
      }
      if (
        origin !== undefined &&
        origin.length > 0 &&
        origin !== "observed" &&
        origin !== "simulated"
      ) {
        return fail(
          "BAD_FLAG_VALUE",
          `column origin must be "observed" or "simulated", not "${origin}"`,
          {
            flag: "table",
            given: raw,
          },
        );
      }
      columns.push({
        name: colName,
        ...(type === undefined || type.length === 0 ? {} : { type: type as ColumnType }),
        ...(origin === undefined || origin.length === 0 ? {} : { origin: origin as Origin }),
      });
    }
    if (columns.length === 0) {
      return fail("BAD_FLAG_VALUE", "--table needs at least one column", {
        flag: "table",
        given: raw,
      });
    }
    out.push({ name, columns, ...(rowCount === undefined ? {} : { rowCount }) });
  }
  return ok(out);
}

// ---------------------------------------------------------------------------
// commands
// ---------------------------------------------------------------------------

const HELP = [
  "parallax -- simulation results you accept before they are active.",
  "",
  ...Object.entries(COMMANDS).map(([name, s]) => `  ${name.padEnd(12)} ${s.summary}`),
  "",
  ...Object.values(COMMANDS).map((s) => `  ${s.usage}`),
  "",
  "  --json          print the {ok, value} envelope instead of prose. The envelope",
  "                  and the prose carry the same values; only the framing differs.",
  "",
  "  exit 0  success",
  "  exit 2  a typed refusal; {code, reason, detail?} is printed as JSON on stderr",
  "  exit 1  an unexpected throw; also JSON on stderr, with code UNEXPECTED",
  "",
  `  domains: ${DOMAIN_KEYS.join(", ")} (default ${DEFAULT_DOMAIN})`,
  "",
  "  A run is governed by default, exactly as it is through the tool surface.",
  "  Pass --no-governed for the ungoverned baseline on its own.",
  "",
].join("\n");

export async function main(argv: readonly string[], io: Io = stdio): Promise<number> {
  const parsed = parseArgs(argv);
  if (!parsed.ok) return refuse(io, parsed.error);
  const a = parsed.value;
  const json = a.flags.json === true;

  switch (a.command) {
    case "help":
      io.out(`${HELP}\n`);
      return 0;

    case "status": {
      const r = handlers.status();
      if (!r.ok) return refuse(io, r.error);
      if (json) return emit(io, r.value);
      const v = r.value;
      io.out(`state       ${v.state}\n`);
      io.out(`workspace   ${v.cwd} (${v.readable ? `${v.entryCount} entries` : "UNREADABLE"})\n`);
      if (v.head !== null) {
        io.out(`pending     ${v.head.ref}  ${v.head.title}\n`);
        for (const q of v.head.blockingRemaining) io.out(`  open  ${q.n}. ${q.question}\n`);
      }
      for (const acc of v.accepted) {
        io.out(
          `accepted    ${acc.ontologyId.slice(0, 12)}  ${acc.domain}  by ${acc.acceptedBy}  ${
            acc.mintable ? "mintable" : `NOT MINTABLE (${acc.mintError?.code})`
          }\n`,
        );
      }
      for (const run of v.runs) {
        io.out(
          `run         ${run.runId.slice(0, 12)}  ${run.violations} violations  ${run.branchClass}  ${run.url}\n`,
        );
      }
      return 0;
    }

    case "propose": {
      const kind = one(a, "kind") ?? "agent-workspace";
      if (kind !== "agent-workspace" && kind !== "filesystem" && kind !== "business-data") {
        return refuse(
          io,
          fail("BAD_FLAG_VALUE", "--kind must be agent-workspace, filesystem or business-data", {
            flag: "kind",
            given: kind,
          }).error,
        );
      }
      const chunk = integer(a, "chunk-chars");
      if (!chunk.ok) return refuse(io, chunk.error);
      const t = tables(a);
      if (!t.ok) return refuse(io, t.error);
      const root = one(a, "root");
      const within = one(a, "within");
      const r = handlers.propose({
        kind,
        ...(root === undefined ? {} : { root }),
        ...(within === undefined ? {} : { within }),
        ...(t.value.length === 0 ? {} : { tables: t.value }),
        ...(chunk.value === undefined ? {} : { chunkChars: chunk.value }),
      });
      if (!r.ok) return refuse(io, r.error);
      if (json) return emit(io, r.value);
      io.out(`${r.value.text}\n\n`);
      io.out(`pending     ${r.value.pendingPath}\n`);
      io.out(`accept it   parallax accept --proposal ${r.value.ref} --by <who>\n`);
      return 0;
    }

    case "render": {
      const chunk = integer(a, "chunk-chars");
      if (!chunk.ok) return refuse(io, chunk.error);
      const r = handlers.render({
        ...(one(a, "proposal") === undefined ? {} : { ref: one(a, "proposal") as string }),
        ...(chunk.value === undefined ? {} : { chunkChars: chunk.value }),
      });
      if (!r.ok) return refuse(io, r.error);
      if (json) return emit(io, r.value);
      io.out(`${r.value.text}\n\n`);
      io.out(`accept it   parallax accept --proposal ${r.value.ref} --by <who>\n`);
      return 0;
    }

    case "parse-reply": {
      const r = handlers.classifyReply({
        text: one(a, "text") ?? "",
        ...(one(a, "proposal") === undefined ? {} : { ref: one(a, "proposal") as string }),
      });
      if (!r.ok) return refuse(io, r.error);
      if (json) return emit(io, r.value);
      const v = r.value;
      io.out(`intent      ${v.intent}\n`);
      if (v.reason !== null) io.out(`reason      ${v.reason}\n`);
      for (const ansr of v.answers) io.out(`  answer  ${ansr.n}. ${ansr.slot} = ${ansr.text}\n`);
      for (const q of v.stillOpen) io.out(`  open    ${q.n}. ${q.question}\n`);
      io.out(`can accept  ${v.canAccept}\n`);
      return 0;
    }

    case "answer": {
      const recorded = answers(a);
      if (!recorded.ok) return refuse(io, recorded.error);
      const r = handlers.answer({
        ...(one(a, "proposal") === undefined ? {} : { ref: one(a, "proposal") as string }),
        answers: recorded.value,
      });
      if (!r.ok) return refuse(io, r.error);
      if (json) return emit(io, r.value);
      const v = r.value;
      for (const rec of v.recorded) io.out(`recorded    ${rec.n}. ${rec.slot} = ${rec.text}\n`);
      for (const q of v.stillOpen) io.out(`open        ${q.n}. ${q.question}\n`);
      io.out(`can accept  ${v.canAccept}\n`);
      return 0;
    }

    case "accept": {
      const ans = answers(a);
      if (!ans.ok) return refuse(io, ans.error);
      const r = handlers.accept({
        ref: one(a, "proposal") ?? "",
        acceptedBy: one(a, "by") ?? "",
        domain: one(a, "domain") ?? DEFAULT_DOMAIN,
        ...(ans.value.length === 0 ? {} : { answers: ans.value }),
        acknowledgeUnmapped: a.flags["acknowledge-unmapped"] === true,
      });
      if (!r.ok) return refuse(io, r.error);
      if (json) return emit(io, r.value);
      const v = r.value;
      io.out(`ontology    ${v.ontologyId}${v.idempotent ? "  (already accepted)" : ""}\n`);
      io.out(`domain      ${v.domain} @ ${v.domainHash.slice(0, 12)}\n`);
      io.out(`accepted by ${v.acceptedBy}  (a claim, not an authentication)\n`);
      io.out(
        `mapping     ${v.reconciliation.covered.length} covered, ${v.reconciliation.unmappedFromContext.length} context field(s) ignored by the domain, ${v.reconciliation.domainOnly.length} domain-only\n`,
      );
      io.out(`run it      parallax run --ontology ${v.ontologyId.slice(0, 12)}\n`);
      return 0;
    }

    case "run": {
      const horizon = integer(a, "horizon");
      if (!horizon.ok) return refuse(io, horizon.error);
      const seed = integer(a, "seed");
      if (!seed.ok) return refuse(io, seed.error);
      const trials = integer(a, "trials");
      if (!trials.ok) return refuse(io, trials.error);
      if (a.flags.governed === true && a.flags["no-governed"] === true) {
        return refuse(
          io,
          fail("BAD_FLAG_VALUE", "--governed and --no-governed contradict each other", {}).error,
        );
      }
      const r = await handlers.run({
        // "" and undefined both mean "the newest acceptance" to findAcceptance,
        // so this stays a plain pass-through.
        ontologyId: one(a, "ontology") ?? "",
        ...(horizon.value === undefined ? {} : { horizon: horizon.value }),
        ...(seed.value === undefined ? {} : { seed: seed.value }),
        ...(trials.value === undefined ? {} : { trials: trials.value }),
        governed: a.flags["no-governed"] !== true,
      });
      if (!r.ok) return refuse(io, r.error);
      if (json) return emit(io, r.value);
      io.out(`${r.value.text}\n\n`);
      io.out(`receipt     ${r.value.receiptPath}\n`);
      io.out(`export it   parallax receipt --run ${r.value.runId.slice(0, 12)} --out run.html\n`);
      return 0;
    }

    case "receipt": {
      const r = await handlers.receipt({
        runId: one(a, "run") ?? "",
        ...(one(a, "out") === undefined ? {} : { out: one(a, "out") as string }),
      });
      if (!r.ok) return refuse(io, r.error);
      const v = r.value;
      if (json) {
        return emit(io, {
          runId: v.runId,
          url: v.url,
          receiptPath: v.receiptPath,
          bytes: v.bytes,
          regenerated: v.regenerated,
          writtenTo: v.writtenTo,
        });
      }
      if (v.writtenTo !== null) {
        io.out(`${v.writtenTo}  (${v.bytes} bytes${v.regenerated ? ", regenerated" : ""})\n`);
        return 0;
      }
      io.out(v.html);
      return 0;
    }

    case "reject": {
      const r = handlers.reject({
        ...(one(a, "proposal") === undefined ? {} : { ref: one(a, "proposal") as string }),
        reason: one(a, "reason") ?? "",
      });
      if (!r.ok) return refuse(io, r.error);
      if (json) return emit(io, r.value);
      io.out(`archived    ${r.value.archivedPath}\n`);
      return 0;
    }

    default:
      return refuse(
        io,
        fail("UNKNOWN_COMMAND", `no command called "${a.command}"`, {
          commands: Object.keys(COMMANDS),
        }).error,
      );
  }
}

function emit(io: Io, value: unknown): number {
  io.out(`${JSON.stringify({ ok: true, value }, null, 2)}\n`);
  return 0;
}

/**
 * A refusal is a VALUE, printed as JSON, never a stack trace.
 *
 * The same `{code, reason, detail?}` a tool call receives and an HTTP response
 * carries. Anything that has to be parsed out of English prose is not an
 * interface, and a caller cannot recover from what it cannot distinguish.
 */
function refuse(io: Io, error: CliError): number {
  io.err(`${JSON.stringify(error)}\n`);
  return 2;
}

/** Nothing above throws by design. This is what happens when something does. */
export async function runCli(argv: readonly string[], io: Io = stdio): Promise<number> {
  try {
    return await main(argv, io);
  } catch (e) {
    // A workspace that cannot be written to is an expectable condition, not a
    // defect in this program -- and it is the confinement posture the design
    // assumes, so it is the FIRST thing a tenant on a read-only mount hits.
    // Reporting it as UNEXPECTED told the operator Parallax is broken when the
    // accurate answer was that their directory is not writable; the two have
    // completely different remedies. Exit 2 (a typed refusal), not 1 (a defect).
    if (e instanceof WorkspaceNotWritableError) {
      io.err(
        `${JSON.stringify({
          code: "WORKSPACE_NOT_WRITABLE",
          reason:
            "Parallax needs to write its thread state to .parallax/ in this directory, and the directory is not writable",
          detail: { root: e.root, cause: e.cause },
        })}\n`,
      );
      return 2;
    }
    io.err(
      `${JSON.stringify({
        code: "UNEXPECTED",
        reason: "the command threw instead of returning a typed error",
        detail: { cause: e instanceof Error ? e.message : String(e) },
      })}\n`,
    );
    return 1;
  }
}

if (import.meta.main) {
  process.exitCode = await runCli(process.argv.slice(2));
}
