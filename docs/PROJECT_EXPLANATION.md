# AdaptiveSched: Project Explanation

## 1. Introduction and Core Motivation

Modern operating systems face an increasingly heterogeneous computing landscape. On any given system, the processor concurrently executes workloads with fundamentally conflicting operational requirements:
- Latency-critical interactive applications (e.g., audio processing, 3D rendering, interactive desktop shells) require near-instantaneous thread dispatching and minimal scheduling delay.
- Compute-intensive batch processes (e.g., code compilation, scientific simulations, video encoding) require sustained throughput, maximized cache residency, and minimized context switching overhead.
- Network and database servers require high-frequency task switching with predictable bounded tail latencies.

Traditionally, general-purpose operating systems such as Linux have relied on a single, monolithic, in-kernel CPU scheduler (historically the Completely Fair Scheduler or CFS, and more recently the Earliest Eligible Virtual Deadline First or EEVDF scheduler). While CFS and EEVDF are engineered to provide acceptable baseline fairness across average desktop workloads, a single static policy cannot optimize performance across distinct, dynamically shifting workload phases.

With Linux kernel version 6.12, the Linux kernel community merged **sched_ext** (SCX), an extensible scheduling framework that allows user-space and kernel engineers to implement custom CPU schedulers using extended Berkeley Packet Filters (eBPF). Through sched_ext, different scheduling policies such as `scx_rusty` (multi-queue, cache-aware scheduler implemented in Rust), `scx_lavd` (latency-aware scheduler optimized for gaming and interactive workloads), `scx_bpfland` (interactive vruntime-based scheduler), and `scx_simple` (minimal baseline FIFO scheduler) can be loaded and replaced dynamically at runtime.

However, sched_ext provides only the low-level mechanism for executing schedulers; **it does not provide an autonomous decision-making policy to select which scheduler to run**. System administrators or end users are left to manually profile their workloads and statically load schedulers through trial and error.

Existing academic proposals attempting dynamic scheduler selection, such as ASA (Adaptive Scheduler Architecture), rely on offline machine learning classifiers trained on predefined synthetic benchmarks and static, machine-specific calibration lookup tables. These offline approaches fail to generalize across unseen workloads, require laborious hardware-specific retraining, and provide no safety guarantees if a poorly suited scheduler causes severe performance degradation.

AdaptiveSched solves this fundamental operating systems problem by formulating CPU scheduler selection as an **online non-stationary multi-armed bandit (MAB) problem** integrated with an **SLO-aware safety watchdog and automated rollback state machine**.

---

## 2. System Architecture

AdaptiveSched operates in user space as a lightweight control plane coordinating metrics collection, reinforcement learning, scheduler lifecycle management, and safety governance.

```
+-------------------------------------------------------------------------+
|                        AdaptiveSched User Space                         |
|                                                                         |
|  +-------------------+   +--------------------+   +------------------+  |
|  | Rich Terminal CLI |   | Flask REST API     |   | Web Dashboard    |  |
|  | (Status/Control)  |   | (JSON Endpoints)   |   | (Real-time UI)   |  |
|  +---------+---------+   +---------+----------+   +--------+---------+  |
|            |                       |                       |            |
|            +-----------------------+-----------------------+            |
|                                    |                                    |
|                                    v                                    |
|  +-------------------------------------------------------------------+  |
|  |                     AdaptiveSched Core Engine                     |  |
|  |                                                                   |  |
|  |  +---------------------+  +-----------------+  +---------------+  |  |
|  |  | Multi-Armed Bandit  |  | SLO Watchdog &  |  | Scheduler     |  |  |
|  |  | (UCB1 / TS / EG)    |  | Rollback Engine |  | Manager       |  |  |
|  |  +----------+----------+  +--------+--------+  +-------+-------+  |  |
|  |             ^                      ^                   |          |  |
|  |             |                      |                   |          |  |
|  |             |  +-------------------+                   |          |  |
|  |             |  |                                       |          |  |
|  |  +----------+--+-------------------+                   |          |  |
|  |  | Reward Computation Engine       |                   |          |  |
|  |  +------------------+--------------+                   |          |  |
|  |                     ^                                  |          |  |
|  |                     |                                  |          |  |
|  |  +------------------+--------------+                   |          |  |
|  |  | Metrics Collector Interface    |                   |          |  |
|  |  | (Linux procfs / Mock Collector) |                   |          |  |
|  |  +---------------------------------+                   |          |  |
|  +--------------------------------------------------------+----------+  |
|                                                           |             |
+-----------------------------------------------------------|-------------+
                                                            |
                                                            v
+-------------------------------------------------------------------------+
|                          Linux Kernel Subsystem                         |
|                                                                         |
|  +-----------------------------+       +-----------------------------+  |
|  | /proc Telemetry             |       | sched_ext (SCX Framework)   |  |
|  | (/proc/stat, /proc/loadavg) |       | (scx_rusty, scx_lavd, etc.) |  |
|  +-----------------------------+       +-----------------------------+  |
|                                                                         |
+-------------------------------------------------------------------------+
```

The system comprises five core modules:

1. **Metrics Collection Layer**: Continuously gathers system state indicators (CPU utilization, context switch rates, runnable run-queue task counts, scheduling latency, and throughput). Implemented as an abstract interface (`IMetricsCollector`) with two drop-in backends:
   - `ProcMetricsCollector`: Parses Linux `/proc/stat` and `/proc/loadavg` without external runtime dependencies.
   - `MockMetricsCollector`: Produces mathematically modeled, Gaussian-distributed workload responses with sinusoidal drift and controllable latency spikes for safe, reproducible demonstrations.

2. **Online Bandit Learning Engine**: Treats each sched_ext scheduling policy as an independent "arm" in a multi-armed bandit. Without requiring any pre-training or offline datasets, the bandit samples scheduling arms, receives composite reward feedback based on observed performance, and dynamically converges toward the policy that maximizes reward for the current workload pattern. Implemented algorithms include:
   - **UCB1 (Upper Confidence Bound)**: Balances exploitation of high-performing schedulers with exploration of less-tested policies using optimism in the face of uncertainty.
   - **Thompson Sampling**: Uses Bayesian posterior beta distributions to sample scheduler choices probabilistically.
   - **Epsilon-Greedy**: Selects the empirical best scheduler with probability $(1 - \epsilon)$ and explores random alternatives with probability $\epsilon$.

3. **Multi-Objective Reward Function**: Converts multi-dimensional runtime telemetry into a normalized scalar reward $R \in [0, 1]$. It optimizes three objectives simultaneously:
   - Minimizing tail latency ($P_{99}$ latency or run-queue scheduling delay).
   - Maximizing operational throughput.
   - Maintaining CPU utilization within an efficient operational envelope (penalizing idle waste and extreme saturation).

4. **SLO Watchdog and Automated Rollback**: Provides a mission-critical safety net. Because autonomous exploration could occasionally select a scheduler ill-suited to current workload demands, the watchdog monitors compliance against user-configured Service Level Objectives (e.g., Balanced, Interactive, or Throughput profiles). If performance degrades beyond threshold limits for consecutive evaluation cycles, the watchdog preempts the agent, forces an immediate rollback to the guaranteed-safe default kernel scheduler (CFS/EEVDF), and initiates a cooldown lockout to prevent regression.

5. **Management and Telemetry Interfaces**:
   - **Rich Terminal CLI**: Provides command-line status inspection, manual scheduler overrides, SLO profile reconfiguration, and switch audit history viewing.
   - **Web Control Room**: A single-page dashboard built with Flask, Vanilla CSS, and Chart.js featuring live metric streaming, real-time latency and throughput line charts, bandit arm reward estimates, watchdog state tracking, and interactive workload spike simulation.

---

## 3. Team Member Roles and Responsibilities

The AdaptiveSched project was designed, implemented, evaluated, and documented jointly by:

| Team Member | Core Roles and Responsibilities |
|-------------|---------------------------------|
| **Arjun Tyagi (24BCE0605)** | **Core Engine, Safety Governance, and User Interface**<br>- Architectural design and state synchronization in the central decision engine (`AdaptiveSchedEngine`).<br>- Design and implementation of the SLO watchdog, compliance scoring, and automated rollback state machine (`SLOWatchdog`).<br>- Implementation of the interactive Flask dashboard, REST API endpoints, Chart.js telemetry visualizations, and server-side hydration layer.<br>- Development of the Rich terminal command-line interface (`src.cli.main`).<br>- Configuration management, YAML SLO profile schemas, and end-to-end integration testing. |
| **Aritra Ghosh (24BCE0598)** | **Online Bandit Learning and Kernel Metrics Collection**<br>- Formulation and implementation of the multi-armed bandit algorithms (UCB1, Thompson Sampling, Epsilon-Greedy).<br>- Formulation and normalization of the multi-objective reward function (`RewardComputer`).<br>- Design and implementation of the metrics collection layer, including Linux procfs parsing (`ProcMetricsCollector`) and simulation modeling (`MockMetricsCollector`).<br>- Implementation of the Linux sched_ext process manager (`LinuxSchedulerManager`) and mock adapter (`MockSchedulerManager`).<br>- Design and implementation of the Linux CPU microbenchmark harness (`scripts/benchmark_linux.py`). |

---

## 4. Operational Workflow

The engine executes in a periodic control loop (configurable, defaulting to 5 seconds per cycle):

1. **Telemetry Sampling**: The metrics collector records instantaneous utilization, context switch counts, latency, and throughput over the sample interval.
2. **Reward Calculation**: If the engine made an active selection, the observed metrics are compared against historical baselines to compute a scalar reward.
3. **Safety and SLO Evaluation**: The watchdog passes the metric sample through a rolling window filter and evaluates it against active SLO constraints (e.g., latency ceiling, context switch ceiling, CPU saturation limit).
   - If an SLO violation is detected, a violation counter increments. If the counter reaches the violation threshold (e.g., 3 consecutive cycles), an immediate rollback to `default` is triggered, and a cooldown timer is engaged.
   - If the metrics meet all constraints, the violation counter resets to zero.
4. **Bandit Policy Selection**: If the watchdog is not in rollback or cooldown, the active bandit algorithm updates its arm statistics with the computed reward and selects the optimal arm for the next interval.
5. **Scheduler Switching**: If the selected arm differs from the active scheduler, the scheduler manager signals the kernel to switch policies, and the watchdog enters a brief grace period (5 seconds) to allow system state to stabilize before resuming compliance evaluation.
6. **Telemetry Publishing**: The decision, metrics, watchdog state, and audit record are appended to the circular history buffer and pushed to the REST API and live dashboard.

---

## 5. Verification and Validation

The implementation is verified through:
- **Comprehensive Unit Test Suite**: 13 automated unit tests covering bandit selection convergence, mathematical reward bounding, rolling window watchdog rollback, health monitoring, procfs delta metrics extraction, and Flask REST API lifecycle.
- **Repeatable Microbenchmarking**: A standalone benchmark runner (`scripts/benchmark_linux.py`) measuring CPU execution runtimes, context switch densities, and throughput across candidate schedulers.
- **Interactive Demonstrations**: Complete browser and CLI consoles allowing operators to observe policy convergence, manually force scheduler switches, change SLO profiles on the fly, and inject workload spikes to observe automated watchdog intervention.
