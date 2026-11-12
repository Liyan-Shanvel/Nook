"""Turn 5 s samples into events, the way Rize's client does, into its OWN db (data/smarttrack.db).

- One open event. Close it and open a new one when app, title or site changes, or after 180 s.
- Idle: when nobody touched the mouse/keyboard for IDLE_AFTER seconds, the open event is closed at the
  moment input STOPPED (backdated), so idle minutes are never counted as work.
- Sleep / gaps: if the loop itself missed more than GAP seconds (PC asleep), close at the last good sample.
- 'ignore' kinds (password managers, private windows) are never stored."""
import os
import sqlite3
import time

from . import capture, rules as R

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(HERE, "data", "smarttrack.db")
RULES_JSON = os.path.join(HERE, "data", "smarttrack_rules.json")
POLL = 5
IDLE_AFTER = 120
MAX_EVENT = 180
GAP = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS event(
  id INTEGER PRIMARY KEY, start REAL NOT NULL, end REAL NOT NULL,
  exe TEXT, app TEXT, host TEXT, title TEXT, kind TEXT, cat TEXT, rule TEXT);
CREATE INDEX IF NOT EXISTS event_start ON event(start);
"""


def connect(path=DB):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


class Recorder:
    def __init__(self, con, rules=None, store_titles=True):
        self.con = con
        self.rules = rules if rules is not None else R.load(RULES_JSON)
        self.store_titles = store_titles
        self.prev = None          # open event dict
        self.last_tick = None

    def _close(self, at):
        p, self.prev = self.prev, None
        if not p or at - p["start"] < 1:
            return
        if p["cat"] == "ignore":
            return
        self.con.execute(
            "INSERT INTO event(start,end,exe,app,host,title,kind,cat,rule) VALUES(?,?,?,?,?,?,?,?,?)",
            (p["start"], at, p["exe"], p["app"], p["host"], p["title"] if self.store_titles else "",
             p["kind"], p["cat"], p["rule"]))
        self.con.commit()

    def step(self, s, now):
        """Feed one sample (from capture.sample(), or None). Returns the open event or None."""
        if self.last_tick is not None and now - self.last_tick > GAP and self.prev:
            self._close(self.last_tick)                        # PC slept or the loop stalled
        self.last_tick = now
        if s is None:
            self._close(now)
            return None
        if s["idle"] >= IDLE_AFTER:
            if self.prev:
                self._close(max(self.prev["start"], now - s["idle"]))   # backdate to last input
            return None
        if s["private"]:
            kind, cat, rule = "private", "ignore", "private-window"
        else:
            kind, cat, rule = R.classify(s["exe"], s["title"], s["host"], self.rules)
        cur = {"exe": s["exe"], "app": R.app_label(s["exe"]), "host": s["host"], "title": s["title"],
               "kind": kind, "cat": cat, "rule": rule}
        p = self.prev
        changed = not p or any(p[k] != cur[k] for k in ("exe", "title", "host"))
        if p and (changed or now - p["start"] >= MAX_EVENT):
            self._close(now)
            p = None
        if p is None:
            cur["start"] = now
            self.prev = cur
        return self.prev

    def stop(self):
        self._close(time.time())


AI_FIRST_DELAY = 600      # first daily AI sort 10 min after start, so there is something to sort


def _ai_job(rec, log):
    """Background, own db connection. Any failure = try again on the next daily check."""
    from . import ai_sort
    con = connect()
    try:
        if ai_sort.sort_unknowns(con, log=log):
            rec.rules = R.load(RULES_JSON)          # new rules apply to the very next sample
        ai_sort.mark_ran()
    except Exception as e:                         # noqa: BLE001 - outage is never a verdict
        log(f"ai_sort failed, will retry: {e!r}")
    finally:
        con.close()


def run(verbose=False, seconds=None, ai=True):
    import threading
    from . import ai_sort
    con = connect()
    rec = Recorder(con)
    started = time.time()
    next_ai_check = started + AI_FIRST_DELAY
    log = (lambda m: print(time.strftime("%H:%M:%S"), m, flush=True)) if verbose else (lambda m: None)
    stop_at = time.time() + seconds if seconds else None
    try:
        while stop_at is None or time.time() < stop_at:
            now = time.time()
            if ai and now >= next_ai_check:
                next_ai_check = now + 3600                 # look again hourly; runs at most once a day
                if ai_sort.due():
                    threading.Thread(target=_ai_job, args=(rec, log), daemon=True).start()
            ev = rec.step(capture.sample(), now)
            if verbose and ev:
                print(time.strftime("%H:%M:%S"), ev["cat"][:5].ljust(5), ev["kind"].ljust(8),
                      ev["host"] or ev["app"], "|", (ev["title"] or "")[:60], flush=True)
            time.sleep(max(0.5, POLL - (time.time() - now)))
    except KeyboardInterrupt:
        pass
    finally:
        rec.stop()
        con.close()
