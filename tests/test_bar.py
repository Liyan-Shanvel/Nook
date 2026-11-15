"""The taskbar bar drives the SAME timer and task list as the window (store.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bar  # noqa: E402
from store import Store  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def make(tmp_path):
    c = Clock()
    s = Store(str(tmp_path / "t.db"), clock=c)
    bar.time.time = c                       # the bar reads the same fake clock
    bar.chime = lambda: None
    return s, c, bar.Focus(s)


def test_bar_and_app_share_timer(tmp_path):
    s, c, f = make(tmp_path)
    t = s.add_task("Write proposal", s.today())
    f.save()
    assert [x["text"] for x in f.todos] == ["Write proposal"]
    f.run_task(t["id"])
    f.save()
    assert s.timer_state()["running"] and s.timer_state()["task_id"] == t["id"]
    assert f.bar()[0] == "running" and f.cur()["text"] == "Write proposal"
    c.t += 60
    f.toggle()                              # pause from the bar
    f.save()
    assert not s.timer_state()["running"] and f.bar()[0] == "paused"
    assert round(s.focused(s.today())) == 1  # the minute counts in the app


def test_finish_then_break_from_bar(tmp_path):
    s, c, f = make(tmp_path)
    f.toggle()
    c.t += 25 * 60 + 1
    f.save()
    assert f.bar()[:2] == ("done", "Done")
    f.toggle()                              # "Take 5 min"
    f.save()
    assert s.timer_state()["mode"] == "short" and s.timer_state()["running"]


def test_mode_length_tasks(tmp_path):
    s, c, f = make(tmp_path)
    f.set_mode("long")
    f.save()
    assert s.timer_state()["mode"] == "long" and not s.timer_state()["running"]
    f.set_mode("focus")
    f.set_len(1)
    assert s.settings()["focus"] == 30
    f.add("Call Sam")
    f.save()
    tid = f.todos[0]["id"]
    f.select(tid)
    assert s.timer_state()["task_id"] == tid and not s.timer_state()["running"]
    f.toggle_done(tid)
    f.save()
    assert s.task(tid)["done"]
    f.clear_done()
    f.save()
    assert f.todos == [] and s.task(tid)["done"]   # hidden on the bar only, still done in the app


def test_bar_rebuilds_when_the_taskbar_colour_was_read_wrong(monkeypatch):
    """2026-11-15: the bar read the taskbar colour while Windows was still drawing; every pill showed grey."""
    reads = iter([(30, 30, 32)] * 3 + [(70, 85, 105)] * 20)
    monkeypatch.setattr(bar, "sample_taskbar_colour", lambda x, y: next(reads))
    w = type("W", (), {})()
    w.geo, w.H, w.base, w.hidden, w.fs, w.popup = (1920, 1080, 48), 48, (30, 30, 32), False, 0, None
    tick = lambda: bar.Widget.tint_changed(w)  # noqa: E731
    seen = [tick() for _ in range(15)]          # one read every 5 ticks: 3 reads, all matching the key
    assert not any(seen)
    w.base = (25, 25, 28)                       # now the key is wrong vs the real colour (70, 85, 105)
    seen = [tick() for _ in range(15)]
    assert seen[-1] and not any(seen[:-1])      # rebuild only after three matching reads


def test_a_popup_covering_the_corner_does_not_trigger_a_rebuild(monkeypatch):
    monkeypatch.setattr(bar, "sample_taskbar_colour", lambda x, y: (200, 200, 200))
    w = type("W", (), {})()
    w.geo, w.H, w.base, w.hidden, w.fs, w.popup = (1920, 1080, 48), 48, (30, 30, 32), False, 0, object()
    assert not any(bar.Widget.tint_changed(w) for _ in range(30))
