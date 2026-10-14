"""Thompson sampling for rewards normalized to [0, 1]."""

import random
from .bandit_base import BanditBase


class ThompsonSampling(BanditBase):
    """Beta-Bernoulli Thompson sampling using fractional pseudo-counts."""

    def __init__(self, arms, rng=None):
        super().__init__(arms)
        self.alpha = {arm: 1.0 for arm in self.arms}
        self.beta_param = {arm: 1.0 for arm in self.arms}
        self._rng = rng or random

    def select_arm(self) -> str:
        samples = {arm: self._rng.betavariate(self.alpha[arm], self.beta_param[arm])
                   for arm in self.arms}
        return max(self.arms, key=samples.__getitem__)

    def update(self, arm: str, reward: float) -> None:
        reward = float(reward)
        super().update(arm, reward)
        reward = min(1.0, max(0.0, reward))
        self.alpha[arm] += reward
        self.beta_param[arm] += 1.0 - reward
