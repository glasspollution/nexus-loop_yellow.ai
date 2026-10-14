#!/usr/bin/env python
"""Prove the packaged detection is the researched detection: same incidents, same scored report skeleton.

Baselines (validation/baselines/research/) are the outputs of the frozen research scanner (incidents) and of
the verified report fixes (reports, handoff 13.2). Each kit is re-run through nexus.pipeline and compared after
a JSON round trip: incidents byte-for-byte, reports on everything score.py reads (findings' tenant, cohort, window
and regression flag; diagnoses' cause and attributed change; metrics; gaps). The decision layer built afterwards is
verified by validation/run_all.py.

Accepted detection changes since the research freeze (each re-verified on every corpus before its baseline moved):
  * 2026-09-16, same-weekday volume baseline for spikes and drops, and load judged only on "nothing outlives the
    surge" (handoff section 11, rows 20-21). The only baseline effect: bench-01 gains the dismissal of its planted
    holiday volume drop (benign event B1, days 7-8), which the weekday-blind detector had missed.

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


def skeleton(rep):
    """What score.py and the detection proof depend on. The decision layer (impact text, evidence wording,
    prescriptions, standard, verifications) was redesigned after the research freeze and is checked by
    validation/run_all.py instead."""
    return {"team": rep.get("team"), "corpus": rep.get("corpus"), "metrics": rep.get("metrics"), "gaps": rep.get("gaps"),
            "findings": [dict({k: f.get(k) for k in ("id", "tenant", "cohort", "window", "is_regression")},
                              dismissal_explained=bool(f.get("not_a_regression_because")))
                         for f in rep.get("findings", [])],
            "diagnoses": [{k: d.get(k) for k in ("id", "finding_id", "cause_class", "attributed_change", "confidence")}
                          for d in rep.get("diagnoses", [])]}


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
                                 ("report skeleton", res["report"], "report-%s.json" % name)):
            bp = os.path.join(BASELINES, base)
            if not os.path.exists(bp):
                row.append("%s: no baseline" % label)
                continue
            new_v, base_v = roundtrip(new), load_json(bp)
            if label.startswith("report"):
                new_v, base_v = skeleton(new_v), skeleton(base_v)
            diff = first_difference(new_v, base_v)
            failures += bool(diff)
            row.append("%s: %s" % (label, "IDENTICAL" if not diff else "DIFFERS at " + diff[:140]))
        print("%-6s %-12s %s" % ("FAIL" if any("DIFFERS" in r for r in row) else "OK", name, " | ".join(row)))
    print("equivalence: %s" % ("PASS" if not failures else "%d difference(s)" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
