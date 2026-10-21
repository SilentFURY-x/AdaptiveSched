"""Linux system metrics collected from procfs.

This collector reports only measurements that procfs actually provides.
Workload throughput, hardware counters, and tail latency require a workload
probe or perf permissions and are explicitly marked unavailable here.
"""

import os
import time
from typing import Optional

from src.core.models import SystemMetrics
from src.interfaces.metrics_interface import IMetricsCollector


class ProcMetricsCollector(IMetricsCollector):
    """Collect CPU utilization, context-switch rate, and average run-queue wait."""

    UNAVAILABLE = ["ipc", "cache_miss_rate", "throughput_ops", "p99_latency_us"]

    def __init__(self, proc_root: str = "/proc", clock=time.monotonic):
        self.proc_root = proc_root
        self._clock = clock
        self._previous_cpu = None
        self._previous_ctxt = None
        self._previous_sched = None
        self._previous_time: Optional[float] = None

    def start(self) -> None:
        self._previous_cpu = self._read_cpu()
        self._previous_ctxt = self._read_ctxt()
        self._previous_sched = self._read_schedstat_optional()
        self._previous_time = self._clock()

    def stop(self) -> None:
        self._previous_cpu = self._previous_ctxt = self._previous_sched = None
        self._previous_time = None

    def collect(self) -> SystemMetrics:
        now = self._clock()
        cpu = self._read_cpu()
        ctxt = self._read_ctxt()
        sched = self._read_schedstat_optional()
        elapsed = now - self._previous_time if self._previous_time is not None else 0

        cpu_util = 0.0
        if self._previous_cpu is not None:
            total_delta = cpu[0] - self._previous_cpu[0]
            idle_delta = cpu[1] - self._previous_cpu[1]
            if total_delta > 0:
                cpu_util = 100.0 * (1.0 - idle_delta / total_delta)

        context_rate = 0.0
        context_count = 0
        if elapsed > 0 and self._previous_ctxt is not None:
            context_count = max(0, ctxt - self._previous_ctxt)
            context_rate = context_count / elapsed

        latency_us = 0.0
        runqueue = 0.0
        unavailable = list(self.UNAVAILABLE)
        if elapsed > 0 and self._previous_sched is not None and sched is not None:
            delay_delta = max(0, sched[0] - self._previous_sched[0])
            count_delta = max(0, sched[1] - self._previous_sched[1])
            if count_delta:
                latency_us = delay_delta / count_delta / 1000.0
            else:
                unavailable.append("scheduling_latency_us")
        else:
            unavailable.append("scheduling_latency_us")
        try:
            runqueue = self._read_runnable()
        except (OSError, ValueError, IndexError):
            unavailable.append("runqueue_length")

        self._previous_cpu, self._previous_ctxt = cpu, ctxt
        self._previous_sched, self._previous_time = sched, now
        return SystemMetrics(
            timestamp=time.time(), cpu_utilization=max(0.0, min(100.0, cpu_util)),
            context_switches=context_count, context_switch_rate=context_rate,
            scheduling_latency_us=latency_us, runqueue_length=runqueue,
            unavailable_metrics=unavailable,
        )

    def _read_cpu(self):
        path = os.path.join(self.proc_root, "stat")
        with open(path, encoding="ascii") as stream:
            line = next(line for line in stream if line.startswith("cpu "))
        values = [int(value) for value in line.split()[1:]]
        if len(values) < 4:
            raise ValueError("/proc/stat cpu row has fewer than four counters")
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        # guest and guest_nice are already included in user/nice.
        return sum(values[:8]), idle

    def _read_ctxt(self):
        with open(os.path.join(self.proc_root, "stat"), encoding="ascii") as stream:
            for line in stream:
                if line.startswith("ctxt "):
                    return int(line.split()[1])
        raise ValueError("/proc/stat has no ctxt counter")

    def _read_schedstat(self):
        """Return cumulative run delay (ns) and timeslices/counts across CPUs."""
        total_delay, total_count = 0, 0
        with open(os.path.join(self.proc_root, "schedstat"), encoding="ascii") as stream:
            for line in stream:
                fields = line.split()
                if fields and fields[0].startswith("cpu") and fields[0][3:].isdigit():
                    # Linux per-CPU schedstat: yld, sched, goidle, ... run_delay, pcount.
                    if len(fields) >= 10:
                        total_delay += int(fields[-2])
                        total_count += int(fields[-1])
        return (total_delay, total_count) if total_count else None

    def _read_schedstat_optional(self):
        try:
            return self._read_schedstat()
        except (OSError, ValueError):
            return None

    def _read_runnable(self):
        with open(os.path.join(self.proc_root, "loadavg"), encoding="ascii") as stream:
            fields = stream.read().split()
        running, _total = fields[3].split("/", 1)
        return float(running)
