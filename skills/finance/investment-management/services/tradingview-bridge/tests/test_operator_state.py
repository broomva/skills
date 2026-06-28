"""OperatorState tests — persistence + the interlock state machine."""

from __future__ import annotations

from pathlib import Path

from tradingview_bridge.operator.state import CanarySnapshot, OperatorState


def _pass() -> CanarySnapshot:
    return CanarySnapshot(passed=True, detail="ok", checks={"dispatch": True})


def _fail() -> CanarySnapshot:
    return CanarySnapshot(passed=False, detail="boom", checks={"dispatch": False})


def test_fresh_state_blocks_position_management() -> None:
    """A brand-new operator has not yet confirmed the pipeline — no trading."""
    state = OperatorState()
    assert state.position_management_allowed is False


def test_passing_canary_allows_management() -> None:
    state = OperatorState()
    state.record_canary(_pass(), halt_after_failures=3)
    assert state.last_canary_passed is True
    assert state.position_management_allowed is True


def test_single_failure_soft_halts() -> None:
    state = OperatorState()
    state.record_canary(_pass(), halt_after_failures=3)
    state.record_canary(_fail(), halt_after_failures=3)
    assert state.position_management_allowed is False
    assert state.hard_halted is False  # only soft
    assert state.consecutive_canary_failures == 1


def test_soft_halt_auto_recovers() -> None:
    state = OperatorState()
    state.record_canary(_fail(), halt_after_failures=3)
    assert state.position_management_allowed is False
    state.record_canary(_pass(), halt_after_failures=3)
    assert state.position_management_allowed is True
    assert state.consecutive_canary_failures == 0


def test_consecutive_failures_hard_halt() -> None:
    state = OperatorState()
    for _ in range(3):
        state.record_canary(_fail(), halt_after_failures=3)
    assert state.hard_halted is True
    assert "hard halt" in (state.halt_reason or "")


def test_hard_halt_survives_a_passing_canary() -> None:
    """A passing canary does NOT clear a hard halt — only reset() does."""
    state = OperatorState()
    for _ in range(3):
        state.record_canary(_fail(), halt_after_failures=3)
    assert state.hard_halted is True
    state.record_canary(_pass(), halt_after_failures=3)
    assert state.last_canary_passed is True
    assert state.hard_halted is True  # sticky
    assert state.position_management_allowed is False


def test_reset_clears_hard_halt() -> None:
    state = OperatorState()
    for _ in range(3):
        state.record_canary(_fail(), halt_after_failures=3)
    assert state.hard_halted is True
    state.reset()
    assert state.hard_halted is False
    assert state.consecutive_canary_failures == 0
    assert state.halt_reason is None


def test_save_and_load_roundtrip(tmp_state_path: Path) -> None:
    state = OperatorState()
    state.tick_count = 7
    state.record_canary(_pass(), halt_after_failures=3)
    state.save(tmp_state_path)

    loaded = OperatorState.load(tmp_state_path)
    assert loaded.tick_count == 7
    assert loaded.last_canary_passed is True
    assert loaded.last_canary is not None
    assert loaded.last_canary.detail == "ok"


def test_load_absent_file_returns_fresh(tmp_state_path: Path) -> None:
    assert not tmp_state_path.exists()
    state = OperatorState.load(tmp_state_path)
    assert state.tick_count == 0


def test_load_corrupt_file_returns_fresh(tmp_state_path: Path) -> None:
    tmp_state_path.write_text("{not valid json", encoding="utf-8")
    state = OperatorState.load(tmp_state_path)
    assert state.tick_count == 0  # graceful, not a crash
