"""Core engine — Main orchestrator for AdaptiveSched.

The engine is the central component that ties together the agent,
metrics collector, scheduler manager, and SLO watchdog. It runs
the main decision loop and coordinates all module interactions.
"""

import time
import threading
import logging
from typing import Optional, List, Dict, Any

from src.core.config import Config
from src.core.models import SystemMetrics, SchedulerSwitchEvent, AgentStatistics
from src.interfaces.metrics_interface import IMetricsCollector
from src.interfaces.agent_interface import ISchedulerAgent
from src.interfaces.scheduler_interface import ISchedulerManager
from src.watchdog.slo_config import SLOProfile
from src.watchdog.watchdog import SLOWatchdog
from src.watchdog.rollback import RollbackManager
from src.watchdog.health_checker import HealthChecker
from src.metrics.mock_metrics import MockMetricsCollector
from src.agent.mock_agent import MockBanditAgent
from src.scheduler.mock_scheduler import MockSchedulerManager

logger = logging.getLogger('adaptivesched.engine')


class AdaptiveSchedEngine:
    """Main engine that orchestrates all AdaptiveSched components.
    
    Responsibilities:
        1. Initialize all modules based on configuration
        2. Run the main decision loop (collect → decide → switch → evaluate)
        3. Coordinate watchdog with agent decisions
        4. Provide a control interface for CLI/Dashboard
        5. Maintain event history
    """

    def __init__(self, config: Config):
        """Initialize the engine with all components.
        
        Args:
            config: Loaded configuration object.
        """
        self._config = config
        self._running = False
        self._paused = False
        self._start_time: float = 0
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Event history
        self._switch_history: List[SchedulerSwitchEvent] = []
        self._metrics_history: List[SystemMetrics] = []
        
        # Current state
        self._current_metrics: Optional[SystemMetrics] = None
        self._cycle_count = 0
        
        # Initialize components
        self._init_components()

    def _init_components(self) -> None:
        """Initialize all subsystem components based on config."""
        schedulers = self._config.available_schedulers
        default = self._config.default_scheduler
        
        # Scheduler Manager (always mock for now)
        self._scheduler_manager: ISchedulerManager = MockSchedulerManager(
            available=schedulers,
            default=default,
        )
        
        # Metrics Collector
        if self._config.mode == 'mock' or self._config.metrics_implementation == 'mock':
            self._metrics_collector: IMetricsCollector = MockMetricsCollector(schedulers)
        else:
            # Placeholder for real implementation (Aritra)
            self._metrics_collector = MockMetricsCollector(schedulers)
            logger.warning("Real metrics collector not available, using mock")
        
        # Agent
        algorithm = self._config.agent_implementation
        if self._config.mode == 'mock' or algorithm == 'mock':
            self._agent: ISchedulerAgent = MockBanditAgent(schedulers, algorithm)
        else:
            # Placeholder for real implementation (Aritra)
            self._agent = MockBanditAgent(schedulers, algorithm)
            logger.warning("Real bandit agent not available, using mock")
        
        # Rollback Manager
        self._rollback_manager = RollbackManager(
            self._scheduler_manager, default
        )
        
        # SLO Profile
        profile_data = self._config.get_slo_profile()
        if profile_data:
            self._slo_profile = SLOProfile(profile_data)
        else:
            # Fallback to a basic profile
            self._slo_profile = SLOProfile({
                'profile': 'default',
                'constraints': {
                    'p99_latency_us': {'max': 10000, 'weight': 0.5},
                    'cpu_utilization': {'max': 95, 'weight': 0.5},
                },
                'evaluation': {
                    'window_seconds': 10,
                    'violation_threshold': 3,
                    'grace_period_seconds': 5,
                },
                'rollback': {
                    'target': 'default',
                    'cooldown_seconds': 60,
                },
            })
        
        # Health Checker
        self._health_checker = HealthChecker()
        
        # SLO Watchdog
        self._watchdog = SLOWatchdog(
            slo_profile=self._slo_profile,
            rollback_callback=self._on_rollback_requested,
        )

    def _on_rollback_requested(self, reason: str) -> bool:
        """Callback invoked by the watchdog when rollback is needed.
        
        Args:
            reason: Human-readable reason for rollback.
            
        Returns:
            True if rollback was successful.
        """
        success = self._rollback_manager.execute_rollback(reason)
        
        if success:
            # Update mock metrics to use default scheduler profile
            if isinstance(self._metrics_collector, MockMetricsCollector):
                self._metrics_collector.set_active_scheduler(
                    self._rollback_manager.default_scheduler
                )
            
            # Record the event
            self._switch_history.append(SchedulerSwitchEvent(
                from_scheduler=self._scheduler_manager.get_current(),
                to_scheduler=self._rollback_manager.default_scheduler,
                reason="slo_rollback",
                metrics_at_switch=self._current_metrics,
                result="rollback",
            ))
        
        return success

    def start(self) -> None:
        """Start the engine's main decision loop.
        
        Runs the agent loop in a background thread.
        """
        if self._running:
            logger.warning("Engine is already running")
            return
        
        self._running = True
        self._start_time = time.time()
        self._metrics_collector.start()
        
        logger.info("=" * 60)
        logger.info(f"[AdaptiveSched] Starting in {self._config.mode.upper()} mode")
        logger.info(f"[AdaptiveSched] Algorithm: {self._config.agent_implementation}")
        logger.info(f"[AdaptiveSched] SLO Profile: {self._slo_profile.name}")
        logger.info(f"[AdaptiveSched] Schedulers: {', '.join(self._config.available_schedulers)}")
        logger.info(f"[AdaptiveSched] Decision interval: {self._config.decision_interval}s")
        logger.info("=" * 60)
        
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the engine."""
        self._running = False
        self._metrics_collector.stop()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("[AdaptiveSched] Engine stopped")

    def _run_loop(self) -> None:
        """Main decision loop (runs in background thread).
        
        Cycle: collect metrics → update reward → select scheduler → switch → evaluate SLO
        """
        while self._running:
            try:
                if not self._paused:
                    self._cycle_count += 1
                    self._run_cycle()
            except Exception as e:
                logger.error(f"Error in engine cycle: {e}", exc_info=True)
            
            time.sleep(self._config.decision_interval)

    def _run_cycle(self) -> None:
        """Execute a single decision cycle."""
        # 1. Collect metrics
        metrics = self._metrics_collector.collect()
        self._current_metrics = metrics
        self._metrics_history.append(metrics)
        
        # Keep history bounded
        if len(self._metrics_history) > 300:
            self._metrics_history = self._metrics_history[-300:]
        
        current_scheduler = self._scheduler_manager.get_current()
        
        logger.info(f"── Cycle {self._cycle_count} ──")
        logger.info(f"  Metrics: cpu={metrics.cpu_utilization:.1f}%, "
                    f"latency={metrics.scheduling_latency_us:.0f}μs, "
                    f"throughput={metrics.throughput_ops:.0f} ops")
        
        # 2. Update reward for current scheduler
        if hasattr(self._agent, 'compute_reward'):
            reward = self._agent.compute_reward(metrics)
        else:
            # Fallback reward computation
            norm_latency = min(1.0, metrics.scheduling_latency_us / 10000)
            reward = 0.5 * (1 - norm_latency) + 0.5 * min(1.0, metrics.throughput_ops / 15000)
        
        self._agent.update_reward(current_scheduler, reward)
        
        # 3. Evaluate SLO
        watchdog_result = self._watchdog.evaluate(metrics, current_scheduler)
        
        if watchdog_result.get('action') == 'rollback':
            logger.info("  Rollback triggered — skipping agent selection")
            return
        
        # 4. Check if switch is allowed
        if not self._watchdog.is_switch_allowed():
            logger.info("  Switch blocked (cooldown active)")
            return
        
        # 5. Health check
        health = self._health_checker.check(metrics)
        if not health['healthy']:
            logger.warning(f"  Switch blocked (unhealthy): {', '.join(health['issues'])}")
            return
        
        # 6. Ask agent for next scheduler
        selected = self._agent.select_scheduler(metrics)
        
        if selected != current_scheduler:
            logger.info(f"  Agent selected: {selected} (switching from {current_scheduler})")
            
            # Execute switch
            success = self._scheduler_manager.switch_to(selected)
            
            if success:
                # Notify mock metrics of the change
                if isinstance(self._metrics_collector, MockMetricsCollector):
                    self._metrics_collector.set_active_scheduler(selected)
                
                # Notify watchdog
                self._watchdog.on_scheduler_switch()
                
                # Record event
                self._switch_history.append(SchedulerSwitchEvent(
                    from_scheduler=current_scheduler,
                    to_scheduler=selected,
                    reason="agent_select",
                    metrics_at_switch=metrics,
                    result="ok",
                ))
                
                logger.info(f"  Switch successful: {current_scheduler} → {selected}")
            else:
                logger.error(f"  Switch FAILED: {current_scheduler} → {selected}")
        else:
            logger.info(f"  Agent: staying on {current_scheduler} (reward={reward:.3f})")

    # ──── Control Interface ────

    def manual_switch(self, scheduler_name: str) -> dict:
        """Manually switch to a specific scheduler.
        
        Args:
            scheduler_name: Target scheduler name.
            
        Returns:
            Result dictionary with success status and message.
        """
        if not self._running:
            return {'success': False, 'message': 'Engine is not running'}
        
        with self._lock:
            current = self._scheduler_manager.get_current()
            success = self._scheduler_manager.switch_to(scheduler_name)
            
            if success:
                if isinstance(self._metrics_collector, MockMetricsCollector):
                    self._metrics_collector.set_active_scheduler(scheduler_name)
                
                self._watchdog.on_scheduler_switch()
                
                self._switch_history.append(SchedulerSwitchEvent(
                    from_scheduler=current,
                    to_scheduler=scheduler_name,
                    reason="manual",
                    metrics_at_switch=self._current_metrics,
                    result="ok",
                ))
                
                return {'success': True, 'message': f'Switched to {scheduler_name}'}
            else:
                return {'success': False, 'message': f'Failed to switch to {scheduler_name}'}

    def trigger_spike(self, duration: float = 20.0) -> None:
        """Trigger a simulated performance spike (mock mode only).
        
        Args:
            duration: Spike duration in seconds.
        """
        if isinstance(self._metrics_collector, MockMetricsCollector):
            self._metrics_collector.trigger_spike(duration)
            logger.info(f"[Demo] Triggered performance spike ({duration}s)")

    def pause(self) -> None:
        """Pause the agent (stop making decisions)."""
        self._paused = True
        logger.info("[AdaptiveSched] Agent paused")

    def resume(self) -> None:
        """Resume the agent."""
        self._paused = False
        logger.info("[AdaptiveSched] Agent resumed")

    def set_slo_profile(self, profile_name: str) -> bool:
        """Change the active SLO profile.
        
        Args:
            profile_name: Name of the profile to activate.
            
        Returns:
            True if the profile was found and set.
        """
        profile_data = self._config.get_slo_profile(profile_name)
        if profile_data:
            self._slo_profile = SLOProfile(profile_data)
            self._watchdog.slo_profile = self._slo_profile
            self._config.active_slo_profile = profile_name
            logger.info(f"SLO profile changed to '{profile_name}'")
            return True
        return False

    # ──── Status / Query Interface ────

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive system status.
        
        Returns:
            Dictionary with all system state information.
        """
        agent_stats = self._agent.get_statistics()
        watchdog_state = self._watchdog.get_state()
        
        return {
            'running': self._running,
            'paused': self._paused,
            'mode': self._config.mode,
            'algorithm': self._config.agent_implementation,
            'current_scheduler': self._scheduler_manager.get_current(),
            'available_schedulers': self._scheduler_manager.get_available(),
            'slo_profile': self._slo_profile.name,
            'uptime_seconds': time.time() - self._start_time if self._running else 0,
            'cycle_count': self._cycle_count,
            'agent_stats': agent_stats.to_dict(),
            'watchdog': watchdog_state.to_dict(),
            'compliance': self._watchdog.compliance_score,
            'current_metrics': self._current_metrics.to_dict() if self._current_metrics else None,
            'health': self._health_checker.check(self._current_metrics) if self._current_metrics else {'healthy': True, 'issues': [], 'severity': 'ok'},
        }

    def get_metrics_history(self, limit: int = 60) -> List[dict]:
        """Get recent metrics history for charting.
        
        Args:
            limit: Maximum number of entries.
            
        Returns:
            List of metrics dictionaries.
        """
        return [m.to_dict() for m in self._metrics_history[-limit:]]

    def get_switch_history(self, limit: int = 50) -> List[dict]:
        """Get scheduler switch history.
        
        Args:
            limit: Maximum number of entries.
            
        Returns:
            List of switch event dictionaries.
        """
        return [e.to_dict() for e in reversed(self._switch_history[-limit:])]

    def get_slo_status(self) -> Dict[str, Any]:
        """Get detailed SLO status.
        
        Returns:
            Dictionary with SLO profile details and current compliance.
        """
        constraints_status = []
        if self._current_metrics:
            for constraint in self._slo_profile.constraints:
                satisfied, actual = constraint.evaluate(self._current_metrics)
                constraints_status.append({
                    'name': constraint.name,
                    'max': constraint.max_value,
                    'current': round(actual, 2),
                    'status': 'ok' if satisfied else 'violation',
                    'weight': constraint.weight,
                })
        
        return {
            'profile': self._slo_profile.name,
            'compliance': self._watchdog.compliance_score,
            'constraints': constraints_status,
            'evaluation_window': self._slo_profile.window_seconds,
            'violation_threshold': self._slo_profile.violation_threshold,
            'grace_period': self._slo_profile.grace_period_seconds,
            'cooldown': self._slo_profile.cooldown_seconds,
            'available_profiles': self._config.available_slo_profiles,
        }

    def get_watchdog_events(self, limit: int = 50) -> list:
        """Get watchdog event log.
        
        Args:
            limit: Maximum number of events.
            
        Returns:
            List of event dictionaries.
        """
        return self._watchdog.get_events(limit)

    @property
    def is_running(self) -> bool:
        """Check if the engine is running."""
        return self._running
