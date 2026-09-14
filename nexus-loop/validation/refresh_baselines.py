#!/usr/bin/env python
"""Regenerate the research REPORT baselines after a deliberate report change.

    python validation/refresh_baselines.py [--check]

Use this when the report gains or changes a field on purpose - new prose keys, a new honesty
block - and equivalence.py then reports "DIFFERS at /<that key>".

It rewrites only `report-*.json`. The `incidents-*.json` baselines are never touched: those are
the frozen output of the research scanner and are the check that actually matters. If detection or
diagnosis changed, incidents stop comparing IDENTICAL and no amount of refreshing reports will
hide it - which is the point.

The team name must match the one equivalence.py analyses with, or every report_build hash differs
and the diff is unreadable. That is easy to get wrong by hand, which is why this exists.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _common import BASELINES, BENCHMARK, PRACTICE_KIT, ROOT, load_json, utf8_stdout  # noqa: E402

from nexus.pipeline import _json_default, analyse  # noqa: E402

TEAM = "nexus-generic-scan"          # must match equivalence.py
KITS = [("kit", PRACTICE_KIT)] + [("bench-0%d" % i, os.path.join(BENCHMARK, "bench-0%d" % i))
                                  for i in (1, 2, 3, 4)]


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="report what would change without writing anything")
    a = ap.parse_args()
    changed = 0
    for name, kit in KITS:
        if not os.path.isdir(kit):
            print("SKIP   %-10s kit not found" % name)
            continue
        dest = os.path.join(BASELINES, "report-%s.json" % name)
        new = json.loads(json.dumps(analyse(kit, cache_dir=os.path.join(ROOT, ".cache"),
                                            team=TEAM)["report"], default=_json_default))
        old = load_json(dest) if os.path.exists(dest) else None
        if old == new:
            print("SAME   %-10s" % name)
            continue
        changed += 1
        added = sorted(set(new) - set(old or {}))
        removed = sorted(set(old or {}) - set(new))
        note = ("+%s " % ",".join(added) if added else "") + ("-%s" % ",".join(removed) if removed else "")
        if a.check:
            print("WOULD  %-10s %s" % (name, note or "values changed"))
            continue
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(new, fh, indent=1)
        print("WROTE  %-10s %s" % (name, note or "values changed"))
    print("%d baseline(s) %s. Incidents baselines untouched - run equivalence.py to confirm "
          "they still compare IDENTICAL." % (changed, "would change" if a.check else "refreshed"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
