"""Recorded calls from Fathom, so a goal like "30 sales calls" counts itself.

A call counts only when someone outside your company was invited AND at least two people spoke.
A no-show is you talking alone (or nobody talking), so it never counts.

The API key is the user's own, typed in Settings, kept in the local database. Read-only.
"""
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request

URL = "https://api.fathom.ai/external/v1/meetings"
PAGES = 30          # hard stop, about 300 calls a sync
FIRST_DAYS = 400    # how far back the first sync looks


def _ts(s):
    """'2026-11-02T15:00:00Z' -> aware datetime, or None."""
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def to_calls(items):
    """Fathom meeting items -> rows for store.save_calls. Pure, so tests can feed it samples."""
    out = []
    for m in items:
        start = _ts(m.get("recording_start_time")) or _ts(m.get("scheduled_start_time")) or _ts(m.get("created_at"))
        if not start or m.get("recording_id") is None:
            continue
        end = _ts(m.get("recording_end_time"))
        speakers = {(t.get("speaker") or {}).get("display_name") for t in (m.get("transcript") or [])}
        speakers.discard(None)
        speakers.discard("")
        external = m.get("calendar_invitees_domains_type") == "one_or_more_external" or any(
            i.get("is_external") for i in (m.get("calendar_invitees") or []))
        out.append({"id": f"f:{m['recording_id']}", "title": m.get("meeting_title") or m.get("title") or "Call",
                    "day": start.astimezone().date().isoformat(),
                    "mins": max(0.0, (end - start).total_seconds() / 60) if end else 0.0,
                    "speakers": len(speakers), "external": external, "source": "fathom"})
    return out


def fetch(key, after, get=None):
    """All meetings created after `after` (ISO), transcripts included. `get` is swapped in tests."""
    get = get or _get
    items, cursor = [], None
    for _ in range(PAGES):
        q = {"include_transcript": "true", "created_after": after}
        if cursor:
            q["cursor"] = cursor
        body = get(URL + "?" + urllib.parse.urlencode(q), key)
        items += body.get("items") or []
        cursor = body.get("next_cursor")
        if not cursor:
            break
    return items


def _get(url, key):
    req = urllib.request.Request(url, headers={"X-Api-Key": key, "Accept": "application/json",
                                               "User-Agent": "Deepcus"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ValueError("Fathom did not accept that key") from None
        if e.code == 429:
            raise ValueError("Fathom is busy, try again in a minute") from None
        raise ValueError(f"Fathom answered {e.code}") from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError("Could not reach Fathom. Check the internet.") from None


def sync(store, key, get=None, now=None):
    """Pull calls and save them. Raises ValueError with a plain reason; old calls stay either way."""
    now = now or store.clock()
    old = store._get("fathom", None) or {}
    since = now - FIRST_DAYS * 86400 if not old.get("at") else old["at"] - 3 * 86400   # re-read a few days
    after = dt.datetime.fromtimestamp(since, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = to_calls(fetch(key, after, get))
    store.save_calls(rows)
    real = sum(1 for c in store.calls() if c["speakers"] >= 2 and c["external"])
    st = {"ok": True, "at": now, "count": len(store.calls()), "real": real, "error": None}
    store._set("fathom", st)
    return st


def sync_quiet(store):
    key = store._get("fathom_key", "")
    if not key:
        return None
    try:
        return sync(store, key)
    except Exception as e:      # keep the old calls; say why on the Goals screen
        st = {**(store._get("fathom", None) or {}), "ok": False, "error": str(e)[:200]}
        store._set("fathom", st)
        return st


def sync_loop(store, every=1800):
    while True:
        sync_quiet(store)
        time.sleep(every)
