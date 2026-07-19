# Onboarding Agent — Security & Quality Review (2026-07-12)

A three-round review-and-fix pass on `agent_server.py` and the generated `index.html`.
Findings were gathered by three parallel read-only review agents (backend Python,
frontend JS, and content/structure), consolidated, then implemented centrally and
validated (`py_compile` clean, JS parse clean, full rebuild).

## Backend — `agent_server.py` (9 fixes applied)

| ID | Severity | Fix |
|----|----------|-----|
| C1 | Critical | `/api/shutdown` now requires a valid admin session token (POST `{"token": <session_token>}`). Was unauthenticated. |
| H2 | High | `check_login` uses `hmac.compare_digest` (added `import hmac`) instead of `==` for hash comparison (timing-safe). |
| H4 | High | `do_POST` body JSON parse wrapped in `try/except (ValueError, JSONDecodeError)` → returns 400 instead of 500. |
| M2 | Medium | Login rate-limiting: `_login_attempts` dict + `_check_rate_limit`/`_record_failure`/`_clear_attempts`. 30s lockout after 5 failures. Wired into `_admin_login`. |
| M5 | Medium | Added `ps_escape()` helper; applied to all 5 PowerShell path interpolations in `sync_all()` (prevents path-based PS injection). |
| M6 | Medium | `check_login` guards missing keys: `'salt' not in u or 'hash' not in u`. |
| L1 | Low | `create_session` evicts oldest session when `len(_sessions) >= 100` (unbounded growth). |
| L3 | Low | Empty-name guard in `_admin_roster_remove`. |
| L4 | Low | `log_admin_action` truncates detail to `[:256]`. |

**Deferred (documented, not fixed):**
- M1 — session token passed in URL; needs a JS refactor to move to header/body.
- M3 — default admin password hashes hardcoded in source; a deploy-process change, not a code fix.
- M4 — no sync-lock on admin writes; would block ~15s. Low blast radius for a 2-admin local tool.

## Frontend — rebuilt `index.html` via `ob_build3.py` (11 fixes applied)

| Severity | Fix |
|----------|-----|
| High | `appendMsg` — user messages set via `textContent` (was `innerHTML` for all → stored XSS). `if(cls==='user')el.textContent=text;else el.innerHTML=text;` |
| High | Removed dead `.forEach;` no-op in `loadLog`. |
| Med | `applyName` wraps the name in `esc(n)` before innerHTML injection (reflected XSS via name). |
| Med | Removed dead duplicate `openProgressReport(){showCertificate();}` in NEW_JS (correct one is in NEW_JS3). |
| Med | `addRoster` catch shows "Server error — try again." in the input placeholder. |
| Med | `removeRoster` catch reloads roster + inserts an inline warn banner. |
| Med | `buildTacList` Open buttons get `aria-label="Open ${t.name}"`. |
| Low | `buildTacList` null-guard `if(!el)return;`. |
| Low | Removed duplicate `injectTimeBadges()` from the second DOMContentLoaded handler. |
| Low | `Prefferred`→`Preferred` in the Change Preferred Name SharePoint URL. |
| Low | Added `cb1:5,cb2:15,cb3:60,cb4:60,cb5:60,cb6:10` to the TM time dict so CBRE tasks show time badges. |

Also removed earlier: dead `applyName`/`saveName` stubs in the f-string base (shadowed by NEW_JS versions).

**False positives (verified correct, NOT changed):** the "double-escaped UNC paths" for
`r(ACY1R)` vs hardcoded paths — generated HTML shows identical `\\\\ant\\...`; Windows
normalizes extra leading backslashes.

**Final build:** `344,286 bytes | tasks:49 | posix:8`.

## How to test locally (post-patch)

Full test (server + all features):

    python3 "C:\Users\souyackg\Dev\tools\onboarding-agent\agent_server.py"

Binds `127.0.0.1:5901`, sets up local state, starts background sync (skips silently
off-network), auto-opens Chrome. Stdlib only. Stop with Ctrl+C, or it self-exits
~10 min after the tab closes (watchdog, `PING_TIMEOUT_SEC=600`, arms only after the
page calls `/api/ping`).

Quick look (no server): open `index.html` directly — checklist, task details,
resources, cert, and report work client-side; chat/admin/sync/openfile need the server.

**Verify the patches:**
- Login rate-limit: 5 wrong passwords → 30s lockout.
- XSS: chat message `<img src=x onerror=alert(1)>` renders as literal text; name with HTML tags shows escaped in the welcome banner.
- CBRE time badges: cb1–cb6 show 5/15/60/60/60/10 min.
- Admin errors: stop the server mid-op, then roster add/remove → surfaces "Server error".
- `/api/shutdown` needs an admin session token.
