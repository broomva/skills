# Brief for the v2 sealed routing cases (BRO-2674, pre-flip step 4)

This is the whole text a fresh subagent received to write
`reflex-routing-heldout-v2.json`. It was told not to read any file or use any tool,
and it never saw the reflex catalog (`references/reflexes.yaml`), its lines, regexes
or phrases, or the v1 cases. The situations below were written by the pre-flip
session, which has seen the catalog; they describe each need in plain terms and do
not quote a line, regex or phrase list.

---

You are writing test prompts for a classifier that reads one message a developer
types to an AI coding agent in a terminal, and decides which of about thirty
situations the message is in. You will not see the classifier. Do not read any file
and do not use any tool: answer from this brief alone.

The developer runs a fleet of coding agents across many git repos and worktrees. They
type the way people type in a terminal: often lowercase, terse, with typos, PR numbers
(#1192), branch names (feat/x), paths, ticket ids (BRO-2674), product names, and
sometimes a long rambling sentence. Some messages are two words. Vary length, tone,
vocabulary and sentence shape a lot. Do not reuse one template with the nouns
swapped, and do not lean on the words used in the situation descriptions: write what a
real person would type, with the synonyms and paraphrases real people use.

For each situation below write:
- POSITIVE prompts: messages that are clearly in the situation;
- NEAR-MISS prompts: messages on the same topic or with similar words that are NOT in
  the situation (a question about the thing instead of a request, a neighbouring task,
  the same verb on a different object). Near-misses must be ones a careless keyword
  matcher would get wrong, but a careful human would not.

Counts: 10 positives and 5 near-misses per situation, except `change_work`, which
needs 40 positives (at least 10 of them four words or fewer) and 20 near-misses.
Each prompt is one message, standalone. No duplicates across situations.

Return only a JSON object, no prose around it:
{"cases": {"<key>": {"positive": [...], "near_miss": [...]}, ...}}

Situations (key: positive / near-miss):

- change_work: the developer asks the agent to change files or ship them: implement,
  fix, add, refactor, rename, rewrite, write code or docs, commit, push, merge; or a
  short go-ahead that continues such work. / Questions, explanations, code review,
  reading or summarising, and planning or design discussion, where nothing should be
  edited yet.
- p9.watch-after-push: the developer is pushing code, opening a pull request, or
  waiting on CI checks or a deploy, and wants to know how it turns out or to be told
  when it finishes. / Questions about CI configuration, build duration, or what a
  workflow does, with nothing pushed or being waited on.
- p10.branch-first: the developer is on the default branch (main) and asks for a
  change to be made and committed, or switches to main and then asks for a change. /
  Questions about branches, history or the state of main, with no change requested.
- p4.merge-pinned-to-head: the developer asks to merge a specific pull request (by
  number, or "the PR"), possibly squashed, possibly right after approving it. /
  Questions about whether a PR can merge, merge strategies or merge settings, or
  "merge" applied to something that is not a PR (two files, two lists, two configs).
- p10.worktree-removal-guard: the developer asks to remove, delete or tear down one
  or more git worktrees they no longer need. / Questions about worktrees, creating a
  new one, or listing them.
- ctx.live-peer-before-git-op: the developer asks whether another agent or session is
  working in the same checkout or branch right now, or worries one is before a pull or
  push. / Git questions with no concern about other sessions.
- p9.heal-on-red: a pull request's CI checks failed or are red, and the developer asks
  why, or asks for it to be fixed. / Questions about CI setup or required checks, or
  about checks that are passing.
- convention.trash-not-rm: the developer asks to delete or clean up scratch, temp or
  leftover folders or files at named paths. / Questions about those folders (why they
  exist, ignore rules, disk usage), or deleting things that are not files on disk (a
  database row, a git branch, an issue, a cloud resource).
- convention.paseo-fleet-listing: the developer asks about the agents or sessions
  running in Paseo, their agent orchestration app: how many, which are running or
  idle, the state of the fleet. / Paseo questions not about listing its agents
  (installing it, its config, schedules, one feature), or questions about other
  processes.
- p2.gate-destructive-git: the developer asks for a destructive git operation: a
  force-push, a hard reset, cleaning untracked files, deleting a branch, rewriting
  history. / Questions explaining those operations, or safe operations.
- p18.human-doc-in-specs: the developer asks for a document meant for people: an
  explainer, report, guide, write-up, proposal, spec or runbook. / Small edits to code
  comments, docstrings or a README line, or questions about an existing document.
- p15.snapshot: the developer asks where things stand on their work: what's done, is
  everything committed, pushed, merged or green, catch me up. / "Status" of something
  else (an HTTP status code, a vendor's status page, a process exit status), or asking
  for an explanation of how something works.
- skill.kg: the developer asks what is already known in their own knowledge graph
  about a topic, or asks to load or browse the graph's entries on a topic. / General
  questions about knowledge graphs as a technology, or editing one known file.
- p8.janitor-branches: the developer asks to clean up stale, merged, old or dead
  branches (and the worktrees left behind). / Counting or listing branches, renaming
  one, or questions about branch protection.
- p11.bugfix-test-lock: the developer asks for a specific bug or regression to be
  fixed (something behaves wrongly or crashes). / Asking whether something is a bug,
  triaging or labelling issues, writing tests for a feature with no bug, or discussing
  a bug without asking for a fix.
- p12.persist: the developer wants work to keep going for a long time: overnight, for
  hours, across sessions, until some condition holds. / Asking how long something took,
  scheduling a meeting, a quick one-off task.
- p7.freshness: an installed skill, plugin or CLI rejects a documented flag or seems
  out of date, or the developer asks to update their installed skills. / Editing a
  skill's own docs or source, or asking which skill does what.
- p10.cleanup-after-merge: a pull request has just merged and the developer asks to
  clean up after it (its branch, its worktree, local leftovers). / Cleanup before a
  merge (commit messages, squashing), or asking whether something merged.
- p20.cross-review: the developer asks for an independent, adversarial or
  second-opinion review of a PR or change before it merges. / Replying to review
  comments already left, requesting a specific human reviewer, or asking what a review
  said.
- p4.ship-not-ask: the developer asks for a finished deliverable to be built in a repo
  (a page, a feature, a script, a deck, a component), the kind of request that ends
  with the work shipped. / Asking whether to build it, brainstorming, estimating
  effort, or asking for options first.
- skill.arc: the developer is leaving (bed, a flight, the weekend) and hands work over
  to run unattended until it is finished and the machine is left clean. / Mentions of
  leaving or sleep with no hand-over, or asking what is left for later.
- skill.autonomous: the developer gives a bare go-ahead to execute an agreed plan
  without further check-ins. / "Go" or "proceed" used inside a question or a different
  request (go through the plan, go over the risks).
- skill.resume: the agent's previous turn was cut off by an error, interrupt or
  disconnect, and the developer says to pick up and continue. / Resuming something
  other than the agent's own work (a paused schedule, a download, a subscription).
- skill.handoff: the developer asks for a handoff document so a fresh session or
  another agent can pick the work up later. / Reading an existing handoff and
  continuing from it, or handing a task to a human colleague in conversation.
- skill.checkit: the developer shares a link, repo, paper or file with a terse,
  under-specified ask ("check this out", "thoughts?", "look into this"). / A link with
  a fully specified ask (summarise in three bullets, fix the bug in this file, cite
  this).
- skill.dogfood: the developer asks for proof that a change actually works for a user,
  by exercising it end to end like a user would. / Writing unit tests, or reviewing the
  code of the change.
- skill.unslop: the developer says a UI looks generic, AI-generated or templated and
  asks for it to be fixed. / Other UI problems: performance, accessibility bugs, a
  broken layout on one device.
- skill.legal-readiness: the developer asks whether a product is legally ready to
  launch (terms, privacy, compliance claims). / Small legal-adjacent edits (link the
  terms page, update a copyright year) or general legal trivia.
- skill.audit-harness-usage: the developer asks how many tokens, how much cost or
  usage their agent harnesses (Claude Code, Codex, others) consumed over a period. /
  Reducing the token count of one prompt or file, or pricing questions about a model.
- skill.disambiguate: the developer asks to tighten a vague requirement, ticket or
  acceptance criterion so it reads one way only. / Asking what a ticket is about, or
  writing a new ticket from scratch.
- skill.skillify: the developer asks to turn the workflow that just worked into a
  reusable, tested skill. / Asking which existing skill does something, or editing an
  existing skill's text.
