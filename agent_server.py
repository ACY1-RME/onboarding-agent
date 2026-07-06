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

def ensure_local_dirs():
    for d in (LOCAL_PROGRESS_DIR, LOCAL_CACHE_DIR):
        try: os.makedirs(d, exist_ok=True)
        except Exception: pass

def run_ps(cmd, timeout=8):
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return r.returncode == 0
    except Exception:
        return False

def push_to_share(local_file):
    # Best-effort async copy of one progress file up to the network share.
    # UNC paths aren't reliably reachable via plain Python os calls in this
    # environment, but PowerShell handles them fine -- so we shell out.
    fname = os.path.basename(local_file)
    cmd = (
        f"New-Item -ItemType Directory -Path '{SHARE_PROGRESS_DIR}' -Force "
        f"-ErrorAction SilentlyContinue | Out-Null; "
        f"Copy-Item -Path '{local_file}' -Destination '{SHARE_PROGRESS_DIR}\\{fname}' "
        f"-Force -ErrorAction SilentlyContinue"
    )
    run_ps(cmd)

def pull_from_share():
    # Best-effort mirror of everyone else's progress files from the share
    # into a local cache dir so they can be read with normal Python file I/O.
    cmd = (
        f"if (Test-Path '{SHARE_PROGRESS_DIR}') {{ "
        f"Copy-Item -Path '{SHARE_PROGRESS_DIR}\\*.json' -Destination '{LOCAL_CACHE_DIR}' "
        f"-Force -ErrorAction SilentlyContinue }}"
    )
    run_ps(cmd)

def slugify_name(s):
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "unknown"

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
        p = urlparse(self.path).path
        if p in ('/','/index.html'):
            self._file(os.path.join(DEST,'index.html'),'text/html; charset=utf-8')
        elif p == '/api/progress':
            self._list_progress()
        else:
            self._json(404,{'error':'not found'})

    def do_POST(self):
        n  = int(self.headers.get('Content-Length',0))
        bd = json.loads(self.rfile.read(n) or '{}')
        if   self.path=='/api/message':   self._msg(bd.get('message',''))
        elif self.path=='/api/command':   self._cmd(bd.get('action',''),bd.get('arg',''))
        elif self.path=='/api/progress':  self._save_progress(bd)
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
        threading.Thread(target=push_to_share, args=(fn,), daemon=True).start()
        self._json(200, {'ok': True})

    def _list_progress(self):
        ensure_local_dirs()
        pull_from_share()
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

    def _file(self, path, ct):
        try:
            with open(path,'rb') as f: data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', len(data))
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
    url = f'http://127.0.0.1:{PORT}'
    server = HTTPServer(('127.0.0.1', PORT), Handler)
    print(f'ACY1 RME Onboarding Agent  ->  {url}')
    threading.Timer(0.8, lambda: open_url(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print('Stopped.')
