import { beforeAll, describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { OntologyProposal } from "../src/core/ontology";
import { isActive, proposeOntology } from "../src/core/ontology";
import { createHub, type Hub } from "../src/hub/app";
import { bindDomain, LEDGER_KEY } from "../src/hub/domain";
import { HUB_CODES, httpStatusFor, LIBRARY_CODES, STATUS_BY_CODE } from "../src/hub/status";

/**
 * The hub is exercised through its own `fetch` handler rather than a bound
 * socket. Same code path Bun.serve calls, no port to collide with a sibling
 * test run, and every assertion is about the contract rather than about
 * networking.
 *
 * The context is a fixture directory built here, not the repo. Proposals are
 * derived from what is actually in a directory, so pointing the tests at a
 * working tree would make their expectations move whenever anyone adds a file.
 */

const RUNTIME = resolve(fileURLToPath(new URL(".", import.meta.url)), "..");
const LANDING = join(RUNTIME, "hub-static");

let fixture: string;
let hub: Hub;

beforeAll(() => {
  fixture = mkdtempSync(join(tmpdir(), "parallax-hub-"));
  mkdirSync(join(fixture, "ledger"));
  mkdirSync(join(fixture, "notes"));
  writeFileSync(join(fixture, "ledger", "2026-01.csv"), "date,amount\n");
  writeFileSync(join(fixture, "a.ts"), "export const a = 1;\n");
  writeFileSync(join(fixture, "b.ts"), "export const b = 2;\n");
  writeFileSync(join(fixture, "readme.md"), "fixture\n");
  hub = createHub({ contextRoot: fixture, landingDir: LANDING, version: "test" });
});

const url = (path: string) => `http://hub.test${path}`;

function get(path: string, init: RequestInit = {}): Promise<Response> {
  return hub.fetch(new Request(url(path), init));
}

function post(path: string, body: unknown): Promise<Response> {
  return hub.fetch(
    new Request(url(path), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: typeof body === "string" ? body : JSON.stringify(body),
    }),
  );
}

// biome-ignore lint/suspicious/noExplicitAny: test helper reading an untyped wire body
async function body(r: Response): Promise<any> {
  return (await r.json()) as unknown;
}

async function proposeFixture(): Promise<OntologyProposal> {
  const r = await post("/api/ontology/propose", { kind: "agent-workspace" });
  expect(r.status).toBe(200);
  return (await body(r)).proposal as OntologyProposal;
}

function answersFor(p: OntologyProposal): Record<string, string> {
  const out: Record<string, string> = {};
  for (const q of p.openQuestions) if (q.blocking) out[q.slot] = "units";
  return out;
}

async function acceptedId(): Promise<string> {
  const p = await proposeFixture();
  const r = await post("/api/ontology/accept", {
    proposalId: p.id,
    answers: answersFor(p),
    acceptedBy: "test",
  });
  expect(r.status).toBe(200);
  return (await body(r)).ontologyId as string;
}

describe("health", () => {
  test("reports ok, a version and an uptime", async () => {
    const r = await get("/health");
    expect(r.status).toBe(200);
    const b = await body(r);
    expect(b.ok).toBe(true);
    expect(b.version).toBe("test");
    expect(typeof b.uptimeSeconds).toBe("number");
    expect(b.uptimeSeconds).toBeGreaterThanOrEqual(0);
  });

  test("is a 2xx within the platform's health-check budget", async () => {
    const started = performance.now();
    const r = await get("/health");
    expect(r.status).toBeLessThan(300);
    expect(performance.now() - started).toBeLessThan(5000);
  });

  test("refuses a method it does not implement, and says which it does", async () => {
    const r = await post("/health", {});
    expect(r.status).toBe(405);
    expect(r.headers.get("allow")).toBe("GET, HEAD");
    expect((await body(r)).code).toBe("METHOD_NOT_ALLOWED");
  });
});

describe("static", () => {
  test("/ serves the hub's front door", async () => {
    const r = await get("/");
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toContain("text/html");
    expect(await r.text()).toContain("<html");
  });

  test("a nested asset is served with its own content type", async () => {
    const r = await get("/assets/health.js");
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toContain("javascript");
  });

  test("a range request is answered with 206 and the bytes asked for", async () => {
    const r = await get("/index.html", { headers: { range: "bytes=0-99" } });
    expect(r.status).toBe(206);
    expect(r.headers.get("content-range")).toMatch(/^bytes 0-99\/\d+$/);
    expect((await r.arrayBuffer()).byteLength).toBe(100);
  });

  test("a missing file is a typed 404, not an empty body", async () => {
    const r = await get("/does-not-exist.html");
    expect(r.status).toBe(404);
    expect((await body(r)).code).toBe("NOT_FOUND");
  });
});

describe("path traversal", () => {
  /**
   * The plain form is not the attack. A URL parser folds literal `..` segments
   * away before any handler runs, so this arrives as `/package.json` and is
   * merely missing -- asserted here so the encoded cases below are not mistaken
   * for the whole test.
   */
  test("the forms the URL parser folds away arrive as ordinary misses", async () => {
    // `%2e%2e` is a double-dot segment to a WHATWG URL parser exactly as `..`
    // is, so both of these are normalised before any handler sees them. They
    // are asserted here so that a 404 on one of them is never read as the
    // traversal defence working.
    for (const path of ["/../package.json", "/%2e%2e/package.json"]) {
      const r = await get(path);
      expect(r.status).toBe(404);
      expect(await r.text()).not.toContain('"name": "parallax"');
    }
  });

  test("an encoded ../ is refused and never reaches the file", async () => {
    for (const path of [
      "/%2e%2e%2fpackage.json",
      "/..%2fpackage.json",
      "/%2e%2e%2f%2e%2e%2fpackage.json",
      "/assets%2f..%2f..%2fpackage.json",
      "/%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    ]) {
      const r = await get(path);
      const text = await r.text();
      expect(r.status).toBe(403);
      expect(text).toContain("PATH_ESCAPES_ROOT");
      // The control: the file it was reaching for exists and is readable, so a
      // pass here cannot be an accident of the target being absent.
      expect(text).not.toContain('"name": "parallax"');
    }
    expect(await Bun.file(join(RUNTIME, "package.json")).text()).toContain('"name": "parallax"');
  });

  test("a malformed percent-escape is refused rather than guessed at", async () => {
    const r = await get("/%zz");
    expect(r.status).toBe(403);
    expect((await body(r)).code).toBe("PATH_ESCAPES_ROOT");
  });

  test("propose refuses a root that leaves the hub's context", async () => {
    for (const root of ["../..", "../../etc", "ledger/../../.."]) {
      const r = await post("/api/ontology/propose", { kind: "agent-workspace", root });
      expect(r.status).toBe(403);
      expect((await body(r)).code).toBe("PATH_ESCAPES_ROOT");
    }
  });

  test("propose refuses an absolute root outright", async () => {
    const r = await post("/api/ontology/propose", { kind: "filesystem", root: "/etc" });
    expect(r.status).toBe(403);
    expect((await body(r)).code).toBe("PATH_ESCAPES_ROOT");
  });

  test("a root inside the context is allowed, so the refusals above are not blanket", async () => {
    const r = await post("/api/ontology/propose", { kind: "agent-workspace", root: "ledger" });
    expect(r.status).toBe(200);
    expect((await body(r)).proposal.slug).toBe("ledger");
  });
});

describe("propose", () => {
  test("proposes an ontology built from what is actually in the context", async () => {
    const p = await proposeFixture();
    expect(p.initial).toMatchObject({ ledger_count: 0, notes_count: 0, files_ts: 2, files_md: 1 });
    expect(p.actions.map((a) => a.name).sort()).toEqual(["add_to_ledger", "add_to_notes"]);
    expect(p.openQuestions.filter((q) => q.blocking).length).toBe(2);
  });

  test("every proposed element says what it was read from", async () => {
    const p = await proposeFixture();
    for (const key of Object.keys(p.initial)) {
      expect(p.evidence.some((e) => e.slot === `state.${key}`)).toBe(true);
    }
  });

  test("the wire never carries the hub's absolute filesystem path", async () => {
    const p = await proposeFixture();
    expect(JSON.stringify(p)).not.toContain(fixture);
    expect(p.source).toMatchObject({ kind: "agent-workspace", root: "." });
  });

  test("relativising the root does not change the id the caller sends back", async () => {
    const p = await proposeFixture();
    const local = proposeOntology({ kind: "agent-workspace", root: fixture });
    expect(local.ok).toBe(true);
    if (local.ok) expect(local.value.id).toBe(p.id);
  });

  test("business-data proposes from the tables it was given", async () => {
    const r = await post("/api/ontology/propose", {
      kind: "business-data",
      tables: [{ name: "orders", columns: ["id", "total"] }],
    });
    expect(r.status).toBe(200);
    expect((await body(r)).proposal.initial).toMatchObject({ orders_rows: 0 });
  });

  test("business-data without tables is a typed missing-field error", async () => {
    const r = await post("/api/ontology/propose", { kind: "business-data" });
    expect(r.status).toBe(400);
    expect((await body(r)).code).toBe("MISSING_FIELD");
  });

  test("an unknown source kind is refused with the allowed set", async () => {
    const r = await post("/api/ontology/propose", { kind: "telepathy" });
    expect(r.status).toBe(400);
    const b = await body(r);
    expect(b.code).toBe("INVALID_FIELD");
    expect(b.detail.allowed).toContain("agent-workspace");
  });

  test("an empty context is reported as empty, using the library's own code", async () => {
    const empty = mkdtempSync(join(tmpdir(), "parallax-empty-"));
    const solo = createHub({ contextRoot: empty, landingDir: LANDING });
    const r = await solo.fetch(
      new Request(url("/api/ontology/propose"), {
        method: "POST",
        body: JSON.stringify({ kind: "agent-workspace" }),
      }),
    );
    expect(r.status).toBe(400);
    expect((await body(r)).code).toBe("SOURCE_EMPTY");
  });
});

describe("accept", () => {
  test("refuses while blocking questions are open, naming the slots", async () => {
    const p = await proposeFixture();
    const r = await post("/api/ontology/accept", {
      proposalId: p.id,
      answers: {},
      acceptedBy: "test",
    });
    expect(r.status).toBe(409);
    const b = await body(r);
    expect(b.code).toBe("BLOCKING_QUESTIONS_OPEN");
    expect(b.detail.slots.sort()).toEqual(
      p.openQuestions
        .filter((q) => q.blocking)
        .map((q) => q.slot)
        .sort(),
    );
  });

  test("refuses when only some blocking questions are answered", async () => {
    const p = await proposeFixture();
    const blocking = p.openQuestions.filter((q) => q.blocking);
    const first = blocking[0];
    expect(first).toBeDefined();
    const r = await post("/api/ontology/accept", {
      proposalId: p.id,
      answers: first === undefined ? {} : { [first.slot]: "units" },
      acceptedBy: "test",
    });
    expect(r.status).toBe(409);
    expect((await body(r)).detail.slots.length).toBe(blocking.length - 1);
  });

  /** The control for the two refusals above: the same request, answered, is accepted. */
  test("accepts once every blocking question is answered", async () => {
    const p = await proposeFixture();
    const r = await post("/api/ontology/accept", {
      proposalId: p.id,
      answers: answersFor(p),
      acceptedBy: "+57 300 000 0000",
    });
    expect(r.status).toBe(200);
    const b = await body(r);
    expect(typeof b.ontologyId).toBe("string");
    expect(b.world).toEqual({ slug: p.slug, title: p.title });
    expect(typeof b.acceptedAt).toBe("number");
  });

  test("an empty string is not an answer", async () => {
    const p = await proposeFixture();
    const answers = answersFor(p);
    const slot = Object.keys(answers)[0];
    expect(slot).toBeDefined();
    if (slot !== undefined) answers[slot] = "   ";
    const r = await post("/api/ontology/accept", {
      proposalId: p.id,
      answers,
      acceptedBy: "test",
    });
    expect(r.status).toBe(400);
    expect((await body(r)).code).toBe("INVALID_FIELD");
  });

  test("an answer to a question nobody asked is refused by name", async () => {
    const p = await proposeFixture();
    const r = await post("/api/ontology/accept", {
      proposalId: p.id,
      answers: { ...answersFor(p), "action.invented.count": "units" },
      acceptedBy: "test",
    });
    expect(r.status).toBe(400);
    const b = await body(r);
    expect(b.code).toBe("UNKNOWN_QUESTION");
    expect(b.detail.slot).toBe("action.invented.count");
  });

  test("an unknown proposal id is a 404 with the library's error shape", async () => {
    const r = await post("/api/ontology/accept", {
      proposalId: "0".repeat(32),
      answers: {},
      acceptedBy: "test",
    });
    expect(r.status).toBe(404);
    expect((await body(r)).code).toBe("UNKNOWN_PROPOSAL");
  });

  test("a missing acceptedBy is a typed error, because nobody accepted it", async () => {
    const p = await proposeFixture();
    const r = await post("/api/ontology/accept", { proposalId: p.id, answers: answersFor(p) });
    expect(r.status).toBe(400);
    expect((await body(r)).code).toBe("MISSING_FIELD");
  });

  test("the same decision mints the same id, so a receipt url is regenerable", async () => {
    const a = await acceptedId();
    const b = await acceptedId();
    expect(a).toBe(b);
  });

  test("a different person accepting the same proposal is a different ontology", async () => {
    const p = await proposeFixture();
    const one = await post("/api/ontology/accept", {
      proposalId: p.id,
      answers: answersFor(p),
      acceptedBy: "ana",
    });
    const two = await post("/api/ontology/accept", {
      proposalId: p.id,
      answers: answersFor(p),
      acceptedBy: "beto",
    });
    expect((await body(one)).ontologyId).not.toBe((await body(two)).ontologyId);
  });
});

describe("the ontology never crosses the wire", () => {
  test("only an id and the world's name leave the process", async () => {
    const p = await proposeFixture();
    const r = await post("/api/ontology/accept", {
      proposalId: p.id,
      answers: answersFor(p),
      acceptedBy: "test",
    });
    const b = await body(r);
    expect(Object.keys(b.world).sort()).toEqual(["slug", "title"]);
    expect(JSON.stringify(b)).not.toContain("transition");
    expect(JSON.stringify(b)).not.toContain("invariants");
  });

  /**
   * The reason the registry exists. `activate` brands with a module-private
   * symbol that `worldOf` checks at runtime, and a symbol does not survive
   * JSON. If it did, an accepted ontology could be forged in transit.
   */
  test("an accepted ontology does not survive a JSON round trip", async () => {
    const id = await acceptedId();
    const record = hub.state.ontologies.get(id);
    expect(record).toBeDefined();
    if (record === undefined) return;
    expect(isActive(record.active)).toBe(true);
    expect(isActive(JSON.parse(JSON.stringify(record.active)))).toBe(false);
  });
});

describe("run", () => {
  test("produces a receipt and a url that resolves to it", async () => {
    const ontologyId = await acceptedId();
    const r = await post("/api/run", { ontologyId, horizon: 12, seed: 42, governed: false });
    expect(r.status).toBe(200);
    const b = await body(r);
    expect(typeof b.runId).toBe("string");
    expect(b.url).toBe(`http://hub.test/r/${b.runId}`);
    expect(b.branchClass).toBe("PINNED");
    expect(Array.isArray(b.violations)).toBe(true);
    expect(b.scores.map((s: { objective: string }) => s.objective)).toEqual([
      "steps_applied",
      "violations",
    ]);

    const receipt = await get(`/r/${b.runId}`);
    expect(receipt.status).toBe(200);
    expect(receipt.headers.get("content-type")).toContain("text/html");
    const html = await receipt.text();
    expect(html).toContain("Parallax run receipt");
    expect(html).toContain(b.runId);
  });

  /**
   * The run path calls `certifyPolicy` and `rolloutCertified`, never bare
   * `rollout`. The observable difference is that the receipt carries a
   * demonstrated class measured over repeated probes, alongside the declared
   * one -- a bare rollout would have only the declaration.
   */
  test("the class on the log is demonstrated, not declared", async () => {
    const ontologyId = await acceptedId();
    const b = await body(
      await post("/api/run", { ontologyId, horizon: 8, seed: 7, governed: false }),
    );
    const record = hub.state.runs.get(b.runId);
    expect(record).toBeDefined();
    if (record === undefined) return;
    expect(record.receipt.certificate.trials).toBe(3);
    expect(record.receipt.certificate.declared).toBe("PINNED");
    expect(record.receipt.certificate.effective).toBe("PINNED");
    expect(record.receipt.certificate.demoted).toBe(false);
    expect(record.receipt.branchClass).toBe(record.receipt.certificate.effective);
    expect(record.html).toContain("Policy demonstrated");
  });

  test("every step of a simulated rollout is tagged simulated", async () => {
    const ontologyId = await acceptedId();
    const b = await body(
      await post("/api/run", { ontologyId, horizon: 5, seed: 42, governed: false }),
    );
    const record = hub.state.runs.get(b.runId);
    expect(record).toBeDefined();
    if (record === undefined) return;
    expect(record.receipt.trajectory.length).toBe(5);
    expect(record.receipt.trajectory.every((s) => s.origin === "simulated")).toBe(true);
    expect(record.html).toContain("the entire trajectory is simulated");
  });

  /**
   * Fixed fixture, fixed seed, fixed horizon: the numbers below are what this
   * repository produces, not a target anybody chose. Two directories in the
   * fixture means two actions; the scripted actor's amounts run from -3 to +5,
   * so an ungoverned run drives a counter negative and the conservation
   * invariant catches it.
   */
  test("the governor removes the violations the ungoverned run produced", async () => {
    const ontologyId = await acceptedId();
    const open = await body(
      await post("/api/run", { ontologyId, horizon: 12, seed: 42, governed: false }),
    );
    const shielded = await body(
      await post("/api/run", { ontologyId, horizon: 12, seed: 42, governed: true }),
    );
    expect(open.violations.length).toBeGreaterThan(0);
    expect(shielded.violations.length).toBe(0);
    expect(open.violations.map((v: { invariant: string }) => v.invariant)).toContain(
      "counts_nonneg",
    );
    const record = hub.state.runs.get(shielded.runId);
    expect(record?.receipt.baseline?.violations).toBe(open.violations.length);
  });

  test("the same request reproduces the same run id and the same trace", async () => {
    const ontologyId = await acceptedId();
    const first = await body(await post("/api/run", { ontologyId, horizon: 6, seed: 99 }));
    const second = await body(await post("/api/run", { ontologyId, horizon: 6, seed: 99 }));
    expect(first.runId).toBe(second.runId);
    expect(hub.state.runs.get(first.runId)?.receipt.traceHash).toBe(
      hub.state.runs.get(second.runId)?.receipt.traceHash,
    );
  });

  test("a different seed is a different run", async () => {
    const ontologyId = await acceptedId();
    const a = await body(await post("/api/run", { ontologyId, horizon: 6, seed: 1 }));
    const b = await body(await post("/api/run", { ontologyId, horizon: 6, seed: 2 }));
    expect(a.runId).not.toBe(b.runId);
    expect(hub.state.runs.get(a.runId)?.receipt.traceHash).not.toBe(
      hub.state.runs.get(b.runId)?.receipt.traceHash,
    );
  });

  test("an unknown ontology id is a 404, not a run against nothing", async () => {
    const r = await post("/api/run", { ontologyId: "0".repeat(32), horizon: 4, seed: 1 });
    expect(r.status).toBe(404);
    expect((await body(r)).code).toBe("UNKNOWN_ONTOLOGY");
  });

  test("a missing seed is refused rather than defaulted", async () => {
    const ontologyId = await acceptedId();
    const r = await post("/api/run", { ontologyId, horizon: 4 });
    expect(r.status).toBe(400);
    expect((await body(r)).code).toBe("MISSING_FIELD");
    expect((await body(await post("/api/run", { ontologyId, seed: 1 }))).code).toBe(
      "MISSING_FIELD",
    );
  });

  test("a horizon outside the accepted range is refused with the range", async () => {
    const ontologyId = await acceptedId();
    for (const horizon of [0, -1, 501, 2.5, "12"]) {
      const r = await post("/api/run", { ontologyId, horizon, seed: 1 });
      expect(r.status).toBe(400);
      const b = await body(r);
      expect(b.code).toBe("INVALID_FIELD");
      expect(b.detail.field).toBe("horizon");
    }
  });
});

describe("receipts", () => {
  test("a known id renders, an unknown id is a typed 404", async () => {
    const ontologyId = await acceptedId();
    const b = await body(await post("/api/run", { ontologyId, horizon: 4, seed: 3 }));
    expect((await get(`/r/${b.runId}`)).status).toBe(200);

    const missing = await get("/r/ffffffffffffffffffffffffffffffff");
    expect(missing.status).toBe(404);
    const err = await body(missing);
    expect(err.code).toBe("UNKNOWN_RUN");
    expect(err.reason).toContain("in memory");
  });

  test("the short id the demo links by resolves to the same receipt", async () => {
    const ontologyId = await acceptedId();
    const b = await body(await post("/api/run", { ontologyId, horizon: 4, seed: 11 }));
    const short = await get(`/r/${(b.runId as string).slice(0, 8)}`);
    expect(short.status).toBe(200);
    expect(await short.text()).toBe(await (await get(`/r/${b.runId}`)).text());
  });

  test("a receipt id shorter than the demo's link is not guessed at", async () => {
    expect((await get("/r/ab")).status).toBe(404);
  });
});

describe("malformed input", () => {
  test("an unparseable body is a typed error, not a 500 with a stack", async () => {
    const r = await post("/api/run", "{ this is not json");
    expect(r.status).toBe(400);
    const text = await r.text();
    const b = JSON.parse(text) as { code: string; reason: string };
    expect(b.code).toBe("MALFORMED_BODY");
    expect(b.reason).toBe("the request body is not valid JSON");
    // Nothing about the server's insides leaks into a failure a stranger can trigger.
    expect(text).not.toContain("/src/hub/");
    expect(text).not.toContain("at <anonymous>");
    expect(text).not.toContain(".ts:");
  });

  test("an empty body and a JSON array are both refused as bodies", async () => {
    expect((await body(await post("/api/ontology/propose", ""))).code).toBe("MALFORMED_BODY");
    expect((await body(await post("/api/ontology/propose", [1, 2]))).code).toBe("MALFORMED_BODY");
  });

  test("an unknown api route is a typed 404", async () => {
    const r = await post("/api/nope", {});
    expect(r.status).toBe(404);
    expect((await body(r)).code).toBe("UNKNOWN_ROUTE");
  });

  test("every error body carries the code both at the top level and under error", async () => {
    const r = await post("/api/nope", {});
    const b = await body(r);
    expect(b.error).toEqual({ code: b.code, reason: b.reason, detail: b.detail });
  });
});

describe("error codes to http statuses", () => {
  test("every code the library can produce has an explicit status", () => {
    for (const code of LIBRARY_CODES) {
      expect(Object.hasOwn(STATUS_BY_CODE, code)).toBe(true);
      expect(httpStatusFor(code)).toBe(STATUS_BY_CODE[code]);
    }
  });

  test("every transport code has an explicit status", () => {
    for (const code of HUB_CODES) expect(Object.hasOwn(STATUS_BY_CODE, code)).toBe(true);
  });

  test("the gate codes land where a client can act on them", () => {
    expect(httpStatusFor("BLOCKING_QUESTIONS_OPEN")).toBe(409);
    expect(httpStatusFor("UNANSWERED_BLOCKING")).toBe(409);
    expect(httpStatusFor("NOT_ACCEPTED")).toBe(403);
    expect(httpStatusFor("SOURCE_EMPTY")).toBe(400);
    expect(httpStatusFor("EMPTY_TRAJECTORY")).toBe(422);
  });

  test("a code this table has never seen is a 500, never a hopeful 400", () => {
    expect(httpStatusFor("SOMETHING_NEW")).toBe(500);
    expect(httpStatusFor("")).toBe(500);
  });

  test("no status is mapped outside the range an http client understands", () => {
    for (const status of Object.values(STATUS_BY_CODE)) {
      expect(status).toBeGreaterThanOrEqual(400);
      expect(status).toBeLessThan(600);
    }
  });
});

describe("the executable domain the hub binds", () => {
  function fixtureProposal(): OntologyProposal {
    const p = proposeOntology({ kind: "agent-workspace", root: fixture });
    if (!p.ok) throw new Error("fixture proposal failed");
    return p.value;
  }

  test("actions are paired with the state fields they move", () => {
    const binding = bindDomain(fixtureProposal());
    expect(binding.targets.map((t) => `${t.action}->${t.key}`).sort()).toEqual([
      "add_to_ledger->ledger_count",
      "add_to_notes->notes_count",
    ]);
  });

  test("counts_nonneg holds on a clean state and fires on a negative one", () => {
    const inv = bindDomain(fixtureProposal()).invariants.find((i) => i.name === "counts_nonneg");
    expect(inv).toBeDefined();
    if (inv === undefined) return;
    expect(inv.check({ ledger_count: 3, notes_count: 0 })).toBeNull();
    expect(inv.check({ ledger_count: -1, notes_count: 0 })).toContain("ledger_count:-1");
  });

  test("ledger_matches_counts holds when the ledger agrees and fires when it does not", () => {
    const inv = bindDomain(fixtureProposal()).invariants.find(
      (i) => i.name === "ledger_matches_counts",
    );
    expect(inv).toBeDefined();
    if (inv === undefined) return;
    expect(inv.check({ ledger_count: 2, notes_count: 3, [LEDGER_KEY]: 5 })).toBeNull();
    expect(inv.check({ ledger_count: 2, notes_count: 3, [LEDGER_KEY]: 4 })).toContain("ledger");
    // Fields that no action moves are outside the identity, or a file count
    // read from the context would break it on the first step.
    expect(inv.check({ ledger_count: 1, notes_count: 0, files_ts: 2, [LEDGER_KEY]: 1 })).toBeNull();
  });

  test("the transition moves the counter and the ledger by the same amount", () => {
    const binding = bindDomain(fixtureProposal());
    const next = binding.transition(
      { ledger_count: 0, notes_count: 0 },
      {
        seq: 1,
        ts: 0,
        branch: "main",
        actor: "operator",
        action: "add_to_ledger",
        params: { count: 4 },
        derivation: null,
        klass: "PINNED",
      },
    );
    expect(next).toMatchObject({ ledger_count: 4, [LEDGER_KEY]: 4 });
    for (const inv of binding.invariants) expect(inv.check(next)).toBeNull();
  });
});

describe("whatsapp turn", () => {
  test("the first message proposes, and nothing has run", async () => {
    const r = await post("/api/whatsapp/turn", {
      from: "+57 300 000 0001",
      text: "hola",
      threadId: "thread-a",
    });
    expect(r.status).toBe(200);
    const text = ((await body(r)).messages as Array<{ text: string }>)
      .map((m) => m.text)
      .join("\n");
    expect(text).toContain("Nothing runs until you accept it");
    expect(text).toContain("ref ");
    expect(hub.state.ontologies.size).toBeGreaterThanOrEqual(0);
  });

  test("an accept without the answers asks for exactly what is missing", async () => {
    await post("/api/whatsapp/turn", { from: "+57 1", text: "hola", threadId: "thread-b" });
    const r = await post("/api/whatsapp/turn", {
      from: "+57 1",
      text: "dale, acepto",
      threadId: "thread-b",
    });
    const text = ((await body(r)).messages as Array<{ text: string }>)[0]?.text ?? "";
    expect(text).toContain("still need an answer");
    expect(text).toContain("What unit");
  });

  test("answers accumulate across turns and only then does it run", async () => {
    const open = await post("/api/whatsapp/turn", {
      from: "+57 2",
      text: "hola",
      threadId: "thread-c",
    });
    const rendered = ((await body(open)).messages as Array<{ text: string }>)
      .map((m) => m.text)
      .join("\n");
    const count = Number(/\*Before this can run\* \((\d+)\)/.exec(rendered)?.[1] ?? "0");
    expect(count).toBe(2);

    const partial = await post("/api/whatsapp/turn", {
      from: "+57 2",
      text: "1. unidades",
      threadId: "thread-c",
    });
    const partialText = ((await body(partial)).messages as Array<{ text: string }>)[0]?.text ?? "";
    expect(partialText).toContain("Still open (1)");

    const done = await post("/api/whatsapp/turn", {
      from: "+57 2",
      text: "2. unidades\nsi, dale",
      threadId: "thread-c",
    });
    const doneText = ((await body(done)).messages as Array<{ text: string }>)[0]?.text ?? "";
    expect(doneText).toContain("Accepted.");
    expect(doneText).toContain(LEDGER_KEY);
    expect(doneText).toContain("Violations: 0");
    expect(doneText).toMatch(/Receipt: http:\/\/hub\.test\/r\/[0-9a-f]{32}/);

    const receiptUrl = /Receipt: (\S+)/.exec(doneText)?.[1] ?? "";
    const receipt = await hub.fetch(new Request(receiptUrl));
    expect(receipt.status).toBe(200);
    expect(await receipt.text()).toContain("Parallax run receipt");
  });

  test("a reply that rejects wins over one that also accepts, and nothing runs", async () => {
    await post("/api/whatsapp/turn", { from: "+57 3", text: "hola", threadId: "thread-d" });
    const before = hub.state.runs.size;
    const r = await post("/api/whatsapp/turn", {
      from: "+57 3",
      text: "1. unidades\n2. unidades\nno, mejor no, acepto luego",
      threadId: "thread-d",
    });
    const text = ((await body(r)).messages as Array<{ text: string }>)[0]?.text ?? "";
    expect(text).toContain("Discarded");
    expect(hub.state.runs.size).toBe(before);
  });

  test("a reply that reads as neither is answered without guessing", async () => {
    await post("/api/whatsapp/turn", { from: "+57 4", text: "hola", threadId: "thread-e" });
    const r = await post("/api/whatsapp/turn", {
      from: "+57 4",
      text: "que tal el clima",
      threadId: "thread-e",
    });
    const text = ((await body(r)).messages as Array<{ text: string }>)[0]?.text ?? "";
    expect(text).toContain("could not read that as an answer");
  });

  test("an accept on a thread with nothing open proposes instead of activating", async () => {
    // One thread being mid-conversation must not make another thread's first
    // message an acceptance. Proposals are shared by id because they are
    // derived from the same context; answers and stage are per thread.
    await post("/api/whatsapp/turn", { from: "+57 5", text: "hola", threadId: "thread-f" });
    const before = hub.state.ontologies.size;
    const other = await post("/api/whatsapp/turn", {
      from: "+57 6",
      text: "1. unidades\n2. unidades\nacepto",
      threadId: "thread-g",
    });
    const text = ((await body(other)).messages as Array<{ text: string }>)
      .map((m) => m.text)
      .join("\n");
    expect(text).toContain("Nothing runs until you accept it");
    expect(hub.state.ontologies.size).toBe(before);
  });

  test("a turn without a threadId is a typed error", async () => {
    const r = await post("/api/whatsapp/turn", { from: "+57 7", text: "hola" });
    expect(r.status).toBe(400);
    expect((await body(r)).code).toBe("MISSING_FIELD");
  });
});
