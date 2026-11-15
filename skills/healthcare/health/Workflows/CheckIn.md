# CheckIn: the holistic daily check-in

**When invoked:** a scheduled daily check-in, or the user says "check-in", "how am I
doing", "journal", "log my day". Health is holistic: **physical, mental and spiritual**
(spiritual in the non-religious sense: meaning, connection, presence).

## Why it exists

The trace store measures the body. It cannot see mood, stress, craving, meaning or
connection, and [Coaching](Coaching.md) names that "subjective state" gap as the main
reason v1 gives no prescriptions. The check-in fills it with a few seconds of the user's
own words a day, stored next to the watch data so the two can be read together.

| Dimension | Covers | Source |
|---|---|---|
| **Physical** | sleep, energy, movement, appetite, symptoms, substances | trace store + check-in |
| **Mental** | mood, stress or anxiety, focus, cravings | check-in |
| **Spiritual** | meaning and purpose, real connection with people, presence or reflection, gratitude, nature | check-in |

## Protocol

0. **Safety before anything.** Check the user's message, and every answer at every step,
   against the [safety triggers](#safety-lines-not-coaching). That table is the only list of
   triggers, and its *Action* column decides what happens next: **stop**, **say first, then
   continue**, or **say, don't record**.
1. **Snapshot.** `health status`; if the store is stale, sync. Read last night's sleep
   (`health raw --endpoint sleep` for the night) and the last 7 journal entries.
2. **Ask, don't interrogate.** One structured question call (AskUserQuestion in Claude Code),
   four questions, each with 3–4 options plus free text. Keep the wording warm and short:
   - Body: "How did your body feel today?" (Strong · Okay · Tired or heavy · Unwell)
   - Mind: "How was your mind today?" (Calm, clear · Okay · Stressed or anxious · Low or flat)
   - Spirit: "Did today feel connected to what matters to you?" (Yes · Partly · Disconnected · Hard to say)
   - One user-defined item the user is tracking (a habit, a symptom, anything they name). It is
     optional: with none defined, ask three questions. At the first check-in, offer to
     define one: its name, the question, 3–4 options and their scores. Store that in the
     brief; from then on it is asked like the others.
   Then one optional follow-up: "What did you do for yourself today?" (multi-select:
   moved · time outside · time with someone · reflection), a free-text note, and
   "Any intention for tomorrow?". Its options are up to three intentions the user has set
   before, in their own words, plus a free-text answer. The agent never invents one.
3. **Record** the answers with `health checkin record` (see *Storage*). The label goes in verbatim, and so
   does any free-text answer. The score comes from this table and nowhere else, so trends stay
   comparable week to week:

   | Dimension | Labels → score |
   |---|---|
   | Body | Strong 8 · Okay 5 · Tired or heavy 3 · Unwell 1 |
   | Mind | Calm, clear 8 · Okay 5 · Stressed or anxious 3 · Low or flat 2 |
   | Spirit | Yes 8 · Partly 5 · Disconnected 2 · Hard to say: no score |

   A free-text answer has no score: never guess one. A user-defined item is scored only on
   a scale the user set when they defined it, and that scale is stored in the brief.
4. **Reflect in 4–6 lines.** One line per dimension, each tied to a number or a trend
   (measured data against the user's own baseline, never a population norm), then the
   intention the user chose, repeated back. Observations, not instructions: the v1
   boundary in [Coaching](Coaching.md) holds, so the agent does not prescribe. No lecturing.
   A lapse or a bad day logged honestly gets thanks, then curiosity about what led to it.
5. **Weekly** (one fixed day): a short table of the week per dimension, what improved, what
   slipped, and the user's intention for the week.
6. **If the user doesn't answer,** record nothing and don't nag. Offer a late entry for that
   date at the next check-in.

## Safety lines (not coaching)

The check-in reflects. It does not diagnose or prescribe, but it never stays quiet about risk.
This table is the single source of safety triggers; step 0 and every later step defer to it.
Whatever the action, the line is said plainly and **first**, before any other reply.

| Trigger | Action | What to say |
|---|---|---|
| Thoughts of self-harm, or danger right now | stop | The local emergency number now (for example 911 or 112). Then a crisis line for the user's country: one the user has recorded, or a directory such as findahelpline.com if the location is unknown. |
| Words of hopelessness | stop | Talk to a doctor or a trusted person soon, plus the same crisis-line route. |
| Chest pain, fainting, or palpitations with dizziness, happening now | stop | Emergency services now. |
| Mind "Low or flat", or a `safety_stop`, on 3 or more of the last 5 days (journal plus today) | say first, then continue | Low for several days now. A doctor or a trusted person this week is worth it, plus the crisis-line route. |
| Chest pain, fainting or palpitations that have passed, or a fever lasting more than two days | say first, then continue | A clinician the same day (for the fever, soon). The check-in goes on, and the symptom is recorded under `symptoms` in the user's words. |

**stop** means nothing else that turn: no snapshot, no sync, no questions, no storage beyond
one marker, `health checkin record safety_stop=yes`, with no words, so the low-days row
above can count that day. Resume another time, only if the user wants to. **say first, then
continue** means the check-in goes on after the line.

## Storage

`health checkin` is the **only writer** of the journal. Agents never edit the file by hand,
so the rules below hold whoever runs the check-in. They live in code
(`adapters/repositories/journal.py`) and are tested (`tests/unit/adapters/test_journal.py`).

```bash
health checkin record body="Okay" body_score=5 mind="Calm, clear" mind_score=8 note="good walk"
health checkin record --date 2026-01-14 spirit="Partly" spirit_score=5   # a late answer
health checkin show --days 7
```

- **Path:** `journal.jsonl` in the skill's data directory (`$BROOMVA_HEALTH_DATA_DIR`, default
  `~/broomva-health/`, 0700, outside every repo; see
  [References/privacy-architecture.md](../References/privacy-architecture.md)). The file is
  0600. `--journal` (or `$BROOMVA_HEALTH_JOURNAL`) picks another file only if its folder is
  owner-only, not inside a git work tree and not inside a cloud-synced folder. Otherwise the
  command refuses and writes nothing.
- **One object per date, one line each.** Recording merges into that date's object: new keys
  win and earlier answers stay. Every write takes an exclusive lock (10 s at most), rewrites
  the file through a temp file with fsync and an atomic replace, and keeps any line that
  does not parse, verbatim, in place. If the lock times out (exit 3) or the write fails,
  nothing is written. The agent then says so and keeps the answers in its reply to record later.
- Values: `8` becomes a number, `yes`/`no` a boolean, anything else text. Extra keys for
  whatever the user tracks (for example `symptoms`, or a named habit) are allowed; readers
  ignore keys they don't know. `safety_stop: true` marks a day the safety table stopped.

A stored line:

```json
{"date": "2026-01-15", "at": "21:04", "body": "Okay", "body_score": 5, "mind": "Calm, clear", "mind_score": 8, "spirit": "Partly", "spirit_score": 5, "practices": "moved, outside", "note": "long day, good walk at sunset"}
```

## Running it as an agentic loop

A long-lived agent thread with a daily scheduled prompt works better than a desktop
notification: the agent asks, records and reflects in one place, and keeps its own brief
(protocol, baselines, current context) in a private file it re-reads after every context
compaction. The brief lives next to the journal, as `checkin-brief.md` in the data
directory, with the same rules: 0600, outside every repo and every cloud-synced folder. The
scheduled prompt should only say "read the brief and run the check-in", so no personal
detail sits in the scheduler.

## Example reply

```
Body 5: tired, matches a short night (6.4 h, HRV 47 vs your 50 baseline).
Mind 8: calm despite that.
Spirit 5: partly connected; the walk counted.
Your intention for tomorrow: same wake time, outside before screens.
```
