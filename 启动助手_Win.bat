@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Google AI Trial Studio - blog.caowo.de ^| faka.cdkey.si

set "PY_EXE="
set "PY_ARGS="

:rescan_py
if exist "%~dp0runtime\python\python.exe" (
    "%~dp0runtime\python\python.exe" -c "import sys; assert sys.version_info >= (3,9)" >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=%~dp0runtime\python\python.exe"
        set "PATH=%~dp0runtime\python\Scripts;%~dp0runtime\python;%~dp0platform-tools;%PATH%"
        goto :found_py
    )
)

py -3 -c "import sys; assert sys.version_info >= (3,9)" >nul 2>&1
if not errorlevel 1 (
    set "PY_EXE=py"
    set "PY_ARGS=-3"
    goto :found_py
)

python -c "import sys; assert sys.version_info >= (3,9)" >nul 2>&1
if not errorlevel 1 (
    set "PY_EXE=python"
    goto :found_py
)

if exist "%SystemRoot%\py.exe" (
    "%SystemRoot%\py.exe" -3 -c "import sys; assert sys.version_info >= (3,9)" >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=%SystemRoot%\py.exe"
        set "PY_ARGS=-3"
        goto :found_py
    )
)

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "C:\Python3*" "%ProgramFiles%\Python3*" "%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3") do (
    if exist "%%~fD\python.exe" (
        "%%~fD\python.exe" -c "import sys; assert sys.version_info >= (3,9)" >nul 2>&1
        if not errorlevel 1 (
            set "PY_EXE=%%~fD\python.exe"
            goto :found_py
        )
    )
)

if defined TRIED_WINGET goto :py_missing
set "TRIED_WINGET=1"
echo ========================================================================
echo   [!] 未检测到 Python 3.9+ 运行环境
echo   [*] 正在通过 Windows 官方 winget 自动安装 Python 3.12 (安装后自动继续)...
echo   [*] 官方博客: https://blog.caowo.de/  ^|  发卡网(GPT代充): https://faka.cdkey.si/
echo ========================================================================
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
goto :rescan_py

:py_missing
echo [-] 自动安装未成功，请前往 https://www.python.org/downloads/ 安装 Python 3.12 (勾选 Add to PATH) 后重新双击运行。
echo     技术博客          : https://blog.caowo.de/
echo     发卡网 (GPT 代充) : https://faka.cdkey.si/
pause
exit /b 1

:found_py
"%PY_EXE%" %PY_ARGS% "%~dp0gtool.py" %*
echo.
echo   📖 技术博客          : https://blog.caowo.de/
echo   🛒 发卡网 (GPT 代充) : https://faka.cdkey.si/
echo.
pause
