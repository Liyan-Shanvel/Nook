"""The `nook` command line: argument parsing and output. Never talks to a real Nook."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nook  # noqa: E402


def test_key_value_args_take_the_schema_types():
    assert nook.parse_args("add_task", ["title=Gym at 6", "start=18:00", "goal_id=3"]) == \
        {"title": "Gym at 6", "start": "18:00", "goal_id": 3}


def test_json_args():
    assert nook.parse_args("add_task", ['{"title": "Gym"}']) == {"title": "Gym"}


@pytest.mark.parametrize("name,words", [("nope", []), ("add_task", ["title"]), ("add_task", ["colour=red"]),
                                        ("add_task", ["goal_id=abc"])])
def test_bad_input_is_refused(name, words):
    with pytest.raises(ValueError):
        nook.parse_args(name, words)


def test_main_calls_the_tool_and_prints_json():
    seen, printed = [], []
    rc = nook.main(["add_task", "title=Gym"], call=lambda n, a: (seen.append((n, a)) or (True, {"id": 7})),
                   out=printed.append)
    assert rc == 0 and seen == [("add_task", {"title": "Gym"})]
    assert json.loads(printed[0]) == {"ok": True, "result": {"id": 7}}


def test_main_reports_nook_errors_with_exit_1():
    printed = []
    rc = nook.main(["get_today"], call=lambda n, a: (False, "Nook is not running."), out=printed.append)
    assert rc == 1 and json.loads(printed[0])["ok"] is False


def test_tools_lists_every_tool():
    text = nook.tools_text()
    assert "add_task(title, description?, day?, start?, end?, goal_id?)" in text
    assert text.count("\n") >= 20
