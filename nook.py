"""Deepcus from the command line, for any bot or agent that can run a command.

  py nook.py tools                                  list every tool and its inputs
  py nook.py get_today
  py nook.py add_task title="Gym" start=18:00 end=19:00
  py nook.py tick_habit id=2
  py nook.py add_task '{"title": "Gym", "start": "18:00", "end": "19:00"}'

Talks to the running Deepcus app on this PC (127.0.0.1) with the key from Deepcus's data folder, so
nothing touches the database directly. Prints JSON. Exit code 0 = done, 1 = Deepcus said no, 2 = bad input.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_api  # noqa: E402
import nook_mcp  # noqa: E402


def _schema(name):
    for t in agent_api.tool_list():
        if t["name"] == name:
            return t["input_schema"]
    return None


def _value(raw, spec):
    kind = (spec or {}).get("type")
    if kind == "integer":
        return int(raw)
    if kind == "number":
        return float(raw)
    if kind == "boolean":
        if raw.lower() in ("true", "yes", "1"):
            return True
        if raw.lower() in ("false", "no", "0"):
            return False
        raise ValueError(f"{raw!r} is not true or false")
    if kind in ("array", "object"):
        return json.loads(raw)
    return raw


def parse_args(name, words):
    """key=value words (or one JSON object) -> the tool's input dict."""
    schema = _schema(name)
    if schema is None:
        raise ValueError(f"no tool {name!r}. Run: py nook.py tools")
    if len(words) == 1 and words[0].lstrip().startswith("{"):
        args = json.loads(words[0])
        if not isinstance(args, dict):
            raise ValueError("the JSON must be an object")
        return args
    props, args = schema.get("properties", {}), {}
    for w in words:
        key, eq, raw = w.partition("=")
        if not eq:
            raise ValueError(f"{w!r} should look like key=value")
        if key not in props:
            raise ValueError(f"{name} has no input {key!r}. It takes: {', '.join(props) or 'nothing'}")
        args[key] = _value(raw, props[key])
    return args


def tools_text():
    lines = []
    for t in agent_api.tool_list():
        sch = t["input_schema"]
        req = set(sch.get("required", []))
        ins = [f"{k}{'' if k in req else '?'}" for k in sch.get("properties", {})]
        lines.append(f"{t['name']}({', '.join(ins)})  {t['description']}")
    return "\n".join(lines) + "\n\n? = optional. Times HH:MM (24h). Days YYYY-MM-DD, leave out for today."


def main(argv, call=nook_mcp.http_call, out=print):
    if not argv or argv[0] in ("-h", "--help", "help"):
        out(__doc__.strip())
        return 0
    if argv[0] == "tools":
        out(tools_text())
        return 0
    name = argv[0]
    try:
        args = parse_args(name, argv[1:])
    except ValueError as e:
        out(json.dumps({"ok": False, "error": str(e)}))
        return 2
    ok, res = call(name, args)
    out(json.dumps({"ok": True, "result": res} if ok else {"ok": False, "error": res}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
