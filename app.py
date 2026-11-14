"""Deepcus - Focus & Productivity Tool (was FocusOS). Run: pythonw app.py  (or the installed Deepcus.exe).
Two processes: this one (window, tray, app tracking, Google Calendar sync, agent API) and the taskbar
bar (`--bar`, started by this one and kept alive), so a stuck window never blanks the bar.
Flags: --hidden (start without the window, used by Start with Windows), --bar (the taskbar bar only)."""
import ctypes
import os
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)
RES = getattr(sys, "_MEIPASS", HERE)          # ui/, icon and the Google sign-in key ship here
sys.path.insert(0, HERE)
if __name__ == "__main__" and "--bar" in sys.argv:     # the taskbar bar: light, its own process
    import bar
    bar.main_process()
    sys.exit(0)
from store import Store  # noqa: E402
import tracker  # noqa: E402
import account  # noqa: E402
import calls  # noqa: E402
import agent_api  # noqa: E402
import sounds  # noqa: E402
import updater  # noqa: E402
from version import VERSION  # noqa: E402

account.CLIENT = os.path.join(RES, "google_client.json")
# each Windows user's own data, never inside the install folder
DATA = os.environ.get("FOCUSOS_DATA") or os.path.join(os.environ.get("LOCALAPPDATA", HERE), "FocusOS")
OLD_DATA = os.path.join(HERE, "data")         # where the dev copy kept it before 2026-11-11
LOG = os.path.join(DATA, "error.log")
ICON = os.path.join(RES, "build", "focusos.ico") if not FROZEN else os.path.join(RES, "focusos.ico")


def log_error(where):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            tb = traceback.format_exc()
            tb = "" if tb.startswith("NoneType: None") else tb     # a plain note, not an error
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {where}\n{tb}\n")
    except Exception:
        pass


class Api:
    """Everything the screens can ask for. Names starting with _ are hidden from the page."""

    def __init__(self, store, acct=None, upd=None):
        self._s = store
        self._acct = acct
        self._upd = upd

    # self-update (updater.py)
    def update_status(self):
        return self._upd.status() if self._upd else {"current": VERSION, "ready": False}

    def update_now(self):
        """Start the downloaded installer and close this app so it can be replaced."""
        if not self._upd or not self._upd.install():
            return False
        threading.Timer(0.6, lambda: os._exit(0)).start()
        return True

    # Google account + calendar
    def account_status(self):
        return self._acct.status()

    def skip_sign_in(self):
        return self._acct.skip()

    def sign_in(self):
        return self._acct.sign_in()

    def sign_out(self):
        return self._acct.sign_out()

    def sync_calendar(self):
        self._acct.sync()
        return self._acct.status()

    def _timer(self):
        return self._s.timer_state()            # the store plays the finish sound

    # reads
    def timer(self):
        return self._timer()

    def today_data(self):
        s = self._s
        d = s.today()
        t = self._timer()
        current = None
        if t["task_id"]:
            try:
                current = s.task(t["task_id"])
            except KeyError:
                pass
        return {"today": d, "tasks": s.tasks(d), "carry": s.carry(), "focused": s.focused(d),
                "timer": t, "current": current, "settings": s.settings(), "goals": self._goal_names()}

    def _goal_names(self):
        return [{"id": r["id"], "title": r["title"]} for r in self._s._all(
            "SELECT id,title FROM goal WHERE status IN ('active','paused') ORDER BY pos, created, id")]

    def day_data(self, day):
        s = self._s
        return {"today": s.today(), "day": day, "tasks": s.tasks(day), "meetings": s.meetings(day),
                "lane": s.lane(day), "summary": s.summary(day), "focused": s.focused(day),
                "timer": self._timer(), "settings": s.settings(), "goals": self._goal_names()}

    def range_data(self, a, b):
        s = self._s
        return {"today": s.today(), "tasks": s.tasks(a, b), "meetings": s.meetings(a, b),
                "focus": s.focus_by_day(a, b), "timer": self._timer(), "settings": s.settings()}

    # writes
    def add_task(self, title, day=None, start_min=None, end_min=None):
        return self._s.add_task(title, day, start_min, end_min)

    def update_task(self, tid, fields):
        return self._s.update_task(int(tid), fields)

    def delete_task(self, tid):
        self._s.delete_task(int(tid))
        return True

    def move_to_today(self):
        self._s.move_to_today()
        return True

    def timer_start(self, task_id=None, mode=None):
        return self._s.timer_start(int(task_id) if task_id is not None else None, mode)

    def timer_pause(self):
        return self._s.timer_pause()

    def timer_length(self, mins):
        return self._s.timer_length(mins)

    def timer_label(self, label):
        return self._s.timer_label(label)

    def timer_unlabel(self):
        return self._s.timer_unlabel()

    def sound_styles(self):
        return [[k, v] for k, v in sounds.library()]

    def preview_sound(self, name, style):
        sounds.play(name, style)
        return True

    def timer_reset(self):
        return self._s.timer_reset()

    def timer_dismiss(self):
        return self._s.timer_dismiss()

    def set_setting(self, k, v):
        return self._s.set_setting(k, v)

    # habits
    def habits_data(self):
        s = self._s
        return {"today": s.today(), "habits": s.habits(), "goals": [{"id": g["id"], "title": g["title"]}
                                                                      for g in s.goals()],
                "focused": s.focused(s.today()), "settings": s.settings()}

    def habit_detail(self, hid):
        s = self._s
        h = s.habit_detail(int(hid))
        h["goal"] = s.goal(h["goal_id"])["title"] if h["goal_id"] else None
        return {"today": s.today(), "habit": h, "focused": s.focused(s.today()), "settings": s.settings(),
                "goals": [{"id": g["id"], "title": g["title"]} for g in s.goals()]}

    def add_habit(self, title, days=None, goal_id=None):
        return self._s.add_habit(title, days, goal_id)

    def update_habit(self, hid, fields):
        return self._s.update_habit(int(hid), fields)

    def delete_habit(self, hid):
        self._s.delete_habit(int(hid))
        return True

    def tick_habit(self, hid, day=None, on=True):
        return self._s.tick_habit(int(hid), day, on)

    # goals
    def goals_data(self):
        s = self._s
        return {"today": s.today(), "goals": s.goals(), "focused": s.focused(s.today()), "settings": s.settings(),
                "calls": self._calls_status()}

    def goal_detail(self, gid):
        s = self._s
        return {"today": s.today(), "goal": s.goal(int(gid), detail=True), "goals": self._goal_names(),
                "focused": s.focused(s.today()), "settings": s.settings(), "calls": self._calls_status()}

    def add_goal(self, fields):
        return self._s.add_goal(fields)

    def log_goal(self, gid, amount, day=None, note=""):
        return self._s.log_goal(int(gid), amount, day, note)

    def delete_goal_log(self, lid):
        return self._s.delete_goal_log(int(lid))

    def add_goal_step(self, gid, title):
        return self._s.add_goal_step(int(gid), title)

    def update_goal_step(self, sid, fields):
        return self._s.update_goal_step(int(sid), fields)

    def delete_goal_step(self, sid):
        return self._s.delete_goal_step(int(sid))

    # recorded calls (Fathom). The key stays on this PC.
    def _calls_status(self):
        st = dict(self._s._get("fathom", None) or {})
        st["connected"] = bool(self._s._get("fathom_key", ""))
        return st

    def calls_status(self):
        return self._calls_status()

    def calls_connect(self, key):
        key = (key or "").strip()
        if key:
            calls.sync(self._s, key)                 # raises with the reason when the key is wrong
        self._s._set("fathom_key", key)
        if not key:
            self._s._set("fathom", {})
        return self._calls_status()

    def calls_sync(self):
        calls.sync_quiet(self._s)
        return self._calls_status()

    # calendar extras
    def duplicate_task(self, tid):
        return self._s.duplicate_task(int(tid))

    def hide_event(self, mid, on=True):
        return self._s.hide_event(str(mid), bool(on))

    def show_all_events(self):
        return self._s.show_all_events()

    def hidden_events(self):
        return len(self._s._get("hidden_events", []))

    # vision board
    def vision_data(self):
        s = self._s
        return {"today": s.today(), "cards": s.vision(), "goals": s.goals(), "focused": s.focused(s.today()),
                "settings": s.settings()}

    def add_vision_image(self, b64):
        return self._s.add_vision_image(b64)

    def add_vision_text(self, text):
        return self._s.add_vision_text(text)

    def vision_image(self, vid):
        return self._s.vision_image(int(vid))

    def update_vision(self, vid, fields):
        return self._s.update_vision(int(vid), fields)

    def delete_vision(self, vid):
        self._s.delete_vision(int(vid))
        return True

    def update_goal(self, gid, fields):
        return self._s.update_goal(int(gid), fields)

    def delete_goal(self, gid):
        self._s.delete_goal(int(gid))
        return True

    # progress
    def progress_data(self, a, b):
        s = self._s
        out = s.progress(a, b)
        out.update({"focused": s.focused(s.today()), "settings": s.settings()})
        return out

    def year_data(self, y):
        s = self._s
        out = s.year(int(y))
        out.update({"focused": s.focused(s.today()), "settings": s.settings()})
        return out

    # start with Windows (a shortcut in the user's Startup folder)
    def autostart(self, on=None):
        if on is None:
            return os.path.exists(STARTUP_LNK)
        if on:
            make_startup_shortcut()
        elif os.path.exists(STARTUP_LNK):
            os.remove(STARTUP_LNK)
        return os.path.exists(STARTUP_LNK)


STARTUP_LNK = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup",
                           "Deepcus.lnk")
OLD_STARTUP_LNK = os.path.join(os.path.dirname(STARTUP_LNK), "Nook.lnk")      # the name before 1.3.0


def hang_watch(every=2, wait_ms=5000):
    """Black box for "Deepcus (Not Responding)". Every 2 s, ask the window to answer. If it does not answer
    within 5 s, write every thread's Python stack to DATA/hang.log once per freeze, so the next fix is
    made from evidence. A second guard: if this watcher itself cannot run for 60 s (the whole process is
    stuck), Python's faulthandler writes the stacks from C. (That one can also fire after the PC sleeps.)"""
    import faulthandler
    from ctypes import wintypes as wt
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                                      ctypes.POINTER(ctypes.c_size_t)]
    u.SendMessageTimeoutW.restype = ctypes.c_ssize_t
    u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    u.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    pid = os.getpid()

    def find():
        found = []

        def cb(h, _):
            p = wt.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value == pid:
                t, c = ctypes.create_unicode_buffer(64), ctypes.create_unicode_buffer(64)
                u.GetWindowTextW(h, t, 64)
                u.GetClassNameW(h, c, 64)
                if t.value.startswith("Deepcus") and c.value.startswith("WindowsForms"):
                    found.append(h)
                    return False
            return True
        u.EnumWindows(proc(cb), 0)
        return found[0] if found else None

    path = os.path.join(DATA, "hang.log")
    try:
        if os.path.exists(path) and os.path.getsize(path) > 1024 * 1024:
            os.replace(path, os.path.join(DATA, "hang.old.log"))
        f = open(path, "a", encoding="utf-8")
    except OSError:
        return
    hwnd, hung = None, False
    while True:
        faulthandler.dump_traceback_later(60, repeat=False, file=f)
        time.sleep(every)
        faulthandler.cancel_dump_traceback_later()
        try:
            if not hwnd or not u.IsWindow(hwnd):
                hwnd = find()
                if not hwnd:
                    continue
            res = ctypes.c_size_t()
            ok = u.SendMessageTimeoutW(hwnd, 0, 0, 0, 0x0002, wait_ms, ctypes.byref(res))   # WM_NULL
            if ok:
                if hung:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} window answers again\n\n")
                    f.flush()
                hung = False
            elif not hung:
                hung = True
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} Deepcus {VERSION}: window not answering "
                        f"(err {ctypes.get_last_error()}). Every thread right now:\n")
                f.flush()
                faulthandler.dump_traceback(file=f, all_threads=True)
                f.write("\n")
                f.flush()
        except Exception:
            log_error("hang_watch")
            time.sleep(30)


def start_bar(bar):
    """Start `--bar` unless one is running. Returns a function that says whether a bar is alive."""
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenMutexW.restype = ctypes.c_void_p
    k.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
    k.CloseHandle.argtypes = [ctypes.c_void_p]

    def alive():
        h = k.OpenMutexW(0x00100000, False, bar.BAR_MUTEX)       # SYNCHRONIZE
        if h:
            k.CloseHandle(h)
        return bool(h)

    if not alive():
        try:
            import subprocess
            subprocess.Popen(bar.app_cmd("--bar"), creationflags=0x08000000, close_fds=True)
        except Exception:
            log_error("start bar")
    return alive


def launch_cmd():
    """(program, arguments) that start this app: the installed exe, or pythonw + app.py from source."""
    if FROZEN:
        return sys.executable, ""
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-len("python.exe")] + "pythonw.exe"
    return exe, f'"{os.path.join(HERE, "app.py")}"'


def make_startup_shortcut():
    import subprocess
    exe, args = launch_cmd()
    q = lambda p: p.replace("'", "''")          # noqa: E731  PowerShell single-quote escape
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(STARTUP_LNK)}');"
          f"$s.TargetPath='{q(exe)}';$s.Arguments='{q((args + ' --hidden').strip())}';"
          f"$s.WorkingDirectory='{q(os.path.dirname(exe) if FROZEN else HERE)}';"
          f"$s.IconLocation='{q(exe if FROZEN else ICON)}';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True,
                   creationflags=0x08000000)


def migrate_old_data():
    """First run of the new layout: copy the dev copy's data (tasks, history, sign-in) into DATA once."""
    import shutil
    import sqlite3
    os.makedirs(DATA, exist_ok=True)
    new_db, old_db = os.path.join(DATA, "focusos.db"), os.path.join(OLD_DATA, "focusos.db")
    if FROZEN or os.path.exists(new_db) or not os.path.exists(old_db):
        return
    src, dst = sqlite3.connect(old_db), sqlite3.connect(new_db)
    with dst:
        src.backup(dst)                         # consistent copy even if something has it open
    src.close()
    dst.close()
    for name in ("google_token.json", "smarttrack.db", "smarttrack_rules.json"):
        if os.path.exists(os.path.join(OLD_DATA, name)):
            shutil.copy2(os.path.join(OLD_DATA, name), os.path.join(DATA, name))


def track_loop(store, every=5, idle_after=120):
    """Every 5 s: settle the timer, then note what is in front (unless away or tracking is off)."""
    while True:
        try:
            t = store.timer_state()
            st = store.settings()
            if st["tracking"] and tracker.idle_seconds() < idle_after:
                fg = tracker.foreground()
                if fg and fg[0] and fg[0].lower() not in tracker.SKIP:
                    app, cat = tracker.classify(fg[0], fg[1], st["rules"])
                    label = app
                    if t["running"] and t["mode"] == "focus" and t["task_id"] and cat != "distracted":
                        try:
                            label, cat = store.task(t["task_id"])["title"], "focus"
                        except KeyError:
                            pass
                    elif t["running"] and t["mode"] == "focus" and t.get("label") and cat != "distracted":
                        label, cat = t["label"], "focus"
                    store.track_sample(app, label, cat)
        except Exception:
            log_error("track_loop")
        time.sleep(every)


SHOW_EVENT = "FocusOS_Show_Window"


def main():
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    relaunches = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--relaunch=")), 0)
    for _ in range(40 if relaunches else 1):    # a relaunch waits for the old copy to finish closing
        h = kernel32.CreateMutexW(None, False, "FocusOS_App_Mutex")
        taken = kernel32.GetLastError() == 183
        if not taken:
            break
        kernel32.CloseHandle(h)
        time.sleep(0.25)
    if taken:                               # already running: bring that window up instead
        ev = kernel32.OpenEventW(0x0002, False, SHOW_EVENT)       # EVENT_MODIFY_STATE
        if ev:
            kernel32.SetEvent(ev)
        return
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LiyanShanvel.Deepcus")
    if os.path.exists(OLD_STARTUP_LNK):         # renamed from Nook: keep "start with Windows" working
        try:
            make_startup_shortcut()
            os.remove(OLD_STARTUP_LNK)
        except Exception:
            pass
    import bar
    bar_quit = kernel32.CreateEventW(None, True, False, bar.QUIT_EVENT)
    kernel32.ResetEvent(bar_quit)
    bar_alive = start_bar(bar)
    migrate_old_data()
    os.makedirs(DATA, exist_ok=True)
    store = Store(os.path.join(DATA, "focusos.db"))
    sounds.setup(DATA)
    store.on_sound = sounds.play
    acct = account.Account(store, DATA)
    threading.Thread(target=track_loop, args=(store,), daemon=True).start()
    threading.Thread(target=account.sync_loop, args=(acct,), daemon=True).start()
    threading.Thread(target=calls.sync_loop, args=(store,), daemon=True).start()
    agent_api.serve(store, DATA, VERSION, log_error)   # local API for Claude / bots (127.0.0.1 + token)
    upd = updater.Updater(DATA, log_error)
    if getattr(sys, "frozen", False):           # only the installed app updates itself, never a dev run
        upd.start()

    import webview
    hidden = "--hidden" in sys.argv
    win = webview.create_window("Deepcus", os.path.join(RES, "ui", "index.html"), js_api=Api(store, acct, upd),
                                width=1320, height=860, min_size=(1100, 700), background_color="#161618",
                                hidden=hidden)
    state = {"quitting": False, "visible": not hidden}

    def show():
        try:
            state["visible"] = True
            win.show()
            win.restore()
            win.on_top = True
            win.on_top = False
        except Exception:
            log_error("show")

    def quit_app(*_):
        state["quitting"] = True
        kernel32.SetEvent(bar_quit)             # the bar process quits with Deepcus
        try:
            win.destroy()
        finally:
            os._exit(0)

    def on_closing():
        if state["quitting"]:
            return True
        state["visible"] = False
        win.hide()                          # closing the window keeps Deepcus running in the tray
        return False

    win.events.closing += on_closing

    def wait_show():
        ev = kernel32.CreateEventW(None, False, False, SHOW_EVENT)
        while True:
            kernel32.WaitForSingleObject(ev, 0xFFFFFFFF)
            show()

    threading.Thread(target=wait_show, daemon=True).start()

    def tray():
        try:
            import pystray
            from PIL import Image
            menu = pystray.Menu(pystray.MenuItem("Open Deepcus", lambda: show(), default=True),
                                pystray.MenuItem("Quit Deepcus", quit_app))
            pystray.Icon("Deepcus", Image.open(ICON), "Deepcus", menu).run()
        except Exception:
            log_error("tray")

    threading.Thread(target=tray, daemon=True).start()

    def bar_keeper(every=5):
        """Restart the bar process if it ever stops (crash, its own stuck-watchdog, killed)."""
        quick = []
        while not state["quitting"]:
            time.sleep(every)
            if state["quitting"] or bar_alive():
                continue
            now = time.monotonic()
            quick = [t for t in quick if now - t < 600] + [now]
            if len(quick) > 5:                  # dying over and over: slow down, do not spin
                time.sleep(60)
            log_error(f"bar not running, starting it (restarts in 10 min: {len(quick)})")
            start_bar(bar)

    threading.Thread(target=bar_keeper, daemon=True).start()
    threading.Thread(target=hang_watch, daemon=True).start()
    webview.start(http_server=True)
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        os.makedirs(DATA, exist_ok=True)
        log_error("main")
        raise
