# Field notes

A field note is what the next agent reads before touching the same target. It is worth
writing for a failed mod too. A documented dead end is the cheapest kind of help.

`modlog.py note --out <work>/ship/field-notes/<target>/<slug>.md` scaffolds one from the
journal, in the tree that will ship (SKILL.md step 8). `modlog.py lint-note <note> --root
<work>/ship` checks it. The lint requires six sections, in any order:

| Section | Must contain |
|---|---|
| `## Versions` | the exact target version, the OS, and the tool and loader versions that worked |
| `## Route` | the rung(s) taken, numbered, with the reason, and any stalls with what was re-ranked |
| `## What it really does` | what the target was observed to do, as opposed to what its docs or your first reading said |
| `## Verification` | at least one piece of evidence: a `path` to a screenshot, log or dump made from a fixture you wrote, or a [link](url) to a public source. Cite paths from the root (`--root`, else the enclosing skill): they must exist there, and any absolute, `~/`, `..` or `file://` path fails, because it points at something that does not ship. The lint reads backticks, inline links and reference definitions in this section; HTML tags and definitions elsewhere are not read, so do not cite evidence that way. Evidence from real use is described without a path. Write commands without backticks: `` `/usr/bin/plutil -p x` `` reads as a path |
| `## Gotchas` | a numbered list, each item `symptom → cause → fix` (`->` works too), of what this run hit; or `None hit on this run` when the journal recorded no failure. Never invent one to fill the section |
| `## Envelope` | the rung, the terms that permit the mod, what is shipped, and one `Disclosure:` line starting `none found`, `embargoed (...)` or `cleared YYYY-MM-DD (...)`; the `cleared` date is a real date. Whatever the state, lint fails on any YYYY-MM-DD in the Envelope that has not arrived (it does not read "1 March 2027") and on a second `Disclosure:` label. One finding per note |

The lint also fails while any `TODO(mod-anything)` placeholder remains, and while the
note says "embargoed" anywhere: such a note stays private until the conditions in
`envelope.md` (Disclosure) are met and the line says `cleared`. The scaffold names
each journal evidence file in a placeholder instead of citing it, because the working folder
never ships: copy the file into `examples/<slug>/` and cite that path, or describe it. Gotchas may wrap over several lines; continuation lines are joined to their item.

**What makes a gotcha useful.** The symptom is what you saw, written so someone searching for
it finds it. The cause is what was actually wrong. The fix is what made it work. "Plugin
missing → folder name differs from the manifest id → rename the folder to the id" is useful.
"Fixed the plugin" is not.

**Where notes go.** In the ship tree, `<work>/ship/field-notes/<target>/<slug>.md`, next to
the mod in `<work>/ship/examples/<slug>/`. How the tree is checked, reviewed by the user and
copied is SKILL.md steps 8 and 9; this file does not repeat it.

Search before you start: `grep -ril "<target>" field-notes/`.
