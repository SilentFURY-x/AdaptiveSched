"""Production bandit agent implementing the shared scheduler-agent contract."""

from src.interfaces.agent_interface import ISchedulerAgent
from src.core.models import AgentStatistics, SystemMetrics
from .epsilon_greedy import EpsilonGreedy
from .reward import RewardComputer
from .thompson_sampling import ThompsonSampling
from .ucb1 import UCB1


class BanditAgent(ISchedulerAgent):
    ALGORITHMS = {"ucb1": UCB1, "thompson": ThompsonSampling, "ts": ThompsonSampling,
                  "thompson_sampling": ThompsonSampling,
                  "epsilon_greedy": EpsilonGreedy, "epsilon-greedy": EpsilonGreedy,
                  "egreedy": EpsilonGreedy, "eg": EpsilonGreedy}

    def __init__(self, schedulers, algorithm="ucb1", reward_weights=None, reward_ranges=None):
        self.schedulers = list(schedulers)
        key = algorithm.lower()
        try:
            self.bandit = self.ALGORITHMS[key](self.schedulers)
        except KeyError as exc:
            raise ValueError(f"Unknown bandit algorithm: {algorithm!r}") from exc
        self.algorithm = key
        self.reward_computer = RewardComputer(reward_weights, reward_ranges)

    def select_scheduler(self, metrics: SystemMetrics) -> str:
        return self.bandit.select_arm()

    def update_reward(self, scheduler: str, reward: float) -> None:
        self.bandit.update(scheduler, reward)

    def compute_reward(self, metrics: SystemMetrics) -> float:
        return self.reward_computer.compute(metrics)

    def get_statistics(self) -> AgentStatistics:
        stats = self.bandit.get_statistics()
        return AgentStatistics(algorithm=type(self.bandit).__name__,
                               total_pulls=sum(stats["counts"].values()),
                               arm_counts=stats["counts"], arm_rewards=stats["avg_rewards"])
