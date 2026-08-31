import unittest
from unittest.mock import patch

import step3_agent


class WorkflowContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_workflow_wires_all_nodes_without_network(self):
        calls = []

        async def crawl(state):
            calls.append("crawl")
            return {"crawled_contents": {}, "crawled_screenshots": {}, "crawl_errors": {}}

        async def compare(state):
            calls.append("compare")
            return {"comparisons": {}, "first_time_urls": [], "changed_urls": [], "token_usage": {}}

        async def report(state):
            calls.append("report")
            return {"daily_report": "offline", "report_path": "", "should_push": False}

        async def push(state):
            calls.append("push")
            return {}

        async def finalize(state):
            calls.append("finalize")
            return {}

        state = {
            "run_id": "20260831T010203000000Z-test0001",
            "started_monotonic": 0.0,
            "urls": [],
            "crawled_contents": {},
            "crawled_screenshots": {},
            "crawl_errors": {},
            "comparisons": {},
            "first_time_urls": [],
            "changed_urls": [],
            "token_usage": {},
            "daily_report": "",
            "report_path": "",
            "should_push": False,
        }
        with (
            patch("step3_agent.crawl_all_node", crawl),
            patch("step3_agent.compare_all_node", compare),
            patch("step3_agent.generate_report_node", report),
            patch("step3_agent.push_to_wecom_node", push),
            patch("step3_agent.finalize_evidence_node", finalize),
        ):
            result = await step3_agent.build_competitor_agent().ainvoke(state)
        self.assertEqual(calls, ["crawl", "compare", "report", "push", "finalize"])
        self.assertEqual(result["daily_report"], "offline")


if __name__ == "__main__":
    unittest.main()
