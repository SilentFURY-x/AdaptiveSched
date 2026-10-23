"""AdaptiveSched Dashboard — Flask Web Application.

Provides the web UI and REST API for real-time visualization of scheduler
performance, bandit agent decisions, SLO watchdog monitoring, and manual controls.
"""

import os
import logging
from typing import Optional
from flask import Flask, render_template, jsonify

from src.dashboard.api import api, set_engine
from src.core.config import Config
from src.core.engine import AdaptiveSchedEngine

logger = logging.getLogger('adaptivesched.dashboard')


def create_app(engine: Optional[AdaptiveSchedEngine] = None, config: Optional[Config] = None) -> Flask:
    """Create and configure the Flask dashboard application.
    
    Args:
        engine: AdaptiveSchedEngine instance to bind to the API. If None,
                creates a default engine in mock mode.
        config: Config instance. If None, loaded automatically.
        
    Returns:
        Configured Flask application instance.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')

    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir,
        static_url_path='/static'
    )
    app.config['SECRET_KEY'] = 'adaptivesched-secret-key-2026'

    # If engine not supplied, create one
    if engine is None:
        if config is None:
            config = Config()
        engine = AdaptiveSchedEngine(config)
        engine.start()

    # Bind engine to API blueprint
    set_engine(engine)
    app.engine = engine

    # Register blueprints
    app.register_blueprint(api)

    @app.route('/')
    def index():
        """Serve main dashboard UI with initial hydration payload."""
        status = engine.get_status() if engine else {}
        metrics = engine.get_metrics_history(limit=30) if engine else []
        switches = engine.get_switch_history(limit=15) if engine else []
        slo = engine.get_slo_status() if engine else {}
        events = engine.get_watchdog_events(limit=20) if engine else []
        return render_template(
            'index.html',
            initial_status=status,
            initial_metrics=metrics,
            initial_switches=switches,
            initial_slo=slo,
            initial_events=events,
        )

    @app.route('/health')
    def health():
        """Dashboard health check."""
        return jsonify({
            'status': 'healthy',
            'engine_running': engine.is_running if engine else False
        })

    return app


def run_dashboard(
    engine: Optional[AdaptiveSchedEngine] = None,
    config: Optional[Config] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    debug: bool = False
) -> None:
    """Run the Flask dashboard server.
    
    Args:
        engine: AdaptiveSchedEngine instance.
        config: Config instance.
        host: Host address (defaults to config dashboard_host).
        port: Port number (defaults to config dashboard_port).
        debug: Flask debug mode.
    """
    if config is None:
        config = Config()

    app_host = host or config.dashboard_host
    app_port = port or config.dashboard_port

    app = create_app(engine=engine, config=config)
    
    print(f"\n=======================================================")
    print(f" [AdaptiveSched Dashboard]")
    print(f" URL: http://{app_host if app_host != '0.0.0.0' else 'localhost'}:{app_port}")
    print(f" Mode: {config.mode.upper()} | Profile: {config.active_slo_profile}")
    print(f"=======================================================\n")

    app.run(host=app_host, port=app_port, debug=debug, use_reloader=False)


if __name__ == '__main__':
    run_dashboard()
