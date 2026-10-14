#!/usr/bin/env python
"""Record a human decision on a proposed fix from the command line (the same gate the screen uses).

    python decide.py --out out/practice --list
    python decide.py --out out/practice --prescription p3 --verdict rejected --by "Ops lead" \
                     --reason "Keeps the safety wording; the business accepts the extra cost for now."

The decision is appended to decisions.jsonl and written back into loop-report.json after schema validation; the
untouched system output stays in loop-report.generated.json.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from nexus import decisions, screen  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--list", action="store_true", help="list prescriptions and their decision state")
    ap.add_argument("--prescription", help="prescription id (p1) or fix_id")
    ap.add_argument("--verdict", choices=decisions.VERDICTS)
    ap.add_argument("--by", help="who decided")
    ap.add_argument("--reason", help="why, in words")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    if a.list:
        path = os.path.join(a.out, decisions.REPORT)
        with open(path, encoding="utf-8") as fh:
            rep = json.load(fh)
        for p in rep.get("prescriptions", []):
            ap_ = p.get("approval") or {}
            print("%-4s %-15s %-14s %-25s %s" % (p["id"], p.get("fix_id"), p["change_type"], str(p.get("target"))[:25],
                                                 ap_.get("verdict", "pending")))
            print("     asking approval for: %s" % p["decision"]["asking_approval_for"])
        return 0
    if not (a.prescription and a.verdict):
        ap.error("--prescription and --verdict are required (or use --list)")
    try:
        res = decisions.record(a.out, a.prescription, a.verdict, a.by, a.reason,
                               rebuild=lambda rep: screen.write(a.out, rep))
    except decisions.DecisionError as exc:
        print("not saved (%d): %s" % (exc.status, exc.message), file=sys.stderr)
        return 1
    print(json.dumps({k: v for k, v in res.items() if k != "event"}, indent=1))
    print("recorded: %s %s by %s" % (res["event"]["prescription_id"], res["event"]["verdict"], res["event"]["decided_by"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
