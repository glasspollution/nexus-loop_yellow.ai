#!/usr/bin/env python
"""Definition of done for the 55 machine points (handoff 13.3), checked end to end through the real CLI.

    python validation/make_corpora.py      # once
    python validation/run_all.py

Every kit is run with `python run.py` in a subprocess, exactly as on day 6. Writes validation/results/summary.md
and summary.json; exit code 1 if any check fails.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

from _common import (BENCHMARK, DATA, PRACTICE_KIT, RESULTS, ROOT, find_ground_truth, load_json, score,
                     utf8_stdout)

DETECTION_SOURCES = ("config.py", "loader.py", "detect.py", "multiscale.py", "cohorts.py", "incidents.py", "diagnose.py")
COHORT_KEYS = {"tenant", "intent", "agent_id", "tool", "tool_name", "channel", "segment"}
CHECKS = []


def check(item, name, ok, detail=""):
    CHECKS.append({"item": item, "check": name, "ok": bool(ok), "detail": detail})
    print("  [%s] %-4s %-58s %s" % ("PASS" if ok else "FAIL", item, name, detail))


def run_cli(kit, name, cold=False):
    out = os.path.join(RESULTS, name)
    cmd = [sys.executable, os.path.join(ROOT, "run.py"), "--kit", kit, "--out", out]
    if cold:
        cmd.append("--no-cache")
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, time.time() - t0, out, p.stdout + p.stderr


def regression_matches(report, fault):
    """score.py's own matching rule: tenant, ANY cohort key/value, window overlap with 3 days' tolerance."""
    hits = []
    for f in report["findings"]:
        if not f.get("is_regression") or f.get("tenant") != fault["tenant"]:
            continue
        if fault.get("cohort") and not any(str((f.get("cohort") or {}).get(k, "")).lower() == str(v).lower()
                                           for k, v in fault["cohort"].items()):
            continue
        w = f.get("window") or {}
        if not (w.get("to_day", 999) < fault["onset_day"] - 3 or w.get("from_day", -999) > fault["onset_day"] + fault["duration_days"]):
            hits.append(f)
    return hits


def report_checks(name, rep, catalog):
    check(6, "%s: no pipeline-written approval" % name, not any("approval" in p for p in rep["prescriptions"]))
    ms = rep["metrics"]
    check(7, "%s: every metric has fidelity + coverage.value" % name,
          all(m.get("fidelity") and m["coverage"].get("value") is not None for m in ms))
    tool_ms = [m for m in ms if "tool" in (m["plan"]["source"] + m["name"]).lower() or "tool_call" in m["plan"]["filter"]]
    per_tenant = all("tenant = '" in m["plan"]["filter"] for m in tool_ms)
    check(7, "%s: tool-derived metrics are per tenant" % name, tool_ms and per_tenant, "%d tool metrics" % len(tool_ms))
    cals = [m["calibration"]["agreement"] for m in ms if (m.get("calibration") or {}).get("agreement") is not None]
    check(7, "%s: calibration published and < 0.995" % name, cals and max(cals) < 0.995, str(cals))
    fid = {}
    for m in ms:                                   # score.py reads the FIRST metric declared for an ask
        fid.setdefault(m["ask_id"], m["fidelity"])
    check(7, "%s: A04 measured, A09 judged (first metric per ask)" % name,
          fid.get("A04") == "measured" and fid.get("A09") == "judged", "A04=%s A09=%s" % (fid.get("A04"), fid.get("A09")))
    gaps = {g["ask_id"]: g for g in rep["gaps"]}
    need = set()
    for cap in catalog.get("capabilities", []):
        if cap.get("class") == "NOT_MEASURABLE":
            need |= set((cap.get("required_event") or {}).get("fields") or [])
    a11 = gaps.get("A11") or {}
    check(8, "%s: A11 NOT_MEASURABLE with the catalog's event fields" % name,
          a11.get("verdict") == "NOT_MEASURABLE" and need <= set((a11.get("required_event") or {}).get("fields") or [])
          and a11.get("nearest_proxy") and a11.get("why_the_proxy_misleads"))
    check(8, "%s: A09 REQUIRES_NEW_JUDGE" % name, (gaps.get("A09") or {}).get("verdict") == "REQUIRES_NEW_JUDGE")
    refused = [m["plan"].get("refused_breakdowns") for m in ms]
    check(9, "%s: refused breakdowns cited on every metric + notes" % name,
          all(refused) and all(r.split(":")[0] in rep["system_notes"] for r in refused[0]), (refused[0] or [""])[0][:70])
    for p in rep["prescriptions"]:
        if not (p.get("decision") and (p.get("predicted_delta") or {}).get("to") is not None):
            check(6, "%s: prescription %s framed as decision with prediction" % (name, p["id"]), False)


def generality_check(ground_truths):
    literals = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in COHORT_KEYS and isinstance(v, str) and v not in ("*", ""):
                    literals.add(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for g in ground_truths:
        walk(g)
    hits = []
    for src in DETECTION_SOURCES:
        text = open(os.path.join(ROOT, "nexus", src), encoding="utf-8").read()
        hits += ["%s:%s" % (src, lit) for lit in sorted(literals)
                 if re.search(r"""["']%s["']""" % re.escape(lit), text)]
    check(10, "no tenant/intent/agent/tool literal in detection code", not hits,
          "%d literals searched; %s" % (len(literals), ", ".join(hits[:5]) or "none found"))


def main():
    utf8_stdout()
    shutil.rmtree(RESULTS, ignore_errors=True)
    os.makedirs(RESULTS)
    ground_truths = []

    print("\n== 1. day-6 layout: no ground truth, cold cache, one command")
    kit = os.path.join(DATA, "day6-layout")
    code, secs, out, log = run_cli(kit, "day6-layout", cold=True)
    check(1, "day6-layout: exit 0, report written, < 60 s", code == 0 and os.path.exists(os.path.join(out, "loop-report.json"))
          and secs < 60, "exit %d, %.1f s" % (code, secs))

    print("\n== 2-3, 6-9, 11. scored corpora (practice + fresh sealed)")
    scored = [("practice", PRACTICE_KIT)] + [(os.path.basename(k), k) for k in sorted(glob.glob(os.path.join(DATA, "sealed-*")))]
    check(3, "at least 3 fresh sealed corpora present", len(scored) >= 4, "%d sealed" % (len(scored) - 1))
    for name, kit in scored:
        code, secs, out, log = run_cli(kit, name)
        rp = os.path.join(out, "loop-report.json")
        check(2, "%s: run.py exit 0 (schema valid, contract ok)" % name, code == 0, "%.1f s" % secs)
        if not os.path.exists(rp):
            print(log[-1500:])
            continue
        rep, gt_path = load_json(rp), find_ground_truth(kit)
        gt = load_json(gt_path)
        ground_truths.append(gt)
        sc = score(rp, gt_path)
        sec = {k: v["score"] for k, v in sc["sections"].items()}
        check(3, "%s: score.py 55.00" % name, abs(sc["machine_score"] - 55.0) < 1e-6,
              "%.2f  %s" % (sc["machine_score"], " ".join("%s=%s" % (k.split()[0][:4], v) for k, v in sec.items())))
        report_checks(name, rep, load_json(os.path.join(kit, "catalog.json")))
        counts = {f["id"]: len(regression_matches(rep, f)) for f in gt["faults"]}
        check(11, "%s: exactly one regression finding per planted fault" % name, all(v == 1 for v in counts.values()), str(counts))

    print("\n== 4. clean corpus")
    code, secs, out, log = run_cli(os.path.join(DATA, "clean-practice"), "clean-practice")
    rep = load_json(os.path.join(out, "loop-report.json"))
    regs = [f for f in rep["findings"] if f.get("is_regression")]
    dismissed = [f for f in rep["findings"] if not f.get("is_regression")]
    check(4, "clean-practice: 0 regressions, dismissals still emitted", code == 0 and not regs and dismissed,
          "%d regressions, %d dismissals" % (len(regs), len(dismissed)))

    print("\n== 5. independent benchmark")
    inc_dir = os.path.join(RESULTS, "benchmark-incidents")
    os.makedirs(inc_dir)
    for bench in sorted(glob.glob(os.path.join(BENCHMARK, "bench-0*"))):
        name = os.path.basename(bench)
        code, secs, out, log = run_cli(bench, name)
        check(2, "%s: run.py exit 0" % name, code == 0, "%.1f s" % secs)
        shutil.copy(os.path.join(out, "incidents.json"), os.path.join(inc_dir, "incidents-%s.json" % name))
        ground_truths.append(load_json(os.path.join(bench, "answer_key.json")))
    ev = subprocess.run([sys.executable, os.path.join(BENCHMARK, "evaluate_all.py"), "--incidents-dir", inc_dir,
                         "--split", "all", "--json"], capture_output=True, text=True, encoding="utf-8")
    c = json.loads(ev.stdout)["combined"]
    check(5, "benchmark: >=14/16 exact, 12/12 planted, 4/4 benign, 0 decoy FA, 0 FP",
          c["exact_localised"] >= 14 and c["planted_hit"] == c["planted_total"] == 12 and c["benign_pass"] == 4
          and c["decoy_false_alarms"] == 0 and c["false_positives"] == 0,
          "novel %d/%d exact %d cause %d planted %d/%d benign %d/%d decoyFA %d FP %d"
          % (c["novel_hit"], c["novel_total"], c["exact_localised"], c["cause_correct"], c["planted_hit"],
             c["planted_total"], c["benign_pass"], c["benign_total"], c["decoy_false_alarms"], c["false_positives"]))

    print("\n== 10. generality")
    generality_check(ground_truths)

    failed = [x for x in CHECKS if not x["ok"]]
    with open(os.path.join(RESULTS, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"passed": len(CHECKS) - len(failed), "failed": len(failed), "checks": CHECKS}, fh, indent=1)
    with open(os.path.join(RESULTS, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("# Definition of done (handoff 13.3)\n\n%d checks, %d failed\n\n| # | check | result | detail |\n|---|---|---|---|\n"
                 % (len(CHECKS), len(failed)))
        for x in CHECKS:
            fh.write("| %s | %s | %s | %s |\n" % (x["item"], x["check"], "PASS" if x["ok"] else "**FAIL**",
                                                 str(x["detail"]).replace("|", "/")))
    print("\n%d checks, %d failed  ->  %s" % (len(CHECKS), len(failed), os.path.join(RESULTS, "summary.md")))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
