"""Data models for AdaptiveSched.

Defines shared data structures used across all modules.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import time


@dataclass
class SystemMetrics:
    """System-level metrics collected from the kernel or mock source.
    
    All modules use this as the canonical representation of system state.
    """
    timestamp: float = field(default_factory=time.time)
    cpu_utilization: float = 0.0          # Percentage (0-100)
    context_switches: int = 0              # Count per collection interval
    scheduling_latency_us: float = 0.0     # Microseconds
    ipc: float = 0.0                       # Instructions per cycle
    cache_miss_rate: float = 0.0           # Ratio (0-1)
    runqueue_length: float = 0.0           # Average runqueue depth
    throughput_ops: float = 0.0            # Operations per second
    p99_latency_us: float = 0.0            # 99th percentile latency (μs)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp,
            'cpu_utilization': round(self.cpu_utilization, 2),
            'context_switches': self.context_switches,
            'scheduling_latency_us': round(self.scheduling_latency_us, 2),
            'ipc': round(self.ipc, 3),
            'cache_miss_rate': round(self.cache_miss_rate, 4),
            'runqueue_length': round(self.runqueue_length, 2),
            'throughput_ops': round(self.throughput_ops, 2),
            'p99_latency_us': round(self.p99_latency_us, 2),
        }


@dataclass
class AgentStatistics:
    """Statistics from the bandit agent."""
    algorithm: str = ""
    total_pulls: int = 0
    arm_counts: Dict[str, int] = field(default_factory=dict)
    arm_rewards: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'algorithm': self.algorithm,
            'total_pulls': self.total_pulls,
            'arm_counts': dict(self.arm_counts),
            'arm_rewards': {k: round(v, 4) for k, v in self.arm_rewards.items()},
        }


@dataclass
class SchedulerSwitchEvent:
    """Record of a scheduler switch event."""
    timestamp: float = field(default_factory=time.time)
    from_scheduler: str = ""
    to_scheduler: str = ""
    reason: str = ""                       # "agent_select" | "manual" | "slo_rollback"
    metrics_at_switch: Optional[SystemMetrics] = None
    result: str = "ok"                     # "ok" | "violation" | "rollback"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp,
            'from_scheduler': self.from_scheduler,
            'to_scheduler': self.to_scheduler,
            'reason': self.reason,
            'result': self.result,
            'metrics_at_switch': self.metrics_at_switch.to_dict() if self.metrics_at_switch else None,
        }


@dataclass
class SLOViolation:
    """Record of an SLO constraint violation."""
    timestamp: float = field(default_factory=time.time)
    constraint_name: str = ""
    constraint_max: float = 0.0
    actual_value: float = 0.0
    scheduler: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp,
            'constraint_name': self.constraint_name,
            'constraint_max': self.constraint_max,
            'actual_value': round(self.actual_value, 2),
            'scheduler': self.scheduler,
        }


@dataclass
class WatchdogState:
    """Current state of the SLO watchdog."""
    state: str = "IDLE"                    # IDLE | GRACE_PERIOD | MONITORING | VIOLATION_DETECTED | COOLDOWN
    consecutive_violations: int = 0
    total_violations: int = 0
    last_violation: Optional[SLOViolation] = None
    grace_period_remaining: float = 0.0
    cooldown_remaining: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'state': self.state,
            'consecutive_violations': self.consecutive_violations,
            'total_violations': self.total_violations,
            'last_violation': self.last_violation.to_dict() if self.last_violation else None,
            'grace_period_remaining': round(self.grace_period_remaining, 1),
            'cooldown_remaining': round(self.cooldown_remaining, 1),
        }
