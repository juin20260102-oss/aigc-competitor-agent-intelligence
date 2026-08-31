import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_control import AgentLimits, ModelBudget, build_wecom_summary, emit_run_event


class RunControlTests(unittest.TestCase):
    def test_limits_clamp_invalid_environment_values(self):
        with patch.dict(
            "os.environ",
            {"CRAWL_CONCURRENCY": "99", "MAX_MODEL_CALLS": "bad", "NOTIFICATION_MAX_CHARS": "1"},
            clear=False,
        ):
            limits = AgentLimits.from_env()
        self.assertEqual(limits.crawl_concurrency, 8)
        self.assertEqual(limits.max_model_calls, 25)
        self.assertEqual(limits.notification_max_chars, 500)

    def test_summary_uses_changed_sites_not_report_prefix(self):
        summary = build_wecom_summary(
            {
                "changed_urls": ["https://example.com/pricing"],
                "first_time_urls": ["https://new.example.com"],
                "crawl_errors": {"https://bad.example.com": "timeout"},
                "token_usage": {"model_calls": 2, "total_tokens": 1234},
                "daily_report": "SECRET REPORT PREFIX" * 100,
            },
            max_chars=500,
        )
        self.assertIn("https://example.com/pricing", summary)
        self.assertIn("https://bad.example.com", summary)
        self.assertNotIn("SECRET REPORT PREFIX", summary)

    def test_structured_events_are_single_line_json(self):
        with tempfile.TemporaryDirectory() as directory:
            emit_run_event(directory, "crawl_completed", succeeded=3)
            lines = (Path(directory) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["event"], "crawl_completed")


class ModelBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_budget_reserves_calls_and_token_capacity(self):
        budget = ModelBudget(max_calls=1, max_tokens=100)
        await budget.reserve(90)
        with self.assertRaises(RuntimeError):
            await budget.reserve(1)
        await budget.record(type("Usage", (), {"total_tokens": 80})(), 90)
        self.assertEqual(budget.tokens, 80)
        self.assertEqual(budget.reserved_tokens, 0)


if __name__ == "__main__":
    unittest.main()
