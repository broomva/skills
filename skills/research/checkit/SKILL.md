---
name: checkit
category: research
description: >
  Ingest-and-integrate an artifact someone points at with a terse, deliberately
  under-articulated directive — "check this out", "lets research this", "look
  into this", "wdyt" — followed by a URL, repo, paper, file, image, or pasted
  document. Infers the actual request from a fully-contextualized frame (who is
  asking + what they're working on + what's already known) WITHOUT bouncing a
  clarifying question back, then runs the pipeline: contextualize → deep research
  (verify every source) → analyze → connect → document the finding → suggest
  ranked next steps. The artifact ends up metabolized into knowledge and action,
  not left as a one-paragraph summary. Composes existing research/search/memory
  tools; it does not reimplement them. USE WHEN: check this out, checkit,
  /checkit, lets research this, research this, look into this, dig into this,
  wdyt, what do you think of this, found this, take a look + an artifact; or
  whenever an artifact is shared with an underspecified ask. NOT FOR:
  retrospective "what have I been doing repeatedly" (a discovery/look-back task);
  fully-specified artifact asks ("summarize this PDF in 3 bullets", "fix the bug
  in this file" — answer directly). Triggers on those phrases + a shared artifact.
---

# checkit — ingest an artifact, integrate it, act on it

Someone drops a URL / repo / paper / file / image with a terse directive —
"check this out", "lets research this", "wdyt". The intent is real but
*unstated by design*: they're delegating the articulation, not just the work.

`checkit` **infers the real request from a fully-contextualized frame and acts
on it — without asking back** for read/research steps — then runs an
ingest-and-integrate pipeline so the artifact becomes durable knowledge + a
ranked next step, not a throwaway summary.

It is a **composition skill**: it fires existing research, search, and
note-taking tools in sequence; it does **not** reimplement them.

> **Portability.** The pipeline below is self-contained and works in any agent
> environment. It is most powerful inside a **bstack workspace** (broomva/bstack),
> where it composes with the `checkit` role/x **lens** (request-shape routing) and the
> bstack primitives named below (P15 snapshot, P6 proactive docs, P18 format).
> Outside bstack, treat the primitive names as the plain behaviors they describe
> — the full portable contract is bundled in
> [`references/checkit-lens.md`](references/checkit-lens.md).

## The one rule

> **Never ask "what do you want me to do with this?"** for read/research steps.
>
> The user shared the artifact *because* they didn't want to articulate the ask.
> Infer the intent, state it in one line, and execute. **Carve-out:**
> proceeding-on-inference covers *reversible, low-cost* steps; for
> costly/irreversible ones (an expensive multi-agent deep-research fan-out,
> mutating existing saved notes, filing a ticket) do the cheap version first and
> *surface the expensive option as a ranked next step* — you still never ask,
> you defer.

## Pipeline (what `/checkit <artifact>` does)

1. **Infer + declare intent** — one line: *"Reading this as: <inferred ask>
   (artifact type: X; relevant to: <active work>)."* Then proceed.
   - Use the artifact-type → intent taxonomy in
     [`references/checkit-lens.md`](references/checkit-lens.md). Default for a
     builder/researcher: *evaluate-against-our-stack*, not a neutral summary.

2. **Contextualize first** (bstack: P15 + knowledge-graph load) — snapshot what's
   active (branch, open PRs, recent work) and **search existing notes/knowledge
   for the topic before going external**. Surface what's already known.
   *Knowledge-first prevents re-researching solved problems.*

3. **Deep research — traverse to the primitives.** Pick the engine by artifact
   type (general web research / academic-paper search / single-page fetch), then
   **read the primary source verbatim** — a WebFetch/search answer over a landing
   page is *discovery* (it routes you to what to read), never the citation
   source. Depth floor by type: **repo** → walk the full tree
   (`gh api repos/<o>/<r>/git/trees/<ref>?recursive=1` or clone) and read the
   canonical files (`SPEC.md` / `README` / key sources) verbatim; **docs site** →
   follow the doc tree (many pages), not one; **paper** → read the
   mechanism-bearing sections, not the abstract; **long file** → read it, not the
   first screen; **video / reel / short / TikTok** → *watch it, don't just
   transcribe it* via the adaptive-video-ingest recipe: acquire (yt-dlp; or
   Interceptor on logged-in Chrome for gated content) → pull the transcript first
   (YouTube auto-subs free; whisper otherwise) → **default transcript-first,
   escalate to frames only on signal** (deixis like "look/here/as you can see",
   high ffmpeg scene-change rate, or suspected on-screen text) → sample on
   *change* not on a clock (`ffmpeg select='gt(scene,0.3)'`, one frame per distinct
   visual state) → tile to a montage contact sheet for ONE cheap Read → re-sample
   only the windows the coarse pass couldn't resolve. Never uniform-poll every
   second (drowns talking heads, aliases fast screencasts). Full spec:
   `research/entities/pattern/adaptive-video-ingest.md`. **Verify every external URL** — hallucinated links are a
   catastrophic failure. **Provenance honesty:** a `[HIGH]` tag names the
   artifact *actually read* verbatim; a landing-page/search summary is `[MED]` at
   most, labeled as a summary — never tag a claim "spec/repo-verified" against a
   source you did not open. **Exhaustion check before filing:** "what canonical
   material have I not opened?" (linked spec, referenced files, sub-pages, cited
   sources). Scale depth to stakes, but never below reading the source's own
   primitives.

4. **Analyze the sources** — extract the mechanism / claim / result. What's
   novel? load-bearing? confirms or contradicts what you already knew? Tag every
   external claim **HIGH / MED / LOW** confidence.

5. **Connect + enrich** — make ≥1 explicit link to existing knowledge. If the
   artifact confirms or contradicts a prior note, say which (mutating an existing
   note is gated by the costly/irreversible carve-out above).

6. **Document the finding** (bstack: P6 proactive bookkeeping) — write the note /
   entity / summary **without asking permission**, then report what was filed in
   one line. Provenance traces back to the artifact.

7. **Suggest next steps** — ranked and tied to active work:
   build-vs-reuse decision · a follow-up research thread · a ticket · a doc. The
   artifact must end up **metabolized into action**.

8. **Format for the reader** (bstack: P18) — markdown for knowledge substrate; a
   richer human-read brief only when the finding is a decision artifact.

## Composition map

| Step | Composes (bstack-native names; generic behavior in parens) |
|---|---|
| Infer intent, no ask-back | the `checkit` role/x lens (P17) + persona context (who is asking) |
| Contextualize | P15 state snapshot + knowledge-graph load (search existing notes) |
| Deep research | a research/search skill (web / academic / fetch), depth-scaled |
| Analyze + tag confidence | source verification + HIGH/MED/LOW tagging |
| Connect + enrich | knowledge-graph edges (link to existing notes) |
| Document the finding | P6 proactive bookkeeping (file first, report after) |
| Next steps | goal-formation (turn gaps into ranked next actions) |
| Format | P18 format-follows-audience |

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "It's vague — I should ask what they want." | The vagueness is intentional delegation. Infer + state + proceed. Asking is the failure this skill exists to kill. |
| "A quick summary is enough." | A summary evaporates. checkit produces durable notes + links + ranked next steps, or it didn't run. |
| "I'll research it but skip writing it down." | Research-without-integration leaves knowledge cold; next session re-solves it. Filing is not optional. |
| "Should I create a note for this?" | Never ask — file proactively, report after. |
| "I'll trust my training data on this repo/paper." | Verify with live research; training data is stale. Verify every URL. |
| "A WebFetch/search summary of the page is enough." | A summary is *discovery*, not the source. Traverse to the primitives — read the spec / README / key files / doc tree / paper sections verbatim before any `[HIGH]` claim. |
| "I confirmed the repo/page exists — that's verification." | Existence ≠ contents. `[HIGH]` requires reading the canonical text; a tag naming a source you didn't open is false provenance. |
| "This artifact isn't obviously about our work." | For a focused builder/researcher it almost always is — find the link to active work before defaulting to a neutral read. |
| "Let me just kick off the deep multi-agent run on this guess." | Costly/irreversible on an inference → surface it as a next step instead (the carve-out). |

## Scope

- **In scope**: any artifact (URL, repo, paper, file, image, pasted doc, or a
  bare topic string) shared with an under-specified directive.
- **Out of scope**: fully-specified artifact asks (answer directly);
  retrospective "what have I been doing repeatedly" (a discovery/look-back task).

## Validation (skill self-test)

A `/checkit` run is complete iff: an inferred-intent line appears **before** any
research and **no bounce-back question** was asked for read/research steps; any
costly/irreversible step was surfaced as a ranked next step (not run on a guess);
existing knowledge was searched first; **the primary source was traversed to its
primitives and read verbatim (not a landing-page/search summary), with every
`[HIGH]` claim tracing to that verbatim read**; deep research ran with every URL
verified; ≥1 link to existing knowledge was made; ≥1 finding was filed
proactively; and a ranked next-steps list ties the finding to active work. (Full
checklist: [`references/checkit-lens.md`](references/checkit-lens.md).)

## References

- [`references/checkit-lens.md`](references/checkit-lens.md) — the portable
  no-ask-back contract, the artifact-type → intent taxonomy, the artifact-gate,
  and the full procedure + self-test. Read this for the complete behavior.
- In a **bstack workspace**: the request-shape routing lens is `roles/checkit.md`
  (a `status: candidate` lens — reached today via this skill + reasoning; auto-fire
  pending the role-x phrase-scorer fix, BRO-1338);
  the crystallization record is `research/entities/pattern/bstack-engine.md`
  (§2026-06-02). checkit composes there with P15 / P6 / P17 / P18.
