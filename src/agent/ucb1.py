"""Upper Confidence Bound (UCB1) bandit selection."""

import math
from .bandit_base import BanditBase


class UCB1(BanditBase):
    def __init__(self, arms, exploration_param=None):
        super().__init__(arms)
        self.c = math.sqrt(2.0) if exploration_param is None else float(exploration_param)
        if not math.isfinite(self.c) or self.c < 0:
            raise ValueError("exploration_param must be finite and non-negative")

    def select_arm(self) -> str:
        for arm in self.arms:
            if self.counts[arm] == 0:
                return arm
        total = sum(self.counts.values())
        return max(self.arms, key=lambda arm: self.rewards[arm] + self.c * math.sqrt(
            math.log(total) / self.counts[arm]
        ))
