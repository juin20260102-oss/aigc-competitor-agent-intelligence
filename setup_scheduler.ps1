# Windows 任务计划程序一键注册脚本
# 默认设置：每天早上 09:00 自动执行竞品监控并生成/推送日报
$TaskName = "AIGC_Competitor_Daily_Report"
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$PSScriptRoot\run_daily.bat`"" -WorkingDirectory $PSScriptRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At 9:00AM
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# 如果已存在同名任务则先注销
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# 注册新任务
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "AIGC 竞品监控与日报自动生成定时任务"
Write-Host "============================================================" -ForegroundColor Green
Write-Host "✅ 定时任务注册成功！" -ForegroundColor Green
Write-Host "任务名称: $TaskName" -ForegroundColor Cyan
Write-Host "执行周期: 每天早上 09:00" -ForegroundColor Cyan
Write-Host "执行脚本: $PSScriptRoot\run_daily.bat" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Green
