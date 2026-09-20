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
TEMPLATE_FILE = PROJECT_ROOT / "tools" / "templates" / "dashboard.html"

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

    def test_template_does_not_hardcode_count(self):
        """文案已搬进模板文件，写死数字的风险也跟着转移到那里。"""
        for path in (TEMPLATE_FILE, PROJECT_ROOT / "tools" / "build_static_site.py"):
            # 不用 assertNotRegex：失败时它会把整个模板打进报错信息，没法读
            hit = HERO_COUNT_RE.search(path.read_text(encoding="utf-8"))
            self.assertIsNone(hit, f"{path.name} 写死了站点数：{hit.group(0) if hit else ''}")
        self.assertIn("{{TOTAL_SITES}} 家核心 AIGC 竞品站点",
                      TEMPLATE_FILE.read_text(encoding="utf-8"), "首屏文案未使用占位符")


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


class RenderTemplateTest(unittest.TestCase):
    """模板渲染函数本身的契约。"""

    def setUp(self):
        import importlib
        self.mod = importlib.import_module("tools.build_static_site")

    def test_fills_every_placeholder(self):
        out = self.mod.render_template("a={{A}} b={{B}} a2={{A}}", {"A": 1, "B": "x"})
        self.assertEqual(out, "a=1 b=x a2=1")

    def test_leaves_css_and_js_braces_untouched(self):
        """模板里 198 对字面花括号和 30 处 JS ${...} 都不能被动到。"""
        tpl = "body { color: red; } const s = `${item.name}`; n={{N}}"
        out = self.mod.render_template(tpl, {"N": 7})
        self.assertEqual(out, "body { color: red; } const s = `${item.name}`; n=7")

    def test_rejects_unknown_key(self):
        with self.assertRaises(KeyError):
            self.mod.render_template("only {{A}}", {"A": 1, "NOPE": 2})

    def test_rejects_unfilled_placeholder(self):
        with self.assertRaises(KeyError):
            self.mod.render_template("{{A}} and {{FORGOTTEN}}", {"A": 1})


class TemplateFileTest(unittest.TestCase):
    """模板已从 1381 行的 f-string 抽成独立文件。"""

    def test_template_file_exists_and_is_html(self):
        self.assertTrue(TEMPLATE_FILE.is_file(), "模板文件缺失")
        self.assertTrue(TEMPLATE_FILE.read_text(encoding="utf-8").startswith("<!DOCTYPE html>"))

    def test_builder_no_longer_embeds_the_page(self):
        src = (PROJECT_ROOT / "tools" / "build_static_site.py").read_text(encoding="utf-8")
        self.assertNotIn("<!DOCTYPE html>", src, "页面又被塞回构建器源码了")
        self.assertIn("TEMPLATE_FILE", src)

    def test_every_placeholder_in_template_is_supplied(self):
        """模板里出现的占位符必须都能被 generate_html 填上。"""
        declared = set(re.findall(r"\{\{([A-Z_]+)\}\}", TEMPLATE_FILE.read_text(encoding="utf-8")))
        html = self.mod_generate()
        self.assertTrue(declared, "模板里没有占位符，提取可能出错")
        for name in declared:
            self.assertNotIn("{{%s}}" % name, html, f"占位符 {name} 未被填充")

    def mod_generate(self):
        import importlib
        mod = importlib.import_module("tools.build_static_site")
        return mod.generate_html({"competitors": [], "reports": []})


class ShippedAssetsTest(unittest.TestCase):
    """dist 里只应有页面真正引用的截图。

    data/ 与 runtime/ 各有一套命名（旧的 host_latest.png 与迁移后的
    host--<hash>_latest.png），页面只引用其中一套。早先是两套全量复制，
    每次部署有 59% 的体积是没人会访问的文件。
    """

    @unittest.skipUnless(DIST_INDEX.exists(), "dist 尚未构建")
    def test_ships_exactly_what_the_page_references(self):
        wanted = {c["screenshot"] for c in load_site_data()["competitors"] if c.get("screenshot")}
        shipped = {p.name for p in DIST_SCREENSHOTS.glob("*.png")}
        self.assertEqual(shipped, wanted,
                         f"多余 {sorted(shipped - wanted)[:3]} / 缺失 {sorted(wanted - shipped)[:3]}")

    @unittest.skipUnless(DIST_INDEX.exists(), "dist 尚未构建")
    def test_rebuild_removes_stale_files(self):
        """上一次构建留下的文件必须被清掉，否则 dist 只增不减。"""
        import subprocess
        import sys

        stale = DIST_SCREENSHOTS / "zz_not_referenced_by_any_page.png"
        stale.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.assertTrue(stale.is_file())
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "tools" / "build_static_site.py")],
            cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr[-1000:])
        self.assertFalse(stale.exists(), "重建后陈旧截图仍留在 dist 中")

    def test_copy_assets_warns_instead_of_crashing_on_missing_source(self):
        """被引用但源目录里没有的截图，应当告警而不是让整个构建挂掉。"""
        import importlib
        import io
        import contextlib

        import shutil
        import tempfile
        from unittest import mock

        mod = importlib.import_module("tools.build_static_site")
        # 指向临时目录：copy_assets 会清掉未被引用的文件，不能让它动真实 dist
        tmp = Path(tempfile.mkdtemp(prefix="dist-probe-"))
        try:
            buf = io.StringIO()
            with mock.patch.object(mod, "DIST_DIR", tmp),                  mock.patch.object(mod, "DIST_SCREENSHOTS_DIR", tmp / "screenshots"),                  contextlib.redirect_stdout(buf):
                mod.copy_assets({"competitors": [{"screenshot": "definitely_missing_xyz.png"}]})
            self.assertIn("WARN", buf.getvalue())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
