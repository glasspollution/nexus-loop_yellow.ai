#!/usr/bin/env python
"""Mechanically check the report and screen against the rubric, before a judge does.

    python docs/judge_check.py [--report ...] [--screen screen/index.html]

Every check here is observable pass/fail with no judgement call, so it can be run repeatedly and
cannot be talked into passing. It does NOT check the things that need a person - whether the prose
is any good, whether a stranger understands the screen (docs/STRANGER_TEST.md), or whether the demo
lands under ten minutes. Those are the ones that actually carry the points; this catches the
stupid ways of losing them.

Exit code 0 if nothing failed, 1 otherwise. WARN does not fail the run.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIENCES = {"business_owner", "agent_builder", "platform_owner"}
VERDICTS = {"accepted", "rejected", "deferred"}
JARGON = ["kb.gap", "tool.contract_break", "prompt.regression", "traffic_mix", "judge_change",
          "is_regression", "cohort", "resolution_rate", "kb_miss", "detection", "diagnosis",
          "prescription", "verification", "z=", "p95"]

rows = []


def check(group, name, ok, detail="", warn=False):
    rows.append((group, name, "WARN" if (warn and not ok) else ("PASS" if ok else "FAIL"), detail))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", default=os.path.join(ROOT, "nexus-loop", "out", "loop-report.json"))
    ap.add_argument("--screen", default=os.path.join(ROOT, "screen", "index.html"))
    a = ap.parse_args()

    if not os.path.exists(a.report):
        print("No report at %s - run nexus-loop/run.py first." % a.report, file=sys.stderr)
        return 2
    with open(a.report, encoding="utf-8") as fh:
        r = json.load(fh)

    regs = [f for f in r.get("findings", []) if f.get("is_regression")]
    dis = [f for f in r.get("findings", []) if not f.get("is_regression")]
    dg = {d["finding_id"]: d for d in r.get("diagnoses", [])}
    pres = r.get("prescriptions", [])

    # ---------------- Decision Quality ----------------
    G = "Decision Quality"
    check(G, "at least one regression reported", bool(regs), "%d found" % len(regs))

    bad = [f["id"] for f in regs if not f.get("title_plain")]
    check(G, "every finding has a plain-English title", not bad, "missing: %s" % bad)

    bad = []
    for f in regs:
        t = (f.get("title_plain") or "").lower()
        hits = [j for j in JARGON if j in t]
        # An intent key is internal taxonomy and must be translated: "premium_card_info" means
        # nothing to an operator. A tool or agent identifier is a proper noun - it is the real name
        # of the thing that has to be edited, the audience is the person who edits it, and
        # translating "get_order_status" into "the order status tool" would remove the one string
        # they need. So only intent keys are treated as leakage here.
        for k, v in (f.get("cohort") or {}).items():
            if k == "intent" and str(v).lower() in t:
                hits.append("raw intent key %r" % v)
        if hits:
            bad.append("%s: %s" % (f["id"], ", ".join(hits)))
    check(G, "no metric name or intent key in any title", not bad, "; ".join(bad))

    for field, label in [("conversations_affected", "conversations affected"),
                         ("share_of_traffic", "share of traffic"),
                         ("days_running", "duration in days"),
                         ("derivation", "a derivation someone could re-run")]:
        bad = [f["id"] for f in regs if (f.get("impact") or {}).get(field) is None]
        check(G, "every finding states %s" % label, not bad, "missing: %s" % bad)

    bad = [f["id"] for f in regs if (f.get("impact") or {}).get("cost_usd") is None]
    check(G, "every finding states cost", not bad, "missing: %s" % bad, warn=True)

    bad = [f["id"] for f in regs
           if not set(f.get("audience") or []) or not set(f.get("audience") or []) <= AUDIENCES]
    check(G, "every finding names a valid audience", not bad, "bad: %s" % bad)

    bad = [f["id"] for f in regs if not (f.get("if_nothing_changes") or "").strip()]
    check(G, "every finding says what happens if nobody acts", not bad, "missing: %s" % bad)

    bad = [f["id"] for f in regs if not ((f.get("baseline") or {}).get("justification") or "").strip()]
    check(G, "every finding justifies its baseline in a sentence", not bad, "missing: %s" % bad)

    # the archetype trap: a fault whose outcome never moves must say so
    flat = [f for f in regs if (f.get("impact") or {}).get("impact_type") == "spend_and_time"]
    bad = [f["id"] for f in flat if not (f.get("impact") or {}).get("outcome_note")]
    check(G, "a flat-outcome finding says the outcome did not move", not bad,
          "%d flat-outcome finding(s); missing note: %s" % (len(flat), bad))
    # A flat-outcome finding may still carry a small non-zero lost count - that is what the
    # arithmetic returns for a difference inside the noise. What it may NOT do is leave that count
    # standing unexplained next to "the outcome did not move", because the two read as a
    # contradiction. Require the note to account for it.
    bad = []
    for f in flat:
        lost = ((f.get("impact") or {}).get("downstream") or {}).get("would_have_resolved_at_baseline", 0)
        note = (f.get("impact") or {}).get("outcome_note") or ""
        if lost and str(lost) not in note:
            bad.append("%s: claims %d lost, note does not account for it" % (f["id"], lost))
    check(G, "a flat-outcome finding reconciles any lost-resolution count", not bad, "; ".join(bad))
    bad = [f["id"] for f in flat
           if "sampling error" not in ((f.get("impact") or {}).get("outcome_note") or "")]
    check(G, "a flat-outcome finding quantifies the noise it is claiming", not bad,
          "no sampling error stated: %s" % bad, warn=True)

    bad = [f["id"] for f in dis if not (f.get("not_a_regression_because") or "").strip()]
    check(G, "every dismissal is dismissed in writing", not bad, "silent: %s" % bad)

    bad = [p["id"] for p in pres
           if not ((p.get("decision") or {}).get("asking_approval_for") or "").strip()]
    check(G, "every prescription states what is being approved", not bad, "missing: %s" % bad)
    bad = [p["id"] for p in pres
           if re.search(r"[{}']", (p.get("decision") or {}).get("asking_approval_for", ""))]
    check(G, "no prescription renders a raw dict at an operator", not bad, "raw: %s" % bad)
    bad = [p["id"] for p in pres if "investigate further" in json.dumps(p.get("decision") or {}).lower()]
    check(G, 'no finding says "investigate further"', not bad, "%s" % bad)
    for f, label in [("risk_if_diagnosis_wrong", "the risk if the diagnosis is wrong"),
                     ("would_not_ship_if", "what would stop it shipping")]:
        bad = [p["id"] for p in pres if not ((p.get("decision") or {}).get(f) or "").strip()]
        check(G, "every prescription states %s" % label, not bad, "missing: %s" % bad)
    uniq = {(p.get("decision") or {}).get("risk_if_diagnosis_wrong") for p in pres}
    check(G, "risk text is not one boilerplate line reused", len(uniq) > 1 or len(pres) <= 1,
          "%d distinct across %d prescriptions" % (len(uniq), len(pres)), warn=True)

    # ---------------- Honesty ----------------
    G = "Honesty"
    bad = [m["id"] for m in r.get("metrics", [])
           if not m.get("fidelity") or (m.get("coverage") or {}).get("value") is None]
    check(G, "every metric carries fidelity and coverage", not bad, "missing: %s" % bad)

    cals = [(m["id"], (m.get("calibration") or {}).get("agreement")) for m in r.get("metrics", [])
            if m.get("calibration")]
    check(G, "at least one calibration is published", bool(cals), "%d" % len(cals))
    bad = [i for i, v in cals if v is not None and v >= 0.995]
    check(G, "no calibration is >= 0.995", not bad, "suspicious: %s" % bad)

    cov = r.get("coverage_measured") or {}
    check(G, "coverage is stated per tenant, never blended", len(cov) >= 1,
          ", ".join("%s tool=%.4f" % (t, v.get("tool_call", -1)) for t, v in cov.items()))

    check(G, "at least one question is refused", bool(r.get("gaps")), "%d gaps" % len(r.get("gaps", [])))
    nm = [g for g in r.get("gaps", []) if g.get("verdict") == "NOT_MEASURABLE"]
    bad = [g["ask_id"] for g in nm if not (g.get("required_event") or {}).get("fields")]
    check(G, "each NOT_MEASURABLE gap names the event and its fields", nm and not bad,
          "missing fields: %s" % bad)
    bad = [g["ask_id"] for g in nm if not (g.get("required_event") or {}).get("owner")]
    check(G, "each refusal names the team that owns emitting it", not bad, "missing owner: %s" % bad)
    bad = [g["ask_id"] for g in nm
           if not (g.get("nearest_proxy") and g.get("why_the_proxy_misleads"))]
    check(G, "each refusal names the tempting wrong answer and why it misleads", not bad,
          "missing: %s" % bad)
    refused = {x for m in r.get("metrics", []) for x in (m.get("plan") or {}).get("refused_breakdowns", [])}
    check(G, "the cardinality refusal is present", bool(refused),
          "; ".join(sorted(refused))[:80])

    ids = [g["ask_id"] for g in r.get("gaps", [])]
    check(G, "no two gaps share an ask_id", len(ids) == len(set(ids)), "%s" % ids)

    # ---------------- The Screen ----------------
    G = "The Screen"
    decided = [p for p in pres if (p.get("approval") or {}).get("verdict")]
    check(G, "a human decision is recorded in the report", bool(decided),
          "%d of %d prescriptions" % (len(decided), len(pres)),
          warn=True)
    bad = []
    for p in decided:
        ap_ = p["approval"]
        if ap_.get("verdict") not in VERDICTS:
            bad.append("%s: bad verdict %r" % (p["id"], ap_.get("verdict")))
        for k in ("decided_by", "reason", "at"):
            if not isinstance(ap_.get(k), str) or not ap_.get(k).strip():
                bad.append("%s: %s empty" % (p["id"], k))
    check(G, "every recorded decision carries who, why and when", not bad, "; ".join(bad))
    bad = [p["id"] for p in decided
           if not any(h.get("report_build") for h in p.get("approval_history", []))]
    check(G, "each decision is bound to a report build", not bad, "unbound: %s" % bad, warn=True)

    check(G, "the report carries a build hash", bool(r.get("report_build")), r.get("report_build", ""))

    if os.path.exists(a.screen):
        html = open(a.screen, encoding="utf-8").read()
        for needle, label in [
            ("WHAT WE MEASURED".title(), None),
        ]:
            pass
        for sec in ["What we measured", "Why it happened", "What we propose", "Did it work",
                    "What we threw away", "What we cannot see"]:
            check(G, "screen has the section '%s'" % sec, sec in html)
        check(G, "screen never renders Detection/Diagnosis/Prescription as a heading",
              not re.search(r"'(Detection|Diagnosis|Prescription|Verification)'\)", html))
        check(G, "screen has no severity score invented out of nothing",
              "severity_score" not in html and "/100" not in html)
        check(G, "screen has no re-run-replay button",
              not re.search(r"re-?run.{0,12}replay", html, re.I))
        check(G, "screen has no chat, filters, search or date picker",
              not re.search(r"<input[^>]+type=[\"']?(search|date)", html, re.I))
        check(G, "screen states the frozen-definitions line", "frozen" in html.lower())
        check(G, "screen offers all three schema verdicts",
              all(v in html for v in VERDICTS))
        check(G, "screen never writes the word 'approved' as a verdict",
              not re.search(r"verdict[^\n]{0,20}['\"]approved['\"]", html))
        check(G, "no keyboard shortcut approves a change",
              not re.search(r"key.{0,20}===.{0,8}['\"]Enter['\"][^\n]{0,60}decision", html, re.I))
        check(G, "screen is self-contained (no external script or stylesheet)",
              not re.search(r"<(script|link)[^>]+(src|href)=[\"']https?:", html))
    else:
        check(G, "screen exists at %s" % a.screen, False)

    # ---------------- Framing ----------------
    G = "Framing"
    for rel, label in [("docs/ONE_PAGE_NOTE.md", "one-page note"),
                       ("docs/DEMO_SCRIPT.md", "demo script"),
                       ("docs/RUNBOOK.md", "run-book"),
                       ("docs/STRANGER_TEST.md", "stranger-test protocol")]:
        check(G, "%s exists" % label, os.path.exists(os.path.join(ROOT, rel)))
    note = os.path.join(ROOT, "docs/ONE_PAGE_NOTE.md")
    if os.path.exists(note):
        t = open(note, encoding="utf-8").read().lower()
        for k in ["what is real", "stubbed", "100"]:
            check(G, "note covers '%s'" % k, k in t)
    script = os.path.join(ROOT, "docs/DEMO_SCRIPT.md")
    if os.path.exists(script):
        t = open(script, encoding="utf-8").read().lower()
        check(G, "demo script schedules the refusal its own beat", "refus" in t)
        check(G, "demo script says coverage out loud twice", t.count("out loud") >= 2)
        check(G, "demo script demos a rejection before an approval", "rejection first" in t
              or "demo the rejection" in t.replace("**", ""))
        check(G, "demo script contains the seductive-wrong-answer line",
              "seductive wrong answer" in t)
        check(G, "demo script admits what was faked", "faked" in t)
        check(G, "demo script opens with no screen and no architecture",
              "no architecture" in t)

    # ---------------- report ----------------
    W = 92
    fails = [x for x in rows if x[2] == "FAIL"]
    warns = [x for x in rows if x[2] == "WARN"]
    last = None
    print("=" * W)
    print("JUDGE-PROOF CHECK   report: %s" % a.report)
    print("=" * W)
    for g, name, st, detail in rows:
        if g != last:
            print("\n-- %s" % g)
            last = g
        mark = {"PASS": "  ok  ", "FAIL": " FAIL ", "WARN": " warn "}[st]
        print("%s %-62s %s" % (mark, name, detail[:24] if st != "PASS" else ""))
    print("\n" + "=" * W)
    print("%d checks  |  %d failed  |  %d warnings" % (len(rows), len(fails), len(warns)))
    if fails:
        print("\nFAILED:")
        for g, name, _, detail in fails:
            print("   [%s] %s   %s" % (g, name, detail))
    print("\nNot checked here, and worth more than all of the above:")
    print("   - whether the prose is any good (a person has to read it)")
    print("   - whether a stranger understands the screen (docs/STRANGER_TEST.md)")
    print("   - whether the demo lands under 10:00 (rehearse it, with a stopwatch)")
    print("=" * W)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
