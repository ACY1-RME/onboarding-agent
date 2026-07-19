@echo off
setlocal EnableDelayedExpansion
pushd "%~dp0"

title Onboarding Agent Installer
echo ============================================
echo   ACY1 RME Onboarding Agent - Installer
echo ============================================
echo.

set "SOURCE=%~dp0"
set "DEST=%USERPROFILE%\Documents\ACY1 Onboarding Agent"

py --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Ask your RME lead to install Python.
    popd
    pause
    exit /b 1
)
echo [OK] Python found.

echo.
echo [COPY] Copying files...
if not exist "%DEST%" mkdir "%DEST%"

xcopy /E /Y /Q "%SOURCE%*" "%DEST%\" >nul
if errorlevel 1 (
    echo [ERROR] File copy failed. Check share access.
    popd
    pause
    exit /b 1
)
echo [OK] Files copied to: %DEST%

(
echo @echo off
echo start "" /min py "%%~dp0agent_server.py"
) > "%DEST%\Launch Onboarding Agent.bat"

set "SHORTCUT=%USERPROFILE%\Desktop\Onboarding Agent.lnk"
set "ICON=%DEST%\onboard.ico"
set "TARGET=%DEST%\Launch Onboarding Agent.bat"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%TARGET%'; $sc.WorkingDirectory = '%DEST%'; $sc.IconLocation = '%ICON%'; $sc.WindowStyle = 1; $sc.Description = 'ACY1 RME Onboarding Agent'; $sc.Save()"

if exist "%SHORTCUT%" (
    echo [OK] Desktop shortcut created.
) else (
    echo [WARN] Shortcut not created - run Launch bat directly from: %DEST%
)

popd
echo.
echo ============================================
echo   Install complete! Double-click Onboarding
echo   Agent on your Desktop to launch.
echo ============================================
echo.
pause
