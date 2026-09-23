@echo off
cd /d "%~dp0"
echo ====================================
echo   长期在线 offer 名单生成（push 用）
echo ====================================
echo 规则说明：
echo   1) 当前在线（最后记录小时为 1）
echo   2) 连续在线满 N 小时（断 1 小时即中断）
echo   3) payout eCPC 大于 M（M=0 则不筛）
echo   4) 转化数大于等于 V（V=0 则不筛）
echo   5) 按全程 eCPC 降序排列
echo.
set /p HOURS=请输入连续在线小时阈值（默认 48，直接回车）: 
if "%HOURS%"=="" set HOURS=48
set /p ECPC=请输入 payout eCPC 阈值（默认 0.5，输入 0 则不筛，直接回车）: 
if "%ECPC%"=="" set ECPC=0.5
set /p CONV=请输入转化数阈值（默认 0=不筛，直接回车）: 
if "%CONV%"=="" set CONV=0
echo.
echo 正在查询，请稍候...
echo.
py offer_long_online_report.py --min-hours %HOURS% --ecpc %ECPC% --min-conv %CONV%
echo.
pause
