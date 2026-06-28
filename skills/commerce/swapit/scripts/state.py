"""Swapit state layer — local-first, two-realm storage.

Two hard-separated realms live under the data root (default ``~/.config/swapit``):

* **Realm 1 — KNOWLEDGE** (shareable): ``knowledge/*.jsonl`` — hazards, item-classes,
  alternatives, products. Generic, non-identifying facts. Safe to contribute (M3).
* **Realm 2 — INVENTORY** (PRIVATE, never synced): ``inventory/*`` — the user's items,
  rooms, swaps, bookmarks + an append-only ``events.jsonl`` audit log.

Principle: *the skill's state is the source of truth — the agent is the app.* Every
mutation appends an event to the audit log and updates a materialized JSON document.

The data root is overridable with ``$SWAPIT_HOME`` (used by tests) and otherwise honors
``$XDG_CONFIG_HOME``.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

ISO = "%Y-%m-%dT%H:%M:%SZ"

DEFAULT_ROOMS = [
    "kitchen",
    "bathroom",
    "bedroom",
    "living-room",
    "laundry",
    "nursery",
    "garage",
    "office",
]

# --- THE PRIVACY BOUNDARY (single source of truth for M3 anonymization) ---------
#
# The contribution model is an ALLOWLIST, not a denylist: a payload sent to the
# commons is built *only* from the SHAREABLE_* fields below. Everything else is
# private by default — including `name`, which is free text and the field most
# likely to carry identifying detail ("Grandma's bottle from the Berlin flat").
#
# Note `usage` is deliberately NOT private: its sub-keys (frequency, food/heat/child
# contact) are the non-identifying signal that drives risk and is the most valuable
# thing to contribute. The allowlist picks those sub-keys explicitly.

# Item/usage fields that are SAFE to contribute (generic, non-identifying).
SHAREABLE_ITEM_FIELDS = frozenset({"item_class", "condition"})
SHAREABLE_USAGE_FIELDS = frozenset({"frequency", "food_contact", "heat", "child_contact"})

# Belt-and-suspenders denylist: field names that must NEVER appear in a contribution
# payload. The privacy test (tests/test_privacy.py) and the M3 anonymizer both assert
# that no key in this set survives anonymization. Includes the swap-side identifying
# fields (checklist text, bookmark url/title, cost/vendor) and forward-looking names
# (owner/location/household/purchased) that are forbidden if ever added to a schema.
PRIVATE_FIELDS = frozenset(
    {
        # item-level
        "name",
        "room",
        "quantity",
        "brand",
        "acquired",
        "notes",
        "photos",
        # swap-level
        "cost",
        "vendor",
        "procurer_report_ref",
        "checklist",
        "bookmarks",
        "url",
        "title",
        # forward-looking — forbidden if ever introduced
        "owner",
        "location",
        "household",
        "purchased",
    }
)


def now_iso() -> str:
    return time.strftime(ISO, time.gmtime())


# --------------------------------------------------------------------------- paths
def data_root() -> Path:
    env = os.environ.get("SWAPIT_HOME")
    if env:
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "swapit"


def knowledge_dir() -> Path:
    return data_root() / "knowledge"


def inventory_dir() -> Path:
    return data_root() / "inventory"


def contributions_dir() -> Path:
    return data_root() / "contributions"


def sync_dir() -> Path:
    return data_root() / "sync"


def photos_dir() -> Path:
    return data_root() / "photos"


def ensure_dirs() -> None:
    for d in (knowledge_dir, inventory_dir, contributions_dir, sync_dir, photos_dir):
        d().mkdir(parents=True, exist_ok=True)
    # The private realm (inventory, photos, sync config/queue) is owner-only — it holds
    # what you own and where. Best-effort chmod (no-op on filesystems without POSIX modes).
    for d in (data_root, inventory_dir, photos_dir, contributions_dir, sync_dir):
        try:
            os.chmod(d(), 0o700)
        except OSError:
            pass


# ----------------------------------------------------------------- jsonl / json io
def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:  # pragma: no cover - surfaced by self-heal
            raise ValueError(f"{path}:{i}: invalid JSON: {exc}") from exc
    return out


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    """Atomic write (tmp + replace) so a crash never truncates state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ------------------------------------------------------------- materialized realm 2
def _items_path() -> Path:
    return inventory_dir() / "items.json"


def _swaps_path() -> Path:
    return inventory_dir() / "swaps.json"


def _rooms_path() -> Path:
    return inventory_dir() / "rooms.json"


def _bookmarks_path() -> Path:
    return inventory_dir() / "bookmarks.json"


def events_path() -> Path:
    return inventory_dir() / "events.jsonl"


def load_items() -> dict:
    return read_json(_items_path(), {})


def save_items(d: dict) -> None:
    write_json(_items_path(), d)


def load_swaps() -> dict:
    return read_json(_swaps_path(), {})


def save_swaps(d: dict) -> None:
    write_json(_swaps_path(), d)


def load_rooms() -> list[str]:
    return read_json(_rooms_path(), [])


def save_rooms(rooms: list[str]) -> None:
    write_json(_rooms_path(), rooms)


def load_bookmarks() -> dict:
    return read_json(_bookmarks_path(), {})


def save_bookmarks(d: dict) -> None:
    write_json(_bookmarks_path(), d)


def log_event(event_type: str, payload: dict) -> None:
    """Append to the immutable audit trail. Newest last."""
    append_jsonl(events_path(), {"ts": now_iso(), "type": event_type, "payload": payload})


def is_initialized() -> bool:
    return (knowledge_dir() / "item-classes.jsonl").exists()
