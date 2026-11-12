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
