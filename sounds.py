"""Nook sounds: a small library of soft notification tones (see sounds/CREDITS.md).

Three moments, each can use any sound in the library (or none):
  focus_done  - a focus timer ended
  break_done  - a break ended
  task_done   - a task was ticked
"""
import os
import sys
import threading
import winsound

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(HERE, "sounds")

# id -> name shown in Settings, in the order shown
LIBRARY = {
    "chord": "Chord", "calm": "Calm", "glisten": "Glisten", "glass": "Glass", "cloud": "Cloud",
    "bloom": "Bloom", "rise": "Rise", "polite": "Polite", "whistle": "Whistle", "tap": "Tap", "tick": "Tick",
}
DEFAULT = {"focus_done": "glisten", "break_done": "chord", "task_done": "tap"}
MOMENTS = tuple(DEFAULT)


def path_of(sound):
    return os.path.join(FOLDER, f"{sound}.wav")


def setup(data_dir=None):
    """Kept for app.py: nothing to build now, the files ship with the app."""


def play(name, sound=None):
    """Play one sound now, without waiting. Unknown moment = silent; unknown sound = the default."""
    if name not in DEFAULT:
        return
    sound = sound if sound in LIBRARY else DEFAULT[name]

    def go():
        try:
            p = path_of(sound)
            if os.path.exists(p):
                winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            pass
    threading.Thread(target=go, daemon=True).start()
