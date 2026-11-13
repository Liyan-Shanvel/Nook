"""2026-11-13: every bar rebuild started another usage poller; the extras caused 429s and a frozen reading."""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bar  # noqa: E402


def test_one_poller_per_process(monkeypatch, tmp_path):
    monkeypatch.setattr(bar.Usage, "CACHE", str(tmp_path / "cache.json"))
    monkeypatch.setattr(bar.Usage, "_one", None)
    started = []
    monkeypatch.setattr(bar.Usage, "loop", lambda self: started.append(self))
    a =bar.Usage.shared()
    b = bar.Usage.shared()
    c = bar.Usage.shared()
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon:
            t.join(timeout=1)
    assert a is b is c
    assert len(started) == 1


def test_no_poller_without_claude(monkeypatch, tmp_path):
    monkeypatch.setattr(bar.Usage, "CACHE", str(tmp_path / "cache.json"))
    monkeypatch.setattr(bar.Usage, "_one", None)
    started = []
    monkeypatch.setattr(bar.Usage, "loop", lambda self: started.append(self))
    bar.Usage.shared(poll=False)
    assert started == []
