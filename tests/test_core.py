"""Unit tests for AdaptiveSched Core, Watchdog, Agent, and Dashboard API."""

import unittest
import time
from src.core.models import SystemMetrics, SchedulerSwitchEvent, AgentStatistics
from src.core.config import Config
from src.core.engine import AdaptiveSchedEngine
from src.metrics.mock_metrics import MockMetricsCollector
from src.scheduler.mock_scheduler import MockSchedulerManager
from src.agent.mock_agent import MockBanditAgent
from src.watchdog.slo_config import SLOProfile, SLOConstraint
from src.watchdog.health_checker import HealthChecker
from src.watchdog.rollback import RollbackManager
from src.watchdog.watchdog import SLOWatchdog, WatchdogState
from src.dashboard.app import create_app


class TestAdaptiveSchedCore(unittest.TestCase):
    """Test core models, configuration, and components."""

    def test_models_serialization(self):
        m = SystemMetrics(
            timestamp=100.0,
            cpu_utilization=45.5,
            scheduling_latency_us=1200.0,
            throughput_ops=8500.0,
            context_switches_per_sec=3500.0,
            cache_miss_rate=0.03,
            ipc=1.45,
            memory_used_mb=2048.0,
            memory_total_mb=16384.0,
            active_threads=120,
            running_tasks=4,
        )
        d = m.to_dict()
        self.assertEqual(d['cpu_utilization'], 45.5)
        self.assertEqual(d['scheduling_latency_us'], 1200.0)

        ev = SchedulerSwitchEvent(
            from_scheduler="default",
            to_scheduler="scx_rusty",
            reason="agent_select",
            result="ok",
            metrics_at_switch=m,
        )
        ed = ev.to_dict()
        self.assertEqual(ed['from_scheduler'], 'default')
        self.assertEqual(ed['to_scheduler'], 'scx_rusty')

    def test_config_loader(self):
        config = Config()
        self.assertIn('scx_rusty', config.available_schedulers)
        self.assertEqual(config.default_scheduler, 'default')
        self.assertIn(config.active_slo_profile, ['balanced', 'interactive', 'throughput'])
        profile_data = config.get_slo_profile('balanced')
        self.assertIsNotNone(profile_data)
        self.assertIn('constraints', profile_data)

    def test_mock_scheduler(self):
        sched = MockSchedulerManager(available=['scx_rusty', 'scx_lavd', 'default'], default='default')
        self.assertEqual(sched.get_current(), 'default')
        self.assertTrue(sched.switch_to('scx_rusty'))
        self.assertEqual(sched.get_current(), 'scx_rusty')
        self.assertFalse(sched.switch_to('non_existent_sched'))
        self.assertTrue(sched.reset_to_default())
        self.assertEqual(sched.get_current(), 'default')

    def test_mock_metrics_collector(self):
        collector = MockMetricsCollector(['scx_rusty', 'default'])
        collector.start()
        metrics = collector.collect()
        self.assertGreater(metrics.cpu_utilization, 0)
        self.assertGreater(metrics.scheduling_latency_us, 0)
        
        # Test spike trigger
        collector.trigger_spike(duration=5.0)
        spiked_metrics = collector.collect()
        self.assertGreaterEqual(spiked_metrics.scheduling_latency_us, 5000.0)
        collector.stop()

    def test_mock_bandit_agent(self):
        schedulers = ['scx_rusty', 'scx_lavd', 'default']
        agent = MockBanditAgent(schedulers, algorithm='ucb1')
        collector = MockMetricsCollector(schedulers)
        metrics = collector.collect()

        # Selection
        selected = agent.select_scheduler(metrics)
        self.assertIn(selected, schedulers)

        # Reward update
        reward = agent.compute_reward(metrics)
        self.assertGreaterEqual(reward, 0.0)
        self.assertLessEqual(reward, 1.0)
        agent.update_reward(selected, reward)

        stats = agent.get_statistics()
        self.assertIn(selected, stats.arm_pulls)
        self.assertGreater(stats.arm_pulls[selected], 0)

    def test_slo_profile_and_constraint(self):
        constraint = SLOConstraint(name='p99_latency_us', metric_name='scheduling_latency_us', max_value=5000.0, weight=0.6)
        m_good = SystemMetrics(timestamp=1, cpu_utilization=50, scheduling_latency_us=2000)
        m_bad = SystemMetrics(timestamp=1, cpu_utilization=50, scheduling_latency_us=8000)

        ok, val = constraint.evaluate(m_good)
        self.assertTrue(ok)
        self.assertEqual(val, 2000)

        ok, val = constraint.evaluate(m_bad)
        self.assertFalse(ok)
        self.assertEqual(val, 8000)

    def test_health_checker(self):
        checker = HealthChecker()
        m_healthy = SystemMetrics(timestamp=1, memory_used_mb=2000, memory_total_mb=16000, scheduling_latency_us=1500)
        res = checker.check(m_healthy)
        self.assertTrue(res['healthy'])

        m_unhealthy = SystemMetrics(timestamp=1, memory_used_mb=15900, memory_total_mb=16000, scheduling_latency_us=60000)
        res_bad = checker.check(m_unhealthy)
        self.assertFalse(res_bad['healthy'])
        self.assertGreater(len(res_bad['issues']), 0)

    def test_watchdog_state_machine_and_rollback(self):
        rollback_called = []

        def dummy_rollback(reason: str):
            rollback_called.append(reason)
            return True

        profile = SLOProfile({
            'profile': 'test',
            'constraints': {
                'p99_latency_us': {'max': 2000, 'weight': 1.0}
            },
            'evaluation': {
                'window_seconds': 10,
                'violation_threshold': 2,
                'grace_period_seconds': 0.1,
            },
            'rollback': {
                'target': 'default',
                'cooldown_seconds': 1.0,
            }
        })

        watchdog = SLOWatchdog(slo_profile=profile, rollback_callback=dummy_rollback)
        self.assertEqual(watchdog.state, WatchdogState.IDLE)

        # Trigger scheduler switch -> enters GRACE_PERIOD
        watchdog.on_scheduler_switch()
        self.assertEqual(watchdog.state, WatchdogState.GRACE_PERIOD)

        # Wait for grace period to expire
        time.sleep(0.15)
        
        # Good metric -> MONITORING
        m_good = SystemMetrics(timestamp=1, cpu_utilization=20, scheduling_latency_us=1000)
        r1 = watchdog.evaluate(m_good, 'scx_rusty')
        self.assertEqual(watchdog.state, WatchdogState.MONITORING)
        self.assertEqual(r1['action'], 'none')

        # First violation
        m_bad = SystemMetrics(timestamp=2, cpu_utilization=90, scheduling_latency_us=5000)
        r2 = watchdog.evaluate(m_bad, 'scx_rusty')
        self.assertEqual(r2['action'], 'warning')
        self.assertEqual(watchdog.state, WatchdogState.VIOLATION_DETECTED)

        # Second violation (hits threshold 2) -> triggers rollback & COOLDOWN
        r3 = watchdog.evaluate(m_bad, 'scx_rusty')
        self.assertEqual(r3['action'], 'rollback')
        self.assertEqual(watchdog.state, WatchdogState.COOLDOWN)
        self.assertEqual(len(rollback_called), 1)

    def test_engine_lifecycle(self):
        config = Config()
        config.mode = 'mock'
        config.agent_implementation = 'mock'
        engine = AdaptiveSchedEngine(config)

        # Start engine
        engine.start()
        self.assertTrue(engine.is_running)

        # Let it run 1 cycle
        time.sleep(1.0)
        status = engine.get_status()
        self.assertEqual(status['mode'], 'mock')
        self.assertIn(status['current_scheduler'], config.available_schedulers)

        # Manual switch
        switch_res = engine.manual_switch('scx_lavd')
        self.assertTrue(switch_res['success'])
        self.assertEqual(engine.get_status()['current_scheduler'], 'scx_lavd')

        # Pause and resume
        engine.pause()
        self.assertTrue(engine.get_status()['paused'])
        engine.resume()
        self.assertFalse(engine.get_status()['paused'])

        # Stop engine
        engine.stop()
        self.assertFalse(engine.is_running)

    def test_dashboard_api(self):
        config = Config()
        config.mode = 'mock'
        engine = AdaptiveSchedEngine(config)
        engine.start()

        app = create_app(engine=engine, config=config)
        client = app.test_client()

        # Health endpoint
        res = client.get('/health')
        self.assertEqual(res.status_code, 200)

        # Status endpoint
        res = client.get('/api/status')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('current_scheduler', data)

        # Metrics endpoint
        res = client.get('/api/metrics')
        self.assertEqual(res.status_code, 200)

        # SLO endpoint
        res = client.get('/api/slo')
        self.assertEqual(res.status_code, 200)

        # Manual switch via POST
        res = client.post('/api/switch', json={'scheduler': 'scx_rusty'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get('success'))

        # Spike via POST
        res = client.post('/api/spike', json={'duration': 2.0})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get('success'))

        # UI Page
        res = client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'AdaptiveSched', res.data)

        engine.stop()


if __name__ == '__main__':
    unittest.main()
