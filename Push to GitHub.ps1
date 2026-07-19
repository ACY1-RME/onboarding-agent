
# ACY1-RME GitHub — Auth + Push Fix

$ProjectDir = "$env:USERPROFILE\Dev\tools\onboarding-agent"
$OrgName    = "ACY1-RME"
$RepoName   = "onboarding-agent"

$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("PATH","User")

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ACY1-RME GitHub Auth + Push" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Authenticate ──────────────────────────────────────────────────────
Write-Host "[1/3] Checking GitHub auth..." -ForegroundColor Yellow
$authStatus = & gh auth status 2>&1
if ($authStatus -match "Logged in") {
    Write-Host "      Already logged in." -ForegroundColor Green
} else {
    Write-Host "      Not logged in. Opening browser now..." -ForegroundColor Yellow
    Write-Host "      Complete the login in your browser, then come back here." -ForegroundColor Gray
    Write-Host ""
    & gh auth login --web --git-protocol https

    # Verify it worked
    $authCheck = & gh auth status 2>&1
    if ($authCheck -notmatch "Logged in") {
        Write-Host ""
        Write-Host "Auth did not complete. Make sure you clicked 'Authorize' in the browser." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }
    Write-Host "      Logged in successfully." -ForegroundColor Green
}

& gh auth setup-git

# ── Step 2: Create repo ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "[2/3] Creating GitHub repo..." -ForegroundColor Yellow
$repoOut = & gh repo create "$OrgName/$RepoName" --public --description "ACY1 RME new hire onboarding web app" 2>&1
Write-Host $repoOut

# ── Step 3: Push files ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[3/3] Pushing files..." -ForegroundColor Yellow
Set-Location $ProjectDir

# Repo already initialized from previous run — just fix the remote and push
& git remote remove origin 2>$null
& git remote add origin "https://github.com/$OrgName/$RepoName.git"

# If tree is clean from previous commit attempt, still push
& git add -A
$commitOut = & git commit -m "Initial commit: Onboarding Agent v1.0" 2>&1
Write-Host $commitOut

& git push -u origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Push failed. See error above." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# ── Issues ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Creating roadmap issues..." -ForegroundColor Yellow
$issues = @(
    @{ title="Manager dashboard";                body="Read-only view showing all new hires task progress.`n`nFeatures:`n- List of techs who have run the agent`n- Progress bar per tech`n- Highlight overdue/stalled phases" },
    @{ title="Name prompt on launch";            body="Prompt for name on first load, display in welcome header. Store in localStorage." },
    @{ title="Role-specific tracks (AR vs MHE)"; body="Different Phase 2 task sets for AR tech vs MHE/sorter tech. Add role selector at start of Phase 2." },
    @{ title="Phase 3 specialty tracks";         body="Let tech pick a specialty track after Phase 1+2 (Controls, Mechanical, AR). Low priority." },
    @{ title="Auto-check via EAM";               body="Pull WO completion from HxGN EAM to auto-check tasks. Stretch goal - needs API investigation." }
)
foreach ($issue in $issues) {
    & gh issue create --repo "$OrgName/$RepoName" --title $issue.title --body $issue.body --label "enhancement" 2>&1 | Out-Null
    Write-Host "  Issue: $($issue.title)" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  All done!" -ForegroundColor Cyan
Write-Host "  https://github.com/$OrgName/$RepoName" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Enter to open the repo in your browser..."
Read-Host
Start-Process "https://github.com/$OrgName/$RepoName"
