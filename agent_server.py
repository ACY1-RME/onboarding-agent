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
        if urlparse(self.path).path in ('/','/index.html'):
            self._file(os.path.join(DEST,'index.html'),'text/html; charset=utf-8')
        else:
            self._json(404,{'error':'not found'})

    def do_POST(self):
        n  = int(self.headers.get('Content-Length',0))
        bd = json.loads(self.rfile.read(n) or '{}')
        if   self.path=='/api/message':   self._msg(bd.get('message',''))
        elif self.path=='/api/command':   self._cmd(bd.get('action',''),bd.get('arg',''))
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
