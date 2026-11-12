# Tracking upgrade — what Rize does, what FocusOS should copy

- **What this is:** how Rize's auto tracking works (read from its installed code), and the upgrade plan for `tracker.py`.
- **Updated:** 2026-11-11
- **Status:** ⏳ proposal. No code changed. Waiting for the FocusOS session's OK before touching `tracker.py`.
- **Related:** `SPEC.md` § Auto tracking · `tracker.py` · `store.py` (`track_sample`, `lane`, `summary`, `DEFAULT_RULES`)

## The one thing

Rize's desktop app is a simple recorder: it reads the front window, the **real browser URL**, and idle time, then sorts each sample with **URL-first rules**. The smart parts (focus score, work blocks, breaks) are worked out on Rize's server, so we can't see them. FocusOS already does the recorder's job. The real gaps are **real URLs**, **URL-first rules**, and **taking the idle time back out**.

## What Rize does (observed in Rize 3.0.206, `app.asar` → `.webpack/main/index.js`)

| Part | What Rize does | FocusOS today |
|---|---|---|
| Front window | Native module `@rize-io/get-windows` → app name, exe path, window title, pid, window id, **url**, mode (normal/incognito) | `foreground()` → (exe, title) |
| Browser URL | The native module reads the address bar through Windows UI Automation (the strings `Address and search bar` and `Address field` are in the binary). Chrome, Edge, Brave, Firefox and Opera are handled. If that fails, it tries to find a URL in the title | Guesses the site from the title text |
| Private tabs | Incognito/InPrivate → title and URL are dropped | Not handled |
| URL detail | Hostname only by default (`https://youtube.com`). Full URL only if the rule allows it | n/a |
| Rules | Rules come from the server. Each rule has `appNameRegex`, `urlRegex`, `titleRegex`, `hostKey` and a category. **If there is a URL, only URL rules are checked.** A title regex can then narrow the match. The rule with the **longest hostKey wins**, so `docs.google.com` beats `google.com`. No match → a "Miscellaneous" rule from the app name. A rule can also be marked **do-not-track** (nothing is recorded) | `[pattern, category]` on the app name, word edges, first match wins |
| Idle | `powerMonitor.getSystemIdleTime()` has 3 levels: >30 s "test", **>300 s idle**, >3600 s "dead". When idle starts, the start time is **backdated** (now minus the idle seconds) | Over 120 s → stop logging. The 120 s before that still count as active |
| Event building | One open event at a time. It closes and a new one opens when the bundle id, title **or URL** changes, or when the event is **180 s** old. Events over 6 min are logged as errors. Over 10 min they are dropped | `track_sample(app, label, category, gap=20)` merges in the store |
| Upload | Events go into a queue and are sent in batches of 50 every 60 s (`BATCH_CREATE_TRACKING_EVENTS_V2`). They are saved to disk before an update or quit | Local SQLite. No upload needed |
| Server-side (not visible) | Focus quality score, work blocks, breaks, overwork alerts, timeline | `store.lane()` / `summary()` merging |

Event fields Rize sends: `appName, bundleId, category, startTimestamp, endTimestamp, idle, path, pid, source, tabId, title, trackingRuleHostKey, url`.

## Upgrade plan (in order, one step at a time)

| # | Change | File | Breaks app.py? |
|---|---|---|---|
| 1 | `browser_url(hwnd)`: read the address bar through UI Automation (`comtypes`, free, already on Windows). Hostname only. Returns None for private windows. Hard 200 ms timeout so the 5 s loop never stalls | `tracker.py` (new function) | No |
| 2 | `classify(exe, title, rules, url=None)`: if there's a URL, match its host first (`docs.google.com` before `google.com`), then the app name. The old `[pattern, cat]` rules keep working. A rule may also be `[pattern, cat, "host"]` or `"title"`. Add the category `ignore` (do-not-track) | `tracker.py` | No: `url` is optional |
| 3 | Backdated idle: when idle goes over 120 s, remove the last 120 s from the entry that is still open | needs `store.py` + `app.py` | **Yes: the FocusOS session decides** |
| 4 | `app.py` passes the URL into `classify` and stores the host on the track entry (a new `url` column) | `app.py`, `store.py` | **Yes: the FocusOS session's files** |

Steps 1-2 only add to `tracker.py`, so they're safe to do alone. Steps 3-4 are handed to the FocusOS session as a short change list.

## What can break

- UI Automation can hang on a busy browser → a hard timeout, and it falls back to reading the title. A failed read means "no URL", never "other site".
- Firefox's address bar has a different name → the fallback reads the title, as it does today.
- A host rule that's too short (`google`) catches everything → host rules match whole name parts, and the longest match wins.
