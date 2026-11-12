"""What is in front right now: window, app, and (for browsers) the real site from the address bar.
Windows only. The URL is read with UI Automation, the same way Rize's native module does it."""
import ctypes
import ctypes.wintypes as w
import os
import queue
import re
import threading
from urllib.parse import urlsplit

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.GetForegroundWindow.restype = w.HWND
user32.GetWindowTextLengthW.argtypes = [w.HWND]
user32.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
kernel32.OpenProcess.restype = w.HANDLE
kernel32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
kernel32.CloseHandle.argtypes = [w.HANDLE]
kernel32.GetTickCount.restype = w.DWORD

BROWSERS = {"chrome", "msedge", "brave", "firefox", "opera", "vivaldi", "arc"}
SKIP = {"lockapp.exe", "searchhost.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe", ""}
# Names the browsers give their address bar (Chrome/Edge/Brave/Opera/Vivaldi, Firefox).
ADDRESS_NAMES = ("Address and search bar", "Address field", "Search or enter address",
                 "Search with Google or enter address", "Search or enter web address")
PRIVATE_TITLE = re.compile(r"InPrivate|Incognito|Private Browsing", re.I)


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", w.UINT), ("dwTime", w.DWORD)]


def idle_seconds():
    li = LASTINPUTINFO()
    li.cbSize = ctypes.sizeof(li)
    if not user32.GetLastInputInfo(ctypes.byref(li)):
        return 0.0
    return ((kernel32.GetTickCount() - li.dwTime) & 0xFFFFFFFF) / 1000.0


def foreground():
    """dict(hwnd, pid, exe, title) for the window in front, or None."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    pid = w.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    h = kernel32.OpenProcess(0x1000, False, pid.value)   # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        size = w.DWORD(1024)
        pbuf = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, pbuf, ctypes.byref(size)):
            exe = os.path.basename(pbuf.value)
        kernel32.CloseHandle(h)
    return {"hwnd": int(hwnd), "pid": pid.value, "exe": exe.lower(), "title": buf.value}


def is_browser(exe):
    return exe.lower().removesuffix(".exe") in BROWSERS


def host_of(text):
    """'youtube.com/watch?v=1' -> 'youtube.com'. Search text or junk -> None."""
    t = (text or "").strip()
    if not t or " " in t:
        return None
    if "://" not in t:
        t = "https://" + t
    try:
        parts = urlsplit(t)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return parts.scheme or None          # chrome://, edge://, file -> the scheme name
    host = (parts.hostname or "").lower()
    if "." not in host and host != "localhost":
        return None
    return host.removeprefix("www.")


class _Uia:
    """One UI Automation client on its own thread, so a slow browser can never stall the 5 s loop."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache = {}          # hwnd -> address bar element
        self._client = None
        self._mod = None

    def _init(self):
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as mod
        self._mod = mod
        self._client = comtypes.client.CreateObject(mod.CUIAutomation, interface=mod.IUIAutomation)

    def _find_bar(self, hwnd):
        m, c = self._mod, self._client
        root = c.ElementFromHandle(hwnd)
        edit = c.CreatePropertyCondition(m.UIA_ControlTypePropertyId, m.UIA_EditControlTypeId)
        for name in ADDRESS_NAMES:
            cond = c.CreateAndCondition(edit, c.CreatePropertyCondition(m.UIA_NamePropertyId, name))
            el = root.FindFirst(m.TreeScope_Descendants, cond)
            if el:
                return el
        return None

    def read(self, hwnd):
        if self._client is None:
            self._init()
        el = self._cache.get(hwnd)
        for attempt in (0, 1):
            if el is None:
                el = self._find_bar(hwnd)
                if el is None:
                    return None
                self._cache[hwnd] = el
            try:
                return el.GetCurrentPropertyValue(self._mod.UIA_ValueValuePropertyId)
            except Exception:
                self._cache.pop(hwnd, None)   # the element went stale (tab closed / window rebuilt)
                el = None
        return None


_uia = _Uia()
_busy = threading.Event()


def browser_host(hwnd, timeout=0.4):
    """Host from the browser's address bar, or None. Never raises, never blocks longer than `timeout`."""
    if _busy.is_set():
        return None                       # an earlier read is still stuck; skip, do not pile up threads
    out = {}
    done = threading.Event()

    def work():
        try:
            out["v"] = _uia.read(hwnd)
        except Exception as e:            # noqa: BLE001 - a failed read is "no URL", never a verdict
            out["err"] = repr(e)
        finally:
            _busy.clear()
            done.set()

    _busy.set()
    _jobs.put(work)        # UIA objects belong to the thread that made them: one worker does every read
    if not done.wait(timeout):
        return None
    return host_of(out.get("v"))


_jobs = queue.Queue()


def _worker():
    while True:
        _jobs.get()()


threading.Thread(target=_worker, daemon=True, name="smarttrack-uia").start()


def sample():
    """One reading: dict(exe, title, host, private, idle) or None when nothing useful is in front."""
    fg = foreground()
    if not fg or fg["exe"] in SKIP:
        return None
    private = bool(PRIVATE_TITLE.search(fg["title"]))
    host = None
    if is_browser(fg["exe"]) and not private:
        host = browser_host(fg["hwnd"])
    return {"exe": fg["exe"], "title": "" if private else fg["title"], "host": host,
            "private": private, "idle": idle_seconds()}
