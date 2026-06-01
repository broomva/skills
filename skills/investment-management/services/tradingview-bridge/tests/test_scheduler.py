"""Tests for the UCB1 scheduler (scheduler.py) — deterministic bandit logic."""

from __future__ import annotations

import pytest

from tradingview_bridge.optimize.scheduler import UCB1Scheduler


def test_unpulled_arms_selected_first_alphabetically() -> None:
    s = UCB1Scheduler(["c", "a", "b"])
    # all unpulled → alphabetical
    assert s.select() == "a"
    s.update("a", 0.5)
    assert s.select() == "b"
    s.update("b", 0.5)
    assert s.select() == "c"


def test_exploit_higher_mean_when_bonus_equal() -> None:
    s = UCB1Scheduler(["a", "b"])
    s.update("a", 0.9)
    s.update("b", 0.1)  # both n=1 → equal exploration bonus → higher mean wins
    assert s.select() == "a"


def test_explore_under_sampled_arm() -> None:
    s = UCB1Scheduler(["a", "b"])
    for _ in range(10):
        s.update("a", 0.5)
    s.update("b", 0.5)  # same mean, but b under-sampled → bigger bonus → explore b
    assert s.select() == "b"


def test_deterministic_same_sequence_same_selections() -> None:
    def run() -> list[str]:
        s = UCB1Scheduler(["a", "b", "c"])
        picks = []
        for r in [0.2, 0.8, 0.5, 0.9, 0.1, 0.6]:
            arm = s.select()
            picks.append(arm)
            s.update(arm, r)
        return picks

    assert run() == run()  # no RNG → reproducible


def test_select_respects_available_subset() -> None:
    s = UCB1Scheduler(["a", "b", "c"])
    s.update("a", 0.9)
    s.update("b", 0.9)
    s.update("c", 0.9)
    # exclude the alphabetically-first; select must pick from {b, c}
    assert s.select(available=["b", "c"]) in {"b", "c"}
    assert s.select(available=["c"]) == "c"


def test_unknown_arm_raises() -> None:
    s = UCB1Scheduler(["a"])
    with pytest.raises(KeyError):
        s.update("z", 0.5)
    with pytest.raises(KeyError):
        s.select(available=["z"])


def test_empty_arms_raises() -> None:
    with pytest.raises(ValueError, match="at least one arm"):
        UCB1Scheduler([])


def test_stats_sorted_by_mean_desc() -> None:
    s = UCB1Scheduler(["a", "b", "c"])
    s.update("a", 0.2)
    s.update("b", 0.9)
    s.update("c", 0.5)
    stats = s.stats()
    assert [x.arm for x in stats] == ["b", "c", "a"]
    assert stats[0].mean_reward == pytest.approx(0.9)
    assert s.total_pulls == 3
