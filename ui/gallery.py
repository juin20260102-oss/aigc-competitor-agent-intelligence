"""
UI 模块：视觉存证截图画廊 (Screenshot Gallery - SaaS 旗舰版)
"""

import os
import glob
import streamlit as st
from datetime import datetime

DATA_DIR = "data"
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")


def render_gallery():
    st.markdown('<div class="hero-title">🖼️ 视觉存证与快照画廊</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">全景高清网格化浏览 16+ 竞品最新网页渲染实况，赋能视觉审计与防幻觉抽检</div>', unsafe_allow_html=True)

    screenshots = sorted(glob.glob(os.path.join(SCREENSHOT_DIR, "*.png")))

    if not screenshots:
        st.info("💡 暂无本地截图存证，请先前往【监控大盘】运行一次全量监控。")
        return

    st.caption(f"当前归档共 **{len(screenshots)}** 张真实渲染网页快照：")

    # 3 列响应式画廊
    cols = st.columns(3)

    for idx, s_path in enumerate(screenshots):
        filename = os.path.basename(s_path)
        domain = filename.replace("_latest.png", "").replace(".png", "")
        file_size_kb = os.path.getsize(s_path) / 1024
        mod_time = datetime.fromtimestamp(os.path.getmtime(s_path)).strftime("%Y-%m-%d %H:%M")

        with cols[idx % 3]:
            st.markdown(f"""
<div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 0.8rem; margin-bottom: 1.2rem; box-shadow: 0 2px 8px rgba(0,0,0,0.03);">
    <div style="font-weight: 700; color: #0F172A; font-size: 0.95rem; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center;">
        <span>🌐 {domain}</span>
        <span style="font-size: 0.75rem; background: #EEF2FF; color: #4F46E5; padding: 2px 8px; border-radius: 4px; font-weight: 600;">{file_size_kb:.0f} KB</span>
    </div>
    <div style="font-size: 0.78rem; color: #64748B; margin-bottom: 8px;">🕒 捕获时间：{mod_time}</div>
</div>
""", unsafe_allow_html=True)
            st.image(s_path, use_container_width=True)
            
            target_url = f"https://{domain.replace('_', '/')}"
            st.markdown(f'<div style="text-align: right; margin-bottom: 1.5rem;"><a href="{target_url}" target="_blank" style="font-size: 0.82rem; color: #2563EB; font-weight: 600; text-decoration: none;">访问官网 ↗</a></div>', unsafe_allow_html=True)
