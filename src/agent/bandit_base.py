"""Shared statistics and validation for stationary bandit algorithms."""

from abc import ABC, abstractmethod
import math
from typing import Dict, List


class BanditBase(ABC):
    """Base class for algorithms that learn bounded rewards in [0, 1]."""

    def __init__(self, arms: List[str]):
        if not arms or any(not isinstance(arm, str) or not arm for arm in arms):
            raise ValueError("arms must contain at least one non-empty name")
        if len(set(arms)) != len(arms):
            raise ValueError("arm names must be unique")
        self.arms = list(arms)
        self.counts: Dict[str, int] = {arm: 0 for arm in self.arms}
        self.rewards: Dict[str, float] = {arm: 0.0 for arm in self.arms}

    @abstractmethod
    def select_arm(self) -> str:
        """Choose an arm to evaluate next."""

    def update(self, arm: str, reward: float) -> None:
        """Record one finite reward, clamping minor caller overshoot to [0, 1]."""
        if arm not in self.counts:
            raise ValueError(f"Unknown arm: {arm!r}")
        reward = float(reward)
        if not math.isfinite(reward):
            raise ValueError("reward must be finite")
        reward = min(1.0, max(0.0, reward))
        self.counts[arm] += 1
        n = self.counts[arm]
        self.rewards[arm] += (reward - self.rewards[arm]) / n

    def get_statistics(self) -> dict:
        return {"counts": dict(self.counts), "avg_rewards": dict(self.rewards)}
