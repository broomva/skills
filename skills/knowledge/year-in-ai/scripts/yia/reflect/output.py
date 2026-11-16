"""Writing the episode stage into the private reflect directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from . import read_jsonl, write_json, write_private
from .digest import INSTRUCTIONS
from .episodes import batches


def write(outdir: Path, episodes: List[dict], pending: List[str], manifest: dict) -> dict:
    """Write episodes.jsonl, batches/, the digest instructions and the manifest. Returns the manifest."""
    write_private(outdir / "episodes.jsonl",
                  "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in episodes))
    batch_dir = outdir / "batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    for old in batch_dir.glob("batch-*.json"):
        old.unlink()
    groups = batches(episodes, pending)
    index = []
    for n, group in enumerate(groups, 1):
        name = f"batch-{n:03d}.json"
        write_json(batch_dir / name, {"batch": n, "episodes": group})
        index.append({"batch": n, "file": name, "episodes": [v["id"] for v in group]})
    write_json(batch_dir / "index.json", index)
    write_private(outdir / "digest-instructions.md", INSTRUCTIONS)
    manifest = dict(manifest, batches=len(groups), pending_digests=len(pending))
    write_json(outdir / "manifest.json", manifest)
    return manifest


def load_episodes(outdir: Path) -> List[dict]:
    return read_jsonl(outdir / "episodes.jsonl")


def batch_index(outdir: Path) -> list:
    path = outdir / "batches" / "index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
