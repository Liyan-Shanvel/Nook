# smarttrack — Rize-style auto tracking for FocusOS

- **What this is:** a separate tracking module. It records what you work on (app, real website, idle time) into its own db and works out deep-work blocks and a focus score. It doesn't touch `tracker.py`, `app.py`, `store.py` or `focusos.db`.
- **Updated:** 2026-11-11
- **Status:** ✅ recorder + rules + day report built, 9 tests pass, live 60 s run checked. ⏳ AI sorting of unknown sites (prompt waiting for OK). ⏳ wiring into the app (the FocusOS session's call).
- **Related:** `../TRACKING_PROPOSAL.md` (Rize findings) · `../SPEC.md` § Auto tracking

## The one thing

Rize's desktop app is only a careful recorder. The smart parts run on its server. smarttrack copies the recorder and does the smart parts locally with plain rules, so nothing leaves the PC.

## Commands (from `E:\Apps\FocusOS`)

| Command | What it does |
|---|---|
| `py -m smarttrack once` | one reading of the front window + how it's sorted |
| `py -m smarttrack run -v` | record every 5 s until Ctrl+C (`--for=60` to stop after 60 s) |
| `py -m smarttrack today [YYYY-MM-DD]` | the day's report: score, deep blocks, top sites, unknowns |
| `py -m pytest smarttrack/tests -q` | tests |

## Files

| File | Job |
|---|---|
| `capture.py` | front window + exe + title. The **real site from the address bar** (UI Automation, one worker thread, 0.4 s cap, cached per window, about 10 ms after the first read). Private windows are dropped |
| `rules.py` | kind (code, email, video...) → category (focus / neutral / distracted / ignore). Site rules first, longest host wins. Title rules narrow a site (YouTube + "tutorial" = learn). Rules you add go in `data/smarttrack_rules.json` |
| `recorder.py` | Rize's event model: new event on app/title/site change or every 180 s. Idle over 120 s is **backdated** to the last input. Sleep gaps close at the last sample. `ignore` is never stored |
| `insights.py` | totals, deep-work blocks (≥ 25 min focus, breaks ≤ 2 min), switches per hour, focus score = 60% focus share + 25% deep share + 15% calm |

## What Rize does that we chose not to copy

| Rize feature | Why not |
|---|---|
| Screenshots → Windows OCR every 60 s / cloud vision model every 5 min, sent to its server to tag projects | Heavy, and it ships your screen off the PC. Titles + sites give most of the value |
| Break reminders, overwork alerts, blocker window | Coach/popups were removed by Shanvel. Don't re-add them |
| Server-side rules + sync | One user, one PC. A local JSON file is enough |
