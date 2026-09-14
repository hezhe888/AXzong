@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ====================================
echo   offer 建议关停名单生成
echo ====================================
echo.
set /p DAYS=请输入入库天数（默认 15，直接回车）: 
if "%DAYS%"=="" set DAYS=15
set /p ECPC=请输入 eCPC 阈值（默认 0.1，直接回车）: 
if "%ECPC%"=="" set ECPC=0.1
echo.
echo 正在查询，请稍候...
echo.
py -X utf8 offer_shutdown_report.py --days %DAYS% --ecpc %ECPC%
echo.
pause
