"""1.4: Notes tab store + API, the link-title reader, and the window-raise fix that ended 'Not Responding'."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app  # noqa: E402
from app import Api  # noqa: E402
from store import Store  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def st(tmp_path):
    return Store(str(tmp_path / "t.db"), clock=Clock(1_000_000.0))


def test_add_save_list_order(st):
    a = st.add_note()
    assert a["title"] == "" and a["pinned"] is False
    st.clock.t += 10
    b = st.add_note(title="Second")
    assert [n["id"] for n in st.notes()] == [b["id"], a["id"]]          # newest first
    st.clock.t += 10
    st.save_note(a["id"], {"title": "Links", "body": "<p>hi</p>", "text": "hi"})
    assert [n["id"] for n in st.notes()] == [a["id"], b["id"]]          # an edit moves it up
    n = st.note(a["id"])
    assert (n["title"], n["body"], n["text"]) == ("Links", "<p>hi</p>", "hi")


def test_pin_does_not_count_as_an_edit(st):
    a, b = st.add_note(title="a"), st.add_note(title="b")
    before = st.note(a["id"])["updated"]
    st.clock.t += 50
    st.save_note(a["id"], {"pinned": True})
    assert st.note(a["id"])["updated"] == before
    assert st.notes()[0]["id"] == a["id"] and st.notes()[0]["pinned"] is True   # pinned on top
    st.save_note(a["id"], {"pinned": False})
    assert st.notes()[0]["id"] == b["id"]


def test_delete_and_missing(st):
    a = st.add_note(title="x")
    st.delete_note(a["id"])
    assert st.notes() == []
    with pytest.raises(KeyError):
        st.note(a["id"])
    with pytest.raises(KeyError):
        st.save_note(a["id"], {"title": "y"})


def test_too_long_is_refused(st):
    a = st.add_note()
    with pytest.raises(ValueError):
        st.save_note(a["id"], {"body": "x" * (3 * 1024 * 1024)})
    with pytest.raises(ValueError):
        st.save_note(a["id"], {"title": "t" * 201})


def test_list_carries_text_for_search(st):
    a = st.add_note()
    st.save_note(a["id"], {"text": "call prep\nask about budget"})
    assert "budget" in st.notes()[0]["text"]


def test_api_notes_data_falls_back_to_first(st):
    api = Api(st)
    assert api.notes_data() ["note"] is None
    a = api.add_note()
    b = api.add_note()
    d = api.notes_data(a["id"])
    assert d["note"]["id"] == a["id"] and len(d["notes"]) == 2
    api.delete_note(a["id"])
    assert api.notes_data(a["id"])["note"]["id"] == b["id"]           # a deleted note opens the next one


def test_open_url_only_web_links(st, monkeypatch):
    opened = []
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda u: opened.append(u))
    api = Api(st)
    assert api.open_url("https://example.com/a") is True
    for bad in ("file:///C:/Windows/system32/calc.exe", "javascript:alert(1)", "C:\\x.exe", "", None):
        assert api.open_url(bad) is False
    assert opened == ["https://example.com/a"]


def test_link_title_refuses_non_web():
    assert app.link_title("file:///C:/x") == ""
    assert app.link_title("ftp://x") == ""


def test_window_is_raised_through_invoke_not_from_a_worker_thread():
    """The 2026-11-15 freeze: show() set win.on_top from the wait_show thread, which deadlocks pywebview's
    WinForms thread. The raise must go through Form.Invoke; on_top must never be set directly."""
    src = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    show = src[src.index("    def show():"):src.index("    def quit_app")]
    assert "on_top" not in show
    assert "to_front()" in show
    assert "form.Invoke(" in src[src.index("    def to_front():"):src.index("    def show():")]


def test_bar_watches_the_window_from_outside():
    import bar
    assert callable(bar.app_watch) and callable(bar.find_app_window)
    src = open(os.path.join(HERE, "bar.py"), encoding="utf-8").read()
    assert "target=app_watch" in src
