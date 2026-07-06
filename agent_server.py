"""ACY1 RME Onboarding Agent - HTTP Server (port 5901)"""
import threading, subprocess, json, os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PORT   = 5901
DEST   = os.path.dirname(os.path.abspath(__file__))
AKI    = r"C:\Users\souyackg\.aki\bin\aki.cmd"
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

import re, time

SHARE_PROGRESS_DIR = r"\\ant\dept-na\ACY1\Support\RME\Onboarding Agent\progress"
LOCAL_PROGRESS_DIR = os.path.join(DEST, "progress")
LOCAL_CACHE_DIR     = os.path.join(DEST, "progress_cache")
SYNC_STATE_FILE     = os.path.join(DEST, "sync_state.json")
SYNC_INTERVAL_SEC   = 30

_sync_lock = threading.Lock()
_sync_state = {"connected": False, "last_sync": None, "last_attempt": None, "syncing": False}

def ensure_local_dirs():
    for d in (LOCAL_PROGRESS_DIR, LOCAL_CACHE_DIR):
        try: os.makedirs(d, exist_ok=True)
        except Exception: pass

def load_sync_state():
    global _sync_state
    try:
        with open(SYNC_STATE_FILE, encoding="utf-8") as f:
            _sync_state.update(json.load(f))
    except Exception:
        pass

def persist_sync_state():
    try:
        with open(SYNC_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(_sync_state, f)
    except Exception:
        pass

def run_ps(cmd, timeout=6):
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return r.returncode == 0, r.stdout, r.stderr
    except Exception as e:
        return False, "", str(e)

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
                    f"New-Item -ItemType Directory -Path '{SHARE_PROGRESS_DIR}' -Force "
                    f"-ErrorAction SilentlyContinue | Out-Null; "
                    f"Copy-Item -Path '{LOCAL_PROGRESS_DIR}\\*.json' -Destination '{SHARE_PROGRESS_DIR}' "
                    f"-Force -ErrorAction SilentlyContinue; "
                    f"Copy-Item -Path '{SHARE_PROGRESS_DIR}\\*.json' -Destination '{LOCAL_CACHE_DIR}' "
                    f"-Force -ErrorAction SilentlyContinue; "
                    f"foreach ($f in @('admins.json','roster.json','admin_log.json')) {{ "
                    f"if (Test-Path (Join-Path '{DEST}' $f)) {{ Copy-Item -Path (Join-Path '{DEST}' $f) "
                    f"-Destination (Join-Path '{share_root}' $f) -Force -ErrorAction SilentlyContinue }} "
                    f"if (Test-Path (Join-Path '{share_root}' $f)) {{ "
                    f"$localTime = if (Test-Path (Join-Path '{DEST}' $f)) {{ (Get-Item (Join-Path '{DEST}' $f)).LastWriteTimeUtc }} else {{ [DateTime]::MinValue }}; "
                    f"$shareTime = (Get-Item (Join-Path '{share_root}' $f)).LastWriteTimeUtc; "
                    f"if ($shareTime -gt $localTime) {{ Copy-Item -Path (Join-Path '{share_root}' $f) "
                    f"-Destination (Join-Path '{DEST}' $f) -Force -ErrorAction SilentlyContinue }} }} }}",
                    timeout=15
                )
                _sync_state["last_sync"] = time.time()
            except Exception:
                pass
        _sync_state["syncing"] = False
        persist_sync_state()
        return dict(_sync_state)

def start_background_sync():
    def loop():
        while True:
            try: sync_all()
            except Exception: pass
            time.sleep(SYNC_INTERVAL_SEC)
    t = threading.Thread(target=loop, daemon=True)
    t.start()

def slugify_name(s):
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "unknown"

import hashlib, secrets as _secrets

ADMIN_USERS_FILE = os.path.join(DEST, "admins.json")
ADMIN_ROSTER_FILE = os.path.join(DEST, "roster.json")
ADMIN_LOG_FILE = os.path.join(DEST, "admin_log.json")
_SESSION_TTL = 8 * 3600
_sessions = {}

_DEFAULT_ADMIN_USERS = '{"souyackg": {"salt": "d9d29dd4986f759711a9c1265832eac9", "hash": "2f7c7e53369631faffc1180580c8d36c16a7502e4bc1f0ad2b5b8c255da26563"}, "yeowilli": {"salt": "32921696503980b07ec0bf27f9fd0c43", "hash": "7c70ef1ce62bb9ca9da534c8e3eab14732646a66db47b585b0b68552185dce33"}, "admin": {"salt": "b9b4bc5f5628d47cb662e34eb62c1b08", "hash": "2671481a87afd66cc56dbad7aec9436cb676026622cd618d09d6876242d5136b"}}'

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
        return True
    except Exception:
        return False

def ensure_admin_files():
    ensure_local_dirs()
    if not os.path.exists(ADMIN_USERS_FILE):
        save_json_file(ADMIN_USERS_FILE, json.loads(_DEFAULT_ADMIN_USERS))
    if not os.path.exists(ADMIN_ROSTER_FILE):
        save_json_file(ADMIN_ROSTER_FILE, {"people": []})
    if not os.path.exists(ADMIN_LOG_FILE):
        save_json_file(ADMIN_LOG_FILE, {"entries": []})

def log_admin_action(username, action, detail):
    log = load_json_file(ADMIN_LOG_FILE, {"entries": []})
    log.setdefault("entries", []).append({
        "ts": time.time(), "user": username, "action": action, "detail": detail
    })
    log["entries"] = log["entries"][-500:]
    save_json_file(ADMIN_LOG_FILE, log)

def check_login(username, password):
    users = load_json_file(ADMIN_USERS_FILE, {})
    u = users.get(username)
    if not u:
        return False
    return hash_password(password, u["salt"]) == u["hash"]

def create_session(username):
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


CTX = (
    "You are the ACY1 RME Onboarding Agent helping a new RME technician at ACY1, "
    "an Amazon fulfillment center in West Deptford NJ managed by CBRE. "
    "RME = Reliability Maintenance Engineering. "
    "Training uses the TAC system: TAC 101 (awareness), 201 (proficiency), 301 (expert). "
    "Core 4 equipment: Mechanical Conveyor, Electrical Conveyor, Control Cabinets, Shop Tools. "
    "APM = HxGN EAM work order system. A to Z = Amazon internal training portal. "
    "Key safety: LOTO, Arc Flash, PPE, Hot Work, Confined Space, Machine Safeguarding. "
    "VFDs on site: Eaton SVX/SPX. MDRs: 24VDC ConveyLinx. Motors: 9-lead 480V 3-phase. "
    "Be helpful, encouraging, and practical. Answer questions clearly and concisely.\n\nUser: "
)

def open_url(url):
    for path in CHROME_PATHS:
        if os.path.exists(path):
            subprocess.Popen([path, url])
            return
    print(f"Chrome not found. Open manually: {url}")

def safe(fn):
    try: fn()
    except: pass

CMDS = {
    "openfile": lambda p: (safe(lambda: os.startfile(p)), "Opened file."),
    "openurl":  lambda u: (safe(lambda: open_url(u)),     "Opened in browser."),
}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import parse_qs
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

    def do_POST(self):
        n  = int(self.headers.get('Content-Length',0))
        bd = json.loads(self.rfile.read(n) or '{}')
        if   self.path=='/api/message':   self._msg(bd.get('message',''))
        elif self.path=='/api/command':   self._cmd(bd.get('action',''),bd.get('arg',''))
        elif self.path=='/api/progress':  self._save_progress(bd)
        elif self.path=='/api/sync-now':  self._sync_now()
        elif self.path=='/api/admin/login':          self._admin_login(bd)
        elif self.path=='/api/admin/logout':         self._admin_logout(bd)
        elif self.path=='/api/admin/change-password':self._admin_change_password(bd)
        elif self.path=='/api/admin/roster/add':     self._admin_roster_add(bd)
        elif self.path=='/api/admin/roster/remove':  self._admin_roster_remove(bd)
        elif self.path=='/api/admin/user/edit':      self._admin_user_edit(bd)
        elif self.path=='/api/admin/user/delete':    self._admin_user_delete(bd)
        else: self._json(404,{'error':'not found'})

    def _msg(self, msg):
        if not msg: return self._json(400,{'error':'empty'})
        try:
            r = subprocess.run([AKI,'--cli', CTX+msg],
                               capture_output=True, text=True, timeout=120,
                               encoding='utf-8', errors='replace')
            resp = r.stdout.strip() or r.stderr.strip() or '(no response)'
        except subprocess.TimeoutExpired: resp = 'Request timed out.'
        except Exception as e:           resp = f'Error: {e}'
        self._json(200, {'response': resp, 'type': 'ai'})

    def _cmd(self, action, arg):
        fn = CMDS.get(action)
        if not fn: return self._json(400,{'response':f'Unknown: {action}','type':'command'})
        try:
            res = fn(arg)
            msg = res[1] if isinstance(res,tuple) and len(res)>1 else 'Done.'
        except Exception as e: msg = f'Error: {e}'
        self._json(200, {'response': msg, 'type': 'command'})

    def _save_progress(self, bd):
        name = (bd.get('name') or '').strip()
        if not name:
            return self._json(400, {'ok': False, 'error': 'no name'})
        ensure_local_dirs()
        bd['ts'] = time.time()
        fn = os.path.join(LOCAL_PROGRESS_DIR, slugify_name(name) + '.json')
        try:
            with open(fn, 'w', encoding='utf-8') as f:
                json.dump(bd, f)
        except Exception as e:
            return self._json(200, {'ok': False, 'error': str(e)})
        threading.Thread(target=sync_all, daemon=True).start()
        self._json(200, {'ok': True})

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
                        try:
                            with open(os.path.join(d, fn), encoding='utf-8') as f:
                                people.append(json.load(f))
                        except Exception:
                            pass
        self._json(200, {'people': people})

    def _sync_now(self):
        result = sync_all(manual=True)
        self._json(200, result)

    def _require_admin(self, token):
        user = verify_session(token)
        return user

    def _admin_login(self, bd):
        ensure_admin_files()
        username = (bd.get('username') or '').strip()
        password = bd.get('password') or ''
        if check_login(username, password):
            token = create_session(username)
            log_admin_action(username, 'login', '')
            self._json(200, {'ok': True, 'token': token, 'user': username})
        else:
            self._json(200, {'ok': False, 'error': 'Invalid username or password'})

    def _admin_logout(self, bd):
        token = bd.get('token') or ''
        _sessions.pop(token, None)
        self._json(200, {'ok': True})

    def _admin_change_password(self, bd):
        token = bd.get('token') or ''
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        new_pw = bd.get('new_password') or ''
        if len(new_pw) < 6:
            return self._json(200, {'ok': False, 'error': 'Password must be at least 6 characters'})
        users = load_json_file(ADMIN_USERS_FILE, {})
        salt = _secrets.token_hex(16)
        users[user] = {'salt': salt, 'hash': hash_password(new_pw, salt)}
        save_json_file(ADMIN_USERS_FILE, users)
        log_admin_action(user, 'change_password', '')
        threading.Thread(target=sync_all, daemon=True).start()
        self._json(200, {'ok': True})

    def _admin_get_roster(self, token):
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        ensure_admin_files()
        roster = load_json_file(ADMIN_ROSTER_FILE, {'people': []})
        self._json(200, roster)

    def _admin_roster_add(self, bd):
        token = bd.get('token') or ''
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        name = (bd.get('name') or '').strip()
        role = bd.get('role') or 'both'
        if not name:
            return self._json(200, {'ok': False, 'error': 'Name required'})
        roster = load_json_file(ADMIN_ROSTER_FILE, {'people': []})
        roster.setdefault('people', [])
        roster['people'] = [p for p in roster['people'] if p.get('name','').lower() != name.lower()]
        roster['people'].append({'name': name, 'role': role, 'added_by': user, 'ts': time.time()})
        save_json_file(ADMIN_ROSTER_FILE, roster)
        log_admin_action(user, 'roster_add', name)
        threading.Thread(target=sync_all, daemon=True).start()
        self._json(200, {'ok': True})

    def _admin_roster_remove(self, bd):
        token = bd.get('token') or ''
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        name = (bd.get('name') or '').strip()
        roster = load_json_file(ADMIN_ROSTER_FILE, {'people': []})
        roster.setdefault('people', [])
        roster['people'] = [p for p in roster['people'] if p.get('name','').lower() != name.lower()]
        save_json_file(ADMIN_ROSTER_FILE, roster)
        log_admin_action(user, 'roster_remove', name)
        threading.Thread(target=sync_all, daemon=True).start()
        self._json(200, {'ok': True})

    def _admin_user_edit(self, bd):
        token = bd.get('token') or ''
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        old_name = (bd.get('old_name') or '').strip()
        new_name = (bd.get('new_name') or '').strip() or old_name
        new_role = bd.get('new_role')
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
        data['name'] = new_name
        if new_role:
            data['role'] = new_role
        data['ts'] = time.time()
        new_fn = os.path.join(LOCAL_PROGRESS_DIR, slugify_name(new_name) + '.json')
        save_json_file(new_fn, data)
        if slugify_name(new_name) != slugify_name(old_name):
            for fn in (old_fn, cache_fn):
                try:
                    if os.path.exists(fn): os.remove(fn)
                except Exception: pass
        log_admin_action(user, 'user_edit', f'{old_name} -> {new_name}')
        threading.Thread(target=sync_all, daemon=True).start()
        self._json(200, {'ok': True})

    def _admin_user_delete(self, bd):
        token = bd.get('token') or ''
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        name = (bd.get('name') or '').strip()
        if not name:
            return self._json(200, {'ok': False, 'error': 'name required'})
        removed = False
        for d in (LOCAL_PROGRESS_DIR, LOCAL_CACHE_DIR):
            fn = os.path.join(d, slugify_name(name) + '.json')
            if os.path.exists(fn):
                try:
                    os.remove(fn); removed = True
                except Exception: pass
        log_admin_action(user, 'user_delete', name)
        threading.Thread(target=sync_all, daemon=True).start()
        self._json(200, {'ok': removed})

    def _admin_get_log(self, token):
        user = self._require_admin(token)
        if not user:
            return self._json(401, {'ok': False, 'error': 'Not authenticated'})
        log = load_json_file(ADMIN_LOG_FILE, {'entries': []})
        self._json(200, log)


    def _file(self, path, ct):
        try:
            with open(path,'rb') as f: data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', len(data))
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError: self._json(404,{'error':'file not found'})

    def _json(self, code, obj):
        data = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', len(data))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a): pass

if __name__ == '__main__':
    ensure_local_dirs()
    load_sync_state()
    start_background_sync()
    url = f'http://127.0.0.1:{PORT}'
    server = HTTPServer(('127.0.0.1', PORT), Handler)
    print(f'ACY1 RME Onboarding Agent  ->  {url}')
    threading.Timer(0.8, lambda: open_url(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print('Stopped.')
