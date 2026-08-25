// The sourcer depth loop, as a dynamic workflow.
//
// Recursion cannot be expressed by recursion here: the workflow substrate
// permits one level of nesting, so a node cannot spawn a sub-workflow for what
// it discovers. What replaces it is this -- a depth loop in a single script
// that fans out across the frontier at depth d, lands everything it found, and
// lets the STORE decide what reaches d+1. Breadth-first falls out of that, and
// is the better shape anyway: everything at hop d is known before anything at
// d+1 is fetched.
//
// The division of labour is the entire point, and it is not negotiable:
//
//   the script      claims, fetches, admits, applies verdicts, expands
//   the extractor   reads bytes already on disk, returns byte spans
//   the verifier    reads a span and a claim, blind to the extractor
//
// A crawl agent has no network tool and no write access to the store. It cannot
// fetch and it cannot put a record anywhere, so fabricating evidence stops
// being something a gate must detect and becomes something that is not a
// callable path. That is a deployment property as much as a code one: it holds
// because these agents are given no network tool, and it is the one part of the
// architecture the gate set cannot verify about itself from the inside.
//
// Run:
//   Workflow({ scriptPath: "<skill>/workflows/depth-loop.js",
//              args: { scripts: "<skill>/scripts", seeds: ["https://example.com/"],
//                      maxDepth: 2, budget: 40,
//                      run: "/tmp/crawl/r1", db: "/tmp/crawl/map.db" } })
//
// SOURCER_CHAIN_KEY must reach the agents. Pass `chainKey` in args, or have it
// already in the ambient environment — an unkeyed chain verifies and proves
// nothing, so the daemon refuses to construct without one.

export const meta = {
  name: 'sourcer-depth-loop',
  description: 'Crawl a site set into a verified entity graph, breadth-first, expanding only what verifies',
  whenToUse: 'Mapping a company to its relationships, its leadership and their public profiles, where the map must be trustworthy without a human checking it',
  phases: [
    { title: 'Plan', detail: 'seal the denominator, traverse the seeds, queue the page set' },
    { title: 'Extract', detail: 'one agent per page: bytes on disk in, typed spans out' },
    { title: 'Verify', detail: 'a blinded judge per claim, never shown the extractor’s reasoning' },
    { title: 'Gate', detail: 'the twelve gates over what the run left on disk' },
  ],
}

// `scripts` is required rather than derived from `import.meta.url`: the runtime
// evaluates this body as an async function, not as an ES module, so `import.meta`
// is a syntax error there even though the file reads like a module.
const SCRIPTS = args?.scripts
const RUN = args?.run
const DB = args?.db
const SEEDS = args?.seeds ?? []
const MAX_DEPTH = args?.maxDepth ?? 2
const BUDGET = args?.budget ?? 40
const WIDTH = args?.width ?? 6      // D4: fan-out 6, behind one shared throttle

if (!SCRIPTS || !RUN || !DB || SEEDS.length === 0) {
  throw new Error(
    'args must carry { scripts: "<skill>/scripts", seeds: [...], ' +
    'run: "<dir>", db: "<file>" }',
  )
}

// Each agent gets a FRESH shell, so an export in this process reaches none of
// them. The key therefore travels on the command line when `args.chainKey` is
// given, and otherwise the ambient environment must already carry it — which is
// the right default for a real run, where a key on an argv is a key in `ps`.
// A model returning "[]" as a string is normal; a model returning prose is not,
// and the difference must be a dropped page rather than a dead workflow.
function safeParse(text) {
  try {
    const v = JSON.parse(text ?? '[]')
    return Array.isArray(v) ? v : []
  } catch {
    log(`extractor returned unparseable claims; treating the page as empty`)
    return []
  }
}

const KEY = args?.chainKey ? `SOURCER_CHAIN_KEY=${args.chainKey} ` : ''
const PY = `${KEY}PYTHONDONTWRITEBYTECODE=1 python3 ${SCRIPTS}/sourcer.py`
const GATES = `${KEY}PYTHONDONTWRITEBYTECODE=1 python3 ${SCRIPTS}/gates.py`

// The claim a verifier is asked to judge, with the endpoints NAMED.
//
// Asking about the bare predicate is a real defect and not a cosmetic one. On a
// page reading `ACME employs Alice. Globex employs Bob.`, relating ACME to Bob
// fits inside the relation-span bound and contains both mentions, so the only
// thing standing between it and an `entailed` edge is the question the judge is
// asked. "Does this text say employs" is answered yes. A verifier cannot refuse
// a claim it was never shown.
//
// The names are byte ranges of the snapshot, quoted for the judge to compare
// against the span — the agent still reads the file, it is simply told which
// two things the relation is between.
function claimText(taken, c) {
  return `the subject at bytes ${c.subject.span_start}..${c.subject.span_end} ` +
         `(a ${c.subject.kind}) stands in the relation "${c.predicate}" to ` +
         `the object at bytes ${c.object.span_start}..${c.object.span_end} ` +
         `(a ${c.object.kind}) — read all three ranges of ${taken.path} ` +
         `and judge whether the relation span STATES that relation between ` +
         `those two specific things, not merely that it mentions both`
}
// Schemas declare their FIELDS, and every field is a scalar.
//
// `{type:'object', additionalProperties:true}` looks permissive and is a trap:
// with no declared properties the structured-output layer hands nested objects
// back as JSON *strings*, so `taken.item.digest` was `undefined` and every
// pipeline stage died on it. Found by running the workflow, not by reading it —
// a schema that describes nothing is the same vacuity this skill is about.
//
// So `take` returns a FLAT record rather than a nested `item`. Flat scalars
// cannot be coerced into anything, which makes the contract robust instead of
// merely correct-when-it-works.
const TAKE_SCHEMA = {
  type: 'object',
  properties: {
    found: { type: 'boolean' },
    url: { type: 'string' },
    digest: { type: 'string' },
    depth: { type: 'integer' },
    claim_token: { type: 'string' },
    path: { type: 'string' },
    n_bytes: { type: 'integer' },
    vocabulary: { type: 'string' },
    reason: { type: 'string' },
  },
  required: ['found'],
}

const CLAIMS_SCHEMA = {
  type: 'object',
  properties: { claims_json: { type: 'string' }, count: { type: 'integer' } },
  required: ['claims_json', 'count'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: { entailed: { type: 'boolean' }, why: { type: 'string' } },
  required: ['entailed'],
}

const LAND_SCHEMA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' }, admitted: { type: 'integer' },
    entailed: { type: 'integer' }, refuted: { type: 'integer' },
    expanded: { type: 'integer' }, error: { type: 'string' },
  },
  required: ['ok'],
}

const GATES_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string' }, failing: { type: 'string' },
    probes_ok: { type: 'integer' }, probes_total: { type: 'integer' },
  },
  required: ['verdict'],
}

const PLAN_SCHEMA = {
  type: 'object',
  properties: { queued: { type: 'integer' }, refused: { type: 'string' } },
  required: ['queued'],
}

// ---------------------------------------------------------------------------

phase('Plan')

const seedArgs = SEEDS.map(s => `--seed ${s}`).join(' ')
const planned = await agent(
  `Run exactly this, once, and return its stdout verbatim as JSON:

     ${PY} plan --run ${RUN} --db ${DB} ${seedArgs} --max-depth ${MAX_DEPTH} --budget ${BUDGET}

   Return {"queued": <the "queued" number from its stdout>}. If it exits 2,
   return {"queued": 0, "refused": "<its stderr>"} — a refusal is an answer, not
   an obstacle to work around. Do not edit any file. Do not run anything else.`,
  { label: 'plan', schema: PLAN_SCHEMA },
)
log(`planned: queued ${planned?.queued ?? 0} page(s) from ${SEEDS.length} seed(s)`)

// ---------------------------------------------------------------------------
// The depth loop.
//
// The frontier lives in SQLite, not in this script. `take` hands out the
// shallowest outstanding item under a lease, so this loop is the same whether
// one worker runs it or six do -- and a worker that dies costs one lease rather
// than removing its item from the crawl while the run still reports itself
// complete.

for (let depth = 0; depth <= MAX_DEPTH; depth++) {
  const items = []
  for (let i = 0; i < WIDTH; i++) {
    const taken = await agent(
      `Run exactly this once and return its stdout verbatim as JSON:

         ${PY} take --run ${RUN} --db ${DB} --worker w${i}

       Its stdout has an "item" object (or "item": null). FLATTEN it:
         {"found": true, "url": ..., "digest": ..., "depth": ...,
          "claim_token": ..., "path": ..., "n_bytes": ...,
          "vocabulary": <the "vocabulary" string>}
       If "item" is null return {"found": false, "reason": <its "reason">}.
       That is a normal answer meaning the frontier is empty or the budget is
       spent; do not retry it.`,
      { label: `take:d${depth}:w${i}`, phase: 'Plan', schema: TAKE_SCHEMA },
    )
    if (!taken?.found || !taken.digest) break
    items.push(taken)
  }
  if (items.length === 0) {
    log(`depth ${depth}: frontier empty or budget spent -- stopping`)
    break
  }

  // A pipeline rather than a barrier: an item whose page is slow to read must
  // not hold up the verification of one that has already finished.
  await pipeline(
    items,

    // -- extract: bytes in, spans out -------------------------------------
    (taken) => agent(
      `You are reading ONE page that is already on disk. You have no network and
       you must not fetch anything.

         file: ${taken.path}
         url:  ${taken.url}   (context only -- do NOT fetch it)
         size: ${taken.n_bytes} bytes

       Return a JSON list of relation claims. Each claim locates its entities by
       BYTE OFFSET into that file. There is no field in which to write a name:
       the name IS the bytes at the offsets you give. An offset off by one
       produces a different entity, and a span over the wrong text produces a
       claim the gates will refuse.

       ${taken.vocabulary}

       Emit a claim only where the page states the relation. Two entities
       appearing on the same page are co-mentioned, not related: your relation
       span must contain both endpoint spans AND stay inside the size bound
       above, so there is no span that makes co-mention pass. Widening the span
       until it encloses both is the move that bound exists to refuse.

       An empty list is a correct answer for a page that relates nothing.

       Return {"claims_json": "<the JSON list as a STRING>", "count": <n>}.
       A string, because a nested array comes back mangled otherwise.`,
      { label: `extract:${taken.digest.slice(0, 8)}`, phase: 'Extract',
        schema: CLAIMS_SCHEMA },
    ).then(r => ({ taken, claims: safeParse(r?.claims_json) })),

    // -- verify: blind, one judge per claim -------------------------------
    async ({ taken, claims }) => {
      // A second signature is worth something only when its claim has a
      // different upstream. The daemon attests that these bytes came from this
      // URL; the extractor, that this claim came from these bytes; the verifier,
      // that these bytes support this claim. Three propositions, disjoint
      // custody -- which is why the verifier is never shown who produced what.
      const verdicts = {}
      for (let i = 0; i < claims.length; i++) {
        const c = claims[i]
        const v = await agent(
          `Judge one claim against one span. You are not told who produced either.

             span:  bytes ${c.span_start}..${c.span_end} of ${taken.path}
                    read exactly that byte range of that file, and nothing else
             claim: ${JSON.stringify(claimText(taken, c))}

           Does that span, on its own, STATE that relation? Not "is it
           plausible", not "is it probably true of the world" -- does the text
           say it. A span that merely mentions both things does not.

           Answer {"entailed": true} or {"entailed": false, "why": "..."}.`,
          { label: `verify:d${depth}:${c.predicate}`, phase: 'Verify',
            schema: VERDICT_SCHEMA },
        )
        // A verifier that did not answer leaves the claim out of the file
        // entirely, so its records stay `unchecked` -- which is NOT permission
        // to expand. Defaulting to true here would quietly make the gate
        // optional; defaulting to false would refute claims nobody judged.
        if (v && typeof v.entailed === 'boolean') verdicts[String(i)] = v.entailed
      }
      return { taken, claims, verdicts }
    },

    // -- land: the script decides, from artifacts on disk ------------------
    ({ taken, claims, verdicts }) => {
      const tag = taken.digest.slice(0, 8)
      return agent(
        `Write these two files exactly as given, then run one command.

           ${RUN}/claims-${tag}.json
           ${JSON.stringify(claims)}

           ${RUN}/verdicts-${tag}.json
           ${JSON.stringify(verdicts)}

         Then run exactly:

           ${PY} land --run ${RUN} --db ${DB} \\
             --url ${taken.url} --digest ${taken.digest} \\
             --token ${taken.claim_token} \\
             --claims ${RUN}/claims-${tag}.json \\
             --verdicts ${RUN}/verdicts-${tag}.json

         Return {"ok": true, "admitted": ..., "entailed": ..., "refuted": ...,
         "expanded": ...} from its stdout "stats". Exit 2 is a refusal: return
         {"ok": false, "error": "<its stderr>"}. Do not edit the files to get
         past it, and do not retry -- the lease is released either way, and a
         second attempt would be landing claims against an item you no longer
         hold.`,
        { label: `land:${tag}`, phase: 'Extract', schema: LAND_SCHEMA },
      )
    },
  )

  log(`depth ${depth}: ${items.length} page(s) landed`)
}

// ---------------------------------------------------------------------------

phase('Gate')

const suite = await agent(
  `Run exactly this and return its stdout verbatim as JSON:

     ${GATES} --run ${RUN} --db ${DB} --json

   Exit 0 is VALID and exit 2 is INVALID. Both are answers. Return
   {"verdict": "<the verdict>", "probes_ok": <n>, "probes_total": <n>,
    "failing": "<comma-separated names of gates whose status is not pass or
    annotate, or an empty string>"}. Do not modify anything to change the
    outcome.`,
  { label: 'gates', schema: GATES_SCHEMA },
)

// A run whose gates did not pass is not a smaller result; it is a result nobody
// should read as findings. Returning the verdict attached to the map is the
// whole contract, and the note is deliberately included in both branches --
// a green suite is easy to over-read, and the precise wording is the value.
return {
  verdict: suite?.verdict ?? 'UNKNOWN',
  failing: suite?.failing ?? '',
  probes: `${suite?.probes_ok ?? '?'}/${suite?.probes_total ?? '?'}`,
  note: suite?.verdict === 'VALID'
    ? 'A page at each cited URL, held at each cited digest, verifiably says what the map says it says. That is NOT a claim that what those pages say is true.'
    : 'INVALID -- do not read this map as findings. Check the failing gates below.',
}
