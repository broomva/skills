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

0. **Safety before anything.** If the user's message, or any answer at any step, shows
   danger (self-harm, an emergency symptom happening now), stop the protocol: say the
   [safety lines](#safety-lines-not-coaching) first and do nothing else that turn. No
   snapshot, no sync, no questions, no storage. Resume another time, only if the user wants to.
1. **Snapshot.** `health status`; if the store is stale, sync. Read last night's sleep
   (`health raw --endpoint sleep` for the night) and the last 7 journal entries.
2. **Ask, don't interrogate.** One structured question call (AskUserQuestion in Claude Code),
   four questions, each with 3–4 options plus free text. Keep the wording warm and short:
   - Body: "How did your body feel today?" (Strong · Okay · Tired or heavy · Unwell)
   - Mind: "How was your mind today?" (Calm, clear · Okay · Stressed or anxious · Low or flat)
   - Spirit: "Did today feel connected to what matters to you?" (Yes · Partly · Disconnected · Hard to say)
   - One user-defined item the user is tracking (a habit, a craving, a symptom)
   Then one optional follow-up: "What did you do for yourself today?" (multi-select:
   moved · time outside · time with someone · reflection), a free-text note, and
   "Any intention for tomorrow?". Its options are up to three drawn from what the user has
   chosen or done before, plus their own words.
3. **Record** the answers in the journal (see *Storage*). The label goes in verbatim, and so
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
Say these plainly, and first:
- **Thoughts of self-harm, or danger right now:** the local emergency number now (for
  example 911, 112 or 123). Then a crisis line for the user's country: use one the user has
  recorded, or point to a directory such as findahelpline.com if the location is unknown.
- **Low mood on most recent days, or words of hopelessness:** suggest talking to a doctor or
  a trusted person this week, and give the same crisis-line route.
- **Chest pain, fainting, or palpitations with dizziness happening now:** emergency services
  now. If it has passed: a clinician the same day. A fever lasting more than a couple of
  days: a clinician. None of these is a journal entry.

## Storage

- **Path:** `journal.jsonl` in the skill's data directory (`$BROOMVA_HEALTH_DATA_DIR`, default
  `~/broomva-health/`). It is created 0700 and sits outside every repo, like the traces
  (see [References/privacy-architecture.md](../References/privacy-architecture.md)). The
  journal holds the most sensitive data the skill touches (mood, symptoms, substances, the
  user's own words), so the file is 0600. A user may choose another folder only if, before
  the first write, the agent verifies it is owner-only (0700), not inside a git work tree,
  and not inside a cloud-synced folder. Otherwise it refuses and uses the default.
- **One object per date.** Writing a date merges into that date's object: new keys win and
  old keys stay, so a late follow-up never erases the first answers. Writes are
  single-writer: take an exclusive lock on `journal.lock` (`flock`, wait at most 10 s), read every line, merge,
  write the whole file to a temp file in the same directory, fsync it, `os.replace` it over
  the journal, then release the lock. A scheduled check-in and an on-demand one can then
  never interleave, duplicate a date or leave half a line. A line that does not parse is kept
  verbatim and reported, never dropped. If the lock can't be taken in 10 s, or the write
  fails, write nothing. Tell the user, and keep the answers in the reply so they can be
  recorded next time. A missing journal is created on the first write (0600).

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
