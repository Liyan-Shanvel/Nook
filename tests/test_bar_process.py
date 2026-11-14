"""1.2.1: the taskbar bar runs as its own process (`--bar`). Nothing here starts a real bar."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bar  # noqa: E402


def test_bar_command_from_source():
    cmd = bar.app_cmd("--bar")
    assert cmd[-1] == "--bar" and cmd[-2].endswith("app.py")
    assert cmd[0].lower().endswith("pythonw.exe")      # no console window flashes up


def test_data_dir_follows_the_override(monkeypatch, tmp_path):
    monkeypatch.setenv("FOCUSOS_DATA", str(tmp_path))
    assert bar.data_dir() == str(tmp_path)


def test_names_shared_with_the_app():
    import app
    assert bar.SHOW_EVENT == app.SHOW_EVENT           # the bar's "open Deepcus" pokes the app's event
    assert bar.BAR_MUTEX and bar.QUIT_EVENT
