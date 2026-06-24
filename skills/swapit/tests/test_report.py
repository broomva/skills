"""Report generator: HTML safety, empty inventory, and the 'addressed' semantics."""
import knowledge
import report
import state
import swapit


def test_item_name_is_html_escaped(swapit_home):
    swapit.main(["add", "--name", "<script>alert(1)</script>", "--class", "nonstick-cookware", "--room", "kitchen"])
    swapit.main(["report"])
    html = (state.data_root() / "report.html").read_text()
    assert "<script>alert(1)</script>" not in html  # raw payload must not appear
    assert "&lt;script&gt;" in html  # it was escaped instead


def test_empty_inventory_renders(swapit_home):
    assert swapit.main(["report"]) == 0
    html = (state.data_root() / "report.html").read_text()
    assert "No items" in html or "Nothing flagged" in html  # graceful empty state
    assert "Swapit household report" in html  # report still renders end-to-end


def test_keep_counts_as_addressed(swapit_home):
    swapit.main(["add", "--name", "Decided fine", "--class", "plastic-storage-bin", "--room", "garage", "--status", "keep"])
    kn = knowledge.Knowledge()
    rows = swapit._item_rows(kn, state.load_items())
    summary = report.household_summary(rows)
    assert summary["addressed"] == 1
