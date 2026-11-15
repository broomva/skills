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

1. **Snapshot first.** `health status`; if the store is stale, sync. Read last night's sleep
   (`health raw --endpoint sleep` for the night) and the last 7 journal entries.
2. **Ask, don't interrogate.** One structured question call (AskUserQuestion in Claude Code),
   four questions, each with 3–4 options plus free text. Keep the wording warm and short:
   - Body: "How did your body feel today?" (Strong · Okay · Tired or heavy · Unwell)
   - Mind: "How was your mind today?" (Calm, clear · Okay · Stressed or anxious · Low or flat)
   - Spirit: "Did today feel connected to what matters to you?" (Yes · Partly · Disconnected · Hard to say)
   - One user-defined item the user is tracking (a habit, a craving, a symptom)
   Then one optional follow-up: "What did you do for yourself today?" (multi-select:
   moved · time outside · time with someone · reflection) and a free-text note.
3. **Record** one JSON line per day in the journal (see *Storage*). The user's words go in
   verbatim; options map to 0–10 scores (for example Strong 8, Okay 5, Tired 3, Unwell 1).
   A "hard to say" answer gets no score, never a guessed one.
4. **Reflect in 4–6 lines.** One line per dimension, each tied to a number or a trend
   (measured data against the user's own baseline, never a population norm), then **one**
   small, concrete suggestion. No lecturing. A lapse or a bad day logged honestly gets
   thanks, then curiosity about what led to it.
5. **Weekly** (one fixed day): a short table of the week per dimension, what improved, what
   slipped, and one intention.
6. **If the user doesn't answer,** record nothing and don't nag. Offer a late entry for that
   date at the next check-in.

## Safety lines (not coaching)

The check-in reflects. It does not diagnose or prescribe. Say plainly, and first:
- **Low mood on most recent days, or any words of hopelessness:** suggest a doctor or a trusted
  person, and give the local crisis line. Thoughts of self-harm need urgent help now.
- **Fever, chest pain, palpitations or fainting:** a clinician, not the journal.

## Storage

- Path: `journal.jsonl` in the private health directory, the same directory as the
  [DailyNote](DailyNote.md) projection (default `~/broomva-vault/07-Health/`). Keep it out of
  git and out of cloud mirrors: see [References/privacy-architecture.md](../References/privacy-architecture.md).
- One object per day, and a later entry for the same date replaces it:

```json
{"date": "2026-11-15", "at": "21:04",
 "body": "Okay", "body_score": 5, "mind": "Calm, clear", "mind_score": 8,
 "spirit": "Partly", "spirit_score": 5, "practices": "moved, outside",
 "note": "long day, good walk at sunset"}
```

Extra keys for whatever the user tracks (for example `craving`, `drinks`, `symptoms`) are
allowed. Readers must ignore keys they don't know.

## Running it as an agentic loop

A long-lived agent thread with a daily scheduled prompt works better than a desktop
notification: the agent asks, records and reflects in one place, and keeps its own brief
(protocol, baselines, current context) in a private file it re-reads after every context
compaction. The scheduled prompt should only say "read the brief and run the check-in", so
no personal detail sits in the scheduler.

## Example reply

```
Body 5: tired, matches a short night (6.4 h, HRV 47 vs your 50 baseline).
Mind 8: calm despite that.
Spirit 5: partly connected; the walk counted.
Tomorrow: same wake time, and 10 minutes outside before screens.
```
