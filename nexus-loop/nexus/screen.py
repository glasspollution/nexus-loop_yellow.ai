"""The screen's data contract: screen.json, built only from loop-report.json.

The website renders this file and never computes a number itself. Every figure it shows arrives with its label,
unit, definition, fidelity and coverage resolved from the report's `definitions` registry, every simulated value is
flagged, and the approval state of each fix reflects what was actually written back into the report.

Reading order follows what the problem statement asks a stranger to be able to do: read a finding and its impact,
see the evidence, see what was dismissed and refused, read the proposed fix with its risk and its replay proof, and
approve or reject it.
"""
import datetime
import hashlib
import json
import os

from .decisions import proposal_sha

SCREEN_VERSION = "nexus-loop-screen/1"
SCREEN_FILE = "screen.json"

LABELS = {
    "cause_class": {"kb.gap": "Missing knowledge-base content", "tool.contract_break": "Tool returns empty answers",
                    "tool.outage": "Tool failing", "prompt.regression": "Prompt change made conversations longer",
                    "model.change": "Model change", "routing.error": "Routing sends people to humans",
                    "traffic_mix": "Traffic mix changed", "load": "Traffic surge", "judge_change": "Scoring rubric changed",
                    "unknown": "Cause not identified"},
    "audience": {"agent_builder": "Agent builder", "business_owner": "Business owner", "platform_owner": "Platform team"},
    "severity": {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"},
    "status": {"ongoing": "Still happening", "ended": "Stopped", "persisting": "Persisting after the window",
               "unknown": "Status unknown"},
    "verdict": {"accepted": "Approved", "rejected": "Rejected", "deferred": "Deferred", "pending": "Awaiting a decision"},
    "replay_verdict": {"improved": "Improved in replay", "no_effect": "No effect in replay", "regressed": "Regressed in replay"},
    "gate": {"candidate": "Replay supports shipping", "blocked_golden_set": "Blocked: golden conversations broke",
             "candidate_unguarded": "Improved, but no golden set was checked",
             "not_supported_by_replay": "Replay does not support it", "unverified": "Not verified"},
    "gap_verdict": {"NOT_MEASURABLE": "Cannot be measured", "REQUIRES_NEW_JUDGE": "Needs a new, calibrated judge",
                    "COVERAGE_TOO_LOW": "Coverage too low", "CARDINALITY_REFUSED": "Breakdown refused"},
    "fidelity": {"measured": "Measured from logs", "judged": "Judged by a model", "derived": "Derived from other numbers"},
    "change_type": {"kb.add": "Add knowledge-base content", "kb.synonym": "Map phrasings to existing content",
                    "prompt.edit": "Edit the prompt", "tool.validate": "Validate tool responses",
                    "tool.fallback": "Use the fallback path", "routing.change": "Change routing", "revert": "Roll back",
                    "no_action": "Make no change"},
    "kind": {"load": "Traffic surge", "mix_shift": "Traffic mix shift", "composition": "Composition change",
             "instrument_boundary": "Measurement boundary", "launch": "New slice launched",
             "volume_spike": "Volume spike", "volume_drop": "Volume drop", "coverage_gap": "Logging gap",
             "unlocalized": "Aggregate shift with no locus"},
}

DISCLOSURES = {
    "real": ["Detection, localisation, diagnosis and attribution are computed from the logs.",
             "Every impact figure, baseline, standard and golden set is computed from the corpus.",
             "Coverage, calibration and refusals are derived from the catalog and the data.",
             "Human decisions and their live replay results exist only in this server session."],
    "hand_authored": ["Which operator ask maps to which metric.", "Which change type answers which diagnosed cause.",
                      "The wording templates of decisions and sentences (every number in them is computed)."],
    "simulated": ["Every replay before/after, verdict, golden-set result and 'sessions replayed' comes from the "
                  "organisers' replay simulator; no conversation is re-run.",
                  "Prediction errors and hit rates are measured against that simulator, not real deployments."],
    "stubbed": ["An approval applies the proposal only inside the replay engine; no production change is deployed.",
                "No real knowledge-base article, prompt text or tool patch exists; proposals describe the change.",
                "The A09 abandonment-reason judge is not built: the kit has no human reason labels to calibrate one.",
                "decided_by is a typed name, not an authenticated identity."],
}


def _defs(report):
    return {d["id"]: d for d in report.get("definitions", [])}


def _resolve(fig, defs):
    d = defs.get(fig.get("def")) or {}
    out = dict(fig)
    out.update({"label": d.get("label"), "unit": d.get("unit"), "definition": d.get("definition"),
                "fidelity": d.get("fidelity")})
    ref = defs.get(fig.get("definition_ref"))
    if ref:
        out["metric_definition"] = {k: ref.get(k) for k in ("label", "definition", "unit", "fidelity", "coverage",
                                                            "calibration")}
    return out


def _slice_label(cohort):
    return "all traffic" if not cohort else ", ".join("%s = %s" % kv for kv in cohort.items())


def _fig(impact, def_id):
    return next((f for f in impact.get("figures", []) if f.get("def") == def_id), {})


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _verification(v, defs):
    """Add display-ready replay values without replacing the simulator's raw fields."""
    out = dict(v, verdict_label=LABELS["replay_verdict"].get(v.get("verdict")),
               gate_label=LABELS["gate"].get(v.get("gate")), simulated=True,
               definition=defs.get("replay.before_after"))
    metric = v.get("metric")
    before, after = v.get("before"), v.get("after")
    delta = v.get("observed_delta")
    if not _number(delta) and _number(before) and _number(after):
        delta = after - before
    if metric == "resolution_rate":
        out["metric_label"] = "Resolution rate"
        if _number(before):
            out["before_display"] = "%.1f%%" % (100 * before)
        if _number(after):
            out["after_display"] = "%.1f%%" % (100 * after)
        if _number(delta):
            out["observed_delta_display"] = "%+.1f pp" % (100 * delta)
    elif metric == "median_turns":
        out["metric_label"] = "Median turns"
        if _number(before):
            out["before_display"] = "%.2f turns" % before
        if _number(after):
            out["after_display"] = "%.2f turns" % after
        if _number(delta):
            out["observed_delta_display"] = "%+.2f turns" % delta
    return out


def _headline(f):
    imp = f.get("impact") or {}
    ds = imp.get("downstream") or {}
    hit = _fig(imp, "impact.hit")
    base = (imp.get("baseline") or {}).get("label", "its baseline")
    parts = ["%s conversations in %s over %s days (%s of the tenant's traffic)" % (
        "{:,}".format(imp.get("conversations_affected", 0)), _slice_label(f["cohort"]), imp.get("days_running", "?"),
        _fig(imp, "impact.share").get("display", "?"))]
    if hit:
        parts.append("%s of them %s" % (hit.get("display"), hit.get("predicate")))
    if imp.get("harm") == "behaviour":
        parts.append("against %s they took %s extra turns and %s extra customer-minutes and cost %s more, while "
                     "resolution did not measurably change" % (base, _fig(imp, "impact.extra_turns").get("display"),
                                                                _fig(imp, "impact.extra_minutes").get("display"),
                                                                _fig(imp, "impact.cost_excess").get("display")))
    else:
        parts.append("against %s, %s fewer resolved and %s more reached a human who was not meant to be involved"
                     % (base, "{:,}".format(ds.get("would_have_resolved_at_baseline", 0)),
                        "{:,}".format(ds.get("unplanned_handoffs", 0))))
    return "; ".join(parts) + "."


def build(report, report_sha=None, generated_sha=None, proposal_fingerprint=proposal_sha,
          source_report="loop-report.json", source_mode="batch-artifact"):
    defs = _defs(report)
    diag_by_f = {d["finding_id"]: d for d in report.get("diagnoses", [])}
    rx_by_d = {p["diagnosis_id"]: p for p in report.get("prescriptions", [])}
    ver_by_p = {v["prescription_id"]: v for v in report.get("verifications", [])}
    std_by_cohort = {}
    for s in report.get("standard", []):
        std_by_cohort.setdefault((s.get("tenant"), json.dumps(s.get("cohort"), sort_keys=True)), []).append(s)
    unverified = {}
    for u in (report.get("self_assessment") or {}).get("unverified", []):
        pid, _, why = u.partition(" not verified: ")
        unverified[pid] = why or u

    cards, dismissed = [], []
    for f in report.get("findings", []):
        d = diag_by_f.get(f["id"], {})
        if not f.get("is_regression"):
            dismissed.append({"finding_id": f["id"], "tenant": f["tenant"], "slice": _slice_label(f["cohort"]),
                              "window": f["window"], "cause_class": d.get("cause_class"),
                              "label": LABELS["cause_class"].get(d.get("cause_class"), d.get("cause_class")),
                              "why_not_a_problem": f.get("not_a_regression_because"), "evidence": f.get("evidence", [])})
            continue
        p = rx_by_d.get(d.get("id"))
        imp = f.get("impact") or {}
        card = {"finding_id": f["id"], "diagnosis_id": d.get("id"), "tenant": f["tenant"], "cohort": f["cohort"],
                "slice": _slice_label(f["cohort"]), "window": f["window"], "severity": f.get("severity"),
                "severity_label": LABELS["severity"].get(f.get("severity")),
                "title": "%s: %s" % (LABELS["cause_class"].get(d.get("cause_class"), d.get("cause_class")),
                                     _slice_label(f["cohort"])),
                "headline": _headline(f),
                "status": dict(imp.get("status") or {}, label=LABELS["status"].get((imp.get("status") or {}).get("state"))),
                "impact": {"figures": [_resolve(x, defs) for x in imp.get("figures", [])],
                           "derivation": imp.get("derivation"), "windows": imp.get("windows"),
                           "projection": imp.get("projection"), "harm": imp.get("harm")},
                "baseline": imp.get("baseline"),
                "who_acts": [{"key": a, "label": LABELS["audience"].get(a, a)} for a in f.get("audience", [])],
                "who_acts_why": f.get("audience_why"), "if_nothing_changes": f.get("if_nothing_changes"),
                "observed": {"metric": f.get("metric"), "value": f.get("observed"), "expected": f.get("expected"),
                             "basis": f.get("observed_basis"), "definition": defs.get("metric:" + str(f.get("metric")))},
                "evidence": f.get("evidence_refs") or [{"line": x} for x in f.get("evidence", [])],
                "diagnosis": {"cause_class": d.get("cause_class"),
                              "label": LABELS["cause_class"].get(d.get("cause_class")),
                              "confidence": d.get("confidence"), "config_change": d.get("attribution_detail"),
                              "evidence": d.get("evidence", [])},
                "standard": std_by_cohort.get((f["tenant"], json.dumps(f["cohort"], sort_keys=True)), []),
                "proposal": None, "verification": None, "approval": {"state": "pending",
                                                                     "label": LABELS["verdict"]["pending"]}}
        if p:
            card["proposal"] = {"prescription_id": p["id"], "fix_id": p.get("fix_id"),
                                "proposal_sha": proposal_fingerprint(report, p),
                                "change_type": p["change_type"], "label": LABELS["change_type"].get(p["change_type"]),
                                "target": p.get("target"), "description": p.get("description"),
                                "autonomy_rung": p.get("autonomy_rung"), "owner": p.get("owner"),
                                "decision": p.get("decision"), "alternatives": p.get("alternatives", []),
                                "predicted_delta": p.get("predicted_delta"), "replay_prediction": p.get("replay_prediction"),
                                "mechanism_prediction": p.get("mechanism_prediction"),
                                "standard_gap": p.get("standard_gap", []),
                                "user_first_messages": p.get("user_first_messages", [])}
            v = ver_by_p.get(p["id"])
            if v:
                card["verification"] = _verification(v, defs)
            if p.get("approval"):
                a = p["approval"]
                card["approval"] = dict(a, state=a["verdict"], label=LABELS["verdict"].get(a["verdict"]),
                                        meta=p.get("approval_meta"))
                if a["verdict"] == "accepted" and not v:
                    card["verification"] = {"gate": "unverified", "gate_label": "Replay unavailable",
                                            "reason": unverified.get(p["id"], "the live replay returned no result")}
        cards.append(card)

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    cards.sort(key=lambda c: (order.get(c["severity"], 9), c["status"].get("state") == "ended"))
    gaps = [dict(g, label=LABELS["gap_verdict"].get(g.get("verdict"))) for g in report.get("gaps", [])]
    refused = (report.get("metrics") or [{}])[0].get("plan", {}).get("refused_breakdowns", [])
    metrics = [{"id": m["id"], "name": m.get("name"), "ask_id": m.get("ask_id"), "fidelity": m.get("fidelity"),
                "fidelity_label": LABELS["fidelity"].get(m.get("fidelity")), "coverage": m.get("coverage"),
                "calibration": m.get("calibration"), "plan": m.get("plan")} for m in report.get("metrics", [])]
    answered = {m["ask_id"] for m in report.get("metrics", [])}
    refused_asks = {g["ask_id"]: g for g in report.get("gaps", [])}
    asks = [{"ask_id": a["ask_id"], "text": a["text"],
             "answer": ("refused" if a["ask_id"] in refused_asks and refused_asks[a["ask_id"]]["verdict"] in
                        ("NOT_MEASURABLE", "REQUIRES_NEW_JUDGE") else "answered with a stated coverage limit"
                        if a["ask_id"] in refused_asks else "answered" if a["ask_id"] in answered else "not addressed"),
             "metrics": [m["id"] for m in report.get("metrics", []) if m["ask_id"] == a["ask_id"]],
             "gap": refused_asks.get(a["ask_id"])} for a in report.get("asks", [])]
    log = report.get("decision_log") or {}
    pending = sum(1 for c in cards if c["proposal"] and c["approval"]["state"] == "pending")
    return {
        "screen_version": SCREEN_VERSION,
        "built_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"mode": source_mode, "report": source_report, "report_sha256": report_sha,
                   "generated_report_sha256": generated_sha or log.get("generated_report_sha256"),
                   "analysis_sha256": log.get("analysis_sha256"),
                   "session_revision": log.get("session_revision"), "report_version": report.get("report_version")},
        "header": {"team": report.get("team"), "corpus": report.get("corpus"), "tenants": report.get("tenants"),
                   "days": report.get("days")},
        "summary": {"regressions": len(cards), "dismissed": len(dismissed),
                    "refused_questions": sum(1 for g in gaps if g["verdict"] in ("NOT_MEASURABLE", "REQUIRES_NEW_JUDGE")),
                    "decisions_pending": pending, "decisions_recorded": len(log.get("applied", [])),
                    "needs_reconfirmation": log.get("needs_reconfirmation", [])},
        "findings": cards, "dismissed": dismissed,
        "refusals": {"questions": gaps, "breakdowns": refused, "catalog_contradictions": report.get("data_contradictions", [])},
        "metrics": metrics, "asks": asks,
        "standard": {"entries": report.get("standard", []),
                     "manifest": {k: v for k, v in (report.get("standard_manifest") or {}).items() if k != "golden_sets"},
                     "golden_sets": report.get("standard_manifest", {}).get("golden_sets", {})},
        "self_assessment": report.get("self_assessment"),
        "disclosures": DISCLOSURES, "labels": LABELS, "definitions": defs,
        "system_notes": report.get("system_notes"),
    }


def write(out_dir, report=None):
    path = os.path.join(out_dir, "loop-report.json")
    if report is None:
        with open(path, encoding="utf-8") as fh:
            report = json.load(fh)
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.exists(path) else None
    screen = build(report, sha)
    tmp = os.path.join(out_dir, SCREEN_FILE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(screen, fh, indent=1)
    os.replace(tmp, os.path.join(out_dir, SCREEN_FILE))
    return screen
