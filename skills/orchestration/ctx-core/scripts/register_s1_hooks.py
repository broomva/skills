#!/usr/bin/env python3
"""Register (or remove) the ctx System 1 gate's hooks in ~/.claude/settings.json.

The owner runs this, outside any agent session; no agent edits settings.json.

    python3 register_s1_hooks.py                              # list the stages; change nothing
    python3 register_s1_hooks.py --stages pre-edit,post-bash --shadow
    python3 register_s1_hooks.py --stages pre-edit --dry-run  # print the result, write nothing
    python3 register_s1_hooks.py --stages subagent,pre-edit --shadow \\
        --params ../references/s1-params.candidate.json      # shadow the tuned floors
    python3 register_s1_hooks.py --remove                     # every ctx-s1 entry out

Every stage is off unless named: with no --stages it registers nothing. It
backs settings.json up first, appends one matcher group per stage (it never
replaces anyone else's entry), and is idempotent: a second run with the same
stages changes nothing, and a run with another set replaces only the ctx-s1
groups. Each command carries its own flags (`CTX_S1=1 CTX_S1_STAGES=<stage>`,
plus `CTX_S1_SHADOW=1` with --shadow, which logs decisions and injects
nothing: spec B2). A file at ~/.config/ctx/s1-off turns every stage off without
editing settings.json.

post-bash note: the spec (workspace#840 §6.2) runs the Bash stage inside
ctx-core's phase-2 PostToolUse claims hook, as a library call, so there is one
registration on that matcher. Phase 2 is not built; until it is, post-bash is
registered here on its own.
"""
import argparse
import json
import os
import shlex
import shutil
import stat
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import ctx_s1  # noqa: E402  (the one stage table: events, matchers)

WRAPPER = os.path.join(HERE, "ctx-s1-hook.sh")
MARK = "ctx-s1-hook.sh"
DEFAULT_PYTHON = "/opt/homebrew/bin/python3"
#: Claude Code's outer timeout per stage, in seconds. The hook's own deadline is
#: far tighter (ctx_s1.STAGES `deadline_ms`); this is only the harness's bound.
TIMEOUTS = {"pre-edit": 1, "post-read": 1, "post-bash": 1}
STAGES = {st: (cfg["event"], cfg.get("matcher"), TIMEOUTS.get(st, 2)) for st, cfg in ctx_s1.STAGES.items()}


def command(stage, python, wrapper, shadow, params=None):
    env = ["CTX_S1=1", "CTX_S1_STAGES=%s" % stage]
    if shadow:
        env.append("CTX_S1_SHADOW=1")
    if params:
        env.append("CTX_S1_PARAMS=%s" % shlex.quote(params))
    env.append("CTX_PYTHON=%s" % shlex.quote(python))
    return "%s /bin/sh %s %s" % (" ".join(env), shlex.quote(wrapper), stage)


def is_s1_hook(h):
    return isinstance(h, dict) and MARK in str(h.get("command", ""))


def apply(data, stages, python, wrapper, shadow, remove, params=None):
    hooks = data.setdefault("hooks", {})
    changes = []
    for event in sorted({STAGES[s][0] for s in STAGES}):
        groups = hooks.get(event, [])
        kept, removed = [], 0
        for g in groups:
            inner = g.get("hooks", []) if isinstance(g, dict) else []
            mine = [h for h in inner if is_s1_hook(h)]
            if not mine:
                kept.append(g)
                continue
            removed += len(mine)
            rest = [h for h in inner if not is_s1_hook(h)]
            if rest:  # someone else's hook shares the group: keep the group and theirs
                kept.append(dict(g, hooks=rest))
        if removed:
            changes.append("removed %d ctx-s1 hook(s) from %s" % (removed, event))
        if kept:
            hooks[event] = kept
        elif event in hooks:
            del hooks[event]
    if not remove:
        for stage in stages:
            event, matcher, timeout = STAGES[stage]
            group = {"hooks": [{"type": "command", "timeout": timeout,
                                "command": command(stage, python, wrapper, shadow, params)}]}
            if matcher:
                group = {"matcher": matcher, **group}
            hooks.setdefault(event, []).append(group)
            changes.append("added %s on %s%s%s" % (stage, event, " (%s)" % matcher if matcher else "",
                                                   ", shadow" if shadow else ""))
    if not hooks:
        del data["hooks"]
    return changes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stages", default="", help="comma list of stages to register (default: none)")
    ap.add_argument("--shadow", action="store_true", help="log decisions, inject nothing")
    ap.add_argument("--remove", action="store_true", help="remove every ctx-s1 entry")
    ap.add_argument("--settings", default=os.path.expanduser("~/.claude/settings.json"))
    ap.add_argument("--python", default=DEFAULT_PYTHON)
    ap.add_argument("--wrapper", default=WRAPPER)
    ap.add_argument("--params", help="floors file for these stages (e.g. references/s1-params.candidate.json "
                                     "for a shadow run); default: the shipped references/s1-params.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        print("unknown stage(s): %s; known: %s" % (", ".join(unknown), ", ".join(STAGES)), file=sys.stderr)
        return 2
    if not stages and not args.remove:
        print("No stage named, so nothing is registered (every stage is off by default).")
        print("Stages: " + ", ".join(STAGES))
        print("Example: %s --stages pre-edit,post-bash --shadow" % os.path.basename(sys.argv[0]))
        return 0
    if not os.path.isfile(args.wrapper):
        print("wrapper not found: %s" % args.wrapper, file=sys.stderr)
        return 1
    with open(args.settings) as fh:
        data = json.load(fh)
    before = json.dumps(data, sort_keys=True)
    if not args.remove and not os.path.isfile(args.python):
        print("interpreter not found: %s (pass --python)" % args.python, file=sys.stderr)
        return 1
    params = os.path.abspath(args.params) if args.params else None
    changes = apply(data, stages, args.python, args.wrapper, args.shadow, args.remove, params)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    json.loads(text)  # validate before writing
    if json.dumps(data, sort_keys=True) == before:
        print("nothing to do (already in the requested state)")
        return 0
    if args.dry_run:
        print(text)
        print("\n".join(changes))
        return 0
    backup = "%s.bak-ctx-s1-%s" % (args.settings, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(args.settings, backup)
    mode = stat.S_IMODE(os.stat(args.settings).st_mode)
    tmp = args.settings + ".tmp-ctx-s1"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.chmod(tmp, mode)  # the original's permissions, whatever the umask
    os.replace(tmp, args.settings)
    print("backup: %s" % backup)
    print("\n".join(changes))
    if "post-bash" in stages:
        print("note: post-bash moves inside ctx-core's phase-2 claims hook when that exists (spec §6.2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
