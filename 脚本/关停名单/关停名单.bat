@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ====================================
echo   offer 建议关停名单生成
echo ====================================
echo.
set /p DAYS=请输入入库满几天（默认 7，直接回车）: 
if "%DAYS%"=="" set DAYS=7
set /p ACT=请输入最近几天在线过（默认 3，直接回车）: 
if "%ACT%"=="" set ACT=3
set /p ECPC=请输入 eCPC 上限阈值，低于此值将列入名单（默认 0.1，直接回车）: 
if "%ECPC%"=="" set ECPC=0.1
echo.
echo 正在查询，请稍候...
echo.
py -X utf8 offer_shutdown_report.py --days %DAYS% --active-days %ACT% --ecpc %ECPC%
echo.
pause
