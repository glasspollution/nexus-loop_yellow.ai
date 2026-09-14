"""Stage 4: diagnosis and attribution (handoff section 9).

Layer first: the runtime layer (catalog step_type) whose metrics moved most names the cause class. Only when no
mechanism layer moved are cohort-scoped config rows and discovered version flips used as the cause itself.
Attribution then points at the config row, or the version flip, consistent with that cause.

The weaknesses measured on the benchmark test split (handoff 9.3) are deliberately left as they are.
"""
from collections import defaultdict

import numpy as np

from .cohorts import smask

OUTCOME = {"s.resolved", "s.abandoned", "s.handoff_unplanned", "s.milestones_complete", "s.milestone_ratio"}
BEHAVIOUR = {"s.turns", "s.duration_s", "s.cost_usd"}
FIX = {"kb.gap": "kb.add", "tool.contract_break": "tool.validate", "tool.outage": "tool.fallback",
       "prompt.regression": "prompt.edit", "model.change": "revert", "routing.error": "routing.change"}
CAUSE_WORDS = (("prompt", "prompt.regression"), ("model", "model.change"), ("routing", "routing.error"),
               ("kb", "kb.gap"), ("tool", "tool.outage"))
LAYER_ALIAS = {"s.tool_error_any": "tool_call", "s.guardrail_any": "guardrail"}


def layer(metric):
    if metric in LAYER_ALIAS:
        return LAYER_ALIAS[metric]
    return "session" if metric.startswith("s.") else metric.split(".")[0]


def cause_from_word(word):
    w = (word or "").lower()
    for key, cause in CAUSE_WORDS:
        if key in w:
            return cause
    return None


def consistent(word, cause):
    c2 = cause_from_word(word)
    return bool(c2 and cause and cause != "unknown" and c2.split(".")[0] == cause.split(".")[0])


def diagnose(C, eps, primary, c):
    ten = primary["tenant"]
    metrics = {e["metric"] for e in eps}
    same = [e for e in eps if (e["dim"], e["value"]) == (primary["dim"], primary["value"])]
    onset = min(e["from"] for e in (same or eps))
    by_layer = defaultdict(float)
    for e in eps:
        by_layer[layer(e["metric"])] = max(by_layer[layer(e["metric"])], e["stat"])
    mech = {L: s for L, s in by_layer.items() if L != "session"}
    S, notes = C["S"], []

    touched = {e["value"] for e in eps if e["dim"] != "__all__"}
    agents = set()
    if ten != "*" and "agent_id" in S["codes"]:
        ac = S["codes"]["agent_id"][smask(C, ten, primary["dim"], primary["value"])]
        ac = ac[ac >= 0]
        if len(ac):
            cnt = np.bincount(ac, minlength=len(S["vocab"]["agent_id"]))
            agents = {S["vocab"]["agent_id"][k] for k, n in enumerate(cnt) if n >= 0.3 * len(ac)}
    targets = touched | agents
    rows = []
    for r in C["config"]:
        if ten != "*" and r.get("tenant") not in (ten, "*"):
            continue
        try:
            d = int(r["day"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (onset - 4 <= d <= onset + 1):
            continue
        tgt = r.get("target")
        scope = 2 if tgt in targets else (1 if tgt in (r.get("kind"), "*", ten) else 0)
        if scope:
            rows.append((scope, -abs(d - onset), r))
    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    flips = [f for f in C["flips"] if f["tenant"] == ten and f["agent_id"] in agents
             and onset - 3 <= f["day"] <= onset + 1]

    if mech:
        top = max(mech, key=mech.get)
        tool_m = {e["metric"] for e in eps if layer(e["metric"]) == "tool_call"}
        if top == "tool_call":
            if tool_m & {"tool_call.fail", "tool_call.timeout", "s.tool_error_any"}:
                cause = "tool.outage"
            elif tool_m & {"tool_call.empty", "tool_call.retry"}:
                cause = "tool.contract_break"
            else:
                cause = "unknown"
                notes.append("tool latency degraded without errors or empty payloads")
        elif top == "kb_lookup":
            cause = "kb.gap"
        elif top == "llm_call":
            cause = "model.change"
        elif top == "guardrail":
            cause = "unknown"
            notes.append("the guardrail layer is blocking more often; the schema has no guardrail class")
        else:
            cause = "unknown"
    else:
        # a tenant-wide change is not evidence for a cohort-scoped move when no mechanism layer moved
        kinds = [x[2].get("kind") for x in rows if x[0] == 2]
        if "prompt" in kinds and "model" in kinds:
            cause = "prompt.regression"
            notes.append("a prompt change and a model change both align; no per-call model metric moved, "
                         "so the prompt is the better-supported cause")
        elif kinds:
            cause = cause_from_word(kinds[0]) or "unknown"
        elif flips:
            cause = next((cause_from_word(f["field"]) for f in flips if cause_from_word(f["field"])), "unknown")
        elif "s.handoff_unplanned" in metrics and not (metrics & BEHAVIOUR):
            cause = "routing.error"
        else:
            cause = "unknown"
        if cause == "unknown" and (metrics & BEHAVIOUR) and not (metrics & OUTCOME):
            notes.append("conversation behaviour changed (longer / costlier) with outcomes flat and no aligned change")

    att = None
    for _, _, r in rows:
        if consistent(r.get("kind"), cause):
            att = {"kind": r.get("kind"), "day": int(r["day"]), "target": r.get("target"),
                   "from": r.get("from_value"), "to": r.get("to_value"), "source": "config_timeline"}
            break
    if att is None:
        for f in flips:
            if consistent(f["field"], cause):
                att = {"kind": cause.split(".")[0], "day": f["day"], "target": f["agent_id"], "from": f["from"],
                       "to": f["to"], "source": "version flip discovered in session data (no config row)"}
                break
    conf = 0.35 if cause == "unknown" else 0.6 + (0.15 if mech else 0.0) + (0.15 if att else 0.0)
    return {"cause": cause, "confidence": round(min(conf, 0.95), 2), "attributed_change": att,
            "audience": ["agent_builder", "business_owner"], "notes": notes}
