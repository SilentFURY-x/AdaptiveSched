"""SLO configuration parsing and management.

Loads SLO profiles from YAML files and provides constraint evaluation
against live system metrics.
"""

from typing import Dict, List, Optional, Tuple
import math
from src.core.models import SystemMetrics, SLOViolation


class SLOConstraint:
    """A single SLO constraint (e.g., 'p99_latency_us <= 5000')."""

    def __init__(self, name: str, max_value: float, weight: float = 1.0):
        """Initialize an SLO constraint.
        
        Args:
            name: Metric name (must match a field in SystemMetrics).
            max_value: Maximum allowed value before violation.
            weight: Importance weight for compliance scoring.
        """
        self.name = name
        self.max_value = float(max_value)
        self.weight = float(weight)
        if not math.isfinite(self.max_value) or self.max_value <= 0:
            raise ValueError(f"SLO maximum for {name} must be finite and positive")
        if not math.isfinite(self.weight) or self.weight < 0:
            raise ValueError(f"SLO weight for {name} must be finite and non-negative")

    def evaluate(self, metrics: SystemMetrics) -> Tuple[bool, float]:
        """Evaluate this constraint against current metrics.
        
        Args:
            metrics: Current system metrics.
            
        Returns:
            Tuple of (is_satisfied, actual_value).
        """
        # Map constraint name to metrics field
        metric_map = {
            'p99_latency_us': metrics.p99_latency_us,
            'scheduling_latency_us': metrics.scheduling_latency_us,
            'context_switch_rate': metrics.context_switch_rate,
            'cpu_utilization': metrics.cpu_utilization,
            'cache_miss_rate': metrics.cache_miss_rate,
            'runqueue_length': metrics.runqueue_length,
        }
        
        if self.name in metrics.unavailable_metrics or self.name not in metric_map:
            return False, math.nan
        actual = metric_map[self.name]
        return (actual <= self.max_value, actual)

    def __repr__(self) -> str:
        return f"SLOConstraint({self.name} <= {self.max_value}, weight={self.weight})"


class SLOProfile:
    """A complete SLO profile with multiple constraints and evaluation parameters."""

    def __init__(self, profile_data: Dict):
        """Initialize from a profile dictionary (loaded from YAML).
        
        Args:
            profile_data: Dictionary with profile configuration.
        """
        self.name: str = profile_data.get('profile', 'unknown')
        self.constraints: List[SLOConstraint] = []
        
        # Parse constraints
        constraints_data = profile_data.get('constraints', {})
        supported = {'p99_latency_us', 'scheduling_latency_us', 'context_switch_rate',
                     'cpu_utilization', 'cache_miss_rate', 'runqueue_length'}
        for metric_name, config in constraints_data.items():
            if metric_name not in supported:
                raise ValueError(f"Unsupported SLO metric: {metric_name!r}")
            self.constraints.append(SLOConstraint(
                name=metric_name,
                max_value=config.get('max', float('inf')),
                weight=config.get('weight', 1.0),
            ))
        
        # Evaluation parameters
        eval_config = profile_data.get('evaluation', {})
        self.window_seconds = float(eval_config.get('window_seconds', 10))
        self.violation_threshold = int(eval_config.get('violation_threshold', 3))
        self.grace_period_seconds = float(eval_config.get('grace_period_seconds', 5))
        
        # Rollback parameters
        rollback_config = profile_data.get('rollback', {})
        self.rollback_target: str = rollback_config.get('target', 'default')
        self.cooldown_seconds = float(rollback_config.get('cooldown_seconds', 60))
        if not self.constraints or not any(c.weight > 0 for c in self.constraints):
            raise ValueError("SLO profile must define constraints with at least one positive weight")
        if (not math.isfinite(self.window_seconds) or self.window_seconds <= 0
                or self.violation_threshold < 1):
            raise ValueError("SLO window_seconds and violation_threshold must be positive and finite")
        if (not math.isfinite(self.grace_period_seconds) or self.grace_period_seconds < 0
                or not math.isfinite(self.cooldown_seconds) or self.cooldown_seconds < 0):
            raise ValueError("SLO grace and cooldown durations must be finite and non-negative")

    def evaluate(self, metrics: SystemMetrics, scheduler: str) -> Tuple[bool, float, List[SLOViolation]]:
        """Evaluate all constraints against current metrics.
        
        Args:
            metrics: Current system metrics.
            scheduler: Currently active scheduler (for violation records).
            
        Returns:
            Tuple of:
                - all_satisfied: True if all constraints are met
                - compliance_score: Weighted compliance score (0-100)
                - violations: List of violated constraints
        """
        violations = []
        weighted_score = 0.0
        available_weight = 0.0
        
        for constraint in self.constraints:
            satisfied, actual = constraint.evaluate(metrics)
            if math.isnan(actual):
                continue
            available_weight += constraint.weight
            
            if satisfied:
                # Score based on how far under the limit we are
                margin = 1.0 - (actual / constraint.max_value) if constraint.max_value > 0 else 1.0
                weighted_score += constraint.weight * max(0, margin)
            else:
                violations.append(SLOViolation(
                    constraint_name=constraint.name,
                    constraint_max=constraint.max_value,
                    actual_value=actual,
                    scheduler=scheduler,
                ))
        
        all_satisfied = len(violations) == 0 and available_weight > 0
        compliance = (weighted_score / available_weight * 100) if available_weight > 0 else 0.0
        
        return all_satisfied, compliance, violations

    def get_constraints_summary(self) -> List[Dict]:
        """Get a summary of all constraints for display.
        
        Returns:
            List of constraint dictionaries.
        """
        return [
            {
                'name': c.name,
                'max': c.max_value,
                'weight': c.weight,
            }
            for c in self.constraints
        ]

    def __repr__(self) -> str:
        return f"SLOProfile({self.name}, constraints={len(self.constraints)})"
