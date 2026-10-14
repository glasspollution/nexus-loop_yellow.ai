"""Every number carries its definition (product handoff 5.5).

A registry of definitions for every figure the report and the screen show: the scanner's metrics (derived from
their naming, generically), the impact figures of a decision packet, the standard, and the replay verification.
Each entry states what the number is, its unit, its filter and denominator, its fidelity and its coverage. Coverage
of step-derived metrics is measured from the data (which agent kinds actually emit each step type), and every place
where the data contradicts the catalog's own coverage semantics is reported rather than silently trusted.
"""

LAYER_WORDS = {"tool_call": "tool call", "llm_call": "model call", "kb_lookup": "knowledge-base lookup",
               "guardrail": "guardrail check", "routing": "routing step", "handoff": "handoff step"}

SESSION_METRICS = {
    "s.resolved": ("Resolution rate", "share", "conversations whose session_end = 'resolved'", "all conversations"),
    "s.abandoned": ("Abandonment rate", "share", "conversations whose session_end = 'abandoned'", "all conversations"),
    "s.handoff_unplanned": ("Unplanned handoff rate", "share",
                            "conversations ending in a handoff where handoff_by_design is not true", "all conversations"),
    "s.milestones_complete": ("Journey completion rate", "share",
                              "conversations that reached every milestone of their journey", "conversations with a journey"),
    "s.milestone_ratio": ("Journey progress", "ratio", "milestones reached / milestones in the journey",
                          "conversations with a journey"),
    "s.turns": ("Turns per conversation", "turns", "mean number of user/agent turns", "all conversations"),
    "s.duration_s": ("Conversation duration", "seconds", "mean seconds from first to last turn", "all conversations"),
    "s.cost_usd": ("Cost per conversation", "USD", "mean cost_usd", "conversations of agent kinds the catalog says emit steps"),
    "s.tool_error_any": ("Conversations with a tool error", "share", "tool_error_count > 0",
                         "conversations of agent kinds the catalog says emit steps"),
    "s.guardrail_any": ("Conversations with a guardrail block", "share", "guardrail_blocks > 0",
                        "conversations of agent kinds the catalog says emit steps"),
}

IMPACT = [
    ("impact.exposed", "Conversations in the slice", "conversations",
     "every conversation of the tenant in the affected slice during the impact window", "count", "measured"),
    ("impact.share", "Share of tenant traffic", "share",
     "exposed conversations / all of the tenant's conversations in the impact window", "ratio", "derived"),
    ("impact.hit", "Conversations actually hit", "conversations",
     "exposed conversations in which the diagnosed mechanism was observed (the hit predicate is stated per finding)",
     "count", "measured"),
    ("impact.resolution_rate", "Resolution rate", "share", "session_end = 'resolved' / conversations", "ratio", "measured"),
    ("impact.lost_resolutions", "Resolutions lost against the baseline", "conversations",
     "(baseline resolution rate - slice resolution rate) x exposed conversations; signed (negative means more resolved "
     "than the baseline), with a 95% normal-approximation range", "estimate", "derived"),
    ("impact.unplanned_handoffs_total", "Unplanned handoffs (total)", "conversations",
     "exposed conversations ending in a handoff with handoff_by_design not true", "count", "measured"),
    ("impact.unplanned_handoffs_excess", "Humans reached who were not meant to be involved, because of this problem",
     "conversations", "unplanned handoffs in the slice - baseline unplanned-handoff rate x exposed conversations, with a "
     "95% range", "estimate", "derived"),
    ("impact.abandoned_excess", "Extra abandoned conversations", "conversations",
     "abandoned in the slice - baseline abandonment rate x exposed conversations", "estimate", "derived"),
    ("impact.extra_turns", "Extra turns", "turns",
     "(mean turns in the slice - mean turns at baseline) x exposed conversations", "estimate", "derived"),
    ("impact.extra_minutes", "Extra customer minutes", "minutes",
     "(mean duration in the slice - mean duration at baseline) x exposed conversations / 60", "estimate", "derived"),
    ("impact.cost_excess", "Extra spend against the baseline", "USD",
     "(mean cost_usd in the slice - mean at baseline) x conversations that carry a cost_usd value; only recorded model "
     "spend, never human handling cost", "estimate", "derived"),
    ("impact.cost_total", "Total recorded spend in the slice", "USD", "sum of cost_usd over exposed conversations",
     "sum", "measured"),
    ("impact.cost_coverage", "Cost coverage", "share", "exposed conversations that carry a cost_usd value / exposed",
     "ratio", "measured"),
    ("impact.days_running", "Days running", "days", "impact window end - onset + 1 (inclusive)", "count", "measured"),
    ("impact.status", "Status at the end of the data", "state",
     "ongoing: the window reaches the last days of the data; ended: after the window the mechanism metric is back within "
     "25% of the gap to its baseline; persisting: it is not", "state", "derived"),
    ("impact.run_rate", "Recent daily rate", "per day", "the same estimate over the last (up to) 7 days of the window, / days",
     "estimate", "derived"),
    ("impact.projection", "Projected cost of inaction", "total",
     "recent daily rate x 7 or 30 days; a projection that assumes the recent rate and volume hold; never shown for a "
     "problem that has ended", "projection", "derived"),
    ("impact.mechanism", "Mechanism metric", "rate or mean",
     "the runtime-layer metric that carries the diagnosed cause, measured in the slice, at baseline and after the window",
     "rate", "measured"),
    ("standard.best", "Standard (best)", "metric units",
     "top-decile weekly value over reference weeks: p90 for higher-is-better, p10 for lower-is-better", "statistic", "derived"),
    ("standard.median", "Standard (typical)", "metric units", "median weekly value over reference weeks", "statistic",
     "derived"),
    ("standard.gap", "Gap to the standard", "metric units", "value in the finding window - standard median", "difference",
     "derived"),
    ("replay.before_after", "Replay before / after", "replay metric units",
     "values returned by the organisers' replay simulator for the cohort; simulated, not measured from the corpus",
     "simulation", "derived"),
    ("replay.prediction_error", "Prediction error", "replay metric units",
     "predicted delta - replayed delta, where the prediction is a fraction of the measured gap applied to the replay's "
     "own before value", "difference", "derived"),
]


def layer_coverage(C):
    """Per step layer: which agent kinds emit it (from the data) and the share of each tenant's sessions that can."""
    S = C["S"]
    kinds = S.get("kinds", [])
    emits = {}
    for key, n in (C.get("kind_steps") or {}).items():
        kind, layer = key.split("|", 1)
        if n > 0:
            emits.setdefault(layer, set()).add(kind)
    out = {}
    for layer, ks in emits.items():
        codes = [kinds.index(k) for k in ks if k in kinds]
        per = {}
        for t in C["tenants"]:
            tm = S["ten"] == S["tenant_index"][t]
            per[t] = round(float(((S["kind"] == codes[0]) if len(codes) == 1 else
                                  sum((S["kind"] == c) for c in codes).astype(bool))[tm].mean()) if codes else 0.0, 4)
        out[layer] = {"kinds": sorted(ks), "coverage": per}
    return out


def catalog_contradictions(C):
    """Agent kinds the catalog says emit NO steps of a type, but which do in this corpus."""
    out = []
    no_step = set(C.get("no_step_kinds") or [])
    for key, n in sorted((C.get("kind_steps") or {}).items()):
        kind, layer = key.split("|", 1)
        if kind in no_step and n > 0:
            out.append({"agent_kind": kind, "step_type": layer, "steps": int(n),
                        "text": "the catalog says %s sessions emit no mechanism steps, but this corpus holds %d %s steps "
                                "from them" % (kind, n, layer)})
    return out


def _metric_entry(C, metric, cov):
    if metric.startswith("s.quality_score@"):
        ver = metric.split("@", 1)[1]
        cal = C["calibration"]["quality_within_version"]
        return {"id": "metric:" + metric, "label": "Judged quality (judge %s)" % ver, "unit": "score 1-5",
                "definition": "mean quality_score over conversations scored by judge_version %s; never compared across "
                              "judge versions" % ver,
                "filter": "judge_version = '%s'" % ver, "denominator": "conversations scored by that judge version",
                "fidelity": "judged", "coverage": {"value": 1.0, "basis": "every conversation carries a judged score"},
                "calibration": {"agreement": cal["agreement"], "n": cal["n"], "tolerance": cal["tolerance"],
                                "basis": "human rubric labels within a matching judge_version"},
                "source": "corpus/sessions.jsonl.gz: quality_score, judge_version"}
    if metric in SESSION_METRICS:
        label, unit, definition, denom = SESSION_METRICS[metric]
        eligible = "catalog" in denom
        return {"id": "metric:" + metric, "label": label, "unit": unit, "definition": definition, "filter": definition,
                "denominator": denom, "fidelity": "measured",
                "coverage": ({"value_by_tenant": C["coverage"], "basis": "share of sessions of catalog-eligible agent kinds"}
                             if eligible else {"value": 1.0, "basis": "present on every session"}),
                "source": "corpus/sessions.jsonl.gz"}
    layer, _, kind = metric.partition(".")
    word = LAYER_WORDS.get(layer, layer)
    text = {"fail": "share of %s steps whose outcome is not 'ok'" % word,
            "timeout": "share of %s steps whose outcome is 'timeout'" % word,
            "blocked": "share of %s steps whose outcome is 'blocked'" % word,
            "retry": "share of %s steps with retry_count > 0" % word,
            "duration_ms": "mean duration of %s steps in milliseconds" % word,
            "empty": "share of successful (outcome 'ok') tool calls that returned zero result fields: an HTTP 200 with "
                     "nothing in it",
            "miss": "share of knowledge-base lookups where kb_hit is false (no confident document)",
            "top_score": "mean retrieval confidence (kb_top_score, 0-1) of knowledge-base lookups",
            "tokens": "mean input + output tokens per model call"}.get(kind, "%s of %s steps" % (kind, word))
    c = cov.get(layer)
    return {"id": "metric:" + metric, "label": "%s: %s" % (word.capitalize(), kind.replace("_", " ")),
            "unit": "share" if kind in ("fail", "timeout", "blocked", "retry", "empty", "miss") else kind,
            "definition": text, "filter": "step_type = '%s'" % layer, "denominator": "%s steps" % word,
            "fidelity": "derived" if kind == "empty" else "measured",
            "coverage": ({"value_by_tenant": c["coverage"], "basis": "share of sessions whose agent kind emits %s steps in "
                                                                     "this corpus (%s)" % (layer, ", ".join(c["kinds"]))}
                         if c else {"value": None, "basis": "no %s steps in this corpus" % layer}),
            "source": "corpus/agent_steps.jsonl.gz"}


def build_definitions(C):
    cov = layer_coverage(C)
    out = [{"id": i, "label": label, "unit": unit, "definition": d, "kind": kind, "fidelity": fid,
            "source": "computed from corpus/sessions.jsonl.gz and corpus/agent_steps.jsonl.gz"
            if not i.startswith("replay.") else "the organisers' replay service response"}
           for i, label, unit, d, kind, fid in IMPACT]
    out += [_metric_entry(C, m, cov) for m in C["metrics"]]
    return out
