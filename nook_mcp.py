"""MCP bridge: lets Claude (or any MCP client) use Nook's tools.

Speaks MCP over stdio (one JSON-RPC message per line) and passes each tool call to the
running Nook app on 127.0.0.1. Standard library only.

Add to Claude Code:   claude mcp add nook -s user -- py E:\\Apps\\FocusOS\\nook_mcp.py
Needs Nook to be open. The token is read from %LOCALAPPDATA%\\FocusOS\\agent_token.txt
(or NOOK_API_TOKEN); the port from NOOK_API_PORT (default 47811).
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_api  # noqa: E402  (tool list, so tools/list works even while Nook is closed)

PROTOCOL = "2025-06-18"
DATA = os.environ.get("FOCUSOS_DATA") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "FocusOS")
BASE = f"http://127.0.0.1:{agent_api.PORT}"


def _token():
    t = os.environ.get("NOOK_API_TOKEN")
    if t:
        return t.strip()
    try:
        with open(os.path.join(DATA, agent_api.TOKEN_FILE), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def http_call(name, args):
    """Returns (ok, result_or_error_text)."""
    req = urllib.request.Request(f"{BASE}/v1/tools/{name}", data=json.dumps(args).encode("utf-8"),
                                 method="POST", headers={"Content-Type": "application/json",
                                                         "Authorization": f"Bearer {_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except ValueError:
            body = {"ok": False, "error": f"HTTP {e.code}"}
    except (urllib.error.URLError, OSError):
        return False, "Nook is not running. Open Nook and try again."
    return (True, body["result"]) if body.get("ok") else (False, body.get("error") or "failed")


def handle(msg, call=http_call):
    """One JSON-RPC message in, one reply out (None for notifications)."""
    mid, method = msg.get("id"), msg.get("method")
    if mid is None:
        return None
    if method == "initialize":
        want = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL
        res = {"protocolVersion": want, "capabilities": {"tools": {}},
               "serverInfo": {"name": "nook", "version": "1.0"},
               "instructions": "Nook is the user's task, calendar, habit and goal app. Read with get_today "
                               "before changing things. Delete only when the user asked. A task title is a "
                               "short to-do title (under 60 characters); put what to do, files and steps in "
                               "its description. To do a task, read its title and description."}
    elif method == "ping":
        res = {}
    elif method == "tools/list":
        res = {"tools": [{"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]}
                         for t in agent_api.tool_list()]}
    elif method == "tools/call":
        p = msg.get("params") or {}
        ok, out = call(p.get("name", ""), p.get("arguments") or {})
        text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str)
        res = {"content": [{"type": "text", "text": text}], "isError": not ok}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": res}


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            out = handle(msg) if isinstance(msg, dict) else None
        if out is not None:
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
