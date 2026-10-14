"""Mock metrics collector for demo and testing.

Generates realistic simulated system metrics without requiring
access to the Linux kernel. Each scheduler has different simulated
performance characteristics, making the demo visually compelling.
"""

import random
import time
import math
from src.interfaces.metrics_interface import IMetricsCollector
from src.core.models import SystemMetrics


# Simulated performance profiles per scheduler
# Each scheduler has a baseline + noise profile for each metric
SCHEDULER_PROFILES = {
    'scx_rusty': {
        'cpu_utilization': (55, 8),        # (mean, stddev)
        'scheduling_latency_us': (800, 200),
        'context_switches': (35000, 5000),
        'ipc': (2.1, 0.3),
        'cache_miss_rate': (0.05, 0.02),
        'runqueue_length': (2.5, 0.8),
        'throughput_ops': (12000, 1500),
        'p99_latency_us': (2500, 500),
    },
    'scx_lavd': {
        'cpu_utilization': (48, 6),
        'scheduling_latency_us': (500, 150),
        'context_switches': (42000, 6000),
        'ipc': (1.9, 0.25),
        'cache_miss_rate': (0.04, 0.015),
        'runqueue_length': (1.8, 0.5),
        'throughput_ops': (10000, 1200),
        'p99_latency_us': (1800, 400),
    },
    'scx_bpfland': {
        'cpu_utilization': (52, 7),
        'scheduling_latency_us': (650, 180),
        'context_switches': (38000, 4500),
        'ipc': (2.0, 0.28),
        'cache_miss_rate': (0.045, 0.018),
        'runqueue_length': (2.2, 0.7),
        'throughput_ops': (11500, 1300),
        'p99_latency_us': (2200, 450),
    },
    'scx_simple': {
        'cpu_utilization': (72, 12),
        'scheduling_latency_us': (3500, 800),
        'context_switches': (25000, 8000),
        'ipc': (1.3, 0.4),
        'cache_miss_rate': (0.12, 0.04),
        'runqueue_length': (5.5, 1.5),
        'throughput_ops': (6000, 2000),
        'p99_latency_us': (12000, 3000),
    },
    'default': {
        'cpu_utilization': (60, 10),
        'scheduling_latency_us': (1500, 400),
        'context_switches': (30000, 6000),
        'ipc': (1.7, 0.3),
        'cache_miss_rate': (0.07, 0.025),
        'runqueue_length': (3.2, 1.0),
        'throughput_ops': (9000, 1500),
        'p99_latency_us': (4500, 1000),
    },
}


class MockMetricsCollector(IMetricsCollector):
    """Generates realistic mock system metrics for demo purposes.
    
    Produces metrics that vary over time with:
    - Gaussian noise around scheduler-specific baselines
    - Sinusoidal workload patterns (simulating periodic load changes)
    - Occasional spikes (simulating workload bursts)
    - Scheduler-dependent performance characteristics
    """

    def __init__(self, schedulers: list = None):
        """Initialize the mock collector.
        
        Args:
            schedulers: List of scheduler names to simulate profiles for.
        """
        self._active_scheduler = 'default'
        self._start_time = time.time()
        self._running = False
        self._spike_active = False
        self._spike_start = 0
        self._spike_duration = 0

    def set_active_scheduler(self, scheduler: str) -> None:
        """Set which scheduler's profile to use for metrics generation.
        
        Args:
            scheduler: Name of the active scheduler.
        """
        self._active_scheduler = scheduler

    def trigger_spike(self, duration: float = 20.0) -> None:
        """Trigger a simulated performance spike (degradation).
        
        Useful for demonstrating SLO violations and rollback.
        
        Args:
            duration: How long the spike lasts in seconds.
        """
        self._spike_active = True
        self._spike_start = time.time()
        self._spike_duration = duration

    def collect(self) -> SystemMetrics:
        """Generate a realistic mock metrics sample.
        
        Returns:
            SystemMetrics with simulated values based on current scheduler
            and workload conditions.
        """
        profile = SCHEDULER_PROFILES.get(
            self._active_scheduler, SCHEDULER_PROFILES['default']
        )
        
        elapsed = time.time() - self._start_time
        
        # Sinusoidal workload modulation (period ~60s)
        workload_factor = 1.0 + 0.15 * math.sin(2 * math.pi * elapsed / 60)
        
        # Check if spike is active
        if self._spike_active:
            if time.time() - self._spike_start > self._spike_duration:
                self._spike_active = False
            else:
                workload_factor *= 2.5  # Significant performance degradation
        
        # Generate metrics with noise
        def _sample(key: str) -> float:
            mean, stddev = profile[key]
            value = random.gauss(mean * workload_factor, stddev)
            return max(0, value)
        
        return SystemMetrics(
            timestamp=time.time(),
            cpu_utilization=min(100, _sample('cpu_utilization')),
            context_switches=int(_sample('context_switches')),
            scheduling_latency_us=_sample('scheduling_latency_us'),
            ipc=max(0.1, _sample('ipc')),
            cache_miss_rate=min(1.0, max(0, _sample('cache_miss_rate'))),
            runqueue_length=max(0, _sample('runqueue_length')),
            throughput_ops=max(0, _sample('throughput_ops')),
            p99_latency_us=_sample('p99_latency_us'),
        )

    def start(self) -> None:
        """Start the mock collector."""
        self._running = True
        self._start_time = time.time()

    def stop(self) -> None:
        """Stop the mock collector."""
        self._running = False
