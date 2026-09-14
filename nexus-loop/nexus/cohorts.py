"""Cohort data access over the per-session arrays built by the loader.

These are the primitives behind every counterfactual question in stage 3: a boolean mask for a cohort,
its daily (n, sum, sum of squares) series, and the overdispersion-adjusted window test that decides
whether an anomaly still fires once some sessions are removed or re-weighted.
"""
import math

import numpy as np

from .detect import phi_binary, phi_cont, rel_effect
from .loader import direction_of, is_bin


def smask(C, ten, dim, val):
    cache = C.setdefault("_mask_cache", {})
    key = (ten, dim, val)
    if key in cache:
        return cache[key]
    S = C["S"]
    tm = np.ones(len(S["day"]), dtype=bool) if ten == "*" else (S["ten"] == S["tenant_index"][ten])
    if dim in (None, "__all__"):
        mk = tm
    elif dim == "tool":
        t = S["tool_mask"].get(val)
        mk = (tm & t) if t is not None else np.zeros_like(tm)
    else:
        vocab = S["vocab"].get(dim, [])
        mk = (tm & (S["codes"][dim] == vocab.index(val))) if val in vocab else np.zeros_like(tm)
    cache[key] = mk
    return mk


def daily(C, metric, mask, tool=None):
    S, D = C["S"], C["days"]
    z = np.zeros(D)
    if tool is not None and metric in S["TMI"] and tool in S["TM"]:
        idxs, arr = S["TM"][tool]
        sel = mask[idxs]
        dd, W = S["day"][idxs][sel], arr[sel, S["TMI"][metric], :]
    elif metric in S["MI"]:
        dd, W = S["day"][mask], S["M"][mask, S["MI"][metric], :]
    else:
        return z, z, z
    if len(dd) == 0:
        return z, z, z
    return tuple(np.bincount(dd, weights=W[:, k], minlength=D) for k in range(3))


def wtest(C, metric, mask, tool, cur, base, c):
    kind = "bin" if is_bin(metric) else "cont"
    n, s1, s2 = daily(C, metric, mask, tool)
    lo, hi = max(0, base[0]), base[1] + 1
    a, b = max(0, cur[0]), cur[1] + 1
    if hi <= lo or b <= a:
        return None
    n1, n0 = n[a:b].sum(), n[lo:hi].sum()
    if n1 < c["MIN_N_CUR"] or n0 < c["MIN_N_BASE"]:
        return None
    m1, m0 = s1[a:b].sum() / n1, s1[lo:hi].sum() / n0
    D = C["days"]
    phi = phi_binary(n, s1, D, c) if kind == "bin" else phi_cont(n, s1, s2, D, c)
    if kind == "bin":
        p = (s1[a:b].sum() + s1[lo:hi].sum()) / (n1 + n0)
        se = math.sqrt(max(p * (1 - p), 1e-12) * (1 / n1 + 1 / n0) * phi)
    else:
        v1 = max(s2[a:b].sum() / n1 - m1 * m1, 1e-12)
        v0 = max(s2[lo:hi].sum() / n0 - m0 * m0, 1e-12)
        se = math.sqrt((v1 / n1 + v0 / n0) * phi)
    z = (m1 - m0) / se if se > 0 else 0.0
    return {"kind": kind, "bad": float(z) * direction_of(metric), "m1": float(m1), "m0": float(m0),
            "n1": float(n1), "n0": float(n0)}


def fires(r, c):
    if r is None or r["bad"] <= c["Z"]:
        return False
    if abs(rel_effect(r["m1"], r["m0"])) < c["MATERIAL_REL"]:
        return False
    if r["kind"] == "bin" and abs(r["m1"] - r["m0"]) < c["MATERIAL_ABS"]:
        return False
    return True


def _units(C, metric, mask, tool, lo, hi):
    n, _, _ = daily(C, metric, mask, tool)
    return float(n[max(0, lo):hi + 1].sum())
