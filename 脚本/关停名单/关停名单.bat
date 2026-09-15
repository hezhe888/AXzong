@echo off
cd /d "%~dp0"
echo ====================================
echo   offer 名单生成（关停 / push）
echo ====================================
echo 规则说明：
echo   1) 入库满 N 天（从监控首现日算起）
echo   2) 最近 M 天内至少一天在线
echo   3) 口径：上限=关停名单（低于阈值）^| 下限=push名单（不低于阈值）
echo.
set /p DAYS=请输入入库满几天（默认 7，直接回车）: 
if "%DAYS%"=="" set DAYS=7
set /p ACT=请输入最近几天内在线过（默认 3，直接回车）: 
if "%ACT%"=="" set ACT=3
set /p MODE=请选择 eCPC 口径（1=上限/关停名单，2=下限/push名单，默认 1，直接回车）: 
if "%MODE%"=="" set MODE=1
set ECMODE=below
if "%MODE%"=="2" set ECMODE=above
set /p ECPC=请输入 eCPC 阈值（默认 0.1，直接回车）: 
if "%ECPC%"=="" set ECPC=0.1
echo.
echo 正在查询，请稍候...
echo.
py offer_shutdown_report.py --days %DAYS% --active-days %ACT% --ecpc-mode %ECMODE% --ecpc %ECPC%
echo.
pause
