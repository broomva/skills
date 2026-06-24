"""Live dashboard server — GET renders, POST mutates state through ops and persists."""
import json
import threading
import urllib.error
import urllib.request

import server
import state


def _start():
    httpd = server.make_server(0)  # ephemeral port
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return r.status, r.read()


def _post(port, path, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read())


def _post_err(port, path, body):
    """POST expecting a 4xx; returns (code, parsed_body)."""
    try:
        _post(port, path, body)
        raise AssertionError("expected an error response")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_dashboard_html_served(swapit_home):
    httpd, port = _start()
    try:
        st, body = _get(port, "/")
        assert st == 200
        assert b"Swapit" in body and b"/api/state" in body
    finally:
        httpd.shutdown()


def test_state_endpoint(swapit_home):
    httpd, port = _start()
    try:
        st, raw = _get(port, "/api/state")
        d = json.loads(raw)
        assert d["knowledge"]["hazards"] >= 20
        assert "summary" in d and "items" in d and "statuses" in d
    finally:
        httpd.shutdown()


def test_add_item_persists_and_scores(swapit_home):
    httpd, port = _start()
    try:
        st, data = _post(
            port,
            "/api/item/add",
            {"name": "Teflon pan", "item_class": "nonstick-cookware", "room": "kitchen",
             "condition": "scratched", "frequency": "daily", "food_contact": True, "heat": True},
        )
        assert st == 200
        assert any(i["name"] == "Teflon pan" and i["band"] == "high" for i in data["items"])
        assert any(it["name"] == "Teflon pan" for it in state.load_items().values())
    finally:
        httpd.shutdown()


def test_choose_alternative_and_toggle_task(swapit_home):
    httpd, port = _start()
    try:
        _, data = _post(port, "/api/item/add", {"name": "Pan", "item_class": "nonstick-cookware", "room": "kitchen"})
        iid = data["items"][0]["id"]

        _, data = _post(port, "/api/swap/choose", {"item_id": iid, "alternative_id": "cast-iron-skillet"})
        it = next(i for i in data["items"] if i["id"] == iid)
        assert it["chosen"] == "cast-iron-skillet"
        assert it["status"] == "swap-planned"  # choosing auto-advances from flagged

        _, data = _post(port, "/api/swap/task/add", {"item_id": iid, "text": "buy skillet"})
        tid = next(i for i in data["items"] if i["id"] == iid)["checklist"][0]["id"]
        _, data = _post(port, "/api/swap/task/toggle", {"item_id": iid, "task_id": tid})
        it = next(i for i in data["items"] if i["id"] == iid)
        assert it["checklist"][0]["done"] is True
    finally:
        httpd.shutdown()


def test_status_change_persists(swapit_home):
    httpd, port = _start()
    try:
        _, data = _post(port, "/api/item/add", {"name": "Bin", "item_class": "plastic-storage-bin", "room": "garage"})
        iid = data["items"][0]["id"]
        _post(port, "/api/item/status", {"item_id": iid, "status": "swapped"})
        assert state.load_items()[iid]["status"] == "swapped"
    finally:
        httpd.shutdown()


def test_unknown_route_404(swapit_home):
    httpd, port = _start()
    try:
        try:
            _post(port, "/api/nope", {})
            raise AssertionError("expected 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        httpd.shutdown()


def test_add_missing_fields_400(swapit_home):
    httpd, port = _start()
    try:
        code, _ = _post_err(port, "/api/item/add", {"name": "x"})  # no item_class
        assert code == 400
    finally:
        httpd.shutdown()


def test_bad_quantity_returns_400_not_500(swapit_home):
    httpd, port = _start()
    try:
        code, _ = _post_err(port, "/api/item/add", {"name": "x", "item_class": "nonstick-cookware", "quantity": "abc"})
        assert code == 400  # coerced, not a leaked 500 traceback
    finally:
        httpd.shutdown()


def test_orphan_item_swap_404_no_swap_created(swapit_home):
    httpd, port = _start()
    try:
        code, _ = _post_err(port, "/api/swap/choose", {"item_id": "itm_ghost", "alternative_id": "cast-iron-skillet"})
        assert code == 404
        assert state.load_swaps() == {}  # no orphan swap document created
    finally:
        httpd.shutdown()


def test_malformed_json_400(swapit_home):
    httpd, port = _start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/item/status",
            data=b"{not json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("expected 400")
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        httpd.shutdown()


def test_global_bookmark_and_swap_bookmark_stores_swap_id(swapit_home):
    httpd, port = _start()
    try:
        # global bookmark (no item) is allowed and unattached
        st, _ = _post(port, "/api/bookmark", {"url": "https://example.com", "title": "X"})
        assert st == 200
        assert any(b["attached_to"] is None for b in state.load_bookmarks().values())

        # a swap-attached bookmark records the SWAP id, not the item id
        _, data = _post(port, "/api/item/add", {"name": "Pan", "item_class": "nonstick-cookware", "room": "kitchen"})
        iid = data["items"][0]["id"]
        _post(port, "/api/bookmark", {"item_id": iid, "url": "https://lodge.example", "title": "L"})
        swap = next(s for s in state.load_swaps().values() if s["item_id"] == iid)
        bm = next(b for b in state.load_bookmarks().values() if b["url"] == "https://lodge.example")
        assert bm["attached_to"] == {"type": "swap", "id": swap["id"]}
    finally:
        httpd.shutdown()


def test_complete_swap_and_procurement(swapit_home):
    httpd, port = _start()
    try:
        _, data = _post(port, "/api/item/add", {"name": "Pan", "item_class": "nonstick-cookware", "room": "kitchen"})
        iid = data["items"][0]["id"]
        _, data = _post(port, "/api/procurement", {"item_id": iid, "status": "purchased", "cost": 42.5, "vendor": "Lodge"})
        it = next(i for i in data["items"] if i["id"] == iid)
        assert it["procurement"]["status"] == "purchased" and it["procurement"]["cost"] == 42.5

        _, data = _post(port, "/api/swap/complete", {"item_id": iid})
        it = next(i for i in data["items"] if i["id"] == iid)
        assert it["status"] == "swapped" and it["procurement"]["status"] == "installed"
    finally:
        httpd.shutdown()
