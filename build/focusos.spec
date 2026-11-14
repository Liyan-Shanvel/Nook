# PyInstaller recipe for Deepcus. Build: py -m PyInstaller build/focusos.spec --noconfirm (from the app folder)
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    datas=[
        (os.path.join(ROOT, "ui"), "ui"),
        (os.path.join(ROOT, "sounds"), "sounds"),
        (os.path.join(ROOT, "build", "focusos.ico"), "."),
        (os.path.join(ROOT, "google_client.json"), "."),
    ],
    hiddenimports=["bar", "account", "calls", "agent_api", "tracker", "store", "sounds", "updater", "version", "pystray._win32", "PIL._tkinter_finder",
                   "webview.platforms.edgechromium", "webview.platforms.winforms", "clr"],
    excludes=["pytest", "matplotlib", "numpy", "pandas", "IPython", "scipy"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Deepcus",
    icon=os.path.join(ROOT, "build", "focusos.ico"),
    version=os.path.join(ROOT, "build", "version.txt"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Deepcus", upx=False)
