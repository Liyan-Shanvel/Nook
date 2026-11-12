"""Nook sounds: a small library of soft notification tones (see sounds/CREDITS.md), plus the person's own.

Three moments, each can use any sound in the library (or none):
  focus_done  - a focus timer ended
  break_done  - a break ended
  task_done   - a task was ticked

Own sounds: any .wav in <data folder>/sounds shows up in the list as "my:<file name>".
They stay on that PC only; they are never shipped with the app.
"""
import os
import sys
import threading
import winsound

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(HERE, "sounds")
USER = None          # set by setup(data_dir); None in tests = no own sounds

# id -> name shown in Settings, in the order shown
LIBRARY = {
    "chord": "Chord", "calm": "Calm", "glisten": "Glisten", "glass": "Glass", "cloud": "Cloud",
    "bloom": "Bloom", "rise": "Rise", "polite": "Polite", "whistle": "Whistle", "tap": "Tap", "tick": "Tick",
}
DEFAULT = {"focus_done": "glisten", "break_done": "chord", "task_done": "tap"}
MOMENTS = tuple(DEFAULT)
MINE = "my:"


def own():
    """The person's own sounds: [(id, name)], sorted by name."""
    if not USER or not os.path.isdir(USER):
        return []
    names = sorted(f[:-4] for f in os.listdir(USER) if f.lower().endswith(".wav"))
    return [(MINE + n, n) for n in names]


def library():
    """Everything the picker shows: built-in first, then own sounds."""
    return list(LIBRARY.items()) + own()


def known(sound):
    return sound in LIBRARY or (isinstance(sound, str) and sound.startswith(MINE) and os.path.exists(path_of(sound)))


def path_of(sound):
    if isinstance(sound, str) and sound.startswith(MINE):
        name = os.path.basename(sound[len(MINE):])          # never leave the folder
        return os.path.join(USER or "", f"{name}.wav")
    return os.path.join(FOLDER, f"{sound}.wav")


def setup(data_dir=None):
    """Point at the folder for own sounds and make sure it exists."""
    global USER
    if data_dir:
        USER = os.path.join(data_dir, "sounds")
        os.makedirs(USER, exist_ok=True)


def play(name, sound=None):
    """Play one sound now, without waiting. Unknown moment = silent; unknown sound = the default."""
    if name not in DEFAULT:
        return
    sound = sound if known(sound) else DEFAULT[name]

    def go():
        try:
            p = path_of(sound)
            if os.path.exists(p):
                winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            pass
    threading.Thread(target=go, daemon=True).start()
