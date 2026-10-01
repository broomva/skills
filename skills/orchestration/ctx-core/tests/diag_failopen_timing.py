"""TEMPORARY diagnostic (removed before merge): the wall-time distribution of the
fail-open `hangs` case, split into the hook's own deadline record and the rest.

    python tests/diag_failopen_timing.py [N]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "scripts" / "ctx_hook.py"
KINDS = {
    "hangs": "import time\ndef run_hook(event, raw, deadline):\n    time.sleep(30)\n    return 'late'\n",
    "raises": "def run_hook(event, raw, deadline):\n    raise ValueError('boom')\n",
}


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def summary(name, xs):
    return "%-28s n=%d p50=%.0f p90=%.0f p99=%.0f max=%.0f ms" % (
        name, len(xs), q(xs, .5) * 1e3, q(xs, .9) * 1e3, q(xs, .99) * 1e3, max(xs) * 1e3)


def main(n):
    tmp = Path(tempfile.mkdtemp())
    home = tmp / "home"
    (home / ".config" / "ctx").mkdir(parents=True)
    (home / ".config" / "ctx" / "scopes.yaml").write_text("version: 1\nscopes: {}\n")
    env = dict(os.environ, HOME=str(home))
    env.pop("CTX_HOOK_BUDGET_MS", None)
    misses = home / ".local" / "state" / "ctx" / "hook-misses.jsonl"
    lines = []
    bare = []
    for _ in range(n):
        t0 = time.monotonic()
        subprocess.run([sys.executable, "-I", "-S", "-c", "import os, signal, sys, time"], env=env)
        bare.append(time.monotonic() - t0)
    lines.append(summary("bare -I -S start+exit", bare))
    for kind, src in KINDS.items():
        d = tmp / kind
        d.mkdir()
        shutil.copy2(HOOK, d / "ctx_hook.py")
        (d / "ctx.py").write_text(src)
        for event in ("session-start", "stop", "stop-failure"):
            wall, rec, rest = [], [], []
            for _ in range(n):
                if misses.exists():
                    misses.unlink()
                t0 = time.monotonic()
                p = subprocess.run([sys.executable, "-I", "-S", str(d / "ctx_hook.py"), event],
                                   input=json.dumps({"session_id": "s-1", "cwd": str(tmp)}).encode(),
                                   capture_output=True, env=env, timeout=30)
                el = time.monotonic() - t0
                assert (p.returncode, p.stdout, p.stderr) == (0, b"", b""), p
                wall.append(el)
                if kind == "hangs":
                    ms = json.loads(misses.read_text().splitlines()[-1])["ms"] / 1e3
                    rec.append(ms)
                    rest.append(el - ms)
            lines.append(summary("%s/%s wall" % (kind, event), wall))
            if rec:
                lines.append(summary("%s/%s record ms" % (kind, event), rec))
                lines.append(summary("%s/%s wall - record" % (kind, event), rest))
    out = "\n".join(lines)
    print(out)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("```\n%s\n```\n" % out)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 50)
