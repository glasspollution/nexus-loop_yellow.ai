#!/usr/bin/env python
"""Print the numbers the demo script needs, read from the report that will actually be on screen.

    python docs/demo_numbers.py [--report nexus-loop/out/loop-report.json]

Run this after the sealed run and before rehearsing. Every figure in DEMO_SCRIPT.md is written as
a [BRACKET] to be filled from here, because every one of them moves on a corpus we have not seen -
days, tenants, cohorts, counts and even which metric is the headline. A number memorised on day 5
is a wrong number on day 6.
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=os.path.join(ROOT, "nexus-loop", "out", "loop-report.json"))
    a = ap.parse_args()
    with open(a.report, encoding="utf-8") as fh:
        r = json.load(fh)

    regs = [f for f in r["findings"] if f["is_regression"]]
    dis = [f for f in r["findings"] if not f["is_regression"]]
    dg = {d["finding_id"]: d for d in r.get("diagnoses", [])}
    pres = {p["diagnosis_id"]: p for p in r.get("prescriptions", [])}
    vers = {}
    for v in r.get("verifications", []):
        vers.setdefault(v["prescription_id"], []).append(v)

    W = 78
    print("=" * W)
    print("DEMO NUMBERS  |  corpus %s  |  build %s" % (r.get("corpus"), r.get("report_build", "n/a")))
    print("=" * W)

    print("\nCOVERAGE - say one of these OUT LOUD, twice (BEAT 1 and BEAT 9)")
    for t, per in (r.get("coverage_measured") or {}).items():
        print("   %-20s tool metrics %.0f%%   (%s)" % (t, 100 * per.get("tool_call", 0), t))
    print("   Never blend them. A single figure describes neither deployment.")

    cal = [m["calibration"] for m in r["metrics"] if m.get("calibration")]
    if cal:
        c = cal[0]
        print("\nCALIBRATION - BEAT 3 or Q&A")
        print("   agrees with human reviewers %.0f%% of the time, n=%d" % (100 * c["agreement"], c["n"]))
        print("   say: a 1.00 would be a bug, not a good judge - the humans disagree with")
        print("        each other about 7.5% of the time")

    print("\nTHE FINDING YOU OPEN ON  (screen shows these; pick the one with the best story)")
    for f in regs:
        imp = f.get("impact") or {}
        d = dg.get(f["id"], {})
        print("\n   [%s] %s" % (f["id"], f.get("title_plain", "")))
        print("        %s" % f.get("status_plain", ""))
        print("        tenant ............ %s" % f["tenant"])
        print("        cohort ............ %s" % f.get("cohort_label", f.get("cohort")))
        print("        conversations ..... %s" % imp.get("conversations_affected"))
        print("        share of traffic .. %.1f%%" % (100 * (imp.get("share_of_traffic") or 0)))
        dn = imp.get("downstream") or {}
        print("        did not resolve ... %s" % dn.get("would_have_resolved_at_baseline"))
        print("        unplanned handoffs  %s" % dn.get("unplanned_handoffs"))
        print("        days running ...... %s" % imp.get("days_running"))
        print("        cost .............. $%s" % imp.get("cost_usd"))
        print("        cause ............. %s" % d.get("cause_class"))
        att = d.get("attributed_change")
        if att:
            print("        config change ..... day %s, %s" % (att.get("day"), att.get("kind")))
        if imp.get("outcome_note"):
            print("        !! OUTCOME NOTE: %s" % imp["outcome_note"])
        p = pres.get(d.get("id"))
        if p:
            for v in vers.get(p["id"], []):
                if v.get("is_alternative"):
                    continue
                print("        replay ............ %s %s -> %s (%s)" %
                      (v.get("metric"), v.get("before"), v.get("after"), v.get("verdict")))
                if v.get("stop_condition_triggered"):
                    print("        !! STOP CONDITION FIRED - the golden set regressed. Demo this.")

    alt = [v for vs in vers.values() for v in vs if v.get("is_alternative")]
    if alt:
        v = alt[0]
        print("\nTHE FIX THAT DID NOT WORK  (BEAT 6 - worth more than a second success)")
        print("   %s: %s %s -> %s, golden set %s" %
              (v.get("verdict"), v.get("metric"), v.get("before"), v.get("after"),
               "clean" if v.get("golden_set_pass") else "REGRESSED"))

    print("\nTHE LOOKALIKE YOU SHOW  (BEAT 2 - pick the traffic_mix one if present)")
    for f in dis:
        d = dg.get(f["id"], {})
        print("   [%s] %-14s %s" % (f["id"], d.get("cause_class"), f.get("title_plain", "")))

    print("\nTHE REFUSALS  (BEAT 8 - A11 is the scripted one)")
    for g in r.get("gaps", []):
        print("   %-5s %-20s %s" % (g["ask_id"], g["verdict"], (g.get("why") or "")[:58]))
        if g.get("nearest_proxy"):
            print("         tempting answer: %s" % g["nearest_proxy"])
    refused = []
    for m in r["metrics"]:
        for x in (m.get("plan") or {}).get("refused_breakdowns", []):
            if x not in refused:
                refused.append(x)
    for x in refused:
        print("   CARD  %s" % x)

    decided = [p for p in r.get("prescriptions", []) if (p.get("approval") or {}).get("verdict")]
    print("\nDECISIONS ALREADY RECORDED: %d of %d" % (len(decided), len(r.get("prescriptions", []))))
    for p in decided:
        print("   %s  %s by %s" % (p["id"], p["approval"]["verdict"], p["approval"]["decided_by"]))
    if decided:
        print("   >> RESET THESE BEFORE THE DEMO:  python docs/reset_decisions.py")
    print("=" * W)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
