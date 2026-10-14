"""Incidents -> loop-report.json (schema shape), with the decision layer attached.

Honesty fields are derived, not hand-written per scenario:
  * coverage = share of sessions whose agent kind emits mechanism steps (read from catalog semantics);
  * calibration = agreement with the human labels, within one judge version;
  * gaps = catalog capabilities declared NOT_MEASURABLE / coverage-limited, matched to asks by keyword.
The ask -> metric mapping for A01/A04/A06/A09 is a planner step (interpreting operator language) and is written by
hand here; it is the one place this harness does not derive something from the data.

Decision layer (product handoff 5-7): every regression carries a decision packet (impact.py), the deployment's
standard and frozen golden set are mined (standard.py), and each regression gets a prescription framed as a decision
(prescribe.py). A definitions registry gives every number its definition. The pipeline never writes `approval`.
"""
import re

from .definitions import build_definitions, catalog_contradictions
from .impact import impact_block, packet
from .measure import compare
from .prescribe import prescribe
from .standard import mine

REPORT_VERSION = "nexus-loop/product-1"


def parse_asks(text):
    out, cur = [], None
    for line in (text or "").splitlines():
        m = re.match(r"^##\s+(A\d+)", line)
        if m:
            cur = m.group(1)
            continue
        if cur and line.startswith(">"):
            out.append((cur, line.lstrip("> ").strip()))
            cur = None
    return out


def metrics_block(C):
    cal = C["calibration"]["quality_within_version"]
    caps = {x["id"]: x for x in C["catalog"].get("capabilities", [])}
    nsk = C["no_step_kinds"]
    out = [
        {"id": "m_containment", "name": "Containment rate", "ask_id": "A01", "grain": "session",
         "fidelity": "measured",
         "coverage": {"value": 1.0, "basis": "session_end and handoff_by_design are present on every session"},
         "calibration": None,
         "plan": {"source": "corpus/sessions.jsonl.gz",
                  "filter": "session_end = 'resolved' OR (session_end = 'handoff' AND handoff_by_design = true)",
                  "denominator": "all sessions in scope", "breakdowns": ["tenant", "intent", "channel"]}},
        {"id": "m_quality", "name": "Judged quality", "ask_id": "A06", "grain": "session", "fidelity": "judged",
         "coverage": {"value": 1.0, "basis": "every session carries a judged score"},
         "calibration": {"agreement": cal["agreement"], "n": cal["n"],
                         "basis": ("labels/rubric_scores.jsonl, compared only within a matching judge_version; "
                                   "agreement means |human - judge| <= %.1f. Not 1.00: the human labels disagree "
                                   "with each other." % cal["tolerance"])},
         "plan": {"source": "corpus/sessions.jsonl.gz", "filter": "quality_score, segmented by judge_version",
                  "denominator": "sessions within one judge_version", "breakdowns": ["tenant", "intent"]}},
        {"id": "m_abandon_reason", "name": "Abandonment reason", "ask_id": "A09", "grain": "session",
         "fidelity": "judged",
         "coverage": {"value": 1.0, "basis": "abandonment is measured on every session; its reason is a judgment"},
         "calibration": None,
         "plan": {"source": "corpus/sessions.jsonl.gz JOIN corpus/turns.jsonl.gz",
                  "filter": ("session_end = 'abandoned' (measured: %d sessions); reason = judge %s over the last user "
                             "turns. Calibration not published: labels/ holds no human abandonment-reason labels, so "
                             "agreement cannot be computed and none is claimed."
                             % (int(C["S"]["M"][:, C["S"]["MI"]["s.abandoned"], 1].sum()), A09_JUDGE)),
                  "denominator": "abandoned sessions", "breakdowns": ["tenant", "intent"],
                  "alternatives_offered": ["session_end = 'abandoned' alone is MEASURED but answers how many "
                                           "gave up, not why"]}},
    ]
    for t in C["tenants"]:
        declared = (caps.get("tool_failure_rate", {}).get("coverage") or {}).get(t)
        out.append({
            "id": "m_tool_failure_" + re.sub(r"\W+", "_", t), "name": "Tool failure rate - " + t, "ask_id": "A04",
            "grain": "step", "fidelity": "measured",
            "coverage": {"value": C["coverage"][t],
                         "basis": ("share of this tenant's sessions whose agent kind emits tool_call steps; the "
                                   "catalog says %s emit none. Computed from the corpus (catalog declares %s)."
                                   % (", ".join(nsk) or "no kind", declared)),
                         "excluded": ["agent_kind in (%s)" % ", ".join(nsk)]},
            "calibration": None,
            "plan": {"source": "corpus/agent_steps.jsonl.gz WHERE step_type = 'tool_call'",
                     "filter": "outcome != 'ok' AND tenant = '%s'" % t,
                     "denominator": "tool_call steps of eligible sessions", "breakdowns": ["tool_name", "error_class"]}})
        out.append({"id": "m_silent_tool_" + re.sub(r"\W+", "_", t), "name": "Empty tool payload rate (derived) - " + t,
                    "ask_id": "A04", "grain": "step", "fidelity": "derived",
                    "coverage": {"value": C["coverage"][t],
                                 "basis": ("derived from result_field_count on outcome='ok' tool calls of this tenant; "
                                           "same coverage hole as its tool failure rate"),
                                 "excluded": ["agent_kind in (%s)" % ", ".join(nsk)]},
                    "calibration": None,
                    "plan": {"source": "corpus/agent_steps.jsonl.gz WHERE step_type = 'tool_call' AND outcome = 'ok'",
                             "filter": "result_field_count = 0 AND tenant = '%s'" % t,
                             "denominator": "outcome='ok' tool_call steps of eligible sessions",
                             "breakdowns": ["tool_name"]}})
    # every refused breakdown is attached to every metric's plan, generically from the catalog budgets
    refused = refusals(C)
    for m in out:
        m["plan"]["refused_breakdowns"] = refused
    return out


A09_JUDGE = "abandon_reason_v1"
ASK_CAPABILITY = {"A09": "abandonment_reason"}   # hand-authored planner step, same status as the metric mapping


def refusals(C):
    return ["%s: %d distinct values exceeds its cardinality budget of %d - refused, not truncated"
            % (c["field"], c["distinct"], c["budget"]) for c in C["cardinality"] if c["refused"]]


def gaps_block(C):
    asks, out = parse_asks(C["asks"]), []
    for cap in C["catalog"].get("capabilities", []):
        if str(cap.get("class", "")).lower() == "requires_new_judge":
            for aid in [a for a, c in ASK_CAPABILITY.items() if c == cap["id"]]:
                out.append({"ask_id": aid, "verdict": "REQUIRES_NEW_JUDGE",
                            "why": cap.get("note") or "",
                            "nearest_proxy": "session_end = 'abandoned' (measured)",
                            "why_the_proxy_misleads": ("it counts everyone who left, including users who got their "
                                                       "answer and simply stopped replying; the question is why"),
                            "required_event": {"name": "abandonment_reason_judgment", "grain": "session",
                                               "fields": ["session_id", "judge_version", "reason",
                                                          "confidence"],
                                               "owner": "platform team",
                                               "calibration_needs": ("human abandonment-reason labels on a sample "
                                                                     "of abandoned sessions, per judge_version")}})
            continue
        tokens = [t for t in cap["id"].split("_") if t not in ("rate", "per", "session", "reason")]
        hits = [aid for aid, text in asks if tokens and all(tok in text.lower() for tok in tokens)]
        if cap.get("class") == "NOT_MEASURABLE":
            proxy = cap.get("nearest_proxy") or ""
            head, sep, tail = proxy.partition("—")
            if not sep:
                head, sep, tail = proxy.partition(" - ")
            for aid in hits:
                out.append({"ask_id": aid, "verdict": "NOT_MEASURABLE", "why": cap.get("blocker") or "",
                            "nearest_proxy": head.strip(" ,;"), "why_the_proxy_misleads": (tail or proxy).strip(" ,;"),
                            "required_event": cap.get("required_event")})
        elif cap.get("fidelity") == "measured" and isinstance(cap.get("coverage"), dict):
            low = {t: v for t, v in cap["coverage"].items() if v < 0.9}
            for aid in hits if low else []:
                out.append({"ask_id": aid, "verdict": "COVERAGE_TOO_LOW",
                            "why": ("%s is computable only on %s. %s Reported with its denominator stated rather "
                                    "than blended." % (cap["id"], ", ".join("%.0f%% of %s" % (100 * v, t)
                                                                           for t, v in low.items()),
                                                       cap.get("coverage_basis", "")))})
    return out


def build_product(C, incidents):
    """Decision packets, standard + golden set, and prescriptions for every regression incident."""
    regs = [i for i in incidents if i["is_regression"]]
    packets = {}
    for inc in regs:
        others = [x for x in regs if x is not inc and x["tenant"] in (inc["tenant"], "*")]
        packets[inc["id"]] = packet(C, inc, others)
    entries, manifest, comparisons = mine(C, incidents)
    prescriptions = {inc["id"]: prescribe(C, inc, packets[inc["id"]], comparisons.get(inc["id"])) for inc in regs}
    return {"packets": packets, "standard": entries, "standard_manifest": manifest, "comparisons": comparisons,
            "prescriptions": prescriptions, "golden_sets": manifest["golden_sets"],
            "definitions": build_definitions(C), "contradictions": catalog_contradictions(C)}


def _r(x, d=5):
    return None if x is None else round(float(x), d)


def _fallback_impact(inc):
    return {"impact": {"conversations_affected": 0, "share_of_traffic": 0.0,
                       "derivation": "no conversation of this slice falls inside days %d-%d" % (inc["from"], inc["to"])},
            "if_nothing_changes": "No conversation in the window could be measured, so no cost of inaction is claimed."}


def system_notes(C, product):
    parts = [
        "Generic scan: one changepoint test over every metric x cohort series, overdispersion-adjusted; breadth, "
        "composition and explain-away tests; diagnosis by runtime layer.",
        "Decision layer: every regression carries exposed / hit / signed lost-resolution counts with 95% ranges, excess "
        "unplanned handoffs over a named baseline, extra time and spend, status at the end of the data, owner, severity "
        "and a plain inaction sentence; every figure is defined in `definitions`.",
        "Standard: weekly top-decile standards from measured exemplars over the reference period (flagged regression "
        "windows excluded); golden set frozen and hashed per tenant before any verification.",
        "Hand-authored: the ask-to-metric mapping and the cause-to-change-type policy.",
        "Not built: the A09 abandonment-reason judge (no human reason labels exist to calibrate one). No change is "
        "deployed by this system; approvals are recorded decisions, not rollouts.",
        "Refused breakdowns: " + ("; ".join(refusals(C)) or "none") + ".",
    ]
    if product["contradictions"]:
        parts.append("Catalog vs data: " + "; ".join(x["text"] for x in product["contradictions"]) + ".")
    return " ".join(parts)


def report(C, incidents, team="nexus-generic-scan", product=None):
    product = product or build_product(C, incidents)
    findings, diagnoses, prescriptions = [], [], []
    for k, inc in enumerate(incidents, 1):
        fid, did = "f%d" % k, "d%d" % k
        ten = inc["tenant"] if inc["tenant"] != "*" else C["tenants"][0]
        prim = inc.get("primary") or {}
        f = {"id": fid, "tenant": ten, "cohort": inc["cohort"],
             "metric": prim.get("metric") or (inc["metrics"][0] if inc["metrics"] else "n/a"),
             "window": {"from_day": max(0, inc["from"] - 2) if inc["is_regression"] else inc["from"],
                        "to_day": inc["to"]},
             "is_regression": inc["is_regression"],
             "evidence": (["applies to every tenant"] if inc["tenant"] == "*" else []) + inc["evidence"],
             "incident_id": inc["id"]}
        if inc.get("evidence_refs"):
            f["evidence_refs"] = inc["evidence_refs"]
        if inc["is_regression"]:
            p = product["packets"].get(inc["id"])
            lo, hi = (p["onset"], p["end"]) if p else (inc["from"], inc["to"])
            if prim:
                cmp = compare(C, prim["metric"], inc["tenant"], prim["dim"], prim["value"], lo, hi, prim.get("mode", "self"))
                if cmp["current"] is not None:
                    f["observed"] = _r(cmp["current"])
                if cmp["baseline"] is not None:
                    f["expected"] = _r(cmp["baseline"])
                f["observed_basis"] = ("%s on %s over days %d-%d; expected = the value for %s on days %d-%d"
                                       % (prim["metric"], "%s=%s" % (prim["dim"], prim["value"]), lo, hi,
                                          cmp["baseline_kind"], cmp["baseline_days"][0], cmp["baseline_days"][1]))
            if p:
                f["severity"] = p["severity"]
                f["impact"], f["if_nothing_changes"] = impact_block(p), p["if_nothing_changes"]
                f["audience"], f["audience_why"] = p["audience"], p["audience_why"]
            else:
                fb = _fallback_impact(inc)
                f["severity"], f["impact"], f["if_nothing_changes"] = "low", fb["impact"], fb["if_nothing_changes"]
                f["audience"] = inc.get("audience", ["agent_builder"])
        else:
            f["severity"] = "low"
            f["not_a_regression_because"] = inc.get("not_a_regression_because", "")
        findings.append(f)
        att = inc.get("attributed_change")
        diag = {"id": did, "finding_id": fid, "cause_class": inc["cause_class"],
                "confidence": inc.get("confidence", 0.5),
                "attributed_change": {"kind": att["kind"], "day": att["day"]} if att else None,
                "evidence": (inc.get("diagnosis_notes") or []) + inc["evidence"][:3]
                + (["attributed via %s: %s %s -> %s" % (att["source"], att.get("target"), att.get("from"),
                                                      att.get("to"))] if att else [])}
        if att:
            from .prescribe import config_note
            diag["attribution_detail"] = {"kind": att["kind"], "day": att["day"], "target": att.get("target"),
                                          "from": att.get("from"), "to": att.get("to"), "source": att.get("source"),
                                          "note": config_note(C, att)}
        diagnoses.append(diag)
        rx = product["prescriptions"].get(inc["id"]) if inc["is_regression"] else None
        if rx:
            prescriptions.append(dict({"id": "p%d" % k, "diagnosis_id": did}, **rx))
            # no "approval" key: it is written only by the approval gate, with verdict, decided_by, reason, at
    return {"team": team, "corpus": C["catalog"].get("corpus_variant", "?"), "report_version": REPORT_VERSION,
            "system_notes": system_notes(C, product),
            "metrics": metrics_block(C), "standard": product["standard"], "findings": findings, "diagnoses": diagnoses,
            "prescriptions": prescriptions, "verifications": [], "gaps": gaps_block(C),
            "self_assessment": {"cycles": 0, "prescription_accuracy": {}},
            "standard_manifest": product["standard_manifest"], "definitions": product["definitions"],
            "data_contradictions": product["contradictions"],
            "asks": [{"ask_id": a, "text": t} for a, t in parse_asks(C["asks"])],
            "tenants": C["tenants"], "days": C["days"]}


def incidents_json(incidents):
    return {"incidents": [{"id": i["id"], "tenant": i["tenant"], "cohort": i["cohort"],
                           "from_day": max(0, i["from"] - 2) if i["is_regression"] else i["from"],
                           "to_day": i["to"], "is_regression": i["is_regression"], "cause_class": i["cause_class"],
                           "metrics": i["metrics"], "kind": i["kind"]} for i in incidents]}
