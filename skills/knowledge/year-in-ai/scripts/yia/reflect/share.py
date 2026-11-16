"""A share-safe copy of a reflection: the user's words, links and paths removed.

The private reflection quotes prompts verbatim and names repositories and
branches. Anything that leaves the machine goes through :func:`redact`:
blockquotes and quoted spans become a placeholder, URLs and filesystem paths
are removed, and every ``--redact-term`` is replaced wherever it appears.
Episode citations stay: they are opaque hashes.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..redact import PLACEHOLDER

QUOTE_REMOVED = "«quote removed»"
_URL = re.compile(r"https?://\S+")
_PATH = re.compile(r"(?:~|/Users|/Volumes|/home|/private|/tmp|/opt)/[^\s)\]`'\"]*")
_QUOTED = re.compile(r"“[^”]+”|\"[^\"\n]+\"")


def redact(markdown: str, terms: Iterable[str] = ()) -> str:
    out = []
    for line in markdown.splitlines():
        if line.lstrip().startswith(">"):
            out.append("> " + QUOTE_REMOVED)
            continue
        line = _QUOTED.sub(lambda m: QUOTE_REMOVED if len(m.group(0).split()) >= 3 else m.group(0), line)
        line = _URL.sub("«link»", line)
        line = _PATH.sub("«path»", line)
        out.append(line)
    text = "\n".join(out) + "\n"
    for term in sorted({t.strip() for t in terms if t and t.strip()},
                       key=len, reverse=True):
        text = re.sub(rf"(?i)\b{re.escape(term)}\b", PLACEHOLDER, text)
    return text
