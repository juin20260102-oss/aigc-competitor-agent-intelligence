"""
UI 模块：历史日报查看与分发。
"""

import os
import glob
import httpx
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

REPORT_DIR = "reports"


def send_to_wecom(content: str, webhook: str) -> tuple[bool, str]:
    """发送 Markdown 报告到企业微信"""
    if not webhook:
        return False, "未配置企业微信 Webhook"
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"### 🚀 AIGC 竞品监控日报（{date_str}）\n\n" + content[:4000]
        }
    }
    try:
        resp = httpx.post(webhook, json=payload, timeout=10.0)
        res = resp.json()
        if res.get("errcode") == 0:
            return True, "推送成功"
        return False, res.get("errmsg", "推送失败")
    except Exception as e:
        return False, str(e)


def render_reports():
    st.markdown('<div class="hero-title">📑 每日竞品情报中心</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">查看历史日报、搜索关键词、下载 Markdown，并对模型结论进行人工复核</div>', unsafe_allow_html=True)

    report_files = sorted(glob.glob(os.path.join(REPORT_DIR, "daily_report_*.md")), reverse=True)

    if not report_files:
        st.info("💡 报告目录下暂无生成的日报，请先前往【监控大盘】启动一次全量监控。")
        return

    # 日报选择栏
    col_sel, col_act1, col_act2 = st.columns([3, 1, 1])
    
    with col_sel:
        selected_file = st.selectbox(
            "📅 选择历史归档日报：",
            options=report_files,
            format_func=lambda x: f"📑 {os.path.basename(x)} （生成于 {datetime.fromtimestamp(os.path.getmtime(x)).strftime('%Y-%m-%d %H:%M')}）"
        )

    if selected_file and os.path.exists(selected_file):
        with open(selected_file, "r", encoding="utf-8") as f:
            report_text = f.read()

        filename = os.path.basename(selected_file)

        with col_act1:
            st.write("")
            st.write("")
            st.download_button(
                label="📥 下载 Markdown",
                data=report_text,
                file_name=filename,
                mime="text/markdown",
                use_container_width=True
            )

        with col_act2:
            st.write("")
            st.write("")
            webhook = os.getenv("WECOM_WEBHOOK", "")
            if st.button("🔔 推送到企业微信", use_container_width=True, help="将当前报告推送到企业微信机器人"):
                if not webhook:
                    st.warning("⚠️ 请先前往【全局系统与安全】配置 Webhook 地址")
                else:
                    success, msg = send_to_wecom(report_text, webhook)
                    if success:
                        st.success("✅ 报告已成功推送到企业微信群！")
                    else:
                        st.error(f"❌ 推送失败：{msg}")

        st.markdown("---")

        # 关键词全文高亮搜索
        search_kw = st.text_input("🔍 全文高亮搜索（如：Gaoding, 可灵, 模特试衣, 补贴, 定价）...", "")

        if search_kw:
            highlighted = report_text.replace(search_kw, f"**:orange[{search_kw}]**")
            st.markdown(highlighted)
        else:
            st.markdown(report_text)
