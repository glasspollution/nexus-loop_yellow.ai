"""Multi-resolution scanning.

A short current window detects sharp changes quickly; a long one has the power to see subtle or
gradual changes that a short window cannot separate from noise. Both run the identical test with the
identical gates. A long-window episode's onset is re-estimated by searching for the split day that
maximises the before/after statistic, so its lag is not inflated by the window length.
"""
import math

from .config import SCALES
from .detect import CFG, phi_binary, phi_cont, scan
from .loader import direction_of, is_bin


def _arrays(C, e):
    D = C["days"]
    store = C["BIN"] if is_bin(e["metric"]) else C["CONT"]
    ser = store.get((e["tenant"], e["metric"], e["dim"], e["value"]), {})
    n, s1, s2 = [0.0] * D, [0.0] * D, [0.0] * D
    for d, v in ser.items():
        n[d], s1[d] = v[0], v[1]
        if len(v) > 2:
            s2[d] = v[2]
    return n, s1, s2


def refine_onset(C, e, c):
    """Split day inside the first firing window that maximises the before/after statistic."""
    if e["mode"] != "self":
        return e["from"]
    D = C["days"]
    n, s1, s2 = _arrays(C, e)
    kind = "bin" if is_bin(e["metric"]) else "cont"
    phi = phi_binary(n, s1, D, c) if kind == "bin" else phi_cont(n, s1, s2, D, c)
    dirn = direction_of(e["metric"])
    t_end = e["from"]
    best_z, best_s = -1e18, e["from"]
    for s in range(max(1, t_end - c["CUR"] + 1), t_end + 1):
        lo = max(0, s - c["BASE"])
        n1, n0 = sum(n[s:t_end + 1]), sum(n[lo:s])
        if n1 <= 0 or n0 < c["MIN_N_BASE"]:
            continue
        m1, m0 = sum(s1[s:t_end + 1]) / n1, sum(s1[lo:s]) / n0
        if kind == "bin":
            p = (sum(s1[s:t_end + 1]) + sum(s1[lo:s])) / (n1 + n0)
            se = math.sqrt(max(p * (1 - p), 1e-12) * (1 / n1 + 1 / n0) * phi)
        else:
            v1 = max(sum(s2[s:t_end + 1]) / n1 - m1 * m1, 1e-12)
            v0 = max(sum(s2[lo:s]) / n0 - m0 * m0, 1e-12)
            se = math.sqrt((v1 / n1 + v0 / n0) * phi)
        z = dirn * (m1 - m0) / se if se > 0 else 0.0
        if z > best_z:
            best_z, best_s = z, s
    return best_s


def scan_multi(C, cfg=None, scales=SCALES):
    base = dict(CFG)
    base.update(cfg or {})
    by_series = {}
    for cur in scales:
        c = dict(base)
        c["CUR"] = cur
        for e in scan(C, c):
            e["scale"] = cur
            if cur > min(scales) and e["support_days"] < cur:
                continue    # a window of L days may only assert a change that itself lasts at least L days
            if e["mode"] == "peer":
                e["from"] = max(e["from"], C["first_day"].get((e["tenant"], e["dim"], e["value"]), 0))
            by_series.setdefault((e["tenant"], e["metric"], e["dim"], e["value"]), []).append(e)
    out = []
    for eps in by_series.values():
        # shortest scale first: where both scales see the same change, the sharper window is kept and the
        # long window only confirms it; the long window's own extent is used only when it alone fired
        eps.sort(key=lambda e: (e["scale"], e["from"]))
        merged = []
        for e in eps:
            m = next((x for x in merged if not (e["to"] < x["from"] - 3 or e["from"] > x["to"] + 3)), None)
            if m is None:
                x = dict(e)
                x["scales"] = [e["scale"]]
                merged.append(x)
                continue
            if e["scale"] == m["scale"]:
                m["from"], m["to"] = min(m["from"], e["from"]), max(m["to"], e["to"])
            m["stat"] = max(m["stat"], e["stat"])
            m["scales"] = sorted(set(m["scales"]) | {e["scale"]})
        out.extend(merged)
    return sorted(out, key=lambda e: (e["tenant"], e["from"], e["metric"]))
