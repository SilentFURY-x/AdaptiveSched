# AdaptiveSched — Demo Tutorial Guide

> **Purpose:** Step-by-step guide to running the AdaptiveSched demo for Review 2  
> **Prerequisites:** Python 3.10+, pip  
> **Time Required:** ~5 minutes to set up, then run the demo

---

## 1. Environment Setup

### 1.1 Install Dependencies

```bash
cd c:\PROJECTS\OS\AdaptiveSched
pip install -r requirements.txt
```

### 1.2 Verify Installation

```bash
python -m src.cli.main --help
```

**Expected Output:**
```
usage: AdaptiveSched [-h] {start,stop,status,switch,slo,history,dashboard} ...

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

optional arguments:
  -h, --help            show this help message and exit
```

---

## 2. Demo Walkthrough

### 2.1 Demo Scenario Overview

We'll demonstrate the following flow:
1. Start the agent in mock mode
2. Observe automatic scheduler selection
3. View real-time metrics on the dashboard
4. Trigger an SLO violation
5. Watch the automatic rollback
6. Review the event history

---

### 2.2 Step 1: Start the Agent

Open **Terminal 1** (the agent terminal):

```bash
cd c:\PROJECTS\OS\AdaptiveSched
python -m src.cli.main start --mode mock --algorithm ucb1
```

**What to show the reviewer:**
- The agent starts and prints initialization info
- It begins collecting metrics and selecting schedulers
- The log output shows scheduler decisions in real-time

**Expected output:**
```
[AdaptiveSched] Starting in MOCK mode...
[AdaptiveSched] Algorithm: UCB1
[AdaptiveSched] SLO Profile: balanced
[AdaptiveSched] Available schedulers: scx_rusty, scx_lavd, scx_bpfland, scx_simple, default
[AdaptiveSched] Agent loop started (interval: 5s)
[AdaptiveSched] ── Cycle 1 ──
[AdaptiveSched] Metrics: cpu=45.2%, latency=1234μs, throughput=8921 ops
[AdaptiveSched] Selected: scx_rusty (UCB1 score: 0.82)
[AdaptiveSched] Switching: default → scx_rusty
[AdaptiveSched] Watchdog: Grace period started (5s)
...
```

Let this run in the background.

---

### 2.3 Step 2: Check Status

Open **Terminal 2** (the control terminal):

```bash
python -m src.cli.main status
```

**What to show the reviewer:**
- Current active scheduler
- Agent statistics (selections per arm, average rewards)
- SLO compliance status
- Watchdog state

**Expected output:**
```
╔══════════════════════════════════════════════════════╗
║              AdaptiveSched Status                    ║
╠══════════════════════════════════════════════════════╣
║ Mode:              mock                              ║
║ Active Scheduler:  scx_rusty                         ║
║ Algorithm:         UCB1                              ║
║ SLO Profile:       balanced                          ║
║ Watchdog State:    MONITORING                        ║
║ SLO Compliance:    ✅ 98.2%                          ║
║ Uptime:            00:02:34                          ║
╠══════════════════════════════════════════════════════╣
║ Arm Statistics:                                      ║
║   scx_rusty:    pulls=5  avg_reward=0.78             ║
║   scx_lavd:     pulls=3  avg_reward=0.65             ║
║   scx_bpfland:  pulls=2  avg_reward=0.71             ║
║   scx_simple:   pulls=1  avg_reward=0.52             ║
║   default:      pulls=4  avg_reward=0.60             ║
╚══════════════════════════════════════════════════════╝
```

---

### 2.4 Step 3: Launch the Dashboard

```bash
python -m src.cli.main dashboard --port 8080
```

**Open browser to:** `http://localhost:8080`

**What to show the reviewer:**
- **Top bar:** Current scheduler name, mode, uptime
- **CPU Metrics chart:** Real-time line chart showing CPU utilization, scheduling latency
- **Throughput chart:** Operations per second over time
- **SLO Gauge:** Green/yellow/red compliance indicator
- **Scheduler History:** Timeline showing which scheduler was active when
- **Bandit Statistics:** Bar chart of arm pull counts and average rewards
- **Event Log:** Scrollable log of all decisions, switches, and violations

**Talk through each section:**
> "The dashboard updates every second. You can see the CPU utilization hovering around 45-65% as our mock simulates a realistic workload. The SLO gauge is green — we're well within our constraints."

---

### 2.5 Step 4: Trigger SLO Violation (Key Demo Moment)

In Terminal 2, simulate a workload spike that causes degradation:

```bash
python -m src.cli.main switch scx_simple --force
```

The mock mode simulates `scx_simple` as performing poorly under load.

**What to show the reviewer on the dashboard:**
1. **Scheduler indicator** changes to `scx_simple`
2. **Watchdog** enters grace period (5 seconds)
3. After grace period, **latency metrics spike** on the chart
4. **SLO gauge** transitions: Green → Yellow → Red
5. After 3 consecutive violations (~15 seconds):
   - **Automatic rollback** triggers
   - Scheduler switches back to `default`
   - SLO gauge returns to green
   - **Event log** shows the rollback with reason

**Talk through this:**
> "Watch what happens when we force a suboptimal scheduler. The watchdog gives it a 5-second grace period to stabilize. But then the latency spikes — you can see it on the chart. The SLO gauge turns yellow at the first violation, then red. After 3 consecutive violations, the watchdog triggers an automatic rollback. The system is now safe on the default scheduler, and the cooldown prevents the agent from immediately switching back."

---

### 2.6 Step 5: View History

```bash
python -m src.cli.main history
```

**Expected output:**
```
╔══════════════════════════════════════════════════════════════════════════╗
║                     Scheduler Switch History                            ║
╠══════════════════════════════════════════════════════════════════════════╣
║  #  │ Time     │ From          │ To            │ Reason      │ Result  ║
╠═════╪══════════╪═══════════════╪═══════════════╪═════════════╪═════════╣
║  1  │ 15:30:05 │ default       │ scx_rusty     │ UCB1 select │ ✅ OK   ║
║  2  │ 15:30:35 │ scx_rusty     │ scx_lavd      │ UCB1 select │ ✅ OK   ║
║  3  │ 15:31:05 │ scx_lavd      │ scx_rusty     │ UCB1 select │ ✅ OK   ║
║  4  │ 15:31:42 │ scx_rusty     │ scx_simple    │ Manual      │ ⚠️ VIOL ║
║  5  │ 15:31:57 │ scx_simple    │ default       │ SLO Rollback│ 🔄 ROLL ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

### 2.7 Step 6: Show SLO Configuration

```bash
python -m src.cli.main slo status
```

**Expected output:**
```
╔══════════════════════════════════════════════════════╗
║              SLO Profile: balanced                   ║
╠══════════════════════════════════════════════════════╣
║ Constraint          │ Max      │ Current  │ Status  ║
╠═════════════════════╪══════════╪══════════╪═════════╣
║ p99_latency_us      │ 10000    │ 2340     │ ✅ OK   ║
║ context_switch_rate  │ 80000    │ 45200    │ ✅ OK   ║
║ cpu_utilization      │ 95       │ 52.3     │ ✅ OK   ║
╠══════════════════════════════════════════════════════╣
║ Evaluation Window:   10s                             ║
║ Violation Threshold: 3 consecutive                   ║
║ Grace Period:        5s                               ║
║ Cooldown:            60s                              ║
╚══════════════════════════════════════════════════════╝
```

---

### 2.8 Step 7: Stop the Agent

```bash
python -m src.cli.main stop
```

---

## 3. Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| Dashboard doesn't open | Check if port 8080 is free, try `--port 8081` |
| Agent won't start | Check if another instance is running: `python -m src.cli.main status` |
| Mock data looks static | This is expected — mock mode generates realistic but synthetic data |

---

## 4. Reviewer Q&A Preparation

Keep these ready to show if asked:

- **Source code:** `src/` directory structure showing clean separation
- **Interface definitions:** `src/interfaces/` showing the contract between modules
- **SLO profiles:** `config/slo_profiles/` showing YAML configurations
- **Tests:** `tests/` directory with unit tests
- **PRD:** `docs/PRD.md` for the full product spec
