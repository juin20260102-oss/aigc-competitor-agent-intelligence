"""
AIGC 竞品监控 Agent 可视化控制台 (现代化高颜值 SaaS 旗舰版)
"""

import streamlit as st

# 页面基础配置
st.set_page_config(
    page_title="AIGC 竞品情报智能看板 · Intelligence Hub",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入高颜值现代化 SaaS 样式 CSS (卡片阴影、渐变徽章、精致排版、毛玻璃质感)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    
    /* 页面背景底色与微光质感 */
    .stApp {
        background-color: #F8FAFC;
    }
    
    /* 侧边栏现代化暗黑磨砂质感 */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }
    section[data-testid="stSidebar"] * {
        color: #E2E8F0 !important;
    }
    div[data-testid="stSidebarNav"] {
        display: none;
    }
    
    /* 侧边栏单选导航定制 */
    div[data-testid="stRadio"] > div {
        gap: 0.4rem;
    }
    div[data-testid="stRadio"] label {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 10px;
        padding: 0.6rem 0.9rem !important;
        transition: all 0.2s ease-in-out;
        cursor: pointer;
    }
    div[data-testid="stRadio"] label:hover {
        background: rgba(59, 130, 246, 0.15) !important;
        border-color: rgba(59, 130, 246, 0.4) !important;
        transform: translateX(4px);
    }
    
    /* 标题与主色调渐变 */
    .hero-title {
        font-size: 2.1rem;
        font-weight: 800;
        background: linear-gradient(135deg, #1E293B 0%, #3B82F6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.02em;
        margin-bottom: 0.3rem;
    }
    .hero-subtitle {
        color: #64748B;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }

    /* 指标卡片 (KPI Cards) */
    .kpi-card {
        background: #FFFFFF;
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.03);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        position: relative;
        overflow: hidden;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 30px -4px rgba(0, 0, 0, 0.08);
    }
    .kpi-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, #3B82F6, #8B5CF6);
    }
    .kpi-title {
        color: #64748B;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.4rem;
    }
    .kpi-value {
        color: #0F172A;
        font-size: 1.9rem;
        font-weight: 800;
        letter-spacing: -0.03em;
    }
    .kpi-sub {
        color: #10B981;
        font-size: 0.82rem;
        font-weight: 600;
        margin-top: 0.3rem;
    }

    /* 评级徽章 (Badges) */
    .badge-s {
        background: linear-gradient(135deg, #FF4B4B, #FF8F00);
        color: white !important;
        padding: 0.25rem 0.6rem;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 700;
        display: inline-block;
    }
    .badge-a {
        background: linear-gradient(135deg, #3B82F6, #2DD4BF);
        color: white !important;
        padding: 0.25rem 0.6rem;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 700;
        display: inline-block;
    }
    .badge-b {
        background: #E2E8F0;
        color: #334155 !important;
        padding: 0.25rem 0.6rem;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 600;
        display: inline-block;
    }

    /* 控制台黑曜石终端样式 */
    .terminal-box {
        background-color: #0B0F19;
        border: 1px solid #1E293B;
        border-radius: 12px;
        padding: 1rem;
        color: #38BDF8;
        font-family: 'Fira Code', Consolas, monospace;
        font-size: 0.85rem;
        line-height: 1.6;
    }

    /* 按钮定制 (Primary Glow) */
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2563EB 0%, #4F46E5 100%) !important;
        border: none !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        padding: 0.65rem 1.4rem !important;
        box-shadow: 0 4px 14px 0 rgba(37, 99, 235, 0.35) !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button[kind="primary"]:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 20px 0 rgba(37, 99, 235, 0.5) !important;
    }

    /* 状态指示点 */
    .status-dot-active {
        height: 9px;
        width: 9px;
        background-color: #10B981;
        border-radius: 50%;
        display: inline-block;
        box-shadow: 0 0 8px #10B981;
        margin-right: 6px;
    }
</style>
""", unsafe_allow_html=True)

# 导入各页面模块
from ui.dashboard import render_dashboard
from ui.reports import render_reports
from ui.competitors import render_competitors
from ui.gallery import render_gallery
from ui.settings import render_settings

# 侧边栏品牌与导航
with st.sidebar:
    st.markdown("""
<div style="padding: 0.5rem 0 1rem 0;">
    <div style="font-size: 1.25rem; font-weight: 800; color: #FFFFFF; display: flex; align-items: center; gap: 8px;">
        <span>⚡</span> AIGC 竞品情报舱
    </div>
    <div style="font-size: 0.78rem; color: #94A3B8; margin-top: 4px;">
        <span class="status-dot-active"></span> Agent 实时态势感知就绪
    </div>
</div>
""", unsafe_allow_html=True)

    st.markdown("---")

    menu_option = st.radio(
        "导航菜单",
        [
            "🏠 监控大盘与控制",
            "📑 每日情报中心",
            "🌐 竞品深度档案",
            "🖼️ 视觉存证画廊",
            "⚙️ 全局系统与安全"
        ],
        index=0
    )

    st.markdown("---")
    
    st.markdown("""
<div style="background: rgba(255,255,255,0.04); border-radius: 10px; padding: 0.8rem; border: 1px solid rgba(255,255,255,0.06); font-size: 0.8rem;">
    <div style="color: #60A5FA; font-weight: 600; margin-bottom: 4px;">🔒 核心特性</div>
    <div style="color: #94A3B8; line-height: 1.6;">
        • 16 站点全并发异步解析<br>
        • 双轨画像 + 历史档案持久化<br>
        • 全文证据归因 & 本地截图<br>
        • API Key 严格密保脱敏
    </div>
</div>
""", unsafe_allow_html=True)
    
    st.caption("引擎版本：v2.5 · Powered by LangGraph")

# 页面路由分发
if menu_option == "🏠 监控大盘与控制":
    render_dashboard()
elif menu_option == "📑 每日情报中心":
    render_reports()
elif menu_option == "🌐 竞品深度档案":
    render_competitors()
elif menu_option == "🖼️ 视觉存证画廊":
    render_gallery()
elif menu_option == "⚙️ 全局系统与安全":
    render_settings()
