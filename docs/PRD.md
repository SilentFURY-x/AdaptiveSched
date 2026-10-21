# AdaptiveSched — Product Requirements Document (PRD)

> **Project Title:** AdaptiveSched: Self-Tuning CPU Scheduler Selection via Online Bandit Learning and SLO-Aware Rollback  
> **Authors:** Arjun Tyagi (24BCE0605) & Aritra Ghosh (24BCE0598)  
> **Course:** Operating Systems — SCOPE Department, VIT Vellore  
> **Date:** October 14, 2026  
> **Version:** 2.0 (Review 2)

> **Implementation status update (October 21, 2026):** This PRD began as a plan. The current code status is in [MVP_STATUS.md](MVP_STATUS.md), which takes precedence over the historical plan and examples below. UCB1, Thompson Sampling, epsilon-greedy, and reward computation are implemented. The project now has a Python procfs collector and a Linux `scx_*` process manager, but Linux real mode has not yet been validated on a supported Linux host. The procfs MVP does not measure workload p99 latency or throughput; older p99 examples below refer to the mock/demo requirement unless stated otherwise.

---

## 1. Executive Summary

AdaptiveSched is a **user-space scheduling agent** for Linux that treats CPU scheduler selection as an **online multi-armed bandit (MAB) problem**. It leverages the `sched_ext` (SCX) framework in the Linux kernel to dynamically load and switch between different scheduling policies at runtime, without requiring offline training or hardware-specific calibration tables.

The system continuously monitors latency and throughput metrics, feeds them as reward signals to the bandit algorithm, and automatically selects the optimal scheduler. A **watchdog module** enforces user-defined **Service Level Objectives (SLOs)**, rolling back to a safe default scheduler upon detecting performance degradation.

### Key Differentiators
| Feature | Existing Systems (ASA, ghOSt) | AdaptiveSched |
|---------|-------------------------------|---------------|
| Training Required | Offline ML models | None (online learning) |
| Hardware Calibration | Machine-specific tables | Self-adapting |
| Safety Mechanism | None | SLO-aware watchdog + auto-rollback |
| Scheduler Framework | Custom / ghOSt | sched_ext (upstream Linux) |

---

## 2. Problem Statement

General-purpose operating systems use a **single, static CPU scheduler** (typically CFS/EEVDF in Linux). This one-size-fits-all approach fails when workloads change dynamically:

- **Gaming workloads** need low-latency, high-responsiveness → benefit from schedulers like `scx_lavd`
- **Compilation workloads** need high throughput → benefit from schedulers like `scx_rusty`
- **Network-heavy workloads** need fast context switching → benefit from schedulers like `scx_bpfland`

While `sched_ext` allows loading different schedulers at runtime, **no automated mechanism exists** to choose the right one. Users must manually benchmark and select.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER SPACE                                   │
│                                                                     │
│  ┌──────────────┐   ┌──────────────────┐   ┌────────────────────┐  │
│  │   CLI (TUI)  │   │   Web Dashboard  │   │   Config Manager   │  │
│  │   (Python)   │   │   (Python/Flask)  │   │     (Python)       │  │
│  └──────┬───────┘   └────────┬─────────┘   └────────┬───────────┘  │
│         │                    │                       │              │
│         ▼                    ▼                       ▼              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Core Engine (Python)                      │   │
│  │  ┌───────────────┐  ┌──────────────┐  ┌──────────────────┐  │   │
│  │  │  Bandit Agent  │  │ SLO Watchdog │  │ Scheduler Switch │  │   │
│  │  │  (UCB1/TS/EG) │  │ + Rollback   │  │    Manager       │  │   │
│  │  └───────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │   │
│  │          │                 │                    │            │   │
│  │          ▼                 ▼                    ▼            │   │
│  │  ┌─────────────────────────────────────────────────────┐    │   │
│  │  │            Metrics Collector Interface               │    │   │
│  │  │         (Python adapter over C library)              │    │   │
│  │  └─────────────────────┬───────────────────────────────┘    │   │
│  └────────────────────────┼────────────────────────────────────┘   │
│                           │                                        │
├───────────────────────────┼────────────────────────────────────────┤
│                    KERNEL BOUNDARY                                  │
│                           │                                        │
│  ┌────────────────────────▼───────────────────────────────────┐    │
│  │              Metrics Collection (C library)                 │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │    │
│  │  │ /proc    │  │ perf_    │  │ BPF/     │  │ sched_ext │  │    │
│  │  │ parser   │  │ event    │  │ tracing  │  │ loader    │  │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                     │
│                        KERNEL SPACE                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Module Breakdown

### 4.1 Module A — Bandit Agent + Metrics Collector (Aritra's Part)

#### 4.1.1 Metrics Collector (`src/metrics/`)

| Component | Language | Purpose |
|-----------|----------|---------|
| `proc_parser.c` | C | Parse `/proc/stat`, `/proc/schedstat`, `/proc/loadavg` |
| `perf_collector.c` | C | Use `perf_event_open()` for hardware counters (IPC, cache misses, context switches) |
| `metrics_bridge.py` | Python | `ctypes`/`cffi` bridge to expose C metrics to Python |
| `mock_metrics.py` | Python | Simulated metrics for demo/testing without root |

**Metrics Collected:**
```python
@dataclass
class SystemMetrics:
    timestamp: float
    cpu_utilization: float        # % from /proc/stat
    context_switches: int         # from /proc/stat
    scheduling_latency_us: float  # from schedstat or perf
    ipc: float                    # instructions per cycle (perf)
    cache_miss_rate: float        # L1/LLC misses (perf)
    runqueue_length: float        # from /proc/schedstat
    throughput_ops: float         # from workload-specific probes
    p99_latency_us: float         # tail latency
```

#### 4.1.2 Bandit Agent (`src/agent/`)

| Component | Language | Purpose |
|-----------|----------|---------|
| `bandit_base.py` | Python | Abstract base class for bandit algorithms |
| `ucb1.py` | Python | Upper Confidence Bound v1 algorithm |
| `thompson_sampling.py` | Python | Thompson Sampling with Beta priors |
| `epsilon_greedy.py` | Python | ε-greedy with decay |
| `reward.py` | Python | Reward computation from metrics |
| `agent_engine.py` | Python | Main agent loop: collect → compute reward → select arm → switch |

**Bandit Formulation:**
- **Arms**: Available sched_ext schedulers (`scx_rusty`, `scx_lavd`, `scx_bpfland`, `scx_simple`, `vscx_default`)
- **Reward**: Composite function of normalized latency (inverse), throughput, and CPU utilization
- **Algorithm**: UCB1 (default), configurable to TS or ε-greedy

```python
reward = (
    w_latency * (1 - norm_latency) +
    w_throughput * norm_throughput +
    w_utilization * norm_utilization
)
# where weights are user-configurable via SLO profile
```

---

### 4.2 Module B — SLO Watchdog + Dashboard + CLI (Arjun's Part)

#### 4.2.1 SLO Watchdog (`src/watchdog/`)

| Component | Language | Purpose |
|-----------|----------|---------|
| `slo_config.py` | Python | SLO definition and parsing |
| `watchdog.py` | Python | Post-switch monitoring and violation detection |
| `rollback.py` | Python | Safe rollback to default scheduler |
| `health_checker.py` | Python | System health verification |

**SLO Configuration:**
```yaml
# config/slo_profiles/interactive.yaml
profile: interactive
constraints:
  p99_latency_us:
    max: 5000
    weight: 0.6
  context_switch_rate:
    max: 50000
    weight: 0.2
  cpu_utilization:
    max: 90
    weight: 0.2
evaluation:
  window_seconds: 10
  violation_threshold: 3  # consecutive violations before rollback
  grace_period_seconds: 5  # time to let new scheduler stabilize
rollback:
  target: "default"  # or specific scheduler name
  cooldown_seconds: 60
```

**Watchdog Algorithm:**
1. After scheduler switch, start grace period (configurable, default 5s)
2. After grace period, begin SLO evaluation window
3. Collect metrics over window, compute SLO compliance score
4. If `violation_count >= threshold` → trigger rollback
5. After rollback, enter cooldown period (no switches allowed)
6. Log all events for audit trail

#### 4.2.2 Dashboard (`src/dashboard/`)

| Component | Language | Purpose |
|-----------|----------|---------|
| `app.py` | Python/Flask | Web server for dashboard |
| `templates/index.html` | HTML/JS | Real-time dashboard UI |
| `static/charts.js` | JavaScript | Chart.js based visualizations |
| `api.py` | Python/Flask | REST API for metrics and control |

**Dashboard Features:**
- Real-time CPU metrics visualization (line charts)
- Current scheduler indicator with switch history timeline
- SLO compliance gauge (green/yellow/red)
- Bandit arm statistics (selection counts, average rewards)
- Manual override controls (force switch, pause agent)
- Event log with rollback history

#### 4.2.3 CLI / TUI (`src/cli/`)

| Component | Language | Purpose |
|-----------|----------|---------|
| `main.py` | Python | Entry point with argument parsing |
| `commands.py` | Python | CLI command implementations |

**CLI Commands:**
```bash
adaptivesched start [--mode mock|real] [--algorithm ucb1|ts|eg]
adaptivesched status
adaptivesched switch <scheduler_name>
adaptivesched slo set <profile>
adaptivesched slo status
adaptivesched history
adaptivesched dashboard [--port 8080]
adaptivesched stop
```

---

## 5. Work Division

### 5.1 Arjun's Scope (Module B — Current Implementation)

| Task | Priority | Status |
|------|----------|--------|
| Project scaffolding & architecture | P0 | Implemented |
| SLO configuration and rolling-window watchdog | P0 | Implemented; Linux and test validation pending |
| Rollback mechanism and health checker | P0 | Implemented; Linux recovery validation pending |
| CLI and dashboard/API | P0 | Implemented for mock MVP; real-mode behavior requires Linux validation |
| Mock mode for demo | P0 | Implemented |
| Module interfaces | P0 | Implemented |

### 5.2 Aritra's Scope (Module A — Separate Plan)

| Task | Priority | Status |
|------|----------|--------|
| Python procfs metrics collector | P0 | Implemented; Linux host validation pending |
| C/perf collector and `ctypes` bridge | P1 | Not implemented; future enhancement |
| UCB1, Thompson Sampling, and ε-greedy | P0/P1 | Implemented in Python |
| Reward computation and bandit agent | P0 | Implemented in Python |
| Linux sched_ext process manager | P1 | MVP implemented; host switching and recovery validation pending |
| Unit tests for collector, algorithms, watchdog, engine, and API | P1 | 13 tests pass; Linux host integration remains untested |

---

## 6. Integration Plan

### 6.1 Interface Contract

Both modules communicate through well-defined Python interfaces:

```python
# src/interfaces/metrics_interface.py
class IMetricsCollector(ABC):
    @abstractmethod
    def collect(self) -> SystemMetrics: ...
    
    @abstractmethod
    def start(self) -> None: ...
    
    @abstractmethod
    def stop(self) -> None: ...

# src/interfaces/agent_interface.py
class ISchedulerAgent(ABC):
    @abstractmethod
    def select_scheduler(self, metrics: SystemMetrics) -> str: ...
    
    @abstractmethod
    def update_reward(self, scheduler: str, reward: float) -> None: ...
    
    @abstractmethod
    def get_statistics(self) -> AgentStatistics: ...
```

### 6.2 Integration Steps

1. **Step 1**: Aritra implements `IMetricsCollector` in `src/metrics/` → replaces `MockMetricsCollector`
2. **Step 2**: Aritra implements `ISchedulerAgent` in `src/agent/` → replaces `MockBanditAgent`
3. **Step 3**: Update `src/core/engine.py` to use real implementations (config toggle)
4. **Step 4**: Test end-to-end with mock mode first, then real kernel
5. **Step 5**: Integration testing with workload generators

### 6.3 Configuration Toggle

```yaml
# config/adaptivesched.yaml
mode: "mock"  # "mock" | "real"
agent:
  implementation: "mock"  # "mock" | "ucb1" | "thompson" | "epsilon_greedy"
metrics:
  implementation: "mock"  # "mock" | "proc" | "perf"
```

For the current Linux MVP, use `--mode real` as described in `MVP_STATUS.md`. It uses procfs measurements and installed foreground `scx_*` binaries, not a C/perf bridge. A supported Linux host and privileges are required; changing the mode on Windows is not supported.

---

## 7. Technology Stack

| Layer | Technology | Justification |
|-------|------------|---------------|
| Agent Logic | Python 3.10+ | Rapid prototyping, rich ecosystem for ML/stats |
| Kernel Metrics | C (with ctypes bridge) | Zero-overhead `/proc` parsing, `perf_event_open` |
| Dashboard | Flask + Chart.js | Lightweight, real-time capable via WebSocket |
| TUI | Rich | Modern terminal UI for live monitoring |
| Config | YAML | Human-readable, widely used |
| Testing | pytest + unittest | Standard Python testing |
| Build (C) | Makefile / CMake | Standard C build system |

---

## 8. Demo Strategy (Review 2)

### 8.1 What We Demo

1. **Architecture walkthrough** — Show the system diagram, explain module separation
2. **Mock mode live demo** — Start the agent in simulation, show scheduler switching
3. **Dashboard** — Real-time metrics visualization with simulated workload transitions
4. **SLO violation + rollback** — Trigger a simulated degradation, watch automatic rollback
5. **CLI** — Show all commands working
6. **Code walkthrough** — Show clean architecture, interfaces, separation of concerns

### 8.2 What We Don't Demo (Yet)

- Real sched_ext kernel interaction (requires specific kernel build)
- Real workload benchmarks (sysbench, stress-ng)
- Production deployment

---

## 9. Directory Structure

```
AdaptiveSched/
├── paper.tex                    # IEEE paper
├── paper.pdf
├── README.md                    # Project overview
├── requirements.txt             # Python dependencies
├── setup.py                     # Package setup
├── Makefile                     # Build system for C components
│
├── config/                      # Configuration files
│   ├── adaptivesched.yaml       # Main config
│   └── slo_profiles/            # SLO profile definitions
│       ├── interactive.yaml
│       ├── throughput.yaml
│       └── balanced.yaml
│
├── src/                         # Source code
│   ├── __init__.py
│   ├── interfaces/              # Abstract interfaces (contract)
│   │   ├── __init__.py
│   │   ├── metrics_interface.py
│   │   ├── agent_interface.py
│   │   └── scheduler_interface.py
│   │
│   ├── core/                    # Core engine
│   │   ├── __init__.py
│   │   ├── engine.py            # Main orchestrator
│   │   ├── config.py            # Config loader
│   │   └── models.py            # Data models
│   │
│   ├── metrics/                 # Metrics collection (Aritra)
│   │   ├── __init__.py
│   │   ├── mock_metrics.py      # Mock for demo (Arjun provides)
│   │   ├── proc_parser.c        # C: /proc parser (Aritra)
│   │   ├── perf_collector.c     # C: perf events (Aritra)
│   │   └── metrics_bridge.py    # Python-C bridge (Aritra)
│   │
│   ├── agent/                   # Bandit agent (Aritra)
│   │   ├── __init__.py
│   │   ├── mock_agent.py        # Mock for demo (Arjun provides)
│   │   ├── bandit_base.py       # Abstract bandit (Aritra)
│   │   ├── ucb1.py              # UCB1 algorithm (Aritra)
│   │   ├── thompson_sampling.py # Thompson Sampling (Aritra)
│   │   ├── epsilon_greedy.py    # ε-greedy (Aritra)
│   │   ├── reward.py            # Reward computation (Aritra)
│   │   └── agent_engine.py      # Agent loop (Aritra)
│   │
│   ├── watchdog/                # SLO Watchdog (Arjun)
│   │   ├── __init__.py
│   │   ├── slo_config.py
│   │   ├── watchdog.py
│   │   ├── rollback.py
│   │   └── health_checker.py
│   │
│   ├── scheduler/               # Scheduler management
│   │   ├── __init__.py
│   │   ├── manager.py           # Scheduler switch manager
│   │   └── mock_scheduler.py    # Mock scheduler switching
│   │
│   ├── dashboard/               # Web Dashboard (Arjun)
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── api.py
│   │   ├── templates/
│   │   │   └── index.html
│   │   └── static/
│   │       ├── css/
│   │       │   └── dashboard.css
│   │       └── js/
│   │           └── charts.js
│   │
│   └── cli/                     # CLI / TUI (Arjun)
│       ├── __init__.py
│       ├── main.py
│       └── commands.py
│
├── tests/                       # Test suite
│   ├── __init__.py
│   ├── test_watchdog.py
│   ├── test_slo.py
│   ├── test_engine.py
│   └── test_mock.py
│
└── docs/                        # Documentation
    ├── PRD.md                   # This document
    ├── MVP_STATUS.md            # Current implementation status and limits
    ├── DEMO_GUIDE.md            # Demo tutorial
    ├── ARITRA_PLAN.md           # Aritra's implementation plan
    └── ARCHITECTURE.md          # Detailed architecture doc
```

---

## 10. Success Criteria (Review 2)

| Criterion | Target |
|-----------|--------|
| Working mock demo | Agent starts, switches schedulers, shows metrics |
| Dashboard functional | Real-time charts update with simulated data |
| SLO rollback works | Triggering violation causes automatic rollback |
| CLI commands work | All listed commands execute correctly |
| Code quality | Clean architecture, documented, typed |
| Paper alignment | Implementation matches paper's proposed architecture |

---

## 11. Future Roadmap (Post Review 2)

| Phase | Target | Description |
|-------|--------|-------------|
| Review 3 | Integration | Merge Aritra's bandit agent + real metrics |
| Review 3 | Real kernel | Test on Linux 6.12+ with sched_ext |
| Final | Benchmarks | sysbench, hackbench, schbench workloads |
| Final | Paper update | Results section with real data |
| Final | Evaluation | Compare UCB1 vs TS vs ε-greedy convergence |

---

## 12. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| sched_ext not available on demo machine | Mock mode simulates all behavior |
| Scheduler switch causes system crash | Watchdog + rollback + grace period |
| Bandit algorithm doesn't converge | Multiple algorithm options, tunable parameters |
| Teammate integration conflicts | Well-defined interfaces, config-based switching |
| Demo fails during review | Pre-recorded backup demo video |
