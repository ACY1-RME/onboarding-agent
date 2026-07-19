"""ACY1 RME Onboarding Agent - HTTP Server (port 5901)"""
import threading
import subprocess
import json
import os
import contextlib
import hmac
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT   = 5901
DEST   = os.path.dirname(os.path.abspath(__file__))
# Writable per-user state dir (so the agent can run read-only from the share).
_appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or DEST
STATE = os.path.join(_appdata, "ACY1 Onboarding Agent")
try:
    os.makedirs(STATE, exist_ok=True)
except Exception:
    STATE = DEST
def _find_aki():
    # Try AKI_BIN env var first (set by Aki installer), then common install paths.
    # We call Aki.exe directly to avoid aki.cmd's %AKI_BIN% expansion failing
    # when the env var hasn't propagated to a freshly launched process.
    b = os.environ.get("AKI_BIN", "")
    if b and os.path.isfile(b):
        return b
    for loc in [
        os.path.join(os.environ.get("LOCALAPPDATA",""), "Aki", "Aki.exe"),
        os.path.join(os.environ.get("PROGRAMFILES",""), "Aki", "Aki.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)",""), "Aki", "Aki.exe"),
    ]:
        if loc and os.path.isfile(loc):
            return loc
    return ""
AKI = _find_aki()
PROFILE = "acy1-onboarding"  # constrained Q&A profile shipped in ./profile/
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

import re
import time

SHARE_PROGRESS_DIR = r"\\ant\dept-na\ACY1\Support\RME\RME Tools\onboarding-agent\progress"
LOCAL_PROGRESS_DIR = os.path.join(STATE, "progress")
LOCAL_CACHE_DIR     = os.path.join(STATE, "progress_cache")
SYNC_STATE_FILE     = os.path.join(STATE, "sync_state.json")
SYNC_INTERVAL_SEC   = 30

# --- Auto-shutdown watchdog: exit when the browser tab stops pinging ---
_last_ping = [0.0]
_page_seen = [False]
PING_TIMEOUT_SEC = 600
def start_shutdown_watchdog():
    def loop():
        while True:
            time.sleep(3)
            if _page_seen[0] and (time.time() - _last_ping[0]) > PING_TIMEOUT_SEC:
                os._exit(0)
    threading.Thread(target=loop, daemon=True).start()

_sync_lock = threading.Lock()
_file_lock  = threading.Lock()  # guards all JSON read-modify-write ops
_sync_state = {"connected": False, "last_sync": None, "last_attempt": None, "syncing": False}

def ensure_local_dirs():
    for d in (LOCAL_PROGRESS_DIR, LOCAL_CACHE_DIR):
        with contextlib.suppress(Exception):
            os.makedirs(d, exist_ok=True)

def load_sync_state():
    global _sync_state  # noqa: PLW0602 -- .update() mutates module-level dict
    with contextlib.suppress(Exception), open(SYNC_STATE_FILE, encoding="utf-8") as f:
        _sync_state.update(json.load(f))

def persist_sync_state():
    with contextlib.suppress(Exception), open(SYNC_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(_sync_state, f)

def run_ps(cmd, timeout=6):
    try:
        r = subprocess.run(  # noqa: S603
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],  # noqa: S607
            capture_output=True, text=True, timeout=timeout,
            check=False
        )
    except Exception as e:
        return False, "", str(e)
    else:
        return r.returncode == 0, r.stdout, r.stderr

def check_share_reachable():
    # Quick, short-timeout probe -- won't hang the app if we're offline.
    ok, out, _ = run_ps(f"if (Test-Path '{SHARE_PROGRESS_DIR}') {{'YES'}} else {{'NO'}}", timeout=5)
    return ok and "YES" in out

def sync_all(manual=False):
    # Offline-first: local files are always the source of truth.
    # This best-effort pushes everything local up to the share and pulls
    # everything else down, updating sync state either way.
    with _sync_lock:
        _sync_state["syncing"] = True
        _sync_state["last_attempt"] = time.time()
        persist_sync_state()
        ensure_local_dirs()
        reachable = check_share_reachable()
        _sync_state["connected"] = reachable
        if reachable:
            try:
                share_root = os.path.dirname(SHARE_PROGRESS_DIR)
                run_ps(
                    f"New-Item -ItemType Directory -Path '{ps_escape(SHARE_PROGRESS_DIR)}' -Force "
                    f"-ErrorAction SilentlyContinue | Out-Null; "
                    f"Copy-Item -Path '{ps_escape(LOCAL_PROGRESS_DIR)}\\*.json' -Destination '{ps_escape(SHARE_PROGRESS_DIR)}' "
                    f"-Force -ErrorAction SilentlyContinue; "
                    f"Copy-Item -Path '{ps_escape(SHARE_PROGRESS_DIR)}\\*.json' -Destination '{ps_escape(LOCAL_CACHE_DIR)}' "
                    f"-Force -ErrorAction SilentlyContinue; "
                    f"",
                    timeout=15
                )
                # roster.json, admin_log.json, and admins.json all use convergent
                # union merge (not newest-wins) so two admins never clobber each other.
                for _fn, _mrg, _def in (
                    ("roster.json", merge_roster, {"people": [], "removed": []}),
                    ("admin_log.json", merge_log, {"entries": []}),
                    ("admins.json", merge_admins, {}),
                ):
                    _lp = os.path.join(STATE, _fn)
                    _sp = os.path.join(share_root, _fn)
                    _merged = _mrg(load_json_file(_lp, _def), load_json_file(_sp, _def))
                    save_json_file(_lp, _merged)
                    save_json_file(_sp, _merged)
                _sync_state["last_sync"] = time.time()
            except Exception:  # noqa: S110 -- sync failure is non-fatal, no logger available
                pass
        _sync_state["syncing"] = False
        persist_sync_state()
        return dict(_sync_state)

def start_background_sync():
    def loop():
        while True:
            with contextlib.suppress(Exception):
                sync_all()
            time.sleep(SYNC_INTERVAL_SEC)
    t = threading.Thread(target=loop, daemon=True)
    t.start()

def ps_escape(p):
    """Escape single quotes in paths used inside PowerShell single-quoted strings."""
    return (p or '').replace("'", "''")

def slugify_name(s):
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "unknown"

import hashlib
import secrets as _secrets

ADMIN_USERS_FILE = os.path.join(STATE, "admins.json")
ADMIN_ROSTER_FILE = os.path.join(STATE, "roster.json")
ADMIN_LOG_FILE = os.path.join(STATE, "admin_log.json")
_SESSION_TTL = 8 * 3600
_sessions = {}
_login_attempts = {}  # {username_lower: {'count': int, 'lock_until': float}}

def _check_rate_limit(username):
    key = (username or '').lower()
    rec = _login_attempts.get(key, {})
    return time.time() >= rec.get('lock_until', 0)

def _record_failure(username):
    key = (username or '').lower()
    rec = _login_attempts.get(key, {'count': 0, 'lock_until': 0})
    rec['count'] = rec.get('count', 0) + 1
    if rec['count'] >= 5:
        rec['lock_until'] = time.time() + 30
        rec['count'] = 0
    _login_attempts[key] = rec

def _clear_attempts(username):
    _login_attempts.pop((username or '').lower(), None)

_DEFAULT_ADMIN_USERS = '{"souyackg": {"salt": "d9d29dd4986f759711a9c1265832eac9", "hash": "2f7c7e53369631faffc1180580c8d36c16a7502e4bc1f0ad2b5b8c255da26563"}, "yeowilli": {"salt": "32921696503980b07ec0bf27f9fd0c43", "hash": "7c70ef1ce62bb9ca9da534c8e3eab14732646a66db47b585b0b68552185dce33"}, "admin": {"salt": "b9b4bc5f5628d47cb662e34eb62c1b08", "hash": "2671481a87afd66cc56dbad7aec9436cb676026622cd618d09d6876242d5136b"}, "billy": {"salt": "a73d9ccd45949f4935b92c9bc05b0847", "hash": "d012ca98d60a8f201a08a1e5ccee54480b6794d0e3cf183433950522757e1d04"}}'

def hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 100000).hex()

def load_json_file(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json_file(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
    except Exception:
        return False
    else:
        return True

def merge_roster(a, b):
    """Convergent union merge for roster.json across admins.
    People are unioned by name (newest ts wins); removals are tombstoned so a
    delete on one machine is not resurrected by another machine's stale copy."""
    a = a or {}
    b = b or {}
    def people_idx(d):
        idx = {}
        for pr in d.get("people", []):
            idx[pr.get("name", "").lower()] = pr
        return idx
    pa, pb = people_idx(a), people_idx(b)
    merged = {}
    for k in set(pa) | set(pb):
        cands = [x for x in (pa.get(k), pb.get(k)) if x]
        merged[k] = max(cands, key=lambda pr: pr.get("ts", 0))
    def tomb_idx(d):
        idx = {}
        for t in d.get("removed", []):
            k = t.get("name", "").lower()
            idx[k] = max(idx.get(k, 0), t.get("ts", 0))
        return idx
    ta, tb = tomb_idx(a), tomb_idx(b)
    tombs = {}
    for k in set(ta) | set(tb):
        tombs[k] = max(ta.get(k, 0), tb.get(k, 0))
    people = [pr for k, pr in merged.items()
              if not (k in tombs and tombs[k] >= pr.get("ts", 0))]
    removed = [{"name": k, "ts": v} for k, v in tombs.items()]
    return {"people": sorted(people, key=lambda pr: pr.get("name", "").lower()),
            "removed": removed}

def merge_log(a, b):
    """Union of admin_log entries (dedup on ts/user/action/detail), newest 500."""
    seen = set()
    out = []
    for d in (a or {}, b or {}):
        for e in d.get("entries", []):
            key = (e.get("ts"), e.get("user"), e.get("action"), e.get("detail"))
            if key not in seen:
                seen.add(key)
                out.append(e)
    out.sort(key=lambda e: e.get("ts", 0))
    return {"entries": out[-500:]}

def merge_admins(a, b):
    """Convergent union merge for admins.json.
    Keeps ALL users from both sides so adding a user on two different machines
    never silently drops the other's entry.  Per-user content from (a) wins on
    conflict because (a) is always the local copy, which is the authority."""
    merged = dict(b or {})
    merged.update(a or {})   # local (a) wins same-key conflict
    return merged

def ensure_admin_files():
    ensure_local_dirs()
    if not os.path.exists(ADMIN_USERS_FILE):
        save_json_file(ADMIN_USERS_FILE, json.loads(_DEFAULT_ADMIN_USERS))
    if not os.path.exists(ADMIN_ROSTER_FILE):
        save_json_file(ADMIN_ROSTER_FILE, {"people": []})
    if not os.path.exists(ADMIN_LOG_FILE):
        save_json_file(ADMIN_LOG_FILE, {"entries": []})

def log_admin_action(username, action, detail):
    with _file_lock:
        log = load_json_file(ADMIN_LOG_FILE, {"entries": []})
        log.setdefault("entries", []).append({
            "ts": time.time(), "user": username, "action": action,
            "detail": str(detail or '')[:256]
        })
        log["entries"] = log["entries"][-500:]
        save_json_file(ADMIN_LOG_FILE, log)

def check_login(username, password):
    users = load_json_file(ADMIN_USERS_FILE, {})
    u = users.get(username) or users.get((username or '').lower())
    if not u or 'salt' not in u or 'hash' not in u:
        return False
    return hmac.compare_digest(hash_password(password, u["salt"]), u["hash"])

def create_session(username):
    # Evict oldest session if cap reached (prevents login-spam memory growth)
    if len(_sessions) >= 100:
        oldest = min(_sessions, key=lambda t: _sessions[t].get('expires', 0))
        _sessions.pop(oldest, None)
    token = _secrets.token_urlsafe(24)
    _sessions[token] = {"user": username, "expires": time.time() + _SESSION_TTL}
    return token

def verify_session(token):
    s = _sessions.get(token)
    if not s:
        return None
    if time.time() > s["expires"]:
        _sessions.pop(token, None)
        return None
    return s["user"]


def ensure_profile():
    """Install the constrained onboarding profile into the local Aki if missing."""
    if not os.path.exists(AKI):
        return
    prof = os.path.join(os.path.expanduser("~"), ".aki", "profiles_v3", PROFILE)
    if os.path.isdir(prof):
        return
    src = os.path.join(DEST, "profile", PROFILE)
    if not os.path.isdir(src):
        return
    with contextlib.suppress(Exception):
        subprocess.run(  # noqa: S603
            [AKI, "profile", "install", src], timeout=90,
            capture_output=True, text=True, check=False)

def open_url(url):
    for path in CHROME_PATHS:
        if os.path.exists(path):
            subprocess.Popen([path, url])  # noqa: S603
            return
    print(f"Chrome not found. Open manually: {url}")

def _safe_url(u):
    """Only allow http/https URLs to reach open_url (prevents file://, javascript:, etc.)."""
    return isinstance(u, str) and u.startswith(("http://", "https://"))


def safe(fn):
    with contextlib.suppress(Exception):
        fn()

CMDS = {
    "openfile": lambda p: (safe(lambda: os.startfile(p)), "Opened file."),  # noqa: S606
    "openurl":  lambda u: (safe(lambda: open_url(u)), "Opened in browser.") if _safe_url(u) else (None, "Blocked: URL must use http:// or https://."),
}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        p = parsed.path
        qs = parse_qs(parsed.query)
        token = (qs.get('token') or [''])[0]
        if p in ('/','/index.html'):
            self._file(os.path.join(DEST,'index.html'),'text/html; charset=utf-8')
        elif p == '/api/progress':
            self._list_progress()
        elif p == '/api/sync-status':
            self._json(200, dict(_sync_state))
        elif p == '/api/admin/roster':
            self._admin_get_roster(token)
        elif p == '/api/admin/log':
            self._admin_get_log(token)
        else:
            self._json(404,{'error':'not found'})

    def do_POST(self):  # noqa: C901 -- dispatch handler complexity is inherent
        try:
            n  = int(self.headers.get('Content-Length',0) or 0)
            MAX_BODY = 512 * 1024
            if n > MAX_BODY:
                return self._json(413, {'error': 'request too large'})
            bd = json.loads(self.rfile.read(n) or '{}')
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {'error': 'bad request'})
        if   self.path=='/api/ping':
            _last_ping[0] = time.time()
            _page_seen[0] = True
            return self._json(200, {'ok': True})
        if   self.path=='/api/shutdown':
            if not self._require_admin(bd.get('token','')):
                return self._json(401, {'ok': False, 'error': 'Not authenticated'})
            self._json(200, {'ok': True})
            self.wfile.flush()
            os._exit(0)
        if self.path == '/api/message':
            return self._msg(bd.get('message', ''))
        if self.path == '/api/command':
            return self._cmd(bd.get('action', ''), bd.get('arg', ''))
        if self.path == '/api/progress':
            return self._save_progress(bd)
        if self.path == '/api/sync-now':
            return self._sync_now()
        if self.path == '/api/admin/login':
            return self._admin_login(bd)
        if self.path == '/api/admin/logout':
            return self._admin_logout(bd)
        if self.path == '/api/admin/change-password':
            return self._admin_change_password(bd)
        if self.path == '/api/admin/roster/add':
            return self._admin_roster_add(bd)
        if self.path == '/api/admin/roster/remove':
            return self._admin_roster_remove(bd)
        if self.path == '/api/admin/user/edit':
            return self._admin_user_edit(bd)
        if self.path == '/api/admin/user/delete':
            return self._admin_user_delete(bd)
        return self._json(404, {'error': 'not found'})

    def _msg(self, msg):
        if not msg:
            return self._json(400, {'error': 'empty'})
        MAX_MSG_LEN = 2000
        if len(msg) > MAX_MSG_LEN:
            return self._json(400, {'error': f'Message too long (max {MAX_MSG_LEN} characters)'})
        if not os.path.exists(AKI):
            return self._json(200, {'response':
                "The AI assistant needs the Aki app, which isn't installed on this PC. "
                "Everything else works without it: use the checklist, the Resources and "
                "Quick Links buttons, and the phase guides. To get Aki, see the AI Tools "
                "section of your onboarding checklist or ask RME (SOUYACKG).",
                'type': 'ai'})
        try:
            r = subprocess.run(  # noqa: S603
                [AKI, '--cli', '-p', PROFILE, msg],
                               capture_output=True, text=True, timeout=120,
                               encoding='utf-8', errors='replace', check=False)
            resp = r.stdout.strip() or r.stderr.strip() or '(no response)'
        except subprocess.TimeoutExpired:
            resp = 'Request timed out.'
        except Exception as e:
            resp = f'Error: {e}'
        return self._json(200, {'response': resp, 'type': 'ai'})

    def _cmd(self, action, arg):
        fn = CMDS.get(action)
        if not fn:
            return self._json(400, {'response': f'Unknown: {action}', 'type': 'command'})
        try:
            res = fn(arg)
            msg = res[1] if isinstance(res,tuple) and len(res)>1 else 'Done.'
        except Exception as e:
            msg = f'Error: {e}'
        return self._json(200, {'response': msg, 'type': 'command'})

    def _save_progress(self, bd):
        name = (bd.get('name') or '').strip()
        if not name:
            return self._json(400, {'ok': False, 'error': 'no name'})
        ensure_local_dirs()
        raw_checked = bd.get('checked') or []
        if not isinstance(raw_checked, list):
            raw_checked = []
        def _to_int(v, lo=None, hi=None):
            try:
                n = int(v or 0)
            except (TypeError, ValueError):
                n = 0
            if lo is not None:
                n = max(lo, n)
            if hi is not None:
                n = min(hi, n)
            return n
        clean = {
            'name':    name[:60],
            'role':    str(bd.get('role') or '')[:20],
            'start':   str(bd.get('start') or '')[:12],
            'done':    _to_int(bd.get('done'), lo=0),
            'total':   _to_int(bd.get('total'), lo=0),
            'pct':     _to_int(bd.get('pct'), lo=0, hi=100),
            'checked': [str(x)[:20] for x in raw_checked[:100]],
            'ts':      time.time(),
        }
        fn = os.path.join(LOCAL_PROGRESS_DIR, slugify_name(name[:60]) + '.json')
        try:
            with _file_lock, open(fn, 'w', encoding='utf-8') as f:
                json.dump(clean, f)
        except Exception as e:
            return self._json(200, {'ok': False, 'error': str(e)})
        threading.Thread(target=sync_all, daemon=True).start()
        return self._json(200, {'ok': True})

    def _list_progress(self):
        # Reads local + cached-from-share files only -- instant, never blocks
        # on the network. Background thread + Sync Now button keep the
        # cache fresh whenever the share is reachable.
        ensure_local_dirs()
        people = []
        seen = set()
        for d in (LOCAL_PROGRESS_DIR, LOCAL_CACHE_DIR):
            if os.path.isdir(d):
                for fn in os.listdir(d):
                    if fn.endswith('.json') and fn not in seen:
                        seen.add(fn)
                        with contextlib.suppress(Exception), open(os.path.join(d, fn), encoding='utf-8') as f:
                            people.append(json.load(f))
        self._json(200, {'people': people})

    def _sync_now(self):
        result = sync_all(manual=True)
        self._json(200, result)

    def _require_admin(self, token):
        return verify_session(token)

    def _admin_login(self, bd):
        ensure_admin_files()
        username = (bd.get('username') or '').strip()
        password = bd.get('password') or ''
        if not _check_rate_limit(username):
            return self._json(200, {'ok': False, 'error': 'Too many failed attempts. Try again in 30 seconds.'})
        if check_login(username, password):
            _clear_attempts(username)
            token = create_session(username)
            log_admin_action(username, 'login', '')
            return self._json(200, {'ok': True, 'token': token, 'user': username})
        _record_failure(username)
        return self._json(200, {'ok': False, 'error': 'Invalid username or password'})

    def _admin_logout(self, bd):
        token = bd.get('token') or ''
        _sessions.pop(token, None)
        return self._json(200, {'ok': True})

    def _admin_change_password(self, bd):
        token = bd.get('token') or ''
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        new_pw = bd.get('new_password') or ''
        if len(new_pw) < 6:
            return self._json(200, {'ok': False, 'error': 'Password must be at least 6 characters'})
        with _file_lock:
            users = load_json_file(ADMIN_USERS_FILE, {})
            salt = _secrets.token_hex(16)
            users[user] = {'salt': salt, 'hash': hash_password(new_pw, salt)}
            save_json_file(ADMIN_USERS_FILE, users)
        log_admin_action(user, 'change_password', '')
        threading.Thread(target=sync_all, daemon=True).start()
        return self._json(200, {'ok': True})

    def _admin_get_roster(self, token):
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        ensure_admin_files()
        roster = load_json_file(ADMIN_ROSTER_FILE, {'people': []})
        return self._json(200, roster)

    def _admin_roster_add(self, bd):
        token = bd.get('token') or ''
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        name = (bd.get('name') or '').strip()
        role = bd.get('role') or 'both'
        if not name:
            return self._json(200, {'ok': False, 'error': 'Name required'})
        with _file_lock:
            roster = load_json_file(ADMIN_ROSTER_FILE, {'people': []})
            roster.setdefault('people', [])
            roster.setdefault('removed', [])
            roster['people'] = [p for p in roster['people'] if p.get('name','').lower() != name.lower()]
            roster['removed'] = [t for t in roster['removed'] if t.get('name','').lower() != name.lower()]
            roster['people'].append({'name': name, 'role': role, 'added_by': user, 'ts': time.time()})
            save_json_file(ADMIN_ROSTER_FILE, roster)
        log_admin_action(user, 'roster_add', name)
        threading.Thread(target=sync_all, daemon=True).start()
        return self._json(200, {'ok': True})

    def _admin_roster_remove(self, bd):
        token = bd.get('token') or ''
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        name = (bd.get('name') or '').strip()
        if not name:
            return self._json(200, {'ok': False, 'error': 'name required'})
        with _file_lock:
            roster = load_json_file(ADMIN_ROSTER_FILE, {'people': []})
            roster.setdefault('people', [])
            roster.setdefault('removed', [])
            roster['people'] = [p for p in roster['people'] if p.get('name','').lower() != name.lower()]
            roster['removed'] = [t for t in roster['removed'] if t.get('name','').lower() != name.lower()]
            roster['removed'].append({'name': name.lower(), 'ts': time.time()})
            save_json_file(ADMIN_ROSTER_FILE, roster)
        log_admin_action(user, 'roster_remove', name)
        threading.Thread(target=sync_all, daemon=True).start()
        return self._json(200, {'ok': True})

    def _admin_user_edit(self, bd):  # noqa: C901 -- field-validation handler
        token = bd.get('token') or ''
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        old_name = (bd.get('old_name') or '').strip()
        new_name = ((bd.get('new_name') or '').strip() or old_name)[:60]
        new_role = str(bd.get('new_role') or '')[:20] or None
        if not old_name:
            return self._json(200, {'ok': False, 'error': 'old_name required'})
        old_fn = os.path.join(LOCAL_PROGRESS_DIR, slugify_name(old_name) + '.json')
        cache_fn = os.path.join(LOCAL_CACHE_DIR, slugify_name(old_name) + '.json')
        data = None
        for fn in (old_fn, cache_fn):
            if os.path.exists(fn):
                data = load_json_file(fn, None)
                break
        if data is None:
            return self._json(200, {'ok': False, 'error': 'User progress file not found'})
        if not isinstance(data, dict):
            return self._json(200, {'ok': False, 'error': 'Progress file is corrupt (not a JSON object)'})
        with _file_lock:
            data['name'] = new_name
            if new_role:
                data['role'] = new_role
            data['ts'] = time.time()
            new_fn = os.path.join(LOCAL_PROGRESS_DIR, slugify_name(new_name) + '.json')
            save_json_file(new_fn, data)
            if slugify_name(new_name) != slugify_name(old_name):
                for fn in (old_fn, cache_fn):
                    with contextlib.suppress(Exception):
                        if os.path.exists(fn):
                            os.remove(fn)
        log_admin_action(user, 'user_edit', f'{old_name} -> {new_name}')
        threading.Thread(target=sync_all, daemon=True).start()
        return self._json(200, {'ok': True})

    def _admin_user_delete(self, bd):
        token = bd.get('token') or ''
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        name = (bd.get('name') or '').strip()
        if not name:
            return self._json(200, {'ok': False, 'error': 'name required'})
        removed = False
        with _file_lock:
            for d in (LOCAL_PROGRESS_DIR, LOCAL_CACHE_DIR):
                fn = os.path.join(d, slugify_name(name[:60]) + '.json')
                if os.path.exists(fn):
                    with contextlib.suppress(Exception):
                        os.remove(fn)
                        removed = True
        log_admin_action(user, 'user_delete', name)
        threading.Thread(target=sync_all, daemon=True).start()
        return self._json(200, {'ok': removed})

    def _admin_get_log(self, token):
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        log = load_json_file(ADMIN_LOG_FILE, {'entries': []})
        return self._json(200, log)


    def _sec_headers(self):
        """Emit security headers on every response."""
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        # CSP: self-hosted only; inline scripts/styles required by the single-file app.
        self.send_header(
            'Content-Security-Policy',
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "object-src 'none'"
        )

    def _file(self, path, ct):
        try:
            with open(path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', len(data))
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self._sec_headers()
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._json(404, {'error': 'file not found'})

    def _json(self, code, obj):
        data = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', len(data))
        self._sec_headers()
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a): pass

if __name__ == '__main__':
    ensure_local_dirs()
    ensure_profile()
    load_sync_state()
    start_background_sync()
    start_shutdown_watchdog()
    url = f'http://127.0.0.1:{PORT}'
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print(f'ACY1 RME Onboarding Agent  ->  {url}')
    threading.Timer(0.8, lambda: open_url(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Stopped.')
