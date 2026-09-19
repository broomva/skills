"""
Entity-COHERENCE gate at the promotion stage.

The Nous sum gate's false positives are identity failures, not score failures:
a section heading, a person's name, or a phrase lifted from a source document
filed as a `concept`. Measured 2026-09-18 (jev-1.13.0) on 9 human-quarantined
junk pages vs 30 accepted pages: specificity AUC 0.60, relevance AUC 0.81, a
Noul "is the title a coherent knowledge-graph node the core_claim is genuinely
about?" AUC 0.98.

Every test here is hermetic: the network seam (`_coherence_transport`, or
`urllib.request.urlopen` beneath it) is monkeypatched. No test may reach
api.typesafe.ai.

Mutation proofs (run by hand and recorded in the PR body):
  * flip `<` to `>` in the threshold comparison → the boundary tests fail;
  * comment out the gate call inside promote_item → the quarantine and
    checked-counter tests fail.
"""
import http.client
import io
import json
import urllib.error
import urllib.request

import pytest

import bookkeeping
from bookkeeping import RawItem, ScoredItem, promote_item

# A body that derives a complete core_claim (see derive_core_claim) and is
# long enough to exercise the excerpt cap.
BODY = (
    "The arcan agent loop uses bi-temporal event sourcing because the soul file "
    "must replay deterministically; this means the promotion gate stays consistent."
)


def _item(content=BODY, author="", source_id="2026-09-18-test-raw"):
    return RawItem(
        item_id="cafebabe",
        source_id=source_id,
        source_type="research",
        content=content,
        quote="",
        author=author,
        timestamp="2026-09-18T00:00:00+00:00",
        metadata={},
    )


def _scored(content=BODY):
    return ScoredItem(
        item=_item(content),
        novelty=3, specificity=3, relevance=3, total=9, promote=True,
        candidate_entities=["test-entity"],
        scoring_method="heuristic",
        reasoning={},
    )


def _response(p):
    """The wire shape api.typesafe.ai returns (probed live 2026-09-18)."""
    return {
        "model": "jev-1.13.0",
        "answers": {"coherent": {"type": "noul", "noul": p}},
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


@pytest.fixture
def gate(tmp_path, monkeypatch):
    """Gate ON, every on-disk root redirected under tmp_path, counters reset.

    Returns a dict with the redirected `entities` and `quarantine` roots and a
    `calls` list the transport stubs append to.
    """
    entities = tmp_path / "research" / "entities"
    for et in bookkeeping.ENTITY_TYPES:
        (entities / et).mkdir(parents=True, exist_ok=True)
    quarantine = tmp_path / "config" / "quarantine"
    monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", tmp_path)
    monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", entities)
    monkeypatch.setattr(bookkeeping, "QUARANTINE_DIR", quarantine)
    monkeypatch.setenv(bookkeeping.COHERENCE_GATE_ENV, "1")
    bookkeeping.reset_coherence_run_state()
    yield {"entities": entities, "quarantine": quarantine, "calls": []}
    bookkeeping.reset_coherence_run_state()


def _stub_transport(monkeypatch, gate, result):
    """Replace the network seam. `result` is a value, or an exception to raise."""
    def transport(payload):
        gate["calls"].append(payload)
        if isinstance(result, BaseException):
            raise result
        return result
    monkeypatch.setattr(bookkeeping, "_coherence_transport", transport)


def _quarantine_files(gate):
    return sorted(gate["quarantine"].rglob("*.md")) if gate["quarantine"].exists() else []


# ── 1. transport unavailable → pass-through, counted, LOUD ─────────────────────

class TestUnavailablePassesThrough:

    def test_transport_none_writes_page_counts_unavailable_and_warns(
            self, gate, monkeypatch, capsys):
        _stub_transport(monkeypatch, gate, None)
        path = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert path is not None and path.exists(), "unavailable ⇒ status quo: the page is written"
        assert bookkeeping.coherence_unavailable == 1
        assert bookkeeping.coherence_checked == 0
        assert bookkeeping.coherence_rejected == 0
        err = capsys.readouterr().err
        assert "[coherence]" in err and "unavailable" in err, err
        assert _quarantine_files(gate) == []

    # 7. transport raises / malformed → unavailable, page written, cause named
    @pytest.mark.parametrize("result, cause_fragment", [
        (OSError("socket exploded"), "OSError"),
        (ConnectionResetError("peer reset"), "ConnectionResetError"),
        (TimeoutError("timed out"), "TimeoutError"),
        (urllib.error.URLError("timed out"), "URLError"),
        (http.client.BadStatusLine("HTTP/9.9"), "BadStatusLine"),
        (json.JSONDecodeError("Expecting value", "x", 0), "JSONDecodeError"),
        (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"), "UnicodeDecodeError"),
        ({"answers": {}}, "malformed"),
        ({"answers": {"coherent": {"noul": "high"}}}, "malformed"),
        ({"answers": {"coherent": {"noul": 1.5}}}, "malformed"),
        ({"answers": {"coherent": {"noul": True}}}, "malformed"),
        ("not json at all", "malformed"),
        ([], "malformed"),
    ])
    def test_raise_or_malformed_is_unavailable(
            self, gate, monkeypatch, capsys, result, cause_fragment):
        _stub_transport(monkeypatch, gate, result)
        path = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert path is not None and path.exists()
        assert bookkeeping.coherence_unavailable == 1
        assert bookkeeping.coherence_checked == 0
        err = capsys.readouterr().err
        assert cause_fragment in err, err
        assert _quarantine_files(gate) == []

    def test_programming_errors_are_not_reported_as_unavailable(self, gate, monkeypatch):
        """A bug in this module must surface, not degrade the gate into a
        permanent no-op announced as a network condition."""
        _stub_transport(monkeypatch, gate, TypeError("Object of type set is not JSON serializable"))
        with pytest.raises(TypeError):
            promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert bookkeeping.coherence_unavailable == 0
        assert not (gate["entities"] / "concept" / "event-sourcing.md").exists()

    def test_varying_malformed_bodies_share_one_cause_line(self, gate, monkeypatch, capsys):
        """The cause must be constant per condition or the once-per-run dedupe
        is defeated by a backend returning per-item garbage — which would also
        echo third-party response bodies into the transcript."""
        bodies = iter([{"answers": {"x": 1}},
                       {"answers": {"coherent": {"noul": "a"}}},
                       "zzz-third-party-body-zzz"])
        monkeypatch.setattr(bookkeeping, "_coherence_transport", lambda payload: next(bodies))
        for slug in ("event-sourcing", "promotion-gate", "knowledge-graph"):
            promote_item(_scored(), slug, entity_type="concept")
        err = capsys.readouterr().err
        assert err.count("[coherence]") == 1, err
        assert bookkeeping.coherence_unavailable == 3
        assert "zzz-third-party-body-zzz" not in err

    def test_http_error_names_the_status(self, gate, monkeypatch, capsys):
        exc = urllib.error.HTTPError(
            bookkeeping.TYPESAFE_SYSTEMONE_URL, 503, "Service Unavailable", {},
            io.BytesIO(b"{}"))
        _stub_transport(monkeypatch, gate, exc)
        path = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert path is not None and path.exists()
        assert bookkeeping.coherence_unavailable == 1
        assert "HTTP 503" in capsys.readouterr().err

    def test_cause_line_printed_once_per_run_but_counted_every_time(
            self, gate, monkeypatch, capsys):
        _stub_transport(monkeypatch, gate, None)
        promote_item(_scored(), "event-sourcing", entity_type="concept")
        promote_item(_scored(), "promotion-gate", entity_type="concept")
        assert bookkeeping.coherence_unavailable == 2
        err = capsys.readouterr().err
        assert err.count("[coherence]") == 1, err
        # A new run starts the dedupe over — the cause must surface again.
        bookkeeping.reset_coherence_run_state()
        promote_item(_scored(), "knowledge-graph", entity_type="concept")
        assert capsys.readouterr().err.count("[coherence]") == 1
        assert bookkeeping.coherence_unavailable == 1


# ── 2/3. rejection quarantines; acceptance writes ──────────────────────────────

class TestVerdicts:

    def test_low_score_quarantines_and_never_writes_entity(self, gate, monkeypatch, capsys):
        _stub_transport(monkeypatch, gate, _response(0.1))
        ret = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert ret is None
        assert not (gate["entities"] / "concept" / "event-sourcing.md").exists()
        files = _quarantine_files(gate)
        assert len(files) == 1, files
        qpath = files[0]
        assert qpath.name == "concept_event-sourcing.md"
        assert qpath.parent.name.endswith("-coherence"), qpath.parent
        fm = qpath.read_text().split("---")[1]
        assert "coherence: 0.1\n" in fm, fm
        assert "coherence_gate: rejected\n" in fm, fm
        assert "slug: event-sourcing" in fm
        assert bookkeeping.coherence_rejected == 1
        assert bookkeeping.coherence_checked == 1
        assert bookkeeping.coherence_unavailable == 0
        out = capsys.readouterr().out
        assert "QUARANTINE" in out and "concept/event-sourcing" in out, out

    def test_quarantined_page_is_recoverable_verbatim(self, gate, monkeypatch):
        """Only the two gate fields are added — the rest is the page that would
        have been written, so a false rejection is a `mv` plus two deletions."""
        _stub_transport(monkeypatch, gate, _response(0.9))
        accepted = promote_item(_scored(), "event-sourcing", entity_type="concept").read_text()
        bookkeeping.reset_coherence_run_state()
        _stub_transport(monkeypatch, gate, _response(0.1))
        promote_item(_scored(), "promotion-gate", entity_type="concept")
        quarantined = _quarantine_files(gate)[0].read_text()
        stripped = "\n".join(
            l for l in quarantined.splitlines()
            if not l.startswith(("coherence:", "coherence_gate:"))
        ) + "\n"
        assert stripped.replace("promotion-gate", "event-sourcing") \
                       .replace("Promotion Gate", "Event Sourcing") == accepted

    def test_high_score_promotes_and_counts_checked(self, gate, monkeypatch):
        _stub_transport(monkeypatch, gate, _response(0.9))
        path = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert path is not None and path.exists()
        assert bookkeeping.coherence_checked == 1
        assert bookkeeping.coherence_rejected == 0
        assert bookkeeping.coherence_unavailable == 0
        assert _quarantine_files(gate) == []
        assert "coherence" not in path.read_text().split("---")[1]

    def test_dry_run_still_asks_but_writes_nothing(self, gate, monkeypatch, capsys):
        _stub_transport(monkeypatch, gate, _response(0.1))
        ret = promote_item(_scored(), "event-sourcing", entity_type="concept", dry_run=True)
        assert ret is None
        assert len(gate["calls"]) == 1
        assert bookkeeping.coherence_rejected == 1
        assert bookkeeping.coherence_rejected_slug("event-sourcing")
        assert _quarantine_files(gate) == []
        assert not (gate["entities"] / "concept" / "event-sourcing.md").exists()
        assert "dry-run" in capsys.readouterr().out

    def test_quarantine_write_failure_is_loud_and_still_refuses(
            self, gate, monkeypatch, tmp_path, capsys):
        """The SAFE verdict must never abort the run, and a failed quarantine
        write must not fall through to writing the entity page."""
        blocker = tmp_path / "blocker"
        blocker.write_text("i am a file, not a directory")
        monkeypatch.setattr(bookkeeping, "QUARANTINE_DIR", blocker / "quarantine")
        _stub_transport(monkeypatch, gate, _response(0.1))
        ret = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert ret is None
        assert not (gate["entities"] / "concept" / "event-sourcing.md").exists()
        assert bookkeeping.coherence_rejected == 1
        captured = capsys.readouterr()
        assert "quarantine write FAILED" in captured.err
        assert "QUARANTINE" in captured.out

    def test_quarantine_filename_cannot_escape_the_dated_dir(self):
        name = bookkeeping._quarantine_filename("tool/../../etc", "event-sourcing")
        assert "/" not in name and ".." not in name
        assert name.endswith("_event-sourcing.md")
        assert bookkeeping._quarantine_filename("concept", "x") == "concept_x.md"

    @pytest.mark.parametrize("p, rendered", [
        (0.1, "0.1"), (0.49, "0.49"), (0.93, "0.93"), (0.0, "0.0"), (1.0, "1.0"),
        (0.00001, "0.00001"),  # NOT "1e-05": PyYAML would read that back as a string
    ])
    def test_coherence_is_rendered_as_a_yaml_float(self, p, rendered):
        assert bookkeeping._yaml_float(p) == rendered
        assert "e" not in rendered and "." in rendered


# ── the rejection has memory ───────────────────────────────────────────────────

class TestRejectionMemory:

    def test_prior_quarantine_is_remembered_without_a_call(self, gate, monkeypatch, capsys):
        prior_dir = gate["quarantine"] / "2026-09-01-coherence"
        prior_dir.mkdir(parents=True)
        prior = prior_dir / "concept_event-sourcing.md"
        prior_text = "---\nslug: event-sourcing\ncoherence: 0.1\ncoherence_gate: rejected\n---\n"
        prior.write_text(prior_text)
        _stub_transport(monkeypatch, gate, _response(0.9))  # would ADMIT if asked
        ret = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert ret is None
        assert gate["calls"] == [], "no call may be paid for a remembered rejection"
        assert not (gate["entities"] / "concept" / "event-sourcing.md").exists()
        assert bookkeeping.coherence_stats() == {
            "enabled": True, "checked": 0, "rejected": 0, "unavailable": 0, "remembered": 1}
        assert bookkeeping.coherence_rejected_slug("event-sourcing")
        assert prior.read_text() == prior_text, "the prior copy is never overwritten"
        assert "quarantined by an earlier run" in capsys.readouterr().out
        # Moving the file out (recovery) or deleting it re-opens the question.
        prior.unlink()
        bookkeeping.reset_coherence_run_state()
        ret = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert ret is not None and ret.exists()
        assert len(gate["calls"]) == 1

    def test_same_run_second_attempt_is_remembered_not_overwritten(self, gate, monkeypatch):
        _stub_transport(monkeypatch, gate, _response(0.1))
        promote_item(_scored(), "event-sourcing", entity_type="concept")
        q = _quarantine_files(gate)[0]
        before, mtime = q.read_text(), q.stat().st_mtime_ns
        _stub_transport(monkeypatch, gate, _response(0.9))
        gate["calls"].clear()
        assert promote_item(_scored(), "event-sourcing", entity_type="concept") is None
        assert gate["calls"] == []
        assert q.read_text() == before and q.stat().st_mtime_ns == mtime
        assert bookkeeping.coherence_rejected == 1 and bookkeeping.coherence_remembered == 1

    def test_dry_run_recurrence_in_one_run_is_not_charged_twice(self, gate, monkeypatch, capsys):
        """Dry-run writes no quarantine file, so the on-disk memory cannot
        see a same-run recurrence — the in-run memory must."""
        _stub_transport(monkeypatch, gate, _response(0.1))
        promote_item(_scored(), "event-sourcing", entity_type="concept", dry_run=True)
        assert len(gate["calls"]) == 1
        promote_item(_scored(), "event-sourcing", entity_type="concept", dry_run=True)
        assert len(gate["calls"]) == 1, "second attempt must not be charged"
        assert bookkeeping.coherence_stats() == {
            "enabled": True, "checked": 1, "rejected": 1, "unavailable": 0, "remembered": 1}
        assert "refused earlier in this run" in capsys.readouterr().out
        # A different TYPE for the same slug is a different page: charged.
        promote_item(_scored(), "event-sourcing", entity_type="tool", dry_run=True)
        assert len(gate["calls"]) == 2
        assert bookkeeping.coherence_rejected_slug("event-sourcing")

    def test_memory_is_per_type(self, gate, monkeypatch):
        (gate["quarantine"] / "2026-09-01-coherence").mkdir(parents=True)
        (gate["quarantine"] / "2026-09-01-coherence" / "pattern_event-sourcing.md").write_text("x")
        _stub_transport(monkeypatch, gate, _response(0.9))
        ret = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert ret is not None and len(gate["calls"]) == 1
        assert bookkeeping.coherence_remembered == 0

    def test_disabled_gate_ignores_the_memory(self, gate, monkeypatch):
        """Explicitly switching the gate off is the operator's decision to
        write pages ungated — including ones an earlier run refused."""
        (gate["quarantine"] / "2026-09-01-coherence").mkdir(parents=True)
        (gate["quarantine"] / "2026-09-01-coherence" / "concept_event-sourcing.md").write_text("x")
        monkeypatch.setenv(bookkeeping.COHERENCE_GATE_ENV, "0")
        _stub_transport(monkeypatch, gate, _response(0.0))
        ret = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert ret is not None and ret.exists()
        assert gate["calls"] == [] and bookkeeping.coherence_remembered == 0


# ── 4. the threshold boundary (mutation proof for `<`) ─────────────────────────

class TestThresholdBoundary:

    def test_threshold_is_the_named_constant(self):
        assert bookkeeping.COHERENCE_THRESHOLD == 0.5

    @pytest.mark.parametrize("p, expect_quarantine", [
        (0.49, True),
        (0.51, False),
        (0.5, False),   # exactly at threshold PASSES: the comparison is strict
        (0.0, True),
        (1.0, False),
    ])
    def test_boundary(self, gate, monkeypatch, p, expect_quarantine):
        _stub_transport(monkeypatch, gate, _response(p))
        ret = promote_item(_scored(), "event-sourcing", entity_type="concept")
        page = gate["entities"] / "concept" / "event-sourcing.md"
        if expect_quarantine:
            assert ret is None
            assert not page.exists()
            assert len(_quarantine_files(gate)) == 1
            assert bookkeeping.coherence_rejected == 1
        else:
            assert ret == page and page.exists()
            assert _quarantine_files(gate) == []
            assert bookkeeping.coherence_rejected == 0
        assert bookkeeping.coherence_checked == 1


# ── 5. type-aware criteria ─────────────────────────────────────────────────────

class TestTypeAwareCriteria:

    def _payload_for(self, gate, monkeypatch, entity_type, slug):
        _stub_transport(monkeypatch, gate, _response(0.9))
        promote_item(_scored(), slug, entity_type=entity_type)
        assert len(gate["calls"]) == 1
        return gate["calls"][0]

    def test_tool_and_concept_get_different_criteria(self, gate, monkeypatch):
        tool = self._payload_for(gate, monkeypatch, "tool", "orca-ade")
        gate["calls"].clear()
        concept = self._payload_for(gate, monkeypatch, "concept", "event-sourcing")

        for payload, et in ((tool, "tool"), (concept, "concept")):
            assert payload["model"] == bookkeeping.COHERENCE_MODEL
            assert payload["state"]["entity_type"] == et
            q = payload["questions"]["coherent"]
            assert q["type"] == "noul"
            assert q["instructions"]
            assert set(q["criteria"]) == {"true", "false"}

        assert tool["questions"]["coherent"]["criteria"]["true"] \
            != concept["questions"]["coherent"]["criteria"]["true"]
        assert tool["questions"]["coherent"]["criteria"]["false"] \
            != concept["questions"]["coherent"]["criteria"]["false"]
        # A product NAME is legitimate for a tool; the concept criteria say the
        # opposite about names.
        assert "name" in tool["questions"]["coherent"]["criteria"]["true"].lower()
        assert "name" in concept["questions"]["coherent"]["criteria"]["false"].lower()

    @pytest.mark.parametrize("entity_type", ["tool", "person", "project", "org"])
    def test_named_types_share_the_named_criteria(self, entity_type):
        assert bookkeeping._coherence_criteria_for(entity_type) \
            is bookkeeping.COHERENCE_CRITERIA["named"]

    @pytest.mark.parametrize("entity_type", [
        "concept", "pattern", "question", "discovery", "framework-refinement",
        "industry-pattern", "persona", "unknown-type"])
    def test_concept_like_and_unknown_types_get_the_concept_criteria(self, entity_type):
        assert bookkeeping._coherence_criteria_for(entity_type) \
            is bookkeeping.COHERENCE_CRITERIA["concept"]

    def test_every_entity_type_has_a_deliberate_bucket(self):
        """Adding a type to ENTITY_TYPES must force a criteria decision, not
        silently inherit the punitive default."""
        named, concept = bookkeeping._COHERENCE_NAMED_TYPES, bookkeeping._COHERENCE_CONCEPT_TYPES
        assert named & concept == set()
        assert named | concept == set(bookkeeping.ENTITY_TYPES), (
            sorted(set(bookkeeping.ENTITY_TYPES) ^ (named | concept)))

    def test_state_carries_the_identity_fields_and_caps_the_excerpt(self, gate, monkeypatch):
        long_body = BODY + " " + ("x" * 5000)
        _stub_transport(monkeypatch, gate, _response(0.9))
        promote_item(_scored(long_body), "event-sourcing", entity_type="concept")
        state = gate["calls"][0]["state"]
        assert state["slug"] == "event-sourcing"
        assert state["title"] == "Event Sourcing"
        assert state["entity_type"] == "concept"
        assert state["core_claim"] and len(state["core_claim"]) <= 140
        assert len(state["body_excerpt"]) == bookkeeping.COHERENCE_BODY_EXCERPT_CHARS
        assert set(state) == {"slug", "title", "entity_type", "core_claim", "body_excerpt"}


# ── 6. explicit disable ────────────────────────────────────────────────────────

class TestDisable:

    @pytest.mark.parametrize("value", ["0", "false", "off", "no", " 0 "])
    def test_env_zero_never_calls_transport(self, gate, monkeypatch, value):
        monkeypatch.setenv(bookkeeping.COHERENCE_GATE_ENV, value)
        _stub_transport(monkeypatch, gate, _response(0.0))  # would reject if consulted
        path = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert path is not None and path.exists()
        assert gate["calls"] == []
        assert bookkeeping.coherence_stats() == {
            "enabled": False, "checked": 0, "rejected": 0, "unavailable": 0, "remembered": 0}

    def test_unset_env_means_enabled(self, monkeypatch):
        monkeypatch.delenv(bookkeeping.COHERENCE_GATE_ENV, raising=False)
        assert bookkeeping.coherence_gate_enabled() is True


# ── 8. the existing-page update path is untouched ──────────────────────────────

class TestUpdatePathIsUntouched:

    def test_existing_page_never_calls_transport(self, gate, monkeypatch):
        _stub_transport(monkeypatch, gate, _response(0.9))
        first = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert first is not None
        assert len(gate["calls"]) == 1
        bookkeeping.reset_coherence_run_state()
        _stub_transport(monkeypatch, gate, _response(0.0))  # would reject a NEW page
        gate["calls"].clear()
        promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert gate["calls"] == [], "update path must not consult the gate"
        assert first.exists()
        assert bookkeeping.coherence_stats()["checked"] == 0

    def test_gate_sits_after_the_cheaper_gates(self, gate, monkeypatch):
        """A junk slug or an underivable claim is refused BEFORE the paid call."""
        _stub_transport(monkeypatch, gate, _response(0.9))
        assert promote_item(_scored(), "the-goodhart", entity_type="pattern") is None
        underivable = (  # the BRO-1983 fixture: no complete claim ≤140 chars
            "## VERIFIED VERDICTS (2026-07-20) — authoritative\n\n"
            "**The three novelty checks:**\n\n"
            "- **(a) Model-invariant harness stability — PARTIAL YES**, our uniform-margin "
            "result holds only under the assumptions listed in section 4 of the writeup, "
            "which we have not yet validated on a second model family.\n"
        )
        assert promote_item(_scored(underivable), "event-sourcing",
                            entity_type="concept") is None
        assert gate["calls"] == []


# ── the real transport, with urlopen faked ─────────────────────────────────────

class TestRealTransport:

    def test_no_key_names_the_cause_without_any_request(
            self, gate, monkeypatch, tmp_path, capsys):
        monkeypatch.delenv(bookkeeping.TYPESAFE_API_KEY_ENV, raising=False)
        monkeypatch.setattr(bookkeeping, "TYPESAFE_API_KEY_FILE", tmp_path / "absent")

        def boom(*a, **k):
            raise AssertionError("urlopen must not be called without a key")
        monkeypatch.setattr(urllib.request, "urlopen", boom)

        path = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert path is not None and path.exists()
        assert bookkeeping.coherence_unavailable == 1
        err = capsys.readouterr().err
        assert "no API key" in err and bookkeeping.TYPESAFE_API_KEY_ENV in err, err

    def test_malformed_key_is_never_sent_and_never_echoed(
            self, gate, monkeypatch, tmp_path, capsys):
        """A soft-wrapped paste leaves a newline INSIDE the key. http.client
        would raise ValueError carrying the full header value — so the key is
        refused before a request exists, and the cause names no bytes of it."""
        monkeypatch.delenv(bookkeeping.TYPESAFE_API_KEY_ENV, raising=False)
        keyfile = tmp_path / "api_key"
        keyfile.write_text("sk-live-part-one\nsk-live-part-two\n")
        monkeypatch.setattr(bookkeeping, "TYPESAFE_API_KEY_FILE", keyfile)

        def boom(*a, **k):
            raise AssertionError("urlopen must not be called with a malformed key")
        monkeypatch.setattr(urllib.request, "urlopen", boom)

        path = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert path is not None and path.exists()
        assert bookkeeping.coherence_unavailable == 1
        err = capsys.readouterr().err
        assert "malformed" in err, err
        assert "sk-live" not in err

    def test_undecodable_key_file_is_no_key_not_a_crash(
            self, gate, monkeypatch, tmp_path, capsys):
        """The redactor re-reads the key on the unavailable path; a non-UTF-8
        key file must not turn that into a second exception inside the
        handler that escapes promote_item and aborts the run."""
        monkeypatch.delenv(bookkeeping.TYPESAFE_API_KEY_ENV, raising=False)
        keyfile = tmp_path / "api_key"
        keyfile.write_bytes(b"\xff\xfe\x00 not utf-8 \x80")
        monkeypatch.setattr(bookkeeping, "TYPESAFE_API_KEY_FILE", keyfile)

        def boom(*a, **k):
            raise AssertionError("urlopen must not be called without a key")
        monkeypatch.setattr(urllib.request, "urlopen", boom)

        path = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert path is not None and path.exists()
        assert bookkeeping.coherence_unavailable == 1
        assert "no API key" in capsys.readouterr().err

    def test_key_in_an_exception_message_is_redacted(self, gate, monkeypatch, capsys):
        monkeypatch.setenv(bookkeeping.TYPESAFE_API_KEY_ENV, "sk-secret-777")
        _stub_transport(monkeypatch, gate,
                        OSError("Invalid header value 'Bearer sk-secret-777\\n'"))
        path = promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert path is not None
        err = capsys.readouterr().err
        assert "sk-secret-777" not in err, err
        assert "***" in err

    def test_key_file_is_read_when_env_is_unset(self, monkeypatch, tmp_path):
        monkeypatch.delenv(bookkeeping.TYPESAFE_API_KEY_ENV, raising=False)
        keyfile = tmp_path / "api_key"
        keyfile.write_text("  file-key-123\n")
        monkeypatch.setattr(bookkeeping, "TYPESAFE_API_KEY_FILE", keyfile)
        assert bookkeeping._typesafe_api_key() == "file-key-123"
        monkeypatch.setenv(bookkeeping.TYPESAFE_API_KEY_ENV, "env-key-456")
        assert bookkeeping._typesafe_api_key() == "env-key-456", "env wins over the file"

    def test_posts_bearer_json_and_parses_noul(self, gate, monkeypatch):
        monkeypatch.setenv(bookkeeping.TYPESAFE_API_KEY_ENV, "sk-test-key")
        seen = {}

        class FakeResp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            seen["method"] = req.get_method()
            seen["auth"] = req.get_header("Authorization")
            seen["ctype"] = req.get_header("Content-type")
            seen["body"] = json.loads(req.data.decode("utf-8"))
            seen["timeout"] = timeout
            return FakeResp(json.dumps(_response(0.93)).encode("utf-8"))
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        p = bookkeeping.entity_coherence(
            "orca-ade", "Orca Ade", "tool", "Orca abstracts the transport.", "body")
        assert p == 0.93
        assert seen["url"] == "https://api.typesafe.ai/v1/systemone"
        assert seen["method"] == "POST"
        assert seen["auth"] == "Bearer sk-test-key"
        assert seen["ctype"] == "application/json"
        assert seen["timeout"] == bookkeeping.COHERENCE_TIMEOUT_S == 10
        assert seen["body"]["model"] == "jev-latest"
        assert seen["body"]["state"]["entity_type"] == "tool"
        assert seen["body"]["questions"]["coherent"]["type"] == "noul"
        assert bookkeeping.coherence_checked == 1

    def test_http_error_from_urlopen_is_unavailable_with_status(
            self, gate, monkeypatch, capsys):
        monkeypatch.setenv(bookkeeping.TYPESAFE_API_KEY_ENV, "sk-test-key")

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {},
                                         io.BytesIO(b'{"error":"bad key"}'))
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        assert bookkeeping.entity_coherence("s", "S", "concept", "c.", "b") is None
        assert bookkeeping.coherence_unavailable == 1
        err = capsys.readouterr().err
        assert "HTTP 401" in err and "sk-test-key" not in err


# ── counters, stats, and the run-log entry ─────────────────────────────────────

def _pipeline_fixture(tmp_path, monkeypatch):
    """A one-item raw note under tmp roots; returns the config dir."""
    notes = tmp_path / "research" / "notes"
    notes.mkdir(parents=True)
    config = tmp_path / "config"
    monkeypatch.setattr(bookkeeping, "NOTES_DIR", notes)
    monkeypatch.setattr(bookkeeping, "CONFIG_DIR", config)
    monkeypatch.setattr(bookkeeping, "RUN_LOG", config / "run-log.jsonl")
    monkeypatch.setattr(bookkeeping, "STATUS_CACHE", config / "status.json")
    # Same fixture item test_layer2_retention uses: it is known to resolve
    # to at least one entity-shaped candidate through scatter/resolve.
    (notes / "2026-09-18-fresh-raw.md").write_text(
        "---\nsource: test\n---\n\n"
        "## Item 1 — @someone (web)\n\n"
        "**Score**: 7/9 — novelty:3 specificity:2 relevance:2\n\n"
        "**Our angle**: The arcan agent loop uses bi-temporal event sourcing "
        "because the soul file must replay deterministically; this means the "
        "promotion gate and memory provenance stay consistent across 1000 runs.\n"
    )
    return config


class TestRunState:

    def test_stats_shape_and_reset(self, gate, monkeypatch):
        _stub_transport(monkeypatch, gate, _response(0.1))
        promote_item(_scored(), "event-sourcing", entity_type="concept")
        assert bookkeeping.coherence_stats() == {
            "enabled": True, "checked": 1, "rejected": 1, "unavailable": 0, "remembered": 0}
        assert bookkeeping.coherence_rejected_slug("event-sourcing")
        bookkeeping.reset_coherence_run_state()
        assert bookkeeping.coherence_stats() == {
            "enabled": True, "checked": 0, "rejected": 0, "unavailable": 0, "remembered": 0}
        assert not bookkeeping.coherence_rejected_slug("event-sourcing")

    def test_run_pipeline_entry_carries_coherence_stats(
            self, gate, monkeypatch, tmp_path, capsys):
        config = _pipeline_fixture(tmp_path, monkeypatch)
        _stub_transport(monkeypatch, gate, _response(0.1))
        # Poison the counters: run_pipeline must reset them at its start.
        bookkeeping.coherence_unavailable = 99
        entry = bookkeeping.run_pipeline(verbose=False)
        assert entry, "fixture must produce a pipeline run"
        n = len(gate["calls"])
        assert n >= 1, "the pipeline must have consulted the gate"
        assert entry["coherence"] == bookkeeping.coherence_stats()
        assert entry["coherence"]["unavailable"] == 0, "counters were not reset"
        assert entry["coherence"]["rejected"] == n
        assert entry["coherence"]["checked"] == n
        assert entry["entities_created"] == 0, "a quarantined page is not a created page"
        assert list(gate["entities"].rglob("*.md")) == [], "every candidate was rejected"
        assert len(_quarantine_files(gate)) == n
        logged = json.loads((config / "run-log.jsonl").read_text().splitlines()[-1])
        assert logged["coherence"] == entry["coherence"]
        out = capsys.readouterr().out
        assert (f"Coherence gate: on | checked: {n} | rejected: {n} "
                f"| remembered: 0 | unavailable: 0") in out, out

    def test_cmd_promote_survives_and_counts_honestly(
            self, gate, monkeypatch, tmp_path, capsys):
        """cmd_promote had no test at all; a `path` shadowing crash on its
        most common invocation shipped green. Pin: it runs to its summary
        line on every outcome, and a quarantined item is not 'promoted'."""
        import argparse
        config = _pipeline_fixture(tmp_path, monkeypatch)
        src = bookkeeping.NOTES_DIR / "2026-09-18-fresh-raw.md"
        args = lambda dry: argparse.Namespace(file=str(src), dry_run=dry, verbose=False)

        _stub_transport(monkeypatch, gate, _response(0.1))
        bookkeeping.cmd_promote(args(True))
        out = capsys.readouterr().out
        assert "[promote] Done: 0 items promoted from 2026-09-18-fresh-raw.md" in out, out
        assert "DRY RUN" in out
        assert len(gate["calls"]) >= 1
        assert list(gate["entities"].rglob("*.md")) == []

        gate["calls"].clear()
        bookkeeping.cmd_promote(args(False))
        out = capsys.readouterr().out
        assert "Done: 0 items promoted" in out and "QUARANTINE" in out, out
        assert list(gate["entities"].rglob("*.md")) == []
        assert len(_quarantine_files(gate)) == len(gate["calls"]) >= 1

        # Control: an admitting verdict promotes and counts (memory cleared:
        # cmd_promote resets run state, and the quarantined copy is removed).
        for q in _quarantine_files(gate):
            q.unlink()
        gate["calls"].clear()
        _stub_transport(monkeypatch, gate, _response(0.9))
        bookkeeping.cmd_promote(args(False))
        out = capsys.readouterr().out
        assert "Done: 1 items promoted from 2026-09-18-fresh-raw.md" in out, out
        assert len(list(gate["entities"].rglob("*.md"))) == 1
        assert not (config / "run-log.jsonl").exists(), "cmd_promote does not write the run log"

    def test_dry_run_pipeline_does_not_count_a_rejection_as_created(
            self, gate, monkeypatch, tmp_path, capsys):
        """In dry-run promote_item returns None for BOTH 'would create' and
        'gate refused'; the pipeline must not report a refused page as created."""
        config = _pipeline_fixture(tmp_path, monkeypatch)
        _stub_transport(monkeypatch, gate, _response(0.1))
        entry = bookkeeping.run_pipeline(dry_run=True, verbose=False)
        n = len(gate["calls"])
        assert n >= 1
        assert entry["entities_created"] == 0
        assert entry["coherence"]["rejected"] == n
        assert list(gate["entities"].rglob("*.md")) == []
        assert _quarantine_files(gate) == [], "dry-run writes no quarantine file"
        assert not (config / "run-log.jsonl").exists(), "dry-run writes no run log"
        out = capsys.readouterr().out
        assert "dry-run: would QUARANTINE" in out
        assert "Entities created: 0" in out
        # Control: an admitting verdict IS counted as a would-be create.
        gate["calls"].clear()
        _stub_transport(monkeypatch, gate, _response(0.9))
        entry = bookkeeping.run_pipeline(dry_run=True, verbose=False)
        assert entry["entities_created"] == len(gate["calls"]) >= 1
