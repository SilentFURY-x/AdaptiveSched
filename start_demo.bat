@echo off
title AdaptiveSched Demo Runner - Review 2
echo ======================================================================
echo    AdaptiveSched: Autonomous CPU Scheduler Selection Engine
echo    Project Review 2 Demo Environment
echo ======================================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PY_CMD=python
) else (
    where py >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        set PY_CMD=py -3
    ) else (
        echo [ERROR] Neither 'python' nor 'py' was found in PATH.
        pause
        exit /b 1
    )
)

echo Using Python command: %PY_CMD%
echo.
echo Installing dependencies if needed...
%PY_CMD% -m pip install -r requirements.txt
echo.
echo Starting AdaptiveSched Agent and Web Dashboard...
%PY_CMD% run_demo.py
pause
