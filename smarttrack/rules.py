"""Sort a sample into a KIND (code, email, video...) and a CATEGORY (focus / neutral / distracted / ignore).

Rize's order, copied: if there is a site, check SITE rules first, and the most specific host wins
(docs.google.com beats google.com). A TITLE rule can narrow a site or app ("YouTube" + title "tutorial").
No site -> APP rules on the exe/app name. No match -> kind "other", category neutral.
Rules live in rules.json next to the db (editable); built-in defaults are below."""
import json
import os
import re

# kind -> category. 'ignore' = do-not-track: nothing is stored (banking, passwords).
KINDS = {
    "code": "focus", "write": "focus", "design": "focus", "research": "focus", "sales": "focus",
    "email": "focus", "planning": "focus", "meeting": "focus", "learn": "focus", "ai": "focus",
    "chat": "neutral", "admin": "neutral", "files": "neutral", "local": "neutral", "other": "neutral",
    "social": "distracted", "video": "distracted", "news": "distracted", "shopping": "distracted",
    "games": "distracted", "adult": "distracted",
    "private": "ignore",
}

# [match, on, kind]   on = site | app | title.  Title rules may add "site:<host>" / "app:<name>" as a 4th item to scope them.
DEFAULT_RULES = [
    # sites
    ["github.com", "site", "code"], ["stackoverflow.com", "site", "code"], ["modal.com", "site", "code"],
    ["supabase.com", "site", "code"], ["vercel.com", "site", "code"], ["localhost", "site", "code"],
    ["127.0.0.1", "site", "code"],
    ["claude.ai", "site", "ai"], ["chatgpt.com", "site", "ai"], ["gemini.google.com", "site", "ai"],
    ["mail.google.com", "site", "email"], ["outlook.office.com", "site", "email"], ["outlook.live.com", "site", "email"],
    ["docs.google.com", "site", "write"], ["notion.so", "site", "write"], ["paper.design", "site", "design"],
    ["figma.com", "site", "design"], ["canva.com", "site", "design"],
    ["drive.google.com", "site", "files"], ["calendar.google.com", "site", "planning"],
    ["meet.google.com", "site", "meeting"], ["zoom.us", "site", "meeting"], ["fathom.video", "site", "meeting"],
    ["plusvibe.ai", "site", "sales"], ["apollo.io", "site", "sales"], ["linkedin.com", "site", "social"],
    ["whop.com", "site", "sales"], ["pandadoc.com", "site", "sales"],
    ["slack.com", "site", "chat"], ["web.whatsapp.com", "site", "chat"], ["discord.com", "site", "chat"],
    ["youtube.com", "site", "video"], ["netflix.com", "site", "video"], ["primevideo.com", "site", "video"],
    ["hotstar.com", "site", "video"], ["twitch.tv", "site", "video"],
    ["instagram.com", "site", "social"], ["facebook.com", "site", "social"], ["x.com", "site", "social"],
    ["twitter.com", "site", "social"], ["reddit.com", "site", "social"], ["threads.net", "site", "social"],
    ["amazon.in", "site", "shopping"], ["amazon.com", "site", "shopping"], ["flipkart.com", "site", "shopping"],
    ["news.google.com", "site", "news"], ["news.ycombinator.com", "site", "news"],
    ["chrome", "site", "admin"], ["edge", "site", "admin"], ["brave", "site", "admin"],
    # titles that change the meaning of a site
    ["tutorial", "title", "learn", "site:youtube.com"], ["course", "title", "learn", "site:youtube.com"],
    ["how to", "title", "learn", "site:youtube.com"],
    # apps
    ["code", "app", "code"], ["cursor", "app", "code"], ["windowsterminal", "app", "code"],
    ["powershell", "app", "code"], ["cmd", "app", "code"], ["python", "app", "code"], ["py", "app", "code"],
    ["claude", "app", "ai"], ["obsidian", "app", "write"], ["notion", "app", "write"], ["winword", "app", "write"],
    ["excel", "app", "write"], ["paper", "app", "design"], ["figma", "app", "design"],
    ["outlook", "app", "email"], ["olk", "app", "email"], ["zoom", "app", "meeting"], ["teams", "app", "meeting"],
    ["ms-teams", "app", "meeting"], ["slack", "app", "chat"], ["whatsapp", "app", "chat"], ["discord", "app", "chat"],
    ["explorer", "app", "files"], ["rize", "app", "admin"], ["systemsettings", "app", "admin"],
    ["steam", "app", "games"], ["spotify", "app", "other"],
    ["1password", "app", "private"], ["bitwarden", "app", "private"], ["keepass", "app", "private"],
]


def _word(pattern):
    return re.compile(r"(?<![a-z0-9])" + re.escape(pattern.lower()) + r"(?![a-z0-9])")


def load(path=None):
    """Rules from rules.json if it exists (user edits + AI suggestions on top), else the defaults."""
    rules = [list(r) for r in DEFAULT_RULES]
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            extra = json.load(f)
        rules = [list(r) for r in extra] + rules   # user rules first: they win ties
    return rules


def _host_match(host, pattern):
    """'docs.google.com' matches 'google.com' and 'docs.google.com', never 'oogle.com'."""
    return host == pattern or host.endswith("." + pattern)


def app_label(exe):
    stem = exe.lower().removesuffix(".exe")
    return stem


def classify(exe, title, host, rules):
    """-> (kind, category, rule_key). rule_key is the matched pattern, '' when nothing matched."""
    stem = app_label(exe)
    low_title = (title or "").lower()
    kind, key = None, ""
    if host:
        hits = [r for r in rules if r[1] == "site" and _host_match(host, r[0].lower())]
        if hits:
            best = max(hits, key=lambda r: len(r[0]))     # longest host wins (Rize's hostKey rule)
            kind, key = best[2], best[0]
    else:
        for r in rules:
            if r[1] == "app" and _word(r[0]).fullmatch(stem):
                kind, key = r[2], r[0]
                break
    # title rules narrow what the site/app said
    for r in rules:
        if r[1] != "title":
            continue
        scope = r[3] if len(r) > 3 else ""
        if scope.startswith("site:") and not (host and _host_match(host, scope[5:])):
            continue
        if scope.startswith("app:") and scope[4:] != stem:
            continue
        if _word(r[0]).search(low_title):
            kind, key = r[2], f"{key}+{r[0]}" if key else r[0]
            break
    kind = kind or "other"
    return kind, KINDS.get(kind, "neutral"), key
