"""Tests for the disambiguate deterministic core.

The word-count cases are the worked examples published in ASD-STE100 Issue 9
section 8, where the standard states the expected count for each sentence.
Using them as fixtures means the algorithm is checked against the authority
rather than against my reading of it.

Every detector asserts both polarities: the pattern fires on the defect and
stays silent on the clean rewrite. A suite that only proves firing is
self-certifying — it passes just as happily when the detector matches
everything. An adversarial review found this claim was false for three
detectors (A1-pronoun-antecedent, A3, D3-semicolon); A3 was deleted and the
other two are covered below.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from disambiguate import (  # noqa: E402
    CEILING,
    check_document,
    check_sentence,
    count_ste_words,
    detect_mode,
    main,
    split_sentences,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "disambiguate.py"


def codes(findings) -> set[str]:
    return {f.code for f in findings}


def check(sent, mode="procedural", glossary=()):
    return check_sentence(1, sent, mode, glossary)


# --------------------------------------------------------------------------
# Word count — oracle cases from the standard, section 8
# --------------------------------------------------------------------------

ORACLE = [
    ("Install the three auxiliary screws (2) in the flange of the motor assembly (9).", 14),
    ("Make sure that the EMER pushbutton switch is released (the EMER legend is off).", 10),
    ("Remove the safety pin (10).", 5),
    ("Do steps 13 thru 16 a minimum of three times.", 10),
    ("The spar box has twenty-one ribs.", 6),
    ("Make sure that the temperature in the room is 10 °C.", 10),
    ("Make sure that the temperature in the room is 10 degrees Celsius.", 10),
    ("The unit weighs 20 kg.", 4),
    ("The unit weighs 20 kilograms.", 4),
    ("The resistance must be 10 ohms.", 5),
    ("For remote access, use the VPN.", 6),
    ("During this safety check, obey NASA protocols.", 7),
    ("Tag circuit breaker 36L7.", 4),
    ("Release the SHORT-CIRCUIT TEST switch.", 4),
    ("Clean the surface with a soap-and-water solution.", 7),
    ("Use the trial-and-error method.", 4),
    ("Put preservation oil into the unit through the vent hole.", 10),
    ("Continue until the oil level is approximately 6 mm (0.24 in) below the surface "
     "of the flange cover.", 16),
    ("The crew rest compartment.", 4),
    ("The cabin sub-compartment", 3),
    ("Touch the “Service Overview” arrow to select the function page.", 9),
    ("The maintenance team does a test of this system each day at 10 a.m.", 13),
    ("Examine the No. 1 bearing installation.", 5),
    ("CAUTION: WHEN YOU REMOVE THE SHROUD (26), BE CAREFUL NOT TO CAUSE DAMAGE TO "
     "THE SURFACE OF THE FLANGE ASSEMBLY (22).", 20),
    ("Installation of a Business Class (B/C) Seat", 7),
    ("Hardware and Software Configuration Check of the In-Flight Entertainment (IFE) System", 11),
    ("To extinguish a possible fire, portable fire extinguishers are installed in these areas:", 13),
]


@pytest.mark.parametrize("sentence,expected", ORACLE)
def test_word_count_matches_published_value(sentence, expected):
    got, _ = count_ste_words(sentence)
    assert got == expected, f"{sentence!r}: expected {expected}, got {got}"


def test_parenthetical_counts_as_one_word():
    plain, _ = count_ste_words("Remove the safety pin.")
    with_ref, _ = count_ste_words("Remove the safety pin (10).")
    assert with_ref == plain + 1


def test_number_and_unit_bind_into_one_word():
    assert count_ste_words("The unit weighs 20 kg.")[0] == 4
    assert count_ste_words("The unit weighs twenty kilograms and more.")[0] == 6


def test_hyphenated_compound_is_one_word():
    assert count_ste_words("Use the trial-and-error method.")[0] == 4
    assert count_ste_words("Use the trial and error method.")[0] == 6


def test_uppercase_run_is_quoted_by_typography():
    assert count_ste_words("Release the SHORT-CIRCUIT TEST switch.")[0] == 4


def test_predominantly_uppercase_sentence_is_not_collapsed():
    """A safety instruction is conventionally all caps. Case then carries no
    quoting signal, so folding it would report a 20-word caution as one word."""
    n, _ = count_ste_words(
        "CAUTION: WHEN YOU REMOVE THE SHROUD (26), BE CAREFUL NOT TO CAUSE "
        "DAMAGE TO THE SURFACE OF THE FLANGE ASSEMBLY (22)."
    )
    assert n == 20


def test_proper_noun_limit_is_surfaced_not_guessed():
    """Multi-word proper nouns need domain knowledge. The published count for
    this sentence is 8; the mechanical count is higher. The algorithm must not
    pretend — it must report the gap and name the remedy."""
    n, advisories = count_ste_words(
        "The first president of the United States of America was George Washington."
    )
    assert n == 12, "pin the mechanical count; 'greater than 8' passes for 900"
    assert advisories, "the shortfall must be surfaced as an advisory"
    assert any("glossary" in a.lower() for a in advisories)


def test_glossary_closes_the_proper_noun_gap():
    n, _ = count_ste_words(
        "The first president of the United States of America was George Washington.",
        glossary=["United States of America", "George Washington"],
    )
    assert n == 8


def test_step_marker_is_not_counted():
    assert count_ste_words("1. Remove the safety pin (10).")[0] == 5
    assert count_ste_words("A. Remove the safety pin (10).")[0] == 5


# --------------------------------------------------------------------------
# Mode detection
# --------------------------------------------------------------------------


def test_mode_detection_procedural():
    text = "Remove the cover.\nInstall the seal.\nTorque the bolts to 4 Nm."
    assert detect_mode(text) == "procedural"


def test_mode_detection_descriptive():
    text = ("The valve controls the flow of fuel. The pump supplies pressure to "
            "the manifold. The sensor reports the temperature.")
    assert detect_mode(text) == "descriptive"


def test_condition_first_instruction_still_reads_as_procedural():
    text = ("When the light comes on, set the switch to NORMAL.\n"
            "If the pressure falls, close the valve.\n"
            "After the test ends, remove the probe.")
    assert detect_mode(text) == "procedural"


def test_ceilings_differ_by_mode():
    assert CEILING["procedural"] == 20
    assert CEILING["descriptive"] == 25


# --------------------------------------------------------------------------
# A — Which thing?
# --------------------------------------------------------------------------


def test_bare_demonstrative_fires():
    f = check("Make sure that the cover is not locked. This can cause damage to the probe.")
    assert "A1-bare-demonstrative" in codes(f)


def test_bare_demonstrative_silent_when_head_noun_present():
    f = check("If the cover is locked, this condition can cause damage to the probe.")
    assert "A1-bare-demonstrative" not in codes(f)


def test_noun_stack_fires_at_four():
    f = check("Calibrate the runway light connection resistance calibration unit.")
    assert "A2-noun-stack" in codes(f)


def test_noun_stack_silent_at_three():
    f = check("Calibrate the actuator operating rod.")
    assert "A2-noun-stack" not in codes(f)


def test_noun_stack_fix_names_the_head_noun():
    f = [x for x in check("Remove the engine transmission housing attachment bolts.")
         if x.code == "A2-noun-stack"]
    assert f, "expected a noun-stack finding"
    assert "of the" in f[0].fix


def test_synonym_drift_fires_across_document():
    text = ("Put the housing on the main body.\n"
            "Install the two bolts in the body.\n"
            "Attach the transducer to the body assembly.\n")
    assert "A4-synonym-drift" in codes(check_document(text, "procedural", ()))


def test_synonym_drift_silent_when_one_name_is_used():
    text = ("Put the housing on the body assembly.\n"
            "Install the two bolts in the body assembly.\n"
            "Attach the transducer to the body assembly.\n")
    assert "A4-synonym-drift" not in codes(check_document(text, "procedural", ()))


# --------------------------------------------------------------------------
# B — Who must, and must they?
# --------------------------------------------------------------------------


def test_agentless_passive_fires_and_is_warn():
    f = [x for x in check("Oil and grease are removed with a degreasing agent.")
         if x.code.startswith("B1-passive")]
    assert f
    assert f[0].code == "B1-passive-agentless"
    assert f[0].severity == "warn"


def test_passive_with_named_agent_is_downgraded():
    f = [x for x in check("The report is reviewed by the safety officer.")
         if x.code.startswith("B1-passive")]
    assert f
    assert f[0].severity == "info"


def test_active_command_is_silent():
    f = check("Remove oil and grease with a degreasing agent.")
    assert not any(c.startswith("B1-passive") for c in codes(f))


def test_non_imperative_instruction_fires():
    assert "B2-non-imperative-instruction" in codes(check("The test can be continued."))


def test_imperative_rewrite_is_silent():
    assert "B2-non-imperative-instruction" not in codes(check("Continue the test."))


def test_weak_modal_fires():
    assert "B3-weak-modal" in codes(check("The system should retry the request."))


def test_strong_modal_is_silent():
    assert "B3-weak-modal" not in codes(check("The system must retry the request."))


def test_dropped_subject_fires():
    assert "B4-dropped-subject" in codes(check("If installed, remove the shims."))


def test_restored_subject_is_silent():
    assert "B4-dropped-subject" not in codes(check("If the shims are installed, remove them."))


# --------------------------------------------------------------------------
# C — How do I know it is done?
# --------------------------------------------------------------------------


def test_abstract_assertion_fires():
    assert "C1-abstract-assertion" in codes(check("No leaks are permitted."))


def test_actionable_check_is_silent():
    assert "C1-abstract-assertion" not in codes(check("Make sure that there are no leaks."))


def test_unquantified_delta_fires():
    assert "C2-unquantified-delta" in codes(check("The new index makes the query faster."))


def test_quantified_delta_is_silent():
    f = check("The new index reduces p95 query time from 800 ms to 200 ms.")
    assert "C2-unquantified-delta" not in codes(f)


def test_vague_predicate_fires_on_word_and_on_phrase():
    assert "C3-vague-predicate" in codes(check("The system handles errors gracefully."))
    assert "C3-vague-predicate" in codes(check("Retry the request as needed."))


def test_vague_predicate_silent_when_observable_is_named():
    f = check("On a 5xx response, retry the request three times, then write one error record.")
    assert "C3-vague-predicate" not in codes(f)


def test_missing_consequence_fires_on_a_warning():
    f = check("WARNING: DO NOT SWALLOW THE SOLVENT.")
    assert "C4-missing-consequence" in codes(f)


def test_stated_consequence_is_silent():
    f = check("WARNING: DO NOT SWALLOW THE SOLVENT. SOLVENTS ARE POISONOUS AND "
              "CAN CAUSE INJURY OR DEATH.")
    assert "C4-missing-consequence" not in codes(f)


# --------------------------------------------------------------------------
# D — Can I hold this?
# --------------------------------------------------------------------------


def test_over_length_fires_past_the_procedural_ceiling():
    long = ("Put preservation oil into the unit through the vent hole until the oil "
            "level is approximately 6 mm below the surface of the flange cover.")
    assert "D1-over-length" in codes(check(long, mode="procedural"))


def test_same_sentence_passes_under_the_descriptive_ceiling():
    """The ceiling is a property of the mode, not of the prose. A 22-word
    sentence is a defect in a procedure and acceptable in a description."""
    s = ("The pump supplies fuel to the manifold through the vent hole until the "
         "level is approximately six units below the flange cover surface.")
    n, _ = count_ste_words(s)
    assert CEILING["procedural"] < n <= CEILING["descriptive"]
    assert "D1-over-length" in codes(check(s, mode="procedural"))
    assert "D1-over-length" not in codes(check(s, mode="descriptive"))


def test_semicolon_is_a_block():
    f = [x for x in check("Close the isolating valves; tag the valves.") if x.code == "D3-semicolon"]
    assert f
    assert f[0].severity == "block"


def test_compound_obligation_fires():
    f = check("Set the TEST switch to the middle position and release the SHORT-CIRCUIT TEST switch.")
    assert "D2-compound-obligation" in codes(f)


def test_split_steps_are_silent():
    assert "D2-compound-obligation" not in codes(check("Set the TEST switch to the middle position."))


def test_paragraph_overrun_fires_past_six_sentences():
    para = " ".join(f"The valve controls flow number {i}." for i in range(1, 9))
    assert "D4-paragraph-overrun" in codes(check_document(para, "descriptive", ()))


def test_paragraph_of_six_is_silent():
    para = " ".join(f"The valve controls flow number {i}." for i in range(1, 7))
    assert "D4-paragraph-overrun" not in codes(check_document(para, "descriptive", ()))


def test_mode_mixing_in_a_list_fires():
    text = ("- Remove the cover\n"
            "- The seal is made of rubber\n"
            "- Install the new seal\n")
    assert "D5-mode-mixing" in codes(check_document(text, "procedural", ()))


def test_uniform_list_is_silent():
    text = ("- Remove the cover\n"
            "- Remove the seal\n"
            "- Install the new seal\n")
    assert "D5-mode-mixing" not in codes(check_document(text, "procedural", ()))


# --------------------------------------------------------------------------
# E — Can I parse it at all?
# --------------------------------------------------------------------------


def test_ing_form_fires_after_a_be_verb():
    assert "E1-ing-form" in codes(check("The pump is supplying fuel to the manifold."))


def test_finite_verb_is_silent():
    assert "E1-ing-form" not in codes(check("The pump supplies fuel to the manifold."))


def test_dropped_that_fires():
    assert "E2-dropped-that" in codes(check("Make sure the valve is open."))


def test_present_that_is_silent():
    assert "E2-dropped-that" not in codes(check("Make sure that the valve is open."))


def test_condition_after_action_fires():
    assert "E3-condition-after-action" in codes(check("Set the switch to NORMAL when the light comes on."))


def test_condition_first_is_silent():
    assert "E3-condition-after-action" not in codes(check("When the light comes on, set the switch to NORMAL."))


def test_contraction_fires():
    assert "E4-contraction" in codes(check("If your hands are wet, don't touch the adapter."))


def test_full_words_are_silent():
    assert "E4-contraction" not in codes(check("If your hands are wet, do not touch the adapter."))


def test_latin_abbreviation_fires():
    assert "E5-latin-abbreviation" in codes(check("Discard the standard parts (e.g. washers)."))


def test_english_words_are_silent():
    assert "E5-latin-abbreviation" not in codes(check("Discard the standard parts (for example, washers)."))


def test_opaque_phrasal_verb_fires():
    assert "E6-opaque-phrasal-verb" in codes(check("Carry out the inspection of the seal."))


def test_single_verb_is_silent():
    assert "E6-opaque-phrasal-verb" not in codes(check("Do the inspection of the seal."))


def test_slash_conjunction_fires():
    assert "E7-slash-conjunction" in codes(check("Update the config and/or restart the service."))


def test_file_path_is_not_a_slash_conjunction():
    assert "E7-slash-conjunction" not in codes(check("Open the file at src/main.py and read it."))


# --------------------------------------------------------------------------
# Sentence splitting
# --------------------------------------------------------------------------


def test_colon_ends_a_sentence():
    parts = split_sentences("The report must include: a form, a drawing.")
    assert len(parts) == 2


def test_abbreviation_period_does_not_split():
    parts = split_sentences("Examine the No. 1 bearing installation.")
    assert len(parts) == 1


# --------------------------------------------------------------------------
# Substitution discipline — the invariant that makes findings actionable
# --------------------------------------------------------------------------


SAMPLE = """
The system should handle errors gracefully.
Oil and grease are to be removed with a degreasing agent.
Set the switch to NORMAL when the light comes on.
Close the isolating valves; tag the valves.
Calibrate the runway light connection resistance calibration unit.
"""


def test_every_finding_carries_a_fix():
    """A prohibition without a substitute is not actionable. The source standard
    never lists a disallowed word without an approved alternative; the checker
    inherits that constraint."""
    findings = check_document(SAMPLE, "procedural", ())
    assert findings
    for f in findings:
        assert f.fix.strip(), f"{f.code} reports a defect with no rewrite"
        assert f.why.strip(), f"{f.code} reports a defect with no reason"


def test_every_finding_declares_a_family_and_severity():
    findings = check_document(SAMPLE, "procedural", ())
    assert findings, "guard: without this the loop below passes on an empty list"
    for f in findings:
        assert f.family in {"A", "B", "C", "D", "E"}
        assert f.severity in {"block", "warn", "info"}


def test_clean_requirement_produces_no_warn_or_block():
    clean = ("When the response status is 5xx, retry the request three times.\n"
             "Make sure that the retry interval is 200 ms.\n"
             "Write one error record for each failed retry.\n")
    findings = check_document(clean, "procedural", ())
    loud = [f for f in findings if f.severity in {"warn", "block"}]
    assert not loud, f"clean text produced {[f.code for f in loud]}"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_json_output_is_wellformed(tmp_path):
    p = tmp_path / "req.md"
    p.write_text(SAMPLE)
    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(p), "--json"],
        capture_output=True, text=True,
    )
    payload = json.loads(out.stdout)
    assert payload["summary"]["total"] > 0
    assert payload["mode"] in {"procedural", "descriptive"}
    assert all({"code", "why", "fix"} <= set(f) for f in payload["findings"])


def test_cli_exit_code_signals_a_block(tmp_path):
    p = tmp_path / "req.md"
    p.write_text("Close the isolating valves; tag the valves.\n")
    rc = subprocess.run([sys.executable, str(SCRIPT), str(p)], capture_output=True).returncode
    assert rc == 1


def test_cli_exit_zero_on_clean_text(tmp_path):
    p = tmp_path / "req.md"
    p.write_text("Remove the cover.\nInstall the new seal.\n")
    rc = subprocess.run([sys.executable, str(SCRIPT), str(p)], capture_output=True).returncode
    assert rc == 0


def test_cli_count_mode():
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--count", "Remove the safety pin (10)."],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == "5"


def test_strict_promotes_warn_to_failure(tmp_path):
    p = tmp_path / "req.md"
    p.write_text("The system should handle errors gracefully.\n")
    lenient = subprocess.run([sys.executable, str(SCRIPT), str(p)], capture_output=True).returncode
    strict = subprocess.run([sys.executable, str(SCRIPT), str(p), "--strict"], capture_output=True).returncode
    assert lenient == 0
    assert strict == 1


# --------------------------------------------------------------------------
# Regressions caught by running the checker on real requirement prose
# --------------------------------------------------------------------------


def test_short_command_with_trailing_condition_still_fires():
    """A character-ratio threshold put this sentence one character under the
    bar and let a genuine condition-after-action defect through."""
    f = check("Set the retry flag to true when the upstream provider is unavailable.")
    assert "E3-condition-after-action" in codes(f)


def test_condition_word_as_verb_complement_is_silent():
    """"Record when the alarm fires" states what to record, not a condition on
    the action. Three words must precede the marker before it counts."""
    assert "E3-condition-after-action" not in codes(check("Record when the alarm fires."))
    assert "E3-condition-after-action" not in codes(check("Check when the light comes on."))


def test_verb_inflection_ends_a_noun_stack():
    """"The new caching layer makes the login flow faster" is not a five-word
    noun stack headed by "makes"."""
    assert "A2-noun-stack" not in codes(check("The new caching layer makes the login flow faster.",
                                              mode="descriptive"))


def test_command_checks_apply_inside_a_descriptive_document():
    """Document mode sets the length ceiling. Whether a sentence is a command is
    a property of that sentence, so an instruction buried in a description is
    still held to the instruction rules."""
    text = ("The valve controls the flow of fuel.\n"
            "The pump supplies pressure to the manifold.\n"
            "Set the switch to NORMAL when the light comes on.\n"
            "The sensor reports the temperature.\n")
    assert detect_mode(text) == "descriptive"
    assert "E3-condition-after-action" in codes(check_document(text, "descriptive", ()))


def test_noun_stack_requires_a_determiner_anchor():
    """A stack is a noun phrase, so it follows a determiner. Without that anchor
    the run-of-content-words heuristic matched ordinary clauses — running the
    checker on its own documentation reported 23 stacks, 22 of them clauses."""
    for clause in [
        "Two readers ship two systems and both claim conformance.",
        "Native English engineers misread them badly.",
        "It joins two independent clauses together.",
    ]:
        assert "A2-noun-stack" not in codes(check(clause, mode="descriptive")), clause


def test_noun_stack_still_fires_behind_a_determiner():
    for stack in [
        "Update the user session token refresh interval configuration value.",
        "Remove the engine transmission housing attachment bolts.",
    ]:
        assert "A2-noun-stack" in codes(check(stack)), stack


def test_comma_ends_a_noun_stack():
    """Two short noun phrases separated by a comma are not one long stack."""
    f = check("Remove the cover, the seal, the gasket, and the bolt.")
    assert "A2-noun-stack" not in codes(f)


# --------------------------------------------------------------------------
# Regressions from the adversarial review (P20)
#
# Each of these reproduces a defect the review found by running the checker on
# input I had not thought of. Ordered by the severity it was reported at.
# --------------------------------------------------------------------------


def test_unclosed_fence_does_not_blank_the_rest_of_the_document():
    """BLOCKER. A running in_fence toggle let one stray ``` line swallow every
    following line, so the checker reported 'no ambiguity found' and exit 0 on
    text it had stopped reading. A linter that reports clean on unchecked input
    is worse than no linter."""
    doc = (
        "Intro line.\n\nExample of a fence marker:\n\n```\n\n"
        "Close the isolating valves; tag the valves.\n"
    )
    findings = check_document(doc, "procedural", ())
    assert "D3-semicolon" in codes(findings), "content after an unpaired fence must stay checked"


def test_closed_fence_is_still_skipped():
    doc = "Intro line.\n\n```\nClose the valves; tag them.\n```\n\nThe end.\n"
    assert "D3-semicolon" not in codes(check_document(doc, "procedural", ()))


def test_longer_fence_is_not_closed_by_a_shorter_one():
    """A three-backtick line inside a four-backtick block does not close it."""
    doc = "````\nsome text\n```\nClose the valves; tag them.\n````\n"
    assert "D3-semicolon" not in codes(check_document(doc, "procedural", ()))


def test_glossary_term_does_not_split_ordinary_words():
    """BLOCKER. An unbounded substring match made --glossary INCREASE the count,
    the opposite of what it documents. 'IT' shattered 'critical' and 'item'."""
    plain = count_ste_words("The unit is a critical item.")[0]
    assert count_ste_words("The unit is a critical item.", glossary=["IT"])[0] == plain
    assert count_ste_words("The category of logs is growing.", glossary=["Go"])[0] == \
        count_ste_words("The category of logs is growing.")[0]


def test_nested_parentheses_collapse_to_one_word():
    assert count_ste_words("Install the screw (see the note (a) below) in the flange.")[0] == 7


def test_punctuation_only_tokens_are_not_words():
    assert count_ste_words("The service retries — three times — before it fails.")[0] == 8
    assert count_ste_words("The build passed ✅ and the deploy finished 🚀.")[0] == 7


def test_numeric_range_binds_its_unit():
    assert count_ste_words("The latency is 10-20 ms.")[0] == 4


def test_comparative_does_not_fire_on_ordinary_nouns():
    """MAJOR. 'optimizer', 'the lower bound', and 'one or more errors' were all
    reported as unquantified deltas."""
    for clean in [
        "The query optimizer chooses an index for each join.",
        "The lower bound of the range is inclusive.",
        "Set the log level to a higher verbosity in the staging environment.",
        "The build fails when the linter reports one or more errors.",
        "The release includes a performance enhancement for the search page.",
    ]:
        assert "C2-unquantified-delta" not in codes(check(clean, mode="descriptive")), clean


def test_comparative_still_fires_on_a_real_unquantified_claim():
    for defect in [
        "The new caching layer makes the login flow faster.",
        "This change improves throughput.",
    ]:
        assert "C2-unquantified-delta" in codes(check(defect, mode="descriptive")), defect


def test_spelled_out_quantity_counts_as_quantification():
    assert "C2-unquantified-delta" not in codes(
        check("The index makes the query three times faster.", mode="descriptive"))


def test_attachment_ambiguity_is_not_auto_detected():
    """MAJOR. The surface rule fired on every imperative containing 'with',
    including a sentence this suite uses as a clean fixture. Deciding between
    the instrument, the accompaniment, and a property needs a parse, so it moved
    to the catalog as a judgment item."""
    for clean in [
        "Clean the surface with a soap-and-water solution.",
        "Sign the request with the HMAC key.",
        "Start the server with the --verbose flag.",
    ]:
        assert not any(c.startswith("A3") for c in codes(check(clean))), clean


def test_etc_path_segment_is_not_a_vague_predicate():
    """MAJOR. '\\betc\\b' matched the /etc/ path segment."""
    assert "C3-vague-predicate" not in codes(check("The config file lives at /etc/app/config.yaml."))
    assert "C3-vague-predicate" not in codes(check("Edit /etc/hosts."))


def test_latin_etc_still_fires_with_its_period():
    assert "E5-latin-abbreviation" in codes(check("Discard the washers, bolts, etc."))


def test_slash_does_not_fire_on_routes_mime_types_or_uris():
    """MAJOR. A general \\w+/\\w+ rule flagged every path, route and MIME type."""
    for clean in [
        "GET /v1/users returns a JSON array of user objects.",
        "Call POST /api/v2/sessions with the refresh token.",
        "The response Content-Type is application/json.",
        "Store the artifact in s3://builds/nightly.",
        "The config file lives at /etc/app/config.yaml.",
    ]:
        assert "E7-slash-conjunction" not in codes(check(clean, mode="descriptive")), clean


def test_slash_still_fires_on_a_real_ambiguous_conjunction():
    assert "E7-slash-conjunction" in codes(check("Update the config and/or restart the service."))


def test_note_label_does_not_demand_a_consequence():
    """MINOR. Only a warning or a caution carries risk. A note is
    informational by definition (rule 5.5)."""
    assert "C4-missing-consequence" not in codes(check("Note: the migration takes about five minutes."))


def test_warning_label_still_demands_a_consequence():
    assert "C4-missing-consequence" in codes(check("WARNING: DO NOT SWALLOW THE SOLVENT."))


def test_y_verb_inflection_ends_a_noun_stack():
    """MAJOR. VERB_FORMS was built by appending s/es/ed/ing, which never
    generates y->ies, so 'retries' was absorbed into a stack."""
    assert "A2-noun-stack" not in codes(
        check("The webhook retries three times with exponential backoff.", mode="descriptive"))


def test_out_of_vocabulary_imperatives_are_recognized():
    """MAJOR. A closed verb list gated three detectors, so every verb missing
    from it silently switched them off."""
    from disambiguate import is_imperative
    for cmd in [
        "Notify the team and page the on-call.",
        "Provision the cluster with terraform.",
        "Escalate to the on-call when the alert fires.",
    ]:
        assert is_imperative(cmd), cmd
    assert "E3-condition-after-action" in codes(check("Escalate to the on-call when the alert fires."))


def test_statements_are_not_read_as_commands():
    from disambiguate import is_imperative
    for stmt in [
        "Sessions are validated on each request.",
        "Latency should stay under 200 ms.",
        "Configuration changes require approval.",
        "The system retries the request.",
        "Users must authenticate before they read a record.",
    ]:
        assert not is_imperative(stmt), stmt


def test_comma_chained_commands_are_a_compound_obligation():
    assert "D2-compound-obligation" in codes(
        check("Remove the cover, install the seal, torque the bolts."))


def test_single_command_with_a_comma_is_not_compound():
    assert "D2-compound-obligation" not in codes(
        check("When the light comes on, set the switch to NORMAL."))


def test_html_block_is_not_prose():
    """MINOR. A CSS declaration became a block-severity semicolon finding."""
    doc = 'Intro.\n\n<div style="color: red; padding: 4px">\n'
    assert "D3-semicolon" not in codes(check_document(doc, "descriptive", ()))


def test_frontmatter_after_a_blank_line_is_still_stripped():
    doc = '\n---\ntitle: the thing; the other thing\n---\n\nThe valve controls flow.\n'
    assert "D3-semicolon" not in codes(check_document(doc, "descriptive", ()))


def test_table_row_without_a_leading_pipe_is_not_prose():
    doc = "status | should be set appropriately | yes\n"
    assert not codes(check_document(doc, "descriptive", ()))


def test_pronoun_antecedent_asserts_both_polarities():
    """The review found this detector had no test at all, in either direction."""
    assert "A1-pronoun-antecedent" in codes(
        check("If you engage the pins with the seats, they can become damaged.",
              mode="descriptive"))
    assert "A1-pronoun-antecedent" not in codes(
        check("Remove the cover.", mode="procedural"))


def test_semicolon_asserts_both_polarities():
    assert "D3-semicolon" in codes(check("Close the valves; tag them."))
    assert "D3-semicolon" not in codes(check("Close the valves. Tag them."))


def test_leading_imperative_is_not_a_vague_predicate():
    """'Clean the surface' is precise. 'clean code' is not. Only the adjective
    reading is the defect, and the verb reading was being flagged."""
    assert "C3-vague-predicate" not in codes(check("Clean the surface with a soap-and-water solution."))
    assert "C3-vague-predicate" in codes(check("The module must have clean interfaces.", mode="descriptive"))


# --------------------------------------------------------------------------
# Round-2 adversarial review (P20)
#
# Round 1's fixes were fitted to the example sentences the reviewer named
# rather than to the classes behind them, so each generalized one step and
# broke. These tests assert the CLASS. Every one was mutation-proven: the
# mechanism it covers was reverted and the test observed to fail.
# --------------------------------------------------------------------------


def test_unbalanced_fence_strips_nothing_and_says_so():
    """BLOCKER, twice. A running toggle blanked the tail. Greedy pairing then
    paired the stray opener with the NEXT REAL BLOCK's opener, blanking the
    prose and checking the code — the same silent skip, one shape further out.
    A heuristic feeding a CI gate must fail open: strip nothing, and report."""
    variants = {
        "stray then a real block": "Intro.\n\n```\n\nClose the valves; tag them.\n\n```\nprint('x')\n```\n",
        "stray only": "Intro.\n\n```\n\nClose the valves; tag them.\n",
        "two strays": "```\nClose the valves; tag them.\n```\n```\nmore prose; here\n",
        "fence after frontmatter": "---\ntitle: x\n---\n```\nClose the valves; tag them.\n",
    }
    for name, doc in variants.items():
        found = codes(check_document(doc, "procedural", ()))
        assert "D3-semicolon" in found, f"{name}: prose was silently skipped"
        assert "D0-unbalanced-fence" in found, f"{name}: imbalance not reported"


def test_balanced_fence_is_still_stripped_and_reports_nothing():
    doc = "Intro.\n\n```\nClose the valves; tag them.\n```\n\nThe end.\n"
    found = codes(check_document(doc, "procedural", ()))
    assert "D3-semicolon" not in found
    assert "D0-unbalanced-fence" not in found


OPS_STACKS = [
    "Remove the engine mount attachment bolts.",
    "Check the primary database backup retention policy.",
    "Replace the hydraulic pump seal pin retainer.",
    "Audit the production database snapshot restore procedure.",
    "Update the user session token refresh interval value.",
    "Rotate the primary cluster access key material.",
    "Tune the message queue consumer batch size.",
    "Verify the disk volume mount point permission.",
]


def test_noun_homograph_verbs_do_not_blind_the_stack_detector():
    """MAJOR. Adding ops verbs to IMPERATIVE_HINT fed them into VERB_FORMS,
    which terminates a stack run, so every stack containing 'mount', 'backup',
    'snapshot', 'pin', 'access', 'queue' went silent. Detection fell 8/12 to
    1/12 on an ops corpus while all 131 tests stayed green. The two roles are
    now separate sets."""
    detected = sum("A2-noun-stack" in codes(check(s)) for s in OPS_STACKS)
    assert detected >= 7, f"only {detected}/8 stacks detected — homographs are blinding it again"


DESCRIPTIVE_NOUN_INITIAL = [
    "Migration to the new schema takes five minutes.",
    "Replication from the primary is asynchronous.",
    "Encryption at rest is enabled.",
    "Deployment to production needs approval.",
    "Integration with the vendor is complete.",
    "Growth in the index size is linear.",
    "Visibility into the queue depth is limited.",
    "Compliance with the policy is audited.",
    "Access to the API requires a token.",
    "Support for TLS 1.2 ends in June.",
    "Traffic in the region is mirrored.",
    "Permission for the operation is denied.",
]


def test_noun_plus_preposition_is_not_a_command():
    """MAJOR. The fallback's preposition branch read a third of ordinary
    descriptive prose as commands, flipping whole documents to the procedural
    20-word ceiling and switching on B2. Genuine commands take a DETERMINER as
    word two; noun-initial statements take a preposition. The blocklist that
    had been fitted to five specific counterexamples went away with the branch.
    """
    from disambiguate import is_imperative
    misread = [s for s in DESCRIPTIVE_NOUN_INITIAL if is_imperative(s)]
    assert not misread, f"read as commands: {misread}"
    assert detect_mode("\n".join(DESCRIPTIVE_NOUN_INITIAL)) == "descriptive"


def test_structural_fallback_recognizes_verbs_outside_the_list():
    """The fallback must still earn its place: these verbs are NOT in
    IMPERATIVE_HINT, so only the determiner branch can catch them."""
    from disambiguate import is_imperative, IMPERATIVE_HINT
    for cmd, verb in [("Quiesce the writer before the snapshot.", "quiesce"),
                      ("Marshal the payload into the queue.", "marshal"),
                      ("Reconcile the ledger after the batch ends.", "reconcile")]:
        assert verb not in IMPERATIVE_HINT, f"{verb} is in the list; this no longer tests the fallback"
        assert is_imperative(cmd), cmd


def test_previously_blocklisted_verbs_work_as_commands():
    """MINOR. The blocklist held five words that were not in IMPERATIVE_HINT,
    so each was a silent false negative when used as a real command."""
    from disambiguate import is_imperative
    for cmd in ["Access the console when the alarm fires.",
                "Cache the response for the session when traffic spikes.",
                "Support the legacy client until the migration ends.",
                "Default the value to zero when the field is empty.",
                "Progress the ticket to done after the review ends."]:
        assert is_imperative(cmd), cmd
    assert "E3-condition-after-action" in codes(check("Access the console when the alarm fires."))


def test_glossary_term_beside_a_hyphenated_compound():
    """MAJOR. \\b treats '-' as a boundary, so a term abutting a hyphenated
    compound still split it and inflated the count."""
    for sent, term in [("Clean the surface with a soap-and-water solution.", "soap"),
                       ("Use the trial-and-error method.", "trial")]:
        assert count_ste_words(sent, [term])[0] == count_ste_words(sent)[0], sent


def test_drift_requires_the_shared_word_to_head_a_variant():
    """MINOR. Clustering on any shared word reported three distinct things as
    one thing under three names. Drift is several names for ONE item, and the
    shared word heads at least one of them."""
    distinct = "The test suite runs.\nThe test runner starts.\nThe test fixture loads.\n"
    assert "A4-synonym-drift" not in codes(check_document(distinct, "descriptive", ()))
    real = ("Put the housing on the main body.\nInstall the bolts in the body.\n"
            "Attach the transducer to the body assembly.\n")
    assert "A4-synonym-drift" in codes(check_document(real, "procedural", ()))


def test_comparative_guard_is_load_bearing():
    """MINOR. The guard had no test — the narrowed pattern alone satisfied the
    existing ones."""
    assert "C2-unquantified-delta" not in codes(
        check("The tool provides a better experience for the operator.", mode="descriptive"))
    assert "C2-unquantified-delta" in codes(
        check("This release makes the export better.", mode="descriptive"))
