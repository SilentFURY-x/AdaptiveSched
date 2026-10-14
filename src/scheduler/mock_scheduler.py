"""Mock scheduler manager for demo and testing.

Simulates scheduler switching without requiring sched_ext kernel support.
Introduces realistic switch latency and maintains state.
"""

import time
import logging
from typing import List
from src.interfaces.scheduler_interface import ISchedulerManager

logger = logging.getLogger('adaptivesched.scheduler')


class MockSchedulerManager(ISchedulerManager):
    """Simulates scheduler switching for demo purposes.
    
    Maintains the current scheduler name and simulates the time
    it takes to load/unload sched_ext BPF programs.
    """

    def __init__(self, available: List[str] = None, default: str = 'default'):
        """Initialize mock scheduler manager.
        
        Args:
            available: List of available scheduler names.
            default: Name of the default scheduler.
        """
        self._available = available or [
            'scx_rusty', 'scx_lavd', 'scx_bpfland', 'scx_simple', 'default'
        ]
        self._current = default
        self._switch_count = 0

    def switch_to(self, scheduler_name: str) -> bool:
        """Switch to a different scheduler (simulated).
        
        Simulates the ~10-50ms latency of loading a sched_ext scheduler.
        
        Args:
            scheduler_name: Target scheduler name.
            
        Returns:
            True if switch was successful.
        """
        if scheduler_name not in self._available:
            logger.error(f"Scheduler '{scheduler_name}' not available. "
                        f"Available: {self._available}")
            return False

        if scheduler_name == self._current:
            logger.info(f"Already on scheduler '{scheduler_name}', no switch needed")
            return True

        old = self._current
        # Simulate switch latency (10-50ms in real sched_ext)
        time.sleep(0.02)
        self._current = scheduler_name
        self._switch_count += 1
        logger.info(f"Switched scheduler: {old} → {scheduler_name} "
                    f"(switch #{self._switch_count})")
        return True

    def get_current(self) -> str:
        """Get the currently active scheduler name.
        
        Returns:
            Current scheduler name.
        """
        return self._current

    def get_available(self) -> List[str]:
        """Get available schedulers.
        
        Returns:
            List of available scheduler names.
        """
        return list(self._available)
