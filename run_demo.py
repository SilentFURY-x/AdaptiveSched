"""AdaptiveSched -- Quick Demo Launcher.

Launches the complete AdaptiveSched engine in mock mode with online bandit learning,
SLO watchdog safety monitoring, and the real-time interactive web dashboard.
"""

import sys
import os
import time
import webbrowser
import threading

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.core.config import Config
from src.core.engine import AdaptiveSchedEngine
from src.dashboard.app import create_app


def main():
    print("=" * 70)
    print("   AdaptiveSched -- Live Demonstration")
    print("   Autonomous CPU Scheduler Selection via Online Bandit Learning")
    print("   Arjun Tyagi (24BCE0605) & Aritra Ghosh (24BCE0598)")
    print("=" * 70)

    config = Config()
    config.mode = 'mock'
    config.agent_implementation = 'ucb1'
    config.active_slo_profile = 'balanced'

    engine = AdaptiveSchedEngine(config)
    engine.start()

    port = config.dashboard_port
    host = '127.0.0.1'

    app = create_app(engine=engine, config=config)

    print(f"\n[AdaptiveSched] Engine started in MOCK mode with UCB1 bandit learning.")
    print(f"[AdaptiveSched] Serving Real-Time Dashboard at: http://localhost:{port}")
    print(f"[AdaptiveSched] Try these CLI commands in a second terminal:")
    print(f"    python -m src.cli.main status")
    print(f"    python -m src.cli.main switch scx_rusty")
    print(f"    python -m src.cli.main slo --set interactive")
    print(f"    python -m src.cli.main history\n")
    print("Opening browser dashboard in 2 seconds...")

    def open_browser():
        time.sleep(1.8)
        try:
            webbrowser.open(f"http://localhost:{port}")
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n[AdaptiveSched] Shutting down demo cleanly...")
    finally:
        engine.stop()
        print("[AdaptiveSched] Goodbye!")


if __name__ == '__main__':
    main()
