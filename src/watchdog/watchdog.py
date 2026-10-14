"""SLO Watchdog — Post-switch monitoring and violation detection.

The watchdog operates as a state machine that monitors system metrics
after each scheduler switch, detects SLO violations, and triggers
automatic rollback when performance degrades beyond acceptable thresholds.

State Machine:
    IDLE → GRACE_PERIOD → MONITORING ↔ VIOLATION_DETECTED → COOLDOWN → IDLE
                                     ↗ (rollback triggered)
"""

import time
import logging
from typing import Optional, Callable
from src.core.models import SystemMetrics, SLOViolation, WatchdogState
from src.watchdog.slo_config import SLOProfile

logger = logging.getLogger('adaptivesched.watchdog')


class SLOWatchdog:
    """SLO-aware watchdog with automatic rollback.
    
    Monitors post-switch performance against user-defined SLO constraints.
    If consecutive violations exceed the threshold, triggers rollback to
    the safe default scheduler.
    
    Attributes:
        state: Current watchdog state.
        slo_profile: Active SLO profile with constraints.
        consecutive_violations: Count of consecutive constraint violations.
    """

    # Watchdog states
    STATE_IDLE = "IDLE"
    STATE_GRACE_PERIOD = "GRACE_PERIOD"
    STATE_MONITORING = "MONITORING"
    STATE_VIOLATION_DETECTED = "VIOLATION_DETECTED"
    STATE_COOLDOWN = "COOLDOWN"

    def __init__(self, slo_profile: SLOProfile, rollback_callback: Optional[Callable] = None):
        """Initialize the SLO watchdog.
        
        Args:
            slo_profile: The SLO profile defining constraints and thresholds.
            rollback_callback: Function to call when rollback is triggered.
                              Signature: callback(reason: str) -> bool
        """
        self._profile = slo_profile
        self._rollback_callback = rollback_callback
        
        # State tracking
        self._state = self.STATE_IDLE
        self._consecutive_violations = 0
        self._total_violations = 0
        self._last_violation: Optional[SLOViolation] = None
        
        # Timing
        self._grace_start: float = 0
        self._cooldown_start: float = 0
        self._last_eval_time: float = 0
        
        # Compliance tracking
        self._compliance_score: float = 100.0
        self._compliance_history: list = []
        
        # Event log
        self._events: list = []

    @property
    def state(self) -> str:
        """Get the current watchdog state."""
        return self._state

    @property
    def compliance_score(self) -> float:
        """Get the current compliance score (0-100)."""
        return self._compliance_score

    @property
    def slo_profile(self) -> SLOProfile:
        """Get the active SLO profile."""
        return self._profile
    
    @slo_profile.setter
    def slo_profile(self, profile: SLOProfile) -> None:
        """Set a new SLO profile."""
        self._profile = profile
        self._log_event("profile_changed", f"SLO profile changed to '{profile.name}'")

    def on_scheduler_switch(self) -> None:
        """Called when a scheduler switch occurs.
        
        Transitions the watchdog from IDLE or MONITORING to GRACE_PERIOD,
        allowing the new scheduler time to stabilize before evaluation.
        """
        if self._state == self.STATE_COOLDOWN:
            logger.warning("Scheduler switch during cooldown — this should not happen")
            return
        
        self._state = self.STATE_GRACE_PERIOD
        self._grace_start = time.time()
        self._consecutive_violations = 0
        self._log_event("grace_period_started", 
                       f"Grace period started ({self._profile.grace_period_seconds}s)")
        logger.info(f"[Watchdog] Grace period started "
                   f"({self._profile.grace_period_seconds}s)")

    def evaluate(self, metrics: SystemMetrics, current_scheduler: str) -> dict:
        """Evaluate current metrics against SLO constraints.
        
        This should be called periodically (e.g., every 1 second).
        Handles state transitions automatically.
        
        Args:
            metrics: Current system metrics.
            current_scheduler: Currently active scheduler name.
            
        Returns:
            Dictionary with evaluation result:
                - state: Current watchdog state
                - compliance: Compliance score (0-100)
                - violations: List of current violations
                - action: None | "rollback"
        """
        now = time.time()
        result = {
            'state': self._state,
            'compliance': self._compliance_score,
            'violations': [],
            'action': None,
        }

        # Handle IDLE state
        if self._state == self.STATE_IDLE:
            # Just compute compliance without acting
            _, compliance, violations = self._profile.evaluate(metrics, current_scheduler)
            self._compliance_score = compliance
            result['compliance'] = compliance
            result['violations'] = [v.to_dict() for v in violations]
            return result

        # Handle GRACE_PERIOD state
        if self._state == self.STATE_GRACE_PERIOD:
            elapsed = now - self._grace_start
            remaining = self._profile.grace_period_seconds - elapsed
            
            if remaining <= 0:
                self._state = self.STATE_MONITORING
                self._log_event("monitoring_started", "Grace period ended, monitoring started")
                logger.info("[Watchdog] Grace period ended → MONITORING")
            else:
                result['state'] = self.STATE_GRACE_PERIOD
                return result

        # Handle COOLDOWN state
        if self._state == self.STATE_COOLDOWN:
            elapsed = now - self._cooldown_start
            remaining = self._profile.cooldown_seconds - elapsed
            
            if remaining <= 0:
                self._state = self.STATE_IDLE
                self._consecutive_violations = 0
                self._log_event("cooldown_ended", "Cooldown period ended")
                logger.info("[Watchdog] Cooldown ended → IDLE")
            
            result['state'] = self._state
            return result

        # Handle MONITORING / VIOLATION_DETECTED states
        if self._state in (self.STATE_MONITORING, self.STATE_VIOLATION_DETECTED):
            satisfied, compliance, violations = self._profile.evaluate(
                metrics, current_scheduler
            )
            self._compliance_score = compliance
            
            # Track compliance history (keep last 60 entries)
            self._compliance_history.append({
                'timestamp': now,
                'score': compliance,
            })
            if len(self._compliance_history) > 60:
                self._compliance_history = self._compliance_history[-60:]
            
            result['compliance'] = compliance
            result['violations'] = [v.to_dict() for v in violations]
            
            if not satisfied:
                self._consecutive_violations += 1
                self._total_violations += 1
                self._last_violation = violations[0] if violations else None
                self._state = self.STATE_VIOLATION_DETECTED
                
                self._log_event("violation_detected", 
                              f"Violation #{self._consecutive_violations}: "
                              f"{', '.join(v.constraint_name for v in violations)}")
                logger.warning(
                    f"[Watchdog] SLO violation #{self._consecutive_violations}/"
                    f"{self._profile.violation_threshold}: "
                    f"{', '.join(f'{v.constraint_name}={v.actual_value:.0f}>{v.constraint_max:.0f}' for v in violations)}"
                )
                
                # Check if we've exceeded the violation threshold
                if self._consecutive_violations >= self._profile.violation_threshold:
                    result['action'] = 'rollback'
                    self._trigger_rollback(violations)
            else:
                # Reset consecutive count on success
                if self._consecutive_violations > 0:
                    logger.info(f"[Watchdog] Violations cleared (was {self._consecutive_violations})")
                self._consecutive_violations = 0
                self._state = self.STATE_MONITORING
            
            result['state'] = self._state

        return result

    def _trigger_rollback(self, violations: list) -> None:
        """Execute automatic rollback to safe scheduler.
        
        Args:
            violations: List of SLOViolation objects that triggered the rollback.
        """
        reason = (
            f"SLO rollback: {self._consecutive_violations} consecutive violations "
            f"({', '.join(v.constraint_name for v in violations)})"
        )
        
        self._log_event("rollback_triggered", reason)
        logger.critical(f"[Watchdog] ROLLBACK TRIGGERED — {reason}")
        
        # Call the rollback callback
        if self._rollback_callback:
            success = self._rollback_callback(reason)
            if success:
                self._log_event("rollback_completed", "Rollback successful")
            else:
                self._log_event("rollback_failed", "Rollback callback returned False")
        
        # Enter cooldown
        self._state = self.STATE_COOLDOWN
        self._cooldown_start = time.time()
        self._consecutive_violations = 0
        
        logger.info(f"[Watchdog] Entering cooldown ({self._profile.cooldown_seconds}s)")

    def is_switch_allowed(self) -> bool:
        """Check if a scheduler switch is currently allowed.
        
        Returns:
            True if not in cooldown or grace period.
        """
        if self._state == self.STATE_COOLDOWN:
            elapsed = time.time() - self._cooldown_start
            if elapsed < self._profile.cooldown_seconds:
                return False
        return True

    def get_state(self) -> WatchdogState:
        """Get the full watchdog state for display.
        
        Returns:
            WatchdogState with all current values.
        """
        now = time.time()
        
        grace_remaining = 0.0
        if self._state == self.STATE_GRACE_PERIOD:
            grace_remaining = max(0, self._profile.grace_period_seconds - (now - self._grace_start))
        
        cooldown_remaining = 0.0
        if self._state == self.STATE_COOLDOWN:
            cooldown_remaining = max(0, self._profile.cooldown_seconds - (now - self._cooldown_start))
        
        return WatchdogState(
            state=self._state,
            consecutive_violations=self._consecutive_violations,
            total_violations=self._total_violations,
            last_violation=self._last_violation,
            grace_period_remaining=grace_remaining,
            cooldown_remaining=cooldown_remaining,
        )

    def get_events(self, limit: int = 50) -> list:
        """Get recent watchdog events.
        
        Args:
            limit: Maximum number of events to return.
            
        Returns:
            List of event dictionaries (newest first).
        """
        return list(reversed(self._events[-limit:]))

    def get_compliance_history(self) -> list:
        """Get recent compliance score history.
        
        Returns:
            List of {timestamp, score} dictionaries.
        """
        return list(self._compliance_history)

    def _log_event(self, event_type: str, message: str) -> None:
        """Log a watchdog event.
        
        Args:
            event_type: Type identifier for the event.
            message: Human-readable event description.
        """
        self._events.append({
            'timestamp': time.time(),
            'type': event_type,
            'message': message,
            'state': self._state,
        })
