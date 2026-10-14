# AdaptiveSched: Complete Architecture, Codebase & Research Roadmap

> **Document Type:** Comprehensive Technical Architecture, Codebase Walkthrough & Master Study Guide  
> **Target Audience:** Absolute Beginner to Advanced OS Engineer (Zero-to-Mastery)  
> **Reference Paper:** `paper.pdf` / `paper.tex` — *"AdaptiveSched: Self-Tuning CPU Scheduler Selection via Online Bandit Learning and SLO-Aware Rollback"*  
> **Authors:** Arjun Tyagi (24BCE0605) & Aritra Ghosh (24BCE0598), SCOPE, VIT Vellore  
> **Kernel Target:** Linux 6.12+ (`sched_ext` framework) | **Demo Target:** Windows / Linux Mock Environment  

---

## Table of Contents
1. [Foundational Operating System Concepts (Zero-Knowledge Primer)](#1-foundational-operating-system-concepts-zero-knowledge-primer)
2. [Decoding the Research Paper (`paper.pdf`)](#2-decoding-the-research-paper-paperpdf)
3. [Mathematical Foundations of AdaptiveSched](#3-mathematical-foundations-of-adaptivesched)
4. [Master Architecture & System Topology](#4-master-architecture--system-topology)
5. [Folder-by-Folder, File-by-File, Code-by-Code Deep Dive](#5-folder-by-folder-file-by-file-code-by-code-deep-dive)
   - [5.1 Root Workspace Files](#51-root-workspace-files)
   - [5.2 `config/` — Configuration & SLO Profiles](#52-config--configuration--slo-profiles)
   - [5.3 `src/interfaces/` — Abstract Base Classes](#53-srcinterfaces--abstract-base-classes)
   - [5.4 `src/core/` — Data Models, Config & Orchestration Engine](#54-srccore--data-models-config--orchestration-engine)
   - [5.5 `src/agent/` — Multi-Armed Bandit Learning Algorithms](#55-srcagent--multi-armed-bandit-learning-algorithms)
   - [5.6 `src/watchdog/` — SLO Engine, Health Checker & Rollback State Machine](#56-srcwatchdog--slo-engine-health-checker--rollback-state-machine)
   - [5.7 `src/metrics/` — Telemetry & Performance Simulation](#57-srcmetrics--telemetry--performance-simulation)
   - [5.8 `src/scheduler/` — Scheduler Abstraction & Switching](#58-srcscheduler--scheduler-abstraction--switching)
   - [5.9 `src/dashboard/` — Flask Web App, REST API & Glassmorphic UI](#59-srcdashboard--flask-web-app-rest-api--glassmorphic-ui)
   - [5.10 `src/cli/` — Terminal User Interface (Rich CLI)](#510-srccli--terminal-user-interface-rich-cli)
   - [5.11 `tests/` — Verification Suite](#511-tests--verification-suite)
   - [5.12 `docs/` — Specifications, Demo Scripts & Development Plans](#512-docs--specifications-demo-scripts--development-plans)
6. [Life of a Decision Cycle: Step-by-Step Execution Trace](#6-life-of-a-decision-cycle-step-by-step-execution-trace)
7. [The Spike & Rollback Demonstration (Under the Hood)](#7-the-spike--rollback-demonstration-under-the-hood)
8. [Module Separation & Future Production Roadmap](#8-module-separation--future-production-roadmap)
9. [Mastery Defense: 15 Viva & Examination Questions & Answers](#9-mastery-defense-15-viva--examination-questions--answers)

---

# 1. Foundational Operating System Concepts (Zero-Knowledge Primer)

If you have never touched an operating system kernel or written an algorithm, start here.

### 1.1 What is a CPU Scheduler?
Imagine your computer has **8 CPU cores**, but you have **300 processes** running simultaneously (Chrome tabs, Spotify, Discord, VS Code, background system daemons). A core can only execute one thread of instructions at any given instant.
The **CPU Scheduler** is the traffic cop inside the OS kernel. Every few milliseconds (called a *time slice* or *quantum*), it stops the currently running process (*preemption*), saves its state, and picks the next process waiting in a line called the **runqueue**.

### 1.2 The One-Size-Fits-All Dilemma
Historically, general-purpose operating systems like Linux use a single, hardcoded scheduler:
- **CFS (Completely Fair Scheduler)**: Maintained in Linux for ~15 years; ensures every task gets a fair share of CPU time using virtual runtime trees (`vruntime` in a Red-Black tree).
- **EEVDF (Earliest Eligible Virtual Deadline First)**: Replaced CFS in Linux 6.6; schedules based on virtual deadlines and lag.

**The Problem:** Workloads have fundamentally conflicting needs:
1. **Gaming & Audio**: Needs ultra-low latency. If audio buffer frames wait 5 milliseconds, audio crackles. If input latency fluctuates, frames drop. Fairness does not matter; immediacy matters.
2. **Compilation (e.g., `make -j16`, `cargo build`)**: Needs maximum CPU throughput. High context switching overhead wastes CPU cache lines. It wants deep batches and big quanta.
3. **Web Servers & Microservices**: Needs fast wake-up and handling of thousands of lightweight network packets.

A single scheduler policy cannot be optimal for all three at the same time.

### 1.3 What is `sched_ext` (SCX)?
For 30 years, if you wanted to test a new CPU scheduler in Linux, you had to write C code inside kernel space, recompile the entire Linux kernel (taking 30–60 minutes), reboot your computer, and risk kernel panics (crashes).
In **Linux kernel 6.12 (late 2024)**, the Linux kernel merged **`sched_ext` (SCX)**.
`sched_ext` uses **eBPF (Extended Berkeley Packet Filter)** to allow user-space developers to write custom CPU scheduling policies and load them dynamically into the running kernel **without rebooting and without crashing the system**. If an SCX scheduler crashes or bugs out, the kernel detects it and instantly falls back to CFS/EEVDF!

### 1.4 The Missing Link: Why AdaptiveSched Exists
`sched_ext` gave the world custom schedulers like:
- `scx_rusty`: Written in Rust, optimized for multi-core cache locality and throughput.
- `scx_lavd`: Latency-Aware Virtual Deadline, designed for gaming and real-time responsiveness.
- `scx_bpfland`: Prioritizes interactive user tasks over background jobs.
- `scx_simple`: A minimalist FIFO/round-robin scheduler.

**However, Linux provides no brain to decide when to use which scheduler!**
Existing academic solutions (like ASA) train complex machine learning models offline and hardwire hardware-specific lookup tables. If you run them on a different CPU or an unseen workload, they fail.
**AdaptiveSched bridges this gap**: It is an autonomous, user-space software agent that learns in real time using Multi-Armed Bandits which scheduler is best, and protects system stability with a strict Service Level Objective (SLO) watchdog.

---

# 2. Decoding the Research Paper (`paper.pdf`)

The research paper draft in the root directory ([paper.tex](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/paper.tex) / `paper.pdf`) is titled:
> **AdaptiveSched: Self-Tuning CPU Scheduler Selection via Online Bandit Learning and SLO-Aware Rollback**  
> *Authors: Arjun Tyagi (24BCE0605) & Aritra Ghosh (24BCE0598)*  
> *Affiliation: SCOPE Department, VIT Vellore*

### 2.1 The Paper's Core Thesis
The paper proposes three foundational contributions:
1. **Online Formulation**: Formulates CPU scheduler selection not as an offline prediction task, but as an **online non-stationary Multi-Armed Bandit (MAB)** problem. It does not require any pre-training, datasets, or hardware calibration.
2. **Telemetry-Driven Closed-Loop Feedback**: Uses live runtime metrics (scheduling latency, throughput, CPU utilization) as a normalized scalar reward signal.
3. **Safety Watchdog with Automatic Rollback**: Establishes a watchdog state machine enforcing user-defined Service Level Objectives (SLOs). If a chosen scheduler causes latency spikes or instability, the system rolls back to the safe kernel default within seconds.

### 2.2 Literature Review Matrix: Where AdaptiveSched Fits

The paper reviews existing literature and identifies explicit gaps that AdaptiveSched closes:

| System / Paper | Mechanism | Strengths | Critical Weaknesses / Gaps | How AdaptiveSched Solves It |
| :--- | :--- | :--- | :--- | :--- |
| **ghOSt** *(Humphries et al., SOSP '21)* | User-space IPC delegation | Very flexible policy design in data centers | Requires humans to manually configure policies per application | Automates scheduler selection via bandit learning |
| **Syrup** *(Kaffes et al., SOSP '21)* | Cross-stack scheduling framework | Multi-layer execution awareness | Requires manual rule definition; no self-tuning | Online autonomous policy selection |
| **RL for Governors** *(Han et al. 2020, Pattanayak 2019)* | Policy gradient / online RL | Dynamically tunes CPU frequency / idle menu governor | Only tunes parameters of a single policy; doesn't switch policies | Switches entire scheduling paradigms |
| **Decima** *(Mao et al., SIGCOMM '19)* | Deep RL on DAGs | High optimization for Spark clusters | Heavy offline training; operates at cluster level, not OS thread level | Zero offline training; operates at OS scheduler layer |
| **SCX Global Runqueue** *(Tang et al., SMC '24)* | sched_ext global queue optimization | Evaluates BPF scheduling efficiency | Static policy analysis | Dynamic policy switching |
| **ASA: Mixture-of-Schedulers** *(arXiv 2025 preprint)* | Offline ML models + machine-specific voting tables | Feasible dynamic switching on sched_ext | **Fragile**: Needs offline dataset training; hardwired calibration tables fail on new machines | **Bandit online learning**: Machine-agnostic, zero offline training, plus adds **SLO Rollback Watchdog** |

---

# 3. Mathematical Foundations of AdaptiveSched

### 3.1 Multi-Armed Bandit (MAB) Formulation
In reinforcement learning, the Multi-Armed Bandit problem represents an agent choosing among $K$ slot machines (arms), where each arm $a \in \mathcal{A}$ gives a reward from an unknown probability distribution. The goal is to maximize cumulative reward while balancing:
- **Exploitation**: Choosing the arm known to yield the highest reward so far.
- **Exploration**: Trying lesser-known arms to discover if they perform better.

In AdaptiveSched:
- **Arms ($\mathcal{A}$)**: Set of sched_ext schedulers:
  $$\mathcal{A} = \{\text{scx\_rusty}, \text{scx\_lavd}, \text{scx\_bpfland}, \text{scx\_simple}, \text{default}\}$$
- **Reward ($R_t \in [0, 1]$)**: A composite measure of system health computed at time $t$.

### 3.2 Bandit Selection Algorithms Implemented

#### 1. UCB1 (Upper Confidence Bound 1)
Implemented in [`src/agent/ucb1.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/agent/ucb1.py).
UCB1 implements the principle of *"optimism in the face of uncertainty"*. It computes an upper confidence bound for each arm:

$$\text{Score}(a) = \bar{X}_a + c \cdot \sqrt{\frac{\ln N}{n_a}}$$

- $\bar{X}_a$: Average reward obtained from scheduler $a$.
- $N$: Total number of decision cycles across all schedulers ($N = \sum_a n_a$).
- $n_a$: Number of times scheduler $a$ has been selected.
- $c$: Exploration constant (defaults to $\sqrt{2} \approx 1.414$).

**Behavior**:
1. First, pulls every scheduler arm once so $n_a \ge 1$.
2. If an arm has not been tried for a long time, its denominator $n_a$ stays small while $\ln N$ grows, boosting its exploration bonus until the agent tests it again.

#### 2. Thompson Sampling (Bayesian Posterior Sampling)
Implemented in [`src/agent/thompson_sampling.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/agent/thompson_sampling.py).
Maintains a Beta distribution $\text{Beta}(\alpha_a, \beta_a)$ over the expected reward of each scheduler $a$:
- Prior: $\alpha_a = 1.0, \beta_a = 1.0$ (uniform distribution).
- When reward $R \in [0, 1]$ is observed:
  $$\alpha_a \leftarrow \alpha_a + R$$
  $$\beta_a \leftarrow \beta_a + (1 - R)$$
- Selection step: Draws a random sample $\theta_a \sim \text{Beta}(\alpha_a, \beta_a)$ for each arm, and selects:
  $$a^* = \arg\max_{a} \theta_a$$

#### 3. $\epsilon$-Greedy with Exponential Decay
Implemented in [`src/agent/epsilon_greedy.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/agent/epsilon_greedy.py).
- At cycle $t$, exploration probability $\epsilon_t$ decays:
  $$\epsilon_t = \max(\epsilon_{min}, \epsilon_0 \cdot \gamma^{t-1})$$
  (Default: $\epsilon_0 = 0.3$, decay rate $\gamma = 0.995$, $\epsilon_{min} = 0.01$).
- With probability $\epsilon_t$, pick a random scheduler (explore).
- With probability $1 - \epsilon_t$, pick $\arg\max_a \bar{X}_a$ (exploit).

---

### 3.3 The Dynamic Reward Function
Implemented in [`src/agent/reward.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/agent/reward.py).
Raw OS metrics have completely different scales: latency is in microseconds (500–50,000 $\mu$s), throughput is in operations/sec (1,000–50,000 ops), and CPU utilization is a percentage (0–100%).
We first normalize each metric into $[0, 1]$ using min-max clamping:

$$\text{Norm}(x, [min, max]) = \min\left(1.0, \max\left(0.0, \frac{x - min}{max - min}\right)\right)$$

The individual component scores are:
1. **Latency Score** (lower latency is better):
   $$S_{latency} = 1.0 - \text{Norm}(\text{latency}, [100\mu s, 50000\mu s])$$
2. **Throughput Score** (higher throughput is better):
   $$S_{throughput} = \text{Norm}(\text{throughput}, [1000, 50000])$$
3. **CPU Utilization Score** (target utilization $U^* = 70\%$ to avoid idle waste and avoid saturation):
   $$S_{util} = \max\left(0.0, 1.0 - |\text{Norm}(\text{util}, [0, 100]) - 0.70|\right)$$

The final scalar reward is the weighted sum:
$$R = \frac{w_{lat} \cdot S_{latency} + w_{tp} \cdot S_{throughput} + w_{util} \cdot S_{util}}{w_{lat} + w_{tp} + w_{util}} \in [0, 1]$$
*(Default weights: $w_{lat} = 0.40, w_{tp} = 0.35, w_{util} = 0.25$)*.

---

### 3.4 Watchdog State Machine & Compliance Math
Implemented in [`src/watchdog/watchdog.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/watchdog/watchdog.py).

```
   ┌───────────┐
   │   IDLE    │◄─────────────────────────────┐
   └─────┬─────┘                              │
         │ on_scheduler_switch()              │
         ▼                                    │
   ┌───────────────────┐                      │
   │   GRACE_PERIOD    │ (e.g. 5 seconds)     │
   └─────┬─────────────┘                      │
         │ grace elapsed                      │
         ▼                                    │
   ┌───────────────────┐                      │
┌─►│    MONITORING     │                      │
│  └─────┬─────────────┘                      │
│        │ constraint violated                │
│        ▼                                    │
│  ┌───────────────────┐                      │
└──┤VIOLATION_DETECTED │                      │
   └─────┬─────────────┘                      │
         │ violations >= threshold (e.g. 3)   │
         │ -> TRIGGER ROLLBACK!               │
         ▼                                    │
   ┌───────────────────┐                      │
   │     COOLDOWN      │ (e.g. 60 seconds)    │
   └─────┬─────────────┘                      │
         │ cooldown elapsed                   │
         └────────────────────────────────────┘
```

**Compliance Scoring Formula**:
For a set of constraints $C_i$ with maximum allowable thresholds $M_i$, observed values $A_i$, and weights $w_i$:
- If satisfied ($A_i \le M_i$), margin score is $m_i = 1.0 - \frac{A_i}{M_i}$.
- If violated ($A_i > M_i$), margin score is $0.0$.
$$\text{Compliance Score} = \left(\frac{\sum_i w_i \cdot m_i}{\sum_i w_i}\right) \times 100\%$$

---

# 4. Master Architecture & System Topology

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   USER SPACE LAYER                                          │
│                                                                                             │
│   ┌─────────────────────────────┐                    ┌──────────────────────────────────┐   │
│   │   Rich CLI (src/cli/main)   │                    │  Web UI (Flask/HTML/Chart.js)    │   │
│   │  start, status, switch, slo │                    │  Port 8080 - Dark Glassmorphism  │   │
│   └──────────────┬──────────────┘                    └────────────────┬─────────────────┘   │
│                  │                                                    │                     │
│                  │ HTTP / Internal Call                               │ REST API            │
│                  ▼                                                    ▼                     │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                 AdaptiveSchedEngine (src/core/engine.py) - Orchestrator             │   │
│   │                                                                                     │   │
│   │   Main Loop (5s interval):                                                          │   │
│   │   1. Collect Metrics  ──► 2. Compute Reward ──► 3. Update Bandit                    │   │
│   │   4. Watchdog Check   ──► 5. Health Check   ──► 6. Select Arm ──► 7. Switch Sched   │   │
│   └───────┬──────────────────────────┬─────────────────────────────┬────────────────────┘   │
│           │                          │                             │                        │
│           ▼                          ▼                             ▼                        │
│   ┌───────────────┐          ┌───────────────┐             ┌───────────────┐                │
│   │ Bandit Agent  │          │ SLO Watchdog  │             │ Rollback Mgr  │                │
│   │ (src/agent/)  │          │(src/watchdog/)│             │(src/watchdog/)│                │
│   │ UCB1 / TS / EG│          │ State Machine │             │ Safe fallback │                │
│   └───────────────┘          └───────┬───────┘             └───────┬───────┘                │
│                                      │                             │                        │
│                                      └─────── Triggers Rollback ───┘                        │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│                                  ABSTRACT INTERFACES                                        │
│         IMetricsCollector           ISchedulerManager             ISchedulerAgent           │
│     (src/interfaces/metrics)    (src/interfaces/scheduler)    (src/interfaces/agent)        │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│                          EXECUTION PLATFORM (MOCK vs REAL KERNEL)                           │
│                                                                                             │
│   [MOCK ENVIRONMENT - Windows / Review 2 Demo]                                              │
│   ├── MockSchedulerManager  ──► Simulates BPF attach/detach & 20ms switch latency           │
│   └── MockMetricsCollector  ──► Simulates realistic Gaussian profiles, noise & spikes       │
│                                                                                             │
│   [PRODUCTION LINUX KERNEL - Linux 6.12+]                                                   │
│   ├── scx_loader (BPF)      ──► Calls libbpf to load scx_rusty, scx_lavd into kernel        │
│   └── C Metrics Collector   ──► Reads /proc/schedstat & perf_event_open() counters          │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

# 5. Folder-by-Folder, File-by-File, Code-by-Code Deep Dive

Let's inspect every single file in the repository, explaining its purpose, internal mechanics, and relation to the paper.

---

## 5.1 Root Workspace Files

### 1. [`paper.tex`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/paper.tex) / `paper.pdf`
- **What it is**: The IEEE transaction-formatted academic paper proposal authored by Arjun Tyagi and Aritra Ghosh.
- **Why it matters**: It sets the academic foundation: it justifies why static schedulers fail, critiques prior work (ghOSt, Syrup, ASA), and proposes the MAB + SLO Watchdog architecture.
- **Key Sections**:
  - Abstract (Line 20–22): Declares the zero-offline-training MAB agent and SLO watchdog.
  - Literature Review (Line 28–41): Analyzes 7 papers and differentiates AdaptiveSched from ASA preprint.

### 2. [`requirements.txt`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/requirements.txt)
- **Contents**:
  ```text
  flask>=3.0.0
  pyyaml>=6.0
  rich>=13.0.0
  ```
- **Role**: Declares external Python dependencies: `flask` for the web dashboard, `pyyaml` for parsing SLO profile files, and `rich` for formatting terminal output.

### 3. [`run_demo.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/run_demo.py)
- **What it is**: The master launcher script.
- **How it works**:
  1. Instantiates `Config()`.
  2. Spawns `AdaptiveSchedEngine(config)`.
  3. Calls `engine.start()` to start the background agent thread.
  4. Automatically opens `http://localhost:8080` in your web browser using Python's `webbrowser.open()`.
  5. Starts Flask web server via `run_dashboard()`.

### 4. [`start_demo.bat`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/start_demo.bat)
- **What it is**: A Windows batch script for automated evaluation. It checks if Python is installed, installs `requirements.txt`, and launches `run_demo.py`.

---

## 5.2 `config/` — Configuration & SLO Profiles

### 1. [`config/adaptivesched.yaml`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/config/adaptivesched.yaml)
- **What it is**: The global runtime configuration file.
- **Key Parameters**:
  - `mode: "mock"`: Controls whether to run against the simulated environment or real Linux kernel.
  - `agent.implementation: "ucb1"`: Algorithm selector (`ucb1`, `thompson`, `epsilon_greedy`, `mock`).
  - `agent.decision_interval_seconds: 5`: The agent decision cycle period.
  - `schedulers.available`: List of selectable schedulers (`scx_rusty`, `scx_lavd`, `scx_bpfland`, `scx_simple`, `default`).
  - `slo.active_profile: "balanced"`: Which profile in `config/slo_profiles/` is loaded at startup.
  - `dashboard.port: 8080`: Web server port.

### 2. `config/slo_profiles/`
Contains YAML profiles that map human priorities to concrete constraints:
- [`interactive.yaml`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/config/slo_profiles/interactive.yaml):
  - Prioritizes latency for gaming and desktop interactivity.
  - $p99\_latency\_us \le 5000\mu s$ (weight 0.60).
  - Context switch limit: 50,000/s.
- [`throughput.yaml`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/config/slo_profiles/throughput.yaml):
  - Prioritizes throughput for builds and compiling.
  - $p99\_latency\_us \le 15000\mu s$ (more relaxed latency tolerance).
  - Target CPU utilization up to 95%.
- [`balanced.yaml`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/config/slo_profiles/balanced.yaml):
  - Compromise profile: $p99 \le 8000\mu s$, CPU utilization $\le 90\%$.
  - Evaluation settings: `grace_period_seconds: 5`, `violation_threshold: 3`, `cooldown_seconds: 60`.

---

## 5.3 `src/interfaces/` — Abstract Base Classes

These interfaces establish strict software engineering contracts using Python's `abc.ABC`.

### 1. [`src/interfaces/scheduler_interface.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/interfaces/scheduler_interface.py)
Defines `ISchedulerManager`:
- `switch_to(scheduler_name: str) -> bool`: Execute a switch to the named policy.
- `get_current() -> str`: Return active scheduler name.
- `get_available() -> List[str]`: Return all available schedulers.

### 2. [`src/interfaces/metrics_interface.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/interfaces/metrics_interface.py)
Defines `IMetricsCollector`:
- `collect() -> SystemMetrics`: Sample kernel or mock performance counters.
- `start() -> None`: Begin background sampling loop.
- `stop() -> None`: Stop background sampling.

### 3. [`src/interfaces/agent_interface.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/interfaces/agent_interface.py)
Defines `ISchedulerAgent`:
- `select_scheduler(metrics: SystemMetrics) -> str`: Run bandit algorithm to pick next scheduler.
- `update_reward(scheduler: str, reward: float) -> None`: Feed observed performance back into bandit statistics.
- `get_statistics() -> AgentStatistics`: Return pull counts and average rewards for dashboard & CLI.

---

## 5.4 `src/core/` — Data Models, Config & Orchestration Engine

### 1. [`src/core/models.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/core/models.py)
Defines strongly-typed dataclasses passed across threads and modules:
- `SystemMetrics`:
  - `cpu_utilization` (0–100%)
  - `context_switches` (count per interval)
  - `scheduling_latency_us` (average dispatch wait in microseconds)
  - `ipc` (Instructions Per Cycle)
  - `cache_miss_rate` (ratio of L1/LLC cache misses)
  - `runqueue_length` (number of runnable threads queued)
  - `throughput_ops` (workload operations completed per second)
  - `p99_latency_us` (99th percentile tail latency)
- `AgentStatistics`: Holds algorithm name, total pulls, arm counts dictionary, and arm rewards dictionary.
- `SchedulerSwitchEvent`: Tracks switch history (`from_scheduler`, `to_scheduler`, `reason`, `result`, `timestamp`).
- `SLOViolation`: Represents an SLO breach (`constraint_name`, `constraint_max`, `actual_value`, `scheduler`).

### 2. [`src/core/config.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/core/config.py)
- Loads `config/adaptivesched.yaml`.
- Traverses and parses all YAML files in `config/slo_profiles/`.
- Provides getters with fallback defaults.

### 3. [`src/core/engine.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/core/engine.py) — **The Heart of AdaptiveSched**
Contains `AdaptiveSchedEngine`:
- **Lifecycle Management**:
  - `start()`: Spawns a daemon thread executing `_run_loop()`.
  - `stop()`: Gracefully halts metrics collection and engine execution.
- **The Decision Cycle (`_run_cycle()`)**:
  Executed every 5 seconds:
  1. `metrics = self._metrics_collector.collect()`: Collects current performance.
  2. `reward = self._agent.compute_reward(metrics)`: Calculates normalized reward $R \in [0, 1]$.
  3. `self._agent.update_reward(current_scheduler, reward)`: Updates bandit memory.
  4. `watchdog_result = self._watchdog.evaluate(metrics, current)`: Evaluates SLO compliance. If rollback occurred, halts cycle.
  5. `self._watchdog.is_switch_allowed()`: Verifies that cooldown is not active.
  6. `self._health_checker.check(metrics)`: Ensures system is not in a catastrophic state.
  7. `selected = self._agent.select_scheduler(metrics)`: Bandit decides whether to exploit or explore.
  8. If `selected != current`: calls `self._scheduler_manager.switch_to(selected)`, notifies watchdog via `on_scheduler_switch()`, and logs switch event.

---

## 5.5 `src/agent/` — Multi-Armed Bandit Learning Algorithms

### 1. [`src/agent/bandit_base.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/agent/bandit_base.py)
Abstract base class `BanditBase`:
- Validates that arms are non-empty and unique.
- Maintains `self.counts[arm]` and `self.rewards[arm]`.
- Implements numerical incremental mean update:
  $$\mu_n = \mu_{n-1} + \frac{r - \mu_{n-1}}{n}$$
  *(Prevents floating-point overflow and maintains numerically stable moving averages).*

### 2. [`src/agent/ucb1.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/agent/ucb1.py)
Implements the Upper Confidence Bound formula. Ensures every unpulled arm is selected once before calculating logarithmic confidence bounds.

### 3. [`src/agent/thompson_sampling.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/agent/thompson_sampling.py)
Implements Bayesian Thompson Sampling with fractional updates:
- Maintains pseudo-counts $\alpha$ and $\beta$.
- Samples from `random.betavariate(alpha, beta)`.

### 4. [`src/agent/epsilon_greedy.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/agent/epsilon_greedy.py)
Implements $\epsilon$-Greedy with exponential decay:
- Reduces exploration probability on each step: $\epsilon_t = \max(\epsilon_{min}, \epsilon_0 \cdot \gamma^{t-1})$.

### 5. [`src/agent/reward.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/agent/reward.py)
Implements `RewardComputer`:
- Clamps out-of-range metrics.
- Computes weighted harmonic reward between latency, throughput, and CPU utilization.
- Excludes missing or non-finite readings dynamically so unmeasured dimensions do not corrupt learning.

### 6. [`src/agent/agent_engine.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/agent/agent_engine.py)
Implements `BanditAgent`, implementing `ISchedulerAgent`. Serves as the factory uniting `BanditBase` subclasses with `RewardComputer`.

### 7. [`src/agent/mock_agent.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/agent/mock_agent.py)
A lightweight fallback agent used for baseline comparisons and standalone mock demonstrations.

---

## 5.6 `src/watchdog/` — SLO Engine, Health Checker & Rollback State Machine

### 1. [`src/watchdog/slo_config.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/watchdog/slo_config.py)
- `SLOConstraint`: Compares live metric against maximum threshold ($A_i \le M_i$).
- `SLOProfile`: Holds list of constraints, grace period duration, violation threshold count, and cooldown duration. Evaluates all constraints simultaneously.

### 2. [`src/watchdog/watchdog.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/watchdog/watchdog.py)
Implements `SLOWatchdog`:
- Tracks states: `IDLE`, `GRACE_PERIOD`, `MONITORING`, `VIOLATION_DETECTED`, `COOLDOWN`.
- Manages consecutive violation counter.
- When `consecutive_violations >= violation_threshold`:
  1. Calls `self._rollback_callback("consecutive SLO violations exceeded threshold")`.
  2. Sets state to `COOLDOWN`.
  3. Records timestamp to block any new switches until cooldown period finishes.

### 3. [`src/watchdog/rollback.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/watchdog/rollback.py)
Implements `RollbackManager`:
- Directly invokes `scheduler_manager.switch_to(default_scheduler)`.
- Logs timestamped rollback audit record with cause and outcome.

### 4. [`src/watchdog/health_checker.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/watchdog/health_checker.py)
Implements `HealthChecker`:
- Safety net independent of user SLOs.
- Checks hard physical limits (CPU $>98\%$, context switches $>200,000$/sec, runqueue length $>20$, latency $>50,000\mu s$).
- If critical, blocks the agent from attempting a scheduler switch to avoid thrashing an already collapsing system.

---

## 5.7 `src/metrics/` — Telemetry & Performance Simulation

### 1. [`src/metrics/mock_metrics.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/metrics/mock_metrics.py)
Implements `MockMetricsCollector`:
- Simulates realistic kernel metrics for each scheduler based on empirical profiles:
  - `scx_rusty`: High throughput (12,000 ops), moderate latency (800 $\mu$s).
  - `scx_lavd`: Low latency (500 $\mu$s, p99 1800 $\mu$s), ideal for gaming/interactive.
  - `scx_bpfland`: Balanced interactive policy (650 $\mu$s latency).
  - `scx_simple`: FIFO-style, struggles under load (3500 $\mu$s latency, p99 12,000 $\mu$s).
  - `default`: Baseline kernel CFS/EEVDF performance (1500 $\mu$s latency).
- Adds Gaussian noise, diurnal sine wave drift, and responds to manual **Spike Injection** triggers.

---

## 5.8 `src/scheduler/` — Scheduler Abstraction & Switching

### 1. [`src/scheduler/mock_scheduler.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/scheduler/mock_scheduler.py)
Implements `MockSchedulerManager`:
- Maintains active scheduler state string.
- Injects a realistic 20ms sleep during switch (`time.sleep(0.02)`) to faithfully replicate the overhead of loading and attaching an eBPF `sched_ext` program into the Linux kernel.

---

## 5.9 `src/dashboard/` — Flask Web App, REST API & Glassmorphic UI

### 1. [`src/dashboard/app.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/dashboard/app.py)
Flask application factory:
- Connects the running `AdaptiveSchedEngine` instance with Flask routes.
- Serves the single-page application at `/`.

### 2. [`src/dashboard/api.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/dashboard/api.py)
Exposes JSON endpoints:
- `GET /api/status`: Engine state, active scheduler, watchdog state, compliance score, bandit arm stats.
- `GET /api/metrics`: Streaming time-series data for latency, CPU, and throughput.
- `GET /api/switches`: Audit trail of all switches and rollbacks.
- `POST /api/switch`: Manual user override to force a specific scheduler.
- `POST /api/spike`: Injects a simulated workload surge for live demo evaluations.
- `POST /api/slo/set`: Dynamically hot-swaps the active SLO profile.
- `POST /api/pause` & `POST /api/resume`: Freezes/resumes the agent loop.

### 3. [`src/dashboard/templates/index.html`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/dashboard/templates/index.html) & [`charts.js`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/dashboard/static/charts.js)
- Beautiful dark-mode glassmorphic user interface.
- Renders live Chart.js streaming graphs:
  - Latency vs SLO threshold line chart.
  - CPU Utilization & Throughput dual-axis chart.
  - Multi-Armed Bandit Arm Pulls & Average Rewards bar charts.
- Interactive controls: 1-click scheduler manual switch buttons, profile switcher dropdown, and **"Inject Workload Spike"** button.

---

## 5.10 `src/cli/` — Terminal User Interface (Rich CLI)

### 1. [`src/cli/main.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/cli/main.py)
A CLI built using Python's `argparse` and `rich` library:
- `python -m src.cli.main start`: Starts the agent engine.
- `python -m src.cli.main status`: Queries the API and renders a status table showing active scheduler, watchdog state, compliance gauge, and arm statistics.
- `python -m src.cli.main switch <name>`: Manually forces a switch.
- `python -m src.cli.main slo --set <profile>`: Changes SLO profile from the terminal.
- `python -m src.cli.main history`: Prints the complete switch audit table.

---

## 5.11 `tests/` — Verification Suite

### 1. [`tests/test_core.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/tests/test_core.py)
Unit tests covering:
- Serialization/deserialization of dataclasses (`SystemMetrics`, `SchedulerSwitchEvent`).
- Configuration parsing and SLO profile loading.
- Mock scheduler state transitions and simulated switch latency.
- Bandit algorithms (verifying that rewards update and arm counts increase).
- Watchdog violation counting and automatic rollback triggering.
- Health checker threshold enforcement.
- REST API endpoint functionality using Flask's test client.

---

## 5.12 `docs/` — Specifications, Demo Scripts & Development Plans

- [`docs/PRD.md`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/docs/PRD.md): The master Product Requirements Document detailing mathematical models, non-functional requirements, and system contracts.
- [`docs/DEMO_GUIDE.md`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/docs/DEMO_GUIDE.md): Step-by-step instructions for demonstrating the system in front of professors and evaluators.
- [`docs/PRESENTATION_SCRIPT.md`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/docs/PRESENTATION_SCRIPT.md): A slide-by-slide 15-minute spoken script for the presentation.
- [`docs/ARITRA_PLAN.md`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/docs/ARITRA_PLAN.md): Detailed development blueprint for Module A (C metrics collector, `perf_event_open`, and ctypes bridge).

---

# 6. Life of a Decision Cycle: Step-by-Step Execution Trace

To master this project, you must be able to describe exactly what happens during one 5-second decision cycle inside [`src/core/engine.py`](file:///d:/COLGATE_LYF/Semester5/BCSE303P%20-%20Operating%20Systems%20Lab/Project/AdaptiveSched/src/core/engine.py):

```
       [Start of 5-Second Interval]
                   │
                   ▼
       1. Metrics Collection
          metrics = collector.collect()
          (Reads latency, throughput, CPU, context switches)
                   │
                   ▼
       2. Reward Calculation
          reward = agent.compute_reward(metrics)
          (Maps metrics to [0, 1] using latency, throughput, CPU weights)
                   │
                   ▼
       3. Update Bandit Memory
          agent.update_reward(current_scheduler, reward)
          (Increments pull count, updates running average / Beta distribution)
                   │
                   ▼
       4. Watchdog SLO Evaluation
          result = watchdog.evaluate(metrics, current_scheduler)
          ├─► Did constraints fail?
          │   ├─► Yes: increment consecutive_violations
          │   │   └─► If violations >= 3:
          │   │       TRIGGER ROLLBACK to default scheduler!
          │   │       Enter COOLDOWN (60s). Halt cycle.
          │   └─► No: reset violations to 0
          ▼
       5. Pre-Switch Health Check
          health = health_checker.check(metrics)
          (If CPU > 98% or ctx switches > 200,000, abort switch)
                   │
                   ▼
       6. Bandit Arm Selection
          next_scheduler = agent.select_scheduler(metrics)
          (Evaluates UCB1 scores or draws Thompson samples)
                   │
                   ▼
       7. Execution & State Transition
          If next_scheduler != current_scheduler:
          ├─► Call scheduler_manager.switch_to(next_scheduler)
          ├─► watchdog.on_scheduler_switch() (enter GRACE_PERIOD)
          └─► Append to switch_history log
                   │
                   ▼
       [Sleep until next 5s interval]
```

---

# 7. The Spike & Rollback Demonstration (Under the Hood)

The cornerstone demonstration of this project is the **SLO-Aware Rollback**. Here is the exact sequence of events when someone clicks **"Inject Workload Spike"** on the dashboard or runs a CPU stress test:

1. **Trigger**: An API POST request hits `/api/spike`. `MockMetricsCollector` sets `_spike_active = True`.
2. **Degradation**:
   - `scheduling_latency_us` jumps from $500\mu s$ to $>25,000\mu s$.
   - `p99_latency_us` spikes to $>40,000\mu s$.
   - CPU utilization rises to $95\%$.
3. **Watchdog Detection**:
   - **Cycle 1**: Watchdog checks `interactive.yaml` ($p99 \le 5000\mu s$). Observed $40,000\mu s > 5000\mu s$. Violation count = 1. State changes to `VIOLATION_DETECTED`.
   - **Cycle 2**: Still violated. Violation count = 2.
   - **Cycle 3**: Violation count = 3. This reaches `violation_threshold: 3`!
4. **Automatic Rollback Execution**:
   - Watchdog invokes callback: `engine._on_rollback_requested("consecutive SLO violations exceeded threshold")`.
   - `RollbackManager` switches scheduler immediately back to `default` (CFS/EEVDF).
   - Watchdog state transitions to `COOLDOWN` for 60 seconds, preventing the bandit agent from switching schedulers while the system stabilizes.
   - An event of type `slo_rollback` is appended to the audit log and streamed to the dashboard.
5. **Recovery**: Metrics normalize under the stable default scheduler. Once the 60-second cooldown expires, the watchdog transitions back to `IDLE` and permits the bandit agent to resume normal exploration.

---

# 8. Module Separation & Future Production Roadmap

The project is structured according to the academic division between team members:

```
┌─────────────────────────────────────────────────────────┐
│       MODULE B: Architecture, Watchdog & UI             │
│       Lead: Arjun Tyagi (24BCE0605)                     │
│       Status: COMPLETED & FULLY FUNCTIONAL              │
├─────────────────────────────────────────────────────────┤
│ • Core engine decision loop (src/core/engine.py)        │
│ • SLO Watchdog state machine (src/watchdog/watchdog.py) │
│ • Rollback manager & health check (src/watchdog/)       │
│ • Interactive Web Dashboard (Flask + Chart.js)          │
│ • Rich Terminal CLI (src/cli/main.py)                   │
│ • System integration & demo harnesses                   │
└─────────────────────────────────────────────────────────┘
                            ▲
                            │ Communicates via
                            │ src/interfaces/
                            ▼
┌─────────────────────────────────────────────────────────┐
│       MODULE A: Learning & Kernel Collection            │
│       Lead: Aritra Ghosh (24BCE0598)                    │
│       Status: Algorithms Done; C/eBPF Planned           │
├─────────────────────────────────────────────────────────┤
│ • Bandit algorithms (UCB1, Thompson, ε-greedy) [DONE]   │
│ • Dynamic reward computer (src/agent/reward.py) [DONE]  │
│ • C-based /proc/schedstat parser [PLANNED]              │
│ • C-based perf_event_open() hardware counter [PLANNED]  │
│ • ctypes Python-to-C telemetry bridge [PLANNED]         │
│ • sched_ext libbpf loader integration [PLANNED]         │
└─────────────────────────────────────────────────────────┘
```

### The Transition to the Real Linux 6.12 Kernel
To deploy AdaptiveSched onto a real Linux 6.12 machine with `sched_ext`:
1. Compile the C collector: `gcc -shared -o libmetrics.so proc_parser.c perf_collector.c -fPIC`.
2. Connect Python via `ctypes.CDLL("./libmetrics.so")`.
3. In `config/adaptivesched.yaml`, change:
   ```yaml
   mode: "real"
   metrics:
     implementation: "proc"
   ```
4. Sched_ext schedulers (`scx_rusty`, `scx_lavd`) are loaded via their user-space binaries or libbpf calls.

---

# 9. Mastery Defense: 15 Viva & Examination Questions & Answers

Be prepared to answer these questions with confidence during your project reviews:

#### Q1: What is the primary problem with Linux's default CPU scheduler?
**Answer:** Linux's default scheduler (CFS or EEVDF) treats all workloads with generic fairness. It cannot simultaneously minimize tail latency for interactive workloads (e.g., gaming, real-time audio) and maximize batch throughput for compilation or database servers.

#### Q2: What is `sched_ext`, and in which Linux kernel version was it introduced?
**Answer:** `sched_ext` (SCX) is a Linux kernel framework merged in **Linux 6.12** that enables user-space / eBPF-defined CPU scheduling policies to be dynamically loaded, executed, and unloaded at runtime without patching or rebooting the kernel.

#### Q3: Why did you choose Multi-Armed Bandit (MAB) learning instead of Deep Reinforcement Learning (like PPO or DQN)?
**Answer:** Deep RL requires massive neural networks, millions of training cycles, offline data collection, and substantial computational overhead (inference latency). An OS scheduler selector must make decisions in microseconds or milliseconds with virtually zero CPU overhead. MAB algorithms (UCB1, Thompson Sampling) are lightweight ($O(1)$ time complexity per selection), require **zero offline training**, and adapt immediately to non-stationary environments.

#### Q4: What makes your system superior to existing academic work like ASA (Mixture-of-Schedulers)?
**Answer:** ASA relies on offline trained machine learning models and machine-specific static calibration tables. If you run ASA on a CPU it was not calibrated for, its predictions fail. AdaptiveSched uses online bandit learning with zero prior calibration, making it hardware-agnostic, and adds an **SLO-Aware Watchdog with automatic rollback**, which ASA lacks.

#### Q5: Explain the UCB1 equation and the role of the constant $c$.
**Answer:** $\text{Score}(a) = \bar{X}_a + c \sqrt{\frac{\ln N}{n_a}}$. The first term $\bar{X}_a$ is exploitation (how well the scheduler performed previously). The second term $c \sqrt{\frac{\ln N}{n_a}}$ is exploration (an uncertainty bonus that increases for schedulers that have not been tested recently). The constant $c = \sqrt{2}$ balances exploration versus exploitation.

#### Q6: How does Thompson Sampling decide which scheduler to pick?
**Answer:** It models each scheduler's reward as a Beta distribution $\text{Beta}(\alpha, \beta)$. In each cycle, it samples a random value from each arm's posterior distribution and selects the arm with the highest sample. Schedulers with high observed rewards have distributions shifted towards 1, but wide distributions for rarely-tested arms allow for probabilistic exploration.

#### Q7: Why do you need a "Grace Period" after switching schedulers?
**Answer:** Immediately after switching CPU schedulers, the system experiences transient cache migration and runqueue rebalancing overhead. If we evaluated SLO compliance during the first 1–2 seconds, transient spikes would cause false-positive rollbacks. The 5-second grace period allows the new scheduler to stabilize before monitoring begins.

#### Q8: What happens during a Watchdog "Cooldown" period?
**Answer:** After an SLO violation triggers a rollback to the default scheduler, the system enters a 60-second cooldown state. During cooldown, the bandit agent is forbidden from switching schedulers. This prevents rapid oscillation (thrashing) between schedulers while the workload remains hostile.

#### Q9: How is the reward value computed from metrics?
**Answer:** We normalize latency (inversely, so lower latency yields higher reward), throughput (higher is better), and CPU utilization (proximity to 70% target) into $[0, 1]$ bounds. We then calculate a weighted average based on user priorities (defaulting to 40% latency, 35% throughput, 25% utilization).

#### Q10: What is the difference between an SLO violation and a Health Checker failure?
**Answer:** An SLO constraint is user-defined performance expectations (e.g., $p99 \le 5000\mu s$ in `interactive.yaml`). Violating an SLO means performance has degraded below desired service levels, triggering a rollback. The Health Checker monitors absolute physical limits (e.g., CPU utilization $>98\%$ or context switches $>200,000$/sec) to block switches when the operating system is already thrashing.

#### Q11: What is the difference between Module A and Module B in your project division?
**Answer:**
- **Module B (Arjun Tyagi)**: Core engine orchestrator, SLO Watchdog state machine, rollback manager, health checker, Rich CLI, and Flask Web Dashboard.
- **Module A (Aritra Ghosh)**: Multi-armed bandit learning algorithms (UCB1, Thompson, $\epsilon$-greedy), reward normalization computer, C metrics collector (`/proc` and `perf_event_open`), and BPF loader bridge.

#### Q12: How does your demo work on Windows when `sched_ext` is a Linux kernel feature?
**Answer:** The architecture uses strict Abstract Base Classes (`ISchedulerManager`, `IMetricsCollector`). For demonstration and validation on non-Linux platforms, we built `MockSchedulerManager` and `MockMetricsCollector`, which faithfully simulate eBPF attach latency (20ms) and empirical metric distributions with noise, drift, and spike injection. The core learning algorithms, watchdog state machine, engine loop, CLI, and dashboard run real, production code.

#### Q13: What hardware counters does the production C collector measure?
**Answer:** Using the Linux `perf_event_open()` system call, the collector reads hardware performance monitoring units (PMUs) for Instructions Per Cycle (IPC), L1 data cache misses, and Last Level Cache (LLC) misses, alongside parsing `/proc/schedstat` for runqueue latency and context switches.

#### Q14: What is tail latency ($p99$) and why is it critical in your SLO profiles?
**Answer:** While average latency measures typical performance, $p99$ tail latency represents the worst 1% of scheduling delays. For real-time applications like competitive gaming or high-frequency trading, average latency may look acceptable while tail latency spikes cause stuttering or dropped frames. Our watchdog explicitly monitors $p99$ latency.

#### Q15: If the system rolls back to the default scheduler, does the bandit learn from this failure?
**Answer:** Yes. The degraded metrics observed during the violation window yield an extremely low reward ($R \to 0.0$). This updates the bandit's running average for that arm downwards, penalizing it so the agent avoids picking it again under similar load conditions.

---

*This concludes the master technical roadmap and architectural manual for AdaptiveSched.*  
*Keep this document open for presentation defense, codebase review, and viva examination preparation!*
