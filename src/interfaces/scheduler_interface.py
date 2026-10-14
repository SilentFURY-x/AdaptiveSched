"""Interface contract for scheduler management.

Abstracts the actual scheduler switching mechanism (mock or real sched_ext).
"""

from abc import ABC, abstractmethod
from typing import List


class ISchedulerManager(ABC):
    """Abstract interface for managing scheduler switches.
    
    Implementations:
        - MockSchedulerManager: Simulated switching for demo
        - ScxSchedulerManager: Real sched_ext interaction (future)
    """

    @abstractmethod
    def switch_to(self, scheduler_name: str) -> bool:
        """Switch the active scheduler.
        
        Args:
            scheduler_name: Name of the scheduler to activate.
            
        Returns:
            True if the switch was successful, False otherwise.
        """
        ...

    @abstractmethod
    def get_current(self) -> str:
        """Get the name of the currently active scheduler.
        
        Returns:
            Name of the current scheduler.
        """
        ...

    @abstractmethod
    def get_available(self) -> List[str]:
        """Get list of available schedulers.
        
        Returns:
            List of scheduler names that can be switched to.
        """
        ...
