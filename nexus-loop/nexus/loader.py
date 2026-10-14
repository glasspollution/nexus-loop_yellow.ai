"""Generic scanner, stage 1 (v2): fold a kit into
  (a) daily counters for EVERY (metric x slice), and
  (b) per-session metric arrays, so later stages can ask counterfactual questions such as
      "does this anomaly survive if cohort X is removed?" or "does it survive re-weighting?".

Nothing here names a planted fault:
  * metrics come from the catalog's step_type layers and the session measures;
  * slice dimensions are low-cardinality dimensions (the catalog's own breakdown budget);
  * version-like fields are DISCOVERED (a field whose value changes within one agent over time)
    and are never slice keys - they are attribution evidence;
  * which agent kinds emit no mechanism steps is read from the catalog's field semantics.
"""
import csv
import gzip
import hashlib
import json
import os
import pickle
import sys
import time
from array import array
from collections import Counter

import numpy as np

SLICE_DIMS = ("intent", "agent_id", "channel", "segment")
MAX_SLICE_CARDINALITY = 50
NOT_VERSION = {"session_id", "tenant", "ts_start", "ts_end", "channel", "intent", "agent_id",
               "agent_kind", "session_end"}
BIN_SUFFIX = (".fail", ".timeout", ".blocked", ".retry", ".empty", ".miss")
SESSION_BIN = {"s.resolved", "s.abandoned", "s.handoff_unplanned", "s.milestones_complete",
               "s.tool_error_any", "s.guardrail_any"}
LOWER_IS_BAD = {"s.resolved", "s.milestones_complete", "s.milestone_ratio", "kb_lookup.top_score"}


def is_bin(metric):
    return metric in SESSION_BIN or metric.endswith(BIN_SUFFIX)


def direction_of(metric):
    """+1: an increase is bad. -1: a decrease is bad."""
    if metric in LOWER_IS_BAD or metric.startswith("s.quality_score@"):
        return -1
    return +1


class _Direction:
    """Lets older callers write DIRECTION[metric]."""

    def __getitem__(self, metric):
        return direction_of(metric)


DIRECTION = _Direction()


def _cols(n):
    return [array("d", bytes(8 * n)) for _ in range(3)]


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


CACHE_VERSION = 2
FINGERPRINT_FILES = ("catalog.json", "asks.md", "corpus/sessions.jsonl.gz", "corpus/agent_steps.jsonl.gz",
                     "corpus/config_timeline.csv", "labels/rubric_scores.jsonl", "labels/outcome_labels.jsonl")


def _fingerprint(kit):
    """Cache key from the kit's absolute path and its input files' sizes and mtimes. A folder name alone is
    not enough: a sealed kit unpacked into a folder called `kit` must never reuse the practice cache."""
    h = hashlib.sha256(("v%d|%s" % (CACHE_VERSION, os.path.abspath(kit))).encode("utf-8"))
    for rel in FINGERPRINT_FILES:
        p = os.path.join(kit, rel)
        if os.path.exists(p):
            st = os.stat(p)
            h.update(("|%s:%d:%d" % (rel, st.st_size, int(st.st_mtime))).encode("utf-8"))
    return h.hexdigest()[:16]


def load_counters(kit, cache_dir=None):
    tag = os.path.basename(os.path.normpath(kit))
    cache = os.path.join(cache_dir, "counters-%s-%s.pkl" % (tag, _fingerprint(kit))) if cache_dir else None
    if cache and os.path.exists(cache):
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    t0 = time.time()
    cat = json.load(open(os.path.join(kit, "catalog.json"), encoding="utf-8"))
    ak = cat.get("fields", {}).get("session.agent_kind", {})
    sem = ak.get("semantics", "")
    no_step_kinds = {v for v in ak.get("closed_set", []) if v in sem} if " NO " in " %s " % sem else set()

    rubric = _read_jsonl(os.path.join(kit, "labels", "rubric_scores.jsonl"))
    outcome_labels = _read_jsonl(os.path.join(kit, "labels", "outcome_labels.jsonl"))
    labelled = {r["session_id"] for r in rubric} | {r["session_id"] for r in outcome_labels}

    # ---------------- pass 0: sessions ----------------
    rows = []
    version_cands = None
    labelled_rows = {}
    with gzip.open(os.path.join(kit, "corpus", "sessions.jsonl.gz"), "rt", encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            if version_cands is None:
                version_cands = [k for k, v in s.items() if isinstance(v, str) and k not in NOT_VERSION]
            cd = s.get("custom_dims") or {}
            s["segment"] = cd.get("segment")
            rows.append(s)
            if s["session_id"] in labelled:
                labelled_rows[s["session_id"]] = (s.get("quality_score"), s.get("judge_version"),
                                                  s.get("session_end"))
    N = len(rows)
    sid_idx = {s["session_id"]: i for i, s in enumerate(rows)}

    # ---------------- pass 1: steps -> per-session aggregates ----------------
    step_cols, tool_rows = {}, {}
    kind_steps = Counter()      # (agent_kind, step_type) -> steps: checks the catalog's coverage semantics against the data
    with gzip.open(os.path.join(kit, "corpus", "agent_steps.jsonl.gz"), "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            st = r["step_type"]
            if st == "turn":
                continue
            i = sid_idx.get(r["session_id"])
            if i is None:
                continue
            kind_steps[(rows[i].get("agent_kind"), st)] += 1
            outcome = r.get("outcome")
            obs = [(st + ".fail", 0.0 if outcome == "ok" else 1.0)]
            if st in ("tool_call", "llm_call"):
                obs.append((st + ".timeout", 1.0 if outcome == "timeout" else 0.0))
            if st == "guardrail":
                obs.append((st + ".blocked", 1.0 if outcome == "blocked" else 0.0))
            rc = r.get("retry_count")
            if rc is not None:
                obs.append((st + ".retry", 1.0 if rc > 0 else 0.0))
            dm = r.get("duration_ms")
            if dm is not None:
                obs.append((st + ".duration_ms", float(dm)))
            if st == "tool_call" and outcome == "ok" and r.get("result_field_count") is not None:
                obs.append(("tool_call.empty", 1.0 if r["result_field_count"] == 0 else 0.0))
            if st == "kb_lookup":
                obs.append(("kb_lookup.miss", 0.0 if r.get("kb_hit") else 1.0))
                if r.get("kb_top_score") is not None:
                    obs.append(("kb_lookup.top_score", float(r["kb_top_score"])))
            if st == "llm_call":
                obs.append(("llm_call.tokens",
                            float((r.get("input_tokens") or 0) + (r.get("output_tokens") or 0))))
            tool = r.get("tool_name") if st == "tool_call" else None
            for m, v in obs:
                c = step_cols.get(m)
                if c is None:
                    c = step_cols[m] = _cols(N)
                c[0][i] += 1.0
                c[1][i] += v
                c[2][i] += v * v
                if tool:
                    d = tool_rows.setdefault((tool, m), {})
                    x = d.get(i)
                    if x is None:
                        x = d[i] = [0.0, 0.0, 0.0]
                    x[0] += 1.0
                    x[1] += v
                    x[2] += v * v
    t1 = time.time()

    # ---------------- session-level metrics ----------------
    scols = {}

    def sput(m, i, v):
        c = scols.get(m)
        if c is None:
            c = scols[m] = _cols(N)
        c[0][i] += 1.0
        c[1][i] += v
        c[2][i] += v * v

    elig = np.zeros(N, dtype=bool)
    for i, s in enumerate(rows):
        end = s["session_end"]
        sput("s.resolved", i, 1.0 if end == "resolved" else 0.0)
        sput("s.abandoned", i, 1.0 if end == "abandoned" else 0.0)
        sput("s.handoff_unplanned", i, 1.0 if (end == "handoff" and not s.get("handoff_by_design")) else 0.0)
        total = s.get("milestones_total") or 0
        if total:
            reached = len(s.get("milestones_reached") or [])
            sput("s.milestones_complete", i, 1.0 if reached >= total else 0.0)
            sput("s.milestone_ratio", i, reached / total)
        if s.get("turns") is not None:
            sput("s.turns", i, float(s["turns"]))
        if s.get("duration_s") is not None:
            sput("s.duration_s", i, float(s["duration_s"]))
        if s.get("agent_kind") not in no_step_kinds:
            elig[i] = True
            if s.get("cost_usd") is not None:
                sput("s.cost_usd", i, float(s["cost_usd"]))
            sput("s.tool_error_any", i, 1.0 if (s.get("tool_error_count") or 0) > 0 else 0.0)
            sput("s.guardrail_any", i, 1.0 if (s.get("guardrail_blocks") or 0) > 0 else 0.0)
        if s.get("quality_score") is not None and s.get("judge_version"):
            # catalog: quality_score "requires" judge_version -> never pooled across versions
            sput("s.quality_score@" + s["judge_version"], i, float(s["quality_score"]))

    metrics = sorted(set(scols) | set(step_cols))
    MI = {m: j for j, m in enumerate(metrics)}
    M = np.zeros((N, len(metrics), 3))
    for m, cols in list(scols.items()) + list(step_cols.items()):
        for k in range(3):
            M[:, MI[m], k] = np.frombuffer(cols[k], dtype=np.float64)

    tools = sorted({t for (t, _) in tool_rows})
    tool_metrics = sorted({m for (_, m) in tool_rows})
    TMI = {m: j for j, m in enumerate(tool_metrics)}
    TM = {}
    for t in tools:
        idxs = sorted(set().union(*[tool_rows[(t, m)].keys() for m in tool_metrics if (t, m) in tool_rows]))
        pos = {ix: p for p, ix in enumerate(idxs)}
        arr = np.zeros((len(idxs), len(tool_metrics), 3))
        for m in tool_metrics:
            for ix, v in tool_rows.get((t, m), {}).items():
                arr[pos[ix], TMI[m]] = v
        TM[t] = (np.array(idxs, dtype=np.int64), arr)

    tenants = sorted({s["tenant"] for s in rows})
    TI = {t: k for k, t in enumerate(tenants)}
    ten_arr = np.array([TI[s["tenant"]] for s in rows], dtype=np.int16)
    day_arr = np.array([s["day"] for s in rows], dtype=np.int64)
    D = int(day_arr.max()) + 1

    vocab, codes, refused = {}, {}, []
    for d in SLICE_DIMS:
        vals = sorted({s.get(d) for s in rows if s.get(d) is not None})
        per_tenant = max(len({s.get(d) for s in rows if s["tenant"] == t and s.get(d) is not None})
                         for t in tenants)
        if per_tenant > MAX_SLICE_CARDINALITY:
            refused.append(d)
            continue
        vi = {v: k for k, v in enumerate(vals)}
        vocab[d] = vals
        codes[d] = np.array([vi.get(s.get(d), -1) for s in rows], dtype=np.int32)
    tool_mask = {}
    for t in tools:
        mk = np.zeros(N, dtype=bool)
        mk[TM[t][0]] = True
        tool_mask[t] = mk

    # ---------------- daily counters per slice ----------------
    BIN, CONT, volume, first_day, slice_n = {}, {}, {}, {}, {}
    for ten in tenants:
        tm = ten_arr == TI[ten]
        slices = [("__all__", "__all__", tm)]
        for d in vocab:
            for k, v in enumerate(vocab[d]):
                mk = tm & (codes[d] == k)
                if mk.any():
                    slices.append((d, v, mk))
        for t in tools:
            mk = tm & tool_mask[t]
            if mk.any():
                slices.append(("tool", t, mk))
        for d, v, mk in slices:
            days = day_arr[mk]
            cnt = np.bincount(days, minlength=D)
            key3 = (ten, d, v)
            volume[key3] = {int(x): int(cnt[x]) for x in np.nonzero(cnt)[0]}
            first_day[key3] = int(days.min())
            slice_n[key3] = int(mk.sum())
            Mk = M[mk]
            if d == "tool":
                idxs, arr = TM[v]
                tsel = mk[idxs]
                tdays, tarr = day_arr[idxs][tsel], arr[tsel]
            for m in metrics:
                if d == "tool" and m in TMI:
                    dd, W = tdays, tarr[:, TMI[m], :]
                else:
                    dd, W = days, Mk[:, MI[m], :]
                if len(dd) == 0:
                    continue
                n = np.bincount(dd, weights=W[:, 0], minlength=D)
                if n.sum() <= 0:
                    continue
                s1 = np.bincount(dd, weights=W[:, 1], minlength=D)
                nz = np.nonzero(n)[0]
                if is_bin(m):
                    BIN[(ten, m, d, v)] = {int(x): [float(n[x]), float(s1[x])] for x in nz}
                else:
                    s2 = np.bincount(dd, weights=W[:, 2], minlength=D)
                    CONT[(ten, m, d, v)] = {int(x): [float(n[x]), float(s1[x]), float(s2[x])] for x in nz}

    # ---------------- discovered version flips ----------------
    dom = {}
    for s in rows:
        for fld in version_cands:
            dom.setdefault((s["tenant"], s["agent_id"], fld), {}).setdefault(s["day"], Counter())[s.get(fld)] += 1
    flips = []
    for (ten, ag, fld), byday in dom.items():
        prev = None
        for d in sorted(byday):
            v = byday[d].most_common(1)[0][0]
            if prev is not None and v != prev:
                flips.append({"tenant": ten, "agent_id": ag, "field": fld, "day": d, "from": prev, "to": v})
            prev = v
    agents_total = len({(s["tenant"], s["agent_id"]) for s in rows})
    by_fd = {}
    for fl in flips:
        by_fd.setdefault((fl["field"], fl["day"]), []).append(fl)
    global_flips = []
    for (fld, d), fls in by_fd.items():
        if len({(f["tenant"], f["agent_id"]) for f in fls}) >= 0.9 * agents_total and \
                len({f["tenant"] for f in fls}) >= 2:
            global_flips.append({"field": fld, "day": d, "from": fls[0]["from"], "to": fls[0]["to"],
                                 "agents": len(fls)})

    # ---------------- calibration against human labels ----------------
    qa = []
    for r in rubric:
        x = labelled_rows.get(r["session_id"])
        if x and x[0] is not None and x[1] == r.get("judge_version_at_label_time"):
            qa.append((r["human_quality"], x[0]))
    oa = [(r["human_resolved"], labelled_rows[r["session_id"]][2] == "resolved")
          for r in outcome_labels if r["session_id"] in labelled_rows and r.get("human_resolved") is not None]
    calibration = {
        "quality_within_version": {"agreement": round(sum(abs(a - b) <= 0.5 for a, b in qa) / len(qa), 4)
                                   if qa else None, "n": len(qa), "tolerance": 0.5},
        "resolved_log_vs_human": {"agreement": round(sum(a == b for a, b in oa) / len(oa), 4) if oa else None,
                                  "n": len(oa)}}

    # ---------------- cardinality budgets ----------------
    card = []
    for fname, fdef in cat.get("fields", {}).items():
        b = fdef.get("cardinality_budget")
        if b is None:
            continue
        leaf = fname.split(".")[-1]
        if fname.startswith("session.custom_dims."):
            vals = {(s.get("custom_dims") or {}).get(leaf) for s in rows}
        else:
            vals = {s.get(leaf) for s in rows}
        card.append({"field": fname, "budget": b, "distinct": len(vals - {None}),
                     "refused": len(vals - {None}) > b})

    cfg_path = os.path.join(kit, "corpus", "config_timeline.csv")
    config = list(csv.DictReader(open(cfg_path, encoding="utf-8"))) if os.path.exists(cfg_path) else []
    asks_path = os.path.join(kit, "asks.md")
    asks = ""
    if os.path.exists(asks_path):
        raw = open(asks_path, "rb").read()
        try:
            asks = raw.decode("utf-8")
        except UnicodeDecodeError:
            asks = raw.decode("cp1252", errors="replace")

    coverage = {t: round(float(elig[ten_arr == TI[t]].mean()), 4) for t in tenants}

    # ---------------- per-session attributes for the decision layer (never read by detection) ----------------
    sid_arr = np.array([s["session_id"] for s in rows])
    cost_arr = np.array([float(s["cost_usd"]) if s.get("cost_usd") is not None else np.nan for s in rows])
    kinds = sorted({s.get("agent_kind") for s in rows if s.get("agent_kind")})
    kind_codes = np.array([kinds.index(s["agent_kind"]) if s.get("agent_kind") in kinds else -1 for s in rows],
                          dtype=np.int16)
    vcodes, vvocab = {}, {}
    for fld in version_cands or []:
        vals = sorted({s.get(fld) for s in rows if isinstance(s.get(fld), str)})
        if not vals or len(vals) > MAX_SLICE_CARDINALITY:
            continue
        vi = {v: k for k, v in enumerate(vals)}
        vvocab[fld] = vals
        vcodes[fld] = np.array([vi.get(s.get(fld), -1) for s in rows], dtype=np.int32)
    labels = {"outcome": {r["session_id"]: r.get("human_resolved") for r in outcome_labels},
              "outcome_n": len(outcome_labels), "rubric_n": len(rubric)}

    out = {"kit": kit, "tenants": tenants, "days": D,
           "BIN": BIN, "CONT": CONT, "volume": volume, "first_day": first_day, "slice_n": slice_n,
           "metrics": metrics,
           "S": {"ten": ten_arr, "day": day_arr, "tenant_index": TI, "codes": codes, "vocab": vocab,
                 "tool_mask": tool_mask, "M": M, "MI": MI, "TM": TM, "TMI": TMI, "elig": elig,
                 "sid": sid_arr, "cost": cost_arr, "kind": kind_codes, "kinds": kinds,
                 "version_codes": vcodes, "version_vocab": vvocab},
           "kind_steps": {"%s|%s" % k: n for k, n in kind_steps.items()}, "labels": labels,
           "version_fields": sorted({f["field"] for f in flips}), "flips": flips,
           "global_flips": global_flips, "refused_dims": refused, "cardinality": card,
           "calibration": calibration, "coverage": coverage, "no_step_kinds": sorted(no_step_kinds),
           "catalog": cat, "config": config, "asks": asks,
           "timing": (round(t1 - t0, 1), round(time.time() - t1, 1))}
    if cache:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache, "wb") as fh:
            pickle.dump(out, fh, protocol=4)
    return out
