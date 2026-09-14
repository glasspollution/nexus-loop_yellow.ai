"""Generic scanner, stage 2: one uniform changepoint test over every (metric x slice) series.

No per-fault detectors. The same test runs on all ~1,400 series:
  * cohorts WITH history are compared to their own past (self baseline). Once a series starts to
    fire, its baseline is FROZEN at the pre-change period, so a long fault cannot be absorbed into a
    rolling baseline and appear to end early;
  * cohorts BORN mid-corpus have no past, so they are compared to their siblings over the same days,
    with the siblings' natural spread (tau) added to the noise, so a permanently-different-but-normal
    cohort does not fire;
  * every statistic is inflated by the series' own measured overdispersion (phi);
  * an episode needs significance AND materiality in consecutive windows, AND at least MIN_RUN
    individual days that each show the move (day-level support) - so one outlier day, which stays
    inside a trailing window for several days, cannot masquerade as a persistent change.
"""
import math
import statistics as st
from collections import defaultdict

from .config import CFG  # noqa: F401  (re-exported; parameters live in config.py)
from .loader import DIRECTION


def _prefix(a):
    p = [0.0]
    for x in a:
        p.append(p[-1] + x)
    return p


def _w(p, lo, hi):
    lo = max(0, lo)
    hi = max(lo, hi)
    return p[hi] - p[lo]


def _arrays(series, D, width):
    cols = [[0.0] * D for _ in range(width)]
    for d, vals in series.items():
        if 0 <= d < D:
            for i in range(width):
                cols[i][d] = vals[i]
    return cols


def phi_binary(n, k, D, c):
    rates = [(k[d] / n[d]) if n[d] >= c["DAY_MIN_N"] else None for d in range(D)]
    res = []
    W = c["PHI_WINDOW"]
    for d in range(D):
        if rates[d] is None:
            continue
        nb = [rates[x] for x in range(max(0, d - W), min(D, d + W + 1)) if x != d and rates[x] is not None]
        if len(nb) < 4:
            continue
        med = st.median(nb)
        p = min(max(med, 1e-4), 1 - 1e-4)
        res.append((rates[d] - med) ** 2 / (p * (1 - p) / n[d]))
    return max(1.0, st.median(res) / 0.455) if len(res) >= 8 else 1.0


def phi_cont(n, s1, s2, D, c):
    means = [(s1[d] / n[d]) if n[d] >= c["DAY_MIN_N"] else None for d in range(D)]
    res = []
    W = c["PHI_WINDOW"]
    for d in range(D):
        if means[d] is None:
            continue
        var = max(s2[d] / n[d] - means[d] ** 2, 1e-12)
        nb = [means[x] for x in range(max(0, d - W), min(D, d + W + 1)) if x != d and means[x] is not None]
        if len(nb) < 4:
            continue
        res.append((means[d] - st.median(nb)) ** 2 / (var / n[d]))
    return max(1.0, st.median(res) / 0.455) if len(res) >= 8 else 1.0


def rel_effect(cur, base):
    if abs(base) < 1e-9:
        return 1.0 if cur > 1e-9 else 0.0
    return (cur - base) / abs(base)


def _material(kind, cur, base, c):
    if abs(rel_effect(cur, base)) < c["MATERIAL_REL"]:
        return False
    if kind == "bin" and abs(cur - base) < c["MATERIAL_ABS"]:
        return False
    return True


def _peer_tau(slice_means):
    vals = [v for v in slice_means if v is not None]
    if len(vals) < 3:
        return None
    med = st.median(vals)
    return 1.4826 * st.median([abs(v - med) for v in vals])


def _stat(kind, n1, s1, q1, n0, s0, q0, phi, tau=None):
    m1, m0 = s1 / n1, s0 / n0
    if kind == "bin":
        if tau is None:
            p = (s1 + s0) / (n1 + n0)
            var = max(p * (1 - p), 1e-12) * (1 / n1 + 1 / n0) * phi
        else:
            var = (max(m1 * (1 - m1), 1e-12) / n1 + max(m0 * (1 - m0), 1e-12) / n0) * phi + tau ** 2
    else:
        v1 = max(q1 / n1 - m1 * m1, 1e-12)
        v0 = max(q0 / n0 - m0 * m0, 1e-12)
        var = (v1 / n1 + v0 / n0) * phi + (tau ** 2 if tau is not None else 0.0)
    return m1, m0, ((m1 - m0) / math.sqrt(var) if var > 0 else 0.0)


def scan(C, cfg=None):
    c = dict(CFG)
    c.update(cfg or {})
    D = C["days"]
    episodes = []
    groups = defaultdict(list)
    for kind, store in (("bin", C["BIN"]), ("cont", C["CONT"])):
        for key in store:
            groups[(key[0], key[1], key[2], kind)].append(key)

    for (ten, metric, dim, kind), keys in groups.items():
        direction = DIRECTION[metric]
        if direction == 0:
            continue
        store = C["BIN"] if kind == "bin" else C["CONT"]
        width = 2 if kind == "bin" else 3
        arr = {key: _arrays(store[key], D, width) for key in keys}
        pre = {key: [_prefix(col) for col in arr[key]] for key in keys}
        levels = []
        for key in keys:
            tot_n = sum(arr[key][0])
            levels.append((sum(arr[key][1]) / tot_n) if tot_n >= 200 else None)
        tau = _peer_tau(levels) if dim != "__all__" else None
        sib = sibp = None
        if tau is not None:
            sib = [[sum(arr[k][i][d] for k in keys) for d in range(D)] for i in range(width)]
            sibp = [_prefix(col) for col in sib]

        for key in keys:
            a, p = arr[key], pre[key]
            phi = phi_binary(a[0], a[1], D, c) if kind == "bin" else phi_cont(a[0], a[1], a[2], D, c)
            newborn = (tau is not None and dim != "__all__"
                       and C["first_day"].get((ten, dim, key[3]), 0) >= c["NEWBORN_DAY"])

            def evaluate(t, frozen):
                lo_c, hi_c = t - c["CUR"] + 1, t + 1
                n1 = _w(p[0], lo_c, hi_c)
                if n1 < c["MIN_N_CUR"]:
                    return None
                s1 = _w(p[1], lo_c, hi_c)
                q1 = _w(p[2], lo_c, hi_c) if kind == "cont" else 0.0
                if newborn:
                    n0 = _w(sibp[0], lo_c, hi_c) - n1
                    if n0 < c["MIN_N_BASE"]:
                        return None
                    s0 = _w(sibp[1], lo_c, hi_c) - s1
                    q0 = (_w(sibp[2], lo_c, hi_c) - q1) if kind == "cont" else 0.0
                    m1, m0, z = _stat(kind, n1, s1, q1, n0, s0, q0, phi, tau)
                    base = ("peer",)
                else:
                    if frozen is None:
                        lo_b, hi_b = max(0, lo_c - c["BASE"]), lo_c
                    else:
                        lo_b, hi_b = frozen[1], frozen[2]
                    if hi_b <= 0:
                        return None
                    n0 = _w(p[0], lo_b, hi_b)
                    days_b = sum(1 for d in range(max(0, lo_b), hi_b) if a[0][d] > 0)
                    if days_b < c["BASE_MIN_DAYS"] or n0 < c["MIN_N_BASE"]:
                        return None
                    s0 = _w(p[1], lo_b, hi_b)
                    q0 = _w(p[2], lo_b, hi_b) if kind == "cont" else 0.0
                    m1, m0, z = _stat(kind, n1, s1, q1, n0, s0, q0, phi)
                    base = ("self", lo_b, hi_b)
                bad = z * direction
                return {"t": t, "fires": bad > c["Z"] and _material(kind, m1, m0, c), "bad": bad,
                        "m1": m1, "m0": m0, "base": base, "n1": n1}

            t = 0
            while t < D:
                r = evaluate(t, None)
                if r is None or not r["fires"]:
                    t += 1
                    continue
                run, t2 = [r], t + 1
                while t2 < D:
                    r2 = evaluate(t2, r["base"])
                    if r2 is not None and r2["fires"]:
                        run.append(r2)
                        t2 += 1
                        continue
                    r3 = evaluate(t2 + 1, r["base"]) if t2 + 1 < D else None
                    if r3 is not None and r3["fires"]:      # tolerate one quiet window inside a change
                        run.append(r3)
                        t2 += 2
                        continue
                    break
                first = run[0]
                strongest = max(run, key=lambda x: x["bad"])
                # a supporting day must carry at least half of the change at its clearest, so a sharp event
                # keeps a tight window and ordinary noise days next to it are not counted as the change
                need = c["SUPPORT_FRAC"] * direction * (strongest["m1"] - strongest["m0"])
                support = []
                for d in range(max(0, first["t"] - c["CUR"] + 1), run[-1]["t"] + 1):
                    nd = a[0][d]
                    if nd < c["DAY_MIN_N"]:
                        continue
                    if newborn:
                        ns = sib[0][d] - nd
                        if ns < c["DAY_MIN_N"]:
                            continue
                        ref = (sib[1][d] - a[1][d]) / ns
                    else:
                        ref = first["m0"]
                    move = direction * (a[1][d] / nd - ref)
                    if move > 0 and move >= need:
                        support.append(d)
                if len(run) >= c["MIN_RUN"] and len(support) >= c["MIN_RUN"]:
                    peak = max(run, key=lambda x: x["bad"])
                    episodes.append({
                        "tenant": ten, "metric": metric, "dim": dim, "value": key[3], "kind": kind,
                        "from": support[0], "to": support[-1], "stat": round(peak["bad"], 2),
                        "effect": round(rel_effect(peak["m1"], peak["m0"]), 4),
                        "cur": round(first["m1"], 5), "base": round(first["m0"], 5),
                        "mode": "peer" if newborn else "self", "phi": round(phi, 2),
                        "tau": (round(tau, 5) if tau else None), "n_cur": int(first["n1"]),
                        "support_days": len(support), "run": len(run)})
                t = t2
    return sorted(episodes, key=lambda e: (e["tenant"], e["from"], e["metric"]))
