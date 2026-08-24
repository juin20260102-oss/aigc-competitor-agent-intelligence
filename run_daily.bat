@echo off
chcp 65001 >nul
cd /d "D:\Anti\Agent_Daily_Report"
echo ======================================================== >> reports\scheduler.log
echo [%date% %time%] 开始执行每日竞品监控任务 >> reports\scheduler.log
python step3_agent.py >> reports\scheduler.log 2>&1
echo [%date% %time%] 每日竞品监控任务执行完毕 >> reports\scheduler.log
