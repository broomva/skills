"""swapit serve — the live local dashboard. The agent is the app.

A stdlib ``http.server`` (no framework, no build step) that renders the skill's
authoritative state and writes every mutation straight back through ``ops.py`` — the same
write path the CLI uses. The browser is a thin view: it ``fetch``es ``/api/state`` and
re-renders from whatever the skill's state says, so the filesystem stays the source of truth.

Binds to 127.0.0.1 only (single-user local tool; not exposed to the network).
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import knowledge  # noqa: E402
import ops  # noqa: E402
import report  # noqa: E402
import state  # noqa: E402
import swapit as cli  # noqa: E402  (reuse assess + _item_rows; already importable)

DEFAULT_PORT = 8731
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "dashboard.html"

# Serialize all writes: ThreadingHTTPServer runs each request on its own thread and the
# ops do load->mutate->save (full-file rewrite). The lock closes the lost-update window
# (write_json's tmp+replace prevents torn files, not lost updates).
_WRITE_LOCK = threading.Lock()

# Routes whose payload references an existing item — guarded so a phantom item_id can't
# create an orphan swap document (the CLI guards this; the server must too).
_ITEM_ROUTES = frozenset(
    {
        "/api/item/status",
        "/api/swap/choose",
        "/api/swap/task/add",
        "/api/swap/task/toggle",
        "/api/swap/complete",
        "/api/procurement",
    }
)


def state_payload() -> dict:
    """The full authoritative view the dashboard renders from."""
    kn = knowledge.Knowledge()
    items = state.load_items()
    swaps = state.load_swaps()
    bookmarks = state.load_bookmarks()
    rows = cli._item_rows(kn, items)

    items_out = []
    for r in rows:
        it, a = r["item"], r["assessment"]
        sw = next((s for s in swaps.values() if s["item_id"] == it["id"]), None) or {}
        items_out.append(
            {
                "id": it["id"],
                "name": it["name"],
                "room": it.get("room") or "unassigned",
                "item_class": it.get("item_class"),
                "status": it.get("status"),
                "score": a["risk"]["score"],
                "band": a["risk"]["band"],
                "hazards": [
                    {"name": c["name"], "risk": c["risk"]}
                    for c in a["risk"]["contributions"]
                    if c["risk"] > 0
                ],
                "alternatives": [
                    {"id": x["alternative_id"], "name": x["name"], "pct": x["pct"]}
                    for x in a["reductions"]
                ],
                "chosen": sw.get("chosen_alternative"),
                "checklist": sw.get("checklist", []),
                "bookmarks": [bookmarks[b] for b in sw.get("bookmarks", []) if b in bookmarks],
                "procurement": sw.get("procurement"),
            }
        )

    return {
        "summary": report.household_summary(rows),
        "rooms": state.load_rooms(),
        "items": items_out,
        "knowledge": kn.stats(),
        "statuses": ops.STATUSES,
        "frequencies": ["daily", "weekly", "monthly", "occasional", "rare", "unused"],
        "conditions": ["new", "good", "aging", "worn", "scratched", "damaged", "sealed"],
        "item_classes": sorted(
            ({"id": c["id"], "name": c["name"], "category": c.get("category")} for c in kn.item_classes.values()),
            key=lambda x: x["name"],
        ),
    }


def handle_post(path: str, p: dict) -> tuple[int, dict]:
    """Route a dashboard mutation to ops.py. Returns (status_code, body)."""
    with _WRITE_LOCK:
        # Item-existence guard for item-scoped routes (+ swap-attached bookmarks).
        if path in _ITEM_ROUTES or (path == "/api/bookmark" and p.get("item_id")):
            item_id = p.get("item_id")
            if not item_id:
                return 400, {"error": "item_id required"}
            if item_id not in state.load_items():
                return 404, {"error": f"no item {item_id}"}

        if path == "/api/item/add":
            if not p.get("name") or not p.get("item_class"):
                return 400, {"error": "name and item_class are required"}
            try:
                quantity = int(p.get("quantity") or 1)
            except (TypeError, ValueError):
                return 400, {"error": "quantity must be an integer"}
            ops.add_item(
                name=p["name"],
                item_class=p["item_class"],
                room=(p.get("room") or None),
                quantity=quantity,
                condition=p.get("condition", "good"),
                usage={
                    "frequency": p.get("frequency", "occasional"),
                    "food_contact": bool(p.get("food_contact")),
                    "heat": bool(p.get("heat")),
                    "child_contact": bool(p.get("child_contact")),
                },
            )
        elif path == "/api/item/status":
            ops.set_item_status(p["item_id"], p["status"])
        elif path == "/api/swap/choose":
            ops.choose_alternative(p["item_id"], p["alternative_id"])
        elif path == "/api/swap/task/add":
            ops.add_task(p["item_id"], p["text"])
        elif path == "/api/swap/task/toggle":
            ops.toggle_task(p["item_id"], p["task_id"])
        elif path == "/api/swap/complete":
            ops.complete_swap(p["item_id"])
        elif path == "/api/bookmark":
            if not p.get("url"):
                return 400, {"error": "url required"}
            if p.get("item_id"):
                ops.add_swap_bookmark(p["item_id"], p["url"], p.get("title"))
            else:
                ops.add_bookmark(p["url"], p.get("title"))
        elif path == "/api/procurement":
            ops.update_procurement(p["item_id"], status=p.get("status"), cost=p.get("cost"), vendor=p.get("vendor"))
        else:
            return 404, {"error": "unknown route"}
        return 200, state_payload()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body, ctype: str = "application/json") -> None:
        data = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, TEMPLATE.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        elif path == "/api/state":
            self._send(200, state_payload())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid json"})
            return
        try:
            code, body = handle_post(self.path.split("?", 1)[0], payload)
        except KeyError as exc:
            code, body = 400, {"error": f"missing field {exc}"}
        except (ValueError, json.JSONDecodeError) as exc:
            code, body = 500, {"error": str(exc)}
        self._send(code, body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002  keep the console quiet
        return


def make_server(port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port: int = DEFAULT_PORT, open_browser: bool = False) -> None:
    httpd = make_server(port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    print(f"swapit dashboard → {url}   (the agent is the app · Ctrl-C to stop)")
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
