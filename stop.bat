@echo off
setlocal enabledelayedexpansion
title Voice AI - Mr.Huynh - Dung ung dung
cd /d "%~dp0"

echo ================================================================
echo         Voice AI - Mr.Huynh - Free Vietnamese Text-to-Speech
echo         Tac gia: Mr.Huynh (https://mrhuynh.net)
echo ================================================================
echo.
echo [+] Dang tim va dong cac tien trinh Voice AI - Mr.Huynh dang chay...
echo.

set "STOPPED=0"

:: Dong tien trinh dang lang nghe tren Port 8001 (may chu cua ung dung)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8001 ^| findstr LISTENING 2^>nul') do (
    set "STOPPED=1"
    echo [+] Dang dong tien trinh Voice AI - Mr.Huynh tren Port 8001 (PID: %%a)...
    taskkill /f /pid %%a >nul 2>&1
)

echo.
if "!STOPPED!"=="1" (
    echo ================================================================
    echo  [+] Da dong thanh cong tat ca tien trinh Voice AI - Mr.Huynh!
    echo ================================================================
) else (
    echo [i] Khong tim thay tien trinh Voice AI - Mr.Huynh nao dang chay.
)
echo.
pause
