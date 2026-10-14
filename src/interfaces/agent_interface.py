"""Interface contract for scheduler selection agents.

Any agent (mock or real bandit) must implement this interface.
"""

from abc import ABC, abstractmethod
from src.core.models import SystemMetrics, AgentStatistics


class ISchedulerAgent(ABC):
    """Abstract interface for the scheduler selection agent.
    
    Implementations:
        - MockBanditAgent: Simulated agent for demo/testing
        - BanditAgent: Real MAB-based agent (Aritra)
    """

    @abstractmethod
    def select_scheduler(self, metrics: SystemMetrics) -> str:
        """Select the next scheduler based on current metrics.
        
        Args:
            metrics: Current system metrics.
            
        Returns:
            Name of the scheduler to switch to (e.g., 'scx_rusty').
        """
        ...

    @abstractmethod
    def update_reward(self, scheduler: str, reward: float) -> None:
        """Update the agent with the observed reward for a scheduler.
        
        Called after a scheduler has been running and its performance
        has been measured.
        
        Args:
            scheduler: Name of the scheduler that was evaluated.
            reward: Reward value in [0, 1].
        """
        ...

    @abstractmethod
    def get_statistics(self) -> AgentStatistics:
        """Get current agent statistics.
        
        Returns:
            AgentStatistics with pull counts and average rewards.
        """
        ...
