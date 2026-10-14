"""Bounded, configurable reward normalization for scheduler metrics."""

import math
from src.core.models import SystemMetrics


class RewardComputer:
    """Map observed latency, throughput and utilization into a [0, 1] reward."""

    DEFAULT_WEIGHTS = {"latency": 0.4, "throughput": 0.35, "utilization": 0.25}

    def __init__(self, weights=None, ranges=None, target_utilization=0.7):
        self.weights = dict(self.DEFAULT_WEIGHTS if weights is None else weights)
        if set(self.weights) != set(self.DEFAULT_WEIGHTS):
            raise ValueError("weights must define latency, throughput and utilization")
        if any(not math.isfinite(float(v)) or float(v) < 0 for v in self.weights.values()):
            raise ValueError("reward weights must be finite and non-negative")
        weight_sum = sum(float(v) for v in self.weights.values())
        if weight_sum <= 0:
            raise ValueError("at least one reward weight must be positive")
        self.weights = {k: float(v) / weight_sum for k, v in self.weights.items()}
        self.ranges = ranges or {
            "latency": (100.0, 50000.0), "throughput": (1000.0, 50000.0),
            "utilization": (0.0, 100.0),
        }
        for name, bounds in self.ranges.items():
            if len(bounds) != 2 or not all(math.isfinite(float(x)) for x in bounds) or bounds[1] <= bounds[0]:
                raise ValueError(f"invalid normalization range for {name}")
        self.target_utilization = float(target_utilization)
        if not 0 <= self.target_utilization <= 1:
            raise ValueError("target_utilization must be in [0, 1]")

    @staticmethod
    def _normalize(value, bounds):
        value = float(value)
        if not math.isfinite(value):
            return 0.0
        return min(1.0, max(0.0, (value - bounds[0]) / (bounds[1] - bounds[0])))

    def compute(self, metrics: SystemMetrics) -> float:
        # A zero latency/throughput is also used by collectors to mean “not
        # available”. Exclude unavailable dimensions and renormalize weights so
        # the agent never treats a missing latency reading as perfect latency.
        scores = {}
        if metrics.scheduling_latency_us > 0:
            scores["latency"] = 1.0 - self._normalize(metrics.scheduling_latency_us, self.ranges["latency"])
        if metrics.throughput_ops > 0:
            scores["throughput"] = self._normalize(metrics.throughput_ops, self.ranges["throughput"])
        if math.isfinite(metrics.cpu_utilization) and metrics.cpu_utilization >= 0:
            utilization = self._normalize(metrics.cpu_utilization, self.ranges["utilization"])
            scores["utilization"] = max(0.0, 1.0 - abs(utilization - self.target_utilization))
        active_weight = sum(self.weights[name] for name in scores)
        if active_weight <= 0:
            return 0.0
        reward = sum(self.weights[name] * score for name, score in scores.items()) / active_weight
        return min(1.0, max(0.0, reward))
