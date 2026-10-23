#!/usr/bin/env python3
"""Render clean terminal screenshots via HTML and headless Firefox."""

import os
import subprocess
import html

TEMPLATES = {
    "terminal_status.png": {
        "title": "adaptive-sched -- cli status",
        "cmd": "python -m src.cli.main status",
        "output": """         System Overview          
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Property         ┃ Value       ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ Status           │ RUNNING     │
│ Agent State      │ ACTIVE      │
│ Operating Mode   │ MOCK        │
│ Bandit Algorithm │ UCB1        │
│ Active Scheduler │ scx_lavd    │
│ Engine Uptime    │ 00:02:15    │
│ Decision Cycles  │ 27          │
└──────────────────┴─────────────┘
                            Live System Metrics                             
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Metric               ┃ Current Reading ┃ Target / Notes                  ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ CPU Utilization      │ 41.9 %          │ Host CPU utilization            │
│ P99 Workload Latency │ 2860 μs         │ Simulated workload tail latency │
│ Throughput           │ 11889 ops/s     │ Simulated completed operations  │
│ Context Switch Rate  │ 29479 /s        │ System-wide                     │
│ Runnable Tasks       │ 2.62            │ Instantaneous procfs count      │
└──────────────────────┴─────────────────┴─────────────────────────────────┘
    SLO Watchdog & Safety Governance     
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Watchdog Field         ┃ Status       ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ Active Profile         │ balanced     │
│ SLO Compliance         │ 64.3 %       │
│ Watchdog State         │ MONITORING   │
│ Consecutive Violations │ 0 / 3        │
│ Total Rollbacks        │ 1            │
└────────────────────────┴──────────────┘"""
    },
    "terminal_history.png": {
        "title": "adaptive-sched -- cli history & watchdog log",
        "cmd": "python -m src.cli.main history",
        "output": """=================================================================
 Scheduler Switch History (Last 10 events)
=================================================================
 [23:34:44] scx_bpfland ──> scx_rusty    (Reason: agent_select, Result: ok)
 [23:34:38] scx_lavd ──> scx_bpfland  (Reason: agent_select, Result: ok)
 [23:34:33] scx_rusty ──> scx_lavd     (Reason: agent_select, Result: ok)
 [23:34:28] scx_bpfland ──> scx_rusty    (Reason: agent_select, Result: ok)
 [23:34:23] scx_lavd ──> scx_bpfland  (Reason: agent_select, Result: ok)
 [23:33:08] scx_simple ──> default      (Reason: slo_rollback, Result: rollback)
 [23:32:53] scx_bpfland ──> scx_simple   (Reason: agent_select, Result: ok)
 [23:32:48] scx_lavd ──> scx_bpfland  (Reason: agent_select, Result: ok)
 [23:32:43] scx_rusty ──> scx_lavd     (Reason: agent_select, Result: ok)
 [23:32:38] default ──> scx_rusty    (Reason: agent_select, Result: ok)

=================================================================
 Watchdog Events & Rollback Log (Recent safety transitions)
=================================================================
 [23:34:08] [INFO     ] Cooldown period ended
 [23:33:08] [INFO     ] Rollback successful
 [23:33:08] [INFO     ] SLO rollback: 3 consecutive violations (p99_latency_us)
 [23:33:08] [INFO     ] Violation #3: p99_latency_us
 [23:33:03] [INFO     ] Violation #2: p99_latency_us
 [23:32:58] [INFO     ] Violation #1: p99_latency_us
 [23:32:58] [INFO     ] Grace period ended, monitoring started
 [23:32:53] [INFO     ] Grace period started (5.0s)
================================================================="""
    },
    "terminal_tests.png": {
        "title": "adaptive-sched -- unit test verification",
        "cmd": "python -m unittest discover -v -s tests",
        "output": """test_all_algorithms_select_known_arms_and_update (test_core.BanditTests.test_all_algorithms_select_known_arms_and_update) ... ok
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

OK"""
    }
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    background: #0f141c;
    margin: 0;
    padding: 30px;
    font-family: 'JetBrains Mono', 'Fira Code', 'DejaVu Sans Mono', Consolas, monospace;
    display: flex;
    justify-content: center;
    align-items: flex-start;
}}
.terminal-window {{
    width: 900px;
    background: #181f2a;
    border-radius: 8px;
    box-shadow: 0 16px 36px rgba(0,0,0,0.55), 0 0 0 1px #263344;
    overflow: hidden;
}}
.terminal-header {{
    background: #1e2736;
    padding: 10px 16px;
    display: flex;
    align-items: center;
    border-bottom: 1px solid #28374a;
}}
.buttons {{
    display: flex;
    gap: 7px;
}}
.button {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
}}
.close {{ background: #e06c75; }}
.minimize {{ background: #e5c07b; }}
.maximize {{ background: #98c379; }}
.title {{
    flex: 1;
    text-align: center;
    font-size: 12px;
    color: #8c9eb4;
    font-weight: 500;
    letter-spacing: 0.5px;
}}
.terminal-body {{
    padding: 20px 24px;
    color: #dbe4ee;
    font-size: 13.5px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-all;
}}
.prompt {{
    color: #61afef;
    font-weight: bold;
    margin-bottom: 12px;
}}
.prompt-user {{ color: #98c379; }}
.prompt-path {{ color: #e5c07b; }}
.output {{
    color: #c5d1de;
}}
</style>
</head>
<body>
<div class="terminal-window">
    <div class="terminal-header">
        <div class="buttons">
            <div class="button close"></div>
            <div class="button minimize"></div>
            <div class="button maximize"></div>
        </div>
        <div class="title">{title}</div>
    </div>
    <div class="terminal-body">
<div class="prompt"><span class="prompt-user">user@adaptivesched</span>:<span class="prompt-path">~/AdaptiveSched</span>$ {cmd}</div><div class="output">{output}</div></div>
</div>
</body>
</html>
"""

def main():
    out_dir = os.path.abspath("docs/report/screenshots")
    os.makedirs(out_dir, exist_ok=True)
    temp_html = "/tmp/terminal_render.html"

    for filename, item in TEMPLATES.items():
        html_content = HTML_TEMPLATE.format(
            title=html.escape(item["title"]),
            cmd=html.escape(item["cmd"]),
            output=html.escape(item["output"])
        )
        with open(temp_html, "w", encoding="utf-8") as f:
            f.write(html_content)

        out_path = os.path.join(out_dir, filename)
        cmd = [
            "firefox",
            "--headless",
            "--no-remote",
            "--profile", "/tmp/fx_profile",
            "--window-size", "980,850",
            f"--screenshot={out_path}",
            f"file://{temp_html}"
        ]
        subprocess.run(cmd, check=True)
        print(f"Rendered: {out_path}")

if __name__ == "__main__":
    main()
