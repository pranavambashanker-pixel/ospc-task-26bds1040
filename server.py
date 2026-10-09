"""Kraut Corner: static site + SQLite sign-up backend. Python 3.8+ standard library only.

Everything lives in this one folder. Run it with start.bat (Windows) or ./start.sh (Mac/Linux),
or:  python server.py   ->  http://localhost:8000

Data (all inside ./data):
  signups.db         the SQLite database (WAL mode, crash-safe)
  signups.csv        a spreadsheet copy, rewritten after every sign-up
  backups/           a timestamped database copy made at every start
  admin_token.txt    key for the admin page (auto-created, or set ADMIN_TOKEN)
Env vars (optional): PORT (8000), DATA_DIR, ADMIN_TOKEN
"""
import csv, hmac, json, os, re, secrets, sqlite3, threading, time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / "public"
DATA = Path(os.environ.get("DATA_DIR", HERE / "data"))
DB_PATH = DATA / "signups.db"
CSV_PATH = DATA / "signups.csv"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
KINDS = {"Get the fan digest", "Suggest a video topic", "Share a favourite video"}
MAX_BODY = 4096
RATE, LOCK = {}, threading.Lock()


def db():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=10000")
    return con


def init():
    DATA.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("""CREATE TABLE IF NOT EXISTS signups(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL, message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
    # startup backup (keeps the 20 newest)
    bdir = DATA / "backups"
    bdir.mkdir(exist_ok=True)
    dest = bdir / f"signups-{datetime.now():%Y%m%d-%H%M%S}.db"
    src, dst = db(), sqlite3.connect(dest)
    src.backup(dst)
    src.close(); dst.close()
    for old in sorted(bdir.glob("signups-*.db"))[:-20]:
        old.unlink()
    write_csv()


def write_csv():
    with db() as con:
        rows = con.execute("SELECT id,name,email,kind,message,created_at FROM signups ORDER BY id").fetchall()
    tmp = CSV_PATH.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "email", "kind", "message", "created_at"])
        w.writerows([tuple(r) for r in rows])
    os.replace(tmp, CSV_PATH)  # atomic: never leaves a half-written file


def admin_token():
    t = os.environ.get("ADMIN_TOKEN")
    if t:
        return t
    f = DATA / "admin_token.txt"
    if not f.exists():
        f.write_text(secrets.token_urlsafe(18))
    return f.read_text().strip()


TOKEN = ""


def limited(ip):
    now = time.time()
    hits = [t for t in RATE.get(ip, []) if now - t < 60] + [now]
    RATE[ip] = hits
    return len(hits) > 8


ADMIN_HTML = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Sign-ups</title><style>body{font:16px system-ui;margin:24px;max-width:1000px}table{border-collapse:collapse;width:100%%}
td,th{border:1px solid #ccc;padding:6px 10px;text-align:left;vertical-align:top}th{background:#eee}a{margin-right:12px}</style>
<h1>Sign-ups (%d)</h1><p><a href="/api/signups.csv?token=%s">Download CSV</a></p><table><tr><th>#<th>Name<th>Email<th>Type<th>Message<th>When (UTC)</tr>%s</table>"""


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class Handler(BaseHTTPRequestHandler):
    server_version = "KrautCorner"

    def _send(self, code, body=b"", ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode(), extra={"Cache-Control": "no-store"})

    def _authed(self, query):
        supplied = self.headers.get("Authorization", "").replace("Bearer ", "", 1)
        m = re.search(r"(?:^|&)token=([^&]+)", query)
        supplied = supplied or (m.group(1) if m else "")
        return hmac.compare_digest(supplied, TOKEN)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path in ("/", "/index.html"):
            return self._send(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8",
                              {"Cache-Control": "no-cache"})
        if path == "/healthz":
            return self._json(200, {"ok": True})
        if path in ("/admin", "/api/signups", "/api/signups.csv"):
            if not self._authed(query):
                return self._json(401, {"ok": False, "error": "unauthorized"})
            with db() as con:
                rows = [dict(r) for r in con.execute("SELECT * FROM signups ORDER BY id DESC")]
            if path == "/api/signups":
                return self._json(200, {"ok": True, "count": len(rows), "signups": rows})
            if path == "/api/signups.csv":
                return self._send(200, CSV_PATH.read_bytes(), "text/csv; charset=utf-8",
                                  {"Content-Disposition": "attachment; filename=signups.csv"})
            body = "".join("<tr>" + "".join(f"<td>{esc(r[k])}" for k in
                           ("id", "name", "email", "kind", "message", "created_at")) + "</tr>" for r in rows)
            m = re.search(r"token=([^&]+)", query)
            return self._send(200, (ADMIN_HTML % (len(rows), esc(m.group(1) if m else ""), body)).encode(),
                              "text/html; charset=utf-8", {"Cache-Control": "no-store"})
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path.split("?")[0] != "/api/signup":
            return self._json(404, {"ok": False, "error": "not found"})
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        if limited(ip):
            return self._json(429, {"ok": False, "error": "too many requests"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= MAX_BODY:
                raise ValueError
            data = json.loads(self.rfile.read(n))
            name = str(data.get("name", "")).strip()[:100]
            email = str(data.get("email", "")).strip().lower()[:254]
            kind = str(data.get("kind", ""))
            message = str(data.get("message", "")).strip()[:500]
        except (ValueError, TypeError, AttributeError):
            return self._json(400, {"ok": False, "error": "invalid request"})
        if not name or not EMAIL_RE.match(email) or kind not in KINDS:
            return self._json(422, {"ok": False, "error": "invalid fields"})
        try:
            with LOCK:
                with db() as con:
                    con.execute("""INSERT INTO signups(name,email,kind,message) VALUES(?,?,?,?)
                        ON CONFLICT(email) DO UPDATE SET name=excluded.name, kind=excluded.kind,
                        message=excluded.message""", (name, email, kind, message))
                write_csv()
        except Exception:
            return self._json(500, {"ok": False, "error": "could not save"})
        self._json(201, {"ok": True})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    init()
    TOKEN = admin_token()
    port = int(os.environ.get("PORT", "8000"))
    print(f"\n  Kraut Corner is running:  http://localhost:{port}")
    print(f"  Admin page:               http://localhost:{port}/admin?token={TOKEN}")
    print(f"  Data folder:              {DATA}\n  (Press Ctrl+C to stop)\n")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
