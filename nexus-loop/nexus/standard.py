"""Stage 6: what good looks like, mined from the deployment's own best conversations (Task 02; handoff section 6).

* EXEMPLAR = a measured fact pattern, never a judgment: resolved, every milestone of its journey reached, no failed
  or empty tool call, no knowledge-base miss.
* REFERENCE PERIOD = every day except the regression windows the scanner flagged (padded 2 days), so a problem's own
  bad days never become its standard, and a slice born mid-corpus is not dropped.
* STANDARDS are weekly aggregates (per-session turn percentiles are integers and useless): best = top decile of the
  reference weeks, median = the typical week. A slice with no before-period uses the peers that share its journey.
* GOLDEN SET = a small, deterministic, hashed sample of exemplars per tenant, frozen before any fix is verified
  (Rule 2: the reviewed set of good conversations is part of the yardstick). Members that also carry a positive human
  outcome label are marked outcome-reviewed; the rest are machine-selected, and nothing is called reviewed that is not.
"""
import hashlib
import json

import numpy as np

from .cohorts import smask
from .config import CFG

EXEMPLAR_DEFINITION = ("session_end = 'resolved' AND every milestone of the journey reached AND no tool_call with "
                       "outcome != 'ok' AND no tool_call with outcome 'ok' and result_field_count = 0 AND no kb_lookup "
                       "with kb_hit false")
REFERENCE_DEFINITION = "all days except regression cohort-windows flagged by the scanner, padded 2 days either side"
MIN_EXEMPLARS, MIN_WEEKS, MIN_WEEK_N = 40, 3, 30
GOLDEN_N = 25
STANDARD_DIMS = ("intent", "agent_id", "tool")
METRICS = {"resolution_rate": +1, "turns_to_resolve": -1, "cost_per_resolved_usd": -1}


def exemplar_mask(C):
    S = C["S"]
    M, MI = S["M"], S["MI"]
    ok = M[:, MI["s.resolved"], 1] > 0
    if "s.milestones_complete" in MI:
        j = MI["s.milestones_complete"]
        ok &= (M[:, j, 0] == 0) | (M[:, j, 1] > 0)
    for m in ("tool_call.fail", "tool_call.empty", "kb_lookup.miss"):
        if m in MI:
            ok &= M[:, MI[m], 1] == 0
    return ok


def reference_mask(C, incidents):
    day = C["S"]["day"]
    excl = np.zeros(len(day), dtype=bool)
    for inc in incidents:
        if inc["is_regression"]:
            excl |= smask(C, inc["tenant"], inc["dim"], inc["value"]) & (day >= inc["from"] - 2) & (day <= inc["to"] + 2)
    return ~excl


def _weekly(C, mask, values=None):
    """Per-week means of `values` (or the resolution rate) over weeks with enough conversations."""
    S = C["S"]
    week = S["day"] // 7
    W = int(week.max()) + 1
    if values is None:
        values = S["M"][:, S["MI"]["s.resolved"], 1]
    ok = mask & ~np.isnan(values)
    cnt = np.bincount(week[ok], minlength=W)
    tot = np.bincount(week[ok], weights=values[ok], minlength=W)
    keep = cnt >= MIN_WEEK_N
    return [float(x) for x in tot[keep] / cnt[keep]], [int(w) for w in np.nonzero(keep)[0]]


def _entry(C, tenant, cohort, metric, mask, ex, basis, gs_version):
    S = C["S"]
    if metric == "resolution_rate":
        vals, weeks = _weekly(C, mask)
    elif metric == "turns_to_resolve":
        vals, weeks = _weekly(C, mask & ex, S["M"][:, S["MI"]["s.turns"], 1])
    else:
        vals, weeks = _weekly(C, mask & ex, S["cost"])
    if len(vals) < MIN_WEEKS or int((mask & ex).sum()) < MIN_EXEMPLARS:
        return None
    best = float(np.percentile(vals, 90 if METRICS[metric] > 0 else 10))
    medv = float(np.median(vals))
    unit = {"resolution_rate": "share of conversations resolved", "turns_to_resolve": "mean turns of exemplar conversations",
            "cost_per_resolved_usd": "mean cost_usd of exemplar conversations"}[metric]
    return {"tenant": tenant, "cohort": cohort, "metric": metric, "exemplar_n": int((mask & ex).sum()),
            "golden_set_version": gs_version, "best": round(best, 5), "median": round(medv, 5),
            "deficit": round(abs(medv - best), 5), "direction": "higher_is_better" if METRICS[metric] > 0 else "lower_is_better",
            "reference_weeks": weeks, "basis": basis,
            "derivation": ("%s per week over %d reference weeks (%s; weeks with >= %d conversations); best = %s of the "
                           "weekly values, median = the typical week, deficit = distance from typical to best. "
                           "Exemplars: %s (n = %d)." % (unit, len(vals), REFERENCE_DEFINITION, MIN_WEEK_N,
                                                        "90th percentile" if METRICS[metric] > 0 else "10th percentile",
                                                        EXEMPLAR_DEFINITION, int((mask & ex).sum())))}


def golden_set(C, ref, ex):
    S = C["S"]
    variant = str(C["catalog"].get("corpus_variant", ""))
    labels = (C.get("labels") or {}).get("outcome", {})
    out = {}
    intents = S["codes"].get("intent")
    for ten in C["tenants"]:
        pool = np.nonzero(smask(C, ten, "__all__", "__all__") & ref & ex)[0]
        strata = {}
        for i in pool:
            strata.setdefault(int(intents[i]) if intents is not None else 0, []).append(i)
        for k in strata:     # exemplars a human also labelled resolved come first, then a stable hash order
            strata[k].sort(key=lambda i: (labels.get(str(S["sid"][i])) is not True,
                                          hashlib.sha256((variant + "|" + S["sid"][i]).encode()).hexdigest()))
        picks, keys, r = [], sorted(strata), 0
        while len(picks) < GOLDEN_N and any(len(strata[k]) > r for k in keys):
            for k in keys:
                if len(strata[k]) > r and len(picks) < GOLDEN_N:
                    picks.append(str(S["sid"][strata[k][r]]))
            r += 1
        ids = sorted(picks)
        version = "gs_" + hashlib.sha256(("%s|%s|%s|%s" % (EXEMPLAR_DEFINITION, REFERENCE_DEFINITION, ten, ",".join(ids)))
                                         .encode()).hexdigest()[:12]
        out[ten] = {"golden_set_version": version, "session_ids": ids, "n": len(ids),
                    "outcome_reviewed_ids": [s for s in ids if labels.get(s) is True],
                    "machine_selected_ids": [s for s in ids if labels.get(s) is not True],
                    "selection": "round-robin over intents; inside an intent ordered by sha256(corpus_variant | session_id)",
                    "exemplar_definition": EXEMPLAR_DEFINITION, "reference_period": REFERENCE_DEFINITION,
                    "review_scope": ("outcome_reviewed_ids carry a positive human 'resolved' label from labels/; that "
                                     "reviews resolution only, not content or policy. The others were selected by the "
                                     "measured exemplar definition and were not reviewed by a person.")}
    return out


def mine(C, incidents):
    """Returns (standard entries, golden set per tenant, per-incident standard comparison)."""
    S, day = C["S"], C["S"]["day"]
    ex, ref = exemplar_mask(C), reference_mask(C, incidents)
    gs = golden_set(C, ref, ex)
    entries, by_key = [], {}

    def add(ten, dim, val, mask, basis, metrics=("resolution_rate", "turns_to_resolve")):
        cohort = {} if dim == "__all__" else {dim: val}
        got = []
        for m in metrics:
            e = _entry(C, ten, cohort, m, mask, ex, basis, gs.get(ten, {}).get("golden_set_version"))
            if e:
                entries.append(e)
                got.append(e)
        by_key[(ten, dim, val)] = got
        return got

    for ten in C["tenants"]:
        tm = smask(C, ten, "__all__", "__all__")
        add(ten, "__all__", "__all__", tm & ref, "own reference period", tuple(METRICS))
        for (t, dim, val) in sorted(C["slice_n"]):
            if t != ten or dim not in STANDARD_DIMS:
                continue
            if C["first_day"].get((t, dim, val), 0) >= CFG["NEWBORN_DAY"]:
                continue        # born mid-corpus: its standard is its journey peers' (below, when a finding needs it)
            add(ten, dim, val, smask(C, ten, dim, val) & ref, "own reference period")

    comparisons = {}
    for inc in incidents:
        if not inc["is_regression"] or inc["dim"] in (None, "__all__"):
            continue
        ten, dim, val = inc["tenant"], inc["dim"], inc["value"]
        key = (ten, dim, val)
        mk = smask(C, ten, dim, val)
        std = by_key.get(key)
        if not std:
            peers = []
            if dim == "intent":
                ms = C["catalog"].get("milestones", {}).get(ten, {})
                peers = [i for i, ch in sorted(ms.items()) if ms.get(val) is not None and ch == ms.get(val) and i != val]
            if peers:
                pm = np.zeros(len(day), dtype=bool)
                for p in peers:
                    pm |= smask(C, ten, "intent", p)
                std = add(ten, dim, val, pm & ref, "peers sharing the journey (%s): no before-period" % ", ".join(peers),
                          tuple(METRICS))
            else:
                std = add(ten, dim, val, mk & ref, "own reference period", tuple(METRICS))
        win = mk & (day >= inc["from"]) & (day <= inc["to"])
        n = int(win.sum())
        cur = {"resolution_rate": float(S["M"][win, S["MI"]["s.resolved"], 1].mean()) if n else None,
               "turns_to_resolve": float(S["M"][win & ex, S["MI"]["s.turns"], 1].mean()) if (win & ex).any() else None,
               "cost_per_resolved_usd": (float(np.nanmean(S["cost"][win & ex]))
                                         if (win & ex).any() and (~np.isnan(S["cost"][win & ex])).any() else None)}
        rows = []
        for e in std:
            v = cur.get(e["metric"])
            if v is None:
                continue
            gap = v - e["median"]
            row = {"metric": e["metric"], "current": round(v, 5), "standard_median": e["median"], "standard_best": e["best"],
                   "gap_to_median": round(gap, 5), "basis": e["basis"], "window": [inc["from"], inc["to"]], "n": n}
            if e["metric"] == "resolution_rate":
                row["below_standard_conversations"] = int(round(max(0.0, -gap) * n))
            elif e["metric"] == "turns_to_resolve" and e["median"]:
                row["relative_to_standard"] = round(gap / e["median"], 4)
            rows.append(row)
        comparisons[inc["id"]] = rows
    manifest = {"exemplar_definition": EXEMPLAR_DEFINITION, "reference_period": REFERENCE_DEFINITION,
                "definition_sha256": hashlib.sha256((EXEMPLAR_DEFINITION + "|" + REFERENCE_DEFINITION).encode()).hexdigest(),
                "exemplar_share": round(float(ex.mean()), 4), "reference_share": round(float(ref.mean()), 4),
                "golden_sets": gs,
                "frozen": "mined once per corpus, before any prescription is verified; nothing after this point re-mines it"}
    manifest["manifest_sha256"] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return entries, manifest, comparisons
