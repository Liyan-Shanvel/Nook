"""py -m smarttrack once | run [-v] [--for=SECONDS] | today [YYYY-MM-DD] | sort [--dry]"""
import datetime as dt
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

from . import capture, insights, recorder, rules  # noqa: E402


def main(argv):
    cmd = argv[0] if argv else "once"
    if cmd == "once":
        s = capture.sample()
        print(json.dumps(s, indent=1))
        if s:
            print("->", rules.classify(s["exe"], s["title"], s["host"], rules.load(recorder.RULES_JSON)))
    elif cmd == "run":
        print("smarttrack recording to", recorder.DB, "(Ctrl+C to stop)")
        secs = next((int(a.split("=")[1]) for a in argv if a.startswith("--for=")), None)
        recorder.run(verbose="-v" in argv, seconds=secs)
    elif cmd == "today":
        day = argv[1] if len(argv) > 1 else dt.date.today().isoformat()
        con = recorder.connect()
        print(json.dumps(insights.report(con, day), indent=1))
    elif cmd == "sort":
        from . import ai_sort
        con = recorder.connect()
        ai_sort.sort_unknowns(con, dry="--dry" in argv)
        if "--dry" not in argv:
            ai_sort.mark_ran()
    else:
        print(__doc__)


main(sys.argv[1:])
