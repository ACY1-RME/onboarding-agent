# Finds and removes duplicate GitHub Issues (same title) in ACY1-RME/onboarding-agent,
# keeping the oldest (lowest-numbered) copy of each and deleting the rest.
$ErrorActionPreference = "Stop"
$repo = "ACY1-RME/onboarding-agent"

try {
    Write-Host "Fetching all issues from $repo..." -ForegroundColor Cyan
    $raw = gh issue list --repo $repo --state all --limit 200 --json number,title,createdAt
    $issues = $raw | ConvertFrom-Json

    if (-not $issues -or $issues.Count -eq 0) {
        Write-Host "No issues found." -ForegroundColor Yellow
        Read-Host "Press Enter to close"
        exit
    }

    Write-Host "`nFound $($issues.Count) total issues.`n"

    # Group by title, sort each group by number (ascending) so the first-created stays
    $groups = $issues | Group-Object -Property title

    $toDelete = @()
    foreach ($g in $groups) {
        if ($g.Count -gt 1) {
            $sorted = $g.Group | Sort-Object -Property number
            $keep = $sorted[0]
            $dupes = $sorted[1..($sorted.Count - 1)]
            Write-Host "Title: '$($g.Name)' -> keeping #$($keep.number), removing $($dupes.number -join ', ')" -ForegroundColor Green
            $toDelete += $dupes
        }
    }

    if ($toDelete.Count -eq 0) {
        Write-Host "`nNo duplicates found. Nothing to do." -ForegroundColor Yellow
        Read-Host "Press Enter to close"
        exit
    }

    Write-Host "`nAbout to permanently delete $($toDelete.Count) duplicate issue(s): #$($toDelete.number -join ', #')" -ForegroundColor Yellow
    $confirm = Read-Host "Type YES to confirm deletion"
    if ($confirm -ne "YES") {
        Write-Host "Cancelled." -ForegroundColor Yellow
        Read-Host "Press Enter to close"
        exit
    }

    foreach ($issue in $toDelete) {
        Write-Host "Deleting #$($issue.number) ($($issue.title))..." -ForegroundColor Cyan
        try {
            gh issue delete $issue.number --repo $repo --yes
        } catch {
            Write-Host "  Delete failed (likely needs admin perms), closing instead..." -ForegroundColor Yellow
            gh issue close $issue.number --repo $repo --reason "not planned" --comment "Duplicate issue, closed by cleanup script."
        }
    }

    Write-Host "`nDone. Refresh the Issues tab to confirm." -ForegroundColor Green
} catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Screenshot this window and share it to get help." -ForegroundColor Yellow
}
Read-Host "`nPress Enter to close"
