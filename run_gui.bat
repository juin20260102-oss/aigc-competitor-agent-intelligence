@echo off
chcp 65001 >nul
cd /d "D:\Anti\Agent_Daily_Report"
echo ========================================================
echo ?? 正在启动 AIGC 竞品监控 Agent 可视化控制台...
echo ========================================================
python -m streamlit run app.py
pause
