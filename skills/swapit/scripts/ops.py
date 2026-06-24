"""Swapit state mutations — the single place inventory/swap state is changed.

Both the CLI (``swapit.py``) and the live dashboard server (``server.py``) call these
helpers, so the "agent is the app" guarantee holds: there is exactly one write path into
the state, whether the mutation originates from a command or a dashboard click.

Each op loads the relevant document, mutates it, saves atomically, and appends an audit
event — so a single API call or CLI flag is one coherent state transition.
"""
from __future__ import annotations

import state

STATUSES = ["keep", "flagged", "swap-planned", "sourcing", "swapped", "disposed"]


def _new_swap(item_id: str) -> dict:
    return {
        "id": state.gen_id("swp"),
        "item_id": item_id,
        "chosen_alternative": None,
        "procurement": {"status": "researching", "procurer_report_ref": None, "cost": None, "vendor": None},
        "checklist": [],
        "bookmarks": [],
        "started": state.now_iso(),
        "completed": None,
    }


def get_or_create_swap(swaps: dict, item_id: str) -> dict:
    """Return the swap for ``item_id`` from ``swaps`` (mutated in place), creating one if absent."""
    swap = next((s for s in swaps.values() if s["item_id"] == item_id), None)
    if swap is None:
        swap = _new_swap(item_id)
        swaps[swap["id"]] = swap
    return swap


def find_swap(item_id: str) -> dict | None:
    swaps = state.load_swaps()
    return next((s for s in swaps.values() if s["item_id"] == item_id), None)


# --------------------------------------------------------------------------- items
def add_item(
    *,
    name: str,
    item_class: str | None,
    room: str | None = None,
    quantity: int = 1,
    brand: str | None = None,
    acquired: str | None = None,
    condition: str = "good",
    usage: dict | None = None,
    status: str = "flagged",
    notes: str = "",
) -> dict:
    items = state.load_items()
    iid = state.gen_id("itm")
    item = {
        "id": iid,
        "name": name,
        "item_class": item_class,
        "room": room,
        "quantity": quantity,
        "brand": brand,
        "acquired": acquired,
        "condition": condition,
        "usage": usage or {"frequency": "occasional", "food_contact": False, "heat": False, "child_contact": False},
        "status": status,
        "notes": notes or "",
        "photos": [],
        "created": state.now_iso(),
        "updated": state.now_iso(),
    }
    items[iid] = item
    state.save_items(items)
    # ensure the room exists in the registry
    if room:
        rooms = state.load_rooms()
        if room not in rooms:
            rooms.append(room)
            state.save_rooms(rooms)
    state.log_event("item.add", {"id": iid, "name": name, "item_class": item_class})
    return item


def set_item_status(item_id: str, status: str) -> bool:
    items = state.load_items()
    if item_id not in items:
        return False
    items[item_id]["status"] = status
    items[item_id]["updated"] = state.now_iso()
    state.save_items(items)
    state.log_event("item.status", {"id": item_id, "status": status})
    return True


# --------------------------------------------------------------------------- swaps
def choose_alternative(item_id: str, alternative_id: str) -> dict:
    swaps = state.load_swaps()
    swap = get_or_create_swap(swaps, item_id)
    swap["chosen_alternative"] = alternative_id
    state.save_swaps(swaps)
    items = state.load_items()
    if item_id in items and items[item_id].get("status") in (None, "keep", "flagged"):
        items[item_id]["status"] = "swap-planned"
        items[item_id]["updated"] = state.now_iso()
        state.save_items(items)
    state.log_event("swap.choose", {"item_id": item_id, "alternative": alternative_id})
    return swap


def add_task(item_id: str, text: str) -> dict:
    swaps = state.load_swaps()
    swap = get_or_create_swap(swaps, item_id)
    task = {"id": state.gen_id("task"), "text": text, "done": False}
    swap["checklist"].append(task)
    state.save_swaps(swaps)
    state.log_event("swap.task.add", {"item_id": item_id, "task_id": task["id"]})
    return task


def set_task_done(item_id: str, ref: str, done: bool) -> bool:
    """Mark a checklist task done/undone by task id or text (first match only)."""
    swaps = state.load_swaps()
    swap = get_or_create_swap(swaps, item_id)
    for t in swap["checklist"]:
        if t["id"] == ref or t["text"] == ref:
            t["done"] = done
            state.save_swaps(swaps)
            state.log_event("swap.task.toggle", {"item_id": item_id, "task_id": t["id"], "done": done})
            return True
    return False


def toggle_task(item_id: str, task_id: str) -> bool:
    swaps = state.load_swaps()
    swap = get_or_create_swap(swaps, item_id)
    for t in swap["checklist"]:
        if t["id"] == task_id:
            t["done"] = not t["done"]
            state.save_swaps(swaps)
            state.log_event("swap.task.toggle", {"item_id": item_id, "task_id": task_id, "done": t["done"]})
            return True
    return False


def update_procurement(item_id: str, *, status: str | None = None, cost=None, vendor: str | None = None) -> dict:
    swaps = state.load_swaps()
    swap = get_or_create_swap(swaps, item_id)
    proc = swap["procurement"]
    if status is not None:
        proc["status"] = status
    if cost is not None:
        proc["cost"] = cost
    if vendor is not None:
        proc["vendor"] = vendor
    state.save_swaps(swaps)
    state.log_event("swap.procurement", {"item_id": item_id, **{k: v for k, v in (("status", status), ("cost", cost), ("vendor", vendor)) if v is not None}})
    return swap


def complete_swap(item_id: str) -> None:
    swaps = state.load_swaps()
    swap = get_or_create_swap(swaps, item_id)
    swap["completed"] = state.now_iso()
    swap["procurement"]["status"] = "installed"
    state.save_swaps(swaps)
    set_item_status(item_id, "swapped")
    state.log_event("swap.complete", {"item_id": item_id})


# ----------------------------------------------------------------------- bookmarks
def add_bookmark(url: str, title: str | None = None, attached_to: dict | None = None) -> str:
    bms = state.load_bookmarks()
    bid = state.gen_id("bkm")
    bms[bid] = {
        "id": bid,
        "url": url,
        "title": title or "",
        "attached_to": attached_to,
        "created": state.now_iso(),
    }
    state.save_bookmarks(bms)
    state.log_event("bookmark.add", {"id": bid, "url": url})
    return bid


def add_swap_bookmark(item_id: str, url: str, title: str | None = None) -> str:
    swaps = state.load_swaps()
    swap = get_or_create_swap(swaps, item_id)
    bid = add_bookmark(url, title, {"type": "swap", "id": swap["id"]})
    swap["bookmarks"].append(bid)
    state.save_swaps(swaps)
    return bid
