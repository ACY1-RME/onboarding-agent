# ACY1 RME Onboarding Agent

A local web app that guides new RME hires through their first 30 days at ACY1.
Runs entirely on the technician's machine - no server, no login required.

## Features
- 15 onboarding tasks across 3 phases
- Task detail panels with step-by-step instructions
- Progress tracked in the browser (localStorage)
- Auto-check on action button clicks
- Links to TAC, EAM, and RME share resources
- POSIX/permissions callouts for tasks that need IT access

## Project Files

| File | Purpose |
|---|---|
| index.html | Front-end UI (generated, do not edit directly) |
| agent_server.py | Serves the app at port 5901, auto-opens Chrome |
| ob_build3.py | Build script - regenerates index.html |
| ob_detail_data.py | All task content: steps, descriptions, links. Edit this. |
| ob_vars.py | Logos, branding, TAC links |
| Install Onboarding Agent.bat | One-click installer for any new machine |

## Making a Content Change

1. Open ob_detail_data.py in any text editor
2. Find the task (labeled # Task 1, # Task 2, etc.)
3. Edit steps, description, or action links
4. Run ob_build3.py - regenerates index.html
5. Test in browser, then push changes back to this repo

## Installing on a New Machine

1. Clone this repo or download the ZIP
2. Run Install Onboarding Agent.bat
3. It installs uv if needed and creates a Desktop shortcut automatically

## Roadmap
See the Issues tab for planned features and current status.

## Site
ACY1 - Amazon Fulfillment Center
Team: RME (Reliability Maintenance Engineering)
