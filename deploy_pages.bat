@echo off
chcp 65001 >nul
title 部署到 Cloudflare Pages

echo ========================================================
echo   一键部署 AIGC 竞品态势感知看板到 Cloudflare Pages
echo ========================================================
echo.

if not exist dist\index.html (
    echo [*] 尚未生成静态文件，正在自动触发构建...
    call build_site.bat
)

echo.
echo 请选择部署方式：
echo   [1] 使用 Cloudflare Wrangler CLI 自动上传部署 (需已安装 Node.js)
echo   [2] 查看网页版拖拽 / GitHub 关联部署指南
echo.
set /p CHOICE="请输入选项 (1 或 2，默认为 1): "

if "%CHOICE%"=="2" goto :GUIDE

echo.
echo [*] 正在调用 Wrangler 部署 dist 目录到 Cloudflare Pages...
call npx -y wrangler pages deploy dist --project-name aigc-intel-hub --branch=main
if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] 部署成功！您已获得专属的 pages.dev 公网链接！
) else (
    echo.
    echo [提示] 命令行部署未完成，您可以采用方式 2 手动拖拽上传。
    goto :GUIDE
)
pause
exit /b 0

:GUIDE
echo.
echo ========================================================
echo   Cloudflare Pages 网页端 1 分钟免命令行部署指南：
echo ========================================================
echo   1. 登录 Cloudflare 控制台: https://dash.cloudflare.com/
echo   2. 点击左侧菜单 "Workers & Pages" -^> "Create" -^> "Pages"
echo   3. 选择 "Upload assets" (直接上传静态资产)
echo   4. 项目名称填入: aigc-intel-hub (可自定义)
echo   5. 将本项目的 "dist" 文件夹整体拖拽上传
echo   6. 点击 "Deploy site"，瞬间生成专属的 https://xxx.pages.dev 域名！
echo ========================================================
echo.
pause
