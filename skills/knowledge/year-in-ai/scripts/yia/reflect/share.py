"""A review draft of a reflection for sharing: the user's words, links and paths removed.

It is not share-safe by itself. Redaction can remove what it can recognise
(quoted and copied text, links, paths, named terms), but a short name, a
credential or a paraphrase of something private in model-written prose is not
recognisable, so a person reads the draft before it leaves the machine.

The private reflection quotes prompts verbatim and names repositories and
branches. Anything that leaves the machine goes through :func:`redact`:
blockquotes, quoted spans of every kind and inline code become a placeholder,
and so does any run of ``VERBATIM_WORDS`` or more words that appears in a
prompt or reply, quoted or not, matched across line breaks, independent of
markup. URLs and filesystem paths
are removed, and every ``--redact-term`` is replaced wherever it appears.
Episode citations stay: they are opaque hashes.
"""

from __future__ import annotations

import re
from typing import Iterable, Set

from ..redact import PLACEHOLDER

QUOTE_REMOVED = "«quote removed»"
_URL = re.compile(r"https?://\S+")
# Any absolute or home-relative path with at least two segments, whatever its
# root: `/workspace/acme/x`, `/srv/...`, `~/notes`. A lone `/checkit` is a
# command, not a path.
_PATH = re.compile(r"(?<![\w.:/])(?:~/|/[\w.@+-]+/)[^\s)\]`'\"]*")
_QUOTED = re.compile(r"“[^”]+”|‘[^’]+’|\"[^\"\n]+\"|(?<!\w)'[^'\n]+'(?!\w)|`[^`\n]+`")
_WORD = re.compile(r"\w+")

#: A run of this many words shared with a prompt or reply is removed.
VERBATIM_WORDS = 5


def ngrams(texts: Iterable[str], n: int = VERBATIM_WORDS) -> Set[int]:
    """Hashes of every run of ``n`` words (case-folded) in ``texts``."""
    out: Set[int] = set()
    for text in texts:
        words = [m.group(0).lower() for m in _WORD.finditer(text or "")]
        out.update(hash(tuple(words[i:i + n])) for i in range(len(words) - n + 1))
    return out


def _strip_verbatim(line: str, grams: Set[int], n: int = VERBATIM_WORDS) -> str:
    words = list(_WORD.finditer(line))
    hit = [False] * len(words)
    for i in range(len(words) - n + 1):
        if hash(tuple(m.group(0).lower() for m in words[i:i + n])) in grams:
            hit[i:i + n] = [True] * n
    out, pos, i = [], 0, 0
    while i < len(words):
        if not hit[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(words) and hit[j + 1]:
            j += 1
        # A run may cross line breaks; keep them so the markdown keeps its shape.
        span = line[words[i].start():words[j].end()]
        out += [line[pos:words[i].start()], QUOTE_REMOVED + "\n" * span.count("\n")]
        pos, i = words[j].end(), j + 1
    out.append(line[pos:])
    return "".join(out)


def redact(markdown: str, terms: Iterable[str] = (), private_texts: Iterable[str] = ()) -> str:
    """The share copy. ``private_texts`` are the prompts and replies whose word runs must not survive."""
    grams = ngrams(private_texts)
    if grams:
        # Matched over the whole document, not line by line: a copied run split
        # across a line break is still the same words.
        markdown = _strip_verbatim(markdown, grams)
    out = []
    for line in markdown.splitlines():
        if line.lstrip().startswith(">"):
            out.append("> " + QUOTE_REMOVED)
            continue
        # Every quoted span, whatever its length: a two-word quote can be a name.
        line = _QUOTED.sub(QUOTE_REMOVED, line)
        line = _URL.sub("«link»", line)
        line = _PATH.sub("«path»", line)
        out.append(line)
    text = "\n".join(out) + "\n"
    for term in sorted({t.strip() for t in terms if t and t.strip()},
                       key=len, reverse=True):
        # Word boundaries only where the term itself starts or ends with a word
        # character: "Project X (confidential)" must match before a space.
        left = r"(?<!\w)" if re.match(r"\w", term) else ""
        right = r"(?!\w)" if re.search(r"\w$", term) else ""
        text = re.sub(rf"(?i){left}{re.escape(term)}{right}", PLACEHOLDER, text)
    return text
