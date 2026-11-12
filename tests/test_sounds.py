import os
import wave

import pytest

import sounds
from store import Store


class Clock:
    t = 1_800_000_000.0

    def __call__(self):
        return self.t


def new_store(tmp_path):
    c = Clock()
    return Store(os.path.join(tmp_path, "t.db"), clock=c), c


def test_every_library_sound_ships_short_and_not_loud():
    for sid in sounds.LIBRARY:
        with wave.open(sounds.path_of(sid)) as w:
            assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == 44100
            secs = w.getnframes() / w.getframerate()
            frames = w.readframes(w.getnframes())
        peak = max(abs(int.from_bytes(frames[i:i + 2], "little", signed=True)) for i in range(0, len(frames), 2))
        assert 0.1 < secs < 3.0, sid
        assert 0.2 < peak / 32767 < 0.5, sid      # levelled near -7 dBFS: never silent, never loud
    assert set(sounds.DEFAULT.values()) <= set(sounds.LIBRARY)


def test_store_fires_each_sound_once_with_its_pick(tmp_path):
    s, c = new_store(tmp_path)
    heard = []
    s.on_sound = lambda n, snd: heard.append((n, snd))
    s.set_setting("sound_pick", {"focus_done": "calm"})
    t = s.add_task("A", s.today())
    s.update_task(t["id"], {"done": True})
    s.update_task(t["id"], {"done": True})       # already done: no second tick
    s.timer_start(mode="focus")
    c.t += 26 * 60
    s.timer_state(); s.timer_state()
    s.timer_start(mode="short")
    c.t += 6 * 60
    s.timer_state()
    d = sounds.DEFAULT
    assert heard == [("task_done", d["task_done"]), ("focus_done", "calm"), ("break_done", d["break_done"])]


def test_old_synth_picks_fall_back_to_defaults(tmp_path):
    s, _ = new_store(tmp_path)
    s._set("settings", {"sound_pick": {"focus_done": "marimba", "task_done": "off"}})
    pick = s.settings()["sound_pick"]
    assert pick == {"focus_done": sounds.DEFAULT["focus_done"], "break_done": sounds.DEFAULT["break_done"],
                    "task_done": "off"}


def test_sounds_off_and_none_are_silent(tmp_path):
    s, _ = new_store(tmp_path)
    heard = []
    s.on_sound = lambda n, snd: heard.append(n)
    s.set_setting("sound_pick", {"task_done": "off"})
    s.update_task(s.add_task("A", s.today())["id"], {"done": True})
    s.set_setting("sounds", False)
    s.update_task(s.add_task("B", s.today())["id"], {"done": True})
    assert heard == []
    with pytest.raises(ValueError):
        s.set_setting("sound_pick", {"task_done": "airhorn"})


def test_task_own_length_drives_the_timer(tmp_path):
    s, c = new_store(tmp_path)
    t = s.add_task("Deep work", s.today())
    s.update_task(t["id"], {"focus_min": 50})
    st = s.timer_start(t["id"])
    assert st["total"] == 50 * 60
    s.timer_pause()
    st = s.timer_length(40)                      # on a task with its own length: the task changes
    assert st["total"] == 40 * 60 and s.task(t["id"])["focus_min"] == 40
    assert s.settings()["focus"] == 25           # default untouched
    with pytest.raises(ValueError):
        s.update_task(t["id"], {"focus_min": 0})


def test_length_change_sets_default_and_restarts_paused(tmp_path):
    s, c = new_store(tmp_path)
    s.timer_start(mode="focus")
    c.t += 60
    with pytest.raises(ValueError):
        s.timer_length(45)                       # running: pause first
    s.timer_pause()
    st = s.timer_length(45)
    assert s.settings()["focus"] == 45 and st["remaining"] == 45 * 60


def test_focus_on_a_name_without_a_task(tmp_path):
    s, c = new_store(tmp_path)
    st = s.timer_label("  Read   the contract ")
    assert st["running"] and st["label"] == "Read the contract" and st["task_id"] is None
    c.t += 10 * 60
    s.timer_pause()
    row = s._all("SELECT label, kind, task_id FROM session")[0]
    assert row == {"label": "Read the contract", "kind": "focus", "task_id": None}
    assert round(s.focused(s.today())) == 10
    t = s.add_task("Other", s.today())
    assert s.timer_start(t["id"])["label"] is None   # starting a task clears the name
    with pytest.raises(ValueError):
        s.timer_label("   ")


def test_own_sounds_show_up_and_can_be_picked(tmp_path, monkeypatch):
    import shutil
    from store import Store
    monkeypatch.setattr(sounds, "USER", None)
    sounds.setup(str(tmp_path))
    shutil.copy(sounds.path_of("tap"), tmp_path / "sounds" / "My chime.wav")
    assert ("my:My chime", "My chime") in sounds.library()
    assert sounds.known("my:My chime") and not sounds.known("my:nope") and not sounds.known("my:../tap")
    s = Store(str(tmp_path / "t.db"))
    s.set_setting("sound_pick", {"focus_done": "my:My chime"})
    assert s.settings()["sound_pick"]["focus_done"] == "my:My chime"
    (tmp_path / "sounds" / "My chime.wav").rename(tmp_path / "gone.bak")
    assert s.settings()["sound_pick"]["focus_done"] == sounds.DEFAULT["focus_done"]   # file gone -> default
