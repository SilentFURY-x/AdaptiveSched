"""Mock bandit agent for demo and testing.

Simulates intelligent scheduler selection using a simple heuristic
that mimics real bandit behavior — exploring initially then converging
on the best scheduler.
"""

import random
import math
from src.interfaces.agent_interface import ISchedulerAgent
from src.core.models import SystemMetrics, AgentStatistics


class MockBanditAgent(ISchedulerAgent):
    """Simulated bandit agent that mimics UCB1 behavior.
    
    Uses a simplified selection mechanism that:
    1. Explores each arm at least once
    2. Then selects based on accumulated rewards with some randomness
    3. Gradually converges on the best-performing scheduler
    """

    def __init__(self, schedulers: list, algorithm: str = 'ucb1'):
        """Initialize the mock agent.
        
        Args:
            schedulers: List of available scheduler names.
            algorithm: Algorithm name (used for display, actual logic is simplified).
        """
        self._schedulers = schedulers
        self._algorithm = algorithm
        self._counts = {s: 0 for s in schedulers}
        self._rewards = {s: 0.0 for s in schedulers}
        self._total_pulls = 0
        
        # Pre-defined "true" qualities for deterministic convergence demo
        self._true_qualities = {
            'scx_rusty': 0.82,
            'scx_lavd': 0.75,
            'scx_bpfland': 0.78,
            'scx_simple': 0.45,
            'default': 0.60,
        }

    def select_scheduler(self, metrics: SystemMetrics) -> str:
        """Select next scheduler using simplified UCB1-like logic.
        
        Args:
            metrics: Current system metrics (used for realistic logging).
            
        Returns:
            Name of the selected scheduler.
        """
        self._total_pulls += 1
        
        # Phase 1: Explore — pull each arm at least once
        for scheduler in self._schedulers:
            if self._counts[scheduler] == 0:
                return scheduler
        
        # Phase 2: UCB1-like selection with noise
        scores = {}
        for scheduler in self._schedulers:
            exploitation = self._rewards[scheduler]
            exploration = math.sqrt(2 * math.log(self._total_pulls) / self._counts[scheduler])
            scores[scheduler] = exploitation + exploration
        
        # Add small random tiebreaking
        best = max(scores, key=lambda s: scores[s] + random.gauss(0, 0.01))
        return best

    def update_reward(self, scheduler: str, reward: float) -> None:
        """Update reward statistics for a scheduler.
        
        Uses incremental mean update for running average.
        
        Args:
            scheduler: Scheduler name.
            reward: Observed reward in [0, 1].
        """
        self._counts[scheduler] += 1
        n = self._counts[scheduler]
        # Incremental mean update
        self._rewards[scheduler] += (reward - self._rewards[scheduler]) / n

    def get_statistics(self) -> AgentStatistics:
        """Get current agent statistics.
        
        Returns:
            AgentStatistics with current pull counts and rewards.
        """
        return AgentStatistics(
            algorithm=f"Mock-{self._algorithm.upper()}",
            total_pulls=self._total_pulls,
            arm_counts=dict(self._counts),
            arm_rewards={k: round(v, 4) for k, v in self._rewards.items()},
        )
    
    def compute_reward(self, metrics: SystemMetrics) -> float:
        """Compute a mock reward from metrics.
        
        Uses a simplified version of the real reward function.
        
        Args:
            metrics: System metrics to compute reward from.
            
        Returns:
            Reward value in [0, 1].
        """
        # Normalize metrics
        norm_latency = min(1.0, metrics.scheduling_latency_us / 10000)
        norm_throughput = min(1.0, metrics.throughput_ops / 15000)
        norm_cpu = metrics.cpu_utilization / 100.0
        
        # Composite reward: lower latency better, higher throughput better
        reward = (
            0.4 * (1.0 - norm_latency) +
            0.35 * norm_throughput +
            0.25 * (1.0 - abs(norm_cpu - 0.6))  # Prefer ~60% utilization
        )
        
        return max(0.0, min(1.0, reward))
