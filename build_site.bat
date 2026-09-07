@echo off
chcp 65001 >nul
title AIGC 竞品态势感知看板 - 静态站点构建器

echo ========================================================
echo   AIGC 竞品态势感知看板 - 静态站点生成 (Static Site)
echo ========================================================
echo.

if exist .venv\Scripts\python.exe (
    set PYTHON_CMD=.venv\Scripts\python.exe
) else (
    set PYTHON_CMD=python
)

echo [*] 正在读取竞品快照、截图与历史日报并编译静态看板...
%PYTHON_CMD% tools\build_static_site.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] 构建失败，请检查 Python 环境与依赖。
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================================
echo   构建成功！生成文件位于 dist 目录：
echo   - dist\index.html （独立纯静态看板）
echo   - dist\screenshots\ （全量页面存证截图）
echo ========================================================
echo.

set /p PREVIEW="是否在默认浏览器中直接打开预览？(Y/n): "
if /i "%PREVIEW%"=="n" goto :EOF

start "" "dist\index.html"
