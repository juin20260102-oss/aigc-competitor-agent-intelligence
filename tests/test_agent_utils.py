import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_utils import (
    AgentRunLock,
    assess_change,
    atomic_write_json,
    compact_error,
    ensure_single_line,
    normalize_content,
    site_key_for_url,
    validate_public_http_url,
)
from step3_agent import call_llm_with_retry, verify_evidence_quotes


class ContentChangeTests(unittest.TestCase):
    def test_markdown_targets_do_not_create_false_change(self):
        old = "[产品介绍](https://example.com/a?trace=1)\n![海报](https://cdn/a.png)"
        new = "[产品介绍](https://example.com/a?trace=2)\n![海报](https://cdn/b.png)"
        self.assertEqual(normalize_content(old), normalize_content(new))
        self.assertFalse(assess_change(old, new).changed)

    def test_substantive_change_is_detected_anywhere_in_document(self):
        old = "稳定内容\n" * 100 + "基础套餐每月 99 元"
        new = "稳定内容\n" * 100 + "专业套餐每月 199 元，并新增团队协作与批量导出功能"
        result = assess_change(old, new, min_changed_characters=10, min_change_ratio=0.001)
        self.assertTrue(result.changed)
        self.assertIn("团队协作", result.diff_context)

    def test_small_noise_is_skipped(self):
        old = "这是长期稳定的产品介绍和功能说明，内容不会频繁变化。" * 20
        new = old + " 1"
        self.assertFalse(assess_change(old, new).changed)

    def test_small_high_signal_price_change_is_not_skipped_on_long_page(self):
        stable = "长期稳定的产品介绍与帮助中心说明。\n" * 500
        result = assess_change(stable + "基础套餐价格 99 元", stable + "基础套餐价格 199 元")
        self.assertTrue(result.changed)


class UrlSafetyTests(unittest.TestCase):
    def test_rejects_private_and_credentialed_urls(self):
        for url in (
            "http://127.0.0.1/admin",
            "http://192.168.1.2",
            "http://169.254.169.254/latest/meta-data",
            "https://user:pass@example.com",
            "file:///etc/passwd",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_public_http_url(url)

    def test_accepts_public_https_url(self):
        self.assertEqual(validate_public_http_url("https://example.com/path"), "https://example.com/path")

    @patch("agent_utils.socket.getaddrinfo")
    def test_dns_resolution_rejects_private_answer(self, getaddrinfo):
        getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]
        with self.assertRaises(ValueError):
            validate_public_http_url("https://example.com", resolve_dns=True)


class PersistenceAndLockTests(unittest.TestCase):
    def test_atomic_json_write(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "nested" / "snapshot.json"
            atomic_write_json(target, {"产品": "测试"})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"产品": "测试"})

    def test_second_lock_is_rejected_and_first_lock_is_cleaned(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.lock"
            with AgentRunLock(path):
                self.assertTrue(path.exists())
                with self.assertRaises(RuntimeError):
                    with AgentRunLock(path):
                        pass
            self.assertFalse(path.exists())

    def test_newline_in_environment_value_is_rejected(self):
        with self.assertRaises(ValueError):
            ensure_single_line("safe\nINJECTED=value", "配置")

    def test_error_is_single_line_short_and_table_safe(self):
        message = compact_error("boom\nC:\\Users\\secret\\file.py | details", max_length=80)
        self.assertNotIn("\n", message)
        self.assertNotIn("C:\\Users", message)
        self.assertIn("\\|", message)

    def test_site_key_preserves_path_identity(self):
        self.assertEqual(site_key_for_url("https://example.com/products/a"), "example.com_products_a")

    def test_unmatched_model_quote_is_flagged(self):
        result = verify_evidence_quotes("结论【依据：页面原文“并不存在的功能”】", "真实页面正文")
        self.assertIn("需人工复核", result)


class ModelRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_call_retries_then_succeeds(self):
        marker = object()

        class FakeCompletions:
            def __init__(self):
                self.calls = 0

            async def create(self, **kwargs):
                self.calls += 1
                if self.calls < 3:
                    raise TimeoutError("temporary")
                return marker

        completions = FakeCompletions()
        client = type(
            "FakeClient",
            (),
            {"chat": type("FakeChat", (), {"completions": completions})()},
        )()
        with patch("step3_agent.asyncio.sleep", return_value=None):
            result = await call_llm_with_retry(
                client, model="test-model", prompt="test", max_tokens=10, attempts=3
            )
        self.assertIs(result, marker)
        self.assertEqual(completions.calls, 3)


if __name__ == "__main__":
    unittest.main()
