import { describe, expect, test } from "bun:test";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { COMMANDS, type Io, main, parseArgs, runCli } from "../src/cli";
import {
  createParallaxTools,
  parallaxTools,
  toolJsonSchema,
  toolSpecs,
  validate,
} from "../src/tools";
import type { ZodLike } from "../src/tools/schemas";

const CLI = fileURLToPath(new URL("../src/cli.ts", import.meta.url));
const TOOLS = fileURLToPath(new URL("../src/tools/index.ts", import.meta.url));

/**
 * The CLI is exercised as a SUBPROCESS, never in-process, for two reasons that
 * are both load-bearing rather than stylistic:
 *
 *   - Exit codes are the interface being tested, and a function's return value
 *     is not evidence about a process's exit status.
 *   - Every acceptance has to survive a process boundary. An `ActiveOntology` is
 *     branded with a module-private symbol and cannot be serialised, so the run
 *     re-mints it from an acceptance receipt. A same-process test would pass
 *     against a cached handle and prove nothing.
 */
async function cli(
  cwd: string,
  args: string[],
): Promise<{ code: number; stdout: string; stderr: string }> {
  const proc = Bun.spawn(["bun", "run", CLI, ...args], { cwd, stdout: "pipe", stderr: "pipe" });
  const [stdout, stderr] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
  ]);
  return { code: await proc.exited, stdout, stderr };
}

function workspace(): string {
  const dir = realpathSync(mkdtempSync(join(tmpdir(), "parallax-test-")));
  writeFileSync(join(dir, "a.ts"), "export const a = 1;\n");
  writeFileSync(join(dir, "b.ts"), "export const b = 2;\n");
  writeFileSync(join(dir, "readme.md"), "# ledger\n");
  // Directories are what the proposer turns into actions, and every numeric
  // action parameter becomes a blocking unit question.
  for (const sub of ["ledger", "notes"]) mkdirSync(join(dir, sub));
  return dir;
}

/** A refusal is a value. This is what "a typed error, not a stack trace" means. */
function parseRefusal(stderr: string): { code: string; reason: string; detail?: unknown } {
  expect(stderr).not.toContain("\n    at ");
  const parsed = JSON.parse(stderr.trim()) as { code: string; reason: string; detail?: unknown };
  expect(typeof parsed.code).toBe("string");
  expect(typeof parsed.reason).toBe("string");
  return parsed;
}

function collector(): Io & { stdout: string; stderr: string } {
  const io = {
    stdout: "",
    stderr: "",
    out(t: string) {
      io.stdout += t;
    },
    err(t: string) {
      io.stderr += t;
    },
  };
  return io;
}

// ---------------------------------------------------------------------------

describe("cli argument parsing", () => {
  test("a bare invocation names no command and lists the ones that exist", () => {
    const r = parseArgs([]);
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.error.code).toBe("NO_COMMAND");
    expect(r.error.detail?.commands).toContain("propose");
  });

  test("an unknown command is refused by name", () => {
    const r = parseArgs(["simulate"]);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("UNKNOWN_COMMAND");
  });

  test("--flag value and --flag=value produce the same parse", () => {
    const a = parseArgs(["run", "--ontology", "abc"]);
    const b = parseArgs(["run", "--ontology=abc"]);
    expect(a.ok && b.ok).toBe(true);
    if (!a.ok || !b.ok) return;
    expect(a.value.values.ontology).toEqual(["abc"]);
    expect(b.value.values.ontology).toEqual(["abc"]);
  });

  test("a boolean flag never swallows the next token", () => {
    const r = parseArgs(["run", "--governed", "--ontology", "abc"]);
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.value.flags.governed).toBe(true);
    expect(r.value.values.ontology).toEqual(["abc"]);
  });

  test("a boolean flag handed a value is refused rather than coerced", () => {
    const r = parseArgs(["run", "--ontology", "abc", "--json=1"]);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("BAD_FLAG_VALUE");
  });

  test("a value flag with nothing after it is refused", () => {
    const r = parseArgs(["run", "--ontology"]);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("BAD_FLAG_VALUE");
  });

  test("an unknown flag is refused, never silently ignored", () => {
    // A dropped --seed is a run at a seed nobody chose, reported as if it were.
    const r = parseArgs(["run", "--ontology", "abc", "--seeed", "7"]);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error.code).toBe("UNKNOWN_FLAG");
      expect(r.error.detail?.flag).toBe("seeed");
    }
  });

  test("a missing required flag names the flag and shows the usage", () => {
    // `receipt`, not `run`: --ontology is deliberately optional on run, so
    // using it here would test the divergence rather than the refusal.
    const r = parseArgs(["receipt"]);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error.code).toBe("MISSING_FLAG");
      expect(r.error.detail?.flag).toBe("run");
      expect(String(r.error.detail?.usage)).toContain("--run");
    }
  });

  test("run without --ontology parses, because the tool surface allows it too", () => {
    // parallax_run declares ontologyId optional -- "Omit for the most recent
    // acceptance." The CLI required it, which made "the agent is a user, not a
    // client library" false at the cheapest place to check it. The pair: the
    // optional flag parses, and a genuinely required one still refuses.
    const r = parseArgs(["run"]);
    expect(r.ok).toBe(true);
    const withId = parseArgs(["run", "--ontology", "abc"]);
    expect(withId.ok).toBe(true);
    expect(parseArgs(["receipt"]).ok).toBe(false);
  });

  test("repeated flags accumulate in the order they were given", () => {
    const r = parseArgs([
      "accept",
      "--proposal",
      "p",
      "--by",
      "me",
      "--answer",
      "1=kilos",
      "--answer",
      "2=units",
    ]);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.values.answer).toEqual(["1=kilos", "2=units"]);
  });

  test("--help routes to help instead of running the command it was typed after", () => {
    const r = parseArgs(["run", "--help"]);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.command).toBe("help");
  });

  test("a stray positional argument is refused rather than guessed at", () => {
    const r = parseArgs(["run", "extra"]);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("BAD_FLAG_VALUE");
  });

  test("every command in the usage text is a command that parses", () => {
    for (const name of ["propose", "status", "help"]) {
      expect(parseArgs([name]).ok).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------

describe("the exit-code contract", () => {
  test("success is 0 and writes nothing to stderr", async () => {
    const io = collector();
    expect(await main(["help"], io)).toBe(0);
    expect(io.stderr).toBe("");
    expect(io.stdout).toContain("parallax");
  });

  test("a typed refusal is 2 and prints a parseable error, not a stack trace", async () => {
    const io = collector();
    expect(await main(["receipt"], io)).toBe(2);
    const e = parseRefusal(io.stderr);
    expect(e.code).toBe("MISSING_FLAG");
    expect(io.stdout).toBe("");
  });

  test("an unexpected throw is 1 and is still JSON, coded UNEXPECTED", async () => {
    const io = collector();
    const exploding: Io = {
      out() {
        throw new Error("the terminal went away");
      },
      err: io.err,
    };
    expect(await runCli(["help"], exploding)).toBe(1);
    const e = parseRefusal(io.stderr);
    expect(e.code).toBe("UNEXPECTED");
    // The cause is carried as data; the reason stays a sentence safe to show.
    expect(JSON.stringify(e.detail)).toContain("the terminal went away");
  });

  test("2 and 1 are different codes, so a refusal is distinguishable from a defect", async () => {
    const refusal = collector();
    const defect = collector();
    const exploding: Io = {
      out() {
        throw new Error("boom");
      },
      err: defect.err,
    };
    expect(await runCli(["nope"], refusal)).toBe(2);
    expect(await runCli(["help"], exploding)).toBe(1);
  });

  test("--json on success emits the same envelope the tools return", async () => {
    const io = collector();
    expect(await main(["status", "--json"], io)).toBe(0);
    const parsed = JSON.parse(io.stdout) as { ok: boolean; value: { state: string } };
    expect(parsed.ok).toBe(true);
    expect(typeof parsed.value.state).toBe("string");
  });

  test("a real process exits 2 on a typed refusal", async () => {
    const dir = workspace();
    try {
      const r = await cli(dir, ["run", "--ontology", "deadbeef"]);
      expect(r.code).toBe(2);
      expect(parseRefusal(r.stderr).code).toBe("NO_ACCEPTED_ONTOLOGY");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 20000);
});

// ---------------------------------------------------------------------------

/**
 * The tool <-> command correspondence, written down ONCE and asserted below.
 *
 * The landing page and the README both claim `--root` is the ONE deliberate
 * divergence between the two surfaces. That claim used to live only in prose,
 * and prose does not fail when someone adds a tenth tool and no command for it.
 * Three tools shipped with no CLI counterpart at all -- render, parse-reply and
 * answer -- while the claim read as though the surfaces already matched.
 *
 * So the claim is a fixture now. Adding a tool without a command, or a command
 * without a tool, or a flag with no field behind it, goes red here.
 */
const TOOL_TO_COMMAND: Readonly<Record<string, string>> = {
  parallax_status: "status",
  parallax_propose_ontology: "propose",
  parallax_render_proposal: "render",
  parallax_parse_reply: "parse-reply",
  parallax_answer_questions: "answer",
  parallax_accept_ontology: "accept",
  parallax_reject_proposal: "reject",
  parallax_run: "run",
  parallax_receipt: "receipt",
};

/** `help` prints the command list; there is nothing for a tool to print it to. */
const CLI_ONLY_COMMANDS = new Set(["help"]);

/**
 * CLI flag -> tool schema field, where the two surfaces spell one thing twice.
 * A rename is not a divergence; a MISSING field is, and that is what is asserted.
 */
const FLAG_TO_FIELD: Readonly<Record<string, string>> = {
  proposal: "ref",
  ontology: "ontologyId",
  run: "runId",
  by: "acceptedBy",
  "chunk-chars": "chunkChars",
  "acknowledge-unmapped": "acknowledgeUnmapped",
  table: "tables",
  answer: "answers",
  "no-governed": "governed",
};

/**
 * Flags that exist on the CLI and deliberately have no tool field.
 *
 * Each one is a CONFINEMENT or FRAMING difference, never a capability:
 *   --json  how the same values are printed.
 *   --root  the documented divergence. An arbitrary root is safe at a terminal
 *           because the person typing the path is the confinement; inside a
 *           sandboxed session a derived path is denied and reads back as an
 *           empty directory, so it is absent from every tool schema.
 *   --out   writes the receipt to a path. The tool returns paths and never the
 *           page itself, on purpose: a receipt is tens of kilobytes.
 */
const CLI_ONLY_FLAGS: Readonly<Record<string, readonly string[]>> = {
  "*": ["json"],
  propose: ["root"],
  receipt: ["out"],
};

describe("the agent is a user: the capability sets correspond", () => {
  test("every tool has exactly one CLI command, and it exists", () => {
    const seen = new Set<string>();
    for (const s of toolSpecs()) {
      const command = TOOL_TO_COMMAND[s.name];
      expect(command, `${s.name} has no CLI command`).toBeDefined();
      expect(COMMANDS[command as string], `no command "${command}"`).toBeDefined();
      expect(seen.has(command as string), `${command} claimed twice`).toBe(false);
      seen.add(command as string);
    }
  });

  test("every CLI command is a tool, or is declared CLI-only", () => {
    const mapped = new Set(Object.values(TOOL_TO_COMMAND));
    for (const name of Object.keys(COMMANDS)) {
      if (CLI_ONLY_COMMANDS.has(name)) continue;
      expect(mapped.has(name), `command "${name}" has no tool behind it`).toBe(true);
    }
  });

  test("every CLI flag is a tool field, a rename of one, or a declared divergence", () => {
    for (const [toolName, command] of Object.entries(TOOL_TO_COMMAND)) {
      const schema = toolJsonSchema(toolName);
      const fields = new Set(Object.keys(schema?.properties ?? {}));
      const allowedHere = new Set([
        ...(CLI_ONLY_FLAGS["*"] ?? []),
        ...(CLI_ONLY_FLAGS[command] ?? []),
      ]);
      for (const flag of COMMANDS[command]?.allowed ?? []) {
        if (allowedHere.has(flag)) continue;
        const field = FLAG_TO_FIELD[flag] ?? flag;
        expect(fields.has(field), `--${flag} on "${command}" has no field on ${toolName}`).toBe(
          true,
        );
      }
    }
  });

  test("--root is the only capability-shaped divergence, and only on propose", () => {
    // Pinning the CONTENT of the allow-list, not just its use. Adding a third
    // entry here is a change to the claim the landing page makes, so it should
    // require editing a test that says so.
    const capabilityDivergences = Object.entries(CLI_ONLY_FLAGS)
      .filter(([command]) => command !== "*")
      .flatMap(([command, flags]) => flags.map((f) => `${command}:${f}`));
    expect(capabilityDivergences.sort()).toEqual(["propose:root", "receipt:out"]);
  });

  test("a command a human can reach records answers WITHOUT accepting", () => {
    // The capability `accept --answer` cannot express, and the reason `answer`
    // is a command rather than a flag: answering must not imply consent.
    expect(COMMANDS.answer).toBeDefined();
    expect(COMMANDS.answer?.allowed).not.toContain("by");
    expect(COMMANDS.accept?.required).toContain("by");
  });
});

describe("the agent is a user: one capability set, two surfaces", () => {
  test("every tool name is legal as both an AI SDK and an MCP tool name", () => {
    for (const s of toolSpecs()) expect(s.name).toMatch(/^[a-z][a-z0-9_]{0,63}$/);
  });

  test("no tool schema offers a path or a filesystem root", () => {
    // A derived path inside a confined session is DENIED, and a denied read comes
    // back as an empty directory rather than an error. Arbitrary roots stay on
    // the CLI, where the person typing the path is the confinement.
    for (const s of toolSpecs()) {
      const schema = toolJsonSchema(s.name);
      expect(schema).not.toBeNull();
      const keys = Object.keys(schema?.properties ?? {});
      expect(keys).not.toContain("root");
      expect(keys).not.toContain("cwd");
      expect(JSON.stringify(schema)).not.toContain("filesystem");
    }
  });

  test("the propose tool tells the caller in words not to derive a path", () => {
    const spec = toolSpecs().find((s) => s.name === "parallax_propose_ontology");
    expect(spec?.description).toContain("DO NOT PASS A PATH");
  });

  test("bad input comes back as a typed value, never as a throw", async () => {
    const tools = toolSpecs();
    const accept = tools.find((s) => s.name === "parallax_accept_ontology");
    expect(accept).toBeDefined();
    if (accept === undefined) return;
    const r = await accept.execute({ ref: "abc" });
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error.code).toBe("INVALID_INPUT");
      expect(r.error.detail?.field).toBe("acceptedBy");
    }
  });

  test("an unknown argument is refused rather than dropped", async () => {
    const run = toolSpecs().find((s) => s.name === "parallax_run");
    const r = await run?.execute({ horizen: 12 });
    expect(r?.ok).toBe(false);
    if (r !== undefined && !r.ok) expect(r.error.code).toBe("INVALID_INPUT");
  });

  test("a wrongly typed argument names the field", async () => {
    const run = toolSpecs().find((s) => s.name === "parallax_run");
    const r = await run?.execute({ seed: "forty-two" });
    expect(r?.ok).toBe(false);
    if (r !== undefined && !r.ok) expect(r.error.detail?.field).toBe("seed");
  });

  test("both surfaces refuse the same thing with the same code", async () => {
    // The claim is not "the codes look similar". It is that the same workspace,
    // asked the same question through a terminal and through a tool call, gives
    // back the same typed value -- so both are run here, against one directory.
    const dir = workspace();
    try {
      const fromCli = await cli(dir, ["run", "--ontology", "nothing-here"]);
      expect(fromCli.code).toBe(2);
      const cliError = parseRefusal(fromCli.stderr);
      expect(cliError.code).toBe("NO_ACCEPTED_ONTOLOGY");

      const probe = join(dir, "probe.ts");
      writeFileSync(
        probe,
        [
          `import { toolSpecs } from ${JSON.stringify(TOOLS)};`,
          "const spec = toolSpecs().find((s) => s.name === process.argv[2]);",
          "const r = await spec.execute(JSON.parse(process.argv[3]));",
          "console.log(JSON.stringify(r));",
        ].join("\n"),
      );
      const proc = Bun.spawn(
        ["bun", "run", probe, "parallax_run", JSON.stringify({ ontologyId: "nothing-here" })],
        { cwd: dir, stdout: "pipe", stderr: "pipe" },
      );
      const stdout = await new Response(proc.stdout).text();
      expect(await proc.exited).toBe(0);
      const fromTool = JSON.parse(stdout) as { ok: boolean; error: { code: string } };
      expect(fromTool.ok).toBe(false);
      expect(fromTool.error.code).toBe(cliError.code);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 30000);

  test("defaults are applied by the schema as well as by the handler", () => {
    const spec = toolSpecs().find((s) => s.name === "parallax_run");
    expect(spec).toBeDefined();
    if (spec === undefined) return;
    const r = validate(spec.input, {});
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.value.horizon).toBe(12);
      expect(r.value.seed).toBe(42);
      expect(r.value.governed).toBe(true);
      expect(r.value.trials).toBe(3);
    }
  });
});

// ---------------------------------------------------------------------------

describe("the AI SDK v6 adapters", () => {
  test("each tool carries a description, an input schema and an execute", () => {
    const tools = parallaxTools();
    expect(Object.keys(tools).length).toBe(toolSpecs().length);
    for (const t of Object.values(tools)) {
      expect(typeof t.description).toBe("string");
      expect(t.description.length).toBeGreaterThan(0);
      expect(typeof t.execute).toBe("function");
      expect(t.inputSchema).toBeDefined();
    }
  });

  test("the input schema satisfies the SDK's own isSchema predicate", () => {
    // Verified against ai@6.0.213: isSchema requires the globally registered
    // marker, a `jsonSchema` property and a `validate` key. Reproduced here so a
    // change in that contract fails as a test rather than at a model call.
    const marker = Symbol.for("vercel.ai.schema");
    for (const t of Object.values(parallaxTools())) {
      const schema = t.inputSchema as Record<string | symbol, unknown>;
      expect(typeof schema).toBe("object");
      expect(schema[marker]).toBe(true);
      expect("jsonSchema" in schema).toBe(true);
      expect("validate" in schema).toBe(true);
    }
  });

  test("the schema's validate mirrors the handler's own refusal", () => {
    const run = parallaxTools().parallax_run;
    expect(run).toBeDefined();
    if (run === undefined) return;
    const schema = run.inputSchema as {
      validate: (v: unknown) => { success: boolean; error?: Error };
    };
    expect(schema.validate({ seed: 42 }).success).toBe(true);
    const bad = schema.validate({ seed: "42" });
    expect(bad.success).toBe(false);
    expect(bad.error?.message).toContain("INVALID_INPUT");
  });

  test("the Zod route builds one tool per spec over the same handlers", () => {
    const { z, built } = fakeZod();
    const tools = createParallaxTools(z);
    expect(Object.keys(tools).length).toBe(toolSpecs().length);
    expect(built.length).toBeGreaterThan(0);
    for (const t of Object.values(tools)) {
      expect(typeof t.execute).toBe("function");
      expect(t.inputSchema).toBeDefined();
    }
  });

  test("the tool() helper is optional and changes nothing about the result", () => {
    const { z } = fakeZod();
    const seen: string[] = [];
    const tools = createParallaxTools(z, (d) => {
      seen.push(String(d.description).slice(0, 12));
      return d;
    });
    expect(seen.length).toBe(toolSpecs().length);
    expect(Object.keys(tools).length).toBe(toolSpecs().length);
  });
});

/**
 * The smallest object that satisfies `ZodLike`.
 *
 * Its existence is the point: `ZodLike` is structural, so neither `zod` nor `ai`
 * is a dependency of this package, and the 60 tests that predate this file stay
 * dependency-free.
 */
interface ZodStub {
  optional(): ZodStub;
  default(value: unknown): ZodStub;
  describe(text: string): ZodStub;
  min(n: number): ZodStub;
  max(n: number): ZodStub;
  int(): ZodStub;
}

function fakeZod(): { z: ZodLike; built: string[] } {
  const built: string[] = [];
  const stub = (kind: string): ZodStub => {
    built.push(kind);
    const self: ZodStub = {
      optional: () => self,
      default: () => self,
      describe: () => self,
      min: () => self,
      max: () => self,
      int: () => self,
    };
    return self;
  };
  const z: ZodLike = {
    object: () => stub("object"),
    array: () => stub("array"),
    string: () => stub("string"),
    number: () => stub("number"),
    boolean: () => stub("boolean"),
    enum: () => stub("enum"),
  };
  return { z, built };
}

// ---------------------------------------------------------------------------

describe("the whole gate, at a terminal", () => {
  test("propose, accept and run, each in its own process", async () => {
    const dir = workspace();
    try {
      const proposed = await cli(dir, ["propose", "--json"]);
      expect(proposed.code).toBe(0);
      const p = JSON.parse(proposed.stdout) as {
        value: { ref: string; blockingQuestions: Array<{ n: number }>; text: string };
      };
      expect(p.value.blockingQuestions.length).toBeGreaterThan(0);
      expect(p.value.text).toContain("Nothing runs until you accept it");

      // State lives under a DOT directory, so writing it does not change the
      // reading of the workspace that the proposal is bound to.
      expect(existsSync(join(dir, ".parallax", "pending"))).toBe(true);
      const again = await cli(dir, ["propose", "--json"]);
      const p2 = JSON.parse(again.stdout) as { value: { ref: string } };
      expect(p2.value.ref).toBe(p.value.ref);

      const bare = await cli(dir, ["accept", "--proposal", p.value.ref, "--by", "+57 300"]);
      expect(bare.code).toBe(2);
      expect(parseRefusal(bare.stderr).code).toBe("BLOCKING_QUESTIONS_OPEN");

      const answers = p.value.blockingQuestions.flatMap((q) => ["--answer", `${q.n}=units`]);
      const unacknowledged = await cli(dir, [
        "accept",
        "--proposal",
        p.value.ref,
        "--by",
        "+57 300",
        ...answers,
      ]);
      expect(unacknowledged.code).toBe(2);
      const gap = parseRefusal(unacknowledged.stderr);
      expect(gap.code).toBe("RECONCILIATION_UNACKNOWLEDGED");
      expect(
        (gap.detail as { unmappedFromContext: string[] }).unmappedFromContext.length,
      ).toBeGreaterThan(0);

      const accepted = await cli(dir, [
        "accept",
        "--proposal",
        p.value.ref,
        "--by",
        "+57 300",
        ...answers,
        "--acknowledge-unmapped",
        "--json",
      ]);
      expect(accepted.code).toBe(0);
      const a = JSON.parse(accepted.stdout) as {
        value: { ontologyId: string; acceptedByAuthenticated: boolean };
      };
      // Parallax records the claim; confining a thread to one sender is the
      // host's job, and the record must not let a reader confuse the two.
      expect(a.value.acceptedByAuthenticated).toBe(false);

      // A NEW process. Nothing survived in memory: the acceptance round-tripped
      // as data and the ontology was re-minted here.
      const ran = await cli(dir, ["run", "--ontology", a.value.ontologyId, "--json"]);
      expect(ran.code).toBe(0);
      const r = JSON.parse(ran.stdout) as {
        value: {
          runId: string;
          steps: number;
          seed: number;
          horizon: number;
          violations: { baseline: number; run: number };
          origins: { observed: number; simulated: number };
          certificate: { trials: number; effective: string };
          text: string;
        };
      };
      expect(r.value.steps).toBeGreaterThan(0);
      expect(r.value.seed).toBe(42);
      expect(r.value.horizon).toBe(12);
      expect(r.value.origins.observed).toBe(0);
      expect(r.value.origins.simulated).toBe(r.value.steps);
      expect(r.value.violations.run).toBeLessThanOrEqual(r.value.violations.baseline);
      // The certification caveat travels with the number it qualifies.
      expect(r.value.text).toContain("has not been proven pure");

      const out = join(dir, "receipt.html");
      const exported = await cli(dir, ["receipt", "--run", r.value.runId, "--out", out]);
      expect(exported.code).toBe(0);
      const html = readFileSync(out, "utf8");
      expect(html).toContain("Parallax run receipt");
      expect(html).toContain("simulated");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 60000);

  test("a run refuses after the context it was accepted against has changed", async () => {
    const dir = workspace();
    try {
      const proposed = await cli(dir, ["propose", "--json"]);
      const p = JSON.parse(proposed.stdout) as {
        value: { ref: string; blockingQuestions: Array<{ n: number }> };
      };
      const answers = p.value.blockingQuestions.flatMap((q) => ["--answer", `${q.n}=units`]);
      const accepted = await cli(dir, [
        "accept",
        "--proposal",
        p.value.ref,
        "--by",
        "tester",
        ...answers,
        "--acknowledge-unmapped",
        "--json",
      ]);
      const a = JSON.parse(accepted.stdout) as { value: { ontologyId: string } };

      // One new file with a new extension is enough: the proposal id is a hash
      // over what was read, so the acceptance is bound to that reading.
      writeFileSync(join(dir, "invoice.csv"), "a,b\n");
      const stale = await cli(dir, ["run", "--ontology", a.value.ontologyId]);
      expect(stale.code).toBe(2);
      expect(parseRefusal(stale.stderr).code).toBe("PROPOSAL_STALE");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 60000);

  test("a lost receipt is regenerated from the run's own parameters", async () => {
    const dir = workspace();
    try {
      const proposed = await cli(dir, ["propose", "--json"]);
      const p = JSON.parse(proposed.stdout) as {
        value: { ref: string; blockingQuestions: Array<{ n: number }> };
      };
      const answers = p.value.blockingQuestions.flatMap((q) => ["--answer", `${q.n}=units`]);
      const accepted = await cli(dir, [
        "accept",
        "--proposal",
        p.value.ref,
        "--by",
        "tester",
        ...answers,
        "--acknowledge-unmapped",
        "--json",
      ]);
      const a = JSON.parse(accepted.stdout) as { value: { ontologyId: string } };
      const ran = await cli(dir, ["run", "--ontology", a.value.ontologyId, "--json"]);
      const r = JSON.parse(ran.stdout) as { value: { runId: string; receiptPath: string } };

      rmSync(r.value.receiptPath);
      const out = join(dir, "again.html");
      const regenerated = await cli(dir, [
        "receipt",
        "--run",
        r.value.runId,
        "--out",
        out,
        "--json",
      ]);
      expect(regenerated.code).toBe(0);
      const v = JSON.parse(regenerated.stdout) as {
        value: { regenerated: boolean; bytes: number };
      };
      expect(v.value.regenerated).toBe(true);
      // A byte count that is actually a byte count.
      expect(v.value.bytes).toBe(Buffer.byteLength(readFileSync(out)));
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 60000);

  test("a rejected proposal is archived rather than deleted", async () => {
    const dir = workspace();
    try {
      const proposed = await cli(dir, ["propose", "--json"]);
      const p = JSON.parse(proposed.stdout) as { value: { ref: string } };
      const rejected = await cli(dir, [
        "reject",
        "--proposal",
        p.value.ref,
        "--reason",
        "wrong workspace",
        "--json",
      ]);
      expect(rejected.code).toBe(0);
      const v = JSON.parse(rejected.stdout) as { value: { archivedPath: string } };
      expect(existsSync(v.value.archivedPath)).toBe(true);
      const record = JSON.parse(readFileSync(v.value.archivedPath, "utf8")) as { reason: string };
      expect(record.reason).toBe("wrong workspace");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 30000);

  test("an empty workspace is reported as empty, with what to check instead", async () => {
    const dir = realpathSync(mkdtempSync(join(tmpdir(), "parallax-empty-")));
    try {
      const r = await cli(dir, ["propose"]);
      expect(r.code).toBe(2);
      const e = parseRefusal(r.stderr);
      expect(e.code).toBe("SOURCE_EMPTY");
      expect(JSON.stringify(e.detail)).toContain("workspace mount");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 20000);

  test("a --within that escapes the workspace is refused", async () => {
    const dir = workspace();
    try {
      const r = await cli(dir, ["propose", "--within", "../"]);
      expect(r.code).toBe(2);
      expect(parseRefusal(r.stderr).code).toBe("PATH_ESCAPES_WORKSPACE");
      const abs = await cli(dir, ["propose", "--within", "/etc"]);
      expect(parseRefusal(abs.stderr).code).toBe("PATH_ABSOLUTE");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 30000);
});

/**
 * Acceptance identity had no behavioural test at all -- only schema inspection --
 * and mutation testing found four surviving mutants here, every one of them a
 * promise the product makes out loud. `bun run mutants` regenerates the list.
 *
 * These drive the real CLI across a process boundary on purpose: an acceptance
 * is only worth anything if it survives one, and the accepted ontology is
 * re-minted from its receipt rather than handed over as a cached object.
 */
describe("acceptance identity", () => {
  async function proposalId(dir: string): Promise<string> {
    const r = await cli(dir, ["propose", "--json"]);
    expect(r.code).toBe(0);
    return (JSON.parse(r.stdout) as { value: { proposalId: string } }).value.proposalId;
  }

  async function acceptWith(
    dir: string,
    unit: string,
    by: string,
  ): Promise<{ ontologyId: string; idempotent: boolean }> {
    const pid = await proposalId(dir);
    const r = await cli(dir, [
      "accept",
      "--proposal",
      pid,
      "--by",
      by,
      "--answer",
      `1=${unit}`,
      "--answer",
      `2=${unit}`,
      "--acknowledge-unmapped",
      "--json",
    ]);
    expect(r.stderr).toBe("");
    expect(r.code).toBe(0);
    return (JSON.parse(r.stdout) as { value: { ontologyId: string; idempotent: boolean } }).value;
  }

  test("the same acceptance twice is idempotent, and says so", async () => {
    const dir = workspace();
    try {
      const first = await acceptWith(dir, "unidades", "carlos");
      const second = await acceptWith(dir, "unidades", "carlos");
      // A retry on a channel with no delivery receipts must not mint twice.
      expect(first.idempotent).toBe(false);
      expect(second.idempotent).toBe(true);
      expect(second.ontologyId).toBe(first.ontologyId);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("identity covers the answer VALUES, not just which slots were filled", async () => {
    const dir = workspace();
    try {
      const unidades = await acceptWith(dir, "unidades", "carlos");
      const cajas = await acceptWith(dir, "cajas", "carlos");
      // Same proposal, same slots, different thing said by the human. Colliding
      // these would run one acceptance under another's answers.
      expect(cajas.idempotent).toBe(false);
      expect(cajas.ontologyId).not.toBe(unidades.ontologyId);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("one person's acceptance is not reused for another person", async () => {
    const dir = workspace();
    try {
      const carlos = await acceptWith(dir, "unidades", "carlos");
      const ana = await acceptWith(dir, "unidades", "ana");
      expect(ana.idempotent).toBe(false);
      expect(ana.ontologyId).not.toBe(carlos.ontologyId);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("run with no --ontology uses the NEWEST acceptance, not the first ever made", async () => {
    const dir = workspace();
    try {
      const older = await acceptWith(dir, "unidades", "carlos");
      const newer = await acceptWith(dir, "cajas", "carlos");
      expect(newer.ontologyId).not.toBe(older.ontologyId);

      const r = await cli(dir, ["run", "--json"]);
      expect(r.code).toBe(0);
      const ran = (JSON.parse(r.stdout) as { value: { ontologyId: string } }).value;
      expect(ran.ontologyId).toBe(newer.ontologyId);
      expect(ran.ontologyId).not.toBe(older.ontologyId);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
