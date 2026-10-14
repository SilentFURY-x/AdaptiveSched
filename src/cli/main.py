"""Command Line Interface (CLI) for AdaptiveSched.

Provides commands to start/stop the scheduling engine, inspect real-time system status,
manually switch schedulers, manage SLO profiles, view audit history, and launch the web dashboard.
"""

import sys
import os
import time
import json
import argparse
import urllib.request
import urllib.error
import logging
from typing import Optional, Dict, Any

from src.core.config import Config
from src.core.engine import AdaptiveSchedEngine
from src.dashboard.app import create_app

# Try importing rich for enhanced terminal aesthetics
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import print as rprint
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None
DEFAULT_API_URL = "http://127.0.0.1:8080"


def _api_get(endpoint: str, base_url: str = DEFAULT_API_URL) -> Optional[Dict[str, Any]]:
    """Helper to perform HTTP GET request against the running AdaptiveSched API."""
    url = f"{base_url.rstrip('/')}{endpoint}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'AdaptiveSched-CLI/1.0'})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None
    except Exception as e:
        return None
    return None


def _api_post(endpoint: str, data: dict, base_url: str = DEFAULT_API_URL) -> Optional[Dict[str, Any]]:
    """Helper to perform HTTP POST request against the running AdaptiveSched API."""
    url = f"{base_url.rstrip('/')}{endpoint}"
    payload = json.dumps(data).encode('utf-8')
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json', 'User-Agent': 'AdaptiveSched-CLI/1.0'}
        )
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode('utf-8'))
        except Exception:
            return {'error': f"HTTP {e.code}"}
    except Exception as e:
        return {'error': str(e)}


def cmd_start(args: argparse.Namespace) -> None:
    """Start the AdaptiveSched engine and integrated API/dashboard server."""
    config = Config()

    # CLI Overrides
    if args.mode:
        config.mode = args.mode
    if args.algorithm:
        config.agent_implementation = args.algorithm
    if args.slo:
        config.active_slo_profile = args.slo
    if args.interval:
        config._data.setdefault('agent', {})['decision_interval_seconds'] = args.interval

    # Configure logging
    log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )

    port = args.port or config.dashboard_port
    host = args.host or config.dashboard_host

    engine = AdaptiveSchedEngine(config)
    engine.start()

    # Start dashboard in a daemon thread so the API is available to other CLI commands
    from threading import Thread
    app = create_app(engine=engine, config=config)

    def run_flask():
        import werkzeug.serving
        # Suppress standard flask logging for clean console demo
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        werkzeug.serving.run_simple(host, port, app, use_reloader=False)

    server_thread = Thread(target=run_flask, daemon=True)
    server_thread.start()

    ui_host = 'localhost' if host == '0.0.0.0' else host
    print("\n" + "=" * 65)
    print("  AdaptiveSched: Autonomous CPU Scheduler Selection Engine")
    print("=" * 65)
    print(f" [Mode]        : {config.mode.upper()}")
    print(f" [Algorithm]   : {config.agent_implementation.upper()}")
    print(f" [SLO Profile] : {config.active_slo_profile}")
    print(f" [Dashboard]   : http://{ui_host}:{port}")
    print(f" [Schedulers]  : {', '.join(config.available_schedulers)}")
    print(f" [Decision]    : Every {config.decision_interval}s")
    print("=" * 65)
    print(" Press Ctrl+C to gracefully stop the engine.\n")

    try:
        while engine.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[AdaptiveSched] Stopping engine...")
        engine.stop()
        print("[AdaptiveSched] Engine shutdown completed successfully.")


def cmd_status(args: argparse.Namespace) -> None:
    """Display real-time system status in the terminal."""
    base_url = f"http://{args.host}:{args.port}"
    status = _api_get('/api/status', base_url)
    slo_data = _api_get('/api/slo', base_url)

    if not status:
        print(f"[Error] Could not connect to AdaptiveSched at {base_url}.")
        print("Ensure the engine is running: python -m src.cli.main start --mode mock")
        sys.exit(1)

    if HAS_RICH and console:
        # Rich UI Formatting
        grid = Table.grid(expand=True)
        grid.add_column()
        
        # System Overview Table
        table_sys = Table(title="System Overview", title_style="bold cyan", border_style="bright_blue")
        table_sys.add_column("Property", style="bold")
        table_sys.add_column("Value", style="green")

        uptime_s = int(status.get('uptime_seconds', 0))
        hrs, rem = divmod(uptime_s, 3600)
        mins, secs = divmod(rem, 60)
        uptime_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"

        table_sys.add_row("Status", "RUNNING" if status.get('running') else "STOPPED")
        table_sys.add_row("Agent State", "PAUSED" if status.get('paused') else "ACTIVE")
        table_sys.add_row("Operating Mode", str(status.get('mode', '')).upper())
        table_sys.add_row("Bandit Algorithm", str(status.get('algorithm', '')).upper())
        table_sys.add_row("Active Scheduler", f"[bold yellow]{status.get('current_scheduler')}[/bold yellow]")
        table_sys.add_row("Engine Uptime", uptime_str)
        table_sys.add_row("Decision Cycles", str(status.get('cycle_count', 0)))
        console.print(table_sys)

        # Current Metrics Table
        metrics = status.get('current_metrics') or {}
        table_met = Table(title="Live Hardware & Workload Metrics", title_style="bold magenta", border_style="magenta")
        table_met.add_column("Metric", style="bold")
        table_met.add_column("Current Reading", style="cyan")
        table_met.add_column("Target / Notes", style="dim")

        table_met.add_row("CPU Utilization", f"{metrics.get('cpu_utilization', 0.0):.1f} %", "Total across all cores")
        table_met.add_row("Scheduling Latency", f"{metrics.get('scheduling_latency_us', 0):.0f} μs", "P99 kernel queue wait")
        table_met.add_row("Throughput", f"{metrics.get('throughput_ops', 0):.0f} ops/s", "Completed execution ops")
        table_met.add_row("Context Switches", f"{metrics.get('context_switches_per_sec', 0):.0f} /s", "Thread switch frequency")
        table_met.add_row("Queued Tasks", str(metrics.get('running_tasks', 0)), "Active run-queue depth")
        console.print(table_met)

        # SLO & Watchdog Table
        wd = status.get('watchdog', {})
        table_slo = Table(title="SLO Watchdog & Safety Governance", title_style="bold yellow", border_style="yellow")
        table_slo.add_column("Watchdog Field", style="bold")
        table_slo.add_column("Status", style="white")

        compliance = status.get('compliance', 100.0)
        comp_color = "green" if compliance >= 95 else ("yellow" if compliance >= 80 else "red")
        table_slo.add_row("Active Profile", f"[bold]{status.get('slo_profile')}[/bold]")
        table_slo.add_row("SLO Compliance", f"[{comp_color}]{compliance:.1f} % [/{comp_color}]")
        table_slo.add_row("Watchdog State", f"[bold]{wd.get('state', 'IDLE').upper()}[/bold]")
        table_slo.add_row("Consecutive Violations", f"{wd.get('consecutive_violations', 0)} / {wd.get('violation_threshold', 3)}")
        table_slo.add_row("Total Rollbacks", str(wd.get('total_rollbacks', 0)))
        console.print(table_slo)

    else:
        # Standard Plaintext Output
        print("\n" + "=" * 50)
        print("       AdaptiveSched Live Status")
        print("=" * 50)
        print(f" Engine State       : {'RUNNING' if status.get('running') else 'STOPPED'}")
        print(f" Active Scheduler   : {status.get('current_scheduler')}")
        print(f" Algorithm          : {status.get('algorithm')}")
        print(f" Active SLO Profile : {status.get('slo_profile')}")
        print(f" SLO Compliance     : {status.get('compliance', 100):.1f}%")
        print(f" Decision Cycles    : {status.get('cycle_count', 0)}")
        m = status.get('current_metrics') or {}
        print("-" * 50)
        print(" Live Metrics:")
        print(f"   CPU Utilization  : {m.get('cpu_utilization', 0):.1f}%")
        print(f"   P99 Latency      : {m.get('scheduling_latency_us', 0):.0f} μs")
        print(f"   Throughput       : {m.get('throughput_ops', 0):.0f} ops/s")
        print("=" * 50 + "\n")


def cmd_switch(args: argparse.Namespace) -> None:
    """Manually switch scheduler via API."""
    base_url = f"http://{args.host}:{args.port}"
    target = args.scheduler

    resp = _api_post('/api/switch', {'scheduler': target}, base_url)
    if not resp:
        print(f"[Error] Could not contact AdaptiveSched API at {base_url}")
        sys.exit(1)

    if resp.get('success'):
        print(f"[AdaptiveSched] Successfully switched active scheduler to: {target}")
    else:
        print(f"[AdaptiveSched Error] Switch failed: {resp.get('message', 'Unknown error')}")


def cmd_slo(args: argparse.Namespace) -> None:
    """Manage SLO profiles."""
    base_url = f"http://{args.host}:{args.port}"

    if args.set:
        profile_name = args.set
        resp = _api_post('/api/slo/set', {'profile': profile_name}, base_url)
        if not resp:
            print(f"[Error] Could not contact AdaptiveSched API at {base_url}")
            sys.exit(1)
        if resp.get('success'):
            print(f"[AdaptiveSched] Active SLO profile set to: {profile_name}")
        else:
            print(f"[AdaptiveSched Error] Profile '{profile_name}' not found.")
        return

    # View current SLO info
    slo_data = _api_get('/api/slo', base_url)
    if not slo_data:
        print(f"[Error] Could not retrieve SLO data from {base_url}")
        sys.exit(1)

    print("\n" + "=" * 55)
    print(f" Active SLO Profile: {slo_data.get('profile', 'unknown').upper()}")
    print(f" Compliance Score  : {slo_data.get('compliance', 100):.1f}%")
    print(f" Available Profiles: {', '.join(slo_data.get('available_profiles', []))}")
    print("-" * 55)
    print(" Constraints:")
    for c in slo_data.get('constraints', []):
        status_symbol = "✔ OK" if c.get('status') == 'ok' else "✖ VIOLATION"
        print(f"   • {c['name']:<20}: max {c['max']}, current {c['current']} [{status_symbol}]")
    print("=" * 55 + "\n")


def cmd_history(args: argparse.Namespace) -> None:
    """Show history of scheduler switches and watchdog rollback events."""
    base_url = f"http://{args.host}:{args.port}"
    limit = args.limit or 20
    switches = _api_get(f'/api/switches?limit={limit}', base_url)
    events = _api_get(f'/api/events?limit={limit}', base_url)

    if switches is None:
        print(f"[Error] Could not retrieve history from {base_url}")
        sys.exit(1)

    print("\n" + "=" * 65)
    print(f" Scheduler Switch History (Last {len(switches)} events)")
    print("=" * 65)
    if not switches:
        print(" No scheduler switches recorded yet.")
    else:
        for s in switches:
            ts = time.strftime('%H:%M:%S', time.localtime(s.get('timestamp', 0)))
            from_s = s.get('from_scheduler')
            to_s = s.get('to_scheduler')
            reason = s.get('reason')
            result = s.get('result')
            print(f" [{ts}] {from_s} ──> {to_s:<12} (Reason: {reason}, Result: {result})")

    if events:
        print("\n" + "=" * 65)
        print(f" Watchdog Events & Rollback Log (Last {len(events)} events)")
        print("=" * 65)
        for ev in events:
            ts = time.strftime('%H:%M:%S', time.localtime(ev.get('timestamp', 0)))
            ev_type = ev.get('event_type', 'info').upper()
            msg = ev.get('message', '')
            print(f" [{ts}] [{ev_type:<9}] {msg}")
    print("=" * 65 + "\n")


def cmd_dashboard(args: argparse.Namespace) -> None:
    """Launch the dashboard in standalone mode."""
    from src.dashboard.app import run_dashboard
    config = Config()
    if args.mode:
        config.mode = args.mode
    run_dashboard(config=config, host=args.host, port=args.port)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI command parser."""
    parser = argparse.ArgumentParser(
        prog="AdaptiveSched",
        description="AdaptiveSched: Self-Tuning CPU Scheduler Selection with SLO-Aware Rollback"
    )
    parser.add_argument('--host', default='127.0.0.1', help='API/Dashboard host address (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=8080, help='API/Dashboard port (default: 8080)')

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: start
    p_start = subparsers.add_parser('start', help='Start the AdaptiveSched agent')
    p_start.add_argument('--mode', choices=['mock', 'real'], default='mock', help='Operating mode (mock/real)')
    p_start.add_argument('--algorithm', choices=['ucb1', 'thompson', 'epsilon_greedy', 'mock'], default='ucb1', help='Bandit algorithm')
    p_start.add_argument('--slo', choices=['balanced', 'interactive', 'throughput'], default='balanced', help='Initial SLO profile')
    p_start.add_argument('--interval', type=float, default=5.0, help='Decision interval in seconds')

    # Subcommand: stop
    subparsers.add_parser('stop', help='Stop the AdaptiveSched agent')

    # Subcommand: status
    subparsers.add_parser('status', help='Show current system status and metrics')

    # Subcommand: switch
    p_switch = subparsers.add_parser('switch', help='Manually switch scheduler')
    p_switch.add_argument('scheduler', help='Target scheduler name (e.g., scx_rusty, scx_lavd, default)')

    # Subcommand: slo
    p_slo = subparsers.add_parser('slo', help='Manage SLO profiles')
    p_slo.add_argument('--set', dest='set', help='Set active SLO profile (balanced, interactive, throughput)')
    p_slo.add_argument('--list', action='store_true', help='List available profiles')

    # Subcommand: history
    p_hist = subparsers.add_parser('history', help='Show scheduler switch history')
    p_hist.add_argument('--limit', type=int, default=20, help='Number of records to show')

    # Subcommand: dashboard
    p_dash = subparsers.add_parser('dashboard', help='Launch the web dashboard')
    p_dash.add_argument('--mode', choices=['mock', 'real'], default='mock', help='Operating mode')

    return parser


def main():
    """Main entrypoint for AdaptiveSched CLI."""
    parser = build_parser()
    args = parser.parse_args()

    cmd_map = {
        'start': cmd_start,
        'status': cmd_status,
        'switch': cmd_switch,
        'slo': cmd_slo,
        'history': cmd_history,
        'dashboard': cmd_dashboard,
    }

    if args.command == 'stop':
        # Send pause or stop signal
        resp = _api_post('/api/pause', {}, f"http://{args.host}:{args.port}")
        if resp and resp.get('success'):
            print("[AdaptiveSched] Sent pause/stop signal to engine.")
        else:
            print("[AdaptiveSched] Unable to stop engine; check if running.")
        return

    handler = cmd_map.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
