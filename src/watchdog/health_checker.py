"""System health checker for pre-switch validation.

Verifies system stability before allowing scheduler switches.
Prevents switches during already-degraded conditions.
"""

import logging
from src.core.models import SystemMetrics

logger = logging.getLogger('adaptivesched.health')


class HealthChecker:
    """Validates system health before scheduler operations.
    
    Checks for conditions that would make a scheduler switch risky:
    - Extremely high CPU utilization (system already overloaded)
    - Very high context switch rate (system thrashing)
    - Extremely long runqueues (scheduler already struggling)
    """

    # Health thresholds (these are absolute safety limits, not SLO constraints)
    CRITICAL_CPU_THRESHOLD = 98.0        # %
    CRITICAL_CTX_SWITCH_RATE = 200000    # per second
    CRITICAL_RUNQUEUE_LENGTH = 20.0      # average depth
    CRITICAL_LATENCY_US = 50000          # microseconds

    def __init__(self):
        """Initialize the health checker."""
        self._last_health_status = True
        self._health_history: list = []

    def check(self, metrics: SystemMetrics) -> dict:
        """Perform a health check on current system state.
        
        Args:
            metrics: Current system metrics.
            
        Returns:
            Dictionary with:
                - healthy: True if system is healthy enough for switches
                - issues: List of detected issues
                - severity: "ok" | "warning" | "critical"
        """
        issues = []
        severity = "ok"
        
        # Check CPU utilization
        if metrics.cpu_utilization >= self.CRITICAL_CPU_THRESHOLD:
            issues.append(f"CPU utilization critical: {metrics.cpu_utilization:.1f}%")
            severity = "critical"
        elif metrics.cpu_utilization >= 90:
            issues.append(f"CPU utilization high: {metrics.cpu_utilization:.1f}%")
            if severity != "critical":
                severity = "warning"
        
        # Check context switch rate
        if metrics.context_switches >= self.CRITICAL_CTX_SWITCH_RATE:
            issues.append(f"Context switch rate critical: {metrics.context_switches}")
            severity = "critical"
        
        # Check runqueue length
        if metrics.runqueue_length >= self.CRITICAL_RUNQUEUE_LENGTH:
            issues.append(f"Runqueue length critical: {metrics.runqueue_length:.1f}")
            severity = "critical"
        
        # Check scheduling latency
        if metrics.scheduling_latency_us >= self.CRITICAL_LATENCY_US:
            issues.append(f"Scheduling latency critical: {metrics.scheduling_latency_us:.0f}μs")
            severity = "critical"
        
        healthy = severity != "critical"
        self._last_health_status = healthy
        
        result = {
            'healthy': healthy,
            'issues': issues,
            'severity': severity,
        }
        
        self._health_history.append(result)
        if len(self._health_history) > 100:
            self._health_history = self._health_history[-100:]
        
        if not healthy:
            logger.warning(f"[Health] System unhealthy: {', '.join(issues)}")
        
        return result

    @property
    def is_healthy(self) -> bool:
        """Get the last known health status."""
        return self._last_health_status
