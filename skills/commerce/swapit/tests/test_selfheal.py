"""Self-heal: clean on seed, detects injected breakage."""
import selfheal
import state


def test_seed_has_no_errors(swapit_home):
    findings = selfheal.run()
    errors = [f for f in findings if f["severity"] == "error"]
    assert errors == [], errors


def test_seed_has_no_warnings(swapit_home):
    findings = selfheal.run()
    warns = [f for f in findings if f["severity"] == "warn"]
    assert warns == [], warns


def test_detects_broken_hazard_edge(swapit_home):
    state.append_jsonl(
        state.knowledge_dir() / "item-classes.jsonl",
        {
            "id": "bogus-class",
            "name": "Bogus",
            "category": "misc",
            "hazards": [{"hazard_id": "does-not-exist", "presence_likelihood": 0.5}],
            "sources": [{"org": "x", "title": "x"}],
        },
    )
    findings = selfheal.run()
    assert any(f["code"] == "broken_edge" for f in findings)
    assert any(f["severity"] == "error" for f in findings)


def test_detects_orphan_swap(swapit_home):
    swaps = state.load_swaps()
    swaps["swp_orphan"] = {"id": "swp_orphan", "item_id": "itm_missing", "checklist": [], "bookmarks": []}
    state.save_swaps(swaps)
    findings = selfheal.run()
    assert any(f["code"] == "orphan_swap" for f in findings)


def test_detects_corrupt_inventory(swapit_home):
    (state.inventory_dir() / "items.json").write_text("{ not valid json", encoding="utf-8")
    findings = selfheal.run()
    assert any(f["code"] == "corrupt_inventory" for f in findings)
    assert any(f["severity"] == "error" for f in findings)


def test_uninitialized_reports_error(monkeypatch, tmp_path):
    monkeypatch.setenv("SWAPIT_HOME", str(tmp_path / "empty"))
    findings = selfheal.run()
    assert findings[0]["code"] == "not_initialized"
