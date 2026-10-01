"""A traversal ranker prototype: an E1 arm, never the default.

Spec workspace#840 §6.1 ranks candidates by one Personalized-PageRank pass over
typed links, seeded at the query's anchors, with each transition into a node
damped by its in-degree^-alpha so hubs do not win every query (HippoRAG). No
typed graph exists yet (Kinetic has no traversal); this prototype walks the
links the corpus already has: entity wikilinks and citations of another item's
file (ctx_s2.link_items).

It fills the same seam as BM25: postings, key -> scored items. For a key k, the
seed distribution is BM25's scores for k; one step of the walk moves `beta` of
each seed item's mass to the items it links to, split by out-degree and damped
by in-degree^-alpha. So it is PPR truncated at one hop, not the converged
walk, and it is labelled that way in every report. E1 scores it on the same
snapshot as BM25 (`ctx-s1 eval --ranker ppr`); by spec §6.6 it may become the
default only after it beats BM25 there and on the rewritten retrieval tasks.
"""

from __future__ import annotations

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any, Dict, List, Sequence, Tuple

import ctx_s2


class PPRRanker(ctx_s2.Ranker):
    name = "ppr1"
    version = 1

    def __init__(self, beta: float = 0.5, alpha: float = 0.5, top: int = ctx_s2.POSTINGS_TOP, **bm25):
        self.beta, self.alpha, self.top = beta, alpha, top
        self.seed = ctx_s2.BM25Ranker(top=top, **bm25)  # the same depth as the BM25 arm
        self.params = {"beta": beta, "alpha": alpha, "top": top, "hops": 1, "seed": "bm25",
                       "seed_params": self.seed.params}
        self._post: Dict[str, List[Tuple[int, float]]] = {}

    def fit(self, items: Sequence[Dict[str, Any]]) -> None:
        self.seed.fit(items)
        out_links = [list(it.get("links") or []) for it in items]
        indeg = [0] * len(items)
        for links in out_links:
            for j in links:
                if 0 <= j < len(items):
                    indeg[j] += 1
        damp = [(d + 1) ** -self.alpha for d in indeg]
        post: Dict[str, List[Tuple[int, float]]] = {}
        for key, seeds in self.seed.postings().items():
            mass: Dict[int, float] = {}
            for i, s in seeds:
                mass[i] = mass.get(i, 0.0) + (1 - self.beta) * s if out_links[i] else mass.get(i, 0.0) + s
                links = out_links[i]
                if not links:
                    continue
                share = self.beta * s / len(links)
                for j in links:
                    if 0 <= j < len(items):
                        mass[j] = mass.get(j, 0.0) + share * damp[j]
            ranked = sorted(mass.items(), key=lambda kv: (-kv[1], kv[0]))[: self.top]
            post[key] = ranked
        self._post = post

    def postings(self) -> Dict[str, List[Tuple[int, float]]]:
        return self._post
