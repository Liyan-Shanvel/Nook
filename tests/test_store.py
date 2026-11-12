import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from store import Store, DEFAULT_RULES  # noqa: E402
import tracker  # noqa: E402

T0 = dt.datetime(2026, 11, 11, 13, 0).timestamp()   # Wed 11 Nov 2026, 1:00 PM local


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def s(tmp_path):
    c = Clock(T0)
    st = Store(str(tmp_path / "t.db"), clock=c)
    st.c = c
    return st


def test_task_is_a_block(s):
    t = s.add_task("Write the weekly update")
    assert t["day"] == "2026-11-11" and t["start_min"] is None
    t = s.update_task(t["id"], {"start_min": 750, "end_min": 840})
    assert (t["start_min"], t["end_min"]) == (750, 840)
    assert [x["id"] for x in s.tasks("2026-11-11")] == [t["id"]]
    t = s.update_task(t["id"], {"start_min": None, "end_min": None})      # remove time, keep task
    assert t["start_min"] is None and s.task(t["id"])


@pytest.mark.parametrize("fields", [{"start_min": 600}, {"start_min": 600, "end_min": 600},
                                    {"start_min": -5, "end_min": 30}, {"title": "  "}, {"pos": 3}])
def test_bad_updates_refused(s, fields):
    t = s.add_task("x")
    with pytest.raises(ValueError):
        s.update_task(t["id"], fields)


def test_done_sets_and_clears_done_at(s):
    t = s.add_task("x")
    assert s.update_task(t["id"], {"done": True})["done_at"] == T0
    assert s.update_task(t["id"], {"done": False})["done_at"] is None


def test_carry_and_move_to_today(s):
    old = s.add_task("Reply to Sam", day="2026-11-10", start_min=960, end_min=1005)
    s.add_task("finished", day="2026-11-10")
    s.update_task(s.tasks("2026-11-10")[-1]["id"], {"done": True})
    assert [t["title"] for t in s.carry()] == ["Reply to Sam"]
    s.move_to_today()
    t = s.task(old["id"])
    assert t["day"] == "2026-11-11" and t["start_min"] is None and s.carry() == []


def test_timer_pause_resume_counts_all_focus(s):
    t = s.add_task("English")
    s.timer_start(t["id"])
    s.c.t += 600
    s.timer_pause()                       # 10 min
    s.c.t += 300                          # paused 5 min: not counted
    st = s.timer_start()
    assert st["running"] and abs(st["remaining"] - 900) < 1e-6
    s.c.t += 900                          # runs out
    st = s.timer_state()
    assert st["finished_now"] and st["just_done"] and not st["running"]
    assert abs(s.focused("2026-11-11") - 25) < 1e-6
    assert s.timer_state()["finished_now"] is False     # only once


def test_switching_task_restarts_focus(s):
    a, b = s.add_task("a"), s.add_task("b")
    s.timer_start(a["id"])
    s.c.t += 120
    st = s.timer_start(b["id"])
    assert st["task_id"] == b["id"] and abs(st["remaining"] - 1500) < 1e-6
    assert abs(s.focused("2026-11-11") - 2) < 1e-6


def test_break_not_counted_as_focus(s):
    s.timer_start(mode="short")
    s.c.t += 400
    s.timer_state()
    assert s.focused("2026-11-11") == 0


def test_delete_running_task_keeps_time(s):
    t = s.add_task("x")
    s.timer_start(t["id"])
    s.c.t += 60
    s.delete_task(t["id"])
    st = s.timer_state()
    assert st["task_id"] is None and st["running"]
    assert abs(s.focused("2026-11-11") - 1) < 1e-6


def test_track_merges_and_hides_short_bits(s):
    ts = T0
    for _ in range(120):                  # 10 min of VS Code
        s.track_sample("VS Code", "VS Code", "focus", ts)
        ts += 5
    for _ in range(12):                   # 1 min of Chrome
        s.track_sample("Chrome", "Chrome", "other", ts)
        ts += 5
    for _ in range(120):                  # 10 min of VS Code again
        s.track_sample("VS Code", "VS Code", "focus", ts)
        ts += 5
    lane = s.lane("2026-11-11")
    assert len(lane) == 1 and lane[0]["label"] == "VS Code"
    assert abs(lane[0]["mins"] - 21) < 0.2
    sm = s.summary("2026-11-11")
    assert abs(sm["other"] - 1) < 0.2 and sm["apps"][0]["app"] == "VS Code"


def test_track_gap_starts_new_entry(s):
    s.track_sample("A", "A", "focus", T0)
    s.track_sample("A", "A", "focus", T0 + 5)
    s.track_sample("A", "A", "focus", T0 + 600)            # came back after 10 min away
    rows = s._all("SELECT start_ts,end_ts FROM track ORDER BY id")
    assert rows == [{"start_ts": T0, "end_ts": T0 + 5}, {"start_ts": T0 + 600, "end_ts": T0 + 600}]


def test_settings_validate(s):
    assert s.set_setting("focus", "30")["focus"] == 30
    with pytest.raises(ValueError):
        s.set_setting("focus", 0)
    with pytest.raises(ValueError):
        s.set_setting("nope", 1)


@pytest.mark.parametrize("exe,title,app,cat", [
    ("chrome.exe", "Funny cats - YouTube - Google Chrome", "YouTube", "distracted"),
    ("msedge.exe", "Inbox - Gmail - Personal - Microsoft​ Edge", "Gmail", "focus"),
    ("chrome.exe", "Shopping at fox.com - Google Chrome", "Shopping at fox.com", "other"),
    ("Code.exe", "youtube_notes.md - Visual Studio Code", "VS Code", "focus"),
    ("WindowsTerminal.exe", "Claude Code", "Terminal", "focus"),
    ("Spotify.exe", "Spotify Premium", "Spotify", "other"),
    ("chrome.exe", "Google Chrome", "Chrome", "other"),
])
def test_classify(exe, title, app, cat):
    assert tracker.classify(exe, title, DEFAULT_RULES) == (app, cat)
