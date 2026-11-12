"""Read a day of events and work out what it meant. No AI, all rules you can check by hand.

- totals per category and per kind
- deep-work blocks: focus time where breaks/side-trips stay short (Rize calls these work blocks)
- context switches per active hour
- focus score 0-100 with its 3 parts shown, so the number is never a mystery"""
import datetime as dt
from collections import Counter, defaultdict

BLOCK_MIN = 25 * 60       # a deep-work block must be at least this long
BLOCK_BREAK = 2 * 60      # non-focus time allowed inside a block before it ends
SWITCH_GAP = 120          # events further apart than this are separate stretches, not a switch


def day_bounds(day):
    d = dt.date.fromisoformat(day) if isinstance(day, str) else day
    start = dt.datetime.combine(d, dt.time()).timestamp()
    return start, start + 86400


def events(con, day):
    a, b = day_bounds(day)
    rows = con.execute("SELECT start,end,app,host,title,kind,cat FROM event WHERE end>? AND start<? ORDER BY start",
                       (a, b)).fetchall()
    out = []
    for s, e, app, host, title, kind, cat in rows:
        s, e = max(s, a), min(e, b)
        if e > s:
            out.append({"start": s, "end": e, "sec": e - s, "where": host or app, "title": title,
                        "kind": kind, "cat": cat})
    return out


def blocks(evs):
    """Deep-work blocks: runs of focus where any non-focus stretch or gap is <= BLOCK_BREAK."""
    out, cur, leak = [], None, 0.0
    for e in evs:
        if e["cat"] == "focus":
            if cur and e["start"] - cur["end"] <= BLOCK_BREAK:
                cur["end"] = e["end"]
                cur["focus"] += e["sec"]
                cur["kinds"][e["kind"]] += e["sec"]
            else:
                if cur:
                    out.append(cur)
                cur = {"start": e["start"], "end": e["end"], "focus": e["sec"], "kinds": Counter({e["kind"]: e["sec"]})}
            leak = 0.0
        elif cur:
            leak += e["sec"]
            if leak > BLOCK_BREAK:
                out.append(cur)
                cur, leak = None, 0.0
    if cur:
        out.append(cur)
    return [b for b in out if b["focus"] >= BLOCK_MIN]


def switches(evs):
    n, prev = 0, None
    for e in evs:
        if prev and e["start"] - prev["end"] <= SWITCH_GAP and e["where"] != prev["where"]:
            n += 1
        prev = e
    return n


def report(con, day):
    evs = events(con, day)
    active = sum(e["sec"] for e in evs)
    by_cat, by_kind, by_where, unknown = Counter(), Counter(), Counter(), Counter()
    by_hour = defaultdict(Counter)
    for e in evs:
        by_cat[e["cat"]] += e["sec"]
        by_kind[e["kind"]] += e["sec"]
        by_where[e["where"]] += e["sec"]
        if e["kind"] == "other":
            unknown[e["where"]] += e["sec"]
        by_hour[dt.datetime.fromtimestamp(e["start"]).hour][e["cat"]] += e["sec"]
    deep = blocks(evs)
    deep_sec = sum(b["focus"] for b in deep)
    sw = switches(evs)
    hours = active / 3600 if active else 0
    sw_per_h = sw / hours if hours else 0
    focus = by_cat["focus"]
    parts = {
        "focus_share": round(100 * focus / active) if active else 0,             # how much was focus
        "deep_share": round(100 * deep_sec / focus) if focus else 0,             # how much focus was deep
        "calm": round(100 * (1 - min(sw_per_h, 40) / 40)) if active else 0,     # fewer switches = calmer
    }
    score = round(0.6 * parts["focus_share"] + 0.25 * parts["deep_share"] + 0.15 * parts["calm"]) if active else 0
    worst_hour = max(by_hour, key=lambda h: by_hour[h]["distracted"], default=None)
    return {
        "day": str(day), "active_min": round(active / 60), "score": score, "score_parts": parts,
        "by_cat_min": {k: round(v / 60) for k, v in by_cat.most_common()},
        "by_kind_min": {k: round(v / 60) for k, v in by_kind.most_common()},
        "top": [(w, round(s / 60)) for w, s in by_where.most_common(8)],
        "deep_blocks": [{"start": dt.datetime.fromtimestamp(b["start"]).strftime("%H:%M"),
                         "end": dt.datetime.fromtimestamp(b["end"]).strftime("%H:%M"),
                         "focus_min": round(b["focus"] / 60), "main": b["kinds"].most_common(1)[0][0]} for b in deep],
        "switches_per_hour": round(sw_per_h, 1),
        "most_distracted_hour": worst_hour if worst_hour is not None and by_hour[worst_hour]["distracted"] >= 300 else None,
        "unknown": [(w, round(s / 60, 1)) for w, s in unknown.most_common(15)],
    }
