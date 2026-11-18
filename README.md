# Shared Calendar

Shared month / week / list calendar with multi-day items and Victorian public holidays. Flask + SQLite, one shared password, everyone signs in with their name.

## Run locally
    python -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    SECRET_KEY=anything INSECURE_COOKIES=1 python app.py   # add SITE_PASSWORD=... to require a password

## Deploy on PythonAnywhere
1. Push this folder to a **private** GitHub repo (no secrets live in the code).
2. PythonAnywhere > Consoles > Bash:
       git clone https://github.com/YOU/shared-calendar.git
       mkvirtualenv cal --python=python3.12     # pick a version PythonAnywhere offers
       pip install -r shared-calendar/requirements.txt
3. Web tab > Add a new web app > Manual configuration > same Python version.
   - Source code: /home/USERNAME/shared-calendar
   - Virtualenv: /home/USERNAME/.virtualenvs/cal
4. Click the WSGI configuration file link, replace its contents with:
       import sys, os
       path = '/home/USERNAME/shared-calendar'
       if path not in sys.path:
           sys.path.insert(0, path)
       os.environ['SECRET_KEY'] = 'long-random-string'
       # optional: uncomment to require a shared password
       # os.environ['SITE_PASSWORD'] = 'password-you-share-with-guests'
       from app import app as application
5. Reload the web app, then open https://USERNAME.pythonanywhere.com

## Updating
Push to GitHub, then in a PythonAnywhere Bash console run `cd shared-calendar && git pull`, then press Reload on the Web tab.

## Notes
- Data lives in `data/calendar.db` (ignored by git, so `git pull` never overwrites it). Download it occasionally as a backup.
- Everyone with the password can add, edit and delete everything.

## Importing items in bulk
Put items in `seed_events.json` (it's in `.gitignore`, so it stays out of GitHub) and run `python seed.py seed_events.json` in a PythonAnywhere Bash console (inside the project folder, virtualenv active). Running it twice won't create duplicates.
