"""Readers for the distilled layer: a knowledge graph and a memory directory.

Both are optional.  On a machine without a bstack-style workspace they simply
report unavailable and the cards that depend on them are dropped — the skill
still produces a full deck from the transcript stores alone.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..model import SourceReport

KG_NAME = "knowledge_graph"
MEMORY_NAME = "memory"

_WIKILINK = re.compile(r"\[\[([^\]|#]+)")
_TITLE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


@dataclass(slots=True)
class GraphStats:
    """Shape of a wikilink-connected markdown graph."""

    entities: int = 0
    edges: int = 0
    dangling: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    most_linked: list[tuple[str, int, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "entities": self.entities,
            "edges": self.edges,
            "dangling": self.dangling,
            "by_type": self.by_type,
            "most_linked": [
                {"slug": slug, "inbound": n, "title": title} for slug, n, title in self.most_linked
            ],
        }


def _scan_graph(files: list[Path], type_of) -> GraphStats:
    stats = GraphStats(entities=len(files))
    slugs = {p.stem for p in files}
    titles: dict[str, str] = {}
    inbound: Counter[str] = Counter()
    by_type: Counter[str] = Counter()

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        by_type[type_of(path)] += 1
        heading = _TITLE.search(text)
        titles[path.stem] = heading.group(1) if heading else path.stem
        for target in _WIKILINK.findall(text):
            target = target.strip()
            if not target or target == path.stem:
                continue
            stats.edges += 1
            if target in slugs:
                inbound[target] += 1
            else:
                stats.dangling += 1

    stats.by_type = dict(sorted(by_type.items(), key=lambda kv: -kv[1]))
    stats.most_linked = [
        (slug, count, titles.get(slug, slug)) for slug, count in inbound.most_common(5)
    ]
    return stats


def read_kg(root: Path | None) -> tuple[SourceReport, GraphStats | None]:
    """Scan an entity graph laid out as ``<root>/<type>/<slug>.md``."""
    if root is None or not root.is_dir():
        reason = "no research/entities directory in this workspace"
        return SourceReport(KG_NAME, False, reason=reason), None
    files = [p for p in root.rglob("*.md") if p.name.lower() != "readme.md"]
    report = SourceReport(KG_NAME, True, root=str(root), files=len(files), records=len(files))
    return report, _scan_graph(files, lambda p: p.parent.name)


def read_memory(root: Path | None) -> tuple[SourceReport, GraphStats | None]:
    """Scan a flat memory directory of one-fact markdown files."""
    if root is None or not root.is_dir():
        reason = "no agent memory directory on this machine"
        return SourceReport(MEMORY_NAME, False, reason=reason), None
    files = [p for p in sorted(root.glob("*.md")) if p.name != "MEMORY.md"]
    report = SourceReport(MEMORY_NAME, True, root=str(root), files=len(files), records=len(files))
    return report, _scan_graph(files, lambda _p: "memory")
