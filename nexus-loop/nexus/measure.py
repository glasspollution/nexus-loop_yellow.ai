"""Window arithmetic shared by evidence, impact and standards: one stated window per displayed number.

The scanner's statistics (first firing window, peak window, frozen baseline) are the right tools for DETECTING a
change, but they are three different periods and must never be printed side by side. Everything an operator reads
is recomputed here over explicit, inclusive day ranges, so the before, the after and the change always agree.
"""
import numpy as np

from .cohorts import daily, smask
from .config import CFG
from .loader import is_bin


def cohort_parts(C, metric, tenant, dim, value):
    """Daily (n, sum, sum of squares) of `metric` for one cohort. A tool cohort's tool metrics use that tool's calls."""
    tool = value if dim == "tool" else None
    return daily(C, metric, smask(C, tenant, dim, value), tool)


def peer_parts(C, metric, tenant, dim, value):
    """Daily series of the cohort's siblings: the other values of the same dimension on the same tenant."""
    S = C["S"]
    tm = smask(C, tenant, "__all__", "__all__")
    if dim == "tool" and metric in S["TMI"]:
        tot = [np.zeros(C["days"]) for _ in range(3)]
        for t in S["TM"]:
            if t != value:
                for k, part in enumerate(daily(C, metric, tm, t)):
                    tot[k] += part
        return tuple(tot)
    if dim in S["codes"]:
        return daily(C, metric, tm & (S["codes"][dim] >= 0) & ~smask(C, tenant, dim, value))
    return daily(C, metric, tm & ~smask(C, tenant, dim, value))


def mean_of(parts, lo, hi):
    """(mean, units) over the inclusive day range [lo, hi]; mean is None when there are no units."""
    D = len(parts[0])
    lo, hi = max(0, int(lo)), min(D - 1, int(hi))
    if hi < lo:
        return None, 0
    n = float(parts[0][lo:hi + 1].sum())
    return (float(parts[1][lo:hi + 1].sum()) / n if n > 0 else None), int(n)


def fmt_value(metric, v):
    if v is None:
        return "n/a"
    if is_bin(metric):
        return "%.2f%%" % (100.0 * v)
    if metric.endswith("cost_usd"):
        return "$%.4f" % v
    return "%.4g" % v


def change(metric, cur, base):
    """Absolute and relative change with the units a reader expects; a zero baseline has no relative change."""
    if cur is None or base is None:
        return {"abs": None, "rel": None, "text": "not measurable"}
    d = cur - base
    if abs(base) < 1e-12:
        return {"abs": d, "rel": None, "text": "absent before (0), now %s" % fmt_value(metric, cur)}
    rel = d / abs(base)
    if is_bin(metric):
        return {"abs": d, "rel": rel, "text": "%+.2f percentage points (%+.0f%% relative)" % (100 * d, 100 * rel)}
    return {"abs": d, "rel": rel, "text": "%+.4g (%+.0f%%)" % (d, 100 * rel)}


def compare(C, metric, tenant, dim, value, lo, hi, mode="self", base_days=None):
    """Cohort value over [lo, hi] against a stated baseline: its own previous days, or its siblings on the same days."""
    base_len = base_days or CFG["BASE"]
    cur, n1 = mean_of(cohort_parts(C, metric, tenant, dim, value), lo, hi)
    if mode == "peer" and dim != "__all__":
        base, n0 = mean_of(peer_parts(C, metric, tenant, dim, value), lo, hi)
        bkind, blo, bhi = "its sibling cohorts", lo, hi
    else:
        blo, bhi = max(0, lo - base_len), lo - 1
        base, n0 = mean_of(cohort_parts(C, metric, tenant, dim, value), blo, bhi)
        bkind = "the same slice"
    return {"metric": metric, "tenant": tenant, "dim": dim, "value": value, "from": int(lo), "to": int(hi),
            "current": cur, "n_current": n1, "baseline": base, "n_baseline": n0, "baseline_kind": bkind,
            "baseline_days": [int(blo), int(bhi)], "change": change(metric, cur, base)}


def where_label(dim, value):
    return "tenant-wide" if dim in (None, "__all__") else "%s=%s" % (dim, value)


def evidence_item(C, e):
    """One scanner episode rendered over its own supporting days, with a consistent baseline and change."""
    r = compare(C, e["metric"], e["tenant"], e["dim"], e["value"], e["from"], e["to"], e.get("mode", "self"))
    r["z"] = e.get("stat")
    r["line"] = ("%s on %s, days %d-%d: %s (n=%d) against %s for %s on days %d-%d (n=%d): %s; scanner statistic z=%.1f"
                 % (e["metric"], where_label(e["dim"], e["value"]), e["from"], e["to"],
                    fmt_value(e["metric"], r["current"]), r["n_current"], fmt_value(e["metric"], r["baseline"]),
                    r["baseline_kind"], r["baseline_days"][0], r["baseline_days"][1], r["n_baseline"],
                    r["change"]["text"], e.get("stat") or 0.0))
    return r
