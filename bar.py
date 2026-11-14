"""Deepcus taskbar bar: Claude usage rings (only if Claude Code is signed in on this PC) + the Deepcus
focus timer and today's tasks. Runs inside the Deepcus app on its own thread; the timer and tasks are the
app's own (store.py), so the bar, the window and the calendar always agree. Copied from
E:/Liyan Shanvel/Taskbar Widget/widget.py on 2026-11-11."""
import ctypes
import ctypes.wintypes as wt
import datetime as dt
import json
import math
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
import winsound

from PIL import Image, ImageDraw, ImageFont, ImageTk

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
DATA = HERE          # set by run()
FONT = os.path.join(HERE, "ui", "Inter-widget.ttf")  # Inter with tnum + cv11 baked in
SETTINGS = None      # set by run()
CREDS = os.path.expanduser(r"~\.claude\.credentials.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
USAGE_PAGE = "https://claude.ai/settings/usage"
POLL_USAGE_S = 90
SS = 4  # supersampling for shapes

# ---- design tokens (design/DESIGN.md) ----
FG = (255, 255, 255)
FG2_A, FG3_A = 0.55, 0.45     # muted text, faint text
TRACK_A = 0.14                # bar ring track
WEEK_A = 0.55                 # week ring / weekly bar
HOVER_A = 0.10                # hover pill on bar + popup buttons
PAD_X, GAP_ITEMS, GAP_IN, GAP_USAGE = 14, 22, 6, 8
CARD = (31, 31, 33)           # popup card (rgba(32,32,34,.86) over a dark desktop)
ALERT_STEPS = [70, 80, 90, None]

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.FindWindowW.restype = ctypes.c_void_p
user32.GetAncestor.restype = ctypes.c_void_p
user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
user32.GetAsyncKeyState.restype = ctypes.c_short

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

S = 1.0  # DPI scale, set at start
HEART = {"at": time.monotonic(), "starts": 0}   # the app's watchdog reads this: a stale beat = a stuck bar


def beat():
    HEART["at"] = time.monotonic()


def log(where):
    """Append the current error to DATA/error.log; keep the file small (one old copy)."""
    import traceback
    try:
        path = os.path.join(DATA, "error.log")
        if os.path.exists(path) and os.path.getsize(path) > 512 * 1024:
            os.replace(path, os.path.join(DATA, "error.old.log"))
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {where}\n{traceback.format_exc()}\n")
    except Exception:
        pass


# ---------- helpers ----------
def over(base, a, top=FG):
    """colour `top` at alpha a over `base`"""
    return tuple(int(round(b + (t - b) * a)) for b, t in zip(base, top))


def lerp(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


_fonts = {}


def font(px, weight):
    k = (px, weight)
    if k not in _fonts:
        f = ImageFont.truetype(FONT, max(8, int(round(px * S))))
        f.set_variation_by_axes([min(32, max(14, px)), weight])  # opsz, wght
        _fonts[k] = f
    return _fonts[k]


def screen_geometry():
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    work = wt.RECT()
    user32.SystemParametersInfoW(0x30, 0, ctypes.byref(work), 0)
    return sw, sh, sh - work.bottom


def sample_taskbar_colour(x, y):
    hdc = user32.GetDC(0)
    c = gdi32.GetPixel(hdc, x, y)
    user32.ReleaseDC(0, hdc)
    if c == 0xFFFFFFFF:
        return (28, 28, 28)
    return (c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF)


def fullscreen_state():
    """What Windows itself reports: 2 = fullscreen app, 3 = fullscreen game, 4 = presentation."""
    st = ctypes.c_int(0)
    try:
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(st)) != 0:
            return 0
    except Exception:
        return 0
    return st.value


def cursor_pos():
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def mouse_down():
    return bool((user32.GetAsyncKeyState(0x01) | user32.GetAsyncKeyState(0x02)) & 0x8000)


def hwnd_of(widget):
    return user32.GetAncestor(widget.winfo_id(), 2)  # GA_ROOT


def no_activate(hwnd):
    style = user32.GetWindowLongW(hwnd, -20)
    user32.SetWindowLongW(hwnd, -20, style | 0x80 | 0x08000000)  # TOOLWINDOW | NOACTIVATE


def round_corners(hwnd, border):
    try:
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 33, ctypes.byref(ctypes.c_int(2)), 4)
        dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 34,
                                  ctypes.byref(ctypes.c_int(border[0] | border[1] << 8 | border[2] << 16)), 4)
    except Exception:
        pass


def fmt_min(m):
    h, mm = divmod(int(m), 60)
    return f"{h}h {mm}m" if h else f"{mm}m"


def fmt_clock(t):
    return t.astimezone().strftime("%I:%M %p").lstrip("0")


def mins_until(t):
    return max(0.0, (t - dt.datetime.now(dt.timezone.utc)).total_seconds() / 60)


def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"alert": 80}


def save_settings(st):
    try:
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except Exception:
        pass


# ---------- drawing primitives (at SS scale) ----------
def ring(g, cx, cy, r, w, colour, pct=None):
    """SVG-style stroke-centred circle from 12 o'clock, clockwise, round caps. pct=None = full track."""
    ro = r + w / 2
    sweep = 360 if pct is None else 360 * min(pct, 100) / 100
    g.arc([(cx - ro) * SS, (cy - ro) * SS, (cx + ro) * SS, (cy + ro) * SS], -90, -90 + sweep,
          fill=colour, width=max(1, int(round(w * SS))))
    if pct is not None and sweep < 360:
        for ang in (-90, -90 + sweep):
            px, py = cx + r * math.cos(math.radians(ang)), cy + r * math.sin(math.radians(ang))
            dot(g, px, py, w / 2, colour)


def dot(g, x, y, r, colour):
    g.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=colour)


def rrect(g, x0, y0, x1, y1, r, colour):
    g.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=r * SS, fill=colour)


def polyline(g, pts, w, colour):
    g.line([(x * SS, y * SS) for x, y in pts], fill=colour, width=max(1, int(round(w * SS))), joint="curve")
    for x, y in (pts[0], pts[-1]):
        dot(g, x, y, w / 2, colour)


def icon(g, name, ox, oy, size, colour):
    """The popup's 16-unit line icons (refresh / bell / open), stroke 1.6."""
    k = size / 16
    P = lambda x, y: (ox + x * k, oy + y * k)
    w = 1.6 * k
    if name == "refresh":
        (x0, y0), (x1, y1) = P(2.5, 2.5), P(13.5, 13.5)
        g.arc([x0 * SS, y0 * SS, x1 * SS, y1 * SS], 0, 315, fill=colour, width=max(1, int(round(w * SS))))
        dot(g, *P(13.5, 8), w / 2, colour)
        polyline(g, [P(13.5, 2.5), P(13.5, 5.5), P(10.5, 5.5)], w, colour)
    elif name == "bell":
        (x0, y0), (x1, y1) = P(4, 3), P(12, 11)
        g.arc([x0 * SS, y0 * SS, x1 * SS, y1 * SS], 180, 360, fill=colour, width=max(1, int(round(w * SS))))
        polyline(g, [P(4, 7), P(4, 11), P(3, 12.5), P(13, 12.5), P(12, 11), P(12, 7)], w, colour)
        (x0, y0), (x1, y1) = P(6.5, 12.5), P(9.5, 15.5)
        g.arc([x0 * SS, y0 * SS, x1 * SS, y1 * SS], 0, 180, fill=colour, width=max(1, int(round(w * SS))))
    elif name == "open":
        polyline(g, [P(9, 3), P(13, 3), P(13, 7)], w, colour)
        polyline(g, [P(13, 3), P(7.5, 8.5)], w, colour)
        polyline(g, [P(12, 10), P(12, 13), P(3, 13), P(3, 4), P(6, 4)], w, colour)


# ---------- Claude usage ----------
class Usage:
    """Polls Claude usage. The last good reading is cached on disk so a restart shows numbers at once
    without a fetch; a 429 (too many requests) backs off instead of showing an error."""
    CACHE = None     # set by run()
    _one = None
    _one_lock = threading.Lock()

    @classmethod
    def shared(cls, poll=True):
        """ONE poller per process. The bar rebuilds its Widget after sleep, a screen change or an Explorer
        restart; each rebuild used to start a new poller and the old ones never stopped, so several asked
        Anthropic every 90 s, got 429 (too many requests), and the shown reading froze (2026-11-13)."""
        with cls._one_lock:
            if cls._one is None:
                cls._one = cls()
                if poll:
                    threading.Thread(target=cls._one.loop, daemon=True).start()
            return cls._one

    def __init__(self):
        self.five = None   # (pct, resets_at)
        self.week = None
        self.error = ""
        self.fetched_at = 0.0
        self.last_try = 0.0
        self.wait = POLL_USAGE_S
        self.lock = threading.Lock()
        self.plan = ""
        try:
            with open(CREDS, encoding="utf-8") as f:
                self.plan = (json.load(f)["claudeAiOauth"].get("subscriptionType") or "").title()
        except Exception:
            pass
        try:
            with open(self.CACHE, encoding="utf-8") as f:
                c = json.load(f)
            self._apply(c["data"])
            self.fetched_at = c["at"]
        except Exception:
            pass

    def _apply(self, data):
        with self.lock:
            self.five = self._window(data.get("five_hour"))
            self.week = self._window(data.get("seven_day"))

    def fetch(self):
        self.last_try = time.time()
        try:
            with open(CREDS, encoding="utf-8") as f:
                token = json.load(f)["claudeAiOauth"]["accessToken"]
            req = urllib.request.Request(USAGE_URL, headers={
                "Authorization": "Bearer " + token,
                "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": "taskbar-widget",
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))
            self._apply(data)
            with self.lock:
                self.error, self.wait, self.fetched_at = "", POLL_USAGE_S, time.time()
            try:
                with open(self.CACHE, "w", encoding="utf-8") as f:
                    json.dump({"at": self.fetched_at, "data": data}, f)
            except Exception:
                pass
        except urllib.error.HTTPError as e:
            with self.lock:
                if e.code == 429:
                    ra = e.headers.get("Retry-After")
                    self.wait = min(300, max(int(ra) if ra and ra.isdigit() else 0, self.wait * 2))
                    self.error = "Busy, retrying" if self.five else "Updating…"  # a throttle is not a reading
                else:
                    self.error = "Sign in to Claude Code" if e.code == 401 else f"Error {e.code}"
        except Exception:
            with self.lock:
                self.error = "Offline"  # keep last good numbers

    def refresh(self):
        if time.time() - self.last_try > 15:  # a button mash must not trigger a 429
            threading.Thread(target=self.fetch, daemon=True).start()

    @staticmethod
    def _window(w):
        if not w or w.get("utilization") is None:
            return None
        ra = w.get("resets_at")
        return float(w["utilization"]), (dt.datetime.fromisoformat(ra) if ra else None)

    def loop(self):
        age = time.time() - self.fetched_at
        if age < POLL_USAGE_S:
            time.sleep(POLL_USAGE_S - age)
        while True:
            self.fetch()
            time.sleep(self.wait)


# ---------- Focus timer + today's tasks (design/focus-widget.html, turn 8) ----------
MODES = (("focus", "Focus"), ("short", "Short"), ("long", "Long"))
GOAL_SESSIONS = 4


def chime():
    threading.Thread(target=lambda: [winsound.MessageBeep(winsound.MB_ICONASTERISK) for _ in range(2)],
                     daemon=True).start()


class Focus:
    """The bar's view of the Deepcus timer + today's tasks. Reads and writes the app's store."""

    def __init__(self, store):
        self.s, self._at, self.sound = store, 0.0, False
        self.refresh(force=True)

    def refresh(self, force=False):
        now = time.time()
        if not force and now - self._at < 0.5:
            return
        self._at = now
        t = self.s.timer_state()            # the store plays the finish sound
        st, day = self.s.settings(), self.s.today()
        self.durs = {m: int(st[m]) * 60 for m in ("focus", "short", "long")}
        self.tot = t["total"]                       # a task's own length wins over the default
        self.name = t.get("label")                  # a focus with just a name, no task
        self.mode, self.running, self.end = t["mode"], t["running"], t["end"]
        self.left, self.just_done, self.done_mode = t["remaining"], t["just_done"], t.get("done_mode")
        self.current = t["task_id"]
        hidden = set(self.s._get("bar_hidden", {}).get(day, []))
        self.todos = [{"id": x["id"], "text": x["title"], "done": bool(x["done"])}
                      for x in self.s.tasks(day) if x["id"] not in hidden]
        self.focused_min = int(self.s.focused(day))

    def update(self):
        self.refresh()

    def save(self):
        self.refresh(force=True)

    def sync_sound(self):
        pass

    # --- reading ---
    def total(self):
        return self.tot

    def remaining(self):
        return max(0.0, self.end - time.time()) if self.running else self.left

    def cur(self):
        return next((t for t in self.todos if t["id"] == self.current and not t["done"]), None)

    def clock(self):
        r = int(math.ceil(self.remaining()))
        return f"{r // 60}:{r % 60:02d}"

    def bar(self):
        """What the taskbar item shows: (kind, bold, muted, timer %, tasks done %)."""
        total, rem = self.total(), self.remaining()
        p = (1 - rem / total) * 100 if total else 0
        goal = (sum(1 for t in self.todos if t["done"]) / len(self.todos) * 100 if self.todos else 0)
        brk = self.mode != "focus"
        if self.just_done and not self.running:
            if self.done_mode == "focus":
                return "done", "Done", f"Take {self.durs['short'] // 60} min", 0, goal
            return "done", "Break over", "Back to it", 0, goal
        if self.running:
            return ("break" if brk else "running"), self.clock(), ("Break" if brk else "Focus"), p, goal
        if rem < total:
            return ("break" if brk else "paused"), self.clock(), ("Break" if brk else "Paused"), p, goal
        if brk:
            return "break", self.clock(), "Break", 0, goal
        left = sum(1 for t in self.todos if not t["done"])
        return "idle", "Focus", (f"{left} task{'s' if left != 1 else ''} left" if left else fmt_min(total / 60)), 0, goal

    # --- actions ---
    def toggle(self):
        self.refresh(force=True)
        if self.running:
            self.s.timer_pause()
        elif self.just_done and self.done_mode == "focus":
            self.s.timer_start(None, "short")
        elif self.just_done:
            self.s.timer_start(None, "focus")
        else:
            self.s.timer_start()

    def reset(self):
        self.refresh(force=True)
        self.s.timer_reset()

    def set_mode(self, m):
        self.refresh(force=True)
        self.s.timer_mode(m)

    def set_len(self, d):
        self.refresh(force=True)
        if self.running:
            return
        step, lo, hi = (5, 5, 120) if self.mode == "focus" else (1, 1, 30) if self.mode == "short" else (5, 5, 60)
        mins = max(lo, min(hi, self.tot // 60 + d * step))
        self.s.timer_length(mins)

    def run_task(self, tid):
        self.refresh(force=True)
        self.s.timer_start(tid)

    def add(self, text):
        self.refresh(force=True)
        self.s.add_task(text, self.s.today())

    def toggle_done(self, tid):
        self.refresh(force=True)
        t = next((x for x in self.todos if x["id"] == tid), None)
        if t:
            self.s.update_task(tid, {"done": not t["done"]})

    def select(self, tid):
        self.refresh(force=True)
        if not self.running:
            self.s.timer_select(tid)

    def clear_done(self):
        self.refresh(force=True)
        day = self.s.today()
        h = self.s._get("bar_hidden", {})
        h = {day: sorted(set(h.get(day, [])) | {t["id"] for t in self.todos if t["done"]})}
        self.s._set("bar_hidden", h)

    def toggle_sound(self):
        pass


# ---------- the bar ----------
class Widget:
    def __init__(self, store, open_app=None):
        global S
        self.settings = load_settings()
        self.open_app = open_app or (lambda: None)
        self.has_claude = os.path.exists(CREDS)
        self.usage = Usage.shared(self.has_claude)
        self.focus = Focus(store)

        sw, sh, tb_h = screen_geometry()
        self.geo = (sw, sh, tb_h)
        self.root = tk.Tk()
        self.root.report_callback_exception = lambda *a: log("bar callback")
        S = s = self.root.winfo_fpixels("1i") / 96.0
        if tb_h <= 0:
            tb_h = int(48 * s)
        self.H, self.W = tb_h, int(560 * s)
        self.base = sample_taskbar_colour(int(4 * s), sh - tb_h // 2)
        # the hover pill's resting colour: one step off the key, so it is invisible but still catches the mouse
        b = self.base
        self.plate = (b[0], b[1], b[2] + 1 if b[2] < 255 else b[2] - 1)

        key = "#%02x%02x%02x" % self.base
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=key)
        self.root.attributes("-transparentcolor", key)
        self.root.geometry(f"{self.W}x{self.H}+0+{sh - tb_h}")
        self.label = tk.Label(self.root, bd=0, bg=key)
        self.label.pack()

        self.label.bind("<Button-1>", self.on_click)
        self.label.bind("<Button-3>", lambda e: self.open_app())
        self.label.bind("<Motion>", self.on_move)
        self.label.bind("<Leave>", lambda e: self.set_hover(None))

        self.root.update_idletasks()
        self.hwnd = hwnd_of(self.label)
        no_activate(self.hwnd)
        self.tray = None
        self.fs = 0
        self.attach()

        self.spans = {}            # item -> (x0, x1) of its pill, in window px
        self.hover = None
        self.hv = {"claude": 0.0, "focus": 0.0}
        self.shown = {"five": 0.0, "week": 0.0}
        self.popup = None          # ClaudePopup or FocusPopup (one at a time)
        self.quitting = False
        self.dead = False          # True = this window is finished; run() builds a fresh one
        self.errors = 0
        self.hidden = False
        self.animating = False
        self.last_pct = None
        self.keep_on_top()
        self.tick()
        if os.environ.get("WIDGET_SELFTEST"):
            kind = "focus" if os.environ["WIDGET_SELFTEST"] == "focus" else "claude"
            self.root.after(2500, lambda: self.toggle_popup(kind))

    # --- window management ---
    def attach(self):
        """Make the taskbar our owner: an owned window is always drawn above its owner."""
        tray = user32.FindWindowW("Shell_TrayWnd", None)
        if tray and tray != self.tray:
            user32.SetWindowLongPtrW(self.hwnd, -8, tray)  # GWLP_HWNDPARENT
            self.tray = tray

    def raise_now(self):
        user32.SetWindowPos(self.hwnd, -1, 0, 0, 0, 0, 0x0013)  # TOPMOST, no move/size/activate

    def keep_on_top(self):
        if self.dead:
            return
        try:
            if not self.hidden:
                self.raise_now()
        except Exception:
            pass
        self.root.after(200, self.keep_on_top)

    def quit(self):
        self.quitting = True
        self.root.destroy()

    def rebuild(self, why):
        """Give up this window; run() makes a new one (Explorer restarted, screen or taskbar changed)."""
        if self.dead:
            return
        self.dead = True
        HEART["why"] = why
        try:
            if self.popup:
                self.popup.close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # --- input ---
    def pill_box(self):
        ph = min(40 * S, self.H - 8 * S)
        return self.H / 2 - ph / 2, self.H / 2 + ph / 2

    def item_at(self, x, y):
        top, bot = self.pill_box()
        if not (top <= y <= bot):
            return None
        for k, (a, b) in self.spans.items():
            if a <= x <= b:
                return k
        return None

    def screen_rect(self, item):
        a, b = self.spans.get(item, (0, 0))
        top, bot = self.pill_box()
        x0, y0 = self.root.winfo_rootx(), self.root.winfo_rooty()
        return x0 + a, y0 + top, x0 + b, y0 + bot

    def set_hover(self, item):
        if item != self.hover:
            self.hover = item
            self.root.config(cursor="hand2" if item else "")
            self._start_anim()

    def on_move(self, e):
        self.set_hover(self.item_at(e.x, e.y))

    def on_click(self, e):
        item = self.item_at(e.x, e.y)
        if item:
            self.toggle_popup(item)
        self.raise_now()

    def toggle_popup(self, kind):
        cur = self.popup
        if cur:
            cur.close()
        if not cur or cur.kind != kind:
            self.popup = ClaudePopup(self) if kind == "claude" else FocusPopup(self)
        self._start_anim()

    # --- loops ---
    def tick(self):
        """Once a second. One bad second must never stop the bar, so errors are logged and the loop goes on."""
        if self.dead:
            return
        beat()
        try:
            if not user32.IsWindow(ctypes.c_void_p(self.hwnd)):
                return self.rebuild("window gone")
            if screen_geometry() != self.geo:
                return self.rebuild("screen changed")
            self._tick()
            self.errors = 0
        except Exception:
            self.errors += 1
            if self.errors in (1, 10):
                log("bar tick")
            if self.errors >= 10:
                return self.rebuild("10 bad ticks")
        if not self.dead:
            self.root.after(1000, self.tick)

    def _tick(self):
        self.attach()
        self.fs = fullscreen_state()
        fs = self.fs in (2, 3, 4)
        if fs and not self.hidden:
            if self.popup:
                self.popup.close()
            self.root.withdraw(); self.hidden = True
        elif not fs and self.hidden:
            self.root.deiconify(); self.hidden = False
        self.focus.update()
        self.check_alert()
        if not self.hidden:
            self._start_anim()
            self.render()
        if self.popup:
            self.popup.render()
        self.write_status()

    def check_alert(self):
        with self.usage.lock:
            five = self.usage.five
        if not five:
            return
        pct, thr = five[0], self.settings.get("alert")
        if thr and self.last_pct is not None and self.last_pct < thr <= pct:
            threading.Thread(target=lambda: winsound.MessageBeep(winsound.MB_ICONEXCLAMATION), daemon=True).start()
            if not self.popup and not self.hidden:
                self.popup = ClaudePopup(self)
        self.last_pct = pct

    def targets(self):
        with self.usage.lock:
            five, week = self.usage.five, self.usage.week
        return {"five": five[0] if five else 0.0, "week": week[0] if week else 0.0}

    def _start_anim(self):
        if not self.animating:
            self.animating = True
            self.root.after(16, self._anim)

    def _anim(self):
        moving = False
        for k, t in self.targets().items():
            v = self.shown[k]
            if abs(t - v) > 0.15:
                self.shown[k] = v + (t - v) * 0.2
                moving = True
            else:
                self.shown[k] = t
        for k in self.hv:
            t = 1.0 if self.hover == k else 0.0
            if abs(self.hv[k] - t) > 0.03:
                self.hv[k] += (t - self.hv[k]) * 0.35
                moving = True
            else:
                self.hv[k] = t
        if not self.hidden:
            self.render()
        if moving:
            self.root.after(16, self._anim)
        else:
            self.animating = False

    # --- drawing ---
    def bar_text(self):
        with self.usage.lock:
            five, err = self.usage.five, self.usage.error
        if five and five[0] >= 100:
            bold, muted = "Limit", (f"Back at {fmt_clock(five[1])}" if five[1] else "")
        elif five:
            bold = f"{five[0]:.0f}%"
            muted = f"{fmt_min(mins_until(five[1]))} left" if five[1] else "not started"
        else:
            bold, muted = "–", "loading"
        return bold, (muted if err == "Busy, retrying" else (err or muted)), five   # a throttle keeps the time left

    def render(self):
        s, W, H, base = S, self.W, self.H, self.base
        fg2, track, week_c = over(base, FG2_A), over(base, TRACK_A), over(base, WEEK_A)
        hover_c = over(base, HOVER_A)
        cy = H / 2
        f_b, f_m = font(13, 600), font(13, 400)
        top, bot = self.pill_box()

        # layout first (design: Claude pill padding 0 10 0 6, focus pill 0 8)
        c_bold, c_muted, five = self.bar_text()
        ring_x = PAD_X * s
        c_tx = ring_x + (28 + GAP_USAGE) * s
        c_mx = c_tx + f_b.getlength(c_bold) + GAP_USAGE * s
        c_end = c_mx + f_m.getlength(c_muted)
        if self.has_claude:
            self.spans["claude"] = (ring_x - 6 * s, c_end + 10 * s)
        else:
            self.spans.pop("claude", None)
            c_end = ring_x - 6 * s - 14 * s
        fkind, f_bold, f_muted, f_pct, f_goal = self.focus.bar()
        f_muted = ellipsize(f_muted, f_m, 180 * s)
        f_pill = c_end + 14 * s
        f_ring = f_pill + 6 * s
        f_tx = f_ring + (28 + 8) * s
        f_mx = f_tx + f_b.getlength(f_bold) + 8 * s
        f_end = f_mx + f_m.getlength(f_muted)
        self.spans["focus"] = (f_pill, f_end + 10 * s)
        # paused = whole item at 60% (design 8b)
        dim = 0.6 if fkind == "paused" else 1.0
        f_fg, f_fg2 = over(base, dim), over(base, FG2_A * dim)

        big = Image.new("RGB", (W * SS, H * SS), base)
        g = ImageDraw.Draw(big)
        for k, (a, b) in self.spans.items():
            rrect(g, a, top, b, bot, 8 * s, self.plate)
        rcx = ring_x + 14 * s
        for r, pct, col in ((11, self.shown["week"], week_c), (6.5, self.shown["five"], FG)) if self.has_claude else ():
            ring(g, rcx, cy, r * s, 3.5 * s, track)
            if pct > 0.3:
                ring(g, rcx, cy, r * s, 3.5 * s, col, pct)
        fcx = f_ring + 14 * s
        # big ring = timer, small ring = tasks done today (his final pick 2026-11-12, after an A/B test)
        t_r, k_r = 11, 6.5
        if fkind == "done":
            # finished = the timer ring closes (no tick badge, no grey pill - his call 2026-11-12);
            # a finished break closes at 55%, like the break ring it was
            ring(g, fcx, cy, t_r * s, 3.5 * s, over(base, WEEK_A) if f_bold == "Break over" else f_fg)
            ring(g, fcx, cy, k_r * s, 3.5 * s, track)
            if f_goal > 0.3:
                ring(g, fcx, cy, k_r * s, 3.5 * s, week_c, f_goal)
        else:
            timer_c = over(base, WEEK_A) if fkind == "break" else f_fg
            ring(g, fcx, cy, t_r * s, 3.5 * s, track)
            if f_pct > 0.3:
                ring(g, fcx, cy, t_r * s, 3.5 * s, timer_c, f_pct)
            if fkind == "paused":
                rrect(g, f_ring + 10.5 * s, cy - 4 * s, f_ring + 12.7 * s, cy + 4 * s, 1 * s, f_fg)
                rrect(g, f_ring + 15.3 * s, cy - 4 * s, f_ring + 17.5 * s, cy + 4 * s, 1 * s, f_fg)
            else:
                ring(g, fcx, cy, k_r * s, 3.5 * s, track)
                if f_goal > 0.3:
                    ring(g, fcx, cy, k_r * s, 3.5 * s, week_c, f_goal)
        img = big.resize((W, H), Image.LANCZOS)
        d = ImageDraw.Draw(img)
        if self.has_claude:
            d.text((c_tx, cy), c_bold, font=f_b, fill=FG, anchor="lm")
            d.text((c_mx, cy), c_muted, font=f_m, fill=fg2, anchor="lm")
        d.text((f_tx, cy), f_bold, font=f_b, fill=f_fg, anchor="lm")
        d.text((f_mx, cy), f_muted, font=f_m, fill=f_fg2, anchor="lm")

        if os.environ.get("WIDGET_SNAPSHOT") and not getattr(self, "_snapped", False) and five \
                and abs(self.shown["five"] - five[0]) < 0.2:
            img.save(os.environ["WIDGET_SNAPSHOT"]); self._snapped = True
        self.last_img = img
        self.photo = ImageTk.PhotoImage(img, master=self.root)
        self.label.configure(image=self.photo)

    def write_status(self):
        try:
            with self.usage.lock:
                five, week, err = self.usage.five, self.usage.week, self.usage.error
            with open(os.path.join(DATA, "bar.status"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"five": five[0] if five else None, "week": week[0] if week else None,
                                    "err": err, "focus": self.focus.bar()[:3], "spans": self.spans,
                                    "popup": bool(self.popup), "hidden": self.hidden, "fs": self.fs,
                                    "owned": bool(self.tray), "at": dt.datetime.now().isoformat(timespec="seconds")}))
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


# ---------- popups ----------
class Popup:
    """Borderless card above the taskbar. Never steals focus; closes on any click outside it
    (except on `exempt`, the bar item that toggles it)."""

    def __init__(self, w, W, H, x, exempt=None):
        self.w, self.W, self.H, self.exempt = w, W, H, exempt
        self.closed = False
        self.hover = None
        sw, sh, tb_h = screen_geometry()
        x = int(max(6 * S, min(x, sw - W - 6 * S)))
        self.top = t = tk.Toplevel(w.root)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        t.geometry(f"{W}x{H}+{x}+{int(sh - tb_h - H - 8 * S)}")
        self.lbl = tk.Label(t, bd=0, bg="#%02x%02x%02x" % CARD)
        self.lbl.pack()
        t.update_idletasks()
        self.hwnd = hwnd_of(self.lbl)
        no_activate(self.hwnd)
        round_corners(self.hwnd, over(CARD, 0.14))
        self.lbl.bind("<Motion>", lambda e: self.set_hover(self.hit(e.x, e.y)))
        self.lbl.bind("<Leave>", lambda e: self.set_hover(None))
        self.lbl.bind("<Button-1>", lambda e: self.on_click(self.hit(e.x, e.y)))
        self._was_down = True
        self.render()
        self._watch()

    def _watch(self):
        if self.closed:
            return
        down = mouse_down()
        if down and not self._was_down:
            x, y = cursor_pos()
            rx, ry = self.top.winfo_rootx(), self.top.winfo_rooty()
            inside = rx <= x < rx + self.W and ry <= y < ry + self.H
            ex = self.w.screen_rect(self.exempt) if self.exempt else None
            on_exempt = ex and ex[0] <= x <= ex[2] and ex[1] <= y <= ex[3]
            if not inside and not on_exempt:
                self.close()
                return
        self._was_down = down
        self.top.after(30, self._watch)

    def set_hover(self, h):
        if h != self.hover:
            self.hover = h
            self.top.config(cursor="hand2" if h is not None else "")
            self.render()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.on_close()
        try:
            self.top.destroy()
        except tk.TclError:
            pass

    def show(self, img, snap_env):
        if os.environ.get(snap_env):
            img.save(os.environ[snap_env])
        self.photo = ImageTk.PhotoImage(img, master=self.top)
        self.lbl.configure(image=self.photo)

    # overridden
    def hit(self, x, y): return None
    def on_click(self, h): pass
    def on_close(self): pass
    def render(self): pass


class ClaudePopup(Popup):
    """design/claude-popup.html (7a): header, hero ring, session + weekly bars, refresh / alert / open."""
    kind = "claude"

    def __init__(self, w):
        x = w.root.winfo_rootx() + w.spans.get("claude", (8 * S, 0))[0]
        self.buttons = {}
        super().__init__(w, int(320 * S), int(306 * S), x, exempt="claude")

    def on_close(self):
        if self.w.popup is self:
            self.w.popup = None
        self.w._start_anim()

    def hit(self, x, y):
        for k, (x0, y0, x1, y1) in self.buttons.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return k
        return None

    def on_click(self, h):
        if h == "refresh":
            self.w.usage.refresh()
        elif h == "alert":
            cur = self.w.settings.get("alert")
            i = ALERT_STEPS.index(cur) if cur in ALERT_STEPS else 0
            self.w.settings["alert"] = ALERT_STEPS[(i + 1) % len(ALERT_STEPS)]
            save_settings(self.w.settings)
        elif h == "open":
            webbrowser.open(USAGE_PAGE)
            self.close()
            return
        self.render()

    def render(self):
        if self.closed:
            return
        s, W, H = S, self.W, self.H
        u = self.w.usage
        with u.lock:
            five, week, err, fetched, plan = u.five, u.week, u.error, u.fetched_at, u.plan
        sp, wp = (five[0] if five else 0.0), (week[0] if week else 0.0)
        panel = over(CARD, 0.06)
        track = over(CARD, 0.12)
        fg2, fg3 = over(CARD, FG2_A), over(CARD, FG3_A)
        week_c = over(CARD, WEEK_A)
        f = lambda v: v * s

        # header
        f_h, f_badge, f_small = font(13, 600), font(11, 600), font(11, 400)
        age = int(time.time() - fetched) if fetched else None
        if err and err != "Updating…":
            updated = err
        elif age is None:
            updated = "Updating…"
        elif age < 60:
            updated = f"Updated {age}s ago"
        else:
            updated = f"Updated {age // 60}m ago"
        upd_w = f_small.getlength(updated)
        badge_w = f_badge.getlength(plan) + f(14) if plan else 0
        hy = f(14 + 8)
        upd_x = W - f(16) - upd_w
        badge_x = upd_x - f(8) - badge_w

        # hero
        ring_cx, ring_cy = f(16 + 48), f(54 + 48)
        # panel
        px0, py0, px1, py1 = f(12), f(166), W - f(12), H - f(12)
        row1, bar1 = f(166 + 12 + 8), f(166 + 12 + 16 + 6)
        row2, bar2 = f(216 + 8), f(216 + 16 + 6)
        foot_y0 = f(254)
        foot_cy = foot_y0 + f(14)
        # buttons right-aligned in the footer: refresh 28, alert (pad 8 + icon 14 + 4 + text + 8), open 28, gap 4
        thr = self.w.settings.get("alert")
        alert_txt = f"{thr}%" if thr else "Off"
        alert_w = f(8 + 14 + 4 + 8) + f_badge.getlength(alert_txt)
        x1 = px1 - f(12)
        bx_open = (x1 - f(28), x1)
        bx_alert = (bx_open[0] - f(4) - alert_w, bx_open[0] - f(4))
        bx_ref = (bx_alert[0] - f(4) - f(28), bx_alert[0] - f(4))
        self.buttons = {k: (a, foot_y0, b, foot_y0 + f(28)) for k, (a, b) in
                        (("refresh", bx_ref), ("alert", bx_alert), ("open", bx_open))}

        big = Image.new("RGB", (W * SS, H * SS), CARD)
        g = ImageDraw.Draw(big)
        if plan:
            rrect(g, badge_x, hy - f(8), badge_x + badge_w, hy + f(8), f(6), over(CARD, 0.10))
        for r, pct, col in ((42, wp, week_c), (29, sp, FG)):
            ring(g, ring_cx, ring_cy, f(r), f(9), track)
            if pct > 0.3:
                ring(g, ring_cx, ring_cy, f(r), f(9), col, pct)
        rrect(g, px0, py0, px1, py1, f(12), panel)
        for by, pct, col in ((bar1, sp, FG), (bar2, wp, week_c)):
            rrect(g, px0 + f(12), by, px1 - f(12), by + f(4), f(2), over(panel, 0.12))
            fw = (px1 - px0 - f(24)) * min(pct, 100) / 100
            if fw > f(1):
                rrect(g, px0 + f(12), by, px0 + f(12) + max(fw, f(4)), by + f(4), f(2), col)
        dot(g, px0 + f(12 + 4), row1, f(4), FG)
        dot(g, px0 + f(12 + 4), row2, f(4), week_c)
        for k, (x0, y0, x1b, y1) in self.buttons.items():
            if self.hover == k:
                rrect(g, x0, y0, x1b, y1, f(8), over(panel, HOVER_A))
        ic = f(14)
        icon(g, "refresh", bx_ref[0] + f(7), foot_cy - ic / 2, ic, FG)
        icon(g, "bell", bx_alert[0] + f(8), foot_cy - ic / 2, ic, FG if thr else fg2)
        icon(g, "open", bx_open[0] + f(7), foot_cy - ic / 2, ic, FG)

        img = big.resize((W, H), Image.LANCZOS)
        d = ImageDraw.Draw(img)
        d.text((f(16), hy), "Claude", font=f_h, fill=FG, anchor="lm")
        if plan:
            d.text((badge_x + f(7), hy), plan, font=f_badge, fill=over(CARD, 0.8), anchor="lm")
        d.text((upd_x, hy), updated, font=f_small, fill=fg3, anchor="lm")

        # hero text: "53" 40/700 + "%" 18/600 on one baseline, then title + reset line
        tx = f(16 + 96 + 16)
        top = ring_cy - f(39.5)
        base_y = top + f(40 * 0.865)
        if five and five[0] >= 100:
            big_txt, unit = "Limit", ""
        else:
            big_txt, unit = (f"{sp:.0f}" if five else "–"), "%"
        f40, f18 = font(40, 700), font(18, 600)
        d.text((tx, base_y), big_txt, font=f40, fill=FG, anchor="ls")
        if unit:
            d.text((tx + f40.getlength(big_txt) + f(2), base_y), unit, font=f18, fill=fg2, anchor="ls")
        d.text((tx, top + f(40 + 4 + 8)), "Current session", font=font(13, 600), fill=FG, anchor="lm")
        if five and five[1]:
            reset_line = f"Resets in {fmt_min(mins_until(five[1]))} · {fmt_clock(five[1])}"
        else:
            reset_line = "Starts with your next message"
        d.text((tx, top + f(40 + 4 + 16 + 4 + 7.5)), reset_line, font=font(12, 400), fill=fg2, anchor="lm")

        # panel rows
        f12, f12b = font(12, 400), font(12, 600)
        for cyy, name, pct in ((row1, "Current session", sp), (row2, "Weekly", wp)):
            d.text((px0 + f(12 + 8 + 6), cyy), name, font=f12, fill=FG, anchor="lm")
            d.text((px1 - f(12), cyy), f"{pct:.0f}%", font=f12b, fill=FG, anchor="rm")
        if week and week[1]:
            wk = week[1].astimezone()
            wk_line = f"Weekly resets {wk.strftime('%a')} {fmt_clock(week[1])}"
        else:
            wk_line = "Weekly"
        d.text((px0 + f(12), foot_cy), wk_line, font=f_small, fill=fg3, anchor="lm")
        d.text((bx_alert[0] + f(8 + 14 + 4), foot_cy), alert_txt, font=f_badge, fill=FG if thr else fg2, anchor="lm")
        self.show(img, "WIDGET_POPUP_SNAPSHOT")


def ellipsize(text, fnt, maxw):
    if fnt.getlength(text) <= maxw:
        return text
    while text and fnt.getlength(text + "…") > maxw:
        text = text[:-1]
    return text.rstrip() + "…"


def glyph(g, name, ox, oy, size, colour, unit):
    """Focus popup glyphs, drawn in the design's own viewBox units (12 or 16 or 10)."""
    k = size / unit
    P = lambda x, y: (ox + x * k, oy + y * k)
    if name == "play":
        g.polygon([(x * SS, y * SS) for x, y in (P(3, 1.8), P(3, 10.2), P(10.2, 6))], fill=colour)
    elif name == "pause":
        for x0 in (2, 7):
            (a, b), (c, d) = P(x0, 1.5), P(x0 + 3, 10.5)
            rrect(g, a, b, c, d, k, colour)
    elif name in ("minus", "plus"):
        polyline(g, [P(3, 6), P(9, 6)], 1.6 * k, colour)
        if name == "plus":
            polyline(g, [P(6, 3), P(6, 9)], 1.6 * k, colour)
    elif name == "add":
        polyline(g, [P(8, 3.5), P(8, 12.5)], 1.6 * k, colour)
        polyline(g, [P(3.5, 8), P(12.5, 8)], 1.6 * k, colour)
    elif name == "reset":
        (x0, y0), (x1, y1) = P(2.5, 2.5), P(13.5, 13.5)
        g.arc([x0 * SS, y0 * SS, x1 * SS, y1 * SS], 225, 180, fill=colour, width=max(1, int(round(1.6 * k * SS))))
        polyline(g, [P(2.5, 2.5), P(2.5, 5.5), P(5.5, 5.5)], 1.6 * k, colour)
        dot(g, *P(2.5, 8), 0.8 * k, colour)
    elif name == "phones":
        w = 1.6 * k
        (x0, y0), (x1, y1) = P(2.5, 2), P(13.5, 13)
        g.arc([x0 * SS, y0 * SS, x1 * SS, y1 * SS], 180, 360, fill=colour, width=max(1, int(round(w * SS))))
        polyline(g, [P(2.5, 7.5), P(2.5, 10)], w, colour)
        polyline(g, [P(13.5, 7.5), P(13.5, 10)], w, colour)
        for xa in (2, 11):
            (a, b), (c, d) = P(xa, 9.5), P(xa + 3, 13.5)
            g.rounded_rectangle([a * SS, b * SS, c * SS, d * SS], radius=k * SS, outline=colour,
                                width=max(1, int(round(w * SS))))
    elif name == "tick":
        polyline(g, [P(2, 5.2), P(4, 7.2), P(8, 2.8)], 1.8 * k, colour)


class FocusPopup(Popup):
    """design/focus-widget.html (8a): modes, timer ring, length, start / reset / rain, today's tasks."""
    kind = "focus"
    MAX_ROWS = 8

    def __init__(self, w):
        self.w, self.buttons = w, {}
        self.editing, self.draft, self.caret = False, "", True
        x = w.root.winfo_rootx() + w.spans.get("focus", (0, 0))[0]
        super().__init__(w, int(320 * S), int(self.height() * S), x, exempt="focus")
        self.top.bind("<Key>", self.on_key)

    def on_close(self):
        if self.w.popup is self:
            self.w.popup = None
        self.w._start_anim()

    # --- layout (design px) ---
    def visible(self):
        t = self.w.focus.todos
        if len(t) <= self.MAX_ROWS:
            return list(t)
        ids = [x["id"] for x in t if not x["done"]][:self.MAX_ROWS]
        ids += [x["id"] for x in t if x["done"]][:self.MAX_ROWS - len(ids)]
        return [x for x in t if x["id"] in ids]

    def height(self):
        return 276 + 34 * len(self.visible()) + 28 + 6 + 12 + 28 + 12

    def resize(self, H):
        sw, sh, tb_h = screen_geometry()
        self.H = H
        self.top.geometry(f"{self.W}x{H}+{self.top.winfo_rootx()}+{int(sh - tb_h - H - 8 * S)}")

    # --- input ---
    def hit(self, x, y):
        for k, (x0, y0, x1, y1) in self.buttons.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return k
        return None

    def take_keys(self):
        """Typing needs keyboard focus: let this one window activate while the task box is in use."""
        style = user32.GetWindowLongW(self.hwnd, -20)
        user32.SetWindowLongW(self.hwnd, -20, style & ~0x08000000)
        user32.SetForegroundWindow(ctypes.c_void_p(self.hwnd))
        self.top.focus_force()

    def _blink(self):
        if self.closed or not self.editing:
            return
        self.caret = not self.caret
        self.render()
        self.top.after(530, self._blink)

    def on_key(self, e):
        if not self.editing:
            return
        ks = e.keysym
        if ks in ("Return", "KP_Enter"):
            if self.draft.strip():
                self.w.focus.add(self.draft.strip()[:120])
                self.w.focus.save()
                self.w.render()
            self.draft = ""
        elif ks == "Escape":
            self.editing = False
        elif ks == "BackSpace":
            self.draft = self.draft[:-1]
        elif e.state & 0x4 and ks.lower() == "v":
            try:
                self.draft = (self.draft + self.top.clipboard_get().splitlines()[0])[:120]
            except Exception:
                pass
        elif e.char and e.char.isprintable() and len(self.draft) < 120:
            self.draft += e.char
        self.caret = True
        self.render()

    def on_click(self, h):
        f = self.w.focus
        if h != "input":
            self.editing = False
        kind = h[0] if isinstance(h, tuple) else h
        if kind == "mode":
            f.set_mode(h[1])
        elif h == "len-":
            f.set_len(-1)
        elif h == "len+":
            f.set_len(1)
        elif h == "run":
            f.toggle()
        elif h == "reset":
            f.reset()
        elif h == "open":
            self.close()
            self.w.open_app()
            return
        elif kind == "chk":
            f.toggle_done(h[1])
        elif kind == "sel":
            f.select(h[1])
        elif kind == "play":
            f.run_task(h[1])
        elif h == "clear":
            f.clear_done()
        elif h == "input" and not self.editing:
            self.editing, self.caret = True, True
            self.take_keys()
            self.top.after(530, self._blink)
        if h is not None:
            f.save()
            f.sync_sound()
            self.w.render()
        self.render()

    # --- drawing ---
    def render(self):
        if self.closed:
            return
        s, W = S, self.W
        f = lambda v: v * s
        fo = self.w.focus
        H = int(self.height() * s)
        if H != self.H:
            self.resize(H)
        rows = self.visible()
        total, rem = fo.total(), fo.remaining()
        p = (1 - rem / total) * 100 if total else 0
        goal = (sum(1 for t in fo.todos if t["done"]) / len(fo.todos) * 100 if fo.todos else 0)
        brk = fo.mode != "focus"
        cur = fo.cur()
        panel, seg = over(CARD, 0.06), over(CARD, 0.08)
        fg2, fg3 = over(CARD, FG2_A), over(CARD, FG3_A)
        f10x, f11b, f11, f12, f12b, f13, f13b = (font(10, 700), font(11, 600), font(11, 400), font(12, 400),
                                                 font(12, 600), font(13, 400), font(13, 600))
        B = {}

        # header: segmented modes, right-aligned
        x, tabs = W - f(18), []
        for k, lab in reversed(MODES):
            tw = f11b.getlength(lab) + f(16)
            tabs.append((k, lab, x - tw, x))
            x -= tw + f(2)
        seg_box = (x, f(14), W - f(16), f(37))
        for k, lab, a, b in tabs:
            B[("mode", k)] = (a, f(16), b, f(35))
        # stepper
        plus = (W - f(16 + 24), f(167), W - f(16), f(191))
        lab_x1 = plus[0] - f(8)
        lab_x0 = lab_x1 - f(44)
        minus = (lab_x0 - f(8 + 24), f(167), lab_x0 - f(8), f(191))
        B["len-"], B["len+"] = minus, plus
        # action buttons
        b_open = (W - f(12 + 32), f(203), W - f(12), f(235))
        b_reset = (b_open[0] - f(6 + 32), f(203), b_open[0] - f(6), f(235))
        b_run = (f(12), f(203), b_reset[0] - f(6), f(235))
        B["run"], B["reset"], B["open"] = b_run, b_reset, b_open
        # tasks
        row_y = []
        for i, t in enumerate(rows):
            ry = f(276 + 34 * i)
            row_y.append(ry)
            now = t["id"] == fo.current and not t["done"]
            running_now = now and fo.mode == "focus" and fo.running
            B[("chk", t["id"])] = (f(20), ry + f(5), f(44), ry + f(29))
            if not t["done"] and not running_now:
                B[("play", t["id"])] = (W - f(24 + 22), ry + f(6), W - f(24), ry + f(28))
            B[("sel", t["id"])] = (f(18), ry, W - f(18), ry + f(34))
        in_y = f(276 + 34 * len(rows))
        B["input"] = (f(18), in_y, W - f(18), in_y + f(28))
        panel_end = in_y + f(28 + 6)
        foot_y = panel_end + f(12)
        n_done = sum(1 for t in fo.todos if t["done"])
        clear_w = f11b.getlength("Clear done") + f(16)
        b_clear = (W - f(16) - clear_w, foot_y, W - f(16), foot_y + f(28))
        if n_done:
            B["clear"] = b_clear
        self.buttons = B
        hv = self.hover

        big = Image.new("RGB", (W * SS, self.H * SS), CARD)
        g = ImageDraw.Draw(big)
        rrect(g, *seg_box, f(8), seg)
        for k, lab, a, b in tabs:
            if fo.mode == k:
                rrect(g, a, f(16), b, f(35), f(6), over(seg, 0.16))
        ring_cx, ring_cy = f(16 + 48), f(53 + 48)
        for r, pct, col in ((42, p, FG), (29, goal, over(CARD, WEEK_A))):
            ring(g, ring_cx, ring_cy, f(r), f(9), over(CARD, 0.12))
            if pct > 0.3:
                ring(g, ring_cx, ring_cy, f(r), f(9), col, pct)
        rrect(g, f(12), f(163), W - f(12), f(195), f(9), panel)
        step_c = over(panel, 0.3) if fo.running else FG
        for key, box, name in (("len-", minus, "minus"), ("len+", plus, "plus")):
            if hv == key and not fo.running:
                rrect(g, *box, f(7), over(panel, 0.12))
            glyph(g, name, box[0] + f(6), box[1] + f(6), f(12), step_c, 12)
        # start / pause button
        rrect(g, *b_run, f(9), FG)
        run_label = "Pause" if fo.running else ("Resume" if rem < total else ("Start break" if brk else "Start focus"))
        grp = f(12 + 6) + f12b.getlength(run_label)
        gx = (b_run[0] + b_run[2]) / 2 - grp / 2
        glyph(g, "pause" if fo.running else "play", gx, f(213), f(12), (0, 0, 0), 12)
        rrect(g, *b_reset, f(9), over(CARD, 0.14) if hv == "reset" else seg)
        glyph(g, "reset", b_reset[0] + f(9), f(212), f(14), FG, 16)
        rrect(g, *b_open, f(9), over(CARD, 0.14) if hv == "open" else seg)
        icon(g, "open", b_open[0] + f(9), f(212), f(14), FG)
        # task panel
        rrect(g, f(12), f(247), W - f(12), panel_end, f(12), panel)
        for t, ry in zip(rows, row_y):
            now = t["id"] == fo.current and not t["done"]
            bg = panel
            if now:
                bg = over(panel, 0.08)
            elif isinstance(hv, tuple) and hv[1] == t["id"]:
                bg = over(panel, 0.06)
            if bg != panel:
                rrect(g, f(18), ry, W - f(18), ry + f(34), f(8), bg)
            ccx, ccy = f(32), ry + f(17)
            if t["done"]:
                dot(g, ccx, ccy, f(8), FG)
                glyph(g, "tick", ccx - f(4.5), ccy - f(4.5), f(9), (0, 0, 0), 10)
            else:
                ring(g, ccx, ccy, f(7.25), f(1.5), over(bg, 0.35))
            if ("play", t["id"]) in B:
                pb = B[("play", t["id"])]
                on = hv == ("play", t["id"])
                rrect(g, *pb, f(6), FG if on else over(bg, 0.08))
                glyph(g, "play", pb[0] + f(6), pb[1] + f(6), f(10), (0, 0, 0) if on else over(bg, 0.8), 12)
            elif now and fo.running and fo.mode == "focus":
                tw = f10x.getlength("NOW") + f(12)
                rrect(g, W - f(24) - tw, ry + f(8), W - f(24), ry + f(26), f(5), FG)
        glyph(g, "add", f(24), in_y + f(6), f(16), over(panel, FG3_A), 16)
        if hv == "clear" and n_done:
            rrect(g, *b_clear, f(8), over(CARD, 0.10))
        img = big.resize((W, self.H), Image.LANCZOS)
        d = ImageDraw.Draw(img)
        d.text((f(16), f(25.5)), "Focus", font=f13b, fill=FG, anchor="lm")
        for k, lab, a, b in tabs:
            d.text(((a + b) / 2, f(25.5)), lab, font=f11b, fill=FG if fo.mode == k else fg2, anchor="mm")
        # hero
        tx = f(16 + 96 + 16)
        top = ring_cy - f(39.5)
        d.text((tx, top + f(40 * 0.865)), fo.clock(), font=font(40, 700), fill=FG, anchor="ls")
        now_label = ("Long break" if fo.mode == "long" else "Short break") if brk else \
            (cur["text"] if cur else fo.name or "Pick a task below")
        d.text((tx, top + f(52)), ellipsize(now_label, f13b, f(170)), font=f13b, fill=FG, anchor="lm")
        d.text((tx, top + f(71.5)), f"{n_done} of {len(fo.todos)} tasks done" if fo.todos else "No tasks yet",
               font=f12, fill=fg2, anchor="lm")
        # stepper
        d.text((f(22), f(179)), {"focus": "Focus length", "short": "Short break", "long": "Long break"}[fo.mode],
               font=f12, fill=over(panel, FG2_A), anchor="lm")
        d.text(((lab_x0 + lab_x1) / 2, f(179)), f"{total // 60} min", font=f12b,
               fill=over(panel, 0.3) if fo.running else FG, anchor="mm")
        d.text((gx + f(18), f(219)), run_label, font=f12b, fill=(0, 0, 0), anchor="lm")
        # tasks
        d.text((f(24), f(265.5)), "TODAY", font=f11b, fill=over(panel, FG3_A), anchor="lm")
        for t, ry in zip(rows, row_y):
            now = t["id"] == fo.current and not t["done"]
            bg = over(panel, 0.08) if now else panel
            right = W - f(24 + 22 + 8)
            if now and fo.running and fo.mode == "focus":
                tw = f10x.getlength("NOW") + f(12)
                d.text((W - f(24) - tw / 2, ry + f(17)), "NOW", font=f10x, fill=(0, 0, 0), anchor="mm")
                right = W - f(24) - tw - f(8)
            col = over(bg, 0.4) if t["done"] else FG
            txt = ellipsize(t["text"], f13, right - f(48))
            d.text((f(48), ry + f(17)), txt, font=f13, fill=col, anchor="lm")
            if t["done"]:
                d.line([(f(48), ry + f(17.5)), (f(48) + f13.getlength(txt), ry + f(17.5))], fill=col,
                       width=max(1, int(round(s))))
        iy = in_y + f(14)
        if self.draft or self.editing:
            shown = self.draft
            while shown and f13.getlength(shown) > W - f(18 + 6 + 48):
                shown = shown[1:]
            d.text((f(48), iy), shown, font=f13, fill=FG, anchor="lm")
            if self.editing and self.caret:
                cx = f(48) + f13.getlength(shown) + f(1)
                d.line([(cx, iy - f(8)), (cx, iy + f(8))], fill=FG, width=max(1, int(round(s))))
        else:
            d.text((f(48), iy), "Add a task, press Enter", font=f13, fill=over(panel, 0.4), anchor="lm")
        # footer
        h, m = divmod(fo.focused_min, 60)
        d.text((f(16), foot_y + f(14)), (f"{h}h " if h else "") + f"{m}m focused today", font=f11, fill=fg3,
               anchor="lm")
        if n_done:
            d.text(((b_clear[0] + b_clear[2]) / 2, foot_y + f(14)), "Clear done", font=f11b,
                   fill=over(CARD, 0.7), anchor="mm")
        self.show(img, "WIDGET_FOCUS_SNAPSHOT")


def run(store, data_dir, open_app=None):
    """Start the bar on this thread and keep it alive: if Explorer restarts and takes the window, start again."""
    global DATA, SETTINGS
    DATA, SETTINGS = data_dir, os.path.join(data_dir, "bar_settings.json")
    Usage.CACHE = os.path.join(data_dir, "claude_usage.cache.json")
    # hold the old standalone widget's lock: if Taskbar Widget/widget.py is started, it sees this and quits,
    # so two bars never fight for the same spot (that fight made the bar blink on 2026-11-12)
    HEART["old_lock"] = ctypes.windll.kernel32.CreateMutexW(None, False, "HG_TaskbarWidget_Mutex")
    fails = 0
    while True:
        w, born = None, time.monotonic()
        beat()
        HEART["starts"] += 1
        try:
            w = Widget(store, open_app)
            w.run()
            if w.quitting:
                return
            fails = 0
        except Exception:
            log("bar")
            fails = 0 if time.monotonic() - born > 60 else fails + 1
        try:
            if w and not w.dead:
                w.dead = True
                w.root.destroy()
        except Exception:
            pass
        beat()
        time.sleep(min(20, 1 + 2 * fails))      # quick after a planned rebuild, slower if it keeps failing


# ---------- the bar as its own process (1.2.1) ----------
# The bar used to be a thread inside the Deepcus window's process. When that process stalled (window
# "Not Responding"), the bar froze too and showed an empty box. Now Deepcus starts `Deepcus.exe --bar`:
# its own process, started first, so a stuck or restarting window never blanks the rings.
BAR_MUTEX = "Nook_Bar_Mutex"
QUIT_EVENT = "Nook_Bar_Quit"
SHOW_EVENT = "FocusOS_Show_Window"      # same name app.py waits on


def _k32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = k.OpenEventW.restype = k.CreateEventW.restype = ctypes.c_void_p
    k.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
    k.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
    k.OpenEventW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
    k.SetEvent.argtypes = k.CloseHandle.argtypes = [ctypes.c_void_p]
    k.WaitForSingleObject.argtypes = [ctypes.c_void_p, wt.DWORD]
    return k


def data_dir():
    return os.environ.get("FOCUSOS_DATA") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "FocusOS")


def app_cmd(*args):
    """Command that starts Deepcus (the installed exe, or pythonw + app.py from source) with extra args."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-len("python.exe")] + "pythonw.exe"
    return [exe, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"), *args]


def open_main():
    """Bring the Deepcus window up: poke the running app, or start it if it is not running."""
    k = _k32()
    ev = k.OpenEventW(0x0002, False, SHOW_EVENT)          # EVENT_MODIFY_STATE
    if ev:
        k.SetEvent(ev)
        k.CloseHandle(ev)
    else:
        subprocess.Popen(app_cmd(), creationflags=0x08000000, close_fds=True)


def main_process():
    """Entry for `Deepcus.exe --bar`. One bar per user; quits when Deepcus is quit from the tray."""
    k = _k32()
    k.CreateMutexW(None, False, BAR_MUTEX)
    if ctypes.get_last_error() == 183:                    # ERROR_ALREADY_EXISTS: a bar is running
        return
    d = data_dir()
    os.makedirs(d, exist_ok=True)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import sounds
    from store import Store
    store = Store(os.path.join(d, "focusos.db"))
    sounds.setup(d)
    store.on_sound = sounds.play

    quit_ev = k.CreateEventW(None, True, False, QUIT_EVENT)

    def wait_quit():
        k.WaitForSingleObject(quit_ev, 0xFFFFFFFF)
        os._exit(0)

    def watchdog(every=10, stale=60):
        """A stuck Tk loop cannot be fixed from inside: leave, and Deepcus starts a fresh bar in seconds."""
        last, strikes = time.monotonic(), 0
        while True:
            time.sleep(every)
            now = time.monotonic()
            woke = now - last > every * 3                 # the PC slept, not a stuck bar
            last = now
            strikes = strikes + 1 if (not woke and now - HEART["at"] > stale) else 0
            if strikes >= 2:
                log(f"bar stuck (starts={HEART['starts']}), restarting the bar")
                os._exit(3)

    threading.Thread(target=wait_quit, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()
    run(store, d, open_main)
