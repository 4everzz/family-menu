@echo off
chcp 936 >nul
title 小家菜单 - 后端服务
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto noenv

echo ============================================
echo    小家菜单 . 后端服务
echo ============================================
echo.
echo   接口地址：http://127.0.0.1:8000
echo   接口文档：http://127.0.0.1:8000/docs
echo   健康检查：http://127.0.0.1:8000/api/v1/health
echo.
echo   关掉这个窗口 = 停止服务。
echo   启动失败时窗口会停在错误信息上，请截图发我。
echo ============================================
echo.

rem Do NOT use run.py here: it enables reload and spawns two processes.
rem Must specify the selector event loop on Windows for psycopg async.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --loop app.core.event_loop:selector_loop_factory

echo.
echo ============================================
echo   [服务已停止]
echo   如果上面有报错，请截图发我。
echo ============================================
pause
exit /b 0

:noenv
echo.
echo   [错误] 找不到虚拟环境：.venv\Scripts\python.exe
echo          请在 backend 目录下创建虚拟环境并安装依赖。
echo.
pause
exit /b 1
