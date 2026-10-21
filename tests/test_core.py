"""Unit tests for AdaptiveSched's mock and Linux procfs MVP paths."""

import os
import tempfile
import time
import unittest
from pathlib import Path

from src.agent.agent_engine import BanditAgent
from src.core.config import Config
from src.core.engine import AdaptiveSchedEngine
from src.core.models import SystemMetrics
from src.dashboard.app import create_app
from src.metrics.mock_metrics import MockMetricsCollector
from src.metrics.proc_metrics import ProcMetricsCollector
from src.scheduler.mock_scheduler import MockSchedulerManager
from src.watchdog.health_checker import HealthChecker
from src.watchdog.slo_config import SLOConstraint, SLOProfile
from src.watchdog.watchdog import SLOWatchdog


class ProcMetricsTests(unittest.TestCase):
    def test_delta_metrics_and_explicit_unavailable_fields(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as proc_root:
            stat = os.path.join(proc_root, "stat")
            schedstat = os.path.join(proc_root, "schedstat")
            loadavg = os.path.join(proc_root, "loadavg")

            def write_sample(user, system, idle, ctxt, delay, count):
                with open(stat, "w", encoding="ascii") as f:
                    f.write(f"cpu {user} 0 {system} {idle} 0 0 0 0 0 0\nctxt {ctxt}\n")
                with open(schedstat, "w", encoding="ascii") as f:
                    f.write(f"cpu0 0 0 0 0 0 0 0 {delay} {count}\n")
                with open(loadavg, "w", encoding="ascii") as f:
                    f.write("0.00 0.00 0.00 5/100 123\n")

            ticks = iter([10.0, 12.0])
            write_sample(100, 50, 850, 100, 1_000_000, 10)
            collector = ProcMetricsCollector(proc_root, clock=lambda: next(ticks))
            collector.start()
            write_sample(200, 100, 1700, 130, 3_000_000, 20)
            metrics = collector.collect()

            self.assertAlmostEqual(metrics.cpu_utilization, 15.0)
            self.assertEqual(metrics.context_switches, 30)
            self.assertAlmostEqual(metrics.context_switch_rate, 15.0)
            self.assertAlmostEqual(metrics.scheduling_latency_us, 200.0)
            self.assertAlmostEqual(metrics.runqueue_length, 5.0)
            self.assertIn("throughput_ops", metrics.unavailable_metrics)
            self.assertIn("p99_latency_us", metrics.unavailable_metrics)

    def test_missing_proc_data_fails_with_clear_error(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as proc_root:
            collector = ProcMetricsCollector(proc_root)
            with self.assertRaises(FileNotFoundError):
                collector.start()


class BanditTests(unittest.TestCase):
    def test_all_algorithms_select_known_arms_and_update(self):
        metrics = SystemMetrics(cpu_utilization=70, scheduling_latency_us=500,
                                throughput_ops=5000)
        for name in ("ucb1", "thompson", "epsilon_greedy"):
            agent = BanditAgent(["arm_a", "arm_b"], name)
            selected = agent.select_scheduler(metrics)
            self.assertIn(selected, ("arm_a", "arm_b"))
            agent.update_reward(selected, agent.compute_reward(metrics))
            self.assertGreaterEqual(agent.get_statistics().total_pulls, 1)

    def test_reward_is_bounded_and_rejects_bad_metrics(self):
        agent = BanditAgent(["a"], "ucb1")
        self.assertGreaterEqual(agent.compute_reward(SystemMetrics(cpu_utilization=50)), 0)
        with self.assertRaises(ValueError):
            agent.update_reward("not-an-arm", 0.5)

    def test_benchmark_quantiles(self):
        from scripts.benchmark_linux import percentile
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2)
        self.assertEqual(percentile([1, 2, 3, 4], 99), 4)
        self.assertIsNone(percentile([], 99))


class MockAndHealthTests(unittest.TestCase):
    def test_mock_scheduler_and_metrics_lifecycle(self):
        scheduler = MockSchedulerManager(["scx_simple", "default"], "default")
        self.assertTrue(scheduler.switch_to("scx_simple"))
        self.assertEqual(scheduler.get_current(), "scx_simple")
        self.assertFalse(scheduler.switch_to("unknown"))
        metrics = MockMetricsCollector(["scx_simple", "default"])
        metrics.start()
        sample = metrics.collect()
        self.assertGreater(sample.context_switch_rate, 0)
        self.assertEqual(sample.unavailable_metrics, [])
        metrics.stop()

    def test_health_checker_uses_per_second_context_switch_rate(self):
        checker = HealthChecker()
        good = checker.check(SystemMetrics(context_switches=250_000, context_switch_rate=100))
        self.assertTrue(good["healthy"])
        bad = checker.check(SystemMetrics(context_switch_rate=200_001))
        self.assertFalse(bad["healthy"])


class SLOTests(unittest.TestCase):
    def profile(self, window=10, threshold=2, grace=0):
        return SLOProfile({
            "profile": "test",
            "constraints": {"scheduling_latency_us": {"max": 100, "weight": 1}},
            "evaluation": {"window_seconds": window,
                           "violation_threshold": threshold,
                           "grace_period_seconds": grace},
            "rollback": {"target": "default", "cooldown_seconds": 1},
        })

    def test_unknown_constraints_are_not_reported_as_good_data(self):
        constraint = SLOConstraint("unknown_metric", 10)
        ok, actual = constraint.evaluate(SystemMetrics())
        self.assertFalse(ok)
        self.assertNotEqual(actual, actual)  # NaN denotes unavailable/unknown.

    def test_rolling_window_uses_worst_sample_and_rolls_back_at_threshold(self):
        rollback_reasons = []
        watchdog = SLOWatchdog(self.profile(), lambda reason: rollback_reasons.append(reason) or True)
        watchdog.on_scheduler_switch()
        watchdog._grace_start -= 1
        good = SystemMetrics(scheduling_latency_us=50)
        bad = SystemMetrics(scheduling_latency_us=120)
        self.assertEqual(watchdog.evaluate(good, "scx_rusty")["action"], None)
        self.assertEqual(watchdog.evaluate(bad, "scx_rusty")["action"], None)
        result = watchdog.evaluate(good, "scx_rusty")
        self.assertEqual(result["action"], "rollback")
        self.assertEqual(len(rollback_reasons), 1)

    def test_unavailable_field_does_not_cause_a_false_slo_pass(self):
        profile = SLOProfile({"profile": "x", "constraints": {
            "p99_latency_us": {"max": 100, "weight": 1}}})
        ok, score, violations = profile.evaluate(
            SystemMetrics(unavailable_metrics=["p99_latency_us"]), "default")
        self.assertFalse(ok)
        self.assertEqual(score, 0)
        self.assertEqual(violations, [])


class EngineAndApiTests(unittest.TestCase):
    def test_configuration_and_mock_profile_keep_p99_semantics(self):
        config = Config()
        self.assertEqual(config.dashboard_host, "127.0.0.1")
        self.assertIn("p99_latency_us", config.get_slo_profile("balanced")["constraints"])
        config.mode = "mock"
        engine = AdaptiveSchedEngine(config)
        self.assertIn("p99_latency_us", [c.name for c in engine._slo_profile.constraints])

    def test_mock_engine_api_and_stop_route(self):
        config = Config()
        config.mode = "mock"
        config.agent_implementation = "ucb1"
        config._data.setdefault("agent", {})["decision_interval_seconds"] = 0.05
        engine = AdaptiveSchedEngine(config)
        engine.start()
        app = create_app(engine, config)
        client = app.test_client()
        self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(client.get("/api/status").status_code, 200)
        self.assertEqual(client.get("/api/metrics").status_code, 200)
        self.assertEqual(client.get("/api/slo").status_code, 200)
        self.assertEqual(client.get("/api/events").status_code, 200)
        self.assertEqual(client.post("/api/switch", json={"scheduler": "missing"}).get_json()["success"], False)
        self.assertTrue(client.post("/api/switch", json={"scheduler": "scx_lavd"}).get_json()["success"])
        self.assertTrue(client.post("/api/spike", json={"duration": 0.1}).get_json()["success"])
        self.assertTrue(client.post("/api/pause", json={}).get_json()["success"])
        self.assertTrue(client.post("/api/resume", json={}).get_json()["success"])
        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.post("/api/stop", json={}).status_code, 200)
        self.assertFalse(engine.is_running)

    def test_invalid_mode_is_rejected(self):
        config = Config()
        config.mode = "unsupported"
        with self.assertRaises(ValueError):
            AdaptiveSchedEngine(config)


if __name__ == "__main__":
    unittest.main()
