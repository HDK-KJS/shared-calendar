"""Shared calendar: Flask + SQLite. Set SITE_PASSWORD to require a shared password; leave it unset for open access."""
import hmac
import json
import os
import sqlite3
import time
from datetime import date, datetime, timedelta
from functools import wraps
from html import escape

from flask import (Flask, Response, abort, g, jsonify, redirect, request, session,
                   send_from_directory)

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("CALENDAR_DB", os.path.join(BASE, "data", "calendar.db"))
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "")
CATS = {"Travel", "Appointment", "Visitors", "Holidays", "Work", "Other"}
NAMES = {"Kimmy", "Hugh", "Gwyn"}

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("SECRET_KEY", "")
if not app.secret_key:
    raise RuntimeError("Set the SECRET_KEY environment variable.")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # set INSECURE_COOKIES=1 only when testing locally over plain http
    SESSION_COOKIE_SECURE=os.environ.get("INSECURE_COOKIES") != "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=90),
)


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, date TEXT NOT NULL, end_date TEXT DEFAULT '',
        time TEXT DEFAULT '', color TEXT DEFAULT '', cat TEXT DEFAULT 'Other',
        notes TEXT DEFAULT '', created_by TEXT DEFAULT '', updated_at TEXT DEFAULT '')"""
    )
    have = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
    for col, ddl in (("end_date", "TEXT DEFAULT ''"), ("color", "TEXT DEFAULT ''")):
        if col not in have:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} {ddl}")
    if "cat" not in have:
        conn.execute("ALTER TABLE events ADD COLUMN cat TEXT DEFAULT 'Other'")
        # one-time: turn the old colour choices into categories
        conn.execute("""UPDATE events SET cat = CASE
            WHEN color IN ('chocolate','blue') THEN 'Travel'
            WHEN color IN ('burgundy','rose','taupe','grey') THEN 'Appointment'
            WHEN color IN ('olive','green') THEN 'Holidays'
            ELSE 'Other' END""")
    conn.commit()
    conn.close()


init_db()


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if SITE_PASSWORD and not session.get("name"):
            if request.path.startswith("/api/"):
                return jsonify(error="Not signed in"), 401
            return redirect("/login")
        return f(*a, **kw)
    return wrapper


LOGIN_PAGE = """<!DOCTYPE html><html lang="en-AU"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Shared Calendar</title>
<style>body{font:16px Georgia,serif;background:#f7f1e4;color:#3b2a24;display:grid;place-items:center;min-height:100vh;margin:0}
form{background:#fffaf0;border:1px solid #e3d6c2;border-radius:12px;padding:24px;width:min(340px,90vw)}
input,button{width:100%;font:inherit;padding:8px;margin-top:8px;border:1px solid #e3d6c2;border-radius:8px;box-sizing:border-box}
button{background:#7a5a3c;color:#fff;border-color:#7a5a3c;cursor:pointer}.e{color:#9a6b2f;font-size:14px}
@media(prefers-color-scheme:dark){body{background:#1f1814;color:#f1e6d6}form{background:#2a211b;border-color:#43362c}input{background:#1f1814;color:#f1e6d6;border-color:#43362c}}</style></head>
<body><form method="post"><h2 style="margin-top:0">Shared Calendar</h2>%s
<input name="name" placeholder="Your name" required maxlength="40" value="%s">
<input name="password" type="password" placeholder="Shared password" required>
<button>Enter</button></form></body></html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if not SITE_PASSWORD:
        return redirect("/")
    err, name = "", ""
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:40]
        pw = request.form.get("password", "")
        if name and hmac.compare_digest(pw.encode(), SITE_PASSWORD.encode()):
            session.permanent = True
            session["name"] = name
            return redirect("/")
        time.sleep(1)  # slows down password guessing
        err = '<p class="e">Wrong password or missing name.</p>'
    return LOGIN_PAGE % (err, escape(name, quote=True))


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/")
@login_required
def index():
    return send_from_directory(os.path.join(BASE, "static"), "index.html")


def clean(data):
    if not isinstance(data, dict):
        abort(400)
    title = str(data.get("title", "")).strip()[:150]
    d = str(data.get("date", "")).strip()
    end = str(data.get("end_date", "")).strip()
    t = str(data.get("time", "")).strip()
    try:
        if t:
            datetime.strptime(t, "%H:%M")
        date.fromisoformat(d)
        if end and date.fromisoformat(end) < date.fromisoformat(d):
            return None
    except ValueError:
        return None
    if not title:
        return None
    if end == d:
        end = ""
    cat = data.get("cat") if data.get("cat") in CATS else "Other"
    return (title, d, end, t, cat, str(data.get("notes", "")).strip()[:2000])


def row_dict(r):
    return dict(r)


@app.get("/api/me")
@login_required
def me():
    return jsonify(name=session.get("name", ""), auth=bool(SITE_PASSWORD))


@app.get("/api/events")
@login_required
def list_events():
    rows = db().execute("SELECT * FROM events ORDER BY date, time").fetchall()
    return jsonify([row_dict(r) for r in rows])


@app.post("/api/events")
@login_required
def create_event():
    data = request.get_json(silent=True)
    v = clean(data)
    if not v:
        return jsonify(error="Title and a valid date are required"), 400
    by = data.get("created_by")
    if by not in NAMES:
        return jsonify(error="Choose who is adding this"), 400
    cur = db().execute(
        "INSERT INTO events (title,date,end_date,time,cat,notes,created_by,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        v + (by, datetime.utcnow().isoformat()))
    db().commit()
    return jsonify(id=cur.lastrowid), 201


@app.put("/api/events/<int:eid>")
@login_required
def update_event(eid):
    data = request.get_json(silent=True)
    v = clean(data)
    if not v:
        return jsonify(error="Title and a valid date are required"), 400
    if data.get("created_by") in NAMES:
        db().execute("UPDATE events SET created_by=? WHERE id=?", (data["created_by"], eid))
    cur = db().execute(
        "UPDATE events SET title=?,date=?,end_date=?,time=?,cat=?,notes=?,updated_at=? WHERE id=?",
        v + (datetime.utcnow().isoformat(), eid))
    db().commit()
    return (jsonify(ok=True) if cur.rowcount else (jsonify(error="Not found"), 404))


@app.delete("/api/events/<int:eid>")
@login_required
def delete_event(eid):
    db().execute("DELETE FROM events WHERE id=?", (eid,))
    db().commit()
    return jsonify(ok=True)


@app.route("/assets/manifest.webmanifest")
def manifest():
    m = {"name": "Calendar", "short_name": "Calendar", "start_url": "/", "scope": "/",
         "display": "standalone", "background_color": "#f4eee2", "theme_color": "#f4eee2",
         "icons": [{"src": "/assets/icon-192.png", "sizes": "192x192", "type": "image/png"},
                   {"src": "/assets/icon-512.png", "sizes": "512x512", "type": "image/png"},
                   {"src": "/assets/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]}
    return Response(json.dumps(m), mimetype="application/manifest+json")


@app.route("/assets/<path:name>")
def assets(name):
    return send_from_directory(os.path.join(BASE, "static", "assets"), name)


if __name__ == "__main__":
    app.run(debug=False, port=5000)
