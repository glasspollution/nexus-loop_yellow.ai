"""Generic scanner, stage 3: episodes -> incidents.

Every step is a question an analyst would ask of ANY anomaly, in this order:
  1. Does it have a locus?          breadth across every dimension; no locus => a global event
  2. Is a global event explained by a driver?   volume spike -> load; a measurement-version
                                    boundary -> instrument change; otherwise platform regression
  3. Is it just composition?        does it survive direct standardization?  (newborn-cohort guard)
  4. Which cohort explains it?      does it survive removing cohort X?  clustering + localization
                                    choose the smallest cohort that explains the others
  5. Which runtime layer moved, and which change aligns?   step_type of the moved metrics, then the
                                    config timeline / discovered version flips as confirmation
Benign movement (volume, mix shifts, launches, measurement boundaries, logging gaps) is emitted as
examined non-regressions, never silently dropped.

Cohort data access (masks, daily series, window tests) lives in cohorts.py; step 5 lives in diagnose.py.
"""
import math
from collections import defaultdict

import numpy as np

from .cohorts import _units, daily, fires, smask, wtest
from .detect import CFG, phi_binary, phi_cont, rel_effect
from .diagnose import BEHAVIOUR, FIX, OUTCOME, diagnose, layer
from .loader import direction_of, is_bin

STRAT_DIMS = ("intent", "agent_id", "channel", "segment")


def _uf(n):
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    return find, union


# ----------------------------------------------------------------------------- the questions

def explained(C, target, remover, c, cache):
    """Does `target`'s anomaly stop firing once `remover`'s sessions are taken out of it?"""
    if target["mode"] != "self":
        return False
    mt = smask(C, target["tenant"], target["dim"], target["value"])
    mr = smask(C, remover["tenant"], remover["dim"], remover["value"])
    if not (mt & mr).any():
        return False
    tool = target["value"] if target["dim"] == "tool" else None
    cur, base = (target["from"], target["to"]), (target["from"] - c["BASE"], target["from"] - 1)
    if target["_i"] not in cache:
        cache[target["_i"]] = wtest(C, target["metric"], mt, tool, cur, base, c)
    full = cache[target["_i"]]
    if full is None or full["bad"] <= 0:
        return False
    resid = wtest(C, target["metric"], mt & ~mr, tool, cur, base, c)
    if resid is None:
        return False            # removing it leaves too little to say anything: not evidence
    if fires(full, c):
        return not fires(resid, c)
    return resid["bad"] < 0.5 * full["bad"]


def _standardize(C, metric, mask, tool, cur, base, by, c, ten=None):
    S = C["S"]
    if by not in S["codes"]:
        return None
    a, b = max(0, cur[0]), cur[1] + 1
    lo, hi = max(0, base[0]), base[1] + 1
    if hi <= lo:
        return None
    codes = S["codes"][by]
    strata = []
    for k in np.unique(codes[mask]):
        if k < 0:
            continue
        n, s1, _ = daily(C, metric, mask & (codes == k), tool)
        nc, nb = n[a:b].sum(), n[lo:hi].sum()
        born = C["first_day"].get((ten, by, S["vocab"][by][int(k)]), 0) if ten else 0
        if born >= lo + c["NEWBORN_DAY"]:
            nb = 0.0    # did not exist for the whole baseline: a newborn stratum, never a re-weighting
        if nc or nb:
            strata.append((nc, nb, s1[a:b].sum(), s1[lo:hi].sum() if nb else 0.0))
    tc, tb = sum(x[0] for x in strata), sum(x[1] for x in strata)
    if tc < c["MIN_N_CUR"] or tb < c["MIN_N_BASE"]:
        return None
    est = [x for x in strata if x[0] > 0 and x[1] > 0]
    wb, ec = sum(x[1] for x in est), sum(x[0] for x in est)
    if not wb or not ec:
        return None
    m_base_all, m_cur_all = sum(x[3] for x in strata) / tb, sum(x[2] for x in strata) / tc
    m_base_est, m_cur_est = sum(x[3] for x in est) / wb, sum(x[2] for x in est) / ec
    std_cur = sum((x[1] / wb) * (x[2] / x[0]) for x in est)
    return {"by": by, "raw": rel_effect(m_cur_all, m_base_all),
            "raw_established": rel_effect(m_cur_est, m_base_est),
            "standardized": rel_effect(std_cur, m_base_est),
            "newborn_share": float(sum(x[0] for x in strata if x[1] == 0) / tc),
            "base": float(m_base_all), "cur": float(m_cur_all), "std_cur": float(std_cur)}


def composition(C, e, c):
    """Is this move a re-weighting of cohorts (or a newly-born cohort), not a within-cohort change?"""
    if e["mode"] != "self":
        return None
    dirn = direction_of(e["metric"])
    mask = smask(C, e["tenant"], e["dim"], e["value"])
    tool = e["value"] if e["dim"] == "tool" else None
    cur, base = (e["from"], e["to"]), (e["from"] - c["BASE"], e["from"] - 1)
    for by in STRAT_DIMS:
        if by == e["dim"]:
            continue
        r = _standardize(C, e["metric"], mask, tool, cur, base, by, c, ten=e["tenant"])
        if not r:
            continue
        raw, std_ = r["raw"] * dirn, r["standardized"] * dirn
        if raw <= 0:
            continue
        # the episode already passed materiality on its peak window; here composition only has to account
        # for the bulk of the whole-window move, whatever its size
        if r["newborn_share"] > 0.01 and r["raw_established"] * dirn < min(c["MATERIAL_REL"], 0.5 * raw):
            r["newborn"] = True
            return r
        if std_ < c["MATERIAL_REL"] and (raw - std_) >= 0.5 * raw:
            r["newborn"] = False
            return r
    return None


def _window_effect(C, key, fr, to, c):
    ser = C["BIN"].get(key) or C["CONT"].get(key)
    if not ser:
        return None
    lo = max(0, fr - c["BASE"])
    n1 = s1 = n0 = s0 = 0.0
    for d, v in ser.items():
        if fr <= d <= to:
            n1 += v[0]
            s1 += v[1]
        elif lo <= d < fr:
            n0 += v[0]
            s0 += v[1]
    if n1 < c["MIN_N_CUR"] or n0 < c["MIN_N_BASE"]:
        return None
    return rel_effect(s1 / n1, s0 / n0)


def breadth(C, E, e, sidx, c):
    """Min over dimensions of the share of sibling cohorts showing a comparable move (at least half the
    episode's effect). Counted on EFFECT SIZE, not on firing: small cohorts that lack the power to fire
    still count. A fault has a locus on some dimension; a platform event has none."""
    ten = e["tenant"]
    tot = C["slice_n"][(ten, "__all__", "__all__")]
    dirn = direction_of(e["metric"])
    target = 0.5 * e["effect"] * dirn
    if target <= 0:
        return 0.0
    fracs = []
    for d in ("intent", "agent_id", "channel", "tool"):
        vals = [v for v in sidx.get((ten, e["metric"], d), ()) if C["slice_n"].get((ten, d, v), 0) >= 0.01 * tot]
        effs = [x for x in (_window_effect(C, (ten, e["metric"], d, v), e["from"], e["to"], c) for v in vals)
                if x is not None]
        if len(effs) < 3:
            continue
        fracs.append(sum(1 for x in effs if x * dirn >= target) / len(effs))
    return min(fracs) if fracs else 0.0


def volume_events(C):
    D, out = C["days"], []
    for ten in C["tenants"]:
        vol = C["volume"].get((ten, "__all__", "__all__"), {})
        v = np.array([vol.get(d, 0) for d in range(D)], dtype=float)
        med = float(np.median(v))
        spread = max(1.4826 * float(np.median(np.abs(v - med))), 1.0)
        for kind, flag in (("spike", (v > med + 6 * spread) & (v > 1.5 * med)),
                           ("drop", (v < med - 6 * spread) & (v < 0.67 * med))):
            run, gap = [], 0
            for d in range(D + 1):
                if d < D and flag[d]:
                    run.append(d)
                    gap = 0
                    continue
                if run and d < D and gap < 2:
                    gap += 1            # a one- or two-day dip inside an event does not end it
                    continue
                if run:
                    out.append({"tenant": ten, "kind": kind, "from": run[0], "to": run[-1],
                                "ratio": float(v[run].mean() / med) if med else 0.0, "median": med})
                run, gap = [], 0
    merged = []
    for e in out:
        twin = [x for x in out if x is not e and x["kind"] == e["kind"] and x["tenant"] != e["tenant"]
                and abs(x["from"] - e["from"]) <= 1]
        if twin:
            if not any(m["tenant"] == "*" and m["kind"] == e["kind"] and abs(m["from"] - e["from"]) <= 1
                       for m in merged):
                merged.append(dict(e, tenant="*"))
        else:
            merged.append(e)
    return merged


def share_events(C, c):
    D, out = C["days"], []
    with np.errstate(invalid="ignore", divide="ignore"):
        for ten in C["tenants"]:
            tot = C["volume"].get((ten, "__all__", "__all__"), {})
            T = np.array([tot.get(d, 0) for d in range(D)], dtype=float)
            ok = T >= 50
            if ok.sum() < 10:
                continue
            for dim in STRAT_DIMS:
                for (t, d_, v), vol in C["volume"].items():
                    if t != ten or d_ != dim or C["first_day"].get((t, d_, v), 0) >= c["NEWBORN_DAY"]:
                        continue
                    x = np.array([vol.get(d, 0) for d in range(D)], dtype=float)
                    sh = np.where(ok, x / np.maximum(T, 1), np.nan)
                    med = float(np.nanmedian(sh))
                    if not (0 < med < 1):
                        continue
                    z = (sh - med) / np.sqrt(med * (1 - med) / np.maximum(T, 1))
                    phi = max(1.0, float(np.nanmedian(z[ok] ** 2)) / 0.455)
                    dev = sh - med
                    flag = ok & (np.abs(dev) >= 0.05) & (np.abs(dev) >= 0.5 * med) & \
                        (np.abs(z) / math.sqrt(phi) >= c["Z"])
                    run = []
                    for d in range(D + 1):
                        if d < D and flag[d] and (not run or np.sign(dev[d]) == np.sign(dev[run[-1]])):
                            run.append(d)
                            continue
                        if len(run) >= c["MIN_RUN"]:
                            out.append({"tenant": ten, "dim": dim, "value": v, "from": run[0], "to": run[-1],
                                        "typical": med, "during": float(np.nanmean(sh[run]))})
                        run = [d] if (d < D and flag[d]) else []
    return out


def coverage_events(C, c):
    S, D, out = C["S"], C["days"], []
    if "agent_id" not in S["codes"]:
        return out
    step_types = sorted({m.split(".")[0] for m in S["MI"] if m.endswith(".fail") and not m.startswith("s.")})
    with np.errstate(invalid="ignore", divide="ignore"):
        for ten in C["tenants"]:
            for ag in S["vocab"]["agent_id"]:
                mk = smask(C, ten, "agent_id", ag)
                if mk.sum() < 200:
                    continue
                sess = np.bincount(S["day"][mk], minlength=D).astype(float)
                for st_ in step_types:
                    n, _, _ = daily(C, st_ + ".fail", mk)
                    rate = np.where(sess >= 20, n / np.maximum(sess, 1), np.nan)
                    valid = ~np.isnan(rate)
                    if valid.sum() < 10:
                        continue
                    med = float(np.nanmedian(rate))
                    if med < 0.05:
                        continue
                    flag = valid & (rate < 0.2 * med)
                    run = []
                    for d in range(D + 1):
                        if d < D and flag[d]:
                            run.append(d)
                            continue
                        if len(run) >= c["MIN_RUN"]:
                            out.append({"tenant": ten, "agent_id": ag, "step_type": st_, "from": run[0],
                                        "to": run[-1], "typical": med, "during": float(np.nanmean(rate[run]))})
                        run = []
    return out


def evidence_lines(eps, primary=None, limit=8):
    out = []
    for e in sorted(eps, key=lambda x: (x is not primary, -x["stat"]))[:limit]:
        where = "tenant-wide" if e["dim"] == "__all__" else "%s=%s" % (e["dim"], e["value"])
        base = "sibling cohorts, same window" if e["mode"] == "peer" else "its own prior days"
        out.append("%s on %s, days %d-%d: %.4g -> %.4g (%+.0f%%, z=%.1f, baseline: %s)"
                   % (e["metric"], where, e["from"], e["to"], e["base"], e["cur"], 100 * e["effect"],
                      e["stat"], base))
    return out


def _inc(tenant, dim, value, fr, to, is_reg, cause, metrics, evidence, kind, **kw):
    d = {"tenant": tenant, "dim": dim, "value": value,
         "cohort": {} if dim in (None, "__all__") else {dim: value},
         "from": int(fr), "to": int(to), "is_regression": bool(is_reg), "cause_class": cause,
         "metrics": sorted(set(metrics)), "evidence": list(evidence), "kind": kind}
    d.update(kw)
    return d


def _compatible(a, b):
    la, lb = layer(a["metric"]), layer(b["metric"])
    return a["metric"] == b["metric"] or la == lb or "session" in (la, lb)


# ----------------------------------------------------------------------------- orchestration


def explain_strength(C, target, remover, c, cache):
    """How much of `target`'s anomaly disappears when `remover`'s sessions are taken out of it.
    0 = none. inf = the target's metric units sit (almost) entirely inside the remover, i.e. for this
    metric they are the same cohort. Never explained by the tenant aggregate: that would be vacuous."""
    if target["mode"] != "self" or remover["dim"] == "__all__":
        return 0.0
    mt = smask(C, target["tenant"], target["dim"], target["value"])
    mr = smask(C, remover["tenant"], remover["dim"], remover["value"])
    if not (mt & mr).any():
        return 0.0
    tool = target["value"] if target["dim"] == "tool" else None
    cur, base = (target["from"], target["to"]), (target["from"] - c["BASE"], target["from"] - 1)
    if target["_i"] not in cache:
        cache[target["_i"]] = wtest(C, target["metric"], mt, tool, cur, base, c)
    full = cache[target["_i"]]
    if full is None or full["bad"] <= 0:
        return 0.0
    tot = _units(C, target["metric"], mt, tool, cur[0], cur[1])
    if tot > 0 and _units(C, target["metric"], mt & mr, tool, cur[0], cur[1]) >= 0.8 * tot:
        return float("inf")
    resid = wtest(C, target["metric"], mt & ~mr, tool, cur, base, c)
    if resid is None:
        return 0.0
    if (fires(full, c) and not fires(resid, c)) or resid["bad"] < 0.5 * full["bad"]:
        return max(full["bad"] - resid["bad"], 1e-6)
    return 0.0


def build(C, E, cfg=None, trace=None):
    c = dict(CFG)
    c.update(cfg or {})
    D, S = C["days"], C["S"]
    fate = trace.setdefault("fate", {}) if trace is not None else {}
    unions_log = trace.setdefault("unions", []) if trace is not None else []
    E = [dict(e) for e in E]
    for i, e in enumerate(E):
        e["_i"] = i
    sk = lambda e: (e["tenant"], e["dim"], e["value"])
    sidx = defaultdict(set)
    for store in (C["BIN"], C["CONT"]):
        for (t, m, d, v) in store:
            sidx[(t, m, d)].add(v)
    consumed, out = set(), []
    vol_ev = volume_events(C)
    used_vol = set()

    # ---------- 1-2. events with no locus ----------
    bre = {e["_i"]: breadth(C, E, e, sidx, c) for e in E}
    groups = []
    for e in sorted((x for x in E if bre[x["_i"]] >= c.get("GLOBAL_BREADTH", 0.6)), key=lambda x: x["from"]):
        g = next((g for g in groups if g["tenant"] == e["tenant"]
                  and not (e["to"] < g["from"] - 2 or e["from"] > g["to"] + 2)), None)
        if g:
            g["metrics"].add(e["metric"])
            g["from"], g["to"] = min(g["from"], e["from"]), max(g["to"], e["to"])
            g["onset"] = g["from"]
        else:
            groups.append({"tenant": e["tenant"], "onset": e["from"], "from": e["from"], "to": e["to"],
                           "metrics": {e["metric"]}})
    glob = []
    judged_requires = {fd.get("requires") for fd in C["catalog"].get("fields", {}).values()
                       if fd.get("fidelity") == "judged" and fd.get("requires")}
    for g in groups:
        mem = [x for x in E if x["tenant"] == g["tenant"] and x["metric"] in g["metrics"]
               and not (x["to"] < g["from"] - 2 or x["from"] > g["to"] + 2) and x["_i"] not in consumed]
        if not mem:
            continue
        ids = {x["_i"] for x in mem}
        spike = next((k for k, v in enumerate(vol_ev) if v["kind"] == "spike" and v["tenant"] in (g["tenant"], "*")
                      and not (v["to"] < g["from"] - 2 or v["from"] > g["to"] + 2)), None)
        if spike is not None:
            sp = vol_ev[spike]

            def outside_driver(x):
                # does any part of this deviation that falls OUTSIDE the volume event carry a change of its own?
                mk = smask(C, x["tenant"], x["dim"], x["value"])
                tool = x["value"] if x["dim"] == "tool" else None
                start = min(x["from"], sp["from"])
                ref = (start - c["BASE"], start - 1)
                parts = []
                if x["from"] <= sp["from"] - 3:
                    parts.append((x["from"], sp["from"] - 1))
                if x["to"] >= sp["to"] + 3:
                    parts.append((sp["to"] + 1, x["to"]))
                return any(fires(wtest(C, x["metric"], mk, tool, part, ref, c), c) for part in parts)

            extra = [x for x in E if x["tenant"] == g["tenant"] and x["_i"] not in consumed and x["_i"] not in ids
                     and not (x["to"] < sp["from"] - 2 or x["from"] > sp["to"] + 2) and not outside_driver(x)]
            mem += extra
            ids |= {x["_i"] for x in extra}
            outlives = [x for x in mem if outside_driver(x)]
            outcome = [x for x in mem if x["metric"] in OUTCOME]
            if not outlives and not outcome:
                used_vol.add(spike)
                r = wtest(C, "s.resolved", smask(C, g["tenant"], "__all__", "__all__"), None,
                          (sp["from"], sp["to"]), (sp["from"] - c["BASE"], sp["from"] - 1), c)
                moved = sorted({x["metric"] for x in mem})
                txt = ("Traffic ran %.1fx its typical daily volume on days %d-%d, and %s moved with it across "
                       "every cohort at once - there is no locus. Resolution went %s, and no outcome metric fired. "
                       "Every co-moving deviation ended within 3 days of volume returning to normal, so nothing "
                       "outlives its driver. This is a capacity / reliability event for the platform view, not a "
                       "quality regression."
                       % (sp["ratio"], sp["from"], sp["to"], ", ".join(moved),
                          ("%.4f -> %.4f" % (r["m0"], r["m1"])) if r else "unmeasurable"))
                glob.append(_inc(g["tenant"], "__all__", "__all__", min(x["from"] for x in mem),
                                 max(x["to"] for x in mem), False, "load", moved, evidence_lines(mem), "load",
                                 not_a_regression_because=txt, audience=["platform_owner"], confidence=0.9))
                for x in mem:
                    fate[x["_i"]] = "global:load"
                consumed |= ids
                continue
        flip = next((f for f in C["global_flips"] if abs(f["day"] - g["onset"]) <= 1), None)
        if flip is not None and flip["field"] in judged_requires and \
                all(x["metric"].startswith("s.quality_score") for x in mem):
            glob.append(_inc(g["tenant"], "__all__", "__all__", flip["day"], D - 1, False, "judge_change",
                             [x["metric"] for x in mem], evidence_lines(mem), "instrument_boundary",
                             not_a_regression_because="moves only on a judged metric at a global judge boundary",
                             confidence=0.9))
            for x in mem:
                fate[x["_i"]] = "global:instrument"
            consumed |= ids
            continue
        primary = max(mem, key=lambda x: x["stat"])
        dg = diagnose(C, mem, primary, c)
        glob.append(_inc(g["tenant"], "__all__", "__all__", min(x["from"] for x in mem), max(x["to"] for x in mem),
                         True, dg["cause"], [x["metric"] for x in mem], evidence_lines(mem, primary), "platform",
                         confidence=dg["confidence"], attributed_change=dg["attributed_change"],
                         audience=["platform_owner"], baseline_mode="self", primary=primary,
                         diagnosis_notes=dg["notes"] + ["no locus on any dimension: platform-wide"]))
        for x in mem:
            fate[x["_i"]] = "global:platform"
        consumed |= ids
    merged = []
    for inc in glob:
        twin = next((m for m in merged if m["kind"] == inc["kind"] and m["tenant"] != inc["tenant"]
                     and abs(m["from"] - inc["from"]) <= 1), None)
        if twin:
            twin["tenant"] = "*"
            twin["metrics"] = sorted(set(twin["metrics"]) | set(inc["metrics"]))
            twin["evidence"] += inc["evidence"]
        else:
            merged.append(inc)
    out += merged

    # ---------- 3. composition ----------
    newborn = [e for e in E if e["mode"] == "peer"]
    comp_links, comp_groups = [], []
    for e in E:
        if e["_i"] in consumed:
            continue
        r = composition(C, e, c)
        if not r:
            continue
        if r.get("newborn"):
            nb = [x for x in newborn if x["tenant"] == e["tenant"] and x["dim"] == r["by"]
                  and not (x["to"] < e["from"] - 3 or x["from"] > e["to"] + 3)]
            if nb:
                comp_links.append((nb[0]["_i"], e["_i"]))
            fate[e["_i"]] = "newborn-driven (link to %s)" % (nb[0]["_i"] if nb else None)
            continue
        fate[e["_i"]] = "composition by %s raw=%+.2f std=%+.2f" % (r["by"], r["raw"], r["standardized"])
        consumed.add(e["_i"])
        e["_comp"] = r
        g = next((g for g in comp_groups if g["tenant"] == e["tenant"]
                  and not (g["to"] < e["from"] - 3 or g["from"] > e["to"] + 3)), None)
        if g:
            g["eps"].append(e)
            g["from"], g["to"] = min(g["from"], e["from"]), max(g["to"], e["to"])
        else:
            comp_groups.append({"tenant": e["tenant"], "from": e["from"], "to": e["to"], "eps": [e]})

    # ---------- 4. explanation forest ----------
    # Every episode is either a ROOT (removing no other cohort explains it) or is explained by removing
    # another cohort. Roots on the same cohort form one incident; explained episodes attach to the root
    # that explains them most strongly. Leakage can therefore never bridge two different faults.
    rem = [e for e in E if e["_i"] not in consumed]
    idx = {e["_i"]: k for k, e in enumerate(rem)}
    R = len(rem)
    xcache = {}
    expl = [dict() for _ in range(R)]
    for a_i, b_i in comp_links:
        if a_i in idx and b_i in idx:
            expl[idx[b_i]][idx[a_i]] = float("inf")
    for i in range(R):
        a = rem[i]
        for j in range(R):
            b = rem[j]
            if i == j or a["tenant"] != b["tenant"] or sk(a) == sk(b):
                continue
            if a["to"] < b["from"] - 3 or b["to"] < a["from"] - 3 or not _compatible(a, b):
                continue
            s_ = explain_strength(C, a, b, c, xcache)
            if s_ > 0:
                expl[i][j] = max(expl[i].get(j, 0.0), s_)
                unions_log.append((a["_i"], b["_i"], "explained by removing it (strength %s)"
                                   % ("inf" if math.isinf(s_) else "%.1f" % s_)))
    find, union = _uf(R)
    for i in range(R):
        for j in expl[i]:
            if i in expl[j]:
                union(i, j)
    classes = defaultdict(list)
    for i in range(R):
        classes[find(i)].append(i)
    cls_of = {i: find(i) for i in range(R)}
    ext, is_root = {}, {}
    for cid, mem in classes.items():
        ext[cid] = {}
        for i in mem:
            for j, s_ in expl[i].items():
                if cls_of[j] != cid:
                    ext[cid][j] = max(ext[cid].get(j, 0.0), s_)
        is_root[cid] = any(all(cls_of[j] == cid for j in expl[i]) for i in mem)

    def root_of(cid, seen):
        if is_root[cid]:
            return cid
        seen.add(cid)
        for j in sorted(ext[cid], key=lambda x: -ext[cid][x]):
            if cls_of[j] not in seen:
                r = root_of(cls_of[j], seen)
                if r is not None:
                    return r
        return None

    roots = [cid for cid in classes if is_root[cid]]
    rpos = {cid: k for k, cid in enumerate(roots)}
    gfind, gunion = _uf(len(roots))
    for x in range(len(roots)):
        ax = [rem[i] for i in classes[roots[x]]]
        for y in range(x + 1, len(roots)):
            by = [rem[i] for i in classes[roots[y]]]
            if any(sk(p_) == sk(q_) and not (p_["to"] < q_["from"] - 3 or q_["to"] < p_["from"] - 3)
                   for p_ in ax for q_ in by):
                gunion(x, y)
    groups_r = defaultdict(list)
    for cid in roots:
        groups_r[("root", gfind(rpos[cid]))].append(cid)
    attach = defaultdict(list)
    for cid in classes:
        if is_root[cid]:
            continue
        r = root_of(cid, set())
        if r is None:
            groups_r[("orphan", cid)].append(cid)
        else:
            attach[("root", gfind(rpos[r]))].append(cid)

    primaries = set()
    for g, cids in groups_r.items():
        root_eps = [rem[i] for cid in cids for i in classes[cid]]
        att_eps = [rem[i] for cid in attach.get(g, []) for i in classes[cid]]
        eps = root_eps + att_eps
        slices = {sk(e) for e in root_eps if e["dim"] != "__all__"}
        if not slices:
            for e in eps:
                fate[e["_i"]] = "unlocalized aggregate"
            out.append(_inc(eps[0]["tenant"], "__all__", "__all__", min(e["from"] for e in eps),
                            max(e["to"] for e in eps), False, "unknown", [e["metric"] for e in eps],
                            evidence_lines(eps), "unlocalized",
                            not_a_regression_because=(
                                "The tenant aggregate moved, but no cohort on any dimension carries the change and "
                                "it is not platform-wide. An aggregate shift with no locus is most often composition "
                                "or measurement drift, so it is flagged for human review rather than asserted as a "
                                "regression."), audience=["platform_owner"], confidence=0.4))
            continue
        tool_layer = any(layer(e["metric"]) == "tool_call" for e in root_eps)
        pk = min(slices, key=lambda s2: ((s2[1] == "tool") != tool_layer, C["slice_n"].get(s2, 10 ** 9),
                                          -max(e["stat"] for e in root_eps if sk(e) == s2)))
        primary = max((e for e in root_eps if sk(e) == pk), key=lambda e: e["stat"])
        primaries.add(pk)
        own = [e for e in root_eps if sk(e) == pk]
        for e in root_eps:
            fate[e["_i"]] = "root; incident primary=%s=%s" % (pk[1], pk[2])
        for e in att_eps:
            fate[e["_i"]] = "explained; attached to incident primary=%s=%s" % (pk[1], pk[2])
        dg = diagnose(C, root_eps, primary, c)
        out.append(_inc(primary["tenant"], primary["dim"], primary["value"], min(e["from"] for e in own),
                        max(e["to"] for e in own), True, dg["cause"], [e["metric"] for e in eps],
                        evidence_lines(eps, primary), "regression", confidence=dg["confidence"],
                        attributed_change=dg["attributed_change"], audience=dg["audience"],
                        baseline_mode=primary["mode"], primary=primary, diagnosis_notes=dg["notes"],
                        explains=sorted({"%s=%s" % (e["dim"], e["value"]) for e in eps if sk(e) != pk})))

    # ---------- 5. examined non-regressions ----------
    shares = share_events(C, c)
    for g in comp_groups:
        tw = next((s for s in shares if s["tenant"] == g["tenant"]
                   and not (s["to"] < g["from"] - 3 or s["from"] > g["to"] + 3)), None)
        r = g["eps"][0]["_comp"]
        line = ("re-weighting by %s explains the move: raw %+.1f%%, mix-standardized %+.1f%%"
                % (r["by"], 100 * r["raw"], 100 * r["standardized"]))
        if tw:
            tw.setdefault("composition", []).append(line)
            tw.setdefault("episodes", []).extend(g["eps"])
            continue
        out.append(_inc(g["tenant"], "__all__", "__all__", g["from"], g["to"], False, "traffic_mix",
                        [e["metric"] for e in g["eps"]], evidence_lines(g["eps"]) + [line], "composition",
                        not_a_regression_because=(
                            "These metrics moved only because the mix of traffic changed: %s. Within every "
                            "established cohort the rates did not move materially." % line), confidence=0.85))
    for s in shares:
        tm = smask(C, s["tenant"], "__all__", "__all__")
        r = _standardize(C, "s.resolved", tm, None, (s["from"], s["to"]), (s["from"] - 14, s["from"] - 1),
                         s["dim"], c, ten=s["tenant"]) or _standardize(C, "s.resolved", tm, None, (s["from"], s["to"]),
                                                      (s["to"] + 1, min(D - 1, s["to"] + 14)), s["dim"], c, ten=s["tenant"])
        eff = ("tenant resolution moved %+.2f%% raw but %+.2f%% once re-weighted to the baseline %s mix"
               % (100 * r["raw"], 100 * r["standardized"], s["dim"])) if r else "aggregate effect not measurable"
        ev = ["%s=%s share of %s traffic: typical %.3f, during %.3f" % (s["dim"], s["value"], s["tenant"],
                                                                       s["typical"], s["during"]), eff]
        ev += s.get("composition", [])
        out.append(_inc(s["tenant"], s["dim"], s["value"], s["from"], s["to"], False, "traffic_mix",
                        ["share:%s" % s["dim"]], ev, "mix_shift",
                        not_a_regression_because=(
                            "The share of traffic from %s=%s moved from a typical %.1f%% to %.1f%% for days %d-%d. "
                            "That changes aggregates without anything getting better or worse: %s. Stratify by %s "
                            "before reading any tenant-level trend over this window."
                            % (s["dim"], s["value"], 100 * s["typical"], 100 * s["during"], s["from"], s["to"],
                               eff, s["dim"])), confidence=0.85))
    for k, v in enumerate(vol_ev):
        if k in used_vol:
            continue
        out.append(_inc(v["tenant"], "__all__", "__all__", v["from"], v["to"], False, "load", ["volume"],
                        ["daily sessions %.0f typical, %.2fx during days %d-%d" % (v["median"], v["ratio"],
                                                                                  v["from"], v["to"])],
                        "volume_" + v["kind"],
                        not_a_regression_because=(
                            "Traffic volume %s to %.2fx its typical level on days %d-%d with no cohort-level "
                            "quality or latency movement attached. Volume is not quality."
                            % ("rose" if v["kind"] == "spike" else "fell", v["ratio"], v["from"], v["to"])),
                        confidence=0.8))
    for (ten, dim, val), fd in C["first_day"].items():
        if dim == "__all__" or fd < c["NEWBORN_DAY"] or C["slice_n"][(ten, dim, val)] < 100 or \
                (ten, dim, val) in primaries:
            continue
        mk, tm = smask(C, ten, dim, val), smask(C, ten, "__all__", "__all__")
        life = S["day"] >= fd
        k = S["MI"]["s.resolved"]
        a, b = S["M"][mk & life, k, :], S["M"][tm & ~mk & life, k, :]
        ra, rb = a[:, 1].sum() / max(1, a[:, 0].sum()), b[:, 1].sum() / max(1, b[:, 0].sum())
        out.append(_inc(ten, dim, val, fd, D - 1, False, "traffic_mix", ["launch"],
                        ["first seen on day %d; %d sessions; resolution %.3f vs %.3f for the rest of the tenant"
                         % (fd, C["slice_n"][(ten, dim, val)], ra, rb)], "launch",
                        not_a_regression_because=(
                            "%s=%s did not exist before day %d, so it has no history to regress from; compared with "
                            "its siblings over the same days, no mechanism or outcome metric fired."
                            % (dim, val, fd)), confidence=0.7))
    for f in C["global_flips"]:
        if f["field"] not in judged_requires:
            continue
        qms = sorted(m for m in S["MI"] if m.startswith("s.quality_score@"))
        lines = []
        for ten in C["tenants"]:
            tm = smask(C, ten, "__all__", "__all__")

            def mean(lo, hi):
                w = tm & (S["day"] >= lo) & (S["day"] < hi)
                n = sum(S["M"][w, S["MI"][m], 0].sum() for m in qms)
                return sum(S["M"][w, S["MI"][m], 1].sum() for m in qms) / n if n else float("nan")

            b_, a_ = mean(f["day"] - 10, f["day"]), mean(f["day"], f["day"] + 10)
            lines.append("%s: judged quality %.3f -> %.3f (%+.3f) if pooled naively across the boundary"
                         % (ten, b_, a_, a_ - b_))
        out.append(_inc("*", "__all__", "__all__", f["day"], D - 1, False, "judge_change", qms,
                        ["%s flips %s -> %s on day %d for %d agents across every tenant"
                         % (f["field"], f["from"], f["to"], f["day"], f["agents"])] + lines,
                        "instrument_boundary",
                        not_a_regression_because=(
                            "%s - the version of the instrument that produces judged scores - changes on day %d for "
                            "every agent on every tenant at once. Judged metrics are comparable only within one "
                            "version, so any trend across this day measures the rubric, not the agents. The scanner "
                            "never compares judged values across it; the naive pooled trend is shown only to make "
                            "the size of the trap visible." % (f["field"], f["day"])), confidence=0.95))
    for ev in coverage_events(C, c):
        out.append(_inc(ev["tenant"], "agent_id", ev["agent_id"], ev["from"], ev["to"], False, "unknown",
                        ["coverage:%s" % ev["step_type"]],
                        ["%s steps per session on agent %s: typical %.2f, during %.2f"
                         % (ev["step_type"], ev["agent_id"], ev["typical"], ev["during"])], "coverage_gap",
                        not_a_regression_because=(
                            "Agent %s stopped emitting %s steps on days %d-%d. That is a logging / instrumentation "
                            "change: metrics derived from those steps lose coverage for this agent, which must be "
                            "stated, but it is not evidence of worse service." % (ev["agent_id"], ev["step_type"],
                                                                                  ev["from"], ev["to"])),
                        confidence=0.7))

    out.sort(key=lambda i: (not i["is_regression"], i["from"]))
    for k, inc in enumerate(out, 1):
        inc["id"] = "i%d" % k
    return out
