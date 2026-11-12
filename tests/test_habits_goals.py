import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from store import Store  # noqa: E402

T0 = dt.datetime(2026, 11, 11, 13, 0).timestamp()   # Wed 11 Nov 2026, 1:00 PM local
DAY = 86400


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def s(tmp_path):
    c = Clock(T0 - 20 * DAY)        # habits get created 20 days before "now"
    st = Store(str(tmp_path / "t.db"), clock=c)
    st.c = c
    return st


def d(n):
    """n days before Wed 11 Nov."""
    return (dt.date(2026, 11, 11) - dt.timedelta(days=n)).isoformat()


def test_streak_open_today_does_not_break(s):
    h = s.add_habit("English")
    s.c.t = T0
    for n in (1, 2, 3):
        s.tick_habit(h["id"], d(n))
    got = s.habit(h["id"])
    assert got["streak"] == 3 and not got["today_done"]
    assert got["week"][-1]["state"] == "open"
    s.tick_habit(h["id"])
    assert s.habit(h["id"])["streak"] == 4


def test_missed_planned_day_breaks_off_day_does_not(s):
    # Mon/Wed/Fri only. 11 Nov is a Wednesday.
    h = s.add_habit("Workout", days=[0, 2, 4])
    s.c.t = T0
    s.tick_habit(h["id"], d(2))     # Mon 9
    s.tick_habit(h["id"], d(5))     # Fri 6
    s.tick_habit(h["id"])           # Wed 11
    assert s.habit(h["id"])["streak"] == 3   # Tue/Sat/Sun are off-days
    s.tick_habit(h["id"], d(5), on=False)
    assert s.habit(h["id"])["streak"] == 2   # Fri 6 missed -> stops there


def test_best_streak_and_rate(s):
    h = s.add_habit("English")
    s.c.t = T0
    for n in range(10, 15):
        s.tick_habit(h["id"], d(n))       # 5 in a row, then a gap
    s.tick_habit(h["id"], d(1))
    got = s.habit(h["id"])
    assert got["best"] == 5 and got["streak"] == 1
    assert got["rate"] == round(100 * 6 / 20)   # 20 planned past days, today open not counted


def test_cannot_tick_future_and_detail_has_12_weeks(s):
    h = s.add_habit("English")
    s.c.t = T0
    with pytest.raises(ValueError):
        s.tick_habit(h["id"], "2026-11-12")
    det = s.habit_detail(h["id"])
    assert len(det["weeks"]) == 12 and det["weeks"][-1]["start"] == "2026-11-09"
    assert det["weeks"][-1]["cells"][3] == "future"


def test_goal_moves_by_ticked_tasks_and_habits(s):
    s.c.t = T0
    g = s.add_goal("Launch my side project", 30, "tasks", "2026-12-31", "tasks")
    t = s.add_task("Three small tasks")
    s.update_task(t["id"], {"goal_id": g["id"]})
    assert s.goal(g["id"])["done"] == 0
    s.update_task(t["id"], {"done": True})
    h = s.add_habit("Apply daily", goal_id=g["id"])
    s.tick_habit(h["id"])
    got = s.goal(g["id"])
    assert got["done"] == 2 and got["pct"] == 7 and got["days_left"] == 50
    assert got["tasks_today"] == ["Three small tasks"] and got["habits"][0]["title"] == "Apply daily"


def test_goal_focus_mode_and_delete_unlinks(s):
    s.c.t = T0
    g = s.add_goal("English to C1", 100, "hours", None, "focus")
    t = s.add_task("English")
    s.update_task(t["id"], {"goal_id": g["id"]})
    s.timer_start(t["id"])
    s.c.t += 15 * 60
    assert abs(s.goal(g["id"])["done"] - 0.25) < 0.01
    s.delete_goal(g["id"])
    assert s.task(t["id"])["goal_id"] is None


def test_typed_goal_and_validation(s):
    s.c.t = T0
    g = s.add_goal("$10k a month", 10000, "$", None, "typed")
    assert s.update_goal(g["id"], {"typed": 1000})["pct"] == 10
    with pytest.raises(ValueError):
        s.add_goal("x", 0)
    with pytest.raises(ValueError):
        s.update_task(s.add_task("y")["id"], {"goal_id": 999})


def test_progress_week(s):
    s.c.t = T0
    h = s.add_habit("English")
    s.tick_habit(h["id"], "2026-11-09")
    s.tick_habit(h["id"], "2026-11-10")
    t = s.add_task("Done thing", "2026-11-10")
    s.update_task(t["id"], {"done": True})
    p = s.progress("2026-11-09", "2026-11-15")
    assert len(p["days"]) == 7 and p["tasks_done"] == 1 and p["past_days"] == 3
    assert p["habits"]["pct"] == 100       # Mon+Tue kept, Wed still open
    assert p["days"][1]["done"] == ["Done thing"]


def test_rules_setting_is_cleaned(s):
    out = s.set_setting("rules", [[" YouTube ", "distracted"], ["youtube", "focus"], ["", "focus"]])
    assert out["rules"] == [["youtube", "distracted"]]
    with pytest.raises(ValueError):
        s.set_setting("rules", [["x", "bad"]])
