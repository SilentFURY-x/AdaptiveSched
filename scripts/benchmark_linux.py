"""Repeatable single-worker CPU benchmark across sched_ext scheduler arms.

Run as root on a Linux host configured for sched_ext. This measures the
benchmark workload's operation throughput and per-operation p99 latency; it
does not infer workload metrics from procfs.
"""

import argparse
import hashlib
import json
import os
import platform
import random
import shutil
import subprocess
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.metrics.proc_metrics import ProcMetricsCollector
from src.scheduler.linux_scheduler import LinuxSchedulerManager


def run_workload(duration_seconds: float, payload_bytes: int):
    payload = bytes((i % 251 for i in range(payload_bytes)))
    latencies = []
    deadline = time.perf_counter() + duration_seconds
    while time.perf_counter() < deadline:
        start = time.perf_counter_ns()
        hashlib.sha256(payload).digest()
        latencies.append((time.perf_counter_ns() - start) / 1000.0)
    return latencies


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((p / 100.0) * len(ordered) + 0.999999) - 1))
    return ordered[index]


def summarize_arm(arm, duration, sample_interval, payload_bytes, warmup):
    collector = ProcMetricsCollector()
    collector.start()
    if warmup > 0:
        run_workload(warmup, payload_bytes)
        collector.collect()

    samples = []
    latencies = []
    started = time.monotonic()
    deadline = started + duration
    while time.monotonic() < deadline:
        interval_start = time.monotonic()
        interval = min(sample_interval, max(0.01, deadline - interval_start))
        op_latencies = run_workload(interval, payload_bytes)
        metrics = collector.collect()
        latencies.extend(op_latencies)
        samples.append({
            "timestamp": metrics.timestamp,
            "cpu_utilization_pct": metrics.cpu_utilization,
            "context_switches_per_sec": metrics.context_switch_rate,
            "average_runqueue_wait_us": metrics.scheduling_latency_us,
            "runnable_tasks": metrics.runqueue_length,
            "operations": len(op_latencies),
            "operations_per_sec": len(op_latencies) / interval,
        })
    elapsed = time.monotonic() - started
    collector.stop()
    total_ops = sum(s["operations"] for s in samples)
    return {
        "scheduler": arm,
        "duration_seconds": elapsed,
        "sample_count": len(samples),
        "operation_count": total_ops,
        "operations_per_sec": total_ops / elapsed if elapsed else 0,
        "operation_latency_us_p50": percentile(latencies, 50),
        "operation_latency_us_p99": percentile(latencies, 99),
        "cpu_utilization_pct_mean": statistics.fmean(s["cpu_utilization_pct"] for s in samples) if samples else None,
        "context_switches_per_sec_mean": statistics.fmean(s["context_switches_per_sec"] for s in samples) if samples else None,
        "average_runqueue_wait_us_mean": statistics.fmean(s["average_runqueue_wait_us"] for s in samples) if samples else None,
        "samples": samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedulers", nargs="+", required=True,
                        help="Ordered schedulers to benchmark; include default as baseline")
    parser.add_argument("--duration", type=float, default=30,
                        help="Measured seconds per scheduler (default: 30)")
    parser.add_argument("--sample-interval", type=float, default=1,
                        help="Seconds per sample and workload batch (default: 1)")
    parser.add_argument("--warmup", type=float, default=3,
                        help="Unrecorded warm-up seconds per scheduler (default: 3)")
    parser.add_argument("--payload-bytes", type=int, default=4096,
                        help="SHA-256 payload size per operation (default: 4096)")
    parser.add_argument("--repeats", type=int, default=3,
                        help="Balanced benchmark rounds (default: 3)")
    parser.add_argument("--seed", type=int, default=1,
                        help="Seed for repeatable scheduler order (default: 1)")
    parser.add_argument("--output", type=Path, default=Path("benchmark-results.json"))
    args = parser.parse_args()

    if not sys.platform.startswith("linux"):
        parser.error("Linux is required")
    if os.geteuid() != 0:
        parser.error("Run as root to manage sched_ext schedulers")
    if args.duration <= 0 or args.sample_interval <= 0 or args.warmup < 0 or args.payload_bytes <= 0 or args.repeats < 1:
        parser.error("duration, sample interval, payload, and repeats must be positive; warmup cannot be negative")

    available = ["default", "scx_rusty", "scx_lavd", "scx_bpfland", "scx_simple"]
    manager = LinuxSchedulerManager(available, default="default")
    installed = set(manager.get_available())
    missing = [name for name in args.schedulers if name not in installed]
    if missing:
        parser.error(f"Unavailable schedulers: {', '.join(missing)}; installed choices: {', '.join(sorted(installed))}")
    if "default" not in args.schedulers:
        parser.error("Include 'default' as the baseline")

    trials = []
    try:
        rng = random.Random(args.seed)
        for repeat in range(args.repeats):
            remaining = [name for name in args.schedulers if name != "default"]
            rng.shuffle(remaining)
            order = ["default", *remaining]
            for scheduler in order:
                manager.switch_to(scheduler)
                # Let the selected scheduler settle before warm-up and measurement.
                time.sleep(1)
                trial = summarize_arm(scheduler, args.duration, args.sample_interval,
                                      args.payload_bytes, args.warmup)
                trial["repeat"] = repeat + 1
                trials.append(trial)
    finally:
        manager.stop()

    baseline = [trial for trial in trials if trial["scheduler"] == "default"]
    summaries = []
    for scheduler in args.schedulers:
        group = [trial for trial in trials if trial["scheduler"] == scheduler]
        throughput = statistics.median(t["operations_per_sec"] for t in group)
        latency = statistics.median(t["operation_latency_us_p99"] for t in group if t["operation_latency_us_p99"] is not None)
        baseline_throughput = statistics.median(t["operations_per_sec"] for t in baseline)
        baseline_latency = statistics.median(t["operation_latency_us_p99"] for t in baseline if t["operation_latency_us_p99"] is not None)
        summaries.append({
            "scheduler": scheduler,
            "repeat_count": len(group),
            "median_operations_per_sec": throughput,
            "throughput_change_pct_vs_default": ((throughput / baseline_throughput) - 1) * 100 if baseline_throughput else None,
            "median_operation_latency_us_p99": latency,
            "p99_latency_change_pct_vs_default": ((latency / baseline_latency) - 1) * 100 if baseline_latency else None,
        })

    payload = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": {
            "hostname": platform.node(),
            "kernel_release": platform.release(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_model": read_cpu_model(),
            "logical_cpus": os.cpu_count(),
            "python": platform.python_version(),
            "git_revision": git_revision(),
        },
        "method": {
            "workload": "single-worker repeated SHA-256 over a fixed-size payload",
            "payload_bytes": args.payload_bytes,
            "duration_seconds_per_scheduler": args.duration,
            "sample_interval_seconds": args.sample_interval,
            "warmup_seconds_per_scheduler": args.warmup,
            "scheduler_order": args.schedulers,
            "scheduler_binaries": {name: shutil.which(name) for name in args.schedulers if name != "default"},
            "repeats": args.repeats,
            "order_seed": args.seed,
            "throughput_and_p99_source": "benchmark operation timings; not procfs estimates",
        },
        "summary": summaries,
        "trials": trials,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(trials)} trials across {len(args.schedulers)} schedulers to {args.output.resolve()}")


def read_cpu_model():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as stream:
            for line in stream:
                if line.lower().startswith(("model name", "hardware")) and ":" in line:
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def git_revision():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


if __name__ == "__main__":
    main()
