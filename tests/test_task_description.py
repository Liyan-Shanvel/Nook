"""1.2.3: tasks carry a description; agents must write short titles."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent_api  # noqa: E402
from store import Store  # noqa: E402


@pytest.fixture
def s(tmp_path):
    return Store(str(tmp_path / "t.db"), clock=lambda: 1_794_600_000.0)


def test_description_round_trip(s):
    t = agent_api.run_tool(s, "add_task", {"title": "Send 10 nursing home emails",
                                           "description": "File SEND_TODAY.txt, 5 min apart."})
    assert t["description"] == "File SEND_TODAY.txt, 5 min apart."
    assert "notes" not in t
    t = agent_api.run_tool(s, "update_task", {"id": t["id"], "description": "Changed"})
    assert t["description"] == "Changed"
    t = agent_api.run_tool(s, "update_task", {"id": t["id"], "description": ""})
    assert t["description"] == ""
    assert agent_api.run_tool(s, "get_today", {})["tasks"][0]["description"] == ""


def test_other_edits_keep_the_description(s):
    t = s.add_task("Gym", notes="Legs day")
    s.update_task(t["id"], {"done": True})
    assert s.task(t["id"])["notes"] == "Legs day"
    assert s.task(s.duplicate_task(t["id"])["id"])["notes"] == "Legs day"


def test_agent_titles_must_be_short(s):
    long = "Send 10 nursing home emails (Nurse Staffing TX) - on clipboard / SEND_TODAY_demand_top10.txt"
    with pytest.raises(ValueError, match="description"):
        agent_api.run_tool(s, "add_task", {"title": long})
    t = agent_api.run_tool(s, "add_task", {"title": "Short one"})
    with pytest.raises(ValueError):
        agent_api.run_tool(s, "update_task", {"id": t["id"], "title": long})
    assert s.add_task(long)["title"] == long          # a person typing in the app is not limited


def test_description_cap(s):
    with pytest.raises(ValueError):
        s.add_task("X", notes="a" * (Store.NOTES_MAX + 1))
