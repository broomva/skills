# Field notes

A field note is what the next agent reads before touching the same target. It is worth
writing for a failed mod too. A documented dead end is the cheapest kind of help.

`modlog.py note --out <work>/field-note.md` scaffolds one from the journal, in the run's own
folder.
`modlog.py lint-note <path>` checks it. The lint requires six sections, in any order:

| Section | Must contain |
|---|---|
| `## Versions` | the exact target version, the OS, and the tool and loader versions that worked |
| `## Route` | the rung(s) taken, numbered, with the reason, and any stalls with what was re-ranked |
| `## What it really does` | what the target was observed to do, as opposed to what its docs or your first reading said |
| `## Verification` | at least one piece of evidence: a `path` to a screenshot, log or dump, or a [link](url). Every cited path must exist, relative to the note or to the skill root |
| `## Gotchas` | a numbered list, each item `symptom → cause → fix` |
| `## Envelope` | the rung, the terms that permit the mod, what is shipped, and the disclosure status |

The lint also fails while any `TODO(mod-anything)` placeholder remains. Gotchas may wrap over several lines; continuation lines are joined to their item.

**What makes a gotcha useful.** The symptom is what you saw, written so someone searching for
it finds it. The cause is what was actually wrong. The fix is what made it work. "Plugin
missing → folder name differs from the manifest id → rename the folder to the id" is useful.
"Fixed the plugin" is not.

**Where notes go.**
1. Write and lint the note in `<work>`. It copies journal text, which may be private.
2. Run `publish_check.py` over the mod and the note together, with your deny file.
3. Only then copy it to `field-notes/<target>/` in this skill, so it ships with it. A shared
   note cites only evidence that ships too (under `examples/`).

Search before you start: `grep -ril "<target>" field-notes/`.
