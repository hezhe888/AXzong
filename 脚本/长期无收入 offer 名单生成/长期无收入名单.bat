@echo off
cd /d "%~dp0"
echo ====================================
echo   长期无收入 offer 名单生成
echo ====================================
echo 规则说明：
echo   1) 入库满 N 天（从监控首现日算起）
echo   2) 最近 M 天内无收入（Revenue=0）
echo   3) 最近 K 天内至少一天在线
echo   4) 按全程 Revenue 降序排列
echo.
set /p DAYS=请输入入库满几天（默认 15，直接回车）: 
if "%DAYS%"=="" set DAYS=15
set /p NOREV=请输入最近多少天内无收入（默认 15，直接回车）: 
if "%NOREV%"=="" set NOREV=15
set /p ACT=请输入最近几天内在线过（默认 1，直接回车）: 
if "%ACT%"=="" set ACT=1
echo.
echo 正在查询，请稍候...
echo.
py offer_no_rev_report.py --days %DAYS% --no-rev-days %NOREV% --active-days %ACT%
echo.
pause
