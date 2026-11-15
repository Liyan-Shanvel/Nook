import os
import hashlib
import json

import updater


def fake_github(tag, blob, sha=None, size=None):
    name = f"Deepcus-Setup-{tag.lstrip('v')}.exe"
    rel = {"tag_name": tag, "assets": [
        {"name": name, "size": len(blob) if size is None else size, "browser_download_url": "u/exe"},
        {"name": name + ".sha256", "size": 64, "browser_download_url": "u/sha"}]}
    calls = []

    def fetch(url, timeout=30):
        calls.append(url)
        if url == updater.API:
            return json.dumps(rel).encode()
        if url == "u/sha":
            return f"{sha or hashlib.sha256(blob).hexdigest()}  {name}\n".encode()
        return blob
    return fetch, calls


def test_version_compare():
    assert updater.newer("v1.2.0", "1.1.9") and updater.newer("2.0.0", "1.9.9")
    assert not updater.newer("v1.1.0", "1.1.0") and not updater.newer("v1.0.9", "1.1.0")
    assert not updater.newer("nightly", "1.0.0")


def test_newer_release_downloads_and_verifies(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "VERSION", "1.0.0")
    fetch, _ = fake_github("v9.0.0", b"installer-bytes")
    u = updater.Updater(str(tmp_path), fetch=fetch)
    assert u.check() is True
    st = u.status()
    assert st["ready"] and st["latest"] == "9.0.0" and st["error"] is None
    assert open(u.setup_path, "rb").read() == b"installer-bytes"


def test_same_version_does_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "VERSION", "9.0.0")
    fetch, calls = fake_github("v9.0.0", b"x")
    u = updater.Updater(str(tmp_path), fetch=fetch)
    assert u.check() is False and not u.status()["ready"] and calls == [updater.API]


def test_bad_checksum_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "VERSION", "1.0.0")
    fetch, _ = fake_github("v9.0.0", b"tampered", sha="0" * 64)
    u = updater.Updater(str(tmp_path), fetch=fetch)
    assert u.check() is False
    st = u.status()
    assert not st["ready"] and "checksum" in st["error"] and u.setup_path is None


def test_offline_is_not_a_crash(tmp_path):
    def fetch(url, timeout=30):
        raise OSError("no network")
    u = updater.Updater(str(tmp_path), fetch=fetch)
    assert u.check() is False and "no network" in u.status()["error"]


def test_tidy_removes_installers_already_moved_past(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "VERSION", "1.3.2")
    up = updater.Updater(str(tmp_path))
    os.makedirs(up.dir)
    for n in ("Nook-Setup-1.1.4.exe", "Deepcus-Setup-1.3.2.exe", "Deepcus-Setup-1.3.3.exe", "notes.txt"):
        open(os.path.join(up.dir, n), "w").close()
    up.tidy()
    assert sorted(os.listdir(up.dir)) == ["Deepcus-Setup-1.3.3.exe", "notes.txt"]
