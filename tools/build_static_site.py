#!/usr/bin/env python3
"""
AIGC 竞品态势感知看板 - 纯静态站点生成器 (Static Site Generator)
将 data/ 与 reports/ 中的结构化数据及截图打包编译为一个独立的现代化纯静态看板，
用于直接部署到 Cloudflare Pages、GitHub Pages 或任何静态托管平台。
"""

import re
import json
import shutil
import html
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
COMPETITORS_FILE = DATA_DIR / "competitors.json"
DIST_DIR = PROJECT_ROOT / "dist"
DIST_SCREENSHOTS_DIR = DIST_DIR / "screenshots"


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
    if COMPETITORS_FILE.exists():
        with open(COMPETITORS_FILE, "r", encoding="utf-8-sig") as f:
            competitors = json.load(f)

    snapshots = {}
    for sp in SNAPSHOTS_DIR.glob("*_latest.json"):
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
            screenshot_filename = Path(orig_shot_path).name
        else:
            domain = url_norm.replace("https://", "").replace("http://", "").split("/")[0]
            candidate = SCREENSHOTS_DIR / f"{domain}_latest.png"
            if candidate.exists():
                screenshot_filename = candidate.name

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
    for rp in sorted(REPORTS_DIR.glob("daily_report_*.md"), reverse=True):
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


def copy_assets():
    """复制截图资源到 dist/screenshots/"""
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    DIST_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    
    count = 0
    if SCREENSHOTS_DIR.exists():
        for img in SCREENSHOTS_DIR.glob("*.png"):
            dest = DIST_SCREENSHOTS_DIR / img.name
            shutil.copy2(img, dest)
            count += 1
    print(f"[OK] 成功复制 {count} 张截图证据到 dist/screenshots/")


def generate_html(data: dict) -> str:
    """生成具备顶尖视觉美感、自包含交互逻辑的单页 HTML"""
    ratings_count = {"S": 0, "A": 0, "B": 0, "C": 0}
    for c in data["competitors"]:
        r = c.get("rating", "A")
        ratings_count[r] = ratings_count.get(r, 0) + 1

    total_sites = len(data["competitors"])
    total_reports = len(data["reports"])
    latest_report_date = data["reports"][0]["date"] if data["reports"] else "N/A"

    json_data_safe = json.dumps(data, ensure_ascii=False).replace("</script>", "<\\/script>")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIGC 竞品态势感知看板 · Intelligence Hub</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-base: #060911;
            --bg-surface: #0E131F;
            --bg-card: rgba(18, 24, 38, 0.75);
            --bg-card-hover: rgba(28, 36, 56, 0.85);
            --bg-glass: rgba(14, 19, 31, 0.85);
            --border-subtle: rgba(255, 255, 255, 0.08);
            --border-hover: rgba(59, 130, 246, 0.45);
            
            --text-main: #F8FAFC;
            --text-secondary: #CBD5E1;
            --text-muted: #8492A6;
            --text-dim: #4B5563;

            --primary: #3B82F6;
            --primary-glow: rgba(59, 130, 246, 0.35);
            --accent-purple: #8B5CF6;
            --accent-emerald: #10B981;
            --accent-amber: #F59E0B;
            --accent-rose: #F43F5E;

            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 18px;
            --radius-full: 9999px;

            --shadow-card: 0 4px 20px -2px rgba(0, 0, 0, 0.5);
            --shadow-glow: 0 0 25px rgba(59, 130, 246, 0.25);
            --shadow-s: 0 0 20px rgba(245, 158, 11, 0.3);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            -webkit-font-smoothing: antialiased;
        }}

        body {{
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            background-color: var(--bg-base);
            color: var(--text-main);
            min-height: 100vh;
            line-height: 1.6;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 15% 10%, rgba(59, 130, 246, 0.12) 0%, transparent 40%),
                radial-gradient(circle at 85% 20%, rgba(139, 92, 246, 0.12) 0%, transparent 40%),
                radial-gradient(circle at 50% 80%, rgba(16, 185, 129, 0.06) 0%, transparent 50%);
            background-attachment: fixed;
        }}

        /* 顶部通栏导航 */
        header.site-header {{
            position: sticky;
            top: 0;
            z-index: 50;
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            background: var(--bg-glass);
            border-bottom: 1px solid var(--border-subtle);
            padding: 0.9rem 2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .logo-area {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .logo-icon {{
            width: 38px;
            height: 38px;
            border-radius: var(--radius-md);
            background: linear-gradient(135deg, var(--primary) 0%, var(--accent-purple) 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
            box-shadow: 0 0 16px var(--primary-glow);
        }}

        .brand-title {{
            font-size: 1.15rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, #FFFFFF 30%, #94A3B8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .brand-badge {{
            font-size: 0.72rem;
            padding: 2px 8px;
            border-radius: var(--radius-full);
            background: rgba(16, 185, 129, 0.15);
            color: var(--accent-emerald);
            border: 1px solid rgba(16, 185, 129, 0.3);
            font-weight: 600;
        }}

        .header-nav {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(255, 255, 255, 0.04);
            padding: 4px;
            border-radius: var(--radius-full);
            border: 1px solid var(--border-subtle);
        }}

        .nav-btn {{
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 7px 18px;
            border-radius: var(--radius-full);
            font-size: 0.88rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .nav-btn:hover {{
            color: var(--text-main);
        }}

        .nav-btn.active {{
            background: linear-gradient(135deg, var(--primary) 0%, #2563EB 100%);
            color: white;
            box-shadow: 0 2px 12px var(--primary-glow);
        }}

        .header-meta {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 0.8rem;
            color: var(--text-muted);
        }}

        .pulse-dot {{
            width: 8px;
            height: 8px;
            background-color: var(--accent-emerald);
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 10px var(--accent-emerald);
            animation: pulse 2s infinite ease-in-out;
        }}

        @keyframes pulse {{
            0%, 100% {{ transform: scale(1); opacity: 1; }}
            50% {{ transform: scale(1.3); opacity: 0.6; }}
        }}

        /* 主体布局 */
        main.container {{
            max-width: 1440px;
            margin: 0 auto;
            padding: 2rem 2rem 4rem 2rem;
        }}

        /* Hero 与 指标卡片 */
        .hero-banner {{
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            margin-bottom: 2rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border-subtle);
        }}

        .hero-heading h1 {{
            font-size: 2.2rem;
            font-weight: 800;
            letter-spacing: -0.03em;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #FFFFFF 0%, #E2E8F0 50%, #94A3B8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .hero-heading p {{
            color: var(--text-muted);
            font-size: 0.95rem;
            max-width: 680px;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1.2rem;
            margin-bottom: 2.5rem;
        }}

        .stat-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            padding: 1.25rem 1.4rem;
            position: relative;
            overflow: hidden;
            backdrop-filter: blur(12px);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}

        .stat-card:hover {{
            transform: translateY(-3px);
            border-color: var(--border-hover);
        }}

        .stat-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--primary), var(--accent-purple));
        }}

        .stat-card.stat-s::before {{
            background: linear-gradient(90deg, #EF4444, #F59E0B);
        }}

        .stat-card.stat-emerald::before {{
            background: linear-gradient(90deg, #10B981, #06B6D4);
        }}

        .stat-label {{
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.4rem;
        }}

        .stat-number {{
            font-size: 2.1rem;
            font-weight: 800;
            color: var(--text-main);
            letter-spacing: -0.03em;
            line-height: 1.1;
        }}

        .stat-desc {{
            font-size: 0.78rem;
            color: var(--text-secondary);
            margin-top: 0.4rem;
        }}

        /* 标签页容器 */
        .tab-content {{
            display: none;
            animation: fadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        .tab-content.active {{
            display: block;
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(8px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        /* ========== TAB 1: 报告阅读器 ========== */
        .reports-layout {{
            display: grid;
            grid-template-columns: 280px 1fr;
            gap: 2rem;
            align-items: start;
        }}

        .reports-sidebar {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            padding: 1rem;
            position: sticky;
            top: 5rem;
        }}

        .sidebar-title {{
            font-size: 0.82rem;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            padding: 0.4rem 0.6rem 0.8rem 0.6rem;
            border-bottom: 1px solid var(--border-subtle);
            margin-bottom: 0.6rem;
        }}

        .report-nav-item {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.75rem 0.9rem;
            border-radius: var(--radius-sm);
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 0.88rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            margin-bottom: 4px;
        }}

        .report-nav-item:hover {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-main);
        }}

        .report-nav-item.active {{
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(139, 92, 246, 0.2) 100%);
            border: 1px solid rgba(59, 130, 246, 0.4);
            color: #60A5FA;
        }}

        .report-article {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-lg);
            padding: 2.5rem;
            box-shadow: var(--shadow-card);
        }}

        .report-toolbar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--border-subtle);
        }}

        .report-meta-tag {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }}

        .action-btn {{
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid var(--border-subtle);
            color: var(--text-secondary);
            padding: 0.45rem 0.9rem;
            border-radius: var(--radius-sm);
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}

        .action-btn:hover {{
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }}

        /* Markdown 文章排版 */
        .prose-h1 {{
            font-size: 1.8rem;
            font-weight: 800;
            margin: 1.5rem 0 1rem 0;
            color: #FFFFFF;
            border-bottom: 1px solid var(--border-subtle);
            padding-bottom: 0.5rem;
        }}

        .prose-h2 {{
            font-size: 1.35rem;
            font-weight: 700;
            margin: 2rem 0 1rem 0;
            color: #93C5FD;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .prose-h3 {{
            font-size: 1.15rem;
            font-weight: 700;
            margin: 1.4rem 0 0.8rem 0;
            color: #F1F5F9;
        }}

        .prose-p {{
            font-size: 0.95rem;
            color: var(--text-secondary);
            line-height: 1.75;
            margin-bottom: 1rem;
        }}

        .prose-ul, .prose-ol {{
            margin: 0.8rem 0 1.2rem 1.6rem;
            color: var(--text-secondary);
            font-size: 0.93rem;
            line-height: 1.7;
        }}

        .prose-ul li {{
            margin-bottom: 0.4rem;
        }}

        .prose-ol {{
            padding-left: 1.2rem;
            margin: 1.2rem 0;
        }}

        .prose-ol > li {{
            margin-bottom: 1.4rem;
            line-height: 1.75;
        }}

        .prose-ol > li::marker {{
            color: #60A5FA;
            font-weight: 800;
            font-size: 1.05rem;
        }}

        .ol-title {{
            font-weight: 700;
            color: var(--text-main);
            margin-bottom: 0.45rem;
            font-size: 1rem;
        }}

        .ol-desc {{
            color: var(--text-secondary);
            font-size: 0.92rem;
            line-height: 1.75;
        }}

        .prose-quote {{
            border-left: 3px solid var(--primary);
            background: rgba(59, 130, 246, 0.08);
            padding: 0.9rem 1.2rem;
            border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
            margin: 1.2rem 0;
            color: #E2E8F0;
            font-size: 0.92rem;
        }}

        .prose-hr {{
            border: none;
            height: 1px;
            background: var(--border-subtle);
            margin: 2rem 0;
        }}

        .evidence-badge {{
            background: rgba(16, 185, 129, 0.12);
            color: #34D399;
            border: 1px solid rgba(16, 185, 129, 0.25);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.82rem;
            font-family: 'JetBrains Mono', monospace;
        }}

        .table-container {{
            overflow-x: auto;
            margin: 1.5rem 0;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border-subtle);
        }}

        .prose-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
            text-align: left;
        }}

        .prose-table th {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-main);
            font-weight: 600;
            padding: 0.8rem 1rem;
            border-bottom: 1px solid var(--border-subtle);
        }}

        .prose-table td {{
            padding: 0.8rem 1rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            color: var(--text-secondary);
        }}

        .prose-table tr:hover td {{
            background: rgba(255, 255, 255, 0.02);
        }}

        .code-block {{
            background: #0B0F19;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            padding: 1.1rem;
            margin: 1.2rem 0;
            overflow-x: auto;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: #38BDF8;
            line-height: 1.6;
        }}

        /* ========== TAB 2: 竞品矩阵 ========== */
        .filter-bar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 1.8rem;
            flex-wrap: wrap;
        }}

        .search-box {{
            flex: 1;
            min-width: 280px;
            position: relative;
        }}

        .search-input {{
            width: 100%;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-full);
            padding: 0.65rem 1.2rem 0.65rem 2.8rem;
            color: var(--text-main);
            font-size: 0.9rem;
            outline: none;
            transition: all 0.2s ease;
        }}

        .search-input:focus {{
            border-color: var(--primary);
            box-shadow: 0 0 16px var(--primary-glow);
        }}

        .search-icon {{
            position: absolute;
            left: 1rem;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            font-size: 0.95rem;
        }}

        .filter-pills {{
            display: flex;
            gap: 6px;
        }}

        .filter-pill {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-subtle);
            color: var(--text-muted);
            padding: 0.45rem 1rem;
            border-radius: var(--radius-full);
            font-size: 0.82rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .filter-pill:hover {{
            color: var(--text-main);
        }}

        .filter-pill.active {{
            background: rgba(59, 130, 246, 0.2);
            border-color: var(--primary);
            color: #60A5FA;
        }}

        .competitors-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 1.5rem;
        }}

        .comp-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
        }}

        .comp-card:hover {{
            transform: translateY(-4px);
            border-color: var(--border-hover);
            box-shadow: 0 12px 30px -4px rgba(0, 0, 0, 0.6);
        }}

        .card-header-bar {{
            padding: 1.1rem 1.3rem;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        }}

        .comp-title-group h3 {{
            font-size: 1.15rem;
            font-weight: 700;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .comp-category {{
            font-size: 0.72rem;
            color: var(--text-muted);
            margin-top: 2px;
        }}

        .rating-badge {{
            padding: 3px 9px;
            border-radius: 6px;
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.02em;
        }}

        .rating-s {{
            background: linear-gradient(135deg, #EF4444 0%, #F59E0B 100%);
            color: white;
            box-shadow: 0 0 12px rgba(239, 68, 68, 0.4);
        }}

        .rating-a {{
            background: linear-gradient(135deg, #3B82F6 0%, #06B6D4 100%);
            color: white;
        }}

        .rating-b {{
            background: rgba(255, 255, 255, 0.1);
            color: #CBD5E1;
        }}

        .card-preview-thumb {{
            width: 100%;
            height: 160px;
            background: #0B0F19;
            overflow: hidden;
            position: relative;
            cursor: pointer;
        }}

        .card-preview-thumb img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            object-position: top;
            transition: transform 0.4s ease;
        }}

        .card-preview-thumb:hover img {{
            transform: scale(1.05);
        }}

        .thumb-overlay {{
            position: absolute;
            inset: 0;
            background: linear-gradient(to top, rgba(14, 19, 31, 0.9) 0%, transparent 60%);
            display: flex;
            align-items: flex-end;
            padding: 0.8rem;
            font-size: 0.75rem;
            color: var(--text-muted);
        }}

        .card-body {{
            padding: 1.2rem;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
        }}

        .comp-summary {{
            font-size: 0.88rem;
            color: var(--text-secondary);
            line-height: 1.55;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}

        .comp-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
        }}

        .feature-tag {{
            background: rgba(255, 255, 255, 0.05);
            color: #94A3B8;
            font-size: 0.72rem;
            padding: 2px 7px;
            border-radius: 4px;
        }}

        .latest-change-box {{
            background: rgba(16, 185, 129, 0.08);
            border-left: 2px solid var(--accent-emerald);
            padding: 0.6rem 0.8rem;
            border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
            font-size: 0.78rem;
            color: #A7F3D0;
            margin-top: auto;
        }}

        .card-footer-actions {{
            padding: 0.8rem 1.2rem;
            background: rgba(0, 0, 0, 0.2);
            border-top: 1px solid rgba(255, 255, 255, 0.04);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .card-btn {{
            background: transparent;
            border: 1px solid var(--border-subtle);
            color: var(--text-secondary);
            padding: 0.4rem 0.85rem;
            border-radius: var(--radius-sm);
            font-size: 0.78rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .card-btn:hover {{
            background: rgba(255, 255, 255, 0.08);
            color: white;
        }}

        .card-btn-primary {{
            background: rgba(59, 130, 246, 0.15);
            border-color: rgba(59, 130, 246, 0.4);
            color: #93C5FD;
        }}

        .card-btn-primary:hover {{
            background: var(--primary);
            color: white;
        }}

        /* ========== TAB 3: 截图证据库 ========== */
        .gallery-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 1.8rem;
        }}

        .gallery-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            overflow: hidden;
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}

        .gallery-card:hover {{
            transform: translateY(-3px);
            border-color: var(--border-hover);
        }}

        .gallery-img-wrapper {{
            width: 100%;
            height: 240px;
            background: #0B0F19;
            position: relative;
            cursor: pointer;
            overflow: hidden;
        }}

        .gallery-img-wrapper img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            object-position: top;
            transition: transform 0.3s ease;
        }}

        .gallery-img-wrapper:hover img {{
            transform: scale(1.03);
        }}

        .gallery-overlay {{
            position: absolute;
            inset: 0;
            background: rgba(6, 9, 17, 0.6);
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0;
            transition: opacity 0.2s ease;
        }}

        .gallery-img-wrapper:hover .gallery-overlay {{
            opacity: 1;
        }}

        .zoom-tip {{
            background: rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(8px);
            padding: 6px 14px;
            border-radius: var(--radius-full);
            font-size: 0.8rem;
            font-weight: 600;
            color: white;
        }}

        .gallery-caption {{
            padding: 1rem 1.2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.82rem;
        }}

        .gallery-title {{
            font-weight: 700;
            color: var(--text-main);
        }}

        .gallery-time {{
            color: var(--text-muted);
            font-size: 0.75rem;
        }}

        /* 模态弹窗 (Modal) */
        .modal-backdrop {{
            position: fixed;
            inset: 0;
            background: rgba(3, 7, 18, 0.85);
            backdrop-filter: blur(12px);
            z-index: 100;
            display: none;
            align-items: center;
            justify-content: center;
            padding: 2rem;
        }}

        .modal-backdrop.active {{
            display: flex;
        }}

        .modal-card {{
            background: #0E1424;
            border: 1px solid var(--border-hover);
            border-radius: var(--radius-lg);
            width: 100%;
            max-width: 860px;
            max-height: 85vh;
            display: flex;
            flex-direction: column;
            box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.9);
            animation: modalPop 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        @keyframes modalPop {{
            from {{ transform: scale(0.95); opacity: 0; }}
            to {{ transform: scale(1); opacity: 1; }}
        }}

        .modal-header {{
            padding: 1.5rem 2rem;
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .modal-header h2 {{
            font-size: 1.35rem;
            font-weight: 800;
            color: white;
        }}

        .modal-close-btn {{
            background: rgba(255, 255, 255, 0.08);
            border: none;
            color: var(--text-muted);
            width: 32px;
            height: 32px;
            border-radius: 50%;
            cursor: pointer;
            font-size: 1.1rem;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
        }}

        .modal-close-btn:hover {{
            background: rgba(239, 68, 68, 0.2);
            color: #EF4444;
        }}

        .modal-content {{
            padding: 2rem;
            overflow-y: auto;
            flex: 1;
        }}

        /* 灯箱 (Lightbox) */
        .lightbox-backdrop {{
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.94);
            z-index: 200;
            display: none;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 2rem;
        }}

        .lightbox-backdrop.active {{
            display: flex;
        }}

        .lightbox-img {{
            max-width: 90vw;
            max-height: 85vh;
            border-radius: var(--radius-sm);
            box-shadow: 0 0 40px rgba(0,0,0,0.8);
            object-fit: contain;
        }}

        .lightbox-caption {{
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-top: 1rem;
            font-weight: 600;
        }}

        .lightbox-close {{
            position: absolute;
            top: 1.5rem;
            right: 2rem;
            background: rgba(255, 255, 255, 0.1);
            border: none;
            color: white;
            font-size: 1.5rem;
            width: 44px;
            height: 44px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
        }}

        .lightbox-close:hover {{
            background: #EF4444;
        }}

        @media (max-width: 1024px) {{
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .reports-layout {{ grid-template-columns: 1fr; }}
            .reports-sidebar {{ position: static; }}
        }}

        @media (max-width: 640px) {{
            header.site-header {{ padding: 0.8rem 1rem; }}
            main.container {{ padding: 1rem 1rem 3rem 1rem; }}
            .stats-grid {{ grid-template-columns: 1fr; }}
            .hero-banner {{ flex-direction: column; align-items: flex-start; gap: 1rem; }}
            .competitors-grid {{ grid-template-columns: 1fr; }}
            .filter-bar {{ flex-direction: column; align-items: stretch; }}
        }}
    </style>
</head>
<body>

    <header class="site-header">
        <div class="logo-area">
            <div class="logo-icon">⚡</div>
            <div>
                <div class="brand-title">AIGC 竞品态势感知看板</div>
            </div>
            <span class="brand-badge">Intelligence Hub</span>
        </div>

        <nav class="header-nav">
            <button class="nav-btn active" onclick="switchTab('reports')">📑 每日情报</button>
            <button class="nav-btn" onclick="switchTab('competitors')">🌐 竞品全景</button>
            <button class="nav-btn" onclick="switchTab('gallery')">🖼️ 截图证据</button>
        </nav>

        <div class="header-meta">
            <span class="pulse-dot"></span>
            <span>数据更新: {latest_report_date}</span>
        </div>
    </header>

    <main class="container">
        <div class="hero-banner">
            <div class="hero-heading">
                <h1>全景态势洞察与版本演进</h1>
                <p>自动化监控 {total_sites} 家核心 AIGC 竞品站点，固化网页正文、渲染截图与结构化引文证据，生成深度画像与每日版本迭代分析。</p>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">监控站点总数</div>
                <div class="stat-number">{total_sites}</div>
                <div class="stat-desc">涵盖设计、视频量产、电商商拍</div>
            </div>
            <div class="stat-card stat-s">
                <div class="stat-label">S 级核心竞品</div>
                <div class="stat-number">{ratings_count.get("S", 0)}</div>
                <div class="stat-desc">重点行业标杆与生态引领者</div>
            </div>
            <div class="stat-card stat-emerald">
                <div class="stat-label">A 级主力竞品</div>
                <div class="stat-number">{ratings_count.get("A", 0)}</div>
                <div class="stat-desc">商业化成熟与产品迭代密集</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">已归档日报</div>
                <div class="stat-number">{total_reports}</div>
                <div class="stat-desc">最新报告：{latest_report_date}</div>
            </div>
        </div>

        <!-- TAB 1: 每日报告 -->
        <section id="tab-reports" class="tab-content active">
            <div class="reports-layout">
                <aside class="reports-sidebar">
                    <div class="sidebar-title">📅 历史日报归档</div>
                    <div id="report-nav-list"></div>
                </aside>

                <article class="report-article">
                    <div class="report-toolbar">
                        <div class="report-meta-tag">
                            <span id="active-report-date-badge" class="brand-badge">2026-08-26</span>
                            <span id="active-report-title" style="font-weight: 700; color: white;">AIGC 竞品态势感知日报</span>
                        </div>
                        <div style="display: flex; gap: 8px;">
                            <button class="action-btn" onclick="copyReportMarkdown()">📋 复制原文</button>
                            <button class="action-btn" onclick="downloadReportMarkdown()">💾 下载 Markdown</button>
                        </div>
                    </div>

                    <div id="report-body-html"></div>
                </article>
            </div>
        </section>

        <!-- TAB 2: 竞品全景 -->
        <section id="tab-competitors" class="tab-content">
            <div class="filter-bar">
                <div class="search-box">
                    <span class="search-icon">🔍</span>
                    <input type="text" id="comp-search" class="search-input" placeholder="搜索竞品名称、功能标签、赛道或定位..." oninput="filterCompetitors()">
                </div>
                <div class="filter-pills">
                    <button class="filter-pill active" onclick="setRatingFilter('ALL', this)">全部 ({total_sites})</button>
                    <button class="filter-pill" onclick="setRatingFilter('S', this)">S 级 ({ratings_count.get("S", 0)})</button>
                    <button class="filter-pill" onclick="setRatingFilter('A', this)">A 级 ({ratings_count.get("A", 0)})</button>
                    <button class="filter-pill" onclick="setRatingFilter('B', this)">B 级 ({ratings_count.get("B", 0)})</button>
                </div>
            </div>

            <div id="competitors-container" class="competitors-grid"></div>
        </section>

        <!-- TAB 3: 截图证据 -->
        <section id="tab-gallery" class="tab-content">
            <div id="gallery-container" class="gallery-grid"></div>
        </section>
    </main>

    <!-- 模态弹窗 (Modal) -->
    <div id="profile-modal" class="modal-backdrop" onclick="closeModalOnBackdrop(event)">
        <div class="modal-card">
            <div class="modal-header">
                <h2 id="modal-title">竞品深度画像</h2>
                <button class="modal-close-btn" onclick="closeProfileModal()">✕</button>
            </div>
            <div id="modal-body" class="modal-content"></div>
        </div>
    </div>

    <!-- 灯箱 (Lightbox) -->
    <div id="lightbox" class="lightbox-backdrop" onclick="closeLightbox()">
        <button class="lightbox-close" onclick="closeLightbox()">✕</button>
        <img id="lightbox-img" class="lightbox-img" src="" alt="页面大图">
        <div id="lightbox-caption" class="lightbox-caption"></div>
    </div>

    <script>
        window.SITE_DATA = {json_data_safe};
        const rawData = window.SITE_DATA;
        let activeReportIndex = 0;
        let currentRatingFilter = 'ALL';
        let currentSearchQuery = '';

        function switchTab(tabId) {{
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
            
            const target = document.getElementById('tab-' + tabId);
            if (target) target.classList.add('active');

            const btns = document.querySelectorAll('.nav-btn');
            if (tabId === 'reports') btns[0].classList.add('active');
            else if (tabId === 'competitors') btns[1].classList.add('active');
            else if (tabId === 'gallery') btns[2].classList.add('active');

            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}

        function renderReports() {{
            const navList = document.getElementById('report-nav-list');
            navList.innerHTML = '';

            rawData.reports.forEach((rep, idx) => {{
                const item = document.createElement('div');
                item.className = 'report-nav-item' + (idx === activeReportIndex ? ' active' : '');
                item.innerHTML = `
                    <span>📄 ${{rep.date}}</span>
                    <span style="font-size: 0.72rem; opacity: 0.7;">${{idx === 0 ? '最新 🔥' : ''}}</span>
                `;
                item.onclick = () => selectReport(idx);
                navList.appendChild(item);
            }});

            showReportContent(activeReportIndex);
        }}

        function selectReport(idx) {{
            activeReportIndex = idx;
            document.querySelectorAll('.report-nav-item').forEach((el, i) => {{
                if (i === idx) el.classList.add('active');
                else el.classList.remove('active');
            }});
            showReportContent(idx);
        }}

        function showReportContent(idx) {{
            const rep = rawData.reports[idx];
            if (!rep) return;
            document.getElementById('active-report-date-badge').textContent = rep.date;
            document.getElementById('active-report-title').textContent = rep.title;
            document.getElementById('report-body-html').innerHTML = rep.html;
        }}

        function copyReportMarkdown() {{
            const rep = rawData.reports[activeReportIndex];
            if (!rep) return;
            navigator.clipboard.writeText(rep.markdown).then(() => {{
                alert('已复制该期日报 Markdown 到剪贴板！');
            }}).catch(() => {{
                alert('复制失败，请手动选择复制。');
            }});
        }}

        function downloadReportMarkdown() {{
            const rep = rawData.reports[activeReportIndex];
            if (!rep) return;
            const blob = new Blob([rep.markdown], {{ type: 'text/markdown;charset=utf-8;' }});
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = rep.id || `daily_report_${{rep.raw_date}}.md`;
            link.click();
        }}

        function renderCompetitors() {{
            const container = document.getElementById('competitors-container');
            container.innerHTML = '';

            const filtered = rawData.competitors.filter(c => {{
                const matchRating = (currentRatingFilter === 'ALL' || c.rating === currentRatingFilter);
                const q = currentSearchQuery.toLowerCase().trim();
                const matchSearch = !q || 
                    c.name.toLowerCase().includes(q) || 
                    c.category.toLowerCase().includes(q) || 
                    c.summary.toLowerCase().includes(q) ||
                    (c.features && c.features.some(f => f.toLowerCase().includes(q)));
                return matchRating && matchSearch;
            }});

            if (filtered.length === 0) {{
                container.innerHTML = `
                    <div style="grid-column: 1 / -1; text-align: center; padding: 4rem; color: var(--text-muted);">
                        <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🔍</div>
                        <div style="font-size: 1.1rem; font-weight: 600;">未找到符合条件的竞品</div>
                        <div style="font-size: 0.85rem; margin-top: 4px;">请尝试更换关键词或筛选条件</div>
                    </div>
                `;
                return;
            }}

            filtered.forEach(c => {{
                const card = document.createElement('div');
                card.className = 'comp-card';

                const ratingClass = c.rating === 'S' ? 'rating-s' : (c.rating === 'A' ? 'rating-a' : 'rating-b');
                const thumbSrc = c.screenshot ? `./screenshots/${{c.screenshot}}` : '';

                const featuresHtml = (c.features || []).map(f => `<span class="feature-tag">${{f}}</span>`).join('');
                
                let changeHtml = '';
                if (c.latest_update && c.latest_update.summary) {{
                    const shortChange = c.latest_update.summary.split('\\n')[0].replace(/#+/g, '').trim();
                    changeHtml = `
                        <div class="latest-change-box">
                            <span style="font-weight: 700;">📌 最新动态 (${{c.latest_update.time}}):</span>
                            <div>${{shortChange.substring(0, 75)}}...</div>
                        </div>
                    `;
                }}

                card.innerHTML = `
                    <div class="card-header-bar">
                        <div class="comp-title-group">
                            <h3>${{c.name}}</h3>
                            <div class="comp-category">${{c.category}}</div>
                        </div>
                        <span class="rating-badge ${{ratingClass}}">${{c.rating}} 级</span>
                    </div>

                    ${{thumbSrc ? `
                    <div class="card-preview-thumb" onclick="openLightbox('${{thumbSrc}}', '${{c.name}} - 最新页面存证')">
                        <img src="${{thumbSrc}}" alt="${{c.name}}" loading="lazy">
                        <div class="thumb-overlay">
                            <span>🔍 点击放大查看页面留存</span>
                        </div>
                    </div>
                    ` : ''}}

                    <div class="card-body">
                        <p class="comp-summary">${{c.summary || '暂无产品定位说明'}}</p>
                        <div class="comp-tags">${{featuresHtml}}</div>
                        ${{changeHtml}}
                    </div>

                    <div class="card-footer-actions">
                        <a href="${{c.url}}" target="_blank" rel="noopener noreferrer" class="card-btn" style="text-decoration: none;">访问站点 ↗</a>
                        <button class="card-btn card-btn-primary" onclick="openProfileModal('${{encodeURIComponent(c.name)}}')">查看深度画像</button>
                    </div>
                `;
                container.appendChild(card);
            }});
        }}

        function setRatingFilter(rating, btn) {{
            currentRatingFilter = rating;
            document.querySelectorAll('.filter-pill').forEach(el => el.classList.remove('active'));
            btn.classList.add('active');
            renderCompetitors();
        }}

        function filterCompetitors() {{
            currentSearchQuery = document.getElementById('comp-search').value;
            renderCompetitors();
        }}

        function openProfileModal(encodedName) {{
            const name = decodeURIComponent(encodedName);
            const comp = rawData.competitors.find(c => c.name === name);
            if (!comp) return;

            document.getElementById('modal-title').textContent = `${{comp.name}} · 深度基准画像与版本动态`;
            document.getElementById('modal-body').innerHTML = comp.profile_html || '<p>暂无基准画像数据</p>';
            document.getElementById('profile-modal').classList.add('active');
        }}

        function closeProfileModal() {{
            document.getElementById('profile-modal').classList.remove('active');
        }}

        function closeModalOnBackdrop(e) {{
            if (e.target.id === 'profile-modal') {{
                closeProfileModal();
            }}
        }}

        function renderGallery() {{
            const container = document.getElementById('gallery-container');
            container.innerHTML = '';

            rawData.competitors.forEach(c => {{
                if (!c.screenshot) return;
                const card = document.createElement('div');
                card.className = 'gallery-card';
                const imgSrc = `./screenshots/${{c.screenshot}}`;

                card.innerHTML = `
                    <div class="gallery-img-wrapper" onclick="openLightbox('${{imgSrc}}', '${{c.name}} · ${{c.url}}')">
                        <img src="${{imgSrc}}" alt="${{c.name}}" loading="lazy">
                        <div class="gallery-overlay">
                            <span class="zoom-tip">🔍 点击放大全屏查看</span>
                        </div>
                    </div>
                    <div class="gallery-caption">
                        <span class="gallery-title">${{c.name}}</span>
                        <span class="gallery-time">${{c.captured_at ? c.captured_at.substring(0, 10) : '近期'}}</span>
                    </div>
                `;
                container.appendChild(card);
            }});
        }}

        function openLightbox(src, caption) {{
            const lb = document.getElementById('lightbox');
            const img = document.getElementById('lightbox-img');
            const cap = document.getElementById('lightbox-caption');
            img.src = src;
            cap.textContent = caption || '';
            lb.classList.add('active');
        }}

        function closeLightbox() {{
            document.getElementById('lightbox').classList.remove('active');
        }}

        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') {{
                closeLightbox();
                closeProfileModal();
            }}
        }});

        renderReports();
        renderCompetitors();
        renderGallery();
    </script>
</body>
</html>
"""


def build():
    print("[*] 开始构建 AIGC 竞品看板静态站点...")
    data = load_all_data()
    print(f"[OK] 成功加载 {len(data['competitors'])} 个竞品档案，{len(data['reports'])} 期历史日报")

    copy_assets()

    html_content = generate_html(data)
    index_path = DIST_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[SUCCESS] 静态单页已成功生成: {index_path}")
    print(f"[INFO] 静态站点输出目录: {DIST_DIR}")
    print("[INFO] 可直接部署至 Cloudflare Pages，无需任何服务端和 API Key！")


if __name__ == "__main__":
    build()
