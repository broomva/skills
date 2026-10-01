#!/usr/bin/env python3
"""ctx-s1: the System 1 gate's own command (ctx.py's CLI belongs to the core).

    ctx-s1 [-C DIR] build [--scope ID] [--no-network] [--ranker bm25] [--json]   System 2: the cache
    ctx-s1 [-C DIR] eval  --snapshot DIR [--params P] [--out DIR] [--ranker bm25|ppr]   E1
    ctx-s1 [-C DIR] tune  --snapshot DIR [--params P] [--trials N] [--ledger L] ...      E3
    ctx-s1 [-C DIR] snapshot --out DIR [--scope ID] [--days N]                          a new E1 snapshot
    ctx-s1 [-C DIR] follow [--days N]                                                    live follow-through

`build` is ctx_s2.py; the rest is ctx_s1_eval.py. The hook itself is
ctx-s1-hook.sh -> ctx_s1_hook.py -> ctx_s1.py, and imports none of this.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    head = 2 if args[:1] == ["-C"] else 0
    if len(args) <= head or args[head] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if len(args) > head else 2
    if args[head] == "build":
        import ctx_s2

        return ctx_s2.main(args)
    import ctx_s1_eval

    return ctx_s1_eval.main(args)


if __name__ == "__main__":
    sys.exit(main())
