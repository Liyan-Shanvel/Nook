"""Test-only: serve the screens in a normal browser with the real Python backend on a scratch DB.
Usage: py tests/devserve.py <db path> <port> [--seed]"""
import datetime as dt
import http.server
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app import Api  # noqa: E402
from store import Store  # noqa: E402

db, port = sys.argv[1], int(sys.argv[2])
store = Store(db)


class FakeAccount:
    """Test-only: never talks to Google. --signed-out starts on the sign-in screen."""
    def __init__(self):
        self.u = None if "--signed-out" in sys.argv else {"email": "alex@example.com", "name": "Alex"}
        self.cal = {"ok": True, "at": __import__("time").time() - 180, "count": 1, "error": None}
        self.skipped = False

    def status(self):
        return {"user": self.u, "busy": False, "error": None, "ready": True, "calendar": self.cal,
                "skipped": self.skipped}

    def skip(self):
        self.skipped = True
        return self.status()

    def sign_in(self):
        self.u = {"email": "alex@example.com", "name": "Alex"}
        return self.status()

    def sign_out(self):
        self.u = None
        return self.status()

    def sync(self):
        return self.cal


api = Api(store, FakeAccount())

if "--seed" in sys.argv:
    today = store.today()
    y = (dt.date.fromisoformat(today) - dt.timedelta(days=1)).isoformat()
    a = store.add_task("Spanish, 45 min", today, 540, 600)
    store.update_task(a["id"], {"done": True})
    b = store.add_task("Write the project brief", today, 630, 690)
    store.update_task(b["id"], {"done": True})
    c = store.add_task("Design review", today, 750, 840)
    store.add_task("Plan next week", today, 1020, 1080)
    store.add_task("Reply to Sam", today)
    store.add_task("Book the dentist", y)
    store.replace_meetings(today, today, [{"id": "m1", "title": "Team sync", "day": today,
                                           "start_min": 960, "end_min": 990}])
    base = dt.datetime.combine(dt.date.fromisoformat(today), dt.time(9, 0)).timestamp()
    for label, cat, mins in [("Spanish, 45 min", "focus", 58), ("Other", "other", 25),
                             ("VS Code", "focus", 70), ("YouTube", "distracted", 30), ("Gmail", "focus", 70)]:
        for i in range(0, mins * 60, 5):
            store.track_sample(label, label, cat, base + i)
        base += mins * 60 + 30
    store.timer_start(c["id"])
    # habits, goals and some history
    import random
    random.seed(4)
    g1 = store.add_goal("Launch my side project", 30, "tasks", "2026-12-31", "tasks")
    g2 = store.add_goal("Spanish to B2", 100, "hours", "2027-03-31", "focus")
    g3 = store.add_goal("Save $10,000", 10000, "$", None, "typed")
    store.update_goal(g3["id"], {"typed": 1000})
    store.update_task(a["id"], {"goal_id": g2["id"]})
    store._q("UPDATE habit SET created=? WHERE 0", ("x",))
    td = dt.date.fromisoformat(today)
    hs = [store.add_habit("Spanish, 45 min", goal_id=g2["id"]), store.add_habit("Workout", days=[0, 2, 4]),
          store.add_habit("Ship one small thing", goal_id=g1["id"]), store.add_habit("No phone before 12")]
    store._q("UPDATE habit SET created=?", ((td - dt.timedelta(days=90)).isoformat(),))
    for i, h in enumerate(hs):
        for n in range(1, 85):
            if random.random() < (0.85 if n < 15 else 0.55) and not (i == 0 and n < 13 and False):
                store.tick_habit(h["id"], (td - dt.timedelta(days=n)).isoformat())
    for n in range(1, 13):
        store.tick_habit(hs[0]["id"], (td - dt.timedelta(days=n)).isoformat())
    store.tick_habit(hs[0]["id"])
    store.tick_habit(hs[1]["id"])
    for n in range(1, 70):
        day = (td - dt.timedelta(days=n)).isoformat()
        mins = random.choice([0, 40, 90, 150, 200, 260])
        t0 = dt.datetime.combine(td - dt.timedelta(days=n), dt.time(10, 0)).timestamp()
        if mins:
            store._q("INSERT INTO session(task_id,kind,start_ts,end_ts,day) VALUES(?,?,?,?,?)",
                     (a["id"] if n % 3 == 0 else None, "focus", t0, t0 + mins * 60, day))
        if n < 10:
            tt = store.add_task(["Inbox zero", "Gym", "Read 20 pages", "Fix the login bug", "Call the bank", "Sketch the logo", "Groceries", "Write the newsletter", "Pay rent"][n - 1], day)
            store.update_task(tt["id"], {"done": True})


FAKE = {"autostart": False}


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(ROOT, "ui"), **k)

    def log_message(self, *a):
        pass

    def do_POST(self):
        name = self.path.split("/api/", 1)[1]
        n = int(self.headers.get("Content-Length") or 0)
        args = json.loads(self.rfile.read(n) or b"[]")
        try:
            if name.startswith("_"):
                raise ValueError("hidden")
            if name == "autostart":           # never touch the real Startup folder from a test
                FAKE["autostart"] = bool(args[0]) if args else FAKE["autostart"]
                out = {"ok": FAKE["autostart"]}
            else:
                out = {"ok": getattr(api, name)(*args)}
        except Exception as e:
            out = {"error": f"{type(e).__name__}: {e}"}
        body = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
