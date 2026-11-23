@echo off
setlocal enabledelayedexpansion
title Voice AI - Mr.Huynh - Tao file .exe
cd /d "%~dp0"

echo ================================================================
echo   Voice AI - Mr.Huynh - TAO FILE .EXE CHO WINDOWS
echo   Chay 1 lan, mat khoang 10-25 phut (can co mang).
echo ================================================================
echo.

:: 1. Kiem tra cong cu
where uv >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Chua cai "uv". Mo PowerShell/CMD, chay lenh sau roi MO LAI cua so nay:
    echo         winget install --id astral-sh.uv -e
    echo         ^(hoac xem https://docs.astral.sh/uv/^)
    pause
    exit /b 1
)
if not exist "app-desktop\voice-ai-app\dist\index.html" (
    where npm >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Thieu giao dien build san va chua cai Node.js 20+.
        echo         Cai bang:  winget install OpenJS.NodeJS.LTS   roi chay lai.
        pause
        exit /b 1
    )
)

:: 2. Thu vien Python
echo [+] Buoc 1/4: Cai thu vien Python...
uv sync --frozen --group desktop
if errorlevel 1 (
    echo [ERROR] uv sync that bai. Kiem tra mang, tat VPN/proxy roi chay lai.
    pause
    exit /b 1
)

:: 3. Tai san mo hinh de file .exe chay duoc ngay, khong can mang
if not exist "models\hf_cache" (
    echo [+] Buoc 2/4: Tai mo hinh giong noi ^(~312 MB^)...
    ".venv\Scripts\python.exe" scripts\fetch_models.py
    if errorlevel 1 (
        echo [!] Khong tai san duoc mo hinh. Van tiep tuc; app se tai o lan chay dau.
    )
) else (
    echo [+] Buoc 2/4: Da co mo hinh trong models\hf_cache.
)

:: 4. Dong goi .exe
echo [+] Buoc 3/4: Dong goi thanh .exe...
call scripts\build_desktop_exe.bat --no-pause
if errorlevel 1 (
    echo [ERROR] Dong goi that bai, xem loi o tren.
    pause
    exit /b 1
)

:: 5. Tao them file cai Setup.exe neu may co Inno Setup
set "HAS_ISCC="
for %%P in (
    "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
) do if exist "%%~P" set "HAS_ISCC=1"
if defined HAS_ISCC (
    echo [+] Buoc 4/4: Tao file cai Setup.exe...
    call scripts\make_installer.bat --no-pause
    if not errorlevel 1 (
        echo [+] Tao goi tai len trang tai ^(dist\downloads-voice-upload.zip^)...
        ".venv\Scripts\python.exe" scripts\make_downloads.py
    )
) else (
    echo [+] Buoc 4/4: Bo qua file cai Setup ^(chua cai Inno Setup; khong bat buoc^).
)

echo.
echo ================================================================
echo  XONG. File chay truc tiep:
echo    dist\Voice-AI-MrHuynh\Voice-AI-MrHuynh.exe
echo  Muon gui cho nguoi khac: nen ca thu muc dist\Voice-AI-MrHuynh thanh .zip
if defined HAS_ISCC echo  File cai dat 1 file: dist\Voice-AI-MrHuynh-v*-win-x86_64.exe
if exist "dist\downloads-voice-upload.zip" echo  TAI LEN HOSTING: dist\downloads-voice-upload.zip  ^(Upload vao mrhuynh.net/downloads/ roi Extract, sau do Trang quan tri ^> Voice AI ^> Phat hanh^)
echo ================================================================
explorer "dist\Voice-AI-MrHuynh"
pause
