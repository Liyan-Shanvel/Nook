import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import account  # noqa: E402
from store import Store  # noqa: E402

IST = __import__("datetime").timezone(__import__("datetime").timedelta(hours=5, minutes=30))


def ev(i, s, e, **k):
    d = {"id": i, "summary": f"M{i}", "start": {"dateTime": s}, "end": {"dateTime": e}}
    d.update(k)
    return d


def test_any_google_account_is_allowed():
    assert account.allowed("me@gmail.com")
    assert account.allowed("someone@company.com")
    assert account.allowed("a.friend@outlook.com")
    assert not account.allowed("")
    assert not account.allowed("no-at-sign")
    assert not account.allowed(None)


def test_skip_google_is_remembered(tmp_path):
    from store import Store
    a = account.Account(Store(str(tmp_path / "t.db")), str(tmp_path))
    assert a.status()["skipped"] is False and a.status()["user"] is None
    assert a.skip()["skipped"] is True
    assert account.Account(a.s, str(tmp_path)).status()["skipped"] is True


def test_events_to_meetings():
    rows = account.to_meetings([
        ev("a", "2026-11-12T16:00:00+05:30", "2026-11-12T16:30:00+05:30"),
        ev("utc", "2026-11-12T10:30:00Z", "2026-11-12T11:00:00Z"),                 # 4 PM IST
        ev("late", "2026-11-12T23:30:00+05:30", "2026-11-13T01:00:00+05:30"),       # cut at midnight
        ev("zero", "2026-11-12T09:00:00+05:30", "2026-11-12T09:00:00+05:30"),       # at least 15 min
        {"id": "allday", "start": {"date": "2026-11-12"}, "end": {"date": "2026-11-13"}},
        ev("gone", "2026-11-12T12:00:00+05:30", "2026-11-12T13:00:00+05:30", status="cancelled"),
        ev("no", "2026-11-12T12:00:00+05:30", "2026-11-12T13:00:00+05:30",
           attendees=[{"self": True, "responseStatus": "declined"}]),
        ev("ooo", "2026-11-12T12:00:00+05:30", "2026-11-12T13:00:00+05:30", eventType="outOfOffice"),
    ], IST)
    got = {r["id"].split(":")[1]: (r["day"], r["start_min"], r["end_min"]) for r in rows}
    assert got == {"a": ("2026-11-12", 960, 990), "utc": ("2026-11-12", 960, 990),
                   "late": ("2026-11-12", 1410, 1440), "zero": ("2026-11-12", 540, 555)}
    assert all(r["source"] == "google" for r in rows)


def test_signed_out_and_sign_out_clears_google_meetings(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    a = account.Account(s, str(tmp_path))
    assert a.user() is None                      # no token file = signed out
    s._set("account", {"email": "alex@example.com", "name": "Alex"})
    assert a.user() is None                      # account row alone is not enough
    (tmp_path / "google_token.json").write_text("{}", encoding="utf-8")
    assert a.user()["email"] == "alex@example.com"
    d = s.today()
    s.replace_meetings(d, d, [{"id": "g:1", "title": "Call", "day": d, "start_min": 600, "end_min": 630}])
    a._revoke = lambda c: None
    a.sign_out()
    assert a.user() is None and s.meetings(d) == []
    assert not (tmp_path / "google_token.json").exists()
    assert s._get("owner", None) is None         # owner is only set by a real sign-in


def test_sign_in_without_client_file_explains(tmp_path, monkeypatch):
    monkeypatch.setattr(account, "CLIENT", str(tmp_path / "missing.json"))
    a = account.Account(Store(str(tmp_path / "t.db")), str(tmp_path))
    st = a.sign_in()
    assert not st["busy"] and "google_client.json" in st["error"]
