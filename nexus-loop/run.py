#!/usr/bin/env python
"""Nexus Loop: produce loop-report.json from a kit, unattended.

    python run.py --kit ../kit
    python run.py --kit /path/to/day6-kit --out out/day6 --team "<team name>" --replay-url http://<host>:8719

Detect, diagnose, prescribe and verify run linked and unattended; the only human step is the approval gate
(server.py or decide.py). Writes into --out:
  loop-report.generated.json   the system's output, untouched
  loop-report.json             the deliverable: the generated report plus any recorded human decisions
  screen.json                  everything the screen shows, with every number's definition resolved
  incidents.json, golden_set.json, definitions.json, replay_trace.json

Exit code 0 = report written and valid; 1 = report written but it failed the schema or contract checks (the problems
are printed); 2 = the kit could not be read.
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from nexus.pipeline import analyse, validate_file, write_outputs  # noqa: E402

STATE = os.path.join(ROOT, "state")


def _fmt(x, pct=False):
    if x is None:
        return "n/a"
    return "%.1f%%" % (100 * x) if pct else "{:,}".format(int(round(x)))


def summarise(result, paths, gen_check, rep_check, seconds):
    rep = result["report"]
    print("=" * 110)
    print("Nexus Loop  |  corpus %s  |  %d episodes -> %d incidents  |  %.1fs"
          % (rep.get("corpus"), len(result["episodes"]), len(result["incidents"]), seconds))
    print("-" * 110)
    for inc in result["incidents"]:
        print("  %-3s %-17s %-40s d%2d..%-2d %-20s %s"
              % ("REG" if inc["is_regression"] else "-", inc["tenant"], str(inc["cohort"])[:40],
                 inc["from"], inc["to"], inc["cause_class"], inc["kind"]))
    print("-" * 110)
    ver = {v["prescription_id"]: v for v in rep["verifications"]}
    for f in rep["findings"]:
        if not f.get("is_regression"):
            continue
        imp = f.get("impact") or {}
        ds = imp.get("downstream") or {}
        p = next((x for x in rep["prescriptions"] if x["diagnosis_id"] == "d" + f["id"][1:]), None)
        v = ver.get(p["id"]) if p else None
        print("  %s %-8s %-9s exposed %6s hit %6s lost %6s humans+ %5s cost+ %8s | %-13s | replay %s"
              % (f["id"], f.get("severity"), (imp.get("status") or {}).get("state"), _fmt(imp.get("conversations_affected")),
                 _fmt(ds.get("conversations_hit")), _fmt(ds.get("would_have_resolved_at_baseline")),
                 _fmt(ds.get("unplanned_handoffs")), "n/a" if imp.get("cost_usd") is None else "$%.2f" % imp["cost_usd"],
                 p["change_type"] if p else "-",
                 ("%s %s->%s %s" % (v["verdict"], v["before"], v["after"], v["gate"])) if v else "not verified"))
    print("-" * 110)
    for m in rep["metrics"]:
        cal = (m.get("calibration") or {}).get("agreement")
        print("  metric %-34s %-5s %-9s coverage %.4f%s" % (m["id"], m["ask_id"], m["fidelity"], m["coverage"]["value"],
                                                          "  calibration %.2f" % cal if cal is not None else ""))
    for g in rep["gaps"]:
        print("  gap    %-5s %s" % (g["ask_id"], g["verdict"]))
    sa = rep.get("self_assessment") or {}
    print("  self-assessment cycles %s  %s" % (sa.get("cycles"), sa.get("prescription_accuracy")))
    print("-" * 110)
    for label, key in (("generated", "generated"), ("report", "report"), ("screen", "screen"), ("incidents", "incidents")):
        print("  %-10s %s" % (label, paths[key]))
    for label, (errs, probs) in (("generated", gen_check), ("report", rep_check)):
        if errs is None:
            print("  schema     NOT CHECKED (pip install jsonschema)")
        else:
            print("  %-10s schema %s, contract %s" % (label, "valid" if not errs else "%d error(s)" % len(errs),
                                                     "ok" if not probs else "%d problem(s)" % len(probs)))
        for line in (errs or []) + probs:
            print("     ! " + line)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--kit", required=True, help="kit directory (catalog.json, corpus/, labels/, asks.md)")
    ap.add_argument("--out", default=os.path.join(ROOT, "out"), help="output directory (default: out/)")
    ap.add_argument("--team", default="nexus-loop", help="team name written into the report")
    ap.add_argument("--cache-dir", default=os.path.join(ROOT, ".cache"), help="loader cache directory")
    ap.add_argument("--no-cache", action="store_true", help="always re-read the corpus")
    ap.add_argument("--replay-url", default=os.environ.get("NEXUS_REPLAY_URL"),
                    help="replay service base URL (or env NEXUS_REPLAY_URL); without it fixes are left unverified")
    ap.add_argument("--replay-team", default=os.environ.get("NEXUS_REPLAY_TEAM"),
                    help="team identity the replay budget is counted against (default: --team)")
    ap.add_argument("--replay-cache", default=os.path.join(STATE, "replay-cache"),
                    help="replay response cache + call ledger; a re-run never spends budget twice")
    ap.add_argument("--max-replay-calls", type=int, default=8, help="new replay calls allowed in this run")
    ap.add_argument("--ledger", default=os.path.join(STATE, "selfassess_ledger.jsonl"),
                    help="persistent self-assessment ledger (one batch per corpus run)")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    t0 = time.time()
    try:
        result = analyse(a.kit, cache_dir=None if a.no_cache else a.cache_dir, team=a.team, replay_url=a.replay_url,
                         replay_team=a.replay_team, replay_cache=a.replay_cache, max_replay_calls=a.max_replay_calls,
                         ledger=a.ledger)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    paths = write_outputs(result, a.out, ledger=a.ledger)
    gen_check, rep_check = validate_file(paths["generated"]), validate_file(paths["report"])
    summarise(result, paths, gen_check, rep_check, time.time() - t0)
    bad = any(errs or probs for errs, probs in (gen_check, rep_check))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
