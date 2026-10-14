"""Epsilon-greedy with exponential exploration decay."""

import random
from .bandit_base import BanditBase


class EpsilonGreedy(BanditBase):
    def __init__(self, arms, epsilon=0.3, decay=0.995, min_epsilon=0.01, rng=None):
        super().__init__(arms)
        self.epsilon_0 = float(epsilon)
        self.decay = float(decay)
        self.min_epsilon = float(min_epsilon)
        if not 0 <= self.epsilon_0 <= 1:
            raise ValueError("epsilon must be in [0, 1]")
        if not 0 < self.decay <= 1:
            raise ValueError("decay must be in (0, 1]")
        if not 0 <= self.min_epsilon <= self.epsilon_0:
            raise ValueError("min_epsilon must be in [0, epsilon]")
        self.epsilon = self.epsilon_0
        self.t = 0
        self._rng = rng or random

    def select_arm(self) -> str:
        self.t += 1
        self.epsilon = max(self.min_epsilon, self.epsilon_0 * self.decay ** (self.t - 1))
        if self._rng.random() < self.epsilon:
            return self._rng.choice(self.arms)
        best_reward = max(self.rewards.values())
        best_arms = [arm for arm in self.arms if self.rewards[arm] == best_reward]
        return self._rng.choice(best_arms)
