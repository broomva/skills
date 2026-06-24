"""Swapit knowledge realm (Realm 1) — load + resolve the shared, shareable graph.

The knowledge graph is three node types plus an optional product layer:

* **hazard**       — a chemical / substance class of concern (BPA, PFAS, phthalates, ...)
* **item_class**   — a generic product category that typically carries hazards
* **alternative**  — a safer swap target; ``replaces`` lists the item-classes it covers
* **product**      — (optional, crowd-sourced) a specific branded SKU mapped to item-classes

Edges:
    item_class --contains--> hazard          (item_class.hazards[].hazard_id)
    alternative --replaces--> item_class      (alternative.replaces[])
    alternative --avoids--> hazard            (alternative.avoids_hazards[])

Seed data ships in ``skills/swapit/seed/*.jsonl`` and is copied into the data root on
``init``. Thereafter the knowledge cache may also be enriched from the networked commons
(M3) — but the seed is always a usable, offline-complete baseline.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import state

SKILL_ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = SKILL_ROOT / "seed"

_FILES = {
    "hazards": "hazards.jsonl",
    "item_classes": "item-classes.jsonl",
    "alternatives": "alternatives.jsonl",
    "products": "products.jsonl",
}


def seed_into_data_root(force: bool = False) -> list[str]:
    """Copy bundled seed knowledge into the data root. Returns the files written."""
    state.ensure_dirs()
    written: list[str] = []
    for key, fname in _FILES.items():
        dest = state.knowledge_dir() / fname
        src = SEED_DIR / fname
        if dest.exists() and not force:
            continue
        if src.exists():
            shutil.copyfile(src, dest)
            written.append(fname)
        elif key == "products" and not dest.exists():
            dest.write_text("", encoding="utf-8")
            written.append(fname)
    return written


class Knowledge:
    """In-memory view over the knowledge cache, keyed by id for O(1) resolution."""

    def __init__(self) -> None:
        kdir = state.knowledge_dir()
        self.hazards = {r["id"]: r for r in state.read_jsonl(kdir / _FILES["hazards"])}
        self.item_classes = {
            r["id"]: r for r in state.read_jsonl(kdir / _FILES["item_classes"])
        }
        self.alternatives = {
            r["id"]: r for r in state.read_jsonl(kdir / _FILES["alternatives"])
        }
        self.products = {r["id"]: r for r in state.read_jsonl(kdir / _FILES["products"])}

    # ---- lookups -------------------------------------------------------------
    def hazard(self, hid: str) -> dict | None:
        return self.hazards.get(hid)

    def item_class(self, cid: str) -> dict | None:
        return self.item_classes.get(cid)

    def alternative(self, aid: str) -> dict | None:
        return self.alternatives.get(aid)

    def hazards_for_class(self, cid: str) -> list[dict]:
        """Resolved hazard records present in an item-class, each annotated with the
        per-class ``presence_likelihood`` and ``rationale`` edge data."""
        cls = self.item_classes.get(cid)
        if not cls:
            return []
        out: list[dict] = []
        for edge in cls.get("hazards", []):
            hz = self.hazards.get(edge.get("hazard_id"))
            if not hz:
                continue
            merged = dict(hz)
            merged["presence_likelihood"] = edge.get("presence_likelihood", 0.5)
            merged["rationale"] = edge.get("rationale", "")
            out.append(merged)
        return out

    def alternatives_for_class(self, cid: str) -> list[dict]:
        """All alternatives whose ``replaces`` list covers this item-class."""
        return [
            a
            for a in self.alternatives.values()
            if cid in a.get("replaces", [])
        ]

    def search(self, query: str, kind: str | None = None) -> list[dict]:
        """Substring search across name / id / aliases / description. ``kind`` filters
        to one of hazard|item-class|alternative."""
        q = query.lower().strip()
        pools = {
            "hazard": self.hazards.values(),
            "item-class": self.item_classes.values(),
            "alternative": self.alternatives.values(),
        }
        results: list[dict] = []
        for k, pool in pools.items():
            if kind and k != kind:
                continue
            for rec in pool:
                hay = " ".join(
                    str(rec.get(f, ""))
                    for f in ("id", "name", "description", "material", "mechanism")
                ).lower()
                hay += " " + " ".join(str(a) for a in rec.get("aliases", []))
                if q in hay:
                    results.append({"kind": k, **rec})
        return results

    def stats(self) -> dict:
        return {
            "hazards": len(self.hazards),
            "item_classes": len(self.item_classes),
            "alternatives": len(self.alternatives),
            "products": len(self.products),
        }
