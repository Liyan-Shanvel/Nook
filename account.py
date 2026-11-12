"""Optional Google sign-in (any Google account) + read-only Google Calendar sync.

The OAuth client lives in google_client.json next to this file (a Google Cloud "Desktop app" client).
The signed-in token lives in data/google_token.json. Nothing here writes to Google.
"""
import datetime as dt
import json
import os
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT = os.path.join(HERE, "google_client.json")
SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email",
          "https://www.googleapis.com/auth/userinfo.profile",
          "https://www.googleapis.com/auth/calendar.readonly"]
USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
EVENTS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SKIP_TYPES = {"workingLocation", "outOfOffice", "birthday"}
PAST, AHEAD = 14, 60          # days of calendar kept in sync around today


def allowed(email):
    """Any real Google account email (Nook is open to everyone; one account per install)."""
    return isinstance(email, str) and email.count("@") == 1 and "." in email.split("@")[1]


def to_meetings(events, local_tz=None):
    """Google events -> meeting rows. Timed events only; declined, cancelled and all-day are dropped.
    An event that runs past midnight is cut at midnight (it shows on the day it starts)."""
    out = []
    for e in events:
        if e.get("status") == "cancelled" or e.get("eventType") in SKIP_TYPES:
            continue
        s, f = e.get("start", {}).get("dateTime"), e.get("end", {}).get("dateTime")
        if not s or not f:
            continue
        if any(a.get("self") and a.get("responseStatus") == "declined" for a in e.get("attendees", [])):
            continue
        a = dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(local_tz)
        b = dt.datetime.fromisoformat(f.replace("Z", "+00:00")).astimezone(local_tz)
        start = a.hour * 60 + a.minute
        end = b.hour * 60 + b.minute if b.date() == a.date() else 1440
        end = max(end, start + 15)
        out.append({"id": f"g:{e['id']}:{a.date().isoformat()}", "title": e.get("summary") or "Busy",
                    "day": a.date().isoformat(), "start_min": start, "end_min": min(end, 1440),
                    "source": "google"})
    return out


class Account:
    def __init__(self, store, data_dir):
        self.s = store
        self.token_path = os.path.join(data_dir, "google_token.json")
        self.lock = threading.Lock()
        self.busy = False
        self.error = None

    # ---------- state ----------
    def user(self):
        u = self.s._get("account", None)
        return u if u and os.path.exists(self.token_path) else None

    def status(self):
        return {"user": self.user(), "busy": self.busy, "error": self.error,
                "ready": os.path.exists(CLIENT), "calendar": self.s._get("gcal", None),
                "skipped": bool(self.s._get("google_skip", False))}

    def skip(self):
        """Use Nook without Google. Settings can still connect it later."""
        self.s._set("google_skip", True)
        return self.status()

    def _creds(self):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
            self._save(creds)
        return creds

    def _save(self, creds):
        tmp = self.token_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        os.replace(tmp, self.token_path)

    # ---------- sign in / out ----------
    def sign_in(self):
        """Opens the browser for Google sign-in. Runs in the background; the screen polls status()."""
        if not os.path.exists(CLIENT):
            self.error = "This copy of Nook has no Google sign-in key yet (google_client.json)."
            return self.status()
        with self.lock:
            if self.busy:
                return self.status()
            self.busy, self.error = True, None
        threading.Thread(target=self._sign_in, daemon=True).start()
        return self.status()

    def _sign_in(self):
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import AuthorizedSession
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT, SCOPES)
            creds = flow.run_local_server(
                port=0, open_browser=True, timeout_seconds=300, prompt="select_account",
                authorization_prompt_message="",
                success_message="Signed in. You can close this tab and go back to Nook.")
            info = AuthorizedSession(creds).get(USERINFO, timeout=20).json()
            email = (info.get("email") or "").lower()
            if not (info.get("email_verified") and allowed(email)):
                self._revoke(creds)
                raise PermissionError("Google did not confirm that account's email. Try another account.")
            owner = self.s._get("owner", None)
            if owner and owner != email:
                self._revoke(creds)
                raise PermissionError(f"This Nook belongs to {owner}. Sign in with that account.")
            self._save(creds)
            self.s._set("owner", email)
            self.s._set("account", {"email": email, "name": info.get("name") or email.split("@")[0]})
            self.sync()
        except Exception as e:      # shown on the sign-in screen
            msg = str(e) or type(e).__name__
            if "timed out" in msg.lower() or isinstance(e, (TimeoutError,)) or "WSGI" in msg:
                msg = "Sign-in took too long. Try again."
            self.error = msg
        finally:
            self.busy = False

    def _revoke(self, creds):
        try:
            import requests
            requests.post("https://oauth2.googleapis.com/revoke", params={"token": creds.token}, timeout=10)
        except Exception:
            pass

    def sign_out(self):
        if os.path.exists(self.token_path):
            try:
                from google.oauth2.credentials import Credentials
                self._revoke(Credentials.from_authorized_user_file(self.token_path, SCOPES))
            except Exception:
                pass
            os.remove(self.token_path)
        self.s._set("account", None)
        self.s._set("gcal", None)
        with self.s.lock:
            self.s._q("DELETE FROM meeting WHERE source='google'")
        return self.status()

    # ---------- calendar ----------
    def sync(self):
        """Pull the primary calendar for today-14 .. today+60 and replace those meetings."""
        if not self.user():
            return None
        try:
            from google.auth.transport.requests import AuthorizedSession
            today = dt.date.fromisoformat(self.s.today())
            a, b = today - dt.timedelta(days=PAST), today + dt.timedelta(days=AHEAD)
            tz = dt.datetime.now().astimezone().tzinfo
            lo = dt.datetime.combine(a, dt.time(0), tz).isoformat()
            hi = dt.datetime.combine(b + dt.timedelta(days=1), dt.time(0), tz).isoformat()
            sess, events, page = AuthorizedSession(self._creds()), [], None
            while True:
                p = {"timeMin": lo, "timeMax": hi, "singleEvents": "true", "orderBy": "startTime",
                     "maxResults": 2500}
                if page:
                    p["pageToken"] = page
                r = sess.get(EVENTS, params=p, timeout=30)
                if r.status_code != 200:
                    raise RuntimeError(_why(r))
                body = r.json()
                events += body.get("items", [])
                page = body.get("nextPageToken")
                if not page:
                    break
            rows = [m for m in to_meetings(events) if a.isoformat() <= m["day"] <= b.isoformat()]
            self.s.replace_meetings(a.isoformat(), b.isoformat(), rows)
            st = {"ok": True, "at": time.time(), "count": len(rows), "error": None}
        except Exception as e:      # keep the old meetings; say why on the Settings screen
            old = self.s._get("gcal", None) or {}
            st = {"ok": False, "at": old.get("at"), "count": old.get("count"), "error": str(e)[:200]}
        self.s._set("gcal", st)
        return st


def _why(r):
    try:
        err = r.json().get("error", {})
        reason = (err.get("errors") or [{}])[0].get("reason", "")
        if reason == "accessNotConfigured" or "has not been used" in err.get("message", ""):
            return "Google Calendar API is turned off in the Google Cloud project."
        if r.status_code in (401, 403):
            return "Google said no. Sign out and sign in again."
        return f"Google Calendar error {r.status_code}: {err.get('message', '')[:120]}"
    except Exception:
        return f"Google Calendar error {r.status_code}"


def sync_loop(acct, every=300):
    """Re-read the calendar every 5 minutes while someone is signed in."""
    while True:
        try:
            acct.sync()
        except Exception:
            pass
        time.sleep(every)
