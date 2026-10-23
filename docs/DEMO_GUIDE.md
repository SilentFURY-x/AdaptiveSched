# AdaptiveSched: Demonstration Guide

This guide provides step-by-step instructions for running and evaluating the AdaptiveSched autonomous CPU scheduler selection system.

The demonstration environment executes in mock mode by default, allowing complete inspection of online bandit learning, metrics collection, interactive operator controls, and safety watchdog rollback without modifying host kernel state.

Prerequisites:
- Python 3.10 or newer
- Virtual environment with dependencies from `requirements.txt` installed

---

## 1. Environment Setup

### 1.1 Install Dependencies

Activate your Python virtual environment and install the required dependencies:

```bash
pip install -r requirements.txt
```

### 1.2 Verify CLI Installation

Confirm that the CLI module executes correctly:

```bash
python -m src.cli.main --help
```

Expected output:
```text
usage: AdaptiveSched [-h] [--host HOST] [--port PORT]
                     {start,stop,status,switch,slo,history,dashboard} ...

AdaptiveSched: Self-Tuning CPU Scheduler Selection

positional arguments:
  {start,stop,status,switch,slo,history,dashboard}
    start               Start the AdaptiveSched agent
    stop                Stop the AdaptiveSched agent
    status              Show current system status
    switch              Manually switch scheduler
    slo                 Manage SLO profiles
    history             Show scheduler switch history
    dashboard           Launch the web dashboard

options:
  -h, --help            show this help message and exit
```

---

## 2. Launching the Demo

### Option A: Complete Demo Launcher (Recommended)

Run the unified demo launcher, which initializes the core engine in mock mode and starts the web dashboard server on `127.0.0.1:8080`:

```bash
python run_demo.py
```

Console banner:
```text
======================================================================
   AdaptiveSched -- Live Demonstration
   Autonomous CPU Scheduler Selection via Online Bandit Learning
   Arjun Tyagi (24BCE0605) & Aritra Ghosh (24BCE0598)
======================================================================

[Demo] Starting AdaptiveSched engine in MOCK mode...
[Demo] Algorithm: UCB1 | SLO Profile: balanced | Interval: 5.0s
[Demo] Engine successfully started.
[Demo] Starting web dashboard at http://127.0.0.1:8080 ...
```

Open a web browser and navigate to:
```text
http://127.0.0.1:8080
```

---

## 3. Step-by-Step Walkthrough

### Step 1: Real-Time CLI Status Inspection

Open a second terminal window while the engine is running and inspect system status:

```bash
python -m src.cli.main status
```

Expected output:
```text
         System Overview          
+------------------+-------------+
| Property         | Value       |
+------------------+-------------+
| Status           | RUNNING     |
| Agent State      | ACTIVE      |
| Operating Mode   | MOCK        |
| Bandit Algorithm | UCB1        |
| Active Scheduler | scx_rusty   |
| Engine Uptime    | 00:01:15    |
| Decision Cycles  | 15          |
+------------------+-------------+
                            Live System Metrics                             
+----------------------+-----------------+---------------------------------+
| Metric               | Current Reading | Target / Notes                  |
+----------------------+-----------------+---------------------------------+
| CPU Utilization      | 42.1 %          | Host CPU utilization            |
| P99 Workload Latency | 2180 us         | Simulated workload tail latency |
| Throughput           | 10850 ops/s     | Simulated completed operations  |
| Context Switch Rate  | 35200 /s        | System-wide                     |
| Runnable Tasks       | 2.50            | Instantaneous procfs count      |
+----------------------+-----------------+---------------------------------+
    SLO Watchdog & Safety Governance     
+------------------------+--------------+
| Watchdog Field         | Status       |
+------------------------+--------------+
| Active Profile         | balanced     |
| SLO Compliance         | 68.5 %       |
| Watchdog State         | MONITORING   |
| Consecutive Violations | 0 / 3        |
| Total Rollbacks        | 0            |
+------------------------+--------------+
```

Key points to observe:
- Operating Mode indicates MOCK mode.
- Active Scheduler shows the arm selected by the UCB1 bandit algorithm.
- Watchdog State confirms the safety module is in MONITORING state with zero violations.

---

### Step 2: Web Dashboard Telemetry and Policy Learning

Observe the running web dashboard (`http://127.0.0.1:8080`):

1. **Header Bar**: Displays MOCK MODE, the active algorithm (ALGO: UCB1), AGENT ACTIVE state, uptime counter, cycle counter, Pause/Resume button, and Simulate Spike button.
2. **KPI Overview Cards**:
   - Card 1: Active Scheduler and list of candidate schedulers (`scx_rusty`, `scx_lavd`, `scx_bpfland`, `scx_simple`, `default`).
   - Card 2: CPU Utilization across 8 simulated cores.
   - Card 3: Workload Latency (P99) comparing measured latency to the active SLO threshold (e.g., Target: < 10000 us).
   - Card 4: System Throughput (ops/sec) and context switch rate.
   - Card 5: SLO Compliance score and current watchdog state.
3. **Performance Charts**:
   - P99 Workload Latency vs. SLO Ceiling line chart.
   - CPU Utilization and Workload Throughput dual-axis line chart.
   - Policy Learning bar chart displaying the estimated reward and selection count ($n$) for each scheduler arm.

---

### Step 3: Triggering SLO Violation and Automated Rollback

This step demonstrates the core safety mechanism of AdaptiveSched.

In Terminal 2, manually force the system to switch to `scx_simple` (a baseline FIFO scheduler unsuited for complex workloads):

```bash
python -m src.cli.main switch scx_simple
```

Alternatively, click the **Simulate 15s workload spike** button on the web dashboard.

**Observable sequence of events**:
1. The Active Scheduler updates to `scx_simple`.
2. The watchdog enters `GRACE_PERIOD` (5 seconds) to allow transient switching effects to settle.
3. Once monitoring resumes, simulated latency spikes from ~2,000 us to over 14,000 us, breaching the 10,000 us SLO ceiling.
4. The latency badge changes to `VIOLATION` in red.
5. In the Watchdog State Machine indicator, the state transitions from `MONITOR` to `VIOLATION`. The consecutive violation counter increments: 1/3, 2/3, 3/3.
6. Upon reaching the threshold (3 consecutive violations), the watchdog automatically triggers an **emergency rollback**:
   - The active scheduler immediately switches back to `default` (CFS/EEVDF).
   - The watchdog transitions into `COOLDOWN` (60 seconds) to prevent the bandit agent from re-selecting the offending arm.
   - The latency chart drops back into the compliant zone below 4,000 us.

---

### Step 4: Audit History Verification

Inspect the audit log of all decisions, manual overrides, and automated rollbacks:

```bash
python -m src.cli.main history
```

Expected output:
```text
=================================================================
 Scheduler Switch History (Recent events)
=================================================================
 [23:33:08] scx_simple --> default      (Reason: slo_rollback, Result: rollback)
 [23:32:53] scx_bpfland --> scx_simple  (Reason: manual,       Result: ok)
 [23:32:48] scx_lavd --> scx_bpfland    (Reason: agent_select, Result: ok)
 [23:32:43] scx_rusty --> scx_lavd      (Reason: agent_select, Result: ok)
 [23:32:38] default --> scx_rusty       (Reason: agent_select, Result: ok)

=================================================================
 Watchdog Events & Rollback Log
=================================================================
 [23:34:08] [INFO     ] Cooldown period ended
 [23:33:08] [INFO     ] Rollback successful
 [23:33:08] [INFO     ] SLO rollback: 3 consecutive violations (p99_latency_us)
 [23:33:08] [INFO     ] Violation #3: p99_latency_us
 [23:33:03] [INFO     ] Violation #2: p99_latency_us
 [23:32:58] [INFO     ] Violation #1: p99_latency_us
 [23:32:58] [INFO     ] Grace period ended, monitoring started
 [23:32:53] [INFO     ] Grace period started (5.0s)
=================================================================
```

---

### Step 5: Dynamic SLO Profile Reconfiguration

AdaptiveSched supports dynamic switching between pre-configured SLO profiles:

1. List available profiles:
   ```bash
   python -m src.cli.main slo --list
   ```

2. Switch to the `interactive` profile (tailored for ultra-low latency, P99 < 3,000 us):
   ```bash
   python -m src.cli.main slo --set interactive
   ```

3. Switch to the `throughput` profile (tailored for batch processing, CPU utilization up to 98%):
   ```bash
   python -m src.cli.main slo --set throughput
   ```

4. Return to the `balanced` general-purpose profile:
   ```bash
   python -m src.cli.main slo --set balanced
   ```

---

### Step 6: Automated Test Suite Verification

Execute the test suite to verify all core invariants:

```bash
python -m unittest discover -v -s tests
```

Expected output:
```text
test_all_algorithms_select_known_arms_and_update (test_core.BanditTests.test_all_algorithms_select_known_arms_and_update) ... ok
test_benchmark_quantiles (test_core.BanditTests.test_benchmark_quantiles) ... ok
test_reward_is_bounded_and_rejects_bad_metrics (test_core.BanditTests.test_reward_is_bounded_and_rejects_bad_metrics) ... ok
test_configuration_and_mock_profile_keep_p99_semantics (test_core.EngineAndApiTests.test_configuration_and_mock_profile_keep_p99_semantics) ... ok
test_invalid_mode_is_rejected (test_core.EngineAndApiTests.test_invalid_mode_is_rejected) ... ok
test_mock_engine_api_and_stop_route (test_core.EngineAndApiTests.test_mock_engine_api_and_stop_route) ... ok
test_health_checker_uses_per_second_context_switch_rate (test_core.MockAndHealthTests.test_health_checker_uses_per_second_context_switch_rate) ... ok
test_mock_scheduler_and_metrics_lifecycle (test_core.MockAndHealthTests.test_mock_scheduler_and_metrics_lifecycle) ... ok
test_delta_metrics_and_explicit_unavailable_fields (test_core.ProcMetricsTests.test_delta_metrics_and_explicit_unavailable_fields) ... ok
test_missing_proc_data_fails_with_clear_error (test_core.ProcMetricsTests.test_missing_proc_data_fails_with_clear_error) ... ok
test_rolling_window_uses_worst_sample_and_rolls_back_at_threshold (test_core.SLOTests.test_rolling_window_uses_worst_sample_and_rolls_back_at_threshold) ... ok
test_unavailable_field_does_not_cause_a_false_slo_pass (test_core.SLOTests.test_unavailable_field_does_not_cause_a_false_slo_pass) ... ok
test_unknown_constraints_are_not_reported_as_good_data (test_core.SLOTests.test_unknown_constraints_are_not_reported_as_good_data) ... ok

----------------------------------------------------------------------
Ran 13 tests in 0.106s

OK
```

---

## 4. Troubleshooting

| Issue | Resolution |
|-------|------------|
| `ModuleNotFoundError: No module named 'flask'` | Activate the project virtual environment where dependencies are installed. |
| `Address already in use: 8080` | Stop the existing instance or launch with `--port 8081`. |
| CLI commands return `Unable to connect` | Ensure `run_demo.py` is actively running in another terminal. |
