# ACY1 RME Onboarding Agent — Maintainer Guide

A local web app that walks new RME hires through the Red Vest onboarding program:
phased checklist, per-task detail cards, resource library, AI assistant, admin
roster + progress dashboard, and a completion certificate.

## How it runs
- Python `ThreadingHTTPServer` on **port 5901** (`agent_server.py`).
- Each teammate runs their **own** instance from the share (`Onboarding Agent.bat`
  / "Run from Share (No Install).bat"). Bundled Python lives in `_py\`.
- UI is a single generated `index.html` (~345 KB, everything inlined).

## Build pipeline (source of truth lives in ~/.aki/tmp)
Edit the sources, then rebuild:
    python3 "C:\Users\souyackg\.aki\tmp\ob_build3.py"
-> writes C:\Users\souyackg\Dev\tools\onboarding-agent\index.html

Source files (all in ~/.aki/tmp):
- ob_build3.py       — page assembly: _PHASES (phase order), _TASKS (task HTML),
                       Resources + Quick Links tabs. New JS injected via {NEW_JSn}.
- ob_detail_data.py  — TASK_DETAILS (per-task desc/steps/links/posix) + path roots.
- ob_assets.py       — ACY1LOGO, HEADER_PHOTO (base64).

Editing rule: use a Python heredoc with an assert-and-replace helper
(rep(old,new)). The `edit` built-in is denied on the Dev path.

Validate after every build:
- no leaked {NEW_JS / {ACY1LOGO} / __CHECKLIST__ / __FT__ in index.html
- no local `Dev\reference` paths in index.html (must all be UNC)
- extract the largest <script> and parse it with:
  node -e "new Function(require('fs').readFileSync('_jsc.js','utf8'))"

## Deploy to the share
    powershell -ExecutionPolicy Bypass -File "C:\Users\souyackg\.aki\tmp\ob_deploy.ps1"
Copies index.html + agent_server.py to
\\ant\dept-na\ACY1\Support\RME\RME Tools\onboarding-agent\
Then confirm local vs share byte sizes match.

## Resource files (share-hosted since 2026-07-10)
All Resources/Quick-Links buttons resolve to the share, so they work for every
teammate (not just the build machine):
- Root REF -> \\...\RME\RME Tools\onboarding-agent\reference  (copied tree)
- EQDOC    -> \\...\RME\Equipment Documentation               (canonical full set)
Re-push the reference tree whenever you reorganize your local Dev\reference:
    powershell -ExecutionPolicy Bypass -File "C:\Users\souyackg\.aki\tmp\copy_ref.ps1"

## State & data model (%LOCALAPPDATA%\ACY1 Onboarding Agent\)
- progress\        one <name-slug>.json per user (per-machine)
- progress_cache\  copies pulled from the share (read by admin dashboard)
- admins.json / roster.json / admin_log.json  admin control files
- sync_state.json  last sync timestamps

Sync (background loop + "Sync Now" button):
- progress: push local -> share, pull share -> local cache (union, additive).
- admins.json: symmetric newest-wins per file (rare credential changes).
- roster.json + admin_log.json: **convergent union merge** (added 2026-07-11) done
  in Python, not newest-wins. Roster people are unioned by name (newest ts wins);
  removals write a tombstone {name, ts} so a delete on one machine is not
  resurrected by another's stale copy; re-adding clears the tombstone. admin_log
  entries are unioned (dedup on ts/user/action/detail, newest 500). This means two
  admins (souyackg + billy) never clobber each other's roster edits.
Known limit: progress identity = slug of first name, so two hires with the same
first name collide into one file.

## Admin accounts
- souyackg / 37@Keystone123
- billy    / ACY1-Billy   (temporary — Billy should change on first login)
- admin    / ACY1-RME
(Reset by writing a fresh salt+hash to admins.json; passwords are hashed.)

## Launching the server (dev / host machine)
Detached PowerShell processes die ~10s after the launching shell exits (sandbox
job-object cleanup). Launch via WMI so it escapes the job object:
    powershell -ExecutionPolicy Bypass -File "C:\Users\souyackg\.aki\tmp\start_ob.ps1"
Liveness check (GET only — does NOT arm the idle watchdog):
    curl -s -m3 http://127.0.0.1:5901/ -o /dev/null -w "%{http_code}"
PING_TIMEOUT_SEC=600. The watchdog only arms after the page calls /api/ping.

## GitHub / share
Share: \\ant\dept-na\ACY1\Support\RME\RME Tools\onboarding-agent\
