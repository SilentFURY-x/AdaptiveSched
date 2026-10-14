# AdaptiveSched — Presentation Script (Review 2)

> **Presenters:** Arjun Tyagi (24BCE0605) & Aritra Ghosh (24BCE0598)  
> **Duration:** ~15 minutes  
> **Date:** October 15, 2026

---

## Slide 0: Title (30 seconds)

**[Show title slide]**

> "Good morning/afternoon. We're Arjun Tyagi and Aritra Ghosh, and today we're presenting our project **AdaptiveSched** — a self-tuning CPU scheduler selection system that uses online bandit learning and SLO-aware rollback. This is our Review 2 progress update."

---

## Slide 1: The Problem (2 minutes)

**[Show workload examples — gaming, compilation, servers]**

> "Modern operating systems like Linux use a **single CPU scheduler** — typically CFS or the newer EEVDF scheduler. But here's the problem: different workloads have fundamentally different scheduling needs."

> "A **gaming workload** needs ultra-low latency and high responsiveness. A **compilation workload** — like building the Linux kernel — needs maximum throughput. A **web server** needs fast context switching for handling many concurrent requests."

> "The Linux kernel's `sched_ext` framework, merged in kernel 6.12, actually allows loading different schedulers at runtime — schedulers like `scx_rusty`, `scx_lavd`, `scx_bpfland`. But here's the gap: **there's no automated way to decide which scheduler to use**. Users have to manually benchmark and pick."

> "Existing solutions like the ASA system rely on **offline-trained ML models** and **hardware-specific calibration tables**. They don't adapt to new environments."

---

## Slide 2: Our Solution (2 minutes)

**[Show architecture diagram]**

> "AdaptiveSched closes this gap. We treat scheduler selection as an **online multi-armed bandit problem**."

> "Think of it like this: each available scheduler is an **arm** of a slot machine. Our agent pulls arms — tries different schedulers — and uses the observed performance as a **reward signal** to learn which scheduler works best for the current workload. The key innovation is that this happens **online** — no offline training needed."

> "We use three bandit algorithms — **UCB1** as the default, plus **Thompson Sampling** and **ε-greedy** as alternatives. The reward is computed from real-time latency, throughput, and CPU utilization metrics."

> "But switching schedulers blindly is dangerous. That's why we built an **SLO Watchdog**. Users define Service Level Objectives — like 'keep P99 latency under 5ms'. After every scheduler switch, the watchdog monitors for violations and **automatically rolls back** to a safe scheduler if performance degrades."

---

## Slide 3: Architecture Deep-Dive (2 minutes)

**[Show system architecture diagram from PRD]**

> "Let me walk you through the architecture. The system has two main layers:"

> "**User Space** contains the core engine written in Python. This includes the Bandit Agent that selects schedulers, the SLO Watchdog that ensures safety, and the Scheduler Switch Manager that executes transitions. Above this sits our CLI interface and a real-time web dashboard."

> "**Kernel Boundary** is bridged by our C-based metrics collector. It reads from `/proc/stat` and `/proc/schedstat` for CPU utilization and scheduling latency, uses `perf_event_open()` for hardware counters like IPC and cache miss rates, and interacts with `sched_ext` to load BPF schedulers."

> "The Python-C bridge uses `ctypes` for zero-copy, low-overhead metric collection. This hybrid approach gives us the **performance of C where it matters** and the **flexibility of Python for the decision-making logic**."

---

## Slide 4: Work Division (1 minute)

**[Show work division table]**

> "We've divided the work cleanly along module boundaries."

> "**I (Arjun) own Module B**: the SLO Watchdog with violation detection and automatic rollback, the web dashboard for real-time visualization, the CLI interface, and the overall system integration framework."

> "**Aritra owns Module A**: the bandit agent algorithms — UCB1, Thompson Sampling, and ε-greedy — the reward computation system, and the C-based metrics collector with the Python bridge."

> "Both modules communicate through **well-defined abstract interfaces**. This means we can develop independently and integrate seamlessly. Right now, mock implementations stand in for Aritra's modules, allowing the full system to run end-to-end."

---

## Slide 5: Technical Deep-Dive — SLO Watchdog (2 minutes)

**[Show watchdog state machine diagram]**

> "Let me dive into the SLO Watchdog, which is my core contribution."

> "The watchdog operates as a **state machine** with five states: IDLE, GRACE_PERIOD, MONITORING, VIOLATION_DETECTED, and COOLDOWN."

> "When the agent switches to a new scheduler, the watchdog enters a **grace period** — by default 5 seconds — to let the new scheduler stabilize. Then it begins active monitoring."

> "During monitoring, it evaluates metrics against user-defined SLO constraints every second. If violations exceed a configurable threshold — say 3 consecutive violations — it triggers an **automatic rollback** to the safe default scheduler."

> "After rollback, a **cooldown period** prevents the agent from immediately switching back, avoiding oscillation. Every event is logged for auditability."

> "SLO profiles are defined in YAML — we have three presets: `interactive` for latency-sensitive workloads, `throughput` for batch processing, and `balanced` for general use."

---

## Slide 6: Live Demo (4 minutes)

**[Switch to terminal]**

> "Let me show you this running. We'll use **mock mode**, which simulates scheduler behavior and metrics without needing a real sched_ext kernel."

### Demo Script:

1. **Start the system:**
   ```bash
   python -m src.cli.main start --mode mock
   ```
   > "The agent is now running. You can see it's collecting metrics and making scheduler decisions."

2. **Check status:**
   ```bash
   python -m src.cli.main status
   ```
   > "Here we see the current scheduler, the agent's statistics, and the SLO compliance status."

3. **Open the dashboard:**
   ```bash
   python -m src.cli.main dashboard
   ```
   > "The web dashboard shows real-time metrics — CPU utilization, scheduling latency, throughput. The line charts update every second. Notice the scheduler indicator at the top and the SLO gauge."

4. **Trigger SLO violation:**
   > "Now I'll simulate a workload change that causes performance degradation..."
   
   > "Watch the SLO gauge turn yellow... red... and there — the watchdog detected 3 consecutive violations and triggered an **automatic rollback**. The system is now back on the default scheduler."

5. **Show history:**
   ```bash
   python -m src.cli.main history
   ```
   > "The history shows every scheduler switch, the metrics at that time, and the rollback event with the reason."

---

## Slide 7: Code Quality & Architecture (1 minute)

**[Show code structure briefly]**

> "A few things about our code quality:"

> "We follow **separation of concerns** — each module is self-contained with clear boundaries. The **interface pattern** means Aritra's real implementations will drop in without changing any of my code."

> "Everything is **typed** using Python dataclasses and type hints. Configuration is externalized in YAML files. The mock system accurately simulates real behavior including realistic metric distributions."

---

## Slide 8: Next Steps (1 minute)

**[Show roadmap]**

> "For the next review, our plan is:"

> "**Integration**: Merge Aritra's bandit agent and real C metrics collector with the existing framework."

> "**Real kernel testing**: Deploy on a Linux 6.12+ machine with sched_ext and test with real workloads — sysbench for throughput, hackbench for scheduling, schbench for latency."

> "**Paper update**: Add results sections with real benchmark data comparing UCB1, Thompson Sampling, and ε-greedy convergence rates."

---

## Slide 9: Q&A (remaining time)

> "Thank you. We're happy to take questions. We can also do a deeper dive into any specific component — the bandit algorithms, the watchdog state machine, or the dashboard."

---

## Backup Points (if asked)

### "Why not just use machine learning?"
> "ML models need offline training data and hardware-specific calibration. Our bandit approach learns online — it adapts to any machine from scratch. It's also mathematically simpler and has provable regret bounds."

### "How fast can it switch schedulers?"
> "sched_ext scheduler loading takes approximately 10-50ms. Our agent's decision loop runs every 5 seconds by default, so overhead is negligible."

### "What if the bandit makes a bad choice?"
> "That's exactly what the SLO Watchdog prevents. Even if the bandit explores a suboptimal scheduler, the watchdog will detect degradation within 10-15 seconds and roll back automatically."

### "How is this different from the ASA paper?"
> "Three key differences: (1) We use online learning instead of offline-trained models, (2) We have an SLO-aware safety mechanism that ASA lacks, (3) We don't need hardware-specific calibration tables."

### "Can it handle rapid workload changes?"
> "The bandit algorithms we use — especially Thompson Sampling — are designed for non-stationary environments. Combined with our sliding window metrics and configurable evaluation windows, the system adapts within 2-3 agent cycles."
