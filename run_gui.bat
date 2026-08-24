@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================================
echo Starting AIGC competitor intelligence console...
echo ========================================================
python -m streamlit run app.py
pause
