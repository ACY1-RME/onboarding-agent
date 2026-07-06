@echo off
setlocal EnableDelayedExpansion

title Onboarding Agent Installer
echo ============================================
echo   ACY1 RME Onboarding Agent - Installer
echo ============================================
echo.

:: ── 1. Source path on RME share ──────────────────────────────────────────────
set "SOURCE=\\ant\dept-na\ACY1\Support\RME\Onboarding Agent"
set "DEST=%USERPROFILE%\Desktop\Onboarding Agent"

if not exist "%SOURCE%" (
    echo [ERROR] Cannot reach RME share:
    echo         %SOURCE%
    echo.
    echo Make sure you are connected to the Amazon network (VPN or on-site).
    pause
    exit /b 1
)

:: ── 2. Check / install uv ────────────────────────────────────────────────────
where uv >nul 2>&1
if errorlevel 1 (
    echo [SETUP] uv not found - installing now...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 (
        echo [ERROR] uv install failed. Ask your site IT or RME lead for help.
        pause
        exit /b 1
    )
    echo [SETUP] uv installed successfully.
) else (
    echo [OK] uv is already installed.
)

:: ── 3. Copy files ────────────────────────────────────────────────────────────
echo.
echo [COPY] Copying files to your Desktop...
if not exist "%DEST%" mkdir "%DEST%"

xcopy /E /Y /Q "%SOURCE%\*" "%DEST%\" >nul
if errorlevel 1 (
    echo [ERROR] File copy failed. Check share access and try again.
    pause
    exit /b 1
)
echo [OK] Files copied.

:: ── 4. Write portable launch bat (uses uv run - no hardcoded Python path) ────
(
echo @echo off
echo uv run "%%~dp0agent_server.py"
) > "%DEST%\Launch Onboarding Agent.bat"

:: ── 5. Create desktop shortcut ───────────────────────────────────────────────
set "SHORTCUT=%USERPROFILE%\Desktop\Onboarding Agent.lnk"
set "ICON=%DEST%\onboard.ico"
set "TARGET=%DEST%\Launch Onboarding Agent.bat"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%TARGET%'; $sc.WorkingDirectory = '%DEST%'; $sc.IconLocation = '%ICON%'; $sc.WindowStyle = 7; $sc.Description = 'ACY1 RME Onboarding Agent'; $sc.Save()"

if exist "%SHORTCUT%" (
    echo [OK] Desktop shortcut created.
) else (
    echo [WARN] Shortcut creation failed - you can still launch from %DEST%
)

echo.
echo ============================================
echo   Install complete!
echo   Double-click "Onboarding Agent" on your
echo   Desktop to launch.
echo ============================================
echo.
pause
