# AdaptiveSched implementation status

**Status checked: October 21, 2026.** This file is the current implementation record. Older planning tables and Review 2 report text describe earlier milestones and should be read as historical material where they conflict with this page.

## What is implemented

- The mock demo remains available on Windows and Linux.
- UCB1, Thompson Sampling, epsilon-greedy, and bounded reward computation are implemented in Python.
- Mock and Linux procfs metrics collectors implement the same interface.
- A Linux scheduler manager can discover installed `scx_*` binaries, start one as a child process, check kernel activation through `/sys/kernel/sched_ext`, and stop only the child it owns. Stopping that process lets sched_ext return to the kernel fair scheduler. It refuses to manage an already active external sched_ext service.
- Real mode requires Linux and root privileges for scheduler management. Linux measurements currently include CPU utilization, context-switch rate, average run-queue wait derived from `/proc/schedstat`, and instantaneous runnable-task count from `/proc/loadavg`. In real mode, configured p99 SLO limits are applied to average run-queue wait and the API labels the constraint accordingly.
- Metrics that the procfs collector cannot provide (`p99_latency_us`, workload throughput, IPC, and cache-miss rate) are marked unavailable. The dashboard displays unavailable values as `—` and identifies average run-queue wait as distinct from p99 latency.
- SLO evaluation uses the worst available value in a rolling `window_seconds` interval. `violation_threshold` counts consecutive evaluations that breach the rolling-window SLO. Unsupported SLO metric names and invalid thresholds are rejected.
- The CLI `stop` command stops the engine and releases a scheduler process owned by this run. Dashboard control endpoints are served on loopback by default.
- A repeatable Linux CPU microbenchmark runner records per-scheduler raw procfs samples, workload operation throughput/p50/p99 latency, host/kernel metadata, repeated trials, and median comparisons against the `default` baseline.

## Current limits

- Linux real mode has not been exercised on a supported Linux host in this workspace. Kernel support, privileges, executable compatibility, recovery behavior, and real switching still need an end-to-end Linux run.
- The collector is Python procfs, not the planned C/perf collector or ctypes bridge. It cannot provide workload throughput or a p99 distribution. Add workload-specific probes before using those measures for policy evaluation.
- The manager requires foreground `scx_*` executables on `PATH`. It intentionally does not take over or terminate schedulers launched by system services. Install and validate the chosen schedulers for the target kernel before enabling real mode.
- A manager-started switch stops the owned scheduler before starting the next one, briefly returning scheduling to the kernel fair scheduler during the transition. “Zero-downtime switching” is not claimed.
- No controlled benchmark has been run. The repository paper remains a proposal/literature review, not an experimental results paper.
- The updated test suite passes: 13 tests via `python -m unittest discover -v`, using the declared requirements installed into a temporary project-local environment. Linux host integration tests and real sched_ext recovery have not been run.

## Run modes

### Mock demo

```bash
python -m pip install -r requirements.txt
python run_demo.py
```

All scheduler performance values in this mode are generated simulation data; the host scheduler is not changed.

### Linux real mode MVP

On a Linux kernel built with `CONFIG_SCHED_CLASS_EXT`, with the required `scx_*` binaries installed and run as root:

```bash
python -m pip install -r requirements.txt
sudo python -m src.cli.main start --mode real --algorithm ucb1 --slo balanced
```

The configured arms are filtered to installed binaries plus `default`. The default arm represents the kernel fair scheduler. Real mode refuses to start if an external sched_ext scheduler is already active. Stop with `python -m src.cli.main stop` from another terminal. Start with a test machine or VM and confirm a recovery path before using this MVP on a machine whose responsiveness matters.

## Run the Linux benchmark

With the Linux prerequisites above, choose only installed scheduler binaries and include `default`:

```bash
sudo python scripts/benchmark_linux.py --schedulers default scx_rusty scx_lavd --duration 30 --repeats 3 --output results/benchmark.json
```

The harness uses one CPU-bound SHA-256 worker and a fixed payload. It is a reproducible microbenchmark, not a substitute for application workloads such as builds, hackbench, or media encoding. Keep the generated JSON with the run's hardware/kernel setup when reporting results.

## Next validation milestone

1. Install supported sched_ext binaries and run mock-to-real setup on a Linux test host.
2. Verify activation, reported scheduler identity, switching, process exit, watchdog rollback, and clean shutdown.
3. Capture kernel version, configuration, privileges, binary versions, and logs.
4. Run and inspect the benchmark output, then add application workloads and repeated comparisons before making general performance claims.

