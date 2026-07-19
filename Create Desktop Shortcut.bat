@echo off
setlocal
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$here='%HERE%';" ^
 "$desk=[Environment]::GetFolderPath('Desktop');" ^
 "$ws=New-Object -ComObject WScript.Shell;" ^
 "$l=$ws.CreateShortcut((Join-Path $desk 'ACY1 Onboarding Agent.lnk'));" ^
 "$l.TargetPath=(Join-Path $here 'Onboarding Agent.bat');" ^
 "$l.Arguments=('\"'+(Join-Path $here 'agent_server.py')+'\"');" ^
 "$l.WorkingDirectory=$here;" ^
 "$l.IconLocation=((Join-Path $here 'onboard.ico')+',0');" ^
 "$l.WindowStyle=7;" ^
 "$l.Save();" ^
 "Write-Host ('Created: '+(Join-Path $desk 'ACY1 Onboarding Agent.lnk'))"
echo.
echo Done. Look for "ACY1 Onboarding Agent" on your Desktop.
pause
