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


if __name__ == "__main__":
    unittest.main()
