@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist reports mkdir reports
echo ======================================================== >> reports\scheduler.log
echo [%date% %time%] Start daily competitor intelligence run >> reports\scheduler.log
python step3_agent.py >> reports\scheduler.log 2>&1
echo [%date% %time%] Daily competitor intelligence run finished >> reports\scheduler.log
