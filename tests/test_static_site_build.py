"""静态站点构建产物的契约测试。

覆盖两类曾经上线的回归：
1. 快照里的 Windows 反斜杠路径在 Linux 构建时被原样带进 HTML，导致截图全部 404；
2. 首屏文案写死站点数，与 competitors.json 的真实数量对不上。
"""

import json
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_INDEX = PROJECT_ROOT / "dist" / "index.html"
DIST_SCREENSHOTS = PROJECT_ROOT / "dist" / "screenshots"
COMPETITORS_FILE = PROJECT_ROOT / "data" / "competitors.json"

SITE_DATA_RE = re.compile(r"window\.SITE_DATA\s*=\s*(\{.*?\});?\s*\n", re.S)
HERO_COUNT_RE = re.compile(r"(\d+)\s*家核心 AIGC 竞品站点")


def load_site_data() -> dict:
    return json.loads(SITE_DATA_RE.search(DIST_INDEX.read_text(encoding="utf-8")).group(1))


class ScreenshotPathTest(unittest.TestCase):
    """截图字段必须是可直接拼进 ./screenshots/ 的裸文件名。"""

    def test_basename_extraction_is_platform_independent(self):
        from tools.build_static_site import PureWindowsPath

        # 存量快照写的是 Windows 风格；新写入的是正斜杠。两者都要能取到文件名。
        for raw in ("data" + chr(92) + "screenshots" + chr(92) + "a.png", "data/screenshots/a.png"):
            self.assertEqual(PureWindowsPath(raw).name, "a.png", raw)

    @unittest.skipUnless(DIST_INDEX.exists(), "dist 尚未构建")
    def test_dist_screenshot_fields_are_bare_filenames(self):
        for comp in load_site_data()["competitors"]:
            shot = comp.get("screenshot", "")
            if not shot:
                continue
            self.assertNotIn("/", shot, f"{comp['name']} 的截图字段含路径分隔符")
            self.assertNotIn(chr(92), shot, f"{comp['name']} 的截图字段含反斜杠")

    @unittest.skipUnless(DIST_INDEX.exists(), "dist 尚未构建")
    def test_every_referenced_screenshot_exists(self):
        for comp in load_site_data()["competitors"]:
            shot = comp.get("screenshot", "")
            if shot:
                self.assertTrue((DIST_SCREENSHOTS / shot).is_file(), f"缺少截图资源：{shot}")


class HeroCopyTest(unittest.TestCase):
    """首屏文案的站点数必须与数据同源。"""

    @unittest.skipUnless(DIST_INDEX.exists(), "dist 尚未构建")
    def test_hero_count_matches_competitors(self):
        html = DIST_INDEX.read_text(encoding="utf-8")
        match = HERO_COUNT_RE.search(html)
        self.assertIsNotNone(match, "首屏未找到站点数文案")
        self.assertEqual(int(match.group(1)), len(load_site_data()["competitors"]))

    def test_source_does_not_hardcode_count(self):
        builder = (PROJECT_ROOT / "tools" / "build_static_site.py").read_text(encoding="utf-8")
        self.assertNotRegex(builder, r"\d+\s*家核心 AIGC 竞品站点", "构建器仍写死了站点数")


class SnapshotPathWriterTest(unittest.TestCase):
    """新写入的快照路径必须可移植（正斜杠）。"""

    def test_writers_use_forward_slashes(self):
        for name in ("onboard_competitors.py", "register_new_competitors.py"):
            src = (PROJECT_ROOT / "tools" / name).read_text(encoding="utf-8")
            self.assertIn('f"data/screenshots/{shot_file}"', src, name)
            self.assertNotIn("data" + chr(92) * 2 + "screenshots", src, f"{name} 仍在写 Windows 路径")


class RuntimePrecedenceTest(unittest.TestCase):
    """构建器必须读 AGENT_RUNTIME_DIR 的真实产出，而不是只读仓库里的演示数据。

    定时任务在 CI 上把 runtime 从 R2 恢复到 AGENT_RUNTIME_DIR；如果构建器
    只看 data/ 和 reports/，跑完一整轮也只会发布演示数据。
    """

    SENTINEL_URL = "https://runtime-sentinel.example"
    PROFILE = "### 【产品基准深度画像】 - **竞争力评级**：**S级**。"

    def _build(self, env=None):
        import subprocess
        import sys

        return subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "tools" / "build_static_site.py")],
            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
        )

    def test_runtime_overrides_demo_data(self):
        import os
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="sitebuild-rt-"))
        try:
            (tmp / "data" / "snapshots").mkdir(parents=True)
            (tmp / "data" / "screenshots").mkdir(parents=True)
            (tmp / "reports").mkdir()

            (tmp / "data" / "competitors.json").write_text(
                json.dumps([{"url": self.SENTINEL_URL, "name": "RUNTIME哨兵",
                             "category": "测试", "enabled": True}], ensure_ascii=False),
                encoding="utf-8",
            )
            (tmp / "data" / "snapshots" / "runtime-sentinel.example_latest.json").write_text(
                json.dumps({"url": self.SENTINEL_URL, "content": "x", "profile": self.PROFILE,
                            "screenshot_path": "data/screenshots/sentinel_latest.png",
                            "captured_at": "2026-09-16T00:00:00", "update_history": []},
                           ensure_ascii=False),
                encoding="utf-8",
            )
            shutil.copy(next((PROJECT_ROOT / "data" / "screenshots").glob("*.png")),
                        tmp / "data" / "screenshots" / "sentinel_latest.png")
            (tmp / "reports" / "daily_report_20260915.md").write_text("# 哨兵", encoding="utf-8")

            result = self._build(env=dict(os.environ, AGENT_RUNTIME_DIR=str(tmp)))
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])

            data = load_site_data()
            self.assertEqual([c["name"] for c in data["competitors"]], ["RUNTIME哨兵"],
                             "竞品配置未采用 runtime")
            self.assertIn("2026-09-15", [r.get("date") for r in data["reports"]],
                          "runtime 日报未被合并进来")
            self.assertTrue((DIST_SCREENSHOTS / "sentinel_latest.png").is_file(),
                            "runtime 截图未复制到 dist")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            self._build()  # 还原成仓库默认数据的产物，避免污染后续步骤

    def test_intermediate_run_reports_are_excluded(self):
        """daily_report_YYYYMMDD_HHMMSS.md 是单次运行的中间产物，不应进站点。"""
        builder = (PROJECT_ROOT / "tools" / "build_static_site.py").read_text(encoding="utf-8")
        self.assertIn('"daily_report_????????.md"', builder)

    def test_builder_reads_runtime_root(self):
        src = (PROJECT_ROOT / "tools" / "build_static_site.py").read_text(encoding="utf-8")
        self.assertIn("RUNTIME_ROOT", src, "构建器没有引用 RUNTIME_ROOT")
        self.assertIn("merged_artifact_files", src, "构建器没有复用 runtime/demo 合并助手")


if __name__ == "__main__":
    unittest.main()
