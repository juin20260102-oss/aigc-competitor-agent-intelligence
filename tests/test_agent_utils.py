import json
import socket
import tempfile
import time
import tomllib
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
    resolve_site_artifact,
    site_key_for_url,
    validate_model_base_url,
    validate_public_http_url,
    validate_wecom_webhook,
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

    def test_meaningful_link_target_change_is_detected(self):
        old = "[价格说明](https://example.com/pricing/basic)"
        new = "[价格说明](https://example.com/pricing/pro)"
        result = assess_change(old, new)
        self.assertTrue(result.changed)
        self.assertIn("/pro", result.diff_context)

    def test_small_noise_is_skipped(self):
        old = "这是长期稳定的产品介绍和功能说明，内容不会频繁变化。" * 20
        new = old + " 1"
        self.assertFalse(assess_change(old, new).changed)

    def test_small_high_signal_price_change_is_not_skipped_on_long_page(self):
        stable = "长期稳定的产品介绍与帮助中心说明。\n" * 500
        result = assess_change(stable + "基础套餐价格 99 元", stable + "基础套餐价格 199 元")
        self.assertTrue(result.changed)

    def test_large_page_small_change_completes_quickly(self):
        stable = "长期稳定的产品功能介绍。\n" * 8000
        started = time.perf_counter()
        result = assess_change(stable + "基础套餐 99 元", stable + "基础套餐 199 元")
        elapsed = time.perf_counter() - started
        self.assertTrue(result.changed)
        self.assertLess(elapsed, 0.5)


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

    def test_model_base_url_must_be_explicitly_allowed(self):
        allowed = ("https://api.example.com/v1",)
        self.assertEqual(
            validate_model_base_url("https://api.example.com/v1/", allowed=allowed),
            "https://api.example.com/v1",
        )
        with self.assertRaises(ValueError):
            validate_model_base_url("https://attacker.example/v1", allowed=allowed)

    def test_wecom_webhook_is_restricted_to_official_endpoint(self):
        valid = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"
        self.assertEqual(validate_wecom_webhook(valid), valid)
        for invalid in (
            "http://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x",
            "https://example.com/cgi-bin/webhook/send?key=x",
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_wecom_webhook(invalid)

    def test_streamlit_is_bound_to_loopback(self):
        config = tomllib.loads((Path(__file__).parents[1] / ".streamlit" / "config.toml").read_text())
        self.assertEqual(config["server"]["address"], "127.0.0.1")
        self.assertTrue(config["server"]["enableXsrfProtection"])


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
        key = site_key_for_url("https://example.com/products/a")
        self.assertTrue(key.startswith("example.com_products_a--"))
        self.assertLessEqual(len(key), 120)

    def test_site_key_avoids_legacy_path_collision(self):
        self.assertNotEqual(
            site_key_for_url("https://example.com/a_b"),
            site_key_for_url("https://example.com/a/b"),
        )

    def test_legacy_runtime_artifact_is_copied_to_current_key(self):
        url = "https://example.com/products/a"
        with tempfile.TemporaryDirectory() as runtime, tempfile.TemporaryDirectory() as demo:
            legacy = Path(runtime) / "example.com_products_a_latest.json"
            legacy.write_text('{"legacy": true}', encoding="utf-8")
            resolved = resolve_site_artifact(runtime, demo, url, "_latest.json")
            self.assertIsNotNone(resolved)
            self.assertNotEqual(resolved, legacy)
            self.assertEqual(resolved.read_bytes(), legacy.read_bytes())

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
