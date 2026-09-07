"""
UI 模块：网页截图存证画廊。
"""

import os
import html
import json
from pathlib import Path
import streamlit as st

from agent_utils import (
    DEMO_DATA_DIR,
    SCREENSHOT_DIR,
    SNAPSHOT_DIR,
    format_beijing_time,
    merged_artifact_files,
    site_key_candidates,
)
from ui.competitors import load_competitors_config


def get_snapshot_capture_times() -> dict[str, str]:
    """读取快照记录的真实抓取时间（优先使用真实的 captured_at 而非文件 mtime）"""
    times = {}
    snapshot_files = merged_artifact_files(SNAPSHOT_DIR, DEMO_DATA_DIR / "snapshots", "*_latest.json")
    for s_file in snapshot_files:
        try:
            with open(s_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                captured = data.get("captured_at")
                if captured:
                    fname = Path(s_file).name.replace("_latest.json", "")
                    times[fname] = format_beijing_time(captured)
                    url = data.get("url", "")
                    if url:
                        domain = url.replace("https://", "").replace("http://", "").split("/")[0]
                        times[domain] = format_beijing_time(captured)
        except Exception:
            pass
    return times


def render_gallery():
    st.markdown('<div class="hero-title">🖼️ 视觉存证与快照画廊</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">浏览最近一次网页渲染截图，对模型提取结果进行人工抽检</div>', unsafe_allow_html=True)

    capture_times = get_snapshot_capture_times()

    screenshots = sorted(
        path for path in merged_artifact_files(SCREENSHOT_DIR, DEMO_DATA_DIR / "screenshots", "*.png")
        if not os.path.basename(path).startswith("test_")
    )
    url_by_key = {
        key: item["url"]
        for item in load_competitors_config()
        for key in site_key_candidates(item["url"])
    }

    if not screenshots:
        st.info("💡 暂无本地截图存证，请先前往【监控大盘】运行一次全量监控。")
        return

    st.caption(f"当前可查看 **{len(screenshots)}** 张最近一次网页快照：")

    # 3 列响应式画廊
    cols = st.columns(3)

    for idx, s_path in enumerate(screenshots):
        filename = os.path.basename(s_path)
        domain = filename.replace("_latest.png", "").replace(".png", "")
        safe_domain = html.escape(domain)
        file_size_kb = os.path.getsize(s_path) / 1024
        
        # 优先从快照元数据获取真实抓取时间，回退时使用文件时间并强制格式化为北京时间
        mod_time = capture_times.get(domain) or format_beijing_time(os.path.getmtime(s_path))

        with cols[idx % 3]:
            st.markdown(f"""
<div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 0.8rem; margin-bottom: 1.2rem; box-shadow: 0 2px 8px rgba(0,0,0,0.03);">
    <div style="font-weight: 700; color: #0F172A; font-size: 0.95rem; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center;">
        <span>🌐 {safe_domain}</span>
        <span style="font-size: 0.75rem; background: #EEF2FF; color: #4F46E5; padding: 2px 8px; border-radius: 4px; font-weight: 600;">{file_size_kb:.0f} KB</span>
    </div>
    <div style="font-size: 0.78rem; color: #64748B; margin-bottom: 8px;">🕒 捕获时间：{mod_time}</div>
</div>
""", unsafe_allow_html=True)
            st.image(s_path, use_container_width=True)
            
            target_url = html.escape(url_by_key.get(domain, f"https://{domain}"), quote=True)
            st.markdown(f'<div style="text-align: right; margin-bottom: 1.5rem;"><a href="{target_url}" target="_blank" style="font-size: 0.82rem; color: #2563EB; font-weight: 600; text-decoration: none;">访问官网 ↗</a></div>', unsafe_allow_html=True)
