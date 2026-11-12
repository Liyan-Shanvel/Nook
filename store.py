"""Nook store: one SQLite file.

A task, a calendar block and a focus session are the SAME item seen three ways:
a task with start_min/end_min is a calendar block; a focus session points at a task.
Times of day are minutes from midnight (0-1440). Timestamps are unix seconds.
"""
import base64
import datetime as dt
import json
import os
import re
import secrets
import sqlite3
import threading
import time

import sounds

SCHEMA = """
CREATE TABLE IF NOT EXISTS task(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, day TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 0, start_min INTEGER, end_min INTEGER,
  pos REAL NOT NULL DEFAULT 0, created REAL NOT NULL, done_at REAL);
CREATE TABLE IF NOT EXISTS meeting(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, day TEXT NOT NULL,
  start_min INTEGER NOT NULL, end_min INTEGER NOT NULL, source TEXT NOT NULL DEFAULT 'google');
CREATE TABLE IF NOT EXISTS session(
  id INTEGER PRIMARY KEY, task_id INTEGER, kind TEXT NOT NULL,
  start_ts REAL NOT NULL, end_ts REAL NOT NULL, day TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS track(
  id INTEGER PRIMARY KEY, day TEXT NOT NULL, start_ts REAL NOT NULL, end_ts REAL NOT NULL,
  app TEXT NOT NULL, label TEXT NOT NULL, category TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS task_day ON task(day);
CREATE INDEX IF NOT EXISTS track_day ON track(day);
CREATE INDEX IF NOT EXISTS session_day ON session(day);
CREATE TABLE IF NOT EXISTS habit(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, days TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]',
  goal_id INTEGER, paused INTEGER NOT NULL DEFAULT 0, pos REAL NOT NULL DEFAULT 0, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS habit_tick(habit_id INTEGER NOT NULL, day TEXT NOT NULL, PRIMARY KEY(habit_id, day));
CREATE TABLE IF NOT EXISTS goal(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, target REAL NOT NULL, unit TEXT NOT NULL DEFAULT '',
  deadline TEXT, mode TEXT NOT NULL DEFAULT 'tasks', typed REAL NOT NULL DEFAULT 0, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS goal_log(
  id INTEGER PRIMARY KEY, goal_id INTEGER NOT NULL, day TEXT NOT NULL, amount REAL NOT NULL,
  note TEXT NOT NULL DEFAULT '', created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS goal_step(
  id INTEGER PRIMARY KEY, goal_id INTEGER NOT NULL, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0,
  done_day TEXT, pos REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS call(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, day TEXT NOT NULL, mins REAL NOT NULL DEFAULT 0,
  speakers INTEGER NOT NULL DEFAULT 0, external INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT 'fathom');
CREATE TABLE IF NOT EXISTS vision(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, file TEXT, text TEXT NOT NULL DEFAULT '',
  caption TEXT NOT NULL DEFAULT '', goal_id INTEGER, wide INTEGER NOT NULL DEFAULT 0,
  pos REAL NOT NULL DEFAULT 0, created REAL NOT NULL);
"""
# What moves a goal. hand = you add it, linked = ticked tasks and habits you point at it,
# tasks_word = ticked tasks with a word, focus_all = all focus time, focus_word = focus on linked
# tasks or ones with a word, calendar = past calendar events with a word, calls = recorded calls
# where the other person showed up, value = a number that moves (weight), steps = a checklist.
GOAL_SOURCES = ("hand", "linked", "tasks_word", "focus_all", "focus_word", "calendar", "calls", "value", "steps")
GOAL_STATUS = ("active", "paused", "done", "archived")
GOAL_COLS = [("source", "TEXT NOT NULL DEFAULT ''"), ("match", "TEXT NOT NULL DEFAULT ''"), ("start", "TEXT"),
             ("period", "TEXT NOT NULL DEFAULT ''"), ("status", "TEXT NOT NULL DEFAULT 'active'"),
             ("why", "TEXT NOT NULL DEFAULT ''"), ("step", "REAL NOT NULL DEFAULT 1"),
             ("base", "REAL NOT NULL DEFAULT 0"), ("pos", "REAL NOT NULL DEFAULT 0")]
VISION_MAX = 3 * 1024 * 1024

# Rules match the APP name only (for a browser that is the site, e.g. "YouTube"), never the
# window title: a code file called youtube_notes.md must not count as distracted.
DEFAULT_RULES = [
    ["youtube", "distracted"], ["instagram", "distracted"], ["netflix", "distracted"],
    ["reddit", "distracted"], ["facebook", "distracted"], ["twitter", "distracted"],
    ["hotstar", "distracted"], ["prime video", "distracted"],
    ["vs code", "focus"], ["terminal", "focus"], ["powershell", "focus"], ["claude", "focus"],
    ["notion", "focus"], ["obsidian", "focus"], ["gmail", "focus"], ["mail", "focus"],
    ["google docs", "focus"], ["google sheets", "focus"], ["excel", "focus"],
    ["paper", "focus"], ["plusvibe", "focus"],
]
DEFAULTS = {"focus": 25, "short": 5, "long": 15, "goal_min": 180,
            "tracking": True, "sound": True, "sounds": True, "rules": DEFAULT_RULES,
            "sound_pick": dict(sounds.DEFAULT)}
# "sound" was the old rain switch (removed); "sounds" = the finish / tick sounds.
MODES = ("focus", "short", "long")


def day_of(ts):
    return dt.date.fromtimestamp(ts).isoformat()


def min_of(ts):
    d = dt.datetime.fromtimestamp(ts)
    return d.hour * 60 + d.minute + d.second / 60


class Store:
    FIELDS = ("title", "day", "done", "start_min", "end_min", "goal_id", "focus_min")

    def __init__(self, path, clock=time.time):
        self.clock = clock
        self.on_sound = None        # app sets this to sounds.play; tests leave it None
        self.lock = threading.RLock()
        self.dir = os.path.dirname(os.path.abspath(path))
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(task)")}
        if "goal_id" not in cols:
            self.db.execute("ALTER TABLE task ADD COLUMN goal_id INTEGER")
            self.db.commit()
        if "focus_min" not in cols:                 # a task's own focus length (None = the default)
            self.db.execute("ALTER TABLE task ADD COLUMN focus_min INTEGER")
            self.db.commit()
        if "label" not in {r[1] for r in self.db.execute("PRAGMA table_info(session)")}:
            self.db.execute("ALTER TABLE session ADD COLUMN label TEXT")   # name of a no-task focus
            self.db.commit()
        if "source" not in {r[1] for r in self.db.execute("PRAGMA table_info(goal)")}:
            # 1.2: goals got "what moves it". Old goals keep their numbers: a typed total becomes one entry.
            for name, kind in GOAL_COLS:
                self.db.execute(f"ALTER TABLE goal ADD COLUMN {name} {kind}")
            self.db.execute("UPDATE goal SET source=CASE mode WHEN 'tasks' THEN 'linked' "
                            "WHEN 'focus' THEN 'focus_word' ELSE 'hand' END, pos=id")
            self.db.execute("INSERT INTO goal_log(goal_id,day,amount,note,created) "
                            "SELECT id, created, typed, '', ? FROM goal WHERE mode='typed' AND typed<>0",
                            (self.clock(),))
            self.db.commit()

    # ---------- plumbing ----------
    def today(self):
        return day_of(self.clock())

    def _q(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def _all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args)]

    def _get(self, k, default):
        r = self._all("SELECT v FROM kv WHERE k=?", (k,))
        return json.loads(r[0]["v"]) if r else default

    def _set(self, k, v):
        self._q("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (k, json.dumps(v)))

    def _sound(self, name):
        """Fire one sound if sounds are on. Never lets a sound problem break the store."""
        if self.on_sound:
            try:
                st = self.settings()
                style = st["sound_pick"].get(name)
                if st.get("sounds", True) and style != "off":
                    self.on_sound(name, style)
            except Exception:
                pass

    # ---------- settings ----------
    def settings(self):
        s = json.loads(json.dumps(DEFAULTS))
        s.update(self._get("settings", {}))
        pick = s.get("sound_pick") or {}           # old or unknown picks fall back to the default
        s["sound_pick"] = {m: pick[m] if sounds.known(pick.get(m)) or pick.get(m) == "off"
                           else sounds.DEFAULT[m] for m in sounds.MOMENTS}
        return s

    def set_setting(self, k, v):
        if k not in DEFAULTS:
            raise ValueError(f"unknown setting {k}")
        if k in MODES or k == "goal_min":
            v = int(v)
            if not 1 <= v <= 600:
                raise ValueError("minutes must be 1-600")
        if k in ("tracking", "sound", "sounds"):
            v = bool(v)
        if k == "sound_pick":
            v = {m: (v or {}).get(m, sounds.DEFAULT[m]) for m in sounds.MOMENTS}
            if any(x != "off" and not sounds.known(x) for x in v.values()):
                raise ValueError("unknown sound")
        if k == "rules":
            clean = []
            for name, cat in v:
                name = str(name).strip().lower()
                if cat not in ("focus", "distracted", "other"):
                    raise ValueError("category must be focus, distracted or other")
                if name and name not in [c[0] for c in clean]:
                    clean.append([name, cat])
            v = clean
        s = self._get("settings", {})
        s[k] = v
        self._set("settings", s)
        return self.settings()

    # ---------- tasks ----------
    @staticmethod
    def _check_times(s, e):
        if (s is None) != (e is None):
            raise ValueError("start and end go together")
        if s is not None and not (0 <= s < e <= 1440):
            raise ValueError("bad time")

    @staticmethod
    def _shape(t):
        t["done"] = bool(t["done"])
        return t

    def task(self, tid):
        r = self._all("SELECT * FROM task WHERE id=?", (tid,))
        if not r:
            raise KeyError(f"no task {tid}")
        return self._shape(r[0])

    def add_task(self, title, day=None, start_min=None, end_min=None):
        title = (title or "").strip()
        if not title:
            raise ValueError("empty title")
        day = day or self.today()
        self._check_times(start_min, end_min)
        with self.lock:
            pos = self._all("SELECT COALESCE(MAX(pos),0)+1 p FROM task WHERE day=?", (day,))[0]["p"]
            cur = self._q("INSERT INTO task(title,day,start_min,end_min,pos,created) VALUES(?,?,?,?,?,?)",
                          (title, day, start_min, end_min, pos, self.clock()))
            return self.task(cur.lastrowid)

    def update_task(self, tid, fields):
        bad = set(fields) - set(self.FIELDS)
        if bad:
            raise ValueError(f"cannot change {sorted(bad)}")
        with self.lock:
            t = self.task(tid)
            new = {**t, **fields}
            new["title"] = (new["title"] or "").strip()
            if not new["title"]:
                raise ValueError("empty title")
            self._check_times(new["start_min"], new["end_min"])
            new["done"] = bool(new["done"])
            done_at = t["done_at"]
            if new["done"] and not t["done"]:
                done_at = self.clock()
                self._sound("task_done")
            elif not new["done"]:
                done_at = None
            gid = new.get("goal_id")
            if gid is not None:
                gid = int(gid)
                if not self._all("SELECT id FROM goal WHERE id=?", (gid,)):
                    raise ValueError("no such goal")
            fm = new.get("focus_min")
            if fm is not None:
                fm = int(fm)
                if not 1 <= fm <= 600:
                    raise ValueError("minutes must be 1-600")
            self._q("UPDATE task SET title=?,day=?,done=?,start_min=?,end_min=?,done_at=?,goal_id=?,focus_min=? "
                    "WHERE id=?", (new["title"], new["day"], int(new["done"]), new["start_min"],
                                   new["end_min"], done_at, gid, fm, tid))
            return self.task(tid)

    def delete_task(self, tid):
        with self.lock:
            self._q("DELETE FROM task WHERE id=?", (tid,))
            t = self._timer()
            if t["task_id"] == tid:
                if t["running"]:
                    self._segment(t, self.clock())
                    t["seg_start"] = self.clock()
                t["task_id"] = None
                self._set("timer", t)

    def duplicate_task(self, tid):
        t = self.task(tid)
        new = self.add_task(t["title"], t["day"])
        return self.update_task(new["id"], {"goal_id": t["goal_id"], "focus_min": t["focus_min"]})

    def tasks(self, a, b=None):
        rows = self._all("SELECT * FROM task WHERE day BETWEEN ? AND ? "
                         "ORDER BY day, start_min IS NULL, start_min, pos", (a, b or a))
        return [self._shape(r) for r in rows]

    def carry(self):
        """Unfinished tasks from earlier days."""
        return [self._shape(r) for r in self._all(
            "SELECT * FROM task WHERE day<? AND done=0 ORDER BY day, pos", (self.today(),))]

    def move_to_today(self):
        """Pull every unfinished past task into today. Old times no longer mean anything, so they go."""
        with self.lock:
            today = self.today()
            for t in self.carry():
                pos = self._all("SELECT COALESCE(MAX(pos),0)+1 p FROM task WHERE day=?", (today,))[0]["p"]
                self._q("UPDATE task SET day=?, start_min=NULL, end_min=NULL, pos=? WHERE id=?",
                        (today, pos, t["id"]))

    # ---------- meetings (filled by the Google Calendar sync) ----------
    def meetings(self, a, b=None):
        hidden = set(self._get("hidden_events", []))
        return [m for m in self._all("SELECT * FROM meeting WHERE day BETWEEN ? AND ? ORDER BY day, start_min",
                                     (a, b or a)) if m["id"] not in hidden]

    def hide_event(self, mid, on=True):
        """Google events are read-only for Nook, so 'remove' means: stop showing it here."""
        ids = [x for x in self._get("hidden_events", []) if x != mid]
        self._set("hidden_events", ids + [mid] if on else ids)
        return len(self._get("hidden_events", []))

    def show_all_events(self):
        self._set("hidden_events", [])
        return 0

    def replace_meetings(self, a, b, items):
        with self.lock:
            self._q("DELETE FROM meeting WHERE day BETWEEN ? AND ?", (a, b))
            for m in items:
                self._q("INSERT OR REPLACE INTO meeting(id,title,day,start_min,end_min,source) "
                        "VALUES(?,?,?,?,?,?)", (m["id"], m["title"], m["day"], m["start_min"],
                                                m["end_min"], m.get("source", "google")))

    # ---------- focus timer ----------
    def _timer(self):
        t = {"mode": "focus", "running": False, "end": 0.0, "left": None, "task_id": None,
             "seg_start": None, "just_done": False, "done_mode": None, "label": None}
        t.update(self._get("timer", {}))
        return t

    def _task_min(self, t):
        """The task's own focus length, if the timer is on a task that has one."""
        if t["task_id"]:
            r = self._all("SELECT focus_min FROM task WHERE id=?", (t["task_id"],))
            if r and r[0]["focus_min"]:
                return int(r[0]["focus_min"])
        return None

    def _total(self, t):
        if t["mode"] == "focus":
            own = self._task_min(t)
            if own:
                return own * 60
        return self.settings()[t["mode"]] * 60

    def _segment(self, t, end_ts):
        """Write the running stretch as a session row, so paused-and-resumed time all counts."""
        if t["seg_start"] and end_ts > t["seg_start"]:
            self._q("INSERT INTO session(task_id,kind,start_ts,end_ts,day,label) VALUES(?,?,?,?,?,?)",
                    (t["task_id"], t["mode"], t["seg_start"], end_ts, day_of(t["seg_start"]),
                     None if t["task_id"] else t.get("label")))
        t["seg_start"] = None

    def timer_length(self, mins):
        """Change how long the timer runs. On a task with its own length, that task changes;
        otherwise the default for this mode. A paused timer starts over at the new length."""
        mins = int(mins)
        if not 1 <= mins <= 600:
            raise ValueError("minutes must be 1-600")
        with self.lock:
            t = self._timer()
            if t["running"]:
                raise ValueError("pause first")
            if t["mode"] == "focus" and self._task_min(t):
                self._q("UPDATE task SET focus_min=? WHERE id=?", (mins, t["task_id"]))
            else:
                self.set_setting(t["mode"], mins)
            t.update(left=None, just_done=False)
            self._set("timer", t)
            return self.timer_state()

    def timer_unlabel(self):
        """Clear what a stopped timer is on (a name or a task), so a new one can be picked."""
        with self.lock:
            t = self._timer()
            if not t["running"]:
                t.update(label=None, task_id=None, left=None)
                self._set("timer", t)
            return self.timer_state()

    def timer_label(self, label):
        """Focus on something that is not a task: just a name, then go."""
        label = " ".join(str(label or "").split())[:80]
        if not label:
            raise ValueError("empty name")
        with self.lock:
            self.timer_state()
            t, now = self._timer(), self.clock()
            if t["running"]:
                self._segment(t, min(now, t["end"]))
            t.update(task_id=None, label=label, mode="focus", running=True, just_done=False,
                     end=now + self.settings()["focus"] * 60, seg_start=now, left=None)
            self._set("timer", t)
            return self.timer_state()

    def timer_state(self):
        with self.lock:
            t, now, finished = self._timer(), self.clock(), False
            if t["running"] and t["end"] <= now:
                self._segment(t, t["end"])
                t.update(running=False, left=None, just_done=True, done_mode=t["mode"])
                self._set("timer", t)
                finished = True
                self._sound("focus_done" if t["mode"] == "focus" else "break_done")
            total = self._total(t)
            if t["running"]:
                rem = max(0.0, t["end"] - now)
            else:
                rem = min(t["left"], total) if t["left"] is not None else total
            return {**t, "total": total, "remaining": rem, "finished_now": finished, "now": now}

    def timer_start(self, task_id=None, mode=None):
        with self.lock:
            self.timer_state()                      # settle a timer that ran out
            t, now = self._timer(), self.clock()
            if mode and mode not in MODES:
                raise ValueError("bad mode")
            if task_id is not None:
                self.task(task_id)                  # must exist
                if task_id != t["task_id"]:
                    if t["running"]:
                        self._segment(t, now)
                    t.update(task_id=task_id, label=None, running=False, left=None)
                    mode = mode or "focus"
            if mode and mode != t["mode"]:
                if t["running"]:
                    self._segment(t, now)
                t.update(mode=mode, running=False, left=None)
            if not t["running"]:
                left = t["left"] if t["left"] is not None else self._total(t)
                t.update(running=True, end=now + left, seg_start=now, left=None)
            t["just_done"] = False
            self._set("timer", t)
            return self.timer_state()

    def timer_pause(self):
        with self.lock:
            t, now = self._timer(), self.clock()
            if t["running"] and t["end"] > now:
                self._segment(t, now)
                t.update(running=False, left=t["end"] - now)
                self._set("timer", t)
            return self.timer_state()

    def timer_reset(self):
        with self.lock:
            t, now = self._timer(), self.clock()
            if t["running"]:
                self._segment(t, min(now, t["end"]))
            t.update(running=False, left=None, just_done=False)
            self._set("timer", t)
            return self.timer_state()

    def timer_mode(self, mode):
        """Pick focus / short / long without starting it (the bar's mode buttons)."""
        if mode not in MODES:
            raise ValueError("bad mode")
        with self.lock:
            t, now = self._timer(), self.clock()
            if t["mode"] != mode or t["just_done"]:
                if t["running"]:
                    self._segment(t, min(now, t["end"]))
                t.update(mode=mode, running=False, left=None, just_done=False)
                self._set("timer", t)
            return self.timer_state()

    def timer_select(self, task_id):
        """Point a stopped timer at a task without starting it."""
        with self.lock:
            t = self._timer()
            if not t["running"] and task_id != t["task_id"]:
                self.task(task_id)
                t.update(task_id=task_id, label=None, left=None)
                self._set("timer", t)
            return self.timer_state()

    def timer_dismiss(self):
        with self.lock:
            t = self._timer()
            t["just_done"] = False
            self._set("timer", t)
            return self.timer_state()

    def focused(self, day):
        """Focus minutes on a day, including the stretch running right now."""
        secs = self._all("SELECT COALESCE(SUM(end_ts-start_ts),0) s FROM session "
                         "WHERE day=? AND kind='focus'", (day,))[0]["s"]
        t = self._timer()
        if t["running"] and t["mode"] == "focus" and t["seg_start"] and day_of(t["seg_start"]) == day:
            secs += max(0.0, min(self.clock(), t["end"]) - t["seg_start"])
        return secs / 60

    def focus_by_day(self, a, b):
        out = {r["day"]: r["s"] / 60 for r in self._all(
            "SELECT day, SUM(end_ts-start_ts) s FROM session WHERE kind='focus' AND day BETWEEN ? AND ? "
            "GROUP BY day", (a, b))}
        today = self.today()
        if a <= today <= b:
            out[today] = self.focused(today)
        return out

    # ---------- auto tracking ----------
    def track_sample(self, app, label, category, ts=None, gap=20):
        """One look at the foreground window. Same thing as last time -> stretch it; else start new."""
        ts = ts if ts is not None else self.clock()
        day = day_of(ts)
        with self.lock:
            last = self._all("SELECT * FROM track ORDER BY id DESC LIMIT 1")
            start = ts
            if last and last[0]["day"] == day and 0 <= ts - last[0]["end_ts"] <= gap:
                L = last[0]
                if (L["app"], L["label"], L["category"]) == (app, label, category):
                    self._q("UPDATE track SET end_ts=? WHERE id=?", (ts, L["id"]))
                    return
                start = L["end_ts"]
            self._q("INSERT INTO track(day,start_ts,end_ts,app,label,category) VALUES(?,?,?,?,?,?)",
                    (day, start, ts, app, label, category))

    def lane(self, day):
        """The WHAT HAPPENED lane: join the same thing across tiny gaps, hide bits under 5 min."""
        rows = self._all("SELECT start_ts,end_ts,label,category FROM track WHERE day=? ORDER BY start_ts",
                         (day,))

        def merge(items, gap):
            out = []
            for r in items:
                if (out and out[-1]["label"] == r["label"] and out[-1]["category"] == r["category"]
                        and r["start_ts"] - out[-1]["end_ts"] <= gap):
                    out[-1]["end_ts"] = max(out[-1]["end_ts"], r["end_ts"])
                else:
                    out.append(dict(r))
            return out

        blocks = [b for b in merge(rows, 60) if b["end_ts"] - b["start_ts"] >= 300]
        return [{"label": b["label"], "category": b["category"], "start_min": min_of(b["start_ts"]),
                 "end_min": min_of(b["end_ts"]), "mins": (b["end_ts"] - b["start_ts"]) / 60}
                for b in merge(blocks, 300)]

    def summary(self, day):
        cats = {r["category"]: r["s"] / 60 for r in self._all(
            "SELECT category, SUM(end_ts-start_ts) s FROM track WHERE day=? GROUP BY category", (day,))}
        apps = [{"app": r["app"], "mins": r["s"] / 60} for r in self._all(
            "SELECT app, SUM(end_ts-start_ts) s FROM track WHERE day=? GROUP BY app ORDER BY s DESC LIMIT 3",
            (day,))]
        return {"total": sum(cats.values()), "focus": cats.get("focus", 0),
                "distracted": cats.get("distracted", 0), "other": cats.get("other", 0), "apps": apps}

    # ---------- habits ----------
    # A habit is planned on some weekdays (0 = Mon). A missed planned day breaks the streak;
    # an off-day never does, and a tick on an off-day still counts.
    @staticmethod
    def _days(v):
        days = sorted({int(x) for x in (json.loads(v) if isinstance(v, str) else v)})
        if not days or any(not 0 <= x <= 6 for x in days):
            raise ValueError("pick at least one day")
        return days

    def _habit_row(self, hid):
        r = self._all("SELECT * FROM habit WHERE id=?", (hid,))
        if not r:
            raise KeyError(f"no habit {hid}")
        h = r[0]
        h["days"], h["paused"] = json.loads(h["days"]), bool(h["paused"])
        return h

    def _ticks(self, hid):
        return {r["day"] for r in self._all("SELECT day FROM habit_tick WHERE habit_id=?", (hid,))}

    def _check_goal(self, gid):
        if gid is None:
            return None
        gid = int(gid)
        if not self._all("SELECT id FROM goal WHERE id=?", (gid,)):
            raise ValueError("no such goal")
        return gid

    def add_habit(self, title, days=None, goal_id=None):
        title = (title or "").strip()
        if not title:
            raise ValueError("empty title")
        days = self._days(days if days is not None else list(range(7)))
        with self.lock:
            pos = self._all("SELECT COALESCE(MAX(pos),0)+1 p FROM habit")[0]["p"]
            cur = self._q("INSERT INTO habit(title,days,goal_id,pos,created) VALUES(?,?,?,?,?)",
                          (title, json.dumps(days), self._check_goal(goal_id), pos, self.today()))
            return self.habit(cur.lastrowid)

    def update_habit(self, hid, fields):
        bad = set(fields) - {"title", "days", "goal_id", "paused"}
        if bad:
            raise ValueError(f"cannot change {sorted(bad)}")
        with self.lock:
            h = {**self._habit_row(hid), **fields}
            h["title"] = (h["title"] or "").strip()
            if not h["title"]:
                raise ValueError("empty title")
            self._q("UPDATE habit SET title=?,days=?,goal_id=?,paused=? WHERE id=?",
                    (h["title"], json.dumps(self._days(h["days"])), self._check_goal(h["goal_id"]),
                     int(bool(h["paused"])), hid))
            return self.habit(hid)

    def delete_habit(self, hid):
        with self.lock:
            self._q("DELETE FROM habit_tick WHERE habit_id=?", (hid,))
            self._q("DELETE FROM habit WHERE id=?", (hid,))

    def tick_habit(self, hid, day=None, on=True):
        day = day or self.today()
        if day > self.today():
            raise ValueError("cannot tick a day that has not come yet")
        self._habit_row(hid)
        if on:
            self._q("INSERT OR IGNORE INTO habit_tick(habit_id,day) VALUES(?,?)", (hid, day))
        else:
            self._q("DELETE FROM habit_tick WHERE habit_id=? AND day=?", (hid, day))
        return self.habit(hid)

    def _stats(self, h, ticks):
        today = dt.date.fromisoformat(self.today())
        start = min([dt.date.fromisoformat(h["created"])] + [dt.date.fromisoformat(t) for t in ticks])
        days = set(h["days"])
        # current streak: walk back from today; an open today does not break it
        n, d = 0, today
        while d >= start:
            iso = d.isoformat()
            if iso in ticks:
                n += 1
            elif d.weekday() in days and d != today:
                break
            d -= dt.timedelta(days=1)
        best = cur = 0
        d = start
        while d <= today:
            iso = d.isoformat()
            if iso in ticks:
                cur += 1
                best = max(best, cur)
            elif d.weekday() in days and d != today:
                cur = 0
            d += dt.timedelta(days=1)
        lo = max(start, today - dt.timedelta(days=83))
        planned = kept = 0
        d = lo
        while d <= today:
            if d.weekday() in days and (d != today or d.isoformat() in ticks):
                planned += 1
                kept += d.isoformat() in ticks
            d += dt.timedelta(days=1)
        return {"streak": n, "best": best, "rate": round(100 * kept / planned) if planned else None}

    def _cell(self, h, ticks, d, today):
        iso = d.isoformat()
        if d > today:
            return "future"
        if iso in ticks:
            return "done"
        if iso < h["created"]:
            return "before"
        if d.weekday() not in h["days"]:
            return "off"
        return "open" if d == today else "miss"

    def habit(self, hid):
        h = self._habit_row(hid)
        ticks = self._ticks(hid)
        today = dt.date.fromisoformat(self.today())
        h.update(self._stats(h, ticks))
        h["week"] = [{"day": (today - dt.timedelta(days=6 - i)).isoformat(),
                      "state": self._cell(h, ticks, today - dt.timedelta(days=6 - i), today)} for i in range(7)]
        h["today_done"] = today.isoformat() in ticks
        h["due_today"] = today.weekday() in h["days"]
        return h

    def habits(self):
        return [self.habit(r["id"]) for r in self._all("SELECT id FROM habit ORDER BY paused, pos")]

    def habit_detail(self, hid):
        h = self.habit(hid)
        ticks = self._ticks(hid)
        today = dt.date.fromisoformat(self.today())
        monday = today - dt.timedelta(days=today.weekday())
        weeks = []
        for w in range(11, -1, -1):
            a = monday - dt.timedelta(weeks=w)
            cells = [self._cell(h, ticks, a + dt.timedelta(days=i), today) for i in range(7)]
            planned = sum(1 for c in cells if c in ("done", "miss"))
            weeks.append({"start": a.isoformat(), "cells": cells,
                          "kept": cells.count("done"), "planned": planned})
        h["weeks"] = weeks
        return h

    def habits_kept(self, a, b):
        """Ticks on planned days / planned days, between a and b (never past today)."""
        b = min(b, self.today())
        planned = kept = 0
        per = []
        for r in self._all("SELECT id FROM habit WHERE paused=0 ORDER BY pos"):
            h = self._habit_row(r["id"])
            ticks = self._ticks(h["id"])
            p = k = 0
            d = dt.date.fromisoformat(max(a, min([h["created"]] + list(ticks))))
            while d.isoformat() <= b:
                iso = d.isoformat()
                if d.weekday() in h["days"] and (iso != self.today() or iso in ticks):
                    p += 1
                    k += iso in ticks
                d += dt.timedelta(days=1)
            per.append({"id": h["id"], "title": h["title"], "kept": k, "planned": p})
            planned += p
            kept += k
        return {"pct": round(100 * kept / planned) if planned else None, "habits": per}

    # ---------- goals ----------
    # A goal has ONE thing that moves it (source). Whatever the source, a number added by hand
    # (goal_log) counts too, so nothing is ever stuck.
    GOAL_FIELDS = ("title", "target", "unit", "deadline", "source", "match", "start", "period",
                   "status", "why", "step", "base", "pos")

    @staticmethod
    def _words(match):
        return [w.strip() for w in (match or "").split(",") if w.strip()]

    @staticmethod
    def _hit(words, text):
        """Whole word, any case: 'call' matches 'Sales call', never 'recall'."""
        text = text or ""
        return any(re.search("(?<![0-9A-Za-z])" + re.escape(w) + "(?![0-9A-Za-z])", text, re.I)
                   for w in words)

    def _goal_row(self, gid):
        r = self._all("SELECT * FROM goal WHERE id=?", (gid,))
        if not r:
            raise KeyError(f"no goal {gid}")
        return r[0]

    @staticmethod
    def _goal_fields(g):
        g["title"] = (g["title"] or "").strip()
        if not g["title"]:
            raise ValueError("empty title")
        g["source"] = g.get("source") or "hand"
        if g["source"] not in GOAL_SOURCES:
            raise ValueError("bad source")
        g["target"] = float(g.get("target") or 0)
        g["base"] = float(g.get("base") or 0)
        if g["source"] == "steps":
            g["target"] = max(g["target"], 1.0)
        elif g["source"] == "value":
            if g["target"] == g["base"]:
                raise ValueError("the target must differ from where you start")
        elif g["target"] <= 0:
            raise ValueError("target must be above 0")
        for k in ("deadline", "start"):
            if g.get(k):
                dt.date.fromisoformat(g[k])
            else:
                g[k] = None
        g["period"] = g.get("period") or ""
        if g["period"] not in ("", "week", "month"):
            raise ValueError("bad period")
        g["status"] = g.get("status") or "active"
        if g["status"] not in GOAL_STATUS:
            raise ValueError("bad status")
        g["match"] = ", ".join(Store._words(g.get("match")))
        if g["source"] in ("calendar", "tasks_word") and not g["match"]:
            raise ValueError("type the word to look for")
        g["unit"] = "hours" if g["source"] in ("focus_all", "focus_word") else (g.get("unit") or "").strip()
        g["why"] = (g.get("why") or "").strip()
        g["step"] = float(g.get("step") or 1)
        if g["step"] <= 0:
            raise ValueError("the +1 amount must be above 0")
        g["pos"] = float(g.get("pos") or 0)
        g["mode"] = {"linked": "tasks", "focus_all": "focus", "focus_word": "focus"}.get(g["source"], "typed")
        return g

    def add_goal(self, title, target=None, unit="", deadline=None, mode=None):
        """add_goal({fields}) from the app. The old (title, target, unit, deadline, mode) form still works."""
        f = dict(title) if isinstance(title, dict) else {
            "title": title, "target": target, "unit": unit, "deadline": deadline,
            "source": {"tasks": "linked", "focus": "focus_word", "typed": "hand"}.get(mode or "tasks", mode)}
        bad = set(f) - set(self.GOAL_FIELDS)
        if bad:
            raise ValueError(f"cannot set {sorted(bad)}")
        g = self._goal_fields(f)
        with self.lock:
            if not f.get("pos"):
                g["pos"] = self._all("SELECT COALESCE(MAX(pos),0)+1 p FROM goal")[0]["p"]
            cur = self._q(
                "INSERT INTO goal(title,target,unit,deadline,mode,typed,created,source,match,start,period,"
                "status,why,step,base,pos) VALUES(?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?)",
                (g["title"], g["target"], g["unit"], g["deadline"], g["mode"], self.today(), g["source"],
                 g["match"], g["start"], g["period"], g["status"], g["why"], g["step"], g["base"], g["pos"]))
            return self.goal(cur.lastrowid)

    def update_goal(self, gid, fields):
        fields = dict(fields)
        typed = fields.pop("typed", None)           # old name for "set the number to"
        if "mode" in fields:
            m = fields.pop("mode")
            fields["source"] = {"tasks": "linked", "focus": "focus_word", "typed": "hand"}.get(m, m)
        bad = set(fields) - set(self.GOAL_FIELDS)
        if bad:
            raise ValueError(f"cannot change {sorted(bad)}")
        with self.lock:
            g = self._goal_fields({**self._goal_row(gid), **fields})
            self._q("UPDATE goal SET title=?,target=?,unit=?,deadline=?,mode=?,source=?,match=?,start=?,period=?,"
                    "status=?,why=?,step=?,base=?,pos=? WHERE id=?",
                    (g["title"], g["target"], g["unit"], g["deadline"], g["mode"], g["source"], g["match"],
                     g["start"], g["period"], g["status"], g["why"], g["step"], g["base"], g["pos"], gid))
            if typed is not None:
                now = self.goal(gid)["done"]
                amount = float(typed) if g["source"] == "value" else float(typed) - now
                if amount or g["source"] == "value":
                    self.log_goal(gid, amount)
            return self.goal(gid)

    def delete_goal(self, gid):
        with self.lock:
            self._q("UPDATE task SET goal_id=NULL WHERE goal_id=?", (gid,))
            self._q("UPDATE habit SET goal_id=NULL WHERE goal_id=?", (gid,))
            self._q("UPDATE vision SET goal_id=NULL WHERE goal_id=?", (gid,))
            self._q("DELETE FROM goal_log WHERE goal_id=?", (gid,))
            self._q("DELETE FROM goal_step WHERE goal_id=?", (gid,))
            self._q("DELETE FROM goal WHERE id=?", (gid,))

    def log_goal(self, gid, amount, day=None, note=""):
        """Add a number by hand. For a 'value' goal (weight) it is the new reading, not a step."""
        g = self._goal_row(gid)
        amount = float(amount)
        if not amount and g["source"] != "value":
            raise ValueError("type a number")
        day = day or self.today()
        dt.date.fromisoformat(day)
        if day > self.today():
            raise ValueError("that day has not come yet")
        cur = self._q("INSERT INTO goal_log(goal_id,day,amount,note,created) VALUES(?,?,?,?,?)",
                      (gid, day, amount, (note or "").strip()[:200], self.clock()))
        return {**self.goal(gid), "log_id": cur.lastrowid}

    def delete_goal_log(self, lid):
        r = self._all("SELECT goal_id FROM goal_log WHERE id=?", (lid,))
        if not r:
            raise KeyError(f"no entry {lid}")
        self._q("DELETE FROM goal_log WHERE id=?", (lid,))
        return self.goal(r[0]["goal_id"])

    def add_goal_step(self, gid, title):
        self._goal_row(gid)
        title = (title or "").strip()
        if not title:
            raise ValueError("empty title")
        with self.lock:
            pos = self._all("SELECT COALESCE(MAX(pos),0)+1 p FROM goal_step WHERE goal_id=?", (gid,))[0]["p"]
            self._q("INSERT INTO goal_step(goal_id,title,pos) VALUES(?,?,?)", (gid, title, pos))
        return self.goal(gid)

    def update_goal_step(self, sid, fields):
        r = self._all("SELECT * FROM goal_step WHERE id=?", (sid,))
        if not r or set(fields) - {"title", "done"}:
            raise ValueError("bad step")
        st = {**r[0], **fields}
        st["title"] = (st["title"] or "").strip()
        if not st["title"]:
            raise ValueError("empty title")
        done = bool(st["done"])
        day = (r[0]["done_day"] or self.today()) if done else None
        self._q("UPDATE goal_step SET title=?,done=?,done_day=? WHERE id=?", (st["title"], int(done), day, sid))
        return self.goal(r[0]["goal_id"])

    def delete_goal_step(self, sid):
        r = self._all("SELECT goal_id FROM goal_step WHERE id=?", (sid,))
        if not r:
            raise KeyError(f"no step {sid}")
        self._q("DELETE FROM goal_step WHERE id=?", (sid,))
        return self.goal(r[0]["goal_id"])

    def _goal_days(self, g):
        """day -> how much the goal moved that day (what Nook saw + what was typed in)."""
        gid, src, words = g["id"], g["source"], self._words(g["match"])
        out = {}

        def add(day, v):
            out[day] = out.get(day, 0.0) + v

        for r in self._all("SELECT day, amount FROM goal_log WHERE goal_id=?", (gid,)):
            add(r["day"], r["amount"])
        if src in ("linked", "tasks_word"):
            for r in self._all("SELECT title, day, done_at, goal_id FROM task WHERE done=1"):
                if r["goal_id"] == gid or (src == "tasks_word" and self._hit(words, r["title"])):
                    add(day_of(r["done_at"]) if r["done_at"] else r["day"], 1)
            for r in self._all("SELECT t.day FROM habit_tick t JOIN habit h ON h.id=t.habit_id "
                               "WHERE h.goal_id=?", (gid,)):
                add(r["day"], 1)
        elif src in ("focus_all", "focus_word"):
            def mine(title, label, goal_id):
                return src == "focus_all" or goal_id == gid or self._hit(words, title) or self._hit(words, label)
            for r in self._all("SELECT s.day, s.end_ts-s.start_ts secs, s.label, t.title, t.goal_id FROM session s "
                               "LEFT JOIN task t ON t.id=s.task_id WHERE s.kind='focus'"):
                if mine(r["title"], r["label"], r["goal_id"]):
                    add(r["day"], r["secs"] / 3600)
            t = self._timer()
            if t["running"] and t["mode"] == "focus" and t["seg_start"]:
                task = self._all("SELECT title, goal_id FROM task WHERE id=?", (t["task_id"],)) if t["task_id"] else []
                title, goal_id = (task[0]["title"], task[0]["goal_id"]) if task else (None, None)
                if mine(title, t.get("label"), goal_id):
                    add(day_of(t["seg_start"]), max(0.0, min(self.clock(), t["end"]) - t["seg_start"]) / 3600)
        elif src == "calendar":
            today, now = self.today(), min_of(self.clock())
            hidden = set(self._get("hidden_events", []))
            for r in self._all("SELECT id, title, day, end_min FROM meeting WHERE day<=?", (today,)):
                over = r["day"] < today or r["end_min"] <= now          # only once it has happened
                if over and r["id"] not in hidden and self._hit(words, r["title"]):
                    add(r["day"], 1)
        elif src == "calls":
            # a recorded call where someone else spoke. A no-show has one speaker, so it never counts.
            for r in self._all("SELECT title, day FROM call WHERE speakers>=2 AND external=1"):
                if not words or self._hit(words, r["title"]):
                    add(r["day"], 1)
        return out

    def _pace(self, g, prog, tgt, days, today):
        if g["status"] != "active":
            return None
        if prog >= tgt:
            return {"state": "done"}
        T = dt.date.fromisoformat(today)
        if g["period"]:
            if g["period"] == "week":
                a, n = T - dt.timedelta(days=T.weekday()), 7
            else:
                a = T.replace(day=1)
                n = ((a + dt.timedelta(days=32)).replace(day=1) - a).days
            per_day = tgt / n
            exp = per_day * (T - a).days                    # where you should be when today starts
            state = "ahead" if prog > exp + per_day else "behind" if prog < exp - per_day * 0.5 else "on"
            return {"state": state, "left": tgt - prog, "per": g["period"]}
        if not g["deadline"]:
            return None
        end = dt.date.fromisoformat(g["deadline"])
        start = min(dt.date.fromisoformat(g["start"] or g["created"]), end)
        left_days = (end - T).days
        if left_days < 0:
            return {"state": "late"}
        total = max((end - start).days, 1)
        el = max(0, min((T - start).days, total))
        per_day = tgt / total
        exp = per_day * el
        state = "ahead" if prog > exp + per_day else "behind" if prog < exp - per_day else "on"
        need = (tgt - prog) if left_days < 7 else (tgt - prog) / left_days * 7
        if days is None:                                     # a moving number or steps: average since the start
            doing = prog / max(el, 1) * 7
        else:
            span = min(28, max(el, 1))
            since = (T - dt.timedelta(days=span - 1)).isoformat()
            doing = sum(v for d, v in days.items() if since <= d <= today) / span * 7
        return {"state": state, "need": need, "doing": doing, "week_only": left_days < 7}

    def goal(self, gid, detail=False):
        g = self._goal_row(gid)
        today, src = self.today(), g["source"]
        T = dt.date.fromisoformat(today)
        monday = (T - dt.timedelta(days=T.weekday())).isoformat()
        lo = g["start"] or ""
        if g["period"] == "week":
            lo = max(lo, monday)
        elif g["period"] == "month":
            lo = max(lo, today[:8] + "01")
        steps = self._all("SELECT * FROM goal_step WHERE goal_id=? ORDER BY pos, id", (gid,))
        days = None
        if src == "value":
            logs = self._all("SELECT amount FROM goal_log WHERE goal_id=? ORDER BY day, id", (gid,))
            done = logs[-1]["amount"] if logs else g["base"]
            span = g["target"] - g["base"]
            tgt, prog = abs(span), (done - g["base"]) / span * abs(span)
        elif src == "steps":
            done = prog = float(sum(1 for x in steps if x["done"]))
            tgt = g["target"] = float(max(len(steps), 1))
        else:
            days = self._goal_days(g)
            done = prog = sum(v for d, v in days.items() if lo <= d <= today)
            tgt = g["target"]
        g["done"] = done
        g["pct"] = max(0, min(100, round(100 * prog / tgt)))
        g["days_left"] = (dt.date.fromisoformat(g["deadline"]) - T).days if g["deadline"] else None
        g["pace"] = self._pace(g, prog, tgt, days, today)
        g["week"] = sum(v for d, v in (days or {}).items() if monday <= d <= today)
        g["habits"] = [{"id": h["id"], "title": h["title"], "streak": self.habit(h["id"])["streak"]}
                       for h in self._all("SELECT id,title FROM habit WHERE goal_id=? ORDER BY pos", (gid,))]
        g["tasks_today"] = [r["title"] for r in self._all(
            "SELECT title FROM task WHERE goal_id=? AND day=? ORDER BY pos", (gid, today))]
        g["steps_total"], g["steps_done"] = len(steps), sum(1 for x in steps if x["done"])
        if detail:
            for x in steps:
                x["done"] = bool(x["done"])
            g["steps"] = steps
            g["logs"] = self._all("SELECT * FROM goal_log WHERE goal_id=? ORDER BY day DESC, id DESC LIMIT 60", (gid,))
            weeks = []
            for i in range(11, -1, -1):
                a = T - dt.timedelta(days=T.weekday() + 7 * i)
                b = (a + dt.timedelta(days=6)).isoformat()
                weeks.append({"a": a.isoformat(),
                              "amount": sum(v for d, v in (days or {}).items() if a.isoformat() <= d <= b)})
            g["weeks"] = weeks if days is not None else []
            g["today"] = today
        return g

    def goals(self):
        return [self.goal(r["id"]) for r in self._all("SELECT id FROM goal ORDER BY pos, created, id")]

    # ---------- recorded calls (filled by the Fathom sync) ----------
    def save_calls(self, items):
        with self.lock:
            for c in items:
                self._q("INSERT OR REPLACE INTO call(id,title,day,mins,speakers,external,source) VALUES(?,?,?,?,?,?,?)",
                        (str(c["id"]), c.get("title") or "Call", c["day"], float(c.get("mins") or 0),
                         int(c.get("speakers") or 0), int(bool(c.get("external"))), c.get("source", "fathom")))

    def calls(self):
        return self._all("SELECT * FROM call ORDER BY day DESC, id DESC")

    # ---------- vision board ----------
    def _vision_dir(self):
        d = os.path.join(self.dir, "vision")
        os.makedirs(d, exist_ok=True)
        return d

    def vision(self):
        rows = self._all("SELECT * FROM vision ORDER BY pos, id")
        for r in rows:
            r["wide"] = bool(r["wide"])
        return rows

    def _vision_row(self, vid):
        r = self._all("SELECT * FROM vision WHERE id=?", (vid,))
        if not r:
            raise KeyError(f"no card {vid}")
        return r[0]

    def _vision_add(self, kind, file=None, text=""):
        with self.lock:
            pos = self._all("SELECT COALESCE(MAX(pos),0)+1 p FROM vision")[0]["p"]
            cur = self._q("INSERT INTO vision(kind,file,text,pos,created) VALUES(?,?,?,?,?)",
                          (kind, file, text, pos, self.clock()))
            return self._vision_row(cur.lastrowid)

    def add_vision_text(self, text):
        text = (text or "").strip()
        if not text:
            raise ValueError("write something")
        return self._vision_add("text", text=text[:400])

    def add_vision_image(self, b64):
        """A picture the page already shrank. Only real JPEG or PNG bytes are kept, under 3 MB."""
        raw = base64.b64decode((b64 or "").split(",")[-1], validate=False)
        if len(raw) > VISION_MAX:
            raise ValueError("that picture is too big")
        if raw[:3] == bytes([0xFF, 0xD8, 0xFF]):
            ext = ".jpg"
        elif raw[:8] == bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]):
            ext = ".png"
        else:
            raise ValueError("that is not a picture Nook can use")
        name = secrets.token_hex(12) + ext
        with open(os.path.join(self._vision_dir(), name), "wb") as f:
            f.write(raw)
        return self._vision_add("image", file=name)

    def vision_image(self, vid):
        r = self._vision_row(vid)
        if r["kind"] != "image" or not r["file"] or os.path.basename(r["file"]) != r["file"]:
            raise ValueError("no picture")
        with open(os.path.join(self._vision_dir(), r["file"]), "rb") as f:
            raw = f.read()
        mime = "image/png" if r["file"].endswith(".png") else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")

    def update_vision(self, vid, fields):
        bad = set(fields) - {"caption", "text", "goal_id", "wide", "pos"}
        if bad:
            raise ValueError(f"cannot change {sorted(bad)}")
        v = {**self._vision_row(vid), **fields}
        self._q("UPDATE vision SET caption=?,text=?,goal_id=?,wide=?,pos=? WHERE id=?",
                ((v["caption"] or "").strip()[:200], (v["text"] or "").strip()[:400],
                 self._check_goal(v["goal_id"]), int(bool(v["wide"])), float(v["pos"]), vid))
        return self._vision_row(vid)

    def delete_vision(self, vid):
        r = self._vision_row(vid)
        self._q("DELETE FROM vision WHERE id=?", (vid,))
        if r["file"] and os.path.basename(r["file"]) == r["file"]:
            try:
                os.remove(os.path.join(self._vision_dir(), r["file"]))
            except OSError:
                pass

    # ---------- progress ----------
    def progress(self, a, b):
        today = self.today()
        A, B = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        focus = self.focus_by_day(a, b)
        tasks = self.tasks(a, b)
        goal = self.settings()["goal_min"]
        days, d = [], A
        while d <= B:
            iso = d.isoformat()
            mine = [t for t in tasks if t["day"] == iso]
            days.append({"day": iso, "focus": focus.get(iso, 0),
                         "done": [t["title"] for t in mine if t["done"]],
                         "open": [t["title"] for t in mine if not t["done"]]})
            d += dt.timedelta(days=1)
        past = [x for x in days if x["day"] <= today]
        # same stretch of the period before, up to the same day
        n = (B - A).days + 1
        upto = min(B, dt.date.fromisoformat(today))
        pa = A - dt.timedelta(days=n)
        pb = pa + (upto - A) if upto >= A else pa
        prev = sum(self.focus_by_day(pa.isoformat(), pb.isoformat()).values()) if upto >= A else 0
        best = max(past, key=lambda x: x["focus"], default=None)
        return {"a": a, "b": b, "today": today, "goal_min": goal, "days": days,
                "focus": sum(x["focus"] for x in days), "prev_focus": prev,
                "tasks_done": sum(len(x["done"]) for x in days),
                "hit": sum(1 for x in past if x["focus"] >= goal), "past_days": len(past),
                "habits": self.habits_kept(a, b),
                "best": best if best and best["focus"] > 0 else None}

    def year(self, y):
        focus = self.focus_by_day(f"{y}-01-01", f"{y}-12-31")
        months = [0.0] * 12
        for k, v in focus.items():
            months[int(k[5:7]) - 1] += v
        done = self._all("SELECT substr(day,6,2) m, COUNT(*) n FROM task WHERE done=1 AND day LIKE ? GROUP BY m",
                         (f"{y}-%",))
        tasks = [0] * 12
        for r in done:
            tasks[int(r["m"]) - 1] = r["n"]
        return {"year": y, "today": self.today(), "months": months, "tasks": tasks,
                "focus": sum(months), "tasks_done": sum(tasks), "goal_min": self.settings()["goal_min"],
                "hit": sum(1 for v in focus.values() if v >= self.settings()["goal_min"]),
                "habits": self.habits_kept(f"{y}-01-01", f"{y}-12-31")}
