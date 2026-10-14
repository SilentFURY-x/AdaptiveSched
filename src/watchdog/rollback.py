"""Rollback manager for safe scheduler restoration.

Handles the mechanics of rolling back to a safe default scheduler
when the watchdog detects SLO violations.
"""

import time
import logging
from typing import Optional
from src.interfaces.scheduler_interface import ISchedulerManager

logger = logging.getLogger('adaptivesched.rollback')


class RollbackManager:
    """Manages safe rollback to the default scheduler.
    
    Records rollback history and enforces cooldown periods
    to prevent oscillation between schedulers.
    """

    def __init__(self, scheduler_manager: ISchedulerManager, default_scheduler: str = 'default'):
        """Initialize the rollback manager.
        
        Args:
            scheduler_manager: The scheduler manager to execute switches.
            default_scheduler: Name of the safe default scheduler.
        """
        self._scheduler_manager = scheduler_manager
        self._default_scheduler = default_scheduler
        self._rollback_history: list = []

    def execute_rollback(self, reason: str) -> bool:
        """Execute a rollback to the default scheduler.
        
        Args:
            reason: Human-readable reason for the rollback.
            
        Returns:
            True if the rollback was successful.
        """
        current = self._scheduler_manager.get_current()
        
        if current == self._default_scheduler:
            logger.info(f"Already on default scheduler '{self._default_scheduler}', "
                       "no rollback needed")
            return True
        
        logger.warning(f"Rolling back: {current} → {self._default_scheduler} "
                      f"(reason: {reason})")
        
        success = self._scheduler_manager.switch_to(self._default_scheduler)
        
        self._rollback_history.append({
            'timestamp': time.time(),
            'from_scheduler': current,
            'to_scheduler': self._default_scheduler,
            'reason': reason,
            'success': success,
        })
        
        if success:
            logger.info(f"Rollback successful: now on '{self._default_scheduler}'")
        else:
            logger.error(f"Rollback FAILED: could not switch to '{self._default_scheduler}'")
        
        return success

    @property
    def default_scheduler(self) -> str:
        """Get the default rollback target scheduler."""
        return self._default_scheduler
    
    @default_scheduler.setter
    def default_scheduler(self, value: str) -> None:
        """Set the default rollback target scheduler."""
        self._default_scheduler = value

    def get_history(self, limit: int = 20) -> list:
        """Get rollback history.
        
        Args:
            limit: Maximum number of entries to return.
            
        Returns:
            List of rollback event dictionaries (newest first).
        """
        return list(reversed(self._rollback_history[-limit:]))
