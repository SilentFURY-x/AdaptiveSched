/**
 * AdaptiveSched Dashboard — Frontend Client Logic
 * Real-time metric streaming, Chart.js updates, interactive scheduler controls,
 * and SLO watchdog state monitoring.
 */

// Global State
let latencyChart = null;
let systemChart = null;
let banditChart = null;
let isPaused = false;
let currentScheduler = 'default';
let availableSchedulers = [];
let updateInterval = null;
let historyUpdateInterval = null;

// Initialize on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    initMotionSystem();
    fetchInitialData();
    updateInterval = setInterval(pollMetrics, 1000);
    historyUpdateInterval = setInterval(() => {
        refreshHistory();
        refreshEvents();
    }, 3000);
});

/* ---------------------------------------------------------
   Motion: Lenis is the sole smooth-scroll engine; GSAP owns reveals.
   Reduced-motion users keep native scrolling and see every final state.
   --------------------------------------------------------- */
function initMotionSystem() {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduceMotion || !window.gsap || !window.ScrollTrigger) return;

    const { gsap, ScrollTrigger } = window;
    gsap.registerPlugin(ScrollTrigger);

    let lenis = null;
    let ticker = null;
    if (window.Lenis) {
        lenis = new window.Lenis({ duration: 0.85, smoothWheel: true, touchMultiplier: 1.15 });
        lenis.on('scroll', ScrollTrigger.update);
        ticker = (time) => lenis.raf(time * 1000);
        gsap.ticker.add(ticker);
        gsap.ticker.lagSmoothing(0);
        window.__adaptiveSchedLenis = lenis;
    }

    window.addEventListener('pagehide', () => {
        clearInterval(updateInterval);
        clearInterval(historyUpdateInterval);
        ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
        if (lenis) lenis.destroy();
        if (ticker) gsap.ticker.remove(ticker);
    }, { once: true });
}

/* ---------------------------------------------------------
   Chart Initialization
   --------------------------------------------------------- */
function initCharts() {
    const commonChartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 350 },
        scales: {
            x: {
                display: false,
                grid: { display: false }
            },
            y: {
                grid: { color: '#e3e8ed' },
                ticks: { color: '#738091', font: { family: 'ui-monospace, Consolas, monospace', size: 10 } }
            }
        },
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: '#293746',
                titleColor: '#ffffff',
                bodyColor: '#d8e0e8',
                borderColor: '#415263',
                borderWidth: 1,
                padding: 10
            }
        }
    };

    // 1. Latency Chart (Latency + SLO Max Line)
    const ctxLatency = document.getElementById('latencyChart').getContext('2d');
    latencyChart = new Chart(ctxLatency, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'P99 workload latency (μs)',
                    data: [],
                    borderColor: '#356da8',
                    backgroundColor: 'rgba(53, 109, 168, 0.09)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.35,
                    pointRadius: 2,
                    pointHoverRadius: 5
                },
                {
                    label: 'SLO Ceiling (μs)',
                    data: [],
                    borderColor: '#c87535',
                    borderWidth: 1.5,
                    borderDash: [5, 5],
                    fill: false,
                    pointRadius: 0
                }
            ]
        },
        options: {
            ...commonChartOptions,
            scales: {
                ...commonChartOptions.scales,
                y: {
                    ...commonChartOptions.scales.y,
                    suggestedMin: 0,
                    suggestedMax: 6000,
                    title: { display: true, text: 'Microseconds (μs)', color: '#738091', font: { size: 10 } }
                }
            }
        }
    });

    // 2. System Performance Chart (CPU % & Throughput)
    const ctxSystem = document.getElementById('systemChart').getContext('2d');
    systemChart = new Chart(ctxSystem, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'CPU (%)',
                    data: [],
                    borderColor: '#718096',
                    backgroundColor: 'rgba(113, 128, 150, 0.09)',
                    borderWidth: 2,
                    yAxisID: 'yCPU',
                    fill: true,
                    tension: 0.35,
                    pointRadius: 2
                },
                {
                    label: 'Throughput (ops/s)',
                    data: [],
                    borderColor: '#4d82b6',
                    borderWidth: 2,
                    yAxisID: 'yThroughput',
                    fill: false,
                    tension: 0.35,
                    pointRadius: 2
                }
            ]
        },
        options: {
            ...commonChartOptions,
            scales: {
                x: { display: false },
                yCPU: {
                    type: 'linear',
                    position: 'left',
                    min: 0,
                    max: 100,
                    grid: { color: '#e3e8ed' },
                    ticks: { color: '#718096', font: { family: 'ui-monospace, Consolas, monospace', size: 10 } }
                },
                yThroughput: {
                    type: 'linear',
                    position: 'right',
                    min: 0,
                    grid: { display: false },
                    ticks: { color: '#4d82b6', font: { family: 'ui-monospace, Consolas, monospace', size: 10 } }
                }
            }
        }
    });

    // 3. Bandit Arms Bar Chart
    const ctxBandit = document.getElementById('banditChart').getContext('2d');
    banditChart = new Chart(ctxBandit, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Estimated Reward',
                data: [],
                backgroundColor: [
                    'rgba(53, 109, 168, 0.78)',
                    'rgba(75, 130, 182, 0.72)',
                    'rgba(113, 128, 150, 0.70)',
                    'rgba(200, 117, 53, 0.72)',
                    'rgba(160, 171, 182, 0.72)'
                ],
                borderColor: [
                    '#356da8', '#4d82b6', '#718096', '#c87535', '#a0abb6'
                ],
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            ...commonChartOptions,
            scales: {
                x: {
                    ticks: { color: '#657385', font: { family: 'ui-monospace, Consolas, monospace', size: 10 } },
                    grid: { display: false }
                },
                y: {
                    min: 0,
                    max: 1.0,
                    ticks: { color: '#738091', font: { family: 'ui-monospace, Consolas, monospace', size: 10 } },
                    grid: { color: '#e3e8ed' }
                }
            }
        }
    });
}

/* ---------------------------------------------------------
   Data Fetching & Polling
   --------------------------------------------------------- */
async function fetchInitialData() {
    await Promise.all([
        pollMetrics(),
        refreshSloProfile(),
        refreshHistory(),
        refreshEvents()
    ]);
}

async function pollMetrics() {
    try {
        const [statusRes, metricsRes] = await Promise.all([
            fetch('/api/status'),
            fetch('/api/metrics?limit=30')
        ]);

        if (statusRes.ok) {
            const status = await statusRes.json();
            updateStatusUI(status);
        }

        if (metricsRes.ok) {
            const metrics = await metricsRes.json();
            updateChartsWithMetrics(metrics);
        }
    } catch (err) {
        console.warn('Dashboard poll error:', err);
    }
}

/* ---------------------------------------------------------
   UI State Updates
   --------------------------------------------------------- */
function updateStatusUI(status) {
    if (!status || status.error) return;

    // Header Badges
    document.getElementById('system-mode-badge').textContent = (status.mode || 'mock').toUpperCase() + ' MODE';
    document.getElementById('system-algo-badge').textContent = 'ALGO: ' + (status.algorithm || 'ucb1').toUpperCase();
    
    isPaused = status.paused;
    const agentBadge = document.getElementById('agent-state-badge');
    const pauseIcon = document.getElementById('pause-icon');
    const pauseText = document.getElementById('pause-text');

    if (status.paused) {
        agentBadge.textContent = 'AGENT PAUSED';
        agentBadge.className = 'badge badge-algo';
        pauseIcon.textContent = '▶';
        pauseText.textContent = 'Resume Agent';
    } else {
        agentBadge.textContent = 'AGENT ACTIVE';
        agentBadge.className = 'badge badge-status pulse';
        pauseIcon.textContent = '⏸';
        pauseText.textContent = 'Pause Agent';
    }

    // Uptime & Cycles
    document.getElementById('uptime-val').textContent = formatSeconds(status.uptime_seconds || 0);
    document.getElementById('cycle-count-val').textContent = status.cycle_count || 0;
    // Active Scheduler
    currentScheduler = status.current_scheduler || 'default';
    document.getElementById('active-scheduler-name').textContent = currentScheduler;
    
    const switchesCount = (status.agent_stats && status.agent_stats.total_switches) ? status.agent_stats.total_switches : 0;
    document.getElementById('scheduler-switch-meta').textContent = `Switches: ${switchesCount} | Active: ${currentScheduler}`;

    // Available schedulers pills & switch buttons
    if (status.available_schedulers && JSON.stringify(status.available_schedulers) !== JSON.stringify(availableSchedulers)) {
        availableSchedulers = status.available_schedulers;
        renderSchedulerButtons(availableSchedulers);
    }
    updateActiveSchedulerHighlights(currentScheduler);

    // Current Metrics KPI
    if (status.current_metrics) {
        const m = status.current_metrics;
        // CPU
        const cpu = (m.cpu_utilization || 0).toFixed(1);
        document.getElementById('cpu-val').textContent = cpu;
        document.getElementById('cpu-bar').style.width = Math.min(100, Math.max(0, cpu)) + '%';
        
        // Latency
        const lat = Math.round(m.p99_latency_us ?? m.scheduling_latency_us ?? 0);
        document.getElementById('latency-val').textContent = lat.toLocaleString();
        
        // Throughput & CS
        document.getElementById('throughput-val').textContent = Math.round(m.throughput_ops || 0).toLocaleString();
        document.getElementById('cs-val').textContent = Math.round(m.context_switches || 0).toLocaleString();
        document.getElementById('run-queue-val').textContent = Number(m.runqueue_length || 0).toFixed(1);
    }

    // SLO Compliance & Watchdog State
    const compliance = (status.compliance !== undefined) ? status.compliance.toFixed(1) : '100.0';
    document.getElementById('slo-score-val').textContent = compliance;

    const wdState = (status.watchdog && status.watchdog.state) ? status.watchdog.state : 'idle';
    updateWatchdogPipeline(wdState, status.watchdog);

    // Bandit arm chart data update
    if (status.agent_stats && status.agent_stats.arm_estimates) {
        updateBanditChart(status.agent_stats.arm_estimates, status.agent_stats.arm_pulls || {});
    }
}

function updateWatchdogPipeline(state, wd) {
    const stateKeys = {
        IDLE: 'idle',
        GRACE_PERIOD: 'grace',
        MONITORING: 'monitor',
        VIOLATION_DETECTED: 'violation',
        COOLDOWN: 'cooldown'
    };
    const stateKey = stateKeys[String(state || 'IDLE').toUpperCase()] || 'idle';
    const wdBadge = document.getElementById('watchdog-state-badge');
    wdBadge.textContent = 'STATE: ' + stateKey.toUpperCase();
    wdBadge.className = 'state-badge state-' + (stateKey === 'monitor' ? 'monitoring' : stateKey);

    const healthTag = document.getElementById('watchdog-health-tag');
    healthTag.classList.remove('tag-success', 'tag-warning', 'tag-danger');
    if (stateKey === 'violation') {
        healthTag.textContent = 'SLO BREACH';
        healthTag.classList.add('tag-danger');
    } else if (stateKey === 'cooldown') {
        healthTag.textContent = 'COOLDOWN';
        healthTag.classList.add('tag-warning');
    } else {
        healthTag.textContent = 'HEALTHY';
        healthTag.classList.add('tag-success');
    }

    // Steps list
    const steps = ['idle', 'grace', 'monitor', 'violation', 'cooldown'];
    steps.forEach(s => {
        const el = document.getElementById('step-' + s);
        if (el) {
            el.classList.remove('active', 'step-violation-active');
            if (s === stateKey) {
                el.classList.add('active');
                if (s === 'violation') {
                    el.classList.add('step-violation-active');
                }
            }
        }
    });

    // Counts
    if (wd) {
        const vCount = wd.consecutive_violations || 0;
        const vThresh = wd.violation_threshold || 3;
        document.getElementById('wd-violation-count').textContent = `${vCount} / ${vThresh}`;
        document.getElementById('wd-rollback-count').textContent = wd.total_rollbacks || 0;
    }
}

function updateChartsWithMetrics(metricsList) {
    if (!metricsList || metricsList.length === 0) return;

    const labels = metricsList.map(m => new Date(m.timestamp * 1000).toLocaleTimeString([], { hour12: false }));
    const latencies = metricsList.map(m => m.p99_latency_us ?? m.scheduling_latency_us ?? 0);
    const cpus = metricsList.map(m => m.cpu_utilization);
    const throughputs = metricsList.map(m => m.throughput_ops);

    // Retrieve active profile target latency (default 5000 if not loaded)
    const targetLatency = window._activeSloMaxLatency || 5000;
    const targetLine = metricsList.map(() => targetLatency);

    // 1. Update Latency Chart
    if (latencyChart) {
        latencyChart.data.labels = labels;
        latencyChart.data.datasets[0].data = latencies;
        latencyChart.data.datasets[1].data = targetLine;
        latencyChart.update('none');
    }

    // 2. Update System Chart
    if (systemChart) {
        systemChart.data.labels = labels;
        systemChart.data.datasets[0].data = cpus;
        systemChart.data.datasets[1].data = throughputs;
        systemChart.update('none');
    }

    // Update latency compliance status tag
    const latestLatency = latencies[latencies.length - 1] || 0;
    const latTag = document.getElementById('latency-status-tag');
    if (latestLatency > targetLatency) {
        latTag.className = 'tag tag-danger';
        latTag.textContent = 'VIOLATION';
    } else {
        latTag.className = 'tag tag-success';
        latTag.textContent = 'COMPLIANT';
    }
}

function updateBanditChart(estimates, pulls) {
    if (!banditChart) return;
    const labels = Object.keys(estimates);
    const data = labels.map(l => estimates[l] || 0);

    banditChart.data.labels = labels.map(l => `${l} (n=${pulls[l] || 0})`);
    banditChart.data.datasets[0].data = data;
    banditChart.update('none');
}

/* ---------------------------------------------------------
   Scheduler Switch Controls
   --------------------------------------------------------- */
function renderSchedulerButtons(schedulers) {
    const listEl = document.getElementById('schedulers-pill-list');
    const btnsEl = document.getElementById('scheduler-switch-buttons');

    if (listEl) {
        listEl.innerHTML = schedulers.map(s => `
            <span class="sched-pill" id="pill-${s}">${s}</span>
        `).join('');
    }

    if (btnsEl) {
        btnsEl.innerHTML = schedulers.map(s => `
            <button class="btn-scheduler" id="btn-sched-${s}" onclick="manualSwitch('${s}')">
                ${s}
            </button>
        `).join('');
    }
}

function updateActiveSchedulerHighlights(active) {
    availableSchedulers.forEach(s => {
        const pill = document.getElementById(`pill-${s}`);
        if (pill) {
            pill.classList.toggle('active', s === active);
        }
        const btn = document.getElementById(`btn-sched-${s}`);
        if (btn) {
            btn.classList.toggle('active', s === active);
        }
    });
}

async function manualSwitch(schedulerName) {
    try {
        const res = await fetch('/api/switch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scheduler: schedulerName })
        });
        const data = await res.json();
        if (data.success) {
            showToast(`Switched to scheduler: ${schedulerName}`, 'success');
            pollMetrics();
            refreshHistory();
        } else {
            showToast(data.message || 'Switch failed', 'error');
        }
    } catch (e) {
        showToast('Error switching scheduler: ' + e.message, 'error');
    }
}

/* ---------------------------------------------------------
   SLO Profile Management
   --------------------------------------------------------- */
async function refreshSloProfile() {
    try {
        const res = await fetch('/api/slo');
        if (res.ok) {
            const data = await res.json();
            document.getElementById('active-profile-name').textContent = data.profile || 'balanced';
            const select = document.getElementById('slo-profile-select');
            if (select) select.value = data.profile || 'balanced';

            // Find latency & CPU constraints
            let maxLatency = 5000;
            let maxCpu = 90;
            if (data.constraints) {
                data.constraints.forEach(c => {
                    if (c.name === 'p99_latency_us' || c.name.includes('latency')) maxLatency = c.max;
                    if (c.name === 'cpu_utilization' || c.name.includes('cpu')) maxCpu = c.max;
                });
            }

            window._activeSloMaxLatency = maxLatency;
            document.getElementById('latency-target-val').textContent = maxLatency;
            document.getElementById('profile-max-latency').textContent = `${maxLatency} μs`;
            document.getElementById('profile-max-cpu').textContent = `${maxCpu}%`;
            document.getElementById('profile-threshold').textContent = `${data.violation_threshold || 3} cycles`;
        }
    } catch (err) {
        console.warn('Failed to load SLO details:', err);
    }
}

async function changeSloProfile(profileName) {
    try {
        const res = await fetch('/api/slo/set', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile: profileName })
        });
        const data = await res.json();
        if (data.success) {
            showToast(`SLO Profile updated to: ${profileName}`, 'success');
            refreshSloProfile();
        } else {
            showToast('Failed to change SLO profile', 'error');
        }
    } catch (e) {
        showToast('Error updating SLO profile: ' + e.message, 'error');
    }
}

/* ---------------------------------------------------------
   Spike & Anomaly Trigger
   --------------------------------------------------------- */
async function triggerSpike(duration = 30) {
    try {
        const res = await fetch('/api/spike', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ duration: duration })
        });
        const data = await res.json();
        showToast(`⚡ Workload spike triggered for ${duration}s! Watch watchdog for SLO rollback.`, 'warning');
        setTimeout(pollMetrics, 500);
    } catch (e) {
        showToast('Failed to trigger spike: ' + e.message, 'error');
    }
}

/* ---------------------------------------------------------
   Pause / Resume
   --------------------------------------------------------- */
async function togglePauseResume() {
    const endpoint = isPaused ? '/api/resume' : '/api/pause';
    try {
        const res = await fetch(endpoint, { method: 'POST' });
        const data = await res.json();
        showToast(data.message || 'Action executed', 'success');
        pollMetrics();
    } catch (e) {
        showToast('Action failed: ' + e.message, 'error');
    }
}

/* ---------------------------------------------------------
   History & Event Logs
   --------------------------------------------------------- */
async function refreshHistory() {
    try {
        const res = await fetch('/api/switches?limit=15');
        if (!res.ok) return;
        const switches = await res.json();
        const tbody = document.getElementById('switch-history-tbody');
        if (!tbody) return;

        if (switches.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">No scheduler switches recorded yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = switches.map(sw => {
            const time = new Date(sw.timestamp * 1000).toLocaleTimeString();
            const isRollback = sw.reason === 'slo_rollback' || sw.result === 'rollback';
            const reasonBadge = isRollback
                ? `<span class="tag tag-danger">ROLLBACK</span>`
                : (sw.reason === 'manual' ? `<span class="tag tag-warning">MANUAL</span>` : `<span class="tag tag-success">AGENT</span>`);

            const lat = sw.metrics_at_switch ? Math.round(sw.metrics_at_switch.scheduling_latency_us) + ' μs' : '--';
            const cpu = sw.metrics_at_switch ? sw.metrics_at_switch.cpu_utilization.toFixed(1) + '%' : '--';

            return `
                <tr>
                    <td class="mono">${time}</td>
                    <td><span class="mono">${sw.from_scheduler}</span></td>
                    <td><b class="mono text-accent">${sw.to_scheduler}</b></td>
                    <td>${reasonBadge}</td>
                    <td class="mono">${lat}</td>
                    <td class="mono">${cpu}</td>
                    <td><span class="tag ${sw.result === 'ok' ? 'tag-success' : 'tag-warning'}">${sw.result.toUpperCase()}</span></td>
                </tr>
            `;
        }).join('');
    } catch (e) {
        console.warn('History fetch error:', e);
    }
}

async function refreshEvents() {
    try {
        const res = await fetch('/api/events?limit=20');
        if (!res.ok) return;
        const events = await res.json();
        const container = document.getElementById('events-log-list');
        if (!container) return;

        if (events.length === 0) {
            container.innerHTML = `<div class="event-placeholder">No safety events recorded yet.</div>`;
            return;
        }

        container.innerHTML = events.map(ev => {
            const time = new Date(ev.timestamp * 1000).toLocaleTimeString();
            const eventType = ev.type || ev.event_type || 'info';
            let itemClass = 'event-info';
            if (eventType.includes('violation')) itemClass = 'event-violation';
            if (eventType.includes('rollback')) itemClass = 'event-rollback';

            return `
                <div class="event-item ${itemClass}">
                    <div class="event-meta">
                        <span>[${eventType.replaceAll('_', ' ').toUpperCase()}]</span>
                        <span class="mono">${time}</span>
                    </div>
                    <div class="event-msg">${ev.message || ev.details || 'Event logged'}</div>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.warn('Events fetch error:', e);
    }
}

/* ---------------------------------------------------------
   Helpers & Utilities
   --------------------------------------------------------- */
function formatSeconds(secs) {
    const s = Math.floor(secs);
    const hrs = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const rem = s % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${rem.toString().padStart(2, '0')}`;
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}
