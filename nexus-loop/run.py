#!/usr/bin/env python
"""Nexus Loop: produce loop-report.json from a kit, unattended.

    python run.py --kit ../kit
    python run.py --kit /path/to/day6-kit --out out/day6 --team "<team name>"

Writes <out>/loop-report.json (the deliverable) and <out>/incidents.json (a flat incident list), validates
the report, and prints a summary. Exit code 0 = report written and valid; 1 = report written but it failed
the schema or contract checks (the problems are printed); 2 = the kit could not be read.
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from nexus.pipeline import analyse, write_outputs  # noqa: E402
from nexus.validate import contract_problems, schema_errors  # noqa: E402


def summarise(result, report_path, incidents_path, errs, problems, seconds):
    rep = result["report"]
    print("=" * 100)
    print("Nexus Loop  |  corpus %s  |  %d episodes -> %d incidents  |  %.1fs"
          % (rep.get("corpus"), len(result["episodes"]), len(result["incidents"]), seconds))
    print("-" * 100)
    for inc in result["incidents"]:
        print("  %-3s %-17s %-40s d%2d..%-2d %-20s %s"
              % ("REG" if inc["is_regression"] else "-", inc["tenant"], json.dumps(inc["cohort"])[:40],
                 inc["from"], inc["to"], inc["cause_class"], inc["kind"]))
    print("-" * 100)
    for m in rep["metrics"]:
        cal = (m.get("calibration") or {}).get("agreement")
        print("  metric %-34s %-5s %-9s coverage %.4f%s" % (m["id"], m["ask_id"], m["fidelity"], m["coverage"]["value"],
                                                          "  calibration %.2f" % cal if cal is not None else ""))
    for g in rep["gaps"]:
        print("  gap    %-5s %s" % (g["ask_id"], g["verdict"]))
    print("-" * 100)
    print("  report     %s" % report_path)
    print("  incidents  %s" % incidents_path)
    if errs is None:
        print("  schema     NOT CHECKED (pip install jsonschema)")
    else:
        print("  schema     %s" % ("valid" if not errs else "%d error(s)" % len(errs)))
    print("  contract   %s" % ("ok" if not problems else "%d problem(s)" % len(problems)))
    for line in (errs or []) + problems:
        print("     ! " + line)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--kit", required=True, help="kit directory (catalog.json, corpus/, labels/, asks.md)")
    ap.add_argument("--out", default=os.path.join(ROOT, "out"), help="output directory (default: out/)")
    ap.add_argument("--team", default="nexus-loop", help="team name written into the report")
    ap.add_argument("--cache-dir", default=os.path.join(ROOT, ".cache"), help="loader cache directory")
    ap.add_argument("--no-cache", action="store_true", help="always re-read the corpus")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    t0 = time.time()
    try:
        result = analyse(a.kit, cache_dir=None if a.no_cache else a.cache_dir, team=a.team)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    report_path, incidents_path = write_outputs(result, a.out)
    with open(report_path, encoding="utf-8") as fh:
        written = json.load(fh)             # validate exactly what was written to disk
    errs, problems = schema_errors(written), contract_problems(written)
    summarise(result, report_path, incidents_path, errs, problems, time.time() - t0)
    return 1 if (errs or problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
