"""1.2: what moves a goal, recorded calls, hidden calendar events, the vision board."""
import base64
import datetime as dt
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calls  # noqa: E402
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
    c = Clock(T0)
    st = Store(str(tmp_path / "t.db"), clock=c)
    st.c = c
    return st


def d(n):
    """n days before Wed 11 Nov."""
    return (dt.date(2026, 11, 11) - dt.timedelta(days=n)).isoformat()


def test_old_database_keeps_its_goals(tmp_path):
    p = str(tmp_path / "old.db")
    db = sqlite3.connect(p)
    db.executescript("""
      CREATE TABLE goal(id INTEGER PRIMARY KEY, title TEXT NOT NULL, target REAL NOT NULL, unit TEXT NOT NULL DEFAULT '',
        deadline TEXT, mode TEXT NOT NULL DEFAULT 'tasks', typed REAL NOT NULL DEFAULT 0, created TEXT NOT NULL);
      INSERT INTO goal(title,target,unit,mode,typed,created) VALUES('Save',10000,'$','typed',2500,'2026-10-01');
      INSERT INTO goal(title,target,unit,mode,typed,created) VALUES('Ship',30,'tasks','tasks',0,'2026-10-01');
      INSERT INTO goal(title,target,unit,mode,typed,created) VALUES('Learn',100,'hours','focus',0,'2026-10-01');
    """)
    db.commit()
    db.close()
    st = Store(p, clock=Clock(T0))
    got = {g["title"]: g for g in st.goals()}
    assert got["Save"]["source"] == "hand" and got["Save"]["done"] == 2500 and got["Save"]["pct"] == 25
    assert got["Ship"]["source"] == "linked" and got["Learn"]["source"] == "focus_word"
    st2 = Store(p, clock=Clock(T0))                      # opening it again must not add the 2500 twice
    assert {g["title"]: g["done"] for g in st2.goals()}["Save"] == 2500


def test_by_hand_log_undo_and_weekly_reset(s):
    g = s.add_goal({"title": "Read", "target": 3, "unit": "chapters", "source": "hand", "period": "week"})
    s.log_goal(g["id"], 1, d(7))                         # last week: does not count this week
    got = s.log_goal(g["id"], 2)
    assert got["done"] == 2 and got["pace"]["left"] == 1 and got["pace"]["per"] == "week"
    assert s.delete_goal_log(got["log_id"])["done"] == 0
    with pytest.raises(ValueError):
        s.log_goal(g["id"], 1, "2026-11-12")             # tomorrow


def test_calls_count_only_when_the_other_person_showed_up(s):
    g = s.add_goal({"title": "30 calls", "target": 30, "source": "calls", "start": "2026-01-01"})
    s.save_calls([
        {"id": "f:1", "title": "Intro call", "day": d(3), "speakers": 2, "external": True},
        {"id": "f:2", "title": "Intro call", "day": d(2), "speakers": 1, "external": True},     # no-show
        {"id": "f:3", "title": "Team sync", "day": d(1), "speakers": 3, "external": False},     # internal
        {"id": "f:4", "title": "Old call", "day": "2025-12-30", "speakers": 2, "external": True},  # before the start
    ])
    assert s.goal(g["id"])["done"] == 1
    s.save_calls([{"id": "f:1", "title": "Intro call", "day": d(3), "speakers": 2, "external": True}])   # a re-sync
    assert s.goal(g["id"])["done"] == 1
    assert s.log_goal(g["id"], 1)["done"] == 2           # a call that was not recorded, added by hand


def test_fathom_items_become_calls():
    items = [
        {"recording_id": 7, "title": "Intro Call", "meeting_title": "Intro Call between A and B",
         "recording_start_time": "2026-11-02T10:00:00Z", "recording_end_time": "2026-11-02T10:31:00Z",
         "calendar_invitees_domains_type": "one_or_more_external",
         "transcript": [{"speaker": {"display_name": "A"}, "text": "hi"}, {"speaker": {"display_name": "B"}, "text": "hi"},
                        {"speaker": {"display_name": "A"}, "text": "so"}]},
        {"recording_id": 8, "title": "Waiting", "recording_start_time": "2026-11-03T10:00:00Z",
         "calendar_invitees": [{"is_external": True}], "transcript": [{"speaker": {"display_name": "A"}, "text": "hello?"}]},
        {"recording_id": 9, "title": "Silent", "created_at": "2026-11-04T10:00:00Z", "transcript": None},
        {"title": "no id"},
    ]
    rows = calls.to_calls(items)
    assert [(r["id"], r["speakers"], r["external"]) for r in rows] == [("f:7", 2, True), ("f:8", 1, True), ("f:9", 0, False)]
    assert rows[0]["title"] == "Intro Call between A and B" and round(rows[0]["mins"]) == 31


def test_fathom_sync_pages_and_keeps_old_calls_on_failure(s):
    pages = {None: {"items": [{"recording_id": 1, "title": "x", "created_at": "2026-11-02T10:00:00Z",
                               "calendar_invitees_domains_type": "one_or_more_external",
                               "transcript": [{"speaker": {"display_name": "A"}}, {"speaker": {"display_name": "B"}}]}],
                    "next_cursor": "c2"},
             "c2": {"items": [{"recording_id": 2, "title": "y", "created_at": "2026-11-03T10:00:00Z"}], "next_cursor": None}}
    seen = []

    def get(url, key):
        assert key == "k"
        seen.append(url)
        return pages["c2" if "cursor=c2" in url else None]

    st = calls.sync(s, "k", get=get)
    assert st["count"] == 2 and st["real"] == 1 and len(seen) == 2 and "include_transcript=true" in seen[0]

    def boom(url, key):
        raise ValueError("Fathom did not accept that key")

    with pytest.raises(ValueError):
        calls.sync(s, "k", get=boom)
    assert len(s.calls()) == 2


def test_calendar_word_is_a_whole_word_and_only_past_events_count(s):
    g = s.add_goal({"title": "Calls", "target": 10, "source": "calendar", "match": "call, demo"})
    today = d(0)
    s.replace_meetings(d(5), d(-5), [
        {"id": "a", "title": "Sales Call with Sam", "day": d(2), "start_min": 600, "end_min": 630},
        {"id": "b", "title": "Recall the notes", "day": d(2), "start_min": 700, "end_min": 730},       # 'recall' is not 'call'
        {"id": "c", "title": "Product DEMO", "day": today, "start_min": 600, "end_min": 660},          # over by 1 PM
        {"id": "e", "title": "Call later today", "day": today, "start_min": 900, "end_min": 930},      # not yet
        {"id": "f", "title": "Call tomorrow", "day": d(-1), "start_min": 600, "end_min": 630},
    ])
    assert s.goal(g["id"])["done"] == 2
    s.hide_event("a")
    assert s.goal(g["id"])["done"] == 1
    assert [m["id"] for m in s.meetings(d(2))] == ["b"]
    s.replace_meetings(d(5), d(-5), [{"id": "a", "title": "Sales Call with Sam", "day": d(2), "start_min": 600, "end_min": 630}])
    assert s.meetings(d(2)) == []                        # a re-sync does not bring a hidden one back
    assert s.show_all_events() == 0 and len(s.meetings(d(2))) == 1
    with pytest.raises(ValueError):
        s.add_goal({"title": "x", "target": 5, "source": "calendar"})   # needs a word


def test_all_focus_time_counts_without_linking(s):
    g = s.add_goal({"title": "120 hours", "target": 120, "source": "focus_all", "start": d(0)})
    s._q("INSERT INTO session(task_id,kind,start_ts,end_ts,day) VALUES(NULL,'focus',?,?,?)", (T0 - DAY, T0 - DAY + 3600, d(1)))
    assert s.goal(g["id"])["done"] == 0                  # yesterday is before the start
    s.timer_start(s.add_task("Deep work")["id"])
    s.c.t = T0 + 15 * 60
    assert abs(s.goal(g["id"])["done"] - 0.25) < 0.01    # the stretch running right now counts
    assert s.goal(g["id"])["unit"] == "hours"


def test_focus_and_tasks_by_word(s):
    gf = s.add_goal({"title": "English", "target": 50, "source": "focus_word", "match": "english"})
    gt = s.add_goal({"title": "Outreach", "target": 20, "source": "tasks_word", "match": "email"})
    a, b = s.add_task("English practice"), s.add_task("Send email to Sam")
    c = s.add_task("Emailing is not a whole word")
    for t, mins in ((a, 60), (b, 30)):
        s._q("INSERT INTO session(task_id,kind,start_ts,end_ts,day) VALUES(?,'focus',?,?,?)", (t["id"], T0, T0 + mins * 60, d(0)))
    s.update_task(b["id"], {"done": True})
    s.update_task(c["id"], {"done": True})
    assert s.goal(gf["id"])["done"] == 1.0 and s.goal(gt["id"])["done"] == 1


def test_a_number_that_moves_up_or_down(s):
    up = s.add_goal({"title": "Gain 3 kg", "target": 61, "base": 58, "unit": "kg", "source": "value",
                     "deadline": "2026-12-31", "start": d(10)})
    assert s.goal(up["id"])["pct"] == 0
    s.log_goal(up["id"], 59.5, d(2))
    got = s.log_goal(up["id"], 59.5)
    assert got["done"] == 59.5 and got["pct"] == 50 and got["pace"]["state"] in ("ahead", "on")
    down = s.add_goal({"title": "Lose", "target": 70, "base": 80, "unit": "kg", "source": "value"})
    assert s.log_goal(down["id"], 75)["pct"] == 50
    assert s.log_goal(down["id"], 82)["pct"] == 0        # went the wrong way: never below 0
    with pytest.raises(ValueError):
        s.add_goal({"title": "x", "target": 5, "base": 5, "source": "value"})


def test_steps_goal(s):
    g = s.add_goal({"title": "Move", "source": "steps"})
    s.add_goal_step(g["id"], "Sign")
    got = s.add_goal_step(g["id"], "Pack")
    assert got["pct"] == 0 and got["steps_total"] == 2
    sid = s.goal(g["id"], detail=True)["steps"][0]["id"]
    assert s.update_goal_step(sid, {"done": True})["pct"] == 50
    assert s.delete_goal_step(sid)["steps_total"] == 1


def test_pace_says_behind_on_track_ahead(s):
    g = s.add_goal({"title": "30 calls", "target": 30, "source": "hand", "start": d(30), "deadline": d(-30)})
    assert s.goal(g["id"])["pace"]["state"] == "behind"          # half the time gone, nothing done
    s.log_goal(g["id"], 15, d(1))
    p = s.goal(g["id"])["pace"]
    assert p["state"] == "on" and abs(p["need"] - 3.5) < 0.01    # 15 left over 30 days
    s.log_goal(g["id"], 10)
    assert s.goal(g["id"])["pace"]["state"] == "ahead"
    s.log_goal(g["id"], 5)
    assert s.goal(g["id"])["pace"]["state"] == "done" and s.goal(g["id"])["pct"] == 100
    s.update_goal(g["id"], {"status": "paused"})
    assert s.goal(g["id"])["pace"] is None


def test_detail_has_twelve_weeks_and_history(s):
    g = s.add_goal({"title": "Books", "target": 12, "source": "hand"})
    s.log_goal(g["id"], 1, d(15), "first")
    s.log_goal(g["id"], 2)
    got = s.goal(g["id"], detail=True)
    assert len(got["weeks"]) == 12 and got["weeks"][-1]["amount"] == 2 and got["weeks"][-3]["amount"] == 1
    assert [x["amount"] for x in got["logs"]] == [2, 1] and got["logs"][1]["note"] == "first"


def test_delete_goal_cleans_up_and_duplicate_task(s):
    g = s.add_goal({"title": "G", "target": 5, "source": "linked"})
    t = s.add_task("Write", d(0), 600, 660)
    s.update_task(t["id"], {"goal_id": g["id"], "focus_min": 50})
    copy = s.duplicate_task(t["id"])
    assert (copy["title"], copy["day"], copy["goal_id"], copy["focus_min"]) == ("Write", d(0), g["id"], 50)
    assert copy["start_min"] is None and not copy["done"] and copy["id"] != t["id"]
    s.log_goal(g["id"], 1)
    card = s.add_vision_text("Why")
    s.update_vision(card["id"], {"goal_id": g["id"]})
    s.delete_goal(g["id"])
    assert s.task(t["id"])["goal_id"] is None and s.vision()[0]["goal_id"] is None
    assert s._all("SELECT COUNT(*) n FROM goal_log")[0]["n"] == 0


JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"0" * 64


def test_vision_keeps_only_real_pictures(s):
    card = s.add_vision_image("data:image/jpeg;base64," + base64.b64encode(JPEG).decode())
    path = os.path.join(s.dir, "vision", card["file"])
    assert os.path.exists(path) and card["file"].endswith(".jpg")
    assert s.vision_image(card["id"]).startswith("data:image/jpeg;base64,")
    with pytest.raises(ValueError):
        s.add_vision_image(base64.b64encode(b"MZ this is a program").decode())
    with pytest.raises(ValueError):
        s.add_vision_image(base64.b64encode(JPEG + b"0" * (3 * 1024 * 1024)).decode())
    got = s.update_vision(card["id"], {"caption": "The flat", "wide": True})
    assert got["caption"] == "The flat" and s.vision()[0]["wide"] is True
    s.delete_vision(card["id"])
    assert not os.path.exists(path) and s.vision() == []
