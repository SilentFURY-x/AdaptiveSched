"""REST API for the AdaptiveSched dashboard.

Provides JSON endpoints for metrics, status, control, and history
consumed by the frontend dashboard.
"""

from flask import Blueprint, jsonify, request

api = Blueprint('api', __name__)

# The engine reference is set by app.py when creating the Flask app
_engine = None


def set_engine(engine):
    """Set the engine reference for API endpoints.
    
    Args:
        engine: AdaptiveSchedEngine instance.
    """
    global _engine
    _engine = engine


@api.route('/api/status')
def get_status():
    """Get comprehensive system status."""
    if not _engine:
        return jsonify({'error': 'Engine not initialized'}), 503
    return jsonify(_engine.get_status())


@api.route('/api/metrics')
def get_metrics():
    """Get recent metrics history for charting."""
    if not _engine:
        return jsonify({'error': 'Engine not initialized'}), 503
    limit = request.args.get('limit', 60, type=int)
    return jsonify(_engine.get_metrics_history(limit))


@api.route('/api/switches')
def get_switches():
    """Get scheduler switch history."""
    if not _engine:
        return jsonify({'error': 'Engine not initialized'}), 503
    limit = request.args.get('limit', 50, type=int)
    return jsonify(_engine.get_switch_history(limit))


@api.route('/api/slo')
def get_slo():
    """Get SLO profile status and compliance."""
    if not _engine:
        return jsonify({'error': 'Engine not initialized'}), 503
    return jsonify(_engine.get_slo_status())


@api.route('/api/events')
def get_events():
    """Get watchdog event log."""
    if not _engine:
        return jsonify({'error': 'Engine not initialized'}), 503
    limit = request.args.get('limit', 50, type=int)
    return jsonify(_engine.get_watchdog_events(limit))


@api.route('/api/switch', methods=['POST'])
def manual_switch():
    """Manually switch to a specific scheduler."""
    if not _engine:
        return jsonify({'error': 'Engine not initialized'}), 503
    data = request.get_json()
    scheduler = data.get('scheduler', '')
    result = _engine.manual_switch(scheduler)
    return jsonify(result)


@api.route('/api/spike', methods=['POST'])
def trigger_spike():
    """Trigger a simulated performance spike (mock mode)."""
    if not _engine:
        return jsonify({'error': 'Engine not initialized'}), 503
    data = request.get_json() or {}
    duration = data.get('duration', 30.0)
    _engine.trigger_spike(duration)
    return jsonify({'success': True, 'message': f'Spike triggered ({duration}s)'})


@api.route('/api/slo/set', methods=['POST'])
def set_slo_profile():
    """Change the active SLO profile."""
    if not _engine:
        return jsonify({'error': 'Engine not initialized'}), 503
    data = request.get_json()
    profile = data.get('profile', '')
    success = _engine.set_slo_profile(profile)
    return jsonify({'success': success, 'profile': profile})


@api.route('/api/pause', methods=['POST'])
def pause_agent():
    """Pause the scheduling agent."""
    if not _engine:
        return jsonify({'error': 'Engine not initialized'}), 503
    _engine.pause()
    return jsonify({'success': True, 'message': 'Agent paused'})


@api.route('/api/resume', methods=['POST'])
def resume_agent():
    """Resume the scheduling agent."""
    if not _engine:
        return jsonify({'error': 'Engine not initialized'}), 503
    _engine.resume()
    return jsonify({'success': True, 'message': 'Agent resumed'})
