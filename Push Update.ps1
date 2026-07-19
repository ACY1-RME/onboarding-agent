# Pushes the latest Onboarding Agent changes (name/role personalization feature) to GitHub.
$ErrorActionPreference = "Stop"
try {
    Set-Location "$env:USERPROFILE\Dev\tools\onboarding-agent"
    git add -A
    git commit -m "Add name/role modal + MHE/AR task filtering + dynamic specialty tracks (closes #2, #3, #4)"
    git push
    Write-Host "`nPushed successfully." -ForegroundColor Green
} catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Screenshot this window and share it to get help." -ForegroundColor Yellow
}
Read-Host "`nPress Enter to close"
