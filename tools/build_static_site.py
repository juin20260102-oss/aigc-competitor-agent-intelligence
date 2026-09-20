#!/usr/bin/env python3
"""
AIGC 竞品态势感知看板 - 纯静态站点生成器 (Static Site Generator)
将 data/ 与 reports/ 中的结构化数据及截图打包编译为一个独立的现代化纯静态看板，
用于直接部署到 Cloudflare Pages、GitHub Pages 或任何静态托管平台。
"""

import re
import sys
import json
import shutil
import html
from pathlib import Path, PureWindowsPath
from datetime import datetime

# Windows 控制台默认可能是 GBK/cp1252，脚本的中文输出会直接抛
# UnicodeEncodeError。本地由 build_site.bat 的 chcp 65001 兜着，但 CI 上
# 直接调用就会失败，所以在这里显式声明输出编码。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_utils import RUNTIME_ROOT, merged_artifact_files  # noqa: E402

# 仓库里的 data/ 与 reports/ 是随仓库分发的演示数据；Agent 真正的产出写在
# RUNTIME_ROOT（可由 AGENT_RUNTIME_DIR 覆盖，CI 上从 R2 恢复）。静态站点
# 必须两者合并、runtime 优先，否则定时任务跑完仍会发布演示数据。
DEMO_DATA_DIR = PROJECT_ROOT / "data"
DEMO_REPORTS_DIR = PROJECT_ROOT / "reports"
RUNTIME_DATA_DIR = RUNTIME_ROOT / "data"
RUNTIME_REPORTS_DIR = RUNTIME_ROOT / "reports"

DATA_DIR = DEMO_DATA_DIR
REPORTS_DIR = DEMO_REPORTS_DIR
SNAPSHOTS_DIR = DEMO_DATA_DIR / "snapshots"
SCREENSHOTS_DIR = DEMO_DATA_DIR / "screenshots"
COMPETITORS_FILE = DEMO_DATA_DIR / "competitors.json"
DIST_DIR = PROJECT_ROOT / "dist"
DIST_SCREENSHOTS_DIR = DIST_DIR / "screenshots"
TEMPLATE_FILE = PROJECT_ROOT / "tools" / "templates" / "dashboard.html"

# runtime 优先、demo 兜底的具体来源
SNAPSHOT_SOURCES = (RUNTIME_DATA_DIR / "snapshots", SNAPSHOTS_DIR)
SCREENSHOT_SOURCES = (SCREENSHOTS_DIR, RUNTIME_DATA_DIR / "screenshots")  # 后者覆盖前者


def markdown_to_html(md_text: str) -> str:
    """
    轻量且语义完备的 Markdown 转 HTML 转换器（纯 Python 实现，零外部依赖）
    支持：标题、粗体、斜体、删除线、代码块、内联代码、无序列表、有序列表、引用、表格、分割线、链接
    """
    if not md_text:
        return ""
    
    lines = md_text.splitlines()
    out = []
    in_code_block = False
    code_block_lang = ""
    code_block_lines = []
    in_list = False
    list_type = "ul"
    in_table = False
    table_lines = []

    def flush_list():
        nonlocal in_list, list_type
        if in_list:
            out.append(f"</{list_type}>")
            in_list = False

    def render_table(t_lines):
        if len(t_lines) < 2:
            return "\n".join(t_lines)
        header_cols = [c.strip() for c in t_lines[0].strip("|").split("|")]
        body_rows = []
        for r in t_lines[2:]:
            if "|" in r:
                body_rows.append([c.strip() for c in r.strip("|").split("|")])
        
        h_html = "".join(f"<th>{inline_format(c)}</th>" for c in header_cols)
        b_html = ""
        for row in body_rows:
            while len(row) < len(header_cols):
                row.append("")
            cells = "".join(f"<td>{inline_format(c)}</td>" for c in row)
            b_html += f"<tr>{cells}</tr>\n"
        
        return f'<div class="table-container"><table class="prose-table"><thead><tr>{h_html}</tr></thead><tbody>{b_html}</tbody></table></div>'

    def inline_format(text: str) -> str:
        tokens = []
        def save_code(m):
            idx = len(tokens)
            tokens.append(f"<code>{html.escape(m.group(1))}</code>")
            return f"__CODE_TOKEN_{idx}__"
        
        text = re.sub(r"`([^`]+)`", save_code, text)
        text = html.escape(text)
        
        for i, tok in enumerate(tokens):
            text = text.replace(f"__CODE_TOKEN_{i}__", tok)
        
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
        text = re.sub(r"\*([^\*]+?)\*", r"<em>\1</em>", text)
        text = re.sub(r"_([^_]+?)_", r"<em>\1</em>", text)
        text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r'<a href="\2" target="_blank" rel="noopener noreferrer">\1 ↗</a>', text)
        text = re.sub(r"(【依据：[^】]+】)", r'<span class="evidence-badge">\1</span>', text)
        return text

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                code_content = html.escape("\n".join(code_block_lines))
                out.append(f'<pre class="code-block" data-lang="{code_block_lang}"><code>{code_content}</code></pre>')
                in_code_block = False
                code_block_lines = []
                code_block_lang = ""
            else:
                flush_list()
                in_code_block = True
                code_block_lang = stripped[3:].strip()
            i += 1
            continue

        if in_code_block:
            code_block_lines.append(line)
            i += 1
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_list()
            if not in_table:
                in_table = True
                table_lines = [stripped]
            else:
                table_lines.append(stripped)
            i += 1
            continue
        else:
            if in_table:
                out.append(render_table(table_lines))
                in_table = False
                table_lines = []

        if not stripped:
            k = i + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            if k < len(lines):
                peek = lines[k].strip()
                if in_list and (re.match(r"^\d+\.\s+", peek) if list_type == "ol" else re.match(r"^[-*+]\s+", peek)):
                    i = k
                    continue
                if in_list and (lines[k].startswith("   ") or lines[k].startswith("\t")):
                    i = k
                    continue
            flush_list()
            i += 1
            continue

        if re.match(r"^(\-{3,}|\*{3,}|_{3,})$", stripped):
            flush_list()
            out.append('<hr class="prose-hr" />')
            i += 1
            continue

        header_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if header_match:
            flush_list()
            level = len(header_match.group(1))
            h_text = header_match.group(2)
            h_id = re.sub(r"[^\w\u4e00-\u9fa5]+", "-", h_text).strip("-").lower()
            out.append(f'<h{level} id="{h_id}" class="prose-h{level}">{inline_format(h_text)}</h{level}>')
            i += 1
            continue

        if stripped.startswith(">"):
            flush_list()
            quote_text = stripped[1:].strip()
            out.append(f'<blockquote class="prose-quote">{inline_format(quote_text)}</blockquote>')
            i += 1
            continue

        ul_match = re.match(r"^[-*+]\s+(.*)$", stripped)
        if ul_match:
            if not in_list or list_type != "ul":
                flush_list()
                out.append('<ul class="prose-ul">')
                in_list = True
                list_type = "ul"
            out.append(f"<li>{inline_format(ul_match.group(1))}</li>")
            i += 1
            continue

        ol_match = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if ol_match:
            num = ol_match.group(1)
            title = ol_match.group(2)
            desc_lines = []
            j = i + 1
            while j < len(lines):
                if not lines[j].strip():
                    k = j + 1
                    while k < len(lines) and not lines[k].strip():
                        k += 1
                    if k < len(lines) and (lines[k].startswith("   ") or lines[k].startswith("\t")):
                        desc_lines.append(lines[k].strip())
                        j = k + 1
                        continue
                    break
                elif lines[j].startswith("   ") or lines[j].startswith("\t"):
                    desc_lines.append(lines[j].strip())
                    j += 1
                elif not re.match(r"^\d+\.\s+", lines[j].strip()) and not re.match(r"^[-*+]\s+", lines[j].strip()) and not lines[j].strip().startswith("#") and not lines[j].strip().startswith("---"):
                    desc_lines.append(lines[j].strip())
                    j += 1
                else:
                    break

            if not in_list or list_type != "ol":
                flush_list()
                out.append('<ol class="prose-ol">')
                in_list = True
                list_type = "ol"

            if desc_lines:
                desc_html = "<br>".join(inline_format(line_item) for line_item in desc_lines)
                out.append(f'<li value="{num}"><div class="ol-title">{inline_format(title)}</div><div class="ol-desc">{desc_html}</div></li>')
            else:
                out.append(f'<li value="{num}">{inline_format(title)}</li>')
            i = j
            continue

        flush_list()
        out.append(f'<p class="prose-p">{inline_format(stripped)}</p>')
        i += 1

    if in_code_block:
        code_content = html.escape("\n".join(code_block_lines))
        out.append(f'<pre class="code-block"><code>{code_content}</code></pre>')
    if in_table:
        out.append(render_table(table_lines))
    flush_list()

    return "\n".join(out)


def load_all_data():
    """读取竞品配置、快照档案与历史日报"""
    competitors = []
    competitors_file = next(
        (p for p in (RUNTIME_DATA_DIR / "competitors.json", COMPETITORS_FILE) if p.exists()),
        None,
    )
    if competitors_file:
        with open(competitors_file, "r", encoding="utf-8-sig") as f:
            competitors = json.load(f)

    snapshots = {}
    for sp in map(Path, merged_artifact_files(*SNAPSHOT_SOURCES, "*_latest.json")):
        try:
            with open(sp, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                url = data.get("url", "")
                if url:
                    snapshots[url.rstrip("/")] = data
        except Exception as err:
            print(f"[Warn] 读取快照失败 {sp}: {err}")

    comp_cards = []
    for c in competitors:
        url_norm = c["url"].rstrip("/")
        snap = snapshots.get(url_norm, {})
        profile = snap.get("profile", "")
        
        rating = "A"
        if "S级" in profile or "S 级" in profile or "评级：S" in profile or "评级: S" in profile:
            rating = "S"
        elif "A级" in profile or "A 级" in profile or "评级：A" in profile or "评级: A" in profile:
            rating = "A"
        elif "B级" in profile or "B 级" in profile or "评级：B" in profile or "评级: B" in profile:
            rating = "B"
        elif "C级" in profile or "C 级" in profile or "评级：C" in profile or "评级: C" in profile:
            rating = "C"

        summary = ""
        pos_match = re.search(r"产品定位[】\*：:]+([^\n]+)", profile)
        if pos_match:
            summary = pos_match.group(1).strip()
            summary = re.sub(r"【依据[：:][^】]+】", "", summary).strip()
        else:
            summary = c.get("category", "")

        features = []
        feat_matches = re.findall(r"\d+\.\s+\*\*([^\*]+)\*\*", profile)
        if feat_matches:
            features = [f.split("：")[0].split(":")[0].strip() for f in feat_matches[:4]]

        screenshot_filename = ""
        orig_shot_path = snap.get("screenshot_path", "")
        if orig_shot_path:
            # 快照里的路径可能是 Windows 反斜杠风格；PureWindowsPath 同时
            # 把 / 和 \ 当分隔符，因此在 Linux 构建时也能正确取到文件名。
            screenshot_filename = PureWindowsPath(orig_shot_path).name
        else:
            domain = url_norm.replace("https://", "").replace("http://", "").split("/")[0]
            for source in SCREENSHOT_SOURCES:
                candidate = source / f"{domain}_latest.png"
                if candidate.exists():
                    screenshot_filename = candidate.name
                    break

        update_history = snap.get("update_history", [])
        latest_update = update_history[-1] if update_history else None

        comp_cards.append({
            "name": c.get("name", ""),
            "url": c.get("url", ""),
            "category": c.get("category", "综合"),
            "enabled": c.get("enabled", True),
            "rating": rating,
            "summary": summary,
            "features": features,
            "profile_markdown": profile,
            "profile_html": markdown_to_html(profile),
            "screenshot": screenshot_filename,
            "captured_at": snap.get("captured_at", ""),
            "latest_update": latest_update,
            "update_count": len(update_history)
        })

    reports = []
    # 严格匹配 8 位日期，排除单次运行留下的 daily_report_YYYYMMDD_HHMMSS.md 中间产物
    report_files = merged_artifact_files(RUNTIME_REPORTS_DIR, REPORTS_DIR, "daily_report_????????.md")
    for rp in sorted(map(Path, report_files), key=lambda item: item.name, reverse=True):
        try:
            filename = rp.name
            date_match = re.search(r"(\d{8})", filename)
            date_str = date_match.group(1) if date_match else filename
            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}" if len(date_str) == 8 else date_str
            
            with open(rp, "r", encoding="utf-8") as f:
                content_md = f.read()

            key_takeaways = ""
            takeaway_match = re.search(r"## 🌟 今日重点提炼\s*(.*?)\s*(?=##|\Z)", content_md, re.DOTALL)
            if takeaway_match:
                key_takeaways = takeaway_match.group(1).strip()

            reports.append({
                "id": filename,
                "date": formatted_date,
                "raw_date": date_str,
                "title": f"AIGC 竞品态势感知日报 ({formatted_date})",
                "markdown": content_md,
                "html": markdown_to_html(content_md),
                "takeaway_html": markdown_to_html(key_takeaways) if key_takeaways else ""
            })
        except Exception as err:
            print(f"[Warn] 读取日报失败 {rp}: {err}")

    return {
        "competitors": comp_cards,
        "reports": reports,
        "build_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def copy_assets(data: dict) -> None:
    """只把页面真正引用的截图复制进 dist/screenshots/。

    早先是把 data/ 和 runtime/ 两处的 *.png 全量复制。两处各有一套命名
    （旧的 host_latest.png 与迁移后的 host--<hash>_latest.png），而页面
    只会引用其中一套，于是每次部署有一半以上的体积是没人会访问的文件。
    """
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    DIST_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    wanted = {c["screenshot"] for c in data["competitors"] if c.get("screenshot")}

    available: dict[str, Path] = {}
    for source in SCREENSHOT_SOURCES:  # 顺序即优先级，runtime 覆盖 demo
        if source.exists():
            for img in source.glob("*.png"):
                if img.name in wanted:
                    available[img.name] = img

    for name, img in available.items():
        shutil.copy2(img, DIST_SCREENSHOTS_DIR / name)

    # 清掉上一次构建留下、本次不再引用的文件，否则 dist 只增不减
    for stale in DIST_SCREENSHOTS_DIR.glob("*.png"):
        if stale.name not in wanted:
            stale.unlink()

    missing = sorted(wanted - available.keys())
    if missing:
        print(f"[WARN] {len(missing)} 张被引用的截图在源目录中缺失：{', '.join(missing[:3])}")
    print(f"[OK] 成功复制 {len(available)} 张截图证据到 dist/screenshots/")


def render_template(template: str, values: dict[str, object]) -> str:
    """把 {{KEY}} 占位符替换为对应取值。

    模板里含 211 条 CSS 规则和一段 JS，其中 198 对花括号是字面量，JS 还用了
    30 处 ${...} 模板字面量。用 f-string 就要手工双写每个花括号，用
    string.Template 又会和 ${...} 冲突，所以这里用显式占位符——只有 7 个键，
    直接替换最不容易出错。
    """
    missing = [key for key in values if "{{%s}}" % key not in template]
    if missing:
        raise KeyError(f"模板中不存在占位符：{', '.join(sorted(missing))}")
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{%s}}" % key, str(value))
    leftover = re.findall(r"\{\{([A-Z_]+)\}\}", rendered)
    if leftover:
        raise KeyError(f"占位符未被填充：{', '.join(sorted(set(leftover)))}")
    return rendered


def generate_html(data: dict) -> str:
    """生成具备顶尖视觉美感、自包含交互逻辑的单页 HTML"""
    ratings_count = {"S": 0, "A": 0, "B": 0, "C": 0}
    for c in data["competitors"]:
        r = c.get("rating", "A")
        ratings_count[r] = ratings_count.get(r, 0) + 1

    json_data_safe = json.dumps(data, ensure_ascii=False).replace("</script>", "<\\/script>")

    return render_template(
        TEMPLATE_FILE.read_text(encoding="utf-8"),
        {
            # 首屏文案与统计卡片必须同源，早先写死 16 家而实际 21 家就是这么来的
            "TOTAL_SITES": len(data["competitors"]),
            "TOTAL_REPORTS": len(data["reports"]),
            "LATEST_REPORT_DATE": data["reports"][0]["date"] if data["reports"] else "N/A",
            "RATING_S": ratings_count.get("S", 0),
            "RATING_A": ratings_count.get("A", 0),
            "RATING_B": ratings_count.get("B", 0),
            "SITE_DATA_JSON": json_data_safe,
        },
    )


def build():
    print("[*] 开始构建 AIGC 竞品看板静态站点...")
    data = load_all_data()
    print(f"[OK] 成功加载 {len(data['competitors'])} 个竞品档案，{len(data['reports'])} 期历史日报")

    copy_assets(data)

    html_content = generate_html(data)
    index_path = DIST_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[SUCCESS] 静态单页已成功生成: {index_path}")
    print(f"[INFO] 静态站点输出目录: {DIST_DIR}")
    print("[INFO] 可直接部署至 Cloudflare Pages，无需任何服务端和 API Key！")


if __name__ == "__main__":
    build()
