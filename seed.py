"""Import events from a JSON file into the calendar. Safe to run twice (skips duplicates).

Usage (from this folder, with your virtualenv active):
    python seed.py seed_events.json
"""
import json
import os
import sys
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "import")
os.environ.setdefault("SITE_PASSWORD", "import")
import app  # noqa: E402  (creates/upgrades the database on import)

path = sys.argv[1] if len(sys.argv) > 1 else "seed_events.json"
added = 0
with app.app.app_context():
    con = app.db()
    for e in json.load(open(path)):
        v = app.clean(e)
        if not v:
            print("Skipped (invalid):", e)
            continue
        dup = con.execute("SELECT 1 FROM events WHERE title=? AND date=? AND end_date=?", v[:3]).fetchone()
        if dup:
            continue
        con.execute(
            "INSERT INTO events (title,date,end_date,time,color,notes,created_by,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            v + ("import", datetime.utcnow().isoformat()))
        added += 1
    con.commit()
print(f"Added {added} item(s).")
