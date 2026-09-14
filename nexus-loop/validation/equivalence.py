#!/usr/bin/env python
"""Prove the packaged code is the researched code: same incidents, same report, on every corpus available.

Baselines (validation/baselines/research/) are the outputs of the frozen research scanner (incidents) and of
the verified report fixes (reports, handoff 13.2). Each kit is re-run through nexus.pipeline and compared after
a JSON round trip.

    python validation/equivalence.py [--research-root <dir holding work/ and bench/ from the research session>]
"""
import argparse
import json
import os

from _common import BASELINES, BENCHMARK, PRACTICE_KIT, ROOT, load_json, utf8_stdout

from nexus.pipeline import _json_default, analyse
from nexus.report import incidents_json


def roundtrip(obj):
    return json.loads(json.dumps(obj, default=_json_default))


def first_difference(a, b, path=""):
    if type(a) is not type(b):
        return "%s: %r != %r" % (path or "<root>", a, b)
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return "%s/%s: present only in %s" % (path, k, "new" if k in a else "baseline")
            d = first_difference(a[k], b[k], "%s/%s" % (path, k))
            if d:
                return d
    elif isinstance(a, list):
        if len(a) != len(b):
            return "%s: length %d != %d" % (path, len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_difference(x, y, "%s[%d]" % (path, i))
            if d:
                return d
    elif a != b:
        return "%s: %r != %r" % (path, a, b)
    return None


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--research-root", default=None, help="research scratchpad (for kit-s1..s3, blind-*, kit-clean, day6sim)")
    a = ap.parse_args()
    kits = [("kit", PRACTICE_KIT)] + [(n, os.path.join(BENCHMARK, n)) for n in ("bench-01", "bench-02", "bench-03", "bench-04")]
    if a.research_root:
        kits += [(n, os.path.join(a.research_root, "work", n)) for n in
                 ("kit-s1", "kit-s2", "kit-s3", "blind-blind", "blind-zebra", "blind-delta", "kit-clean", "day6sim")]
    failures = 0
    for name, kit in kits:
        if not os.path.isdir(kit):
            print("SKIP   %-12s kit not found" % name)
            continue
        res = analyse(kit, cache_dir=os.path.join(ROOT, ".cache"), team="nexus-generic-scan")
        row = []
        for label, new, base in (("incidents", incidents_json(res["incidents"]), "incidents-%s.json" % name),
                                 ("report", res["report"], "report-%s.json" % name)):
            bp = os.path.join(BASELINES, base)
            if not os.path.exists(bp):
                row.append("%s: no baseline" % label)
                continue
            diff = first_difference(roundtrip(new), load_json(bp))
            failures += bool(diff)
            row.append("%s: %s" % (label, "IDENTICAL" if not diff else "DIFFERS at " + diff[:140]))
        print("%-6s %-12s %s" % ("FAIL" if any("DIFFERS" in r for r in row) else "OK", name, " | ".join(row)))
    print("equivalence: %s" % ("PASS" if not failures else "%d difference(s)" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
