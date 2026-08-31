@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist runtime\reports mkdir runtime\reports
set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
echo ======================================================== >> runtime\reports\scheduler.log
echo [%date% %time%] Start daily competitor intelligence run >> runtime\reports\scheduler.log
"%PYTHON_EXE%" step3_agent.py >> runtime\reports\scheduler.log 2>&1
set "AGENT_EXIT=%ERRORLEVEL%"
echo [%date% %time%] Daily run finished with exit code %AGENT_EXIT% >> runtime\reports\scheduler.log
exit /b %AGENT_EXIT%
