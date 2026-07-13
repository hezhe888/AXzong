@echo off
cd /d "%~dp0backend"
echo ========================================
echo   数据分析助手 - Starting...
echo   Backend: http://localhost:8000
echo ========================================
py -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
