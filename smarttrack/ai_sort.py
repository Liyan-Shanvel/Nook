"""Sort the apps/sites smarttrack doesn't know, with Azure gpt-4.1. Runs by itself once a day.

Privacy: only the NAME goes out (a host like 'apollo.io' or an exe stem like 'olk'), never a window
title, URL path, or time. Every answer is cached in data/smarttrack_ai.json so a name is asked once.
Answers become rules in data/smarttrack_rules.json, marked "ai". A rule you write yourself always wins
(AI never overwrites a non-ai rule). An outage just means "try tomorrow", never "other"."""
import json
import os
import time

from . import recorder, rules as R

CACHE = os.path.join(os.path.dirname(recorder.DB), "smarttrack_ai.json")
ENV_FILE = os.environ.get("SMARTTRACK_ENV", r"E:\Liyan Shanvel\Business\.env")
MIN_SEC = 60            # ignore names seen for under a minute in total
LOOKBACK_DAYS = 7
BATCH = 40

ALLOWED = sorted(k for k in R.KINDS if k != "private")
SYSTEM = (
    "You sort computer apps and websites into one KIND for a personal focus tracker.\n"
    "The user is a solo B2B outbound/sales agency founder who also codes and designs.\n"
    f"Allowed kinds: {', '.join(ALLOWED)}.\n"
    "Meaning: code=programming/dev tools, write=docs/notes/sheets, design=design tools, research=reading "
    "reference/docs/search, sales=CRM/outreach/lead tools/invoicing, email, planning=calendar/tasks, "
    "meeting=video calls, learn=courses/tutorials, ai=AI assistants, chat=messaging, admin=settings/system/"
    "utilities/banking/accounts, files=file managers/cloud storage, local=localhost, social, video=streaming, "
    "news, shopping, games, adult, other=cannot tell.\n"
    "Answer 'other' when you are not sure. Never guess from the name's letters alone.\n"
    'Reply JSON only: {"items":[{"name":"<exact name>","kind":"<kind>","sure":true|false}]}'
)


def _load_env():
    out = {}
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def unknowns(con, cache):
    """[(name, 'site'|'app', seconds)] for kind=other in the last week, not asked before."""
    since = time.time() - LOOKBACK_DAYS * 86400
    rows = con.execute(
        "SELECT CASE WHEN host IS NOT NULL AND host!='' THEN host ELSE app END AS name,"
        " CASE WHEN host IS NOT NULL AND host!='' THEN 'site' ELSE 'app' END AS onn,"
        " SUM(end-start) FROM event WHERE kind='other' AND start>? GROUP BY name, onn ORDER BY 3 DESC",
        (since,)).fetchall()
    return [(n, o, s) for n, o, s in rows if n and s >= MIN_SEC and f"{o}:{n}" not in cache]


def build_prompt(items):
    return "\n".join(f"{o}: {n}" for n, o, _ in items)


def _ask(user):
    env = _load_env()
    key = os.environ.get("AZURE_OPEN_AI_API_KEY") or env.get("AZURE_OPEN_AI_API_KEY")
    if not key:
        raise RuntimeError("no AZURE_OPEN_AI_API_KEY")
    from openai import AzureOpenAI
    client = AzureOpenAI(api_key=key,
                         azure_endpoint=env.get("ENDPOINT", "https://sanjeevan.cognitiveservices.azure.com"),
                         api_version=env.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"), timeout=60)
    r = client.chat.completions.create(
        model=env.get("AZURE_DEPLOYMENT", "gpt-4.1"), temperature=0, max_tokens=2000,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
    return json.loads(r.choices[0].message.content)


def sort_unknowns(con, dry=False, log=print):
    cache = _read_json(CACHE, {})
    todo = unknowns(con, cache)
    if not todo:
        log("ai_sort: nothing unknown")
        return []
    added = []
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        user = build_prompt(chunk)
        if dry:
            log("SYSTEM:\n" + SYSTEM + "\n\nUSER:\n" + user)
            return []
        data = _ask(user)                              # raises on outage -> caller retries tomorrow
        sent = {n: o for n, o, _ in chunk}
        got = {it.get("name"): it for it in data.get("items", []) if isinstance(it, dict)}
        for name, onn in sent.items():
            it = got.get(name)
            if it is None:
                continue                               # not answered: ask again next time
            kind = it.get("kind")
            if kind not in ALLOWED or not it.get("sure"):
                kind = "other"
            cache[f"{onn}:{name}"] = {"kind": kind, "at": int(time.time())}
            if kind != "other":
                added.append([name, onn, kind, "ai"])
        _write_json(CACHE, cache)
    if added:
        user_rules = _read_json(recorder.RULES_JSON, [])
        have = {(r[0].lower(), r[1]) for r in user_rules}
        user_rules += [r for r in added if (r[0].lower(), r[1]) not in have]
        _write_json(recorder.RULES_JSON, user_rules)
        reclassify(con)
    for r in added:
        log(f"ai_sort: {r[1]} {r[0]} -> {r[2]}")
    return added


def reclassify(con):
    """Re-sort stored 'other' events with the new rules, so today's report is right straight away."""
    rules = R.load(recorder.RULES_JSON)
    rows = con.execute("SELECT id, exe, title, host FROM event WHERE kind='other'").fetchall()
    for eid, exe, title, host in rows:
        kind, cat, rule = R.classify(exe or "", title or "", host, rules)
        if kind != "other":
            con.execute("UPDATE event SET kind=?, cat=?, rule=? WHERE id=?", (kind, cat, rule, eid))
    con.commit()


def due(state_path=None):
    """True once per calendar day."""
    st = _read_json(CACHE, {}).get("_last_run", "")
    return st != time.strftime("%Y-%m-%d")


def mark_ran():
    cache = _read_json(CACHE, {})
    cache["_last_run"] = time.strftime("%Y-%m-%d")
    _write_json(CACHE, cache)
