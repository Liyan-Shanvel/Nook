"""Which window is in front, and is anyone at the keyboard. Windows only, no extra packages.
Nothing leaves this PC: only the app name (or site name for a browser) is stored, never the title."""
import ctypes
import ctypes.wintypes as w
import os
import re

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


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", w.UINT), ("dwTime", w.DWORD)]


def idle_seconds():
    li = LASTINPUTINFO()
    li.cbSize = ctypes.sizeof(li)
    if not user32.GetLastInputInfo(ctypes.byref(li)):
        return 0.0
    return ((kernel32.GetTickCount() - li.dwTime) & 0xFFFFFFFF) / 1000.0


def foreground():
    """(exe file name, window title) of the window in front, or None."""
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
    return exe, buf.value


BROWSERS = {"chrome", "msedge", "brave", "firefox", "opera", "vivaldi", "arc"}
NAMES = {"code": "VS Code", "windowsterminal": "Terminal", "explorer": "File Explorer",
         "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint", "claude": "Claude",
         "notion": "Notion", "obsidian": "Obsidian", "slack": "Slack", "zoom": "Zoom",
         "ms-teams": "Teams", "teams": "Teams", "spotify": "Spotify", "paper": "Paper",
         "powershell": "PowerShell", "pwsh": "PowerShell", "cmd": "Terminal", "whatsapp": "WhatsApp"}
SKIP = {"lockapp.exe", "searchhost.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe"}
_BROWSER_TAIL = re.compile(r"^(google chrome|microsoft\s*edge|brave|mozilla firefox|firefox|opera|vivaldi|arc"
                           r"|profile \d+|personal|work)$", re.I)


def app_name(exe, title):
    stem = exe.lower()[:-4] if exe.lower().endswith(".exe") else exe.lower()
    if stem in BROWSERS:
        clean = re.sub(r"[​-‏⁠]", "", title)
        parts = [p.strip() for p in re.split(r"\s+[-–—|]\s+", clean) if p.strip()]
        while parts and _BROWSER_TAIL.match(parts[-1]):
            parts.pop()
        # "Video name - YouTube" -> "YouTube"; a bare tab title stays as is
        return (parts[-1] if parts else stem.title())[:40]
    if not stem:
        return "Unknown"
    return NAMES.get(stem, stem[:1].upper() + stem[1:])[:40]


def _word(pattern):
    return re.compile(r"(?<![a-z0-9])" + re.escape(pattern.lower()) + r"(?![a-z0-9])")


def classify(exe, title, rules):
    """(app, category). Rules match the app name with word edges; first match wins; else other."""
    app = app_name(exe, title)
    low = app.lower()
    for pattern, cat in rules:
        if cat in ("focus", "distracted", "other") and _word(pattern).search(low):
            return app, cat
    return app, "other"
