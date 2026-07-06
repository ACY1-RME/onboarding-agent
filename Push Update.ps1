# Pushes the latest Onboarding Agent changes (name/role personalization feature) to GitHub.
$ErrorActionPreference = "Stop"
try {
    Set-Location "$env:USERPROFILE\Desktop\Onboarding Agent"
    git add -A
    git commit -m "Add name/role onboarding modal + MHE/AR task filtering (closes #2, #3)"
    git push
    Write-Host "`nPushed successfully." -ForegroundColor Green
} catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Screenshot this window and share it to get help." -ForegroundColor Yellow
}
Read-Host "`nPress Enter to close"
