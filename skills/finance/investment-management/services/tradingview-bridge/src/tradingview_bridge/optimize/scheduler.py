"""UCB1 bandit scheduler — the LLM-free direction-selection brain (Phase 1, BRO-1294).

Ported from RD-Agent's feedback-stage multi-armed bandit (which adaptively picks
the next R&D direction), minus the LLM. Each *arm* is a strategy family; the
scheduler decides which family to spend the next evaluation on, balancing exploit
(families with high mean reward) against explore (under-sampled families).

Deterministic by construction: UCB1 (no Thompson sampling, no ε-greedy randomness),
unpulled arms first, ties broken by arm name. Same input sequence → same selections,
so a scheduled run is reproducible and testable.

Rewards must be in [0, 1] for the exploration bonus to be well-scaled — our train
scores (StrategyScore.overall) already are.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_UCB_C = math.sqrt(2.0)  # the classic UCB1 exploration constant for [0,1] rewards


@dataclass(frozen=True)
class ArmStat:
    """An arm's accumulated pulls + reward."""

    arm: str
    pulls: int
    total_reward: float

    @property
    def mean_reward(self) -> float:
        return self.total_reward / self.pulls if self.pulls else 0.0


class UCB1Scheduler:
    """Deterministic UCB1 over named arms."""

    def __init__(self, arms: list[str], *, c: float = DEFAULT_UCB_C) -> None:
        if not arms:
            raise ValueError("UCB1Scheduler needs at least one arm")
        self._pulls: dict[str, int] = dict.fromkeys(arms, 0)
        self._reward: dict[str, float] = dict.fromkeys(arms, 0.0)
        self._total_pulls = 0
        self._c = c

    @property
    def total_pulls(self) -> int:
        return self._total_pulls

    def select(self, available: list[str] | None = None) -> str:
        """Pick the next arm to pull (from ``available``, default all arms).

        Unpulled available arms come first (UCB = +inf), alphabetically. Otherwise
        the UCB1 score ``mean + c·sqrt(ln(total)/n)``, ties broken by arm name.
        """
        arms = available if available is not None else list(self._pulls)
        unknown = [a for a in arms if a not in self._pulls]
        if unknown:
            raise KeyError(f"unknown arm(s): {sorted(unknown)}")
        if not arms:
            raise ValueError("no arms available to select")

        unpulled = sorted(a for a in arms if self._pulls[a] == 0)
        if unpulled:
            return unpulled[0]

        def ucb(arm: str) -> float:
            n = self._pulls[arm]
            return self._reward[arm] / n + self._c * math.sqrt(math.log(self._total_pulls) / n)

        # sorted(arms) makes the tie-break alphabetical: max returns the first
        # element attaining the maximum, which is the alphabetically-first name.
        return max(sorted(arms), key=ucb)

    def update(self, arm: str, reward: float) -> None:
        if arm not in self._pulls:
            raise KeyError(f"unknown arm {arm!r}")
        self._pulls[arm] += 1
        self._reward[arm] += reward
        self._total_pulls += 1

    def stats(self) -> list[ArmStat]:
        """Per-arm stats, sorted by mean reward (desc) then name."""
        stats = [
            ArmStat(arm=a, pulls=self._pulls[a], total_reward=self._reward[a]) for a in self._pulls
        ]
        return sorted(stats, key=lambda s: (-s.mean_reward, s.arm))
