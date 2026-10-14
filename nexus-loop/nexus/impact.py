"""Stage 5: the decision packet of a regression (product handoff section 5).

For every real problem it answers the problem statement's questions from the corpus alone:
  * how many conversations were in the affected slice (exposed), what share of traffic, and how many were actually
    hit by the diagnosed mechanism;
  * what happened to them against a NAMED baseline: resolutions lost (signed, with a range), humans reached who
    were never meant to be involved (excess over the baseline rate, total shown beside it), extra time, extra spend;
  * how long it has run and whether it is still running at the end of the data;
  * who has to act, how severe it is, and one plain sentence on what happens if nobody acts;
  * a derivation that names every window, population and formula so a reader can recompute it.
No tenant, cohort, tool or day is named anywhere in this module.
"""
import math

import numpy as np

from .cohorts import smask
from .measure import fmt_value

OWN_DAYS, OWN_MIN_SESSIONS, OWN_MIN_DAYS = 14, 100, 5
RUN_RATE_DAYS, POST_MIN_DAYS, POST_MIN_UNITS = 7, 3, 30
ENDED_FRACTION = 0.25
Z95 = 1.96

AUDIENCE = {
    "kb.gap": ["business_owner", "agent_builder"],
    "tool.contract_break": ["platform_owner", "agent_builder"],
    "tool.outage": ["platform_owner", "agent_builder"],
    "prompt.regression": ["agent_builder", "business_owner"],
    "model.change": ["platform_owner", "agent_builder"],
    "routing.error": ["agent_builder", "business_owner"],
    "unknown": ["platform_owner", "agent_builder"],
}
AUDIENCE_WHY = {
    "kb.gap": "What the agent may say about a product is the business owner's content; the agent builder owns "
              "indexing and retrieval.",
    "tool.contract_break": "The service behind the tool changed what it returns; the platform team owns that service, "
                           "the agent builder can guard against it.",
    "tool.outage": "The tool's service is failing; the platform team owns it, the agent builder owns the fallback path.",
    "prompt.regression": "The agent builder owns the prompt; the change had a stated purpose, so undoing it is the "
                         "business owner's call.",
    "model.change": "Model rollouts are a platform decision; the agent builder owns prompt compatibility.",
    "routing.error": "The agent builder owns routing configuration; the teams receiving handoffs belong to the "
                     "business owner.",
    "unknown": "No runtime layer explains it yet: the platform team triages and the agent builder checks the agent.",
}
MECHANISM = {"kb.gap": "kb_lookup.miss", "tool.contract_break": "tool_call.empty", "tool.outage": "tool_call.fail",
             "prompt.regression": "s.turns", "model.change": "s.turns", "routing.error": "s.handoff_unplanned"}
SEVERITY_ORDER = ["low", "medium", "high", "critical"]


# ----------------------------------------------------------------------------- per-session columns

def _session(C, metric):
    S = C["S"]
    j = S["MI"].get(metric)
    return None if j is None else (S["M"][:, j, 0], S["M"][:, j, 1])


def _tool_session(C, tool, metric):
    S = C["S"]
    if tool not in S["TM"] or metric not in S["TMI"]:
        return None
    idxs, arr = S["TM"][tool]
    n, s = np.zeros(len(S["day"])), np.zeros(len(S["day"]))
    n[idxs], s[idxs] = arr[:, S["TMI"][metric], 0], arr[:, S["TMI"][metric], 1]
    return n, s


def _rate(col, mask):
    if col is None:
        return None, 0
    n = float(col[0][mask].sum())
    return (float(col[1][mask].sum()) / n if n else None), int(n)


def _values(C, metric, mask):
    col = _session(C, metric)
    if col is None:
        return np.array([])
    sel = mask & (col[0] > 0)
    return col[1][sel] / col[0][sel]


def version_field(C, kind):
    """The per-session version field a config-change kind writes (e.g. a prompt change -> the prompt version field)."""
    for fld in sorted(C["S"].get("version_vocab", {})):
        if kind and str(kind).lower() in fld.lower():
            return fld
    return None


def mechanism_column(C, inc, metric):
    if inc["dim"] == "tool":
        col = _tool_session(C, inc["value"], metric)
        if col is not None:
            return col
    return _session(C, metric)


def hit_mask(C, inc, mk):
    """Sessions in which the diagnosed mechanism was actually observed, and the plain words for it."""
    cause, S = inc["cause_class"], C["S"]
    if cause == "kb.gap":
        col = _session(C, "kb_lookup.miss")
        if col is not None:
            return col[1] > 0, "had at least one knowledge-base lookup that found no confident document"
    if cause in ("tool.contract_break", "tool.outage"):
        m = "tool_call.empty" if cause == "tool.contract_break" else "tool_call.fail"
        col = mechanism_column(C, inc, m)
        if col is not None:
            return col[1] > 0, ("received at least one successful tool response with nothing in it (outcome ok, "
                                "zero result fields)" if m == "tool_call.empty" else
                                "had at least one tool call that errored or timed out")
    if cause in ("prompt.regression", "model.change"):
        att = inc.get("attributed_change") or {}
        fld = version_field(C, att.get("kind"))
        vocab = S.get("version_vocab", {}).get(fld, [])
        if fld and att.get("to") in vocab:
            return S["version_codes"][fld] == vocab.index(att["to"]), "were served by %s %s" % (fld, att["to"])
    if cause == "routing.error":
        col = _session(C, "s.handoff_unplanned")
        if col is not None:
            return col[1] > 0, "were handed to a human the agent was not built to hand off to"
    return mk.copy(), "are in the affected slice (no narrower mechanism can be observed for this cause)"


# ----------------------------------------------------------------------------- baseline

def choose_baseline(C, inc, mk, o, e, others):
    """Own past when the slice has one; otherwise same-day peers that follow the same journey; otherwise the rest of
    the tenant on the same days. Days inside other regressions are excluded from every baseline."""
    S = C["S"]
    day, ten = S["day"], inc["tenant"]
    excl = np.zeros(len(day), dtype=bool)
    for x in others:
        excl |= smask(C, x["tenant"], x["dim"], x["value"]) & (day >= x["from"] - 2) & (day <= x["to"] + 2)
    first = C["first_day"].get((ten, inc["dim"], inc["value"]), 0)
    newborn = inc.get("baseline_mode") == "peer" or first >= o - 2
    lo = max(0, o - OWN_DAYS)
    own = mk & (day >= lo) & (day < o) & ~excl
    if not newborn and own.sum() >= OWN_MIN_SESSIONS and len(np.unique(day[own])) >= OWN_MIN_DAYS:
        return own, {"kind": "own_past", "days": [int(lo), int(o - 1)], "n": int(own.sum()),
                     "label": "this slice's own %d days before onset (days %d-%d)" % (o - lo, lo, o - 1),
                     "why": "the slice existed before the problem, so comparing it with its own past holds its traffic "
                            "mix fixed; a problem that looks like its peers is only visible this way"}
    win = (day >= o) & (day <= e)
    reason = ("the slice was first seen on day %d, so it has no before-period" % first if newborn else
              "its own past is too thin (fewer than %d conversations on %d days)" % (OWN_MIN_SESSIONS, OWN_MIN_DAYS))
    if inc["dim"] == "intent":
        ms = C["catalog"].get("milestones", {}).get(ten, {})
        chain = ms.get(inc["value"])
        peers = [i for i, ch in sorted(ms.items()) if chain is not None and ch == chain and i != inc["value"]]
        if peers:
            pm = np.zeros(len(day), dtype=bool)
            for p in peers:
                pm |= smask(C, ten, "intent", p)
            base = pm & win & ~excl
            if base.sum() >= OWN_MIN_SESSIONS:
                return base, {"kind": "peers_same_journey", "days": [int(o), int(e)], "n": int(base.sum()),
                              "peers": peers,
                              "label": "intents with the same journey (%s) on the same days %d-%d" % (", ".join(peers), o, e),
                              "why": reason + "; intents that follow the same milestone chain in the catalog are the "
                                              "closest comparable traffic, measured on the same days so platform "
                                              "conditions match"}
    base = smask(C, ten, "__all__", "__all__") & ~mk & win & ~excl
    if base.sum() < OWN_MIN_SESSIONS:
        base = smask(C, ten, "__all__", "__all__") & ~mk & win
    return base, {"kind": "rest_of_tenant", "days": [int(o), int(e)], "n": int(base.sum()),
                  "label": "the rest of this tenant's traffic on the same days %d-%d" % (o, e),
                  "why": reason + "; no sibling follows the same journey, so the rest of the tenant on the same days is "
                                  "the comparison"}


def _excess(k_c, n, p_b, n_b):
    """Count above what the baseline rate predicts, with a 95% normal-approximation range."""
    p_c = k_c / n if n else 0.0
    x = k_c - p_b * n
    se = math.sqrt(max(n * p_c * (1 - p_c), 0.0) + (n * n * p_b * (1 - p_b) / n_b if n_b else 0.0))
    return x, [x - Z95 * se, x + Z95 * se]


def _r(x, d=4):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), d)


# ----------------------------------------------------------------------------- the packet

def packet(C, inc, others=()):
    S, D = C["S"], C["days"]
    day, ten = S["day"], inc["tenant"]
    mk = smask(C, ten, inc["dim"], inc["value"])
    att = inc.get("attributed_change") or None
    first = C["first_day"].get((ten, inc["dim"], inc["value"]), 0)
    o = int(att["day"]) if att and abs(int(att["day"]) - inc["from"]) <= 4 else inc["from"]
    o, e = max(o, first), inc["to"]
    if e < o:
        o = inc["from"]
    win = (day >= o) & (day <= e)
    coh = mk & win
    n = int(coh.sum())
    if n == 0:
        return None
    N_T = int((smask(C, ten, "__all__", "__all__") & win).sum()) or 1
    base, bl = choose_baseline(C, inc, mk, o, e, others)
    n_B = int(base.sum())
    hit, hit_what = hit_mask(C, inc, mk)
    hc = coh & hit
    h = int(hc.sum())

    res = _session(C, "s.resolved")
    r_C, _ = _rate(res, coh)
    r_B, _ = _rate(res, base)
    r_B = r_C if r_B is None else r_B
    R_C = r_C * n
    x_res, ci_res = _excess(R_C, n, r_B, n_B)
    lost, lost_ci = -x_res, [-ci_res[1], -ci_res[0]]
    r_hit, _ = _rate(res, hc) if h else (None, 0)
    r_nothit, _ = _rate(res, coh & ~hit) if h < n else (None, 0)

    def excess_of(metric):
        col = _session(C, metric)
        k = float(col[1][coh].sum()) if col is not None else 0.0
        p_b, _ = _rate(col, base)
        x, ci = _excess(k, n, p_b or 0.0, n_B)
        return int(k), x, ci, p_b

    U, X_H, X_H_ci, u_B = excess_of("s.handoff_unplanned")
    A, X_A, X_A_ci, a_B = excess_of("s.abandoned")

    tc, tb = _values(C, "s.turns", coh), _values(C, "s.turns", base)
    dc, db = _values(C, "s.duration_s", coh), _values(C, "s.duration_s", base)
    mean = lambda a: float(a.mean()) if len(a) else None
    med = lambda a: float(np.median(a)) if len(a) else None
    extra_turns = (mean(tc) - mean(tb)) * n if len(tc) and len(tb) else None
    extra_min = (mean(dc) - mean(db)) * n / 60.0 if len(dc) and len(db) else None
    turns_rel = (mean(tc) - mean(tb)) / mean(tb) if len(tc) and len(tb) and mean(tb) else None

    cost = S["cost"]
    cc, cb = cost[coh], cost[base]
    cc_ok, cb_ok = cc[~np.isnan(cc)], cb[~np.isnan(cb)]
    n_E = int(len(cc_ok))
    k_C, k_B = (mean(cc_ok), mean(cb_ok))
    cost_excess = (k_C - k_B) * n_E if n_E and k_B is not None else None
    cost_rel = (k_C - k_B) / k_B if n_E and k_B else None
    kinds = S.get("kinds", [])
    declared_no_cost = [kinds.index(k) for k in (C.get("no_step_kinds") or []) if k in kinds]
    cost_on_declared = int(sum(int((~np.isnan(cc) & (S["kind"][coh] == k)).sum()) for k in declared_no_cost))

    # ---- mechanism metric and status ----
    cause = inc["cause_class"]
    prim = (inc.get("primary") or {}).get("metric")
    mech = MECHANISM.get(cause) or prim or "s.resolved"
    mcol = mechanism_column(C, inc, mech)
    m_C, _ = _rate(mcol, coh)
    m_B, _ = _rate(mcol, base)
    post = mk & (day > e)
    post_days = D - 1 - e
    m_post, n_post = _rate(mcol, post)
    if post_days < POST_MIN_DAYS:
        state = "ongoing"
    elif m_post is None or n_post < POST_MIN_UNITS or m_B is None or m_C is None:
        state = "unknown"
    elif abs(m_post - m_B) <= ENDED_FRACTION * abs(m_C - m_B):
        state = "ended"
    else:
        state = "persisting"
    live = None
    if cause in ("prompt.regression", "model.change") and att:
        fld = version_field(C, att.get("kind"))
        vocab = S.get("version_vocab", {}).get(fld, [])
        if fld and att.get("to") in vocab and post.any():
            live = round(float((S["version_codes"][fld][post] == vocab.index(att["to"])).mean()), 4)

    # ---- recent run rate and projection ----
    rlo = max(o, e - RUN_RATE_DAYS + 1)
    rwin = mk & (day >= rlo) & (day <= e)
    n_R, ndays_R = int(rwin.sum()), e - rlo + 1
    r_CR, _ = _rate(res, rwin)
    uc = _session(C, "s.handoff_unplanned")
    k_UR = float(uc[1][rwin].sum()) if uc is not None else 0.0
    rate = {"days": [int(rlo), int(e)],
            "lost_per_day": ((r_B - r_CR) * n_R / ndays_R) if r_CR is not None else None,
            "handoffs_excess_per_day": (k_UR - (u_B or 0.0) * n_R) / ndays_R,
            "minutes_per_day": (extra_min / max(1, e - o + 1)) if extra_min is not None else None,
            "cost_per_day": (cost_excess / max(1, e - o + 1)) if cost_excess is not None else None}
    projection = None
    if state != "ended":
        projection = {k: {"7_days": _r(v * 7, 2), "30_days": _r(v * 30, 2)} for k, v in rate.items()
                      if k != "days" and v is not None}
        projection["assumption"] = "the last %d days' rate and volume hold" % ndays_R

    # ---- harm, severity, owner ----
    lost_share = lost / N_T
    if lost_ci[0] > 0:
        harm = "outcome"
        drop = r_B - r_C
        sev = "critical" if drop >= 0.30 or lost_share >= 0.01 else "high" if drop >= 0.05 or lost_share >= 0.005 else "medium"
    elif max(turns_rel or 0, cost_rel or 0) >= 0.10:
        harm = "behaviour"
        sev = "high" if max(turns_rel or 0, cost_rel or 0) >= 0.25 else "medium"
    elif X_H_ci[0] > 0:
        harm = "handoffs"
        sev = "high" if X_H / N_T >= 0.005 else "medium"
    else:
        harm, sev = "mechanism", "low"
    if state == "ended":
        sev = SEVERITY_ORDER[max(0, SEVERITY_ORDER.index(sev) - 1)]
    audience = AUDIENCE.get(cause, AUDIENCE["unknown"])
    if inc.get("kind") == "platform" or ten == "*":
        audience = ["platform_owner"] + [a for a in audience if a != "platform_owner"]

    fail_rate = None
    if cause == "tool.contract_break":
        fail_rate, _ = _rate(mechanism_column(C, inc, "tool_call.fail"), coh)

    where = "all traffic" if inc["dim"] in (None, "__all__") else "%s = %s" % (inc["dim"], inc["value"])
    p = {"tenant": ten, "where": where, "cause": cause, "onset": int(o), "end": int(e), "days": int(e - o + 1),
         "detection_from": int(max(0, inc["from"] - 2)), "n": n, "N_T": N_T, "share": n / N_T, "hit": h,
         "hit_what": hit_what, "r_C": r_C, "r_B": r_B, "r_hit": r_hit, "r_nothit": r_nothit,
         "lost": lost, "lost_ci": lost_ci, "handoffs_total": U, "handoffs_excess": X_H, "handoffs_ci": X_H_ci,
         "handoff_rate_baseline": u_B, "abandoned_total": A, "abandoned_excess": X_A, "abandoned_ci": X_A_ci,
         "turns": {"mean": mean(tc), "mean_baseline": mean(tb), "median": med(tc), "median_baseline": med(tb),
                   "extra": extra_turns, "relative": turns_rel},
         "minutes_extra": extra_min,
         "cost": {"per_conversation": k_C, "per_conversation_baseline": k_B, "excess": cost_excess,
                  "total": float(cc_ok.sum()) if n_E else None, "coverage": n_E / n, "n": n_E, "relative": cost_rel,
                  "on_declared_no_cost_kinds": cost_on_declared},
         "baseline": bl,
         "mechanism": {"metric": mech, "current": m_C, "baseline": m_B, "after": m_post, "after_days":
                       [int(e + 1), int(D - 1)] if post_days > 0 else None},
         "status": {"state": state, "recovery_day": int(e + 1) if state == "ended" else None,
                    "attributed_version_still_live_share": live},
         "run_rate": rate, "projection": projection, "harm": harm, "severity": sev,
         "audience": audience, "audience_why": AUDIENCE_WHY.get(cause, AUDIENCE_WHY["unknown"]),
         "tool_fail_rate": fail_rate, "attributed_change": att}
    p["status"]["sentence"] = status_sentence(p)
    p["if_nothing_changes"] = inaction(p)
    p["derivation"] = derivation(p)
    p["figures"] = figures(p)
    return p


# ----------------------------------------------------------------------------- words (numbers only from the packet)

def _i(x):
    return "n/a" if x is None else "{:,}".format(int(round(x)))


def _pct(x):
    return "n/a" if x is None else "%.1f%%" % (100 * x)


def status_sentence(p):
    st, m = p["status"], p["mechanism"]
    if st["state"] == "ongoing":
        return "Still happening: the problem runs to the last days of the data (day %d)." % p["end"]
    if st["state"] == "ended":
        s = ("Stopped: after day %d %s in this slice is back to %s (baseline %s, %s while it ran)."
             % (p["end"], m["metric"], fmt_value(m["metric"], m["after"]), fmt_value(m["metric"], m["baseline"]),
                fmt_value(m["metric"], m["current"])))
        if st["attributed_version_still_live_share"]:
            s += " The blamed version is still live on %s of the slice's later traffic, so the recovery is unexplained." \
                 % _pct(st["attributed_version_still_live_share"])
        return s
    if st["state"] == "persisting":
        return ("Persisting: after day %d %s is still %s against a baseline of %s."
                % (p["end"], m["metric"], fmt_value(m["metric"], m["after"]), fmt_value(m["metric"], m["baseline"])))
    return "Status unknown: too little traffic after the window to tell whether it stopped."


def inaction(p):
    """Exactly one plain sentence (the problem statement asks for one), built only from computed numbers."""
    rr, days = p["run_rate"], max(1, p["days"])
    if p["status"]["state"] == "ended":
        if p["harm"] in ("outcome", "handoffs"):
            return ("It has stopped for now with no recorded fix, but if it comes back at the rate it ran, about %s "
                    "conversations a day in this slice would go unresolved and %s a day would reach a human who should not "
                    "have been needed." % (_i(p["lost"] / days), _i(p["handoffs_excess"] / days)))
        return ("It has stopped for now with no recorded fix, but if it comes back, customers in this slice would again "
                "spend about %s extra minutes a day in conversation and it would cost about $%.2f a day more."
                % (_i((p["minutes_extra"] or 0) / days), (p["cost"]["excess"] or 0) / days))
    if p["harm"] == "outcome":
        proj = (p["projection"] or {}).get("lost_per_day", {})
        return ("If nobody acts, about %s conversations a day in this slice will keep failing to resolve and about %s a day "
                "will reach a human who was not meant to be involved, roughly %s lost resolutions over the next 7 days if "
                "the recent rate holds." % (_i(rr["lost_per_day"]), _i(rr["handoffs_excess_per_day"]),
                                            _i(proj.get("7_days"))))
    if p["harm"] == "behaviour":
        proj = (p["projection"] or {}).get("cost_per_day", {})
        return ("Resolution is not measurably worse (%s against %s), but if nobody acts customers in this slice keep "
                "spending about %s extra minutes a day in conversation (%.1f turns on average instead of %.1f) and it "
                "costs about $%.2f a day more: roughly $%.2f over the next 30 days if the recent rate holds."
                % (_pct(p["r_C"]), _pct(p["r_B"]), _i(rr["minutes_per_day"]), p["turns"]["mean"] or 0,
                   p["turns"]["mean_baseline"] or 0, rr["cost_per_day"] or 0, proj.get("30_days") or 0))
    if p["harm"] == "handoffs":
        return ("If nobody acts, about %s conversations a day keep reaching a human who was not meant to be involved."
                % _i(rr["handoffs_excess_per_day"]))
    return ("Nothing customers can see has moved measurably yet (%s %s against %s), but this is an early warning that "
            "will not stay invisible." % (p["mechanism"]["metric"], fmt_value(p["mechanism"]["metric"], p["mechanism"]["current"]),
                                     fmt_value(p["mechanism"]["metric"], p["mechanism"]["baseline"])))


def derivation(p):
    b, t, c, m = p["baseline"], p["turns"], p["cost"], p["mechanism"]
    lines = [
        "WINDOW: impact is measured over days %d-%d (inclusive, %d days). The finding's window starts on day %d only so "
        "that detection lag is scored fairly; no figure below uses those extra days." % (p["onset"], p["end"], p["days"],
                                                                                        p["detection_from"]),
        "EXPOSED: %s conversations of %s in the slice %s over those days, %s of the tenant's %s."
        % (_i(p["n"]), p["tenant"], p["where"], _pct(p["share"]), _i(p["N_T"])),
        "HIT: %s of them %s%s." % (_i(p["hit"]), p["hit_what"],
                                   "" if p["r_hit"] is None or p["r_nothit"] is None else
                                   "; those resolved at %s against %s for the rest of the slice" % (_pct(p["r_hit"]),
                                                                                                  _pct(p["r_nothit"]))),
        "BASELINE: %s, %s conversations. Why: %s." % (b["label"], _i(b["n"]), b["why"]),
        "RESOLUTION: %s in the slice against %s at baseline. Lost resolutions = (baseline rate - slice rate) x %s = %s "
        "(95%% range %s to %s)." % (_pct(p["r_C"]), _pct(p["r_B"]), _i(p["n"]), _i(p["lost"]), _i(p["lost_ci"][0]),
                                    _i(p["lost_ci"][1])),
        "HUMANS: %s conversations ended in a handoff the agent was not built to make; the baseline rate of %s predicts %s, "
        "so %s are attributable to this problem (95%% range %s to %s)." % (
            _i(p["handoffs_total"]), _pct(p["handoff_rate_baseline"]), _i(p["handoffs_total"] - p["handoffs_excess"]),
            _i(p["handoffs_excess"]), _i(p["handoffs_ci"][0]), _i(p["handoffs_ci"][1])),
        "ABANDONED: %s in the slice; the baseline rate predicts %s, so %s %s." % (
            _i(p["abandoned_total"]), _i(p["abandoned_total"] - p["abandoned_excess"]), _i(abs(p["abandoned_excess"])),
            "more" if p["abandoned_excess"] >= 0 else "fewer"),
        "TIME: %.2f turns per conversation against %.2f (median %s against %s): %s %s turns and %s %s customer-minutes "
        "over the window." % (t["mean"] or 0, t["mean_baseline"] or 0, t["median"], t["median_baseline"],
                              _i(abs(t["extra"] or 0)), "more" if (t["extra"] or 0) >= 0 else "fewer",
                              _i(abs(p["minutes_extra"] or 0)), "more" if (p["minutes_extra"] or 0) >= 0 else "fewer"),
        ("COST: %s of %s conversations carry a recorded cost_usd (%s). $%.5f per conversation against $%.5f: $%.2f %s "
         "than the baseline over the window (total recorded spend $%.2f). Only model spend is recorded; human handling "
         "cost is not in the data." % (_i(c["n"]), _i(p["n"]), _pct(c["coverage"]), c["per_conversation"] or 0,
                                        c["per_conversation_baseline"] or 0, abs(c["excess"] or 0),
                                        "more" if (c["excess"] or 0) >= 0 else "less", c["total"] or 0))
        if c["n"] else "COST: no conversation in the slice carries a recorded cost_usd, so no cost is claimed.",
        "MECHANISM: %s is %s in the slice against %s at baseline%s." % (
            m["metric"], fmt_value(m["metric"], m["current"]), fmt_value(m["metric"], m["baseline"]),
            "" if m["after"] is None else " and %s after the window" % fmt_value(m["metric"], m["after"])),
        "STATUS: " + p["status"]["sentence"],
    ]
    if p["tool_fail_rate"] is not None:
        lines.append("DECLARED METRIC: the tool's own error rate reads %s during the problem, so no error-rate alert would "
                     "surface it; only the empty-response rate shows it." % _pct(p["tool_fail_rate"]))
    if p["projection"]:
        lines.append("RUN RATE: over days %d-%d; projections assume %s." % (p["run_rate"]["days"][0],
                                                                          p["run_rate"]["days"][1],
                                                                          p["projection"]["assumption"]))
    if c["on_declared_no_cost_kinds"]:
        lines.append("DATA NOTE: %s of these costed conversations belong to an agent kind the catalog says emits no "
                     "mechanism steps; the data carries cost for them, so they are counted." % _i(c["on_declared_no_cost_kinds"]))
    return " ".join(lines)


def figures(p):
    b = {"kind": p["baseline"]["kind"], "label": p["baseline"]["label"], "n": p["baseline"]["n"]}
    w = [p["onset"], p["end"]]
    f = [
        {"def": "impact.exposed", "value": p["n"], "display": _i(p["n"]), "window": w},
        {"def": "impact.share", "value": _r(p["share"]), "display": _pct(p["share"]), "window": w},
        {"def": "impact.hit", "value": p["hit"], "display": _i(p["hit"]), "window": w, "predicate": p["hit_what"]},
        {"def": "impact.resolution_rate", "value": _r(p["r_C"]), "display": _pct(p["r_C"]), "window": w,
         "baseline": dict(b, value=_r(p["r_B"]), display=_pct(p["r_B"]))},
        {"def": "impact.lost_resolutions", "value": _r(p["lost"], 1), "display": _i(p["lost"]), "window": w,
         "ci95": [_r(x, 1) for x in p["lost_ci"]], "baseline": b},
        {"def": "impact.unplanned_handoffs_excess", "value": _r(p["handoffs_excess"], 1), "display": _i(p["handoffs_excess"]),
         "window": w, "ci95": [_r(x, 1) for x in p["handoffs_ci"]], "baseline": b},
        {"def": "impact.unplanned_handoffs_total", "value": p["handoffs_total"], "display": _i(p["handoffs_total"]),
         "window": w},
        {"def": "impact.abandoned_excess", "value": _r(p["abandoned_excess"], 1), "display": _i(p["abandoned_excess"]),
         "window": w, "baseline": b},
        {"def": "impact.extra_turns", "value": _r(p["turns"]["extra"], 1), "display": _i(p["turns"]["extra"]),
         "window": w, "baseline": b},
        {"def": "impact.extra_minutes", "value": _r(p["minutes_extra"], 1), "display": _i(p["minutes_extra"]),
         "window": w, "baseline": b},
        {"def": "impact.cost_excess", "value": _r(p["cost"]["excess"], 2),
         "display": "n/a" if p["cost"]["excess"] is None else "$%.2f" % p["cost"]["excess"], "window": w, "baseline": b,
         "coverage": _r(p["cost"]["coverage"])},
        {"def": "impact.cost_total", "value": _r(p["cost"]["total"], 2),
         "display": "n/a" if p["cost"]["total"] is None else "$%.2f" % p["cost"]["total"], "window": w},
        {"def": "impact.days_running", "value": p["days"], "display": "%d days" % p["days"], "window": w},
        {"def": "impact.status", "value": p["status"]["state"], "display": p["status"]["state"],
         "text": p["status"]["sentence"]},
        {"def": "impact.mechanism", "metric": p["mechanism"]["metric"], "value": _r(p["mechanism"]["current"], 5),
         "display": fmt_value(p["mechanism"]["metric"], p["mechanism"]["current"]),
         "baseline": dict(b, value=_r(p["mechanism"]["baseline"], 5),
                          display=fmt_value(p["mechanism"]["metric"], p["mechanism"]["baseline"])),
         "after": _r(p["mechanism"]["after"], 5), "definition_ref": "metric:" + p["mechanism"]["metric"]},
    ]
    if p["projection"]:
        f.append({"def": "impact.projection", "value": p["projection"], "display": "see value",
                  "assumption": p["projection"]["assumption"]})
    return f


def impact_block(p):
    """The schema's impact object: required keys with the decision-grade meanings, plus the full packet fields."""
    return {"conversations_affected": p["n"], "share_of_traffic": round(min(1.0, max(0.0, p["share"])), 4),
            "downstream": {"conversations_hit": p["hit"],
                           "would_have_resolved_at_baseline": int(round(p["lost"])),
                           "would_have_resolved_at_baseline_ci95": [_r(x, 1) for x in p["lost_ci"]],
                           "unplanned_handoffs": int(round(p["handoffs_excess"])),
                           "unplanned_handoffs_total": p["handoffs_total"],
                           "unplanned_handoffs_ci95": [_r(x, 1) for x in p["handoffs_ci"]],
                           "abandoned": int(round(p["abandoned_excess"])), "abandoned_total": p["abandoned_total"],
                           "extra_turns": None if p["turns"]["extra"] is None else int(round(p["turns"]["extra"])),
                           "extra_customer_minutes": None if p["minutes_extra"] is None else int(round(p["minutes_extra"])),
                           "meaning": "handoffs and abandoned are EXCESS over the baseline rate (totals beside them); "
                                      "would_have_resolved_at_baseline is signed"},
            "cost_usd": _r(p["cost"]["excess"], 2), "cost_usd_meaning": "excess recorded model spend against the baseline",
            "days_running": p["days"], "derivation": p["derivation"],
            "windows": {"impact": [p["onset"], p["end"]], "finding": [p["detection_from"], p["end"]],
                        "baseline": p["baseline"]["days"], "after": p["mechanism"]["after_days"],
                        "run_rate": p["run_rate"]["days"]},
            "baseline": p["baseline"], "status": p["status"], "harm": p["harm"], "figures": p["figures"],
            "projection": p["projection"]}
