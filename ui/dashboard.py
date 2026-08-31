"""
UI 模块：概览、运行进度与最近日志。
"""

import os
import json
import subprocess
import time
import html
import sys
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv

from agent_utils import (
    DEMO_DATA_DIR,
    DEMO_REPORT_DIR,
    LOG_DIR,
    PROJECT_ROOT,
    REPORT_DIR,
    SCREENSHOT_DIR,
    SNAPSHOT_DIR,
    atomic_write_text,
    ensure_runtime_layout,
    merged_artifact_files,
)

load_dotenv(PROJECT_ROOT / ".env")
ensure_runtime_layout()
LAST_RUN_LOG_PATH = LOG_DIR / "last_run.log"


def get_system_stats():
    """获取系统基础指标数据（基于当前配置清单与快照）"""
    from ui.competitors import load_competitors_config
    config_items = load_competitors_config()
    enabled_count = len([it for it in config_items if it.get("enabled", True)])
    total_configured = len(config_items)

    screenshots = [
        path for path in merged_artifact_files(SCREENSHOT_DIR, DEMO_DATA_DIR / "screenshots", "*.png")
        if not os.path.basename(path).startswith("test_")
    ]
    reports = merged_artifact_files(REPORT_DIR, DEMO_REPORT_DIR, "daily_report_*.md")
    snapshots = merged_artifact_files(SNAPSHOT_DIR, DEMO_DATA_DIR / "snapshots", "*_latest.json")
    
    ratings = {"S": 0, "A": 0, "B": 0, "C": 0, "其他": 0}
    for s_path in snapshots:
        try:
            with open(s_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                prof = data.get("profile", "")
                if "S级" in prof or "S 级" in prof or "评级：S" in prof or "评级: S" in prof:
                    ratings["S"] += 1
                elif "A级" in prof or "A 级" in prof or "评级：A" in prof or "评级: A" in prof:
                    ratings["A"] += 1
                elif "B级" in prof or "B 级" in prof or "评级：B" in prof or "评级: B" in prof:
                    ratings["B"] += 1
                elif "C级" in prof or "C 级" in prof or "评级：C" in prof or "评级: C" in prof:
                    ratings["C"] += 1
                else:
                    ratings["其他"] += 1
        except Exception:
            pass

    return {
        "competitor_count": total_configured,
        "enabled_count": enabled_count,
        "screenshot_count": len(screenshots),
        "report_count": len(reports),
        "ratings": ratings,
        "latest_report": max(reports, key=os.path.getmtime) if reports else None
    }


def render_dashboard():
    st.markdown('<div class="hero-title">⚡ AIGC 竞品情报工作台</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">集中查看竞品档案、截图证据与历史日报，并按需启动新一轮监控</div>', unsafe_allow_html=True)
    
    stats = get_system_stats()

    # 1. KPI 指标卡
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        st.markdown(f"""
<div class="kpi-card">
    <div class="kpi-title">🎯 监控对象</div>
    <div class="kpi-value">{stats['competitor_count']} <span style="font-size: 1rem; font-weight: 500; color: #64748B;">个站点</span></div>
    <div class="kpi-sub">● 已启用 {stats['enabled_count']}/{stats['competitor_count']}</div>
</div>
""", unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
<div class="kpi-card">
    <div class="kpi-title">📸 截图证据</div>
    <div class="kpi-value">{stats['screenshot_count']} <span style="font-size: 1rem; font-weight: 500; color: #64748B;">张</span></div>
    <div class="kpi-sub">● 可供人工抽检</div>
</div>
""", unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
<div class="kpi-card">
    <div class="kpi-title">📑 日报归档</div>
    <div class="kpi-value">{stats['report_count']} <span style="font-size: 1rem; font-weight: 500; color: #64748B;">份</span></div>
    <div class="kpi-sub">● 可搜索与下载</div>
</div>
""", unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
<div class="kpi-card">
    <div class="kpi-title">⭐ 已建档标杆 (S/A)</div>
    <div class="kpi-value">{stats['ratings']['S'] + stats['ratings']['A']} <span style="font-size: 1rem; font-weight: 500; color: #64748B;">个</span></div>
    <div class="kpi-sub" style="color: #F59E0B;">S级: {stats['ratings']['S']} ｜ A级: {stats['ratings']['A']}</div>
</div>
""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 2. 控制台与执行区域
    col_ctrl, col_sched = st.columns([2, 1])

    if "is_running" not in st.session_state:
        st.session_state["is_running"] = False

    has_api_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY"))

    with col_ctrl:
        st.markdown("""
<div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 14px; padding: 1.2rem; box-shadow: 0 2px 10px rgba(0,0,0,0.02);">
    <div style="font-size: 1.1rem; font-weight: 700; color: #0F172A; margin-bottom: 0.3rem;">🚀 启动一轮竞品监控</div>
    <div style="font-size: 0.85rem; color: #64748B; margin-bottom: 0.8rem;">按启用清单抓取网页、保存截图，随后生成基准画像或版本变化，并汇总为待人工复核的日报</div>
</div>
""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        is_running = st.session_state.get("is_running", False)
        btn_label = "⏳ 监控执行中…" if is_running else "⚡ 开始新一轮监控"

        if not has_api_key:
            st.warning("当前为演示查看模式。请先在“设置”中配置模型 API Key，再启动新一轮监控。")
        
        run_btn = st.button(
            btn_label,
            type="primary",
            use_container_width=True,
            disabled=is_running or not has_api_key
        )

        # 进度与日志展示容器（常驻）
        progress_placeholder = st.empty()
        log_placeholder = st.empty()

        if run_btn:
            st.session_state["is_running"] = True
            progress_bar = progress_placeholder.progress(0.05, text="🔄 [阶段 1/3] 正在并发抓取网页与高清存证截图中...")
            
            log_text = ""
            start_time = time.time()

            try:
                process = subprocess.Popen(
                    [sys.executable, str(PROJECT_ROOT / "step3_agent.py")],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(PROJECT_ROOT)
                )

                current_progress = 0.05
                current_stage_text = "🔄 [阶段 1/3] 正在并发抓取网页并生成高清渲染截图..."

                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    log_text += line
                    lines = log_text.splitlines()
                    display_lines = lines[-16:] if len(lines) > 16 else lines
                    
                    safe_lines = [html.escape(line) for line in display_lines]
                    log_placeholder.markdown('<div class="terminal-box">📟 实时执行日志流：<br>' + "<br>".join([f"&gt; {line}" for line in safe_lines]) + '</div>', unsafe_allow_html=True)

                    if "[节点1]" in line:
                        current_progress = 0.10
                        current_stage_text = "🔄 [阶段 1/3] 正在并发抓取竞品网页并生成高清渲染截图..."
                    elif "[成功]" in line:
                        current_progress = min(0.38, current_progress + 0.02)
                        current_stage_text = "🌐 [阶段 1/3] 抓取并截图成功，正在处理下一个站点..."
                    elif "抓取完成" in line:
                        current_progress = 0.40
                        current_stage_text = "✅ [阶段 1/3 完成] 网页抓取与截图全部就绪，正在准备大模型并发解析..."
                    elif "[节点2]" in line:
                        current_progress = 0.45
                        current_stage_text = "🤖 [阶段 2/3] 正在生成基准画像或执行增量对比..."
                    elif "[完成比对]" in line or "[完成建档]" in line:
                        current_progress = min(0.78, current_progress + 0.02)
                    elif "[节点3]" in line:
                        current_progress = 0.82
                        current_stage_text = "📊 [阶段 3/3] 正在汇总提炼宏观行业洞察并全量拼装综合日报..."
                    elif "日报生成完成" in line:
                        current_progress = 1.0
                        current_stage_text = "🎉 全流程监控与日报生成顺利完成！"

                    progress_bar.progress(current_progress, text=current_stage_text)

                process.stdout.close()
                return_code = process.wait()
                elapsed = int(time.time() - start_time)

                # 持久化保存执行日志与状态
                atomic_write_text(LAST_RUN_LOG_PATH, log_text)

                st.session_state["last_run_info"] = {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "elapsed": elapsed,
                    "success": (return_code == 0)
                }

                if return_code == 0:
                    progress_bar.progress(1.0, text=f"✅ 全流程监控执行完毕！总耗时：{elapsed} 秒")
                    st.success(f"🎉 监控执行成功！耗时 {elapsed}s，最新日报已同步生成。")
                    st.balloons()
                else:
                    st.error(f"❌ 运行异常，退出码：{return_code}")

            except Exception as e:
                st.error(f"❌ 启动失败：{e}")
            finally:
                st.session_state["is_running"] = False
                time.sleep(1.5)
                st.rerun()

        # 3. 常驻显示最近一次执行日志记录
        if not run_btn and os.path.exists(LAST_RUN_LOG_PATH):
            with open(LAST_RUN_LOG_PATH, "r", encoding="utf-8", errors="replace") as lf:
                saved_logs = lf.read()
            
            if saved_logs.strip():
                run_info = st.session_state.get("last_run_info", {})
                time_label = run_info.get("time", "近期")
                elapsed_label = f" ｜ 耗时：{run_info['elapsed']}s" if "elapsed" in run_info else ""
                
                with st.expander(f"📟 最近一次 Agent 执行日志（{time_label}{elapsed_label}）", expanded=False):
                    safe_lines = [html.escape(line) for line in saved_logs.splitlines()]
                    st.markdown('<div class="terminal-box" style="max-height: 300px; overflow-y: auto;">' + "<br>".join([f"&gt; {line}" for line in safe_lines]) + '</div>', unsafe_allow_html=True)

    with col_sched:
        st.markdown("""
<div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 14px; padding: 1.2rem; box-shadow: 0 2px 10px rgba(0,0,0,0.02);">
    <div style="font-size: 1.1rem; font-weight: 700; color: #0F172A; margin-bottom: 0.3rem;">⏰ 定时运行</div>
    <div style="font-size: 0.85rem; color: #64748B; margin-bottom: 0.8rem;">仓库提供 Windows 任务计划安装脚本</div>
    <div style="background: #F8FAFC; border-radius: 8px; padding: 0.8rem; border: 1px solid #E2E8F0; font-size: 0.82rem; color: #334155; line-height: 1.8;">
        <div>🗓️ <b>默认周期</b>：每天 09:00</div>
        <div>🔎 <b>当前状态</b>：请在系统任务计划中核验</div>
        <div>🔔 <b>结果分发</b>：Webhook 配置后可推送</div>
    </div>
</div>
""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 刷新全盘数据", use_container_width=True, disabled=st.session_state.get("is_running", False)):
            st.rerun()

    # 4. 最新日报预览卡
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 📑 今日最新情报日报概览")
    
    if stats["latest_report"] and os.path.exists(stats["latest_report"]):
        with open(stats["latest_report"], "r", encoding="utf-8") as f:
            latest_content = f.read()
        
        st.caption(f"📁 当前呈现版本：`{os.path.basename(stats['latest_report'])}` ｜ 生成时间：{datetime.fromtimestamp(os.path.getmtime(stats['latest_report'])).strftime('%Y-%m-%d %H:%M')}")
        with st.expander("🔍 展开阅读完整日报", expanded=False):
            st.markdown(latest_content)
    else:
        st.info("💡 尚未生成日报，请点击上方按钮立即执行首次监控！")
