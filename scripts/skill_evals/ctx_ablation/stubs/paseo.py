#!/usr/bin/env python3
"""``paseo`` inside a case: refuses, and logs the attempt.

The real Paseo CLI talks to the operator's daemon, which listens on the host and is
not isolated by a moved HOME. A trial asked to check on Paseo sessions must not be
able to list, archive or message the operator's real agents. Paseo is reachable in
the case only through its MCP stub (``mcp__paseo__*``).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common  # noqa: E402

NAME = "paseo-cli"


def main(argv: list[str]) -> int:
    sys.stderr.write("paseo: the CLI is not available in this environment; "
                     "use the Paseo MCP tools (mcp__paseo__*)\n")
    _common.log(NAME, {"argv": list(argv), "rc": 1})
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
