# Aritra's Implementation Plan — Module A: Bandit Agent + Metrics Collector

> **Historical plan.** The algorithms and reward computation below have since been implemented in Python, and the repository now includes an initial Python procfs collector and process-based Linux sched_ext manager. The original C/perf collector and ctypes bridge remain future work. See [MVP_STATUS.md](MVP_STATUS.md) for current status and limitations; this document is retained as the original task plan, not a current checklist.

> **Teammate:** Aritra Ghosh (24BCE0598)  
> **Module:** Bandit Agent + Metrics Collector  
> **Deadline:** Final Submission  
> **Integration with:** Arjun's Module B (SLO Watchdog + Dashboard + CLI)

---

## 1. Overview

You own the **intelligent core** of AdaptiveSched — the part that collects real system metrics and makes smart scheduler decisions using multi-armed bandit algorithms. Arjun has built the safety layer (SLO Watchdog), the user interfaces (Dashboard + CLI), and the system integration framework with **mock implementations** of your modules.

Your job: **replace the mocks with real implementations** that conform to the existing interfaces.

---

## 2. What Arjun Has Built (Already Done)

- ✅ Project scaffolding and architecture
- ✅ Abstract interfaces in `src/interfaces/` — **these are your contracts**
- ✅ `MockMetricsCollector` in `src/metrics/mock_metrics.py` — your real collector replaces this
- ✅ `MockBanditAgent` in `src/agent/mock_agent.py` — your real agent replaces this
- ✅ SLO Watchdog + Rollback system
- ✅ Web Dashboard + CLI
- ✅ Core engine that orchestrates everything
- ✅ Configuration system

---

## 3. Your Implementation Tasks

### 3.1 Task 1: C Metrics Collector (P0 — Do First)

**Files to create:**
- `src/metrics/proc_parser.c` — Parse `/proc/stat`, `/proc/schedstat`, `/proc/loadavg`
- `src/metrics/perf_collector.c` — Use `perf_event_open()` for hardware counters
- `src/metrics/metrics_lib.h` — Header file with shared structures
- `src/metrics/Makefile` — Build the C shared library

**What to implement in `proc_parser.c`:**

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Structure matching Python's SystemMetrics
typedef struct {
    double cpu_utilization;      // Parse from /proc/stat (calculate delta)
    long context_switches;       // "ctxt" line in /proc/stat
    double scheduling_latency_us; // From /proc/schedstat
    double runqueue_length;       // From /proc/schedstat
    double load_avg_1min;         // From /proc/loadavg
} ProcMetrics;

// Parse /proc/stat for CPU utilization
// Algorithm:
//   1. Read cpu line: "cpu user nice system idle iowait irq softirq steal"
//   2. total = user + nice + system + idle + iowait + irq + softirq + steal
//   3. idle_total = idle + iowait
//   4. cpu_util = 1 - (delta_idle / delta_total) between two samples
int parse_proc_stat(ProcMetrics *metrics);

// Parse /proc/schedstat for scheduling latency
// Format per CPU: "cpu<N> <yld_count> <sched_count> <sched_goidle> ..."
// We care about run_delay (nanoseconds tasks waited in runqueue)
int parse_proc_schedstat(ProcMetrics *metrics);

// Parse /proc/loadavg
int parse_proc_loadavg(ProcMetrics *metrics);
```

**What to implement in `perf_collector.c`:**

```c
#include <linux/perf_event.h>
#include <sys/syscall.h>
#include <unistd.h>

typedef struct {
    double ipc;                 // instructions / cycles
    double cache_miss_rate;     // LLC misses / LLC references
    long context_switches_hw;   // HW counter for ctx switches
} PerfMetrics;

// Open perf events using perf_event_open() syscall
// Events to monitor:
//   PERF_COUNT_HW_INSTRUCTIONS
//   PERF_COUNT_HW_CPU_CYCLES
//   PERF_COUNT_HW_CACHE_MISSES
//   PERF_COUNT_HW_CACHE_REFERENCES
//   PERF_COUNT_SW_CONTEXT_SWITCHES
int perf_init(void);

// Read all counters and compute derived metrics
int perf_collect(PerfMetrics *metrics);

// Clean up perf file descriptors
void perf_cleanup(void);
```

**Build system (`Makefile`):**

```makefile
CC = gcc
CFLAGS = -shared -fPIC -O2 -Wall
TARGET = libmetrics.so

all: $(TARGET)

$(TARGET): proc_parser.c perf_collector.c
	$(CC) $(CFLAGS) -o $(TARGET) proc_parser.c perf_collector.c

clean:
	rm -f $(TARGET)
```

---

### 3.2 Task 2: Python-C Bridge (P0)

**File to create:** `src/metrics/metrics_bridge.py`

This must implement the `IMetricsCollector` interface from `src/interfaces/metrics_interface.py`.

```python
"""Bridge between C metrics library and Python using ctypes."""
import ctypes
import os
from src.interfaces.metrics_interface import IMetricsCollector
from src.core.models import SystemMetrics

class CMetricsCollector(IMetricsCollector):
    """Real metrics collector using C shared library."""
    
    def __init__(self):
        lib_path = os.path.join(os.path.dirname(__file__), 'libmetrics.so')
        self._lib = ctypes.CDLL(lib_path)
        # Define C structures using ctypes
        # Map to ProcMetrics and PerfMetrics structs
        self._setup_ctypes()
    
    def _setup_ctypes(self):
        """Set up ctypes structures matching C structs."""
        class ProcMetrics(ctypes.Structure):
            _fields_ = [
                ("cpu_utilization", ctypes.c_double),
                ("context_switches", ctypes.c_long),
                ("scheduling_latency_us", ctypes.c_double),
                ("runqueue_length", ctypes.c_double),
                ("load_avg_1min", ctypes.c_double),
            ]
        
        class PerfMetrics(ctypes.Structure):
            _fields_ = [
                ("ipc", ctypes.c_double),
                ("cache_miss_rate", ctypes.c_double),
                ("context_switches_hw", ctypes.c_long),
            ]
        
        self._ProcMetrics = ProcMetrics
        self._PerfMetrics = PerfMetrics
        
        # Set return types
        self._lib.parse_proc_stat.argtypes = [ctypes.POINTER(ProcMetrics)]
        self._lib.parse_proc_stat.restype = ctypes.c_int
        # ... same for other functions
    
    def collect(self) -> SystemMetrics:
        """Collect real system metrics."""
        proc = self._ProcMetrics()
        perf = self._PerfMetrics()
        
        self._lib.parse_proc_stat(ctypes.byref(proc))
        self._lib.parse_proc_schedstat(ctypes.byref(proc))
        self._lib.perf_collect(ctypes.byref(perf))
        
        return SystemMetrics(
            cpu_utilization=proc.cpu_utilization,
            context_switches=proc.context_switches,
            scheduling_latency_us=proc.scheduling_latency_us,
            ipc=perf.ipc,
            cache_miss_rate=perf.cache_miss_rate,
            runqueue_length=proc.runqueue_length,
            throughput_ops=0.0,  # from workload-specific probes
            p99_latency_us=proc.scheduling_latency_us * 2.5,  # estimate
        )
    
    def start(self) -> None:
        self._lib.perf_init()
    
    def stop(self) -> None:
        self._lib.perf_cleanup()
```

---

### 3.3 Task 3: Bandit Algorithms (P0)

**Files to create:**

#### `src/agent/bandit_base.py` — Abstract Base

```python
from abc import ABC, abstractmethod
from typing import List

class BanditBase(ABC):
    """Abstract base class for multi-armed bandit algorithms."""
    
    def __init__(self, arms: List[str]):
        self.arms = arms
        self.counts = {arm: 0 for arm in arms}
        self.rewards = {arm: 0.0 for arm in arms}
    
    @abstractmethod
    def select_arm(self) -> str:
        """Select the next arm to pull."""
        ...
    
    def update(self, arm: str, reward: float) -> None:
        """Update statistics after observing a reward."""
        self.counts[arm] += 1
        n = self.counts[arm]
        # Incremental mean update
        self.rewards[arm] += (reward - self.rewards[arm]) / n
    
    def get_statistics(self) -> dict:
        return {
            "counts": dict(self.counts),
            "avg_rewards": dict(self.rewards),
        }
```

#### `src/agent/ucb1.py` — UCB1 Algorithm

```python
import math
from .bandit_base import BanditBase

class UCB1(BanditBase):
    """Upper Confidence Bound v1 algorithm.
    
    UCB1 balances exploration and exploitation by selecting the arm
    with the highest upper confidence bound:
    
        UCB(a) = avg_reward(a) + c * sqrt(ln(total_pulls) / pulls(a))
    
    where c is the exploration parameter (default sqrt(2)).
    """
    
    def __init__(self, arms, exploration_param=None):
        super().__init__(arms)
        self.c = exploration_param or math.sqrt(2)
    
    def select_arm(self) -> str:
        total = sum(self.counts.values())
        
        # Pull each arm at least once
        for arm in self.arms:
            if self.counts[arm] == 0:
                return arm
        
        # Compute UCB scores
        ucb_scores = {}
        for arm in self.arms:
            exploitation = self.rewards[arm]
            exploration = self.c * math.sqrt(math.log(total) / self.counts[arm])
            ucb_scores[arm] = exploitation + exploration
        
        return max(ucb_scores, key=ucb_scores.get)
```

#### `src/agent/thompson_sampling.py` — Thompson Sampling

```python
import random
from .bandit_base import BanditBase

class ThompsonSampling(BanditBase):
    """Thompson Sampling with Beta distribution priors.
    
    For each arm, maintains a Beta(α, β) distribution.
    Samples from each arm's distribution and selects the maximum.
    
    Since rewards are [0, 1], we use Bernoulli likelihood with
    Beta conjugate prior.
    """
    
    def __init__(self, arms):
        super().__init__(arms)
        self.alpha = {arm: 1.0 for arm in arms}  # successes + 1
        self.beta_param = {arm: 1.0 for arm in arms}   # failures + 1
    
    def select_arm(self) -> str:
        samples = {}
        for arm in self.arms:
            samples[arm] = random.betavariate(
                self.alpha[arm], self.beta_param[arm]
            )
        return max(samples, key=samples.get)
    
    def update(self, arm: str, reward: float) -> None:
        super().update(arm, reward)
        # Update Beta parameters
        # Treat reward as probability of success
        if random.random() < reward:
            self.alpha[arm] += 1
        else:
            self.beta_param[arm] += 1
```

#### `src/agent/epsilon_greedy.py` — ε-Greedy with Decay

```python
import random
from .bandit_base import BanditBase

class EpsilonGreedy(BanditBase):
    """ε-greedy algorithm with exponential decay.
    
    With probability ε, explore (random arm).
    With probability 1-ε, exploit (best known arm).
    ε decays over time: ε_t = ε_0 * decay^t
    """
    
    def __init__(self, arms, epsilon=0.3, decay=0.995, min_epsilon=0.01):
        super().__init__(arms)
        self.epsilon_0 = epsilon
        self.epsilon = epsilon
        self.decay = decay
        self.min_epsilon = min_epsilon
        self.t = 0
    
    def select_arm(self) -> str:
        self.t += 1
        self.epsilon = max(
            self.min_epsilon,
            self.epsilon_0 * (self.decay ** self.t)
        )
        
        if random.random() < self.epsilon:
            return random.choice(self.arms)
        
        # Exploit: pick best arm (with random tiebreaking)
        if all(self.counts[a] == 0 for a in self.arms):
            return random.choice(self.arms)
        
        return max(self.arms, key=lambda a: self.rewards.get(a, 0))
```

---

### 3.4 Task 4: Reward Computation (P0)

**File to create:** `src/agent/reward.py`

```python
"""Reward computation from system metrics.

The reward function maps system metrics to a scalar [0, 1] value
that the bandit algorithm uses to learn which scheduler is best.
"""

from src.core.models import SystemMetrics

class RewardComputer:
    """Computes reward from system metrics."""
    
    def __init__(self, weights=None):
        self.weights = weights or {
            'latency': 0.4,
            'throughput': 0.35,
            'utilization': 0.25,
        }
        # Running min/max for normalization
        self._latency_range = (100, 50000)    # μs
        self._throughput_range = (1000, 50000)  # ops/s
        self._util_range = (0, 100)             # %
    
    def compute(self, metrics: SystemMetrics) -> float:
        """Compute reward in [0, 1] from metrics."""
        # Normalize each metric to [0, 1]
        norm_latency = self._normalize(
            metrics.scheduling_latency_us,
            *self._latency_range
        )
        norm_throughput = self._normalize(
            metrics.throughput_ops,
            *self._throughput_range
        )
        norm_util = self._normalize(
            metrics.cpu_utilization,
            *self._util_range
        )
        
        # Lower latency is better → invert
        reward = (
            self.weights['latency'] * (1.0 - norm_latency) +
            self.weights['throughput'] * norm_throughput +
            self.weights['utilization'] * (1.0 - abs(norm_util - 0.7))
            # Prefer ~70% utilization (not too idle, not saturated)
        )
        
        return max(0.0, min(1.0, reward))
    
    def _normalize(self, value, min_val, max_val):
        """Normalize value to [0, 1]."""
        if max_val == min_val:
            return 0.5
        return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))
```

---

### 3.5 Task 5: Agent Engine (P0)

**File to create:** `src/agent/agent_engine.py`

This must implement the `ISchedulerAgent` interface.

```python
"""Main agent engine that ties bandit + metrics + reward together."""

from src.interfaces.agent_interface import ISchedulerAgent
from src.core.models import SystemMetrics, AgentStatistics
from .ucb1 import UCB1
from .thompson_sampling import ThompsonSampling
from .epsilon_greedy import EpsilonGreedy
from .reward import RewardComputer

class BanditAgent(ISchedulerAgent):
    """Real bandit agent implementation."""
    
    def __init__(self, schedulers, algorithm='ucb1', reward_weights=None):
        self.schedulers = schedulers
        self.reward_computer = RewardComputer(reward_weights)
        
        # Initialize chosen algorithm
        if algorithm == 'ucb1':
            self.bandit = UCB1(schedulers)
        elif algorithm == 'thompson':
            self.bandit = ThompsonSampling(schedulers)
        elif algorithm == 'epsilon_greedy':
            self.bandit = EpsilonGreedy(schedulers)
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")
    
    def select_scheduler(self, metrics: SystemMetrics) -> str:
        """Use bandit algorithm to select next scheduler."""
        return self.bandit.select_arm()
    
    def update_reward(self, scheduler: str, reward: float) -> None:
        """Update bandit with observed reward."""
        self.bandit.update(scheduler, reward)
    
    def compute_reward(self, metrics: SystemMetrics) -> float:
        """Compute reward from metrics."""
        return self.reward_computer.compute(metrics)
    
    def get_statistics(self) -> AgentStatistics:
        stats = self.bandit.get_statistics()
        return AgentStatistics(
            algorithm=type(self.bandit).__name__,
            total_pulls=sum(stats['counts'].values()),
            arm_counts=stats['counts'],
            arm_rewards=stats['avg_rewards'],
        )
```

---

## 4. How to Integrate

Once you've implemented all the above:

### Step 1: Build the C library

```bash
cd src/metrics/
make
```

### Step 2: Update config to use real implementations

Edit `config/adaptivesched.yaml`:

```yaml
mode: "real"  # Change from "mock" to "real"
agent:
  implementation: "ucb1"  # or "thompson" or "epsilon_greedy"
metrics:
  implementation: "proc"  # or "perf"
```

### Step 3: Test with mock first

```bash
# Arjun's mock mode should still work
python -m src.cli.main start --mode mock

# Then test with your real implementations
python -m src.cli.main start --mode real
```

### Step 4: Run integration tests

```bash
pytest tests/ -v
```

---

## 5. Interface Contracts (DO NOT CHANGE)

These interfaces are defined in `src/interfaces/` and are the **contract** between our modules. Do NOT modify them without discussing with Arjun first.

### `IMetricsCollector` — Your collector must implement:
```python
class IMetricsCollector(ABC):
    def collect(self) -> SystemMetrics: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

### `ISchedulerAgent` — Your agent must implement:
```python
class ISchedulerAgent(ABC):
    def select_scheduler(self, metrics: SystemMetrics) -> str: ...
    def update_reward(self, scheduler: str, reward: float) -> None: ...
    def get_statistics(self) -> AgentStatistics: ...
```

---

## 6. Checklist

- [ ] `proc_parser.c` — Parses `/proc/stat`, `/proc/schedstat`, `/proc/loadavg`
- [ ] `perf_collector.c` — Uses `perf_event_open()` for HW counters
- [ ] `metrics_lib.h` — Header with shared C structures
- [ ] `Makefile` — Builds `libmetrics.so`
- [ ] `metrics_bridge.py` — Python-C bridge implementing `IMetricsCollector`
- [ ] `bandit_base.py` — Abstract bandit base class
- [ ] `ucb1.py` — UCB1 algorithm
- [ ] `thompson_sampling.py` — Thompson Sampling
- [ ] `epsilon_greedy.py` — ε-greedy with decay
- [ ] `reward.py` — Reward computation
- [ ] `agent_engine.py` — Main agent implementing `ISchedulerAgent`
- [ ] Unit tests for all bandit algorithms
- [ ] Integration test with Arjun's engine

---

## 7. References

- [UCB1 Paper](https://homes.di.unimi.it/~cesabian/Pubblicazioni/ml-02.pdf) — Auer et al., "Finite-time Analysis of the Multiarmed Bandit Problem"
- [Thompson Sampling Tutorial](https://arxiv.org/abs/1707.02038) — Russo et al.
- [perf_event_open man page](https://man7.org/linux/man-pages/man2/perf_event_open.2.html)
- [/proc/stat format](https://man7.org/linux/man-pages/man5/proc.5.html)
- [sched_ext documentation](https://docs.kernel.org/scheduler/sched-ext.html)

---

> **Questions?** Reach out to Arjun. The mock implementations in `src/metrics/mock_metrics.py` and `src/agent/mock_agent.py` show exactly what behavior is expected.
