# The ladder, the oracle, and passthrough

## Rungs

| Rung | Definition | You are done with this rung when |
|---|---|---|
| 1 · Data and config | You change only what the program already reads: settings, themes, CSS, data files, profiles. | The program picks the change up with no code of yours running. |
| 2 · Sanctioned API | You use an extension point the makers offer: a plugin, an extension or scripting API, an OS automation interface, a documented protocol. | Your code runs through their interface, within the permissions it grants. |
| 3 · Patch from inside | You run code inside the program that its API does not expose: a managed-code patch, an injected script in a renderer, a userscript. | Your code runs in-process and the program still verifies as itself. |
| 4 · Hooks and wires | You work on native code or on the wire: function hooks, a proxy library, network capture and override, an undocumented device protocol. | You can observe and change the behaviour at the boundary. |
| 5 · Reimplement | You rebuild the part you need against the original as oracle: a clone, a decomp, your own client or firmware. | Your version matches the original on the inputs that matter. |

**Choosing.** Start at rung 1 and go up only when the idea needs it. The question is never
"what is the most powerful route?". It is "what is the cheapest route that reaches this idea?".

Rungs cost more as you climb for four reasons:
- they break more often on update;
- they need more of the target's internals;
- they reach closer to its protections;
- they are harder for the next person to install.

A rung-2 mod that covers 80% of the idea usually beats a rung-4 mod that covers all of it.
Say which you chose, and why, in the journal.

**Per sub-goal, not per project.** The route is picked for each sub-goal, and re-picked on a
stall. A re-pick must pass the Rules again. One failure worth checking for first is
rebuilding (rung 5) a component that could simply be run.
- In the Bishop Fox SonicWall firmware write-up (2026-07-08), "Claude did not step back on its
  own. It kept grinding at the failing decryption". The appliance already shipped a working
  implementation, and the fix was to run it.
- The page also carries Claude's own account claiming the idea, so this is one contested
  specimen, not a measured rate.

## The oracle

The running original is the oracle; your reading of the code is not. Shipped tests are a
weaker stand-in. A 2026 study of LLM decompilers (arXiv 2609.05370) found that candidates
passing every shipped test still diverged from the original 4.9% of the time.

**Scriptable runtime.** Build the smallest harness that can do four things to the real
target:
- launch it, in a lab profile;
- act on it, through the API you chose;
- wait for a state;
- capture evidence: a screenshot, a log line, a state dump.

Each run writes its evidence to a file, and `modlog.py ok` records the path. A step with no
artifact did not happen.

**Fake host stand-ins.** When the real target is slow, scarce or dangerous to poke (energy
hardware, a device you could brick, a game that takes minutes to load), build against a fake
that replays recorded traffic or known state first. Then confirm on the real one. SkyCraft
ships `fake_skyrim.py` for this. universal-modder built its GTA V compositor against a fake
D3D11 host before the game was installed.

**Circuit breaker.** The same failure three times on the same route is a stall (`modlog.py
fail` exits 3). Stop and re-rank; don't retry.

## Passthrough

Two programs run at once and exchange state over `127.0.0.1`: the host draws the guest inside
its own frame, and the host's world (collision, events) flows back. No run of this skill has
exercised it yet. The design to start from is in universal-modder's `mashup-mods` skill (see
NOTICE). Begin with its first milestone, one cube from A drawn in B at the right spot. Decide
three things in co-simulation terms first: when state is exchanged, whose clock is
authoritative, and who owns each shared thing.
