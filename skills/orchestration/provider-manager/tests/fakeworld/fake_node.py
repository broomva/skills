#!/usr/bin/env python3
"""A stand-in `node` that answers auth_helper.js's two commands for login tests: find-session
(the browser session's account, from FAKE_BROWSER_EMAIL/FAKE_BROWSER_ORG) and approve-oauth (a code
that fake_claude's `auth login` accepts)."""

import json
import os
import re
import sys


def main(argv):
    if len(argv) < 2 or not argv[0].endswith("auth_helper.js") or not os.environ.get("FAKE_BROWSER_EMAIL"):
        sys.stderr.write("fake node: refused (test guard)\n")
        return 99
    if argv[1] == "find-session":
        print(json.dumps({"session": {"email": os.environ["FAKE_BROWSER_EMAIL"],
                                      "organizationUuid": os.environ.get("FAKE_BROWSER_ORG")}}))
        return 0
    if argv[1] == "approve-oauth":
        m = re.search(r"state=([\w-]+)", argv[2])
        print(json.dumps({"formattedInput": "code-ok#%s" % (m.group(1) if m else "")}))
        return 0
    return 99


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
