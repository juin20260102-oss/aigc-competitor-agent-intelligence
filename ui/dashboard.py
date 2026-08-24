"""
UI 模块：监控大盘与控制中心 (Dashboard - SaaS 旗舰交互版，支持防重提交、多阶段动态进度条与常驻日志)
"""

import os
import glob
import json
import subprocess
import time
import streamlit as st
from datetime import datetime

DATA_DIR = "data"
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")
REPORT_DIR = "reports"
LOG_DIR = os.path.join(DATA_DIR, "logs")
LAST_RUN_LOG_PATH = os.path.join(LOG_DIR, "last_run.log")

os.makedirs(LOG_DIR, exist_ok=True)


def get_system_stats():
    """获取系统基础指标数据（基于当前配置清单与快照）"""
    from ui.competitors import load_competitors_config
    config_items = load_competitors_config()
    enabled_count = len([it for it in config_items if it.get("enabled", True)])
    total_configured = len(config_items)

    screenshots = glob.glob(os.path.join(SCREENSHOT_DIR, "*.png"))
    reports = glob.glob(os.path.join(REPORT_DIR, "daily_report_*.md"))
    snapshots = glob.glob(os.path.join(SNAPSHOT_DIR, "*_latest.json"))
    
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
        "latest_report": sorted(reports)[-1] if reports else None
    }


def render_dashboard():
    st.markdown('<div class="hero-title">⚡ AIGC 竞品态势大盘与控制中心</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">全网 16+ 核心竞品实时感知、基准商业画像档案与自动化调度大盘</div>', unsafe_allow_html=True)
    
    stats = get_system_stats()

    # 1. 现代化 KPI 指标卡
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        st.markdown(f"""
<div class="kpi-card">
    <div class="kpi-title">🎯 监控竞品档案库</div>
    <div class="kpi-value">{stats['competitor_count']} <span style="font-size: 1rem; font-weight: 500; color: #64748B;">个站点</span></div>
    <div class="kpi-sub">● {stats['enabled_count']}/{stats['competitor_count']} 个处于启用监控中</div>
</div>
""", unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
<div class="kpi-card">
    <div class="kpi-title">📸 视觉存证截图</div>
    <div class="kpi-value">{stats['screenshot_count']} <span style="font-size: 1rem; font-weight: 500; color: #64748B;">张高清图</span></div>
    <div class="kpi-sub">● 无头浏览器真实渲染</div>
</div>
""", unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
<div class="kpi-card">
    <div class="kpi-title">📑 综合情报日报</div>
    <div class="kpi-value">{stats['report_count']} <span style="font-size: 1rem; font-weight: 500; color: #64748B;">份归档</span></div>
    <div class="kpi-sub">● 双轨画像 + 增量溯源</div>
</div>
""", unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
<div class="kpi-card">
    <div class="kpi-title">⭐ 核心标杆竞品 (S/A)</div>
    <div class="kpi-value">{stats['ratings']['S'] + stats['ratings']['A']} <span style="font-size: 1rem; font-weight: 500; color: #64748B;">个</span></div>
    <div class="kpi-sub" style="color: #F59E0B;">S级: {stats['ratings']['S']} ｜ A级: {stats['ratings']['A']}</div>
</div>
""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 2. 控制台与执行区域
    col_ctrl, col_sched = st.columns([2, 1])

    if "is_running" not in st.session_state:
        st.session_state["is_running"] = False

    with col_ctrl:
        st.markdown("""
<div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 14px; padding: 1.2rem; box-shadow: 0 2px 10px rgba(0,0,0,0.02);">
    <div style="font-size: 1.1rem; font-weight: 700; color: #0F172A; margin-bottom: 0.3rem;">🚀 Agent 全流程监控调度器</div>
    <div style="font-size: 0.85rem; color: #64748B; margin-bottom: 0.8rem;">一键并发抓取所有生效竞品、截取高清图、调用大模型生成双轨全景画像并拼装完整日报</div>
</div>
""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        is_running = st.session_state.get("is_running", False)
        btn_label = "⏳ 全量竞品监控执行中（已锁定防止重复提交）..." if is_running else "⚡ 立即开始全量竞品监控与深度分析"
        
        run_btn = st.button(
            btn_label,
            type="primary",
            use_container_width=True,
            disabled=is_running
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
                    ["python", "step3_agent.py"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=os.getcwd()
                )

                current_progress = 0.05
                current_stage_text = "🔄 [阶段 1/3] 正在并发抓取网页并生成高清渲染截图..."

                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    log_text += line
                    lines = log_text.splitlines()
                    display_lines = lines[-16:] if len(lines) > 16 else lines
                    
                    log_placeholder.markdown(f'<div class="terminal-box">📟 实时执行日志流：<br>' + "<br>".join([f"&gt; {l}" for l in display_lines]) + '</div>', unsafe_allow_html=True)

                    if "[节点1]" in line:
                        current_progress = 0.10
                        current_stage_text = "🔄 [阶段 1/3] 正在并发抓取竞品网页并生成高清渲染截图..."
                    elif "[成功]" in line:
                        current_progress = min(0.38, current_progress + 0.02)
                        current_stage_text = f"🌐 [阶段 1/3] 抓取并截图成功，正在处理下一个站点..."
                    elif "抓取完成" in line:
                        current_progress = 0.40
                        current_stage_text = "✅ [阶段 1/3 完成] 网页抓取与截图全部就绪，正在准备大模型并发解析..."
                    elif "[节点2]" in line:
                        current_progress = 0.45
                        current_stage_text = "🤖 [阶段 2/3] 16 站点全量并发调用大模型双轨画像与增量对比中..."
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
                with open(LAST_RUN_LOG_PATH, "w", encoding="utf-8") as lf:
                    lf.write(log_text)

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
                    st.markdown(f'<div class="terminal-box" style="max-height: 300px; overflow-y: auto;">' + "<br>".join([f"&gt; {l}" for l in saved_logs.splitlines()]) + '</div>', unsafe_allow_html=True)

    with col_sched:
        st.markdown("""
<div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 14px; padding: 1.2rem; box-shadow: 0 2px 10px rgba(0,0,0,0.02);">
    <div style="font-size: 1.1rem; font-weight: 700; color: #0F172A; margin-bottom: 0.3rem;">⏰ 自动化计划状态</div>
    <div style="font-size: 0.85rem; color: #64748B; margin-bottom: 0.8rem;">Windows 原生任务计划程序</div>
    <div style="background: #F8FAFC; border-radius: 8px; padding: 0.8rem; border: 1px solid #E2E8F0; font-size: 0.82rem; color: #334155; line-height: 1.8;">
        <div>🗓️ <b>执行周期</b>：每天早上 09:00</div>
        <div>🤖 <b>自动化</b>：自动抓取 + 增量分析</div>
        <div>🔔 <b>微信推送</b>：实质性变化自动发群</div>
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
        with st.expander("🔍 展开阅读完整双轨日报", expanded=True):
            st.markdown(latest_content)
    else:
        st.info("💡 尚未生成日报，请点击上方按钮立即执行首次监控！")