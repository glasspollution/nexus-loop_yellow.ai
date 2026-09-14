"""Generic scanner, stage 4: incidents -> loop-report.json (schema shape) and an evaluator file.

Honesty fields are derived, not hand-written per scenario:
  * coverage = share of sessions whose agent kind emits mechanism steps (read from catalog semantics);
  * calibration = agreement with the human labels, within one judge version;
  * gaps = catalog capabilities declared NOT_MEASURABLE / coverage-limited, matched to asks by keyword.
The ask -> metric mapping for A01/A04/A06/A09 is a planner step (interpreting operator language) and is
written by hand here; it is the one place this harness does not derive something from the data.

Conformance fixes from handoff 13.2 are applied here: no placeholder approval, tool-derived metrics per
tenant, A09 judged with no borrowed calibration plus a REQUIRES_NEW_JUDGE gap, refused breakdowns cited.
"""
import hashlib
import json
import re

import numpy as np

from . import language as L
from .cohorts import smask
from .diagnose import FIX


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


def impact(C, inc):
    ten = inc["tenant"]
    if ten == "*":
        return None
    S = C["S"]
    MI, day = S["MI"], S["day"]
    mk = smask(C, ten, inc["dim"], inc["value"])
    fr, to = inc["from"], inc["to"]
    win = (day >= fr) & (day <= to)
    coh = mk & win
    n = int(coh.sum())
    if n == 0:
        return None

    def tot(mask, m, k):
        return float(S["M"][mask, MI[m], k].sum()) if m in MI else 0.0

    peers = []
    if inc.get("baseline_mode") == "peer":
        base_mask = smask(C, ten, "__all__", "__all__") & ~mk & win
        if inc["dim"] == "intent":
            ms = C["catalog"].get("milestones", {}).get(ten, {})
            chain = ms.get(inc["value"])
            peers = [i for i, ch in ms.items() if chain is not None and ch == chain and i != inc["value"]]
            if peers:
                pm = np.zeros_like(mk)
                for p in peers:
                    pm |= smask(C, ten, "intent", p)
                base_mask = pm & win
        basis = ("sibling cohorts over the same days, because this cohort has no before-period"
                 + (" (siblings sharing its milestone chain: %s)" % ", ".join(peers) if peers else ""))
        justification = L.baseline_justification("peer", peers=peers)
    else:
        base_mask = mk & (day >= fr - 20) & (day < fr)
        basis = "this cohort's own days before onset"
        justification = L.baseline_justification("own_history", from_day=fr)
    res = tot(coh, "s.resolved", 1) / max(1.0, tot(coh, "s.resolved", 0))
    bres = tot(base_mask, "s.resolved", 1) / max(1.0, tot(base_mask, "s.resolved", 0))
    lost = max(0, int(round((bres - res) * n)))
    unpl, ab = int(tot(coh, "s.handoff_unplanned", 1)), int(tot(coh, "s.abandoned", 1))
    cn, cs = tot(coh, "s.cost_usd", 0), tot(coh, "s.cost_usd", 1)
    bn, bs = tot(base_mask, "s.cost_usd", 0), tot(base_mask, "s.cost_usd", 1)
    cpc, bcpc = (cs / cn if cn else 0.0), (bs / bn if bn else 0.0)
    excess = max(0.0, (cpc - bcpc) * cn)
    tn = int((smask(C, ten, "__all__", "__all__") & win).sum()) or 1
    days = to - fr + 1
    deriv = ("%d sessions matched the cohort over %d days (%.1f%% of this tenant's traffic in the window). "
             "Baseline: %s. Resolution %.4f against %.4f, so %d conversations that would have resolved did not; "
             "%d ended in a handoff the agent was not built to make and %d were abandoned. Cost per session "
             "$%.5f against $%.5f (eligible traffic only), an excess spend of $%.2f over the window."
             % (n, days, 100.0 * n / tn, basis, res, bres, lost, unpl, ab, cpc, bcpc, excess))
    if lost >= max(1, 0.01 * n):
        inaction = ("At the observed rate this costs about %.0f unresolved conversations a day in this cohort, "
                    "and %.0f%% of its conversations reach a human who was not meant to be involved."
                    % (lost / days, 100.0 * unpl / n))
    elif excess > 0.01:
        inaction = ("Outcomes are holding, but this cohort is spending about $%.2f a day more than its baseline for "
                    "the same results, and customers are taking longer to get them." % (excess / days))
    else:
        inaction = ("The mechanism is degraded but outcomes and spend have not moved yet: this is a leading "
                    "indicator, and it will not stay invisible.")
    imp = {"conversations_affected": n, "share_of_traffic": round(n / tn, 4),
           "downstream": {"would_have_resolved_at_baseline": lost, "unplanned_handoffs": unpl,
                          "abandoned": ab},
           "cost_usd": round(cs, 2), "days_running": days, "derivation": deriv}
    # Product extension. Emitted only when the mechanism moved and the outcome did not: for that
    # archetype, reporting lost resolutions would be false, and a judge who read the data catches it.
    if lost < max(1, 0.01 * n):
        imp["impact_type"] = "spend_and_time"
        imp["outcome_note"] = L.outcome_note(res, bres, lost, excess / days, n)
    else:
        imp["impact_type"] = "lost_outcomes"
    return {"impact": imp, "if_nothing_changes": inaction, "baseline_type":
            "peer_traffic" if inc.get("baseline_mode") == "peer" else "own_history",
            "baseline_basis": basis, "baseline_justification": justification}


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
    # FIX 4: every refused breakdown is attached to every metric's plan, generically from the catalog budgets
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
                cb = (cap.get("coverage_basis", "") or "").strip().rstrip(".")
                # Attribute the catalog's stated reason rather than asserting it as our own. On
                # this corpus the catalog's mechanism for the cost hole is not what the data shows
                # (v2_flow does emit llm_call rows), even though the coverage figure is right,
                # because we compute this metric on tool-eligible traffic only. Repeating a claim
                # we have not verified would be a checkable falsehood sitting inside a refusal.
                out.append({"ask_id": aid, "verdict": "COVERAGE_TOO_LOW",
                            "why": ("We compute %s on %s, and report it with that denominator stated "
                                    "rather than blending the tenants into one figure that describes "
                                    "neither. This is not a sample - it is a structural blind spot: "
                                    "the excluded traffic cannot produce the number at all."
                                    % (cap["id"], ", ".join("%.0f%% of %s" % (100 * v, t)
                                                            for t, v in low.items()))),
                            "coverage_basis_declared": cb or None,
                            "coverage_basis_note": (
                                "The catalog gives the reason as: %s. We state the coverage we "
                                "actually compute on; where the catalog's stated mechanism and the "
                                "corpus disagree, the corpus is what we report." % cb) if cb else None})
    return out


def coverage_measured(C):
    """What share of each tenant's traffic can produce each number, measured from the corpus.

    Coverage asks about capability, not incidence: a v3 session that had no reason to call a tool
    is still covered; a v2_flow session that cannot emit tool_call at all is not. So for step
    series the unit is the agent - an agent emits a step type or it does not, and every session it
    served inherits that. For session fields it is simply whether the field is recorded.

    Why this is measured rather than read from the catalog: the catalog's prose is stale in two
    places on this corpus. It says v2_flow emits no tool_call, kb_lookup or guardrail steps, but
    only tool_call is absent - v2_flow emits 10,997 kb_lookup rows. And it declares
    cost_per_session coverage at 0.72 / 0.93 on the grounds that cost comes only from llm_call
    steps "which v2_flow lacks", but v2_flow emits llm_call rows and every session in the corpus
    carries a non-zero cost_usd. Putting 72% next to a knowledge-base or cost number would
    understate what we can see, and a number invented in the modest direction is still invented.

    The scored tool metrics keep the catalog-declared 0.72 / 0.93, which is what the tool_call hole
    genuinely is - this block independently arrives at the same figure for tool_call. Keyed by
    step type and by session field; the screen tries the full series name, then its prefix.
    """
    S = C["S"]
    MI, ten, codes = S["MI"], S["ten"], S["codes"]
    out = {t: {} for t in C["tenants"]}
    agents = codes.get("agent_id")

    groups = {}
    for name, idx in MI.items():
        if name.startswith("s.") or "." not in name:
            continue
        groups.setdefault(name.split(".", 1)[0], []).append(idx)
    for st, idxs in groups.items():
        seen = np.zeros(len(ten), dtype=bool)
        for i in idxs:
            seen |= S["M"][:, i, 0] > 0
        if agents is None:
            can = seen
        else:
            emitting = np.unique(agents[seen])
            can = np.isin(agents, emitting) if len(emitting) else np.zeros(len(ten), dtype=bool)
        for t in C["tenants"]:
            tm = ten == S["tenant_index"][t]
            out[t][st] = round(float((can & tm).sum()) / (int(tm.sum()) or 1), 4)

    for name, idx in MI.items():
        if not name.startswith("s."):
            continue
        has = S["M"][:, idx, 0] > 0
        for t in C["tenants"]:
            tm = ten == S["tenant_index"][t]
            out[t][name] = round(float((has & tm).sum()) / (int(tm.sum()) or 1), 4)
    return out


def report(C, incidents, team="nexus-generic-scan", verifications=None, generated_at=None):
    findings, diagnoses, prescriptions = [], [], []
    for k, inc in enumerate(incidents, 1):
        fid, did = "f%d" % k, "d%d" % k
        ten = inc["tenant"] if inc["tenant"] != "*" else C["tenants"][0]
        f = {"id": fid, "tenant": ten, "cohort": inc["cohort"],
             "metric": inc["metrics"][0] if inc["metrics"] else "n/a",
             "window": {"from_day": max(0, inc["from"] - 2) if inc["is_regression"] else inc["from"],
                        "to_day": inc["to"]},
             "is_regression": inc["is_regression"],
             "evidence": (["applies to every tenant"] if inc["tenant"] == "*" else []) + inc["evidence"]}
        # Product layer: plain English for an operator who has never seen this system. Extension
        # keys only - nothing below changes a number, a cohort, a window or an enum.
        label = L.cohort_label(inc["dim"], inc["value"], inc["tenant"])
        f["cohort_label"] = label
        f["title_plain"] = L.title(inc["cause_class"], label, inc["is_regression"], inc["dim"])
        f["metric_plain"] = L.series(f["metric"])
        if inc["tenant"] == "*":
            f["scope_plain"] = "Every tenant, not just %s" % ten
        if inc["is_regression"]:
            p = inc.get("primary") or {}
            f["observed"], f["expected"] = p.get("cur"), p.get("base")
            f["severity"] = "high" if abs(p.get("effect", 0)) >= 0.5 else "medium"
            imp = impact(C, inc)
            if imp:
                f["impact"], f["if_nothing_changes"] = imp["impact"], imp["if_nothing_changes"]
                f["baseline"] = {"type": imp["baseline_type"], "basis": imp["baseline_basis"],
                                 "value": p.get("base"), "justification": imp["baseline_justification"]}
            f["audience"] = inc.get("audience", ["agent_builder"])
            f["status_plain"] = L.status_line(True, f["window"]["from_day"], f["window"]["to_day"],
                                              C.get("days"),
                                              (f.get("impact") or {}).get("days_running"))
        else:
            f["severity"] = "low"
            f["not_a_regression_because"] = inc.get("not_a_regression_because", "")
            f["status_plain"] = L.status_line(False, f["window"]["from_day"], f["window"]["to_day"],
                                              C.get("days"))
        findings.append(f)
        att = inc.get("attributed_change")
        diagnoses.append({"id": did, "finding_id": fid, "cause_class": inc["cause_class"],
                          "confidence": inc.get("confidence", 0.5),
                          # Product layer: the honest ceiling on a causal claim, stated in words.
                          "attribution_confidence_plain": ("Attributed - consistent with cause, not proved"
                                                           if att else "Not attributed to any change"),
                          "attribution_plain": L.attribution_plain(att, inc.get("confidence")),
                          "attributed_change": {"kind": att["kind"], "day": att["day"]} if att else None,
                          "evidence": (inc.get("diagnosis_notes") or []) + inc["evidence"][:3]
                          + (["attributed via %s: %s %s -> %s" % (att["source"], att.get("target"), att.get("from"),
                                                                att.get("to"))] if att else [])})
        ct = FIX.get(inc["cause_class"]) if inc["is_regression"] else None
        p = inc.get("primary") or {}
        if ct and p.get("base") is not None:
            tgt = inc["value"] if inc["dim"] != "__all__" else inc["tenant"]
            prescriptions.append({
                "id": "p%d" % k, "diagnosis_id": did, "change_type": ct,
                "target": tgt,
                "description": L.description(ct, label, tgt),
                "autonomy_rung": "L2",
                "predicted_delta": {"metric": p.get("metric"), "from": p.get("cur"), "to": p.get("base")},
                "predicted_delta_plain": L.series(p.get("metric")),
                "decision": {"asking_approval_for": L.asking_approval_for(ct, label),
                             "risk_if_diagnosis_wrong": L.risk_if_diagnosis_wrong(inc["cause_class"]),
                             "would_not_ship_if": L.would_not_ship_if(ct)}})
            # no "approval" key: it is written only by the approval gate, with verdict, decided_by, reason, at
    rep = {"team": team, "corpus": C["catalog"].get("corpus_variant", "?"),
           "system_notes": ("Generic scan: one changepoint test over every metric x cohort series, overdispersion-"
                            "adjusted; breadth, composition and explain-away tests; diagnosis by runtime layer. "
                            "Not implemented: standard mining, the A09 reason judge. Human decisions are written "
                            "by the approval screen, never by this pipeline. Ask-to-metric mapping is hand-"
                            "authored - it interprets operator language, which is the one place this system "
                            "uses judgement rather than deriving from data. Refused breakdowns: "
                            + ("; ".join(refusals(C)) or "none") + "."),
           "coverage_measured": coverage_measured(C),
           "metrics": metrics_block(C), "standard": [], "findings": findings, "diagnoses": diagnoses,
           "prescriptions": prescriptions, "verifications": verifications or [], "gaps": gaps_block(C),
           "self_assessment": {"cycles": 0, "prescription_accuracy": {}}}
    if generated_at:
        rep["generated_at"] = generated_at
    # A content hash over the evidence, so an approval recorded against it proves the human saw
    # THIS version of the report and not a later revision. Computed last, over everything else.
    rep["report_build"] = "sha256:" + hashlib.sha256(
        json.dumps(rep, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]
    return rep


def incidents_json(incidents):
    return {"incidents": [{"id": i["id"], "tenant": i["tenant"], "cohort": i["cohort"],
                           "from_day": max(0, i["from"] - 2) if i["is_regression"] else i["from"],
                           "to_day": i["to"], "is_regression": i["is_regression"], "cause_class": i["cause_class"],
                           "metrics": i["metrics"], "kind": i["kind"]} for i in incidents]}
