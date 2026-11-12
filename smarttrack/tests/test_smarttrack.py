"""py -m pytest smarttrack/tests -q   (from E:/Apps/FocusOS)"""
import sqlite3

from smarttrack import insights, recorder, rules as R
from smarttrack.capture import host_of

RULES = R.load()


def cls(exe, title="", host=None):
    return R.classify(exe, title, host, RULES)[:2]


def test_host_of():
    assert host_of("youtube.com/watch?v=1") == "youtube.com"
    assert host_of("https://www.docs.google.com/d/1") == "docs.google.com"
    assert host_of("best pizza near me") is None
    assert host_of("") is None


def test_longest_host_wins_and_no_partial_host():
    assert cls("chrome.exe", host="docs.google.com") == ("write", "focus")
    assert cls("chrome.exe", host="mail.google.com") == ("email", "focus")
    assert cls("chrome.exe", host="notyoutube.com") == ("other", "neutral")   # never a substring hit
    assert cls("chrome.exe", host="m.youtube.com") == ("video", "distracted")


def test_title_narrows_site_only_in_scope():
    assert cls("chrome.exe", "Python tutorial for beginners - YouTube", "youtube.com") == ("learn", "focus")
    assert cls("chrome.exe", "Funny cats - YouTube", "youtube.com") == ("video", "distracted")
    assert cls("chrome.exe", "Python tutorial", "github.com") == ("code", "focus")


def test_app_rules_whole_name():
    assert cls("Code.exe") == ("code", "focus")
    assert cls("codeblocks.exe") == ("other", "neutral")
    assert cls("1Password.exe") == ("private", "ignore")


def mk():
    con = sqlite3.connect(":memory:")
    con.executescript(recorder.SCHEMA)
    return con, recorder.Recorder(con, rules=RULES)


def S(exe="Code.exe", title="a.py", host=None, idle=0, private=False):
    return {"exe": exe, "title": title, "host": host, "idle": idle, "private": private}


def rows(con):
    return con.execute("SELECT start,end,kind,cat FROM event ORDER BY start").fetchall()


def test_switch_closes_event_and_max_length_splits():
    con, r = mk()
    t = 1000.0
    for i in range(0, 60, 5):
        r.step(S(), t + i)
    r.step(S("chrome.exe", "x", "youtube.com"), t + 60)
    assert rows(con) == [(1000.0, 1060.0, "code", "focus")]
    con2, r2 = mk()
    for i in range(0, 400, 5):
        r2.step(S(), t + i)
    r2.stop()
    assert [round(e - s) for s, e, *_ in rows(con2)][:2] == [180, 180]


def test_idle_is_backdated():
    con, r = mk()
    t = 1000.0
    for i in range(0, 150, 5):
        r.step(S(), t + i)
    r.step(S(idle=125), t + 150)            # input stopped at t+25
    assert [(round(s), round(e)) for s, e, *_ in rows(con)] == [(1000, 1025)]


def test_sleep_gap_closes_at_last_sample():
    con, r = mk()
    r.step(S(), 1000.0)
    r.step(S(), 1005.0)
    r.step(S(), 1600.0)                      # PC slept 10 min
    assert rows(con)[0][:2] == (1000.0, 1005.0)


def test_private_never_stored():
    con, r = mk()
    r.step(S("1password.exe", "vault"), 1000.0)
    r.step(S(), 1010.0)
    r.step(S("chrome.exe", "", None, private=True), 1020.0)
    r.step(S(), 1030.0)
    r.stop()
    assert all(c != "ignore" for *_, c in rows(con))


def test_deep_block_survives_short_break_not_long():
    ev = lambda s, e, cat: {"start": s, "end": e, "sec": e - s, "where": "x", "title": "", "kind": "code", "cat": cat}
    m = 60
    evs = [ev(0, 20 * m, "focus"), ev(20 * m, 21 * m, "distracted"), ev(21 * m, 40 * m, "focus"),
           ev(40 * m, 50 * m, "distracted"), ev(50 * m, 60 * m, "focus")]
    b = insights.blocks(evs)
    assert len(b) == 1 and b[0]["focus"] == 39 * m
