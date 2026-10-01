"""A synthetic world for E1, so CI can replay the harness end to end without
the owner's transcripts (the real snapshot stays on the owner's machine).

Forty sessions, one invented topic each. Every topic has an entity whose claim
names it and one of eight colour groups, and a twin entity created after the
sessions (never a candidate).
Session i runs, in order:

    prompt  "how does the <topic i> relay behave under load"   -> gate injects topic i
    Bash    ls
    Read    topic i's entity                    a strict hit for the first prompt
    prompt  "check the <colour i> group settings"  noise: a word ten items share
    prompt  "notes on the <topic i+1> relay for later"  -> gate injects topic i+1
    Bash    true, 35 times                      no keys, nothing opened
    Read    topic i+1's entity                  needed, but past the 30-call window

so a working gate, with the floor PARAMS give it, makes two claims a session
and one strict hit. `always` also injects the colour group at the noise prompt
(all misses); `wrong-key` gets another session's topic; `never` abstains.
Every entity file is dated before the sessions, so no hit is an "edited later"
one, and no prompt names an entity's slug, so none is an echo.
"""
from __future__ import annotations

import os
import time

import s1_support as S

N_SESSIONS = 40
GAP_S = 3 * 3600
#: The prompt stage's floor: above what a colour word scores, below what a
#: topic word does.
PARAMS = {"version": "synthetic-e1", "stages": {"prompt": {"floor": 4.0}}}


COLOURS = ("amber", "cobalt", "indigo", "jade", "onyx", "pearl", "ruby", "slate")


def topics(n: int = N_SESSIONS):
    cons, vows = "bdfgklmnprstvz", "aeiou"
    out = []
    for i in range(n + 1):
        a, b, c = cons[i % 14], cons[(i * 5 + 3) % 14], cons[(i * 3 + 7) % 14]
        out.append("%s%s%s%s%s%so" % (a, vows[i % 5], b, vows[(i // 5) % 5], c, vows[(i // 2) % 5]))
    return out


ENTITY = """---
id: "pattern/topic-{w}"
type: pattern
created: "{created}"
core_claim: "The {w} relay sheds load after three retries; it belongs to the {colour} group."
---
# The {w} relay
"""


def write_world(world, now: float):
    """The corpus (s1_support's plus the topic entities) and the transcripts.
    Returns the topic list."""
    S.write_corpus(world)
    ws = topics()
    t_first = now - (N_SESSIONS + 2) * GAP_S
    ents = world.broomva / "research" / "entities" / "pattern"
    before = time.strftime("%Y-%m-%d", time.gmtime(t_first - 30 * 86400))
    after = time.strftime("%Y-%m-%d", time.gmtime(now + 2 * 86400))
    for i, w in enumerate(ws):
        c = COLOURS[i % len(COLOURS)]
        (ents / ("topic-%s.md" % w)).write_text(ENTITY.format(w=w, colour=c, created=before))
        (ents / ("topic-%s-later.md" % w)).write_text(ENTITY.format(w=w, colour=c, created=after))
    old = t_first - 86400
    for root in (world.broomva / "research", world.broomva / "docs", S.memory_dir(world.home, world.broomva)):
        for dirpath, _, files in os.walk(str(root)):
            for f in files:
                os.utime(os.path.join(dirpath, f), (old, old))
    for i in range(N_SESSIONS):
        w, v = ws[i], ws[i + 1]
        t = S.Transcript(world, "syn-%02d" % i, world.broomva, t_first + i * GAP_S)
        t.prompt("how does the %s relay behave under load" % w)
        t.tool("Bash", command="ls")
        t.tool("Read", file_path=str(ents / ("topic-%s.md" % w)))
        t.prompt("check the %s group settings" % COLOURS[i % len(COLOURS)])
        t.prompt("notes on the %s relay for later" % v)
        for _ in range(35):
            t.tool("Bash", command="true")
        t.tool("Read", file_path=str(ents / ("topic-%s.md" % v)))
        t.save()
    return ws
