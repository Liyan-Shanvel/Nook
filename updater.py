"""Self-update from GitHub Releases.

Every 6 hours (first check 1 minute after start): read the latest release of REPO. If its tag (vX.Y.Z)
is newer than VERSION, download its Nook-Setup-*.exe in the background, check the size and the
SHA-256 published next to it (Nook-Setup-*.exe.sha256), then tell the app "ready". The person
clicks "Restart to update": the installer runs silently, replaces the app, and opens it again.
Their data (%LOCALAPPDATA%\\FocusOS) is never touched by an update.
"""
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import urllib.request

from version import REPO, VERSION

API = f"https://api.github.com/repos/{REPO}/releases/latest"
EVERY = 3600                     # check every hour
UA = {"User-Agent": "Nook-updater", "Accept": "application/vnd.github+json"}


def parse(v):
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", str(v).strip())
    return tuple(int(x) for x in m.groups()) if m else None


def newer(tag, current=None):
    a, b = parse(tag), parse(current or VERSION)
    return bool(a and b and a > b)


def _get(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


class Updater:
    def __init__(self, data_dir, log=lambda where: None, fetch=_get):
        self.dir = os.path.join(data_dir, "updates")
        self.log, self.fetch = log, fetch
        self.lock = threading.Lock()
        self.state = {"current": VERSION, "latest": None, "ready": False, "error": None, "checked": None}
        self.setup_path = None

    def status(self):
        with self.lock:
            return dict(self.state)

    def check(self):
        """One check + download. Safe to call any time; never raises."""
        try:
            rel = json.loads(self.fetch(API))
            tag = rel.get("tag_name", "")
            with self.lock:
                self.state.update(checked=time.time(), error=None, latest=tag.lstrip("v") or None)
            if not newer(tag):
                return False
            assets = {a["name"]: a for a in rel.get("assets", [])}
            exe = next((a for n, a in assets.items() if n.startswith("Nook-Setup-") and n.endswith(".exe")), None)
            sha = assets.get(exe["name"] + ".sha256") if exe else None
            if not exe or not sha:
                raise RuntimeError("release has no installer or checksum")
            want = self.fetch(sha["browser_download_url"]).decode("utf-8", "replace").split()[0].lower()
            os.makedirs(self.dir, exist_ok=True)
            path = os.path.join(self.dir, exe["name"])
            if not (os.path.exists(path) and self._sha(path) == want):
                blob = self.fetch(exe["browser_download_url"], timeout=300)
                if len(blob) != exe.get("size", len(blob)) or hashlib.sha256(blob).hexdigest() != want:
                    raise RuntimeError("download did not match its checksum")
                tmp = path + ".part"
                with open(tmp, "wb") as f:
                    f.write(blob)
                os.replace(tmp, path)
            self.setup_path = path
            with self.lock:
                self.state["ready"] = True
            return True
        except Exception as e:                      # offline, rate-limited, no release yet: try later
            with self.lock:
                self.state.update(checked=time.time(), error=str(e)[:200])
            return False

    @staticmethod
    def _sha(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def loop(self, first=5):
        time.sleep(first)
        while True:
            self.check()
            time.sleep(EVERY)

    def start(self):
        threading.Thread(target=self.loop, daemon=True).start()

    def install(self):
        """Run the downloaded installer silently, detached, so it can replace this app. Caller then exits."""
        if not self.setup_path or not os.path.exists(self.setup_path):
            return False
        flags = 0x00000008 | 0x00000200                 # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([self.setup_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH"],
                         creationflags=flags, close_fds=True)
        return True
