"""Agent API: lets an AI helper (Claude via MCP, or any bot on this PC) read and change Nook.

A small HTTP server inside the running app, on 127.0.0.1 only. Every call needs the token
kept in <data>/agent_token.txt. The tool list below is the one source for both this server
and the MCP bridge (nook_mcp.py), so the two never drift apart.

  GET  /v1/health          -> {"ok": true, "app": "Nook", "version": ...}   (no token needed)
  GET  /v1/tools           -> [{"name", "description", "input_schema"}]
  POST /v1/tools/<name>    body = the tool's arguments as JSON -> {"ok": true, "result": ...}
"""
import hmac
import json
import os
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("NOOK_API_PORT") or 47811)
TOKEN_FILE = "agent_token.txt"
MAX_BODY = 64 * 1024
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------- argument helpers ----------
def _day(v, name="day"):
    if v is None or v == "":
        return None
    if not isinstance(v, str) or not DAY_RE.match(v):
        raise ValueError(f"{name} must look like 2026-11-12")
    return v


def _min(v, name):
    """'09:30' -> 570. '24:00' is allowed for the end of the day."""
    if v is None or v == "":
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})$", str(v).strip())
    if not m or int(m.group(2)) > 59 or int(m.group(1)) > 24:
        raise ValueError(f"{name} must look like 09:30")
    return int(m.group(1)) * 60 + int(m.group(2))


def _hhmm(n):
    return None if n is None else f"{n // 60:02d}:{n % 60:02d}"


def _id(a, key="id"):
    if key not in a:
        raise ValueError(f"{key} is required")
    try:
        return int(a[key])
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number")


def _task_out(t):
    t = dict(t)
    t["start"], t["end"] = _hhmm(t.get("start_min")), _hhmm(t.get("end_min"))
    for k in ("start_min", "end_min", "pos", "created", "done_at"):
        t.pop(k, None)
    return t


def _goal_out(g):
    p = g.get("pace") or {}
    return {"id": g["id"], "title": g["title"], "source": g.get("source"), "status": g.get("status"),
            "done": round(g.get("done") or 0, 2), "target": g.get("target"), "unit": g.get("unit"),
            "pct": g.get("pct"), "period": g.get("period"), "deadline": g.get("deadline"),
            "pace": p.get("state")}


# ---------- tools ----------
def t_today(s, a):
    day = _day(a.get("day")) or s.today()
    return {"day": day,
            "tasks": [_task_out(t) for t in s.tasks(day)],
            "unfinished_from_before": len(s.carry()) if day == s.today() else None,
            "calendar": s.meetings(day),
            "habits": s.habits(),
            "goals": [_goal_out(g) for g in s.goals()],
            "focus_minutes": round(s.focused(day), 1)}


def t_list_tasks(s, a):
    a1 = _day(a.get("from"), "from") or s.today()
    b1 = _day(a.get("to"), "to") or a1
    return [_task_out(t) for t in s.tasks(a1, b1)]


def t_unfinished(s, a):
    return [_task_out(t) for t in s.carry()]


def t_add_task(s, a):
    t = s.add_task(a.get("title"), _day(a.get("day")), _min(a.get("start"), "start"), _min(a.get("end"), "end"))
    if a.get("goal_id") is not None:
        t = s.update_task(t["id"], {"goal_id": int(a["goal_id"])})
    return _task_out(t)


def t_update_task(s, a):
    tid = _id(a)
    f = {}
    if "title" in a:
        f["title"] = a["title"]
    if "day" in a:
        f["day"] = _day(a["day"]) or s.today()
    if "done" in a:
        f["done"] = bool(a["done"])
    if "goal_id" in a:
        f["goal_id"] = None if a["goal_id"] in (None, "") else int(a["goal_id"])
    if a.get("clear_time"):
        f["start_min"] = f["end_min"] = None
    elif "start" in a or "end" in a:
        f["start_min"], f["end_min"] = _min(a.get("start"), "start"), _min(a.get("end"), "end")
    if not f:
        raise ValueError("nothing to change")
    return _task_out(s.update_task(tid, f))


def t_delete_task(s, a):
    tid = _id(a)
    t = s.task(tid)
    s.delete_task(tid)
    return {"deleted": tid, "title": t["title"]}


def t_move_unfinished_to_today(s, a):
    n = len(s.carry())
    s.move_to_today()
    return {"moved": n}


def t_list_habits(s, a):
    return s.habits()


def t_add_habit(s, a):
    return s.add_habit(a.get("title"), a.get("days"), a.get("goal_id"))


def t_tick_habit(s, a):
    hid = _id(a)
    s.tick_habit(hid, _day(a.get("day")), bool(a.get("done", True)))
    return s.habit(hid)


def t_list_goals(s, a):
    return [_goal_out(g) for g in s.goals()]


def t_goal_detail(s, a):
    return s.goal(_id(a), detail=True)


GOAL_ARGS = ("title", "target", "unit", "deadline", "source", "match", "start", "period", "status", "why",
             "step", "base")


def t_add_goal(s, a):
    return _goal_out(s.add_goal({k: a[k] for k in GOAL_ARGS if k in a}))


def t_update_goal(s, a):
    f = {k: a[k] for k in GOAL_ARGS if k in a}
    if not f:
        raise ValueError("nothing to change")
    return _goal_out(s.update_goal(_id(a), f))


def t_log_goal(s, a):
    gid = _id(a)
    if a.get("amount") is None:
        raise ValueError("amount is required")
    s.log_goal(gid, float(a["amount"]), _day(a.get("day")), str(a.get("note") or ""))
    return _goal_out(s.goal(gid))


def t_calendar(s, a):
    a1 = _day(a.get("from"), "from") or s.today()
    b1 = _day(a.get("to"), "to") or a1
    return {"events": s.meetings(a1, b1), "tasks": [_task_out(t) for t in s.tasks(a1, b1)]}


def t_focus(s, a):
    a1 = _day(a.get("from"), "from") or s.today()
    b1 = _day(a.get("to"), "to") or a1
    return {d: round(m, 1) for d, m in sorted(s.focus_by_day(a1, b1).items())}


def t_timer(s, a):
    return s.timer_state()


def t_start_focus(s, a):
    tid = a.get("task_id")
    return s.timer_start(int(tid) if tid not in (None, "") else None)


def t_pause_focus(s, a):
    return s.timer_pause()


def _obj(props, req=()):
    return {"type": "object", "properties": props, "required": list(req), "additionalProperties": False}


DAY = {"type": "string", "description": "YYYY-MM-DD. Leave out for today."}
TIME = {"type": "string", "description": "24h time like 09:30"}
GOAL_PROPS = {
    "title": {"type": "string"},
    "target": {"type": "number", "description": "the number to reach"},
    "unit": {"type": "string", "description": "e.g. calls, kg, $, books, h"},
    "deadline": DAY,
    "source": {"type": "string", "enum": ["hand", "linked", "tasks_word", "focus_all", "focus_word",
                                          "calendar", "calls", "value", "steps"],
               "description": "what moves it: hand = logged by hand; linked = ticked linked tasks; "
                              "tasks_word / focus_word / calendar = items whose title has the word in 'match'; "
                              "focus_all = all focus hours; calls = Fathom sales calls; value = a number that "
                              "moves (base -> target); steps = a checklist"},
    "match": {"type": "string", "description": "the word to look for (for *_word and calendar)"},
    "start": DAY, "period": {"type": "string", "enum": ["", "week", "month"], "description": "repeat each"},
    "status": {"type": "string", "enum": ["active", "paused", "done", "archived"]},
    "why": {"type": "string"}, "step": {"type": "number", "description": "size of one + click"},
    "base": {"type": "number", "description": "starting value (for source=value)"},
}

TOOLS = {
    "get_today": (t_today, "Everything for one day: tasks, calendar events, habits, goals and focus minutes.",
                  _obj({"day": DAY})),
    "list_tasks": (t_list_tasks, "Tasks between two days (inclusive).", _obj({"from": DAY, "to": DAY})),
    "list_unfinished": (t_unfinished, "Unfinished tasks left on earlier days.", _obj({})),
    "add_task": (t_add_task, "Add a task. Give start and end together to put it on the calendar.",
                 _obj({"title": {"type": "string"}, "day": DAY, "start": TIME, "end": TIME,
                       "goal_id": {"type": "integer", "description": "goal this task counts toward"}},
                      ["title"])),
    "update_task": (t_update_task, "Change a task: rename, move day, set time, mark done, link a goal.",
                    _obj({"id": {"type": "integer"}, "title": {"type": "string"}, "day": DAY,
                          "start": TIME, "end": TIME, "clear_time": {"type": "boolean"},
                          "done": {"type": "boolean"}, "goal_id": {"type": ["integer", "null"]}}, ["id"])),
    "delete_task": (t_delete_task, "Delete a task for good. Only when the user asked for it.",
                    _obj({"id": {"type": "integer"}}, ["id"])),
    "move_unfinished_to_today": (t_move_unfinished_to_today, "Pull every unfinished past task into today.",
                                 _obj({})),
    "list_habits": (t_list_habits, "All habits with their streaks.", _obj({})),
    "add_habit": (t_add_habit, "Add a habit. days = weekdays it is due, 0=Mon..6=Sun (default every day).",
                  _obj({"title": {"type": "string"}, "days": {"type": "array", "items": {"type": "integer"}},
                        "goal_id": {"type": "integer"}}, ["title"])),
    "tick_habit": (t_tick_habit, "Mark a habit done (or not done) for a day.",
                   _obj({"id": {"type": "integer"}, "day": DAY, "done": {"type": "boolean"}}, ["id"])),
    "list_goals": (t_list_goals, "All goals with progress and pace (ahead / on track / behind).", _obj({})),
    "goal_detail": (t_goal_detail, "One goal with its log, steps and the last 12 weeks.",
                    _obj({"id": {"type": "integer"}}, ["id"])),
    "add_goal": (t_add_goal, "Create a goal and say what moves it.", _obj(GOAL_PROPS, ["title"])),
    "update_goal": (t_update_goal, "Change a goal's fields (pause, finish, new target...).",
                    _obj({"id": {"type": "integer"}, **GOAL_PROPS}, ["id"])),
    "log_goal": (t_log_goal, "Add progress to a goal (e.g. amount 1 = one more; for source=value, "
                             "the new reading).",
                 _obj({"id": {"type": "integer"}, "amount": {"type": "number"}, "day": DAY,
                       "note": {"type": "string"}}, ["id", "amount"])),
    "calendar": (t_calendar, "Calendar events and tasks between two days.", _obj({"from": DAY, "to": DAY})),
    "focus_minutes": (t_focus, "Focus minutes per day between two days.", _obj({"from": DAY, "to": DAY})),
    "timer_status": (t_timer, "The focus timer right now.", _obj({})),
    "start_focus": (t_start_focus, "Start the focus timer, optionally on a task.",
                    _obj({"task_id": {"type": "integer"}})),
    "pause_focus": (t_pause_focus, "Pause the focus timer.", _obj({})),
}


def tool_list():
    return [{"name": n, "description": d, "input_schema": sch} for n, (_, d, sch) in TOOLS.items()]


def run_tool(store, name, args):
    if name not in TOOLS:
        raise KeyError(f"no tool {name}")
    if not isinstance(args, dict):
        raise ValueError("arguments must be a JSON object")
    allowed = set(TOOLS[name][2]["properties"])
    bad = set(args) - allowed
    if bad:
        raise ValueError(f"unknown arguments {sorted(bad)}")
    return TOOLS[name][0](store, args)


# ---------- token ----------
def token(data_dir):
    """The secret every caller needs. Made once, kept in the data folder (never in the repo)."""
    p = os.path.join(data_dir, TOKEN_FILE)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            t = f.read().strip()
        if len(t) >= 32:
            return t
    t = secrets.token_urlsafe(32)
    with open(p, "w", encoding="utf-8") as f:
        f.write(t)
    return t


# ---------- server ----------
def make_server(store, tok, version="", port=PORT, log=None):
    lock = threading.Lock()     # one agent call at a time; the store has its own lock too

    class H(BaseHTTPRequestHandler):
        server_version = "Nook"

        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _guard(self, need_token=True):
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):        # blocks DNS-rebinding tricks
                self._send(403, {"ok": False, "error": "bad host"})
                return False
            if self.headers.get("Origin"):                      # web pages may not call this
                self._send(403, {"ok": False, "error": "browsers not allowed"})
                return False
            if need_token:
                got = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
                if not hmac.compare_digest(got.encode(), tok.encode()):
                    self._send(401, {"ok": False, "error": "bad or missing token"})
                    return False
            return True

        def do_GET(self):
            if self.path == "/v1/health":
                if self._guard(need_token=False):
                    self._send(200, {"ok": True, "app": "Nook", "version": version})
            elif self.path == "/v1/tools":
                if self._guard():
                    self._send(200, {"ok": True, "tools": tool_list()})
            else:
                self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            if not self.path.startswith("/v1/tools/"):
                return self._send(404, {"ok": False, "error": "not found"})
            if not self._guard():
                return
            name = self.path[len("/v1/tools/"):]
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._send(413, {"ok": False, "error": "too big"})
            try:
                args = json.loads(self.rfile.read(n) or b"{}") if n else {}
            except ValueError:
                return self._send(400, {"ok": False, "error": "body is not JSON"})
            try:
                with lock:
                    res = run_tool(store, name, args)
                self._send(200, {"ok": True, "result": res})
            except KeyError as e:
                self._send(404, {"ok": False, "error": str(e).strip("'\"")})
            except (ValueError, TypeError) as e:
                self._send(400, {"ok": False, "error": str(e)})
            except Exception as e:      # never crash the app over one bad call
                if log:
                    log(f"agent api {name}: {e!r}")
                self._send(500, {"ok": False, "error": "internal error"})

    return ThreadingHTTPServer(("127.0.0.1", port), H)


def serve(store, data_dir, version="", log=None):
    """Run forever in a daemon thread. A busy port just turns the API off; Nook keeps working."""
    try:
        srv = make_server(store, token(data_dir), version, log=log)
    except OSError as e:
        if log:
            log(f"agent api off: {e!r}")
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
