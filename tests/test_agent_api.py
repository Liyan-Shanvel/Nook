"""Agent API + MCP bridge. Local only: a real server on a free 127.0.0.1 port, a fixed clock."""
import datetime as dt
import http.client
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent_api  # noqa: E402
import nook_mcp  # noqa: E402
from store import Store  # noqa: E402

T0 = dt.datetime(2026, 11, 11, 13, 0).timestamp()   # Wed 11 Nov 2026, 1:00 PM local


@pytest.fixture
def s(tmp_path):
    return Store(str(tmp_path / "t.db"), clock=lambda: T0)


def run(s, name, **a):
    return agent_api.run_tool(s, name, a)


def test_task_round_trip(s):
    t = run(s, "add_task", title="Call Dan", start="09:30", end="10:00")
    assert t["day"] == "2026-11-11" and t["start"] == "09:30" and t["end"] == "10:00" and not t["done"]
    t = run(s, "update_task", id=t["id"], done=True, day="2026-11-12")
    assert t["done"] and t["day"] == "2026-11-12"
    t = run(s, "update_task", id=t["id"], clear_time=True)
    assert t["start"] is None and t["end"] is None
    assert [x["title"] for x in run(s, "list_tasks", **{"from": "2026-11-12"})] == ["Call Dan"]
    assert run(s, "delete_task", id=t["id"])["title"] == "Call Dan"
    assert run(s, "list_tasks", **{"from": "2026-11-12"}) == []


def test_bad_input_is_refused(s):
    with pytest.raises(ValueError):
        run(s, "add_task", title="x", start="9.30", end="10:00")
    with pytest.raises(ValueError):
        run(s, "add_task", title="x", day="12/11/2026")
    with pytest.raises(ValueError):
        run(s, "add_task", title="x", sneaky=1)          # unknown argument
    with pytest.raises(ValueError):
        run(s, "update_task", id=1)                      # nothing to change
    with pytest.raises(KeyError):
        run(s, "drop_everything")


def test_goals_habits_today(s):
    g = run(s, "add_goal", title="Discovery calls", target=30, unit="calls", source="hand")
    g = run(s, "log_goal", id=g["id"], amount=2)
    assert g["done"] == 2 and g["target"] == 30
    assert run(s, "update_goal", id=g["id"], status="paused")["status"] == "paused"
    h = run(s, "add_habit", title="Read")
    run(s, "tick_habit", id=h["id"])
    run(s, "add_task", title="Write offer")
    day = run(s, "get_today")
    assert day["day"] == "2026-11-11"
    assert [t["title"] for t in day["tasks"]] == ["Write offer"]
    assert [x["title"] for x in day["goals"]] == ["Discovery calls"]
    assert [x["title"] for x in day["habits"]] == ["Read"]
    assert "goals" in json.dumps(day, default=str)       # the whole answer is JSON-safe


def test_token_made_once(tmp_path):
    a = agent_api.token(str(tmp_path))
    assert len(a) >= 32 and agent_api.token(str(tmp_path)) == a


@pytest.fixture
def srv(s):
    sv = agent_api.make_server(s, "secret-token-" + "x" * 32, "9.9", port=0)
    threading.Thread(target=sv.serve_forever, daemon=True).start()
    yield sv
    sv.shutdown()
    sv.server_close()


def req(sv, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", sv.server_address[1], timeout=5)
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers or {})
    r = c.getresponse()
    return r.status, json.loads(r.read())


AUTH = {"Authorization": "Bearer secret-token-" + "x" * 32}


def test_http_needs_token(srv):
    assert req(srv, "GET", "/v1/health") == (200, {"ok": True, "app": "Nook", "version": "9.9"})
    assert req(srv, "GET", "/v1/tools")[0] == 401
    assert req(srv, "POST", "/v1/tools/get_today", {}, {"Authorization": "Bearer wrong"})[0] == 401
    code, body = req(srv, "GET", "/v1/tools", headers=AUTH)
    assert code == 200 and "add_task" in [t["name"] for t in body["tools"]]


def test_http_blocks_browsers_and_other_hosts(srv):
    assert req(srv, "POST", "/v1/tools/get_today", {}, {**AUTH, "Origin": "https://evil.example"})[0] == 403
    assert req(srv, "POST", "/v1/tools/get_today", {}, {**AUTH, "Host": "evil.example"})[0] == 403


def test_http_calls_tools(srv):
    code, body = req(srv, "POST", "/v1/tools/add_task", {"title": "Ship it"}, AUTH)
    assert code == 200 and body["result"]["title"] == "Ship it"
    code, body = req(srv, "POST", "/v1/tools/add_task", {"title": ""}, AUTH)
    assert code == 400 and not body["ok"]
    assert req(srv, "POST", "/v1/tools/nope", {}, AUTH)[0] == 404


def test_mcp_bridge():
    init = nook_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": "2025-06-18"}})
    assert init["result"]["protocolVersion"] == "2025-06-18" and "tools" in init["result"]["capabilities"]
    assert nook_mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = nook_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert {"get_today", "add_task", "log_goal"} <= {t["name"] for t in tools}
    assert all(t["inputSchema"]["type"] == "object" for t in tools)
    seen = []
    out = nook_mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "add_task", "arguments": {"title": "A"}}},
                          call=lambda n, a: (seen.append((n, a)), (True, {"id": 7}))[1])
    assert seen == [("add_task", {"title": "A"})]
    assert json.loads(out["result"]["content"][0]["text"]) == {"id": 7} and not out["result"]["isError"]
    err = nook_mcp.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "x"}},
                          call=lambda n, a: (False, "Nook is not running."))
    assert err["result"]["isError"]
    assert nook_mcp.handle({"jsonrpc": "2.0", "id": 5, "method": "bogus"})["error"]["code"] == -32601
