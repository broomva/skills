"""Tests for content-engine-world's world_check.py.

The fictional example world passes; each mutation of a copy proves one check can
go red. A second fixture uses the table form a live grill used (questions and
answers keyed by ask id) so both record forms stay supported.
"""

import shutil
import sys
from pathlib import Path

import pytest
import yaml

SKILL = Path(__file__).resolve().parent.parent / "skills" / "content-engine-world"
sys.path.insert(0, str(SKILL / "scripts"))

import world_check as wc  # noqa: E402

EXAMPLE = SKILL / "examples" / "lantern-market"


@pytest.fixture
def world(tmp_path):
    dst = tmp_path / "world"
    shutil.copytree(EXAMPLE, dst)
    return dst


def codes(world, **kw):
    return sorted({f.code for f in wc.check_world(world, **kw)})


def edit(path, old, new):
    text = path.read_text()
    assert old in text, f"fixture moved: {old!r} not in {path.name}"
    path.write_text(text.replace(old, new, 1))


def test_example_world_passes_complete():
    assert wc.check_world(EXAMPLE, complete=True) == []


def test_cli_exit_codes(world, capsys):
    assert wc.main(["check", str(world), "--complete"]) == 0
    assert "VERDICT: PASS" in capsys.readouterr().out
    edit(world / "characters/wick.md", "likeness: original", "likeness: inspired")
    assert wc.main(["check", str(world)]) == 1
    assert wc.main(["check", str(world / "nope")]) == 2


# --- canon -----------------------------------------------------------------------


def test_w01_duplicate_canon_id(world):
    edit(world / "canon.yaml", "id: prop-last-lamp", "id: cast-keepers")
    assert "W01" in codes(world)


def test_w02_unknown_tier(world):
    edit(world / "canon.yaml", "tier: apocrypha", "tier: legend")
    assert "W02" in codes(world)


def test_numeric_tiers_are_aliases(world):
    edit(world / "canon.yaml", "tier: world\n    status: locked", "tier: 2\n    status: locked")
    assert codes(world) == []


def test_declared_tiers_replace_the_defaults(world):
    data = yaml.safe_load((world / "canon.yaml").read_text())
    data["tiers"] = {"core": "x", "apocrypha": "y"}
    (world / "canon.yaml").write_text(yaml.safe_dump(data))
    assert "W02" in codes(world)  # foundation/world are no longer declared


def test_w03_source_names_an_unknown_decision(world):
    edit(world / "canon.yaml", "source: R1-Q2", "source: R9-Q9")
    assert "W03" in codes(world)


def test_w03_character_cites_unknown_canon(world):
    edit(world / "characters/wick.md", "canon: [cast-keepers]", "canon: [no-such-fact]")
    assert "W03" in codes(world)


def test_w04_locked_on_a_pending_answer(world):
    edit(world / "canon.yaml", "status: draft\n    source: R1-P1", "status: locked\n    source: R1-P1")
    assert "W04" in codes(world)


def test_w04_evidence_is_never_a_default(world):
    edit(world / "canon.yaml", "tier: apocrypha\n    status: draft", "tier: foundation\n    status: locked")
    found = [f for f in wc.check_world(world) if f.code == "W04"]
    assert len(found) == 2  # locked on evidence, and a hard tier on evidence


# --- characters --------------------------------------------------------------------


def test_w05_dna_over_the_cap(world):
    edit(world / "characters/wick.md", "a small dark notch", "a small dark notch " + "very " * 80)
    assert "W05" in codes(world)


def test_w05_cap_is_a_parameter(world):
    assert codes(world) == []
    assert "W05" in codes(world, dna_cap=200)
    edit(world / "canon.yaml", "dna_cap: 600", "dna_cap: 200")
    assert "W05" in codes(world)


def test_w05_dna_opens_with_the_name(world):
    edit(world / "characters/wick.md", "Wick: a rosy", "A rosy")
    assert "W05" in codes(world)


def test_w05_exactly_one_dna_block(world):
    edit(world / "characters/wick.md", "```fixed-dna", "```text")
    assert "W05" in codes(world)


def test_w06_wardrobe_required(world):
    edit(world / "characters/old-shell.md", "```wardrobe default", "```text")
    assert "W06" in codes(world)


def test_w07_likeness_must_be_original(world):
    edit(world / "characters/wick.md", "likeness: original", "likeness: a famous actor")
    assert "W07" in codes(world)


# --- manifest ------------------------------------------------------------------------


def test_w08_kind_must_be_a_library_kind(world):
    edit(world / "asset-manifest.md", "| prop | the-lantern", "| gadget | the-lantern")
    assert "W08" in codes(world)


def test_w09_manifest_row_needs_a_sheet(world):
    (world / "props/the-lantern.md").unlink()
    assert "W09" in codes(world)


def test_w09_sheet_needs_a_manifest_row(world):
    edit(world / "asset-manifest.md", "| character | old-shell | Old Shell | characters/old-shell.md | no | 6 | 0.25 | cast-keepers |\n", "")
    assert "W09" in codes(world)


def test_w10_character_stills_in_skene_lock_range(world):
    edit(world / "asset-manifest.md", "| yes | 8 |", "| yes | 3 |")
    assert "W10" in codes(world)


# --- taste references -------------------------------------------------------------------


def test_w11_taste_reference_in_a_prompt_block(world):
    edit(world / "styles/look.md", "hand-made material textures", "hand-made material textures, in the style of Ilse Varnholt")
    assert "W11" in codes(world)


def test_w11_work_title_counts_too(world):
    edit(world / "locations/the-square.md", "rugs on the sand.", "rugs on the sand, like The Paper Harbour.")
    assert "W11" in codes(world)


def test_w11_reference_in_prose_is_fine(world):
    # The look file names the reference in its bible-only section; that is allowed.
    assert "Ilse Varnholt" in (world / "styles/look.md").read_text()
    assert "W11" not in codes(world)


def test_w11_prompt_files(world):
    (world / "characters/wick-hero.prompt.md").write_text("---\njob: image\n---\nShot: Wick, Slow Caravans mood.\n")
    assert codes(world) == ["W11"]


def test_prompt_files_are_not_sheets(world):
    """P20 r1 #3: a clean prompt file beside a sheet is neither a sheet nor an unlisted asset."""
    (world / "characters/wick-hero.prompt.md").write_text("---\njob: image\n---\nShot: Wick, chest-up.\n")
    (world / "locations/the-square-dawn.prompt.md").write_text("Shot: the square at dawn.\n")
    assert wc.check_world(world, complete=True) == []


def test_w11_external_taste_file(world, tmp_path):
    taste = tmp_path / "private-taste.md"
    taste.write_text("## Taste references\n\n- **Mara Quell** — *Glass Tides* (1999): x\n")
    (world / "owner-taste.md").unlink()
    edit(world / "props/the-lantern.md", "a brass ring", "a Mara Quell brass ring")
    assert "W11" not in codes(world)
    assert "W11" in codes(world, taste=taste)


# --- decisions ---------------------------------------------------------------------------


def test_w12_paraphrased_answer(world):
    edit(world / "decisions.md", '- **Answer:** "Light is the only currency."', "- **Answer:** The owner chose currency.")
    assert "W12" in codes(world)


def test_w12_missing_answer(world):
    edit(world / "decisions.md", '- **Answer:** "Light is the only currency."\n', "")
    assert "W12" in codes(world)


def test_proposals_need_no_answer(world):
    edit(world / "decisions.md", "- **Why it fits:** One lamp that is never sold, T1 and A1.\n- **Answer:** pending\n",
         "- **Why it fits:** One lamp that is never sold, T1 and A1.\n")
    assert codes(world) == []


def test_w13_too_few_seeds(world):
    text = (world / "decisions.md").read_text()
    start, end = text.index("#### R0-S3"), text.index("#### R0-S4")
    (world / "decisions.md").write_text(text[:start] + text[end:])
    assert "W13" in codes(world)


def test_w13_needs_a_stretch_seed(world):
    edit(world / "decisions.md", "- **Stretch:** yes", "- **Stretch:** no")
    edit(world / "decisions.md", "(against the owner's taste)", "")
    assert "W13" in codes(world)


def test_w13_seed_fields(world):
    edit(world / "decisions.md", "- **Hook:** Someone always crosses before it is finished.\n", "")
    assert "W13" in codes(world)


def test_w13_no_round_zero(world):
    text = (world / "decisions.md").read_text()
    start, end = text.index("## Round 0"), text.index("## Round 1")
    (world / "decisions.md").write_text(text[:start] + text[end:])
    assert "W13" in codes(world)


def test_w13_converge_before_diverge(world):
    text = (world / "decisions.md").read_text()
    r0, r1 = text.index("## Round 0"), text.index("## Round 1")
    (world / "decisions.md").write_text(text[:r0] + text[r1:] + "\n" + text[r0:r1])
    assert "W13" in codes(world)


def test_w14_answered_round_needs_method_notes(world):
    edit(world / "decisions.md", "- Borrowing an ingredient seed for a character worked better than a fresh invention.\n", "")
    assert "W14" in codes(world)


def test_w17_duplicate_decision_id(world):
    edit(world / "decisions.md", "#### R1-Q2", "#### R1-Q1")
    assert "W17" in codes(world)


# --- locations, accounts, completeness ------------------------------------------------------


def test_w15_location_needs_a_state(world):
    path = world / "locations/the-square.md"
    path.write_text(path.read_text().replace("```state", "```text"))
    assert "W15" in codes(world)


def test_w16_account_disclosure(world):
    edit(world / "accounts.md", "- **Disclosure:** the platform's AI label on every post, and \"Made with AI\" in the bio.\n", "")
    assert "W16" in codes(world)


def test_w18_complete_needs_the_file_set(world):
    (world / "sound.md").unlink()
    assert "W18" not in codes(world)
    assert "W18" in codes(world, complete=True)


def test_w19_mechanic_evidence_grade(world):
    edit(world / "accounts.md", "| proposal | round 0 |", "| proven | round 0 |")
    assert "W19" in codes(world)


# --- the table form ------------------------------------------------------------------------------

TABLE_DECISIONS = """# A world: decisions

## Round 0: divergent world seeds (asked 2026-02-01)

### Seed 1 · Alpha

- **Premise.** a
- **Hook.** b
- **Why it fits.** T1
- **Why it suits short-form.** c
- **Cost.** low
- **Main risk.** d

### Seed 2 · Beta

- **Premise.** a
- **Hook.** b
- **Why it fits.** T2
- **Why it suits short-form.** c
- **Cost.** low
- **Main risk.** d

### Seed 3 · Gamma

- **Premise.** a
- **Hook.** b
- **Why it fits.** T3
- **Why it suits short-form.** c
- **Cost.** low
- **Main risk.** d

### Seed 4 · Delta (deliberately against the owner's taste)

- **Premise.** a
- **Hook.** b
- **Why it is here.** X1
- **Why it suits short-form.** c
- **Cost.** low
- **Main risk.** d

### Q5 · One world or many

- **Recommendation: one world.**

### Answers

| Ask | Recommended | Answer (verbatim) | Matches? |
|---|---|---|---|
| Q1 `r0-seed-alpha` | build | "Build on it: core." | yes |
| Q2 `r0-seed-beta` | drop | "Drop it." | yes |
| Q3 `r0-seed-gamma` | drop | "Drop it." | yes |
| Q4 `r0-seed-delta` | drop | "Build on it: core." | no |
| Q5 `r0-shape` | one | "One world." | yes |

### Method notes

- The shape question was answered first.

## Round 1: rules (asked 2026-02-02)

| # | Ask | Question | Recommendation | Why |
|---|---|---|---|---|
| 1 | `r1-rule` | The one rule? | **Yes** | T1 |
| 2 | `r1-time` | Real calendar? | **Yes** | T2 |

### Answers

*(waiting; copied verbatim from the ledger when they land)*
"""

TABLE_CANON = """version: 1
facts:
- id: policy-owned
  statement: Owned characters only.
  source: studio-ledger.yaml ip-policy; studio rules file
  status: locked
  tier: 1
- id: seed-alpha
  statement: Alpha is the core.
  source: round 0, r0-seed-alpha (build)
  status: locked
  tier: 1
- id: world-shape
  statement: One world.
  source: round 0, r0-shape (one-world)
  status: locked
  tier: 1
- id: rule-one
  statement: The rule.
  source: round 1, r1-rule
  status: draft
  tier: 1
"""


@pytest.fixture
def table_world(tmp_path):
    w = tmp_path / "table-world"
    w.mkdir()
    (w / "decisions.md").write_text(TABLE_DECISIONS)
    (w / "canon.yaml").write_text(TABLE_CANON)
    return w


def test_table_form_passes(table_world):
    assert wc.check_world(table_world) == []


def test_table_form_items_and_states(table_world):
    items, rounds = wc.parse_decisions((table_world / "decisions.md").read_text())
    by_id = {it.id: it for it in items}
    assert [i for i in by_id if i.startswith("R0-S")] == ["R0-S1", "R0-S2", "R0-S3", "R0-S4"]
    assert by_id["R0-S1"].ask_id == "r0-seed-alpha" and by_id["R0-S1"].answer == "verbatim"
    assert by_id["R0-Q5"].answer == "verbatim"
    assert by_id["R1-Q1"].ask_id == "r1-rule" and by_id["R1-Q1"].answer == "pending"
    assert rounds[1]["waiting"] and rounds[0]["notes"]


def test_table_form_locked_on_a_waiting_ask(table_world):
    edit(table_world / "canon.yaml", "source: round 1, r1-rule\n  status: draft", "source: round 1, r1-rule\n  status: locked")
    assert "W04" in codes(table_world)


def test_table_form_missing_answer_row(table_world):
    edit(table_world / "decisions.md", '| Q3 `r0-seed-gamma` | drop | "Drop it." | yes |\n', "")
    assert "W12" in codes(table_world)


def test_table_form_paraphrased_answer(table_world):
    edit(table_world / "decisions.md", '"Drop it." | yes |\n| Q3', 'owner dropped it | yes |\n| Q3')
    assert "W12" in codes(table_world)


# --- leak ------------------------------------------------------------------------------------------


def test_leak_finds_a_private_term(tmp_path):
    taste = tmp_path / "taste.md"
    taste.write_text("## Taste references\n\n- **Mara Quell** — *Glass Tides* (1999)\n\n## Private terms\n\n- Quell Street\n")
    public = tmp_path / "public"
    public.mkdir()
    (public / "a.md").write_text("Nothing here.\n")
    assert wc.check_leak(public, taste) == []
    (public / "b.md").write_text("We met on Quell Street.\n")
    assert [f.code for f in wc.check_leak(public, taste)] == ["L01"]


def test_the_skill_leaks_nothing_but_its_fictional_example(tmp_path):
    """The skill's files name no taste term of the example owner outside the example."""
    hits = wc.check_leak(SKILL, EXAMPLE / "owner-taste.md")
    assert hits and all(f.path.startswith("examples/lantern-market/") for f in hits)


# --- templates ------------------------------------------------------------------------------------


def test_templates_exist_for_every_output_file():
    templates = {p.name for p in (SKILL / "templates").iterdir()}
    for name in ("owner-taste.md", "decisions.md", "bible.md", "canon.yaml", "character.md", "location.md",
                 "prop.md", "style-lock.md", "sound.md", "timeline.md", "accounts.md", "asset-manifest.md",
                 "evidence.md"):
        assert name in templates, name


def test_canon_template_is_valid_yaml_with_default_tiers():
    data = yaml.safe_load((SKILL / "templates" / "canon.yaml").read_text())
    assert set(data["tiers"]) == set(wc.DEFAULT_TIERS)
    assert data["dna_cap"] == wc.DEFAULT_DNA_CAP


# --- regressions from P20 round 1 (Codex, 2026-10-17) ----------------------------------------------


def test_missing_explicit_taste_file_is_an_error(world, tmp_path, capsys):
    """#1: a --taste path that does not exist must not silently disable W11."""
    edit(world / "props/the-lantern.md", "a brass ring", "an Ilse Varnholt brass ring")
    missing = tmp_path / "missing-private-taste.md"
    with pytest.raises(FileNotFoundError):
        wc.check_world(world, taste=missing)
    assert wc.main(["check", str(world), "--taste", str(missing)]) == 2


def test_unknown_lowercase_ask_id_is_not_external(table_world):
    """#2: a misspelled ask id is unresolved (W03), and cannot lock a fact (W04)."""
    edit(table_world / "canon.yaml", "source: round 0, r0-seed-alpha (build)", "source: round 0, r0-seed-misspelled (build)")
    assert {"W03", "W04"} <= set(codes(table_world))


def test_external_rule_still_counts(table_world):
    assert "W03" not in codes(table_world)  # policy-owned cites another ledger, no local id


def test_external_taste_satisfies_complete(world, tmp_path):
    """#4: the contract allows owner-taste.md in the world or passed as --taste."""
    outside = tmp_path / "private-taste.md"
    shutil.move(world / "owner-taste.md", outside)
    assert "W18" in codes(world, complete=True)
    assert codes(world, complete=True, taste=outside) == []


def test_blank_statement_fails(world):
    """#5: a blank YAML statement is None, not the string 'None'."""
    edit(world / "canon.yaml", 'statement: "A desert night market kept by moths, where every stall sells a kind of light."', "statement:")
    assert "W02" in codes(world)


def test_complete_requires_round_zero(world):
    """#6: an empty decisions file and empty canon cannot pass --complete."""
    (world / "decisions.md").write_text("# decisions\n\n## Round 0: seeds\n")
    (world / "canon.yaml").write_text("version: 1\nfacts: []\n")
    found = codes(world, complete=True)
    assert "W13" in found and "W18" in found


def test_unnamed_state_fails(world):
    """#7: a state block needs a name, since it becomes states[<name>]."""
    path = world / "locations/the-square.md"
    path.write_text(path.read_text().replace("```state open", "```state").replace("```state sandstorm", "```state"))
    assert "W15" in codes(world)


def test_duplicate_state_names_fail(world):
    edit(world / "locations/the-square.md", "```state sandstorm", "```state open")
    assert "W15" in codes(world)


def test_wardrobe_needs_a_default(world):
    edit(world / "characters/wick.md", "```wardrobe default", "```wardrobe festival")
    assert "W06" in codes(world)


def test_manifest_sheet_column_is_validated(world):
    """#8: the declared sheet path must be the one the kind requires."""
    edit(world / "asset-manifest.md", "| characters/wick.md |", "| characters/missing.md |")
    assert "W09" in codes(world)


def test_format_mechanic_must_be_graded(world):
    """#9: removing the Mechanics table cannot hide an ungraded mechanic a format uses."""
    text = (world / "accounts.md").read_text()
    start, end = text.index("## Mechanics"), text.index("## Lantern Market (working handle)")
    (world / "accounts.md").write_text(text[:start] + text[end:])
    assert "W19" in codes(world)
