@echo off
chcp 65001 >nul
title Bybit定时任务调度器

echo ================================
echo    Bybit定时任务调度器
echo ================================
echo.
echo [INFO] 即将启动定时任务调度器
echo [INFO] 执行频率：每30分钟
echo [INFO] 执行任务：complete_flow.py
echo [INFO] 浏览器模式：后台窗口
echo.
echo [TIP] 按 Ctrl+C 可以停止定时任务
echo ================================
echo.

cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
python scheduler.py

echo.
echo 按任意键退出...
pause >nul
