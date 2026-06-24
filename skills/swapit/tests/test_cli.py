"""End-to-end CLI flow: init -> add -> list -> swap -> score -> report -> selfheal."""
import json

import state
import swapit


def test_full_flow(swapit_home, capsys):
    assert swapit.main(["init"]) == 0
    capsys.readouterr()

    assert (
        swapit.main(
            [
                "add", "--name", "Old Teflon pan", "--class", "nonstick-cookware",
                "--room", "kitchen", "--condition", "scratched", "--frequency", "daily",
                "--food-contact", "--heat",
            ]
        )
        == 0
    )
    capsys.readouterr()

    swapit.main(["list", "--json"])
    rows = json.loads(capsys.readouterr().out)
    assert rows and rows[0]["band"] == "high"
    iid = rows[0]["id"]

    assert swapit.main(["swap", iid, "--to", "cast-iron-skillet", "--add-task", "buy skillet", "--status", "sourcing"]) == 0
    capsys.readouterr()

    # the swap + checklist persisted to state (the agent is the app)
    swaps = state.load_swaps()
    swap = next(s for s in swaps.values() if s["item_id"] == iid)
    assert swap["chosen_alternative"] == "cast-iron-skillet"
    assert swap["checklist"][0]["text"] == "buy skillet"
    assert state.load_items()[iid]["status"] == "sourcing"

    swapit.main(["score", "--json"])
    summary = json.loads(capsys.readouterr().out)
    assert summary["total"] == 1
    assert summary["bands"]["high"] == 1

    assert swapit.main(["report"]) == 0
    report = state.data_root() / "report.html"
    assert report.exists()
    html = report.read_text()
    assert "Swapit household report" in html
    assert "Old Teflon pan" in html
    assert "<svg" in html  # inline SVG donut (Category-C HTML)

    assert swapit.main(["selfheal"]) == 0  # exit 0 = no errors


def test_assess_adhoc_class(swapit_home, capsys):
    swapit.main(["assess", "--class", "polycarbonate-bottle", "--frequency", "daily", "--food-contact", "--json"])
    out = json.loads(capsys.readouterr().out)
    hazard_ids = [c["hazard_id"] for c in out["assessment"]["risk"]["contributions"]]
    assert "bpa" in hazard_ids


def test_event_log_appends(swapit_home):
    swapit.main(["add", "--name", "x", "--class", "plastic-storage-bin", "--room", "garage"])
    events = state.read_jsonl(state.events_path())
    assert any(e["type"] == "item.add" for e in events)


def test_corrupt_inventory_exits_gracefully(swapit_home, capsys):
    (state.inventory_dir() / "items.json").write_text("{ broken", encoding="utf-8")
    rc = swapit.main(["list"])
    assert rc == 2  # graceful data-error code, not an uncaught traceback
    assert "selfheal" in capsys.readouterr().err


def test_negative_quantity_rejected(swapit_home):
    import pytest

    with pytest.raises(SystemExit):
        swapit.main(["add", "--name", "x", "--class", "nonstick-cookware", "--room", "kitchen", "--quantity", "-3"])


def test_knowledge_show_respects_type(swapit_home):
    import pytest

    # 'bpa' is a hazard id; asking for it as an alternative must find nothing
    # (the previous fallback chain wrongly returned the hazard regardless of --type)
    with pytest.raises(SystemExit):
        swapit.main(["knowledge", "show", "bpa", "--type", "alternative"])


def test_procure_brief(swapit_home, capsys):
    swapit.main(["add", "--name", "Pan", "--class", "nonstick-cookware", "--room", "kitchen"])
    iid = next(iter(state.load_items()))
    capsys.readouterr()
    assert swapit.main(["procure", iid]) == 0
    out = capsys.readouterr().out
    assert "Procurer handoff brief" in out
    assert "nonstick-cookware" in out
