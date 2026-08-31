@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
echo ========================================================
echo Starting AIGC competitor intelligence console...
echo ========================================================
"%PYTHON_EXE%" -m streamlit run app.py
pause
