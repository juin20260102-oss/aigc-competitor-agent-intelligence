"""设置页的安全边界测试。

ui/ 目录约 1200 行此前零测试。Streamlit 的渲染函数难以直测，但设置页里
两处纯逻辑是安全相关的、也最值得守：API Key 的脱敏展示，以及写入 .env
前对模型端点与企业微信 Webhook 的校验。
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from ui.settings import mask_key, save_env_dict
except ModuleNotFoundError as exc:  # streamlit 等 UI 依赖未安装
    raise unittest.SkipTest(f"缺少 UI 依赖：{exc.name}") from exc

from dotenv import dotenv_values

ALLOWED_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
GOOD_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc123"


class MaskKeyTest(unittest.TestCase):
    """脱敏结果不能泄露密钥中段。"""

    def test_empty_key(self):
        self.assertEqual(mask_key(""), "未配置")

    def test_whitespace_only_does_not_leak(self):
        """strip 后为空，不能走到切片分支去暴露原串。"""
        self.assertEqual(mask_key("    "), "•" * 8)

    def test_short_key_is_fully_masked(self):
        for key in ("a", "12345678"):
            self.assertEqual(mask_key(key), "•" * 8, key)

    def test_long_key_keeps_only_head_and_tail(self):
        key = "sk-abcdefghijklmnopqrstuvwxyz"
        masked = mask_key(key)
        self.assertTrue(masked.startswith("sk-a"))
        self.assertTrue(masked.endswith("wxyz"))
        self.assertEqual(len(masked), len(key))
        self.assertNotIn(key[4:-4], masked, "密钥中段出现在脱敏结果里")

    def test_masked_output_never_contains_full_key(self):
        for key in ("sk-" + "x" * 40, "dash-" + "y" * 12):
            self.assertNotIn(key, mask_key(key), key[:6])


class SaveEnvDictTest(unittest.TestCase):
    """写入 .env 前必须拦住不在允许列表内的端点和伪造的 Webhook。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="envtest-"))
        self.env_file = self.tmp / ".env"
        self.env_file.write_text("EXISTING_KEY=keep-me\n", encoding="utf-8")
        patcher = mock.patch("ui.settings.ENV_FILE", self.env_file)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _payload(self, **over):
        base = {"OPENAI_API_KEY": "sk-test", "OPENAI_BASE_URL": ALLOWED_URL,
                "MODEL_NAME": "qwen3.7-flash", "WECOM_WEBHOOK": ""}
        base.update(over)
        return base

    def test_rejects_base_url_outside_allowlist(self):
        with self.assertRaises(ValueError):
            save_env_dict(self._payload(OPENAI_BASE_URL="https://evil.example.com/v1"))

    def test_rejects_plain_http_base_url(self):
        with self.assertRaises(ValueError):
            save_env_dict(self._payload(OPENAI_BASE_URL="http://dashscope.aliyuncs.com/compatible-mode/v1"))

    def test_rejects_webhook_on_other_host(self):
        with self.assertRaises(ValueError):
            save_env_dict(self._payload(WECOM_WEBHOOK="https://evil.example.com/cgi-bin/webhook/send?key=x"))

    def test_rejects_webhook_without_key_param(self):
        with self.assertRaises(ValueError):
            save_env_dict(self._payload(WECOM_WEBHOOK="https://qyapi.weixin.qq.com/cgi-bin/webhook/send"))

    def test_rejects_newline_injection_in_api_key(self):
        """换行会把 .env 撕成两行，等于可以注入任意配置项。"""
        with self.assertRaises(ValueError):
            save_env_dict(self._payload(OPENAI_API_KEY="sk-good" + chr(10) + "APP_ACCESS_PASSWORD=pwned"))

    def test_accepts_valid_payload_and_keeps_unrelated_keys(self):
        save_env_dict(self._payload(WECOM_WEBHOOK=GOOD_WEBHOOK))
        saved = dotenv_values(self.env_file)
        self.assertEqual(saved["OPENAI_API_KEY"], "sk-test")
        self.assertEqual(saved["OPENAI_BASE_URL"], ALLOWED_URL)
        self.assertEqual(saved["WECOM_WEBHOOK"], GOOD_WEBHOOK)
        self.assertEqual(saved["EXISTING_KEY"], "keep-me", "无关配置项被覆盖了")

    def test_empty_webhook_is_allowed(self):
        save_env_dict(self._payload(WECOM_WEBHOOK=""))
        self.assertEqual(dotenv_values(self.env_file)["WECOM_WEBHOOK"], "")

    def test_failed_validation_leaves_env_untouched(self):
        before = self.env_file.read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            save_env_dict(self._payload(OPENAI_BASE_URL="https://evil.example.com/v1"))
        self.assertEqual(self.env_file.read_text(encoding="utf-8"), before,
                         "校验失败却已经改动了 .env")


if __name__ == "__main__":
    unittest.main()
