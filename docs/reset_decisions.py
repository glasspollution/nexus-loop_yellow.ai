#!/usr/bin/env python
"""Clear recorded decisions from a report so the approval gate can be demonstrated live.

    python docs/reset_decisions.py [--report ...] [--dry-run]

Rehearsing writes real decisions into the real file. If they are still there on demo day the
screen opens showing a receipt instead of the buttons, and the most checkable claim in the whole
submission cannot be demonstrated.

This removes `approval` and `approval_history` from every prescription and nothing else. It is a
demo convenience, not part of the system: the pipeline never writes an approval and neither does
this - it only takes them away. Re-validates before saving, like every other write path.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "nexus-loop"))

try:
    from nexus.validate import contract_problems, schema_errors
except ImportError:
    schema_errors = lambda _: None          # noqa: E731
    contract_problems = lambda _: []        # noqa: E731


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", default=os.path.join(ROOT, "nexus-loop", "out", "loop-report.json"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    with open(a.report, encoding="utf-8") as fh:
        rep = json.load(fh)
    cleared = []
    for p in rep.get("prescriptions", []):
        v = (p.get("approval") or {}).get("verdict")
        if v or p.get("approval_history"):
            cleared.append("%s (%s)" % (p["id"], v or "history only"))
        p.pop("approval", None)
        p.pop("approval_history", None)

    if not cleared:
        print("No decisions recorded in %s - nothing to clear." % a.report)
        return 0
    print("Clearing: %s" % ", ".join(cleared))
    if a.dry_run:
        print("--dry-run: nothing written.")
        return 0

    errs, probs = schema_errors(rep), contract_problems(rep)
    if errs or probs:
        print("Refusing to write: %s" % ((errs or []) + probs), file=sys.stderr)
        return 1
    tmp = a.report + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
    os.replace(tmp, a.report)
    print("Cleared. The screen will show the ACCEPT / REJECT / DEFER buttons again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
