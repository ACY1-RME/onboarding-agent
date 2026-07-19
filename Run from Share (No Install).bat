@echo off
REM ACY1 RME Onboarding Agent -- bootstrap launcher (caches Python locally for fast startup)
set "SHARE=%~dp0"
set "CACHE=%LOCALAPPDATA%\ACY1 Onboarding Agent\_py"
if exist "%CACHE%\pythonw.exe" goto run
title ACY1 Onboarding Agent - one-time setup
echo.
echo   First-time setup (about 15 seconds)...
echo   This only happens once. Future launches are instant.
robocopy "%SHARE%_py" "%CACHE%" /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 >nul
:run
if not exist "%CACHE%\pythonw.exe" set "CACHE=%SHARE%_py"
start "" "%CACHE%\pythonw.exe" "%SHARE%agent_server.py"
exit /b
