"""Stage 10: the loop's record of its own hit rate (Task 04; product handoff section 10).

Frozen choices:
  * HIT = guard-qualified: the replay returned `improved` AND the golden set held. `no_effect` and golden-set
    failures are misses; prescriptions that could not be verified are outside the denominator and listed.
  * The submitted report's `self_assessment` counts ONLY batches run on this corpus (cycles = 1 when this run verified
    anything), so a sealed report never borrows history.
  * A persistent ledger records every batch on every corpus. Prior cycles on OTHER corpora are shown separately in
    `prior_cycles_on_other_corpora` and never merged into this corpus's n or cycles.
  * Nothing is de-weighted until a change type has at least 8 verified prescriptions.
"""
import datetime
import hashlib
import json
import os

HIT_DEFINITION = ("guard-qualified hit: the replay service returned 'improved' AND the golden set held; 'no_effect' and "
                  "golden-set failures count as misses; prescriptions that could not be verified are not in the "
                  "denominator")
MIN_N_TO_DOWNWEIGHT = 8


def is_hit(v):
    return v.get("verdict") == "improved" and v.get("golden_set_pass") is True


def summarise(report):
    pres = {p["id"]: p for p in report.get("prescriptions", [])}
    by = {}
    for v in report.get("verifications", []):
        p = pres.get(v.get("prescription_id"))
        if not p:
            continue
        d = by.setdefault(p["change_type"], {"n": 0, "hits": 0, "errors": [], "run_ids": []})
        d["n"] += 1
        d["hits"] += int(is_hit(v))
        d["run_ids"].append(v.get("replay_run_id"))
        if v.get("prediction_error") is not None:
            d["errors"].append(v["prediction_error"])
    return by


def read_ledger(path):
    if not path or not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def assess(report, corpus, unverified=(), ledger_path=None):
    by = summarise(report)
    acc = {}
    for ct, d in sorted(by.items()):
        acc[ct] = {"n": d["n"], "hits": d["hits"], "hit_rate": round(d["hits"] / d["n"], 4)}
        if d["errors"]:
            acc[ct]["mean_prediction_error"] = round(sum(d["errors"]) / len(d["errors"]), 4)
            acc[ct]["prediction_error_units"] = "replay metric units (predicted delta - replayed delta)"
    cycles = 1 if by else 0
    down = ["%s: hit rate %.2f over %d verified prescriptions" % (ct, a["hit_rate"], a["n"]) for ct, a in acc.items()
            if a["n"] >= MIN_N_TO_DOWNWEIGHT and a["hit_rate"] < 0.5]
    prior = {}
    for rec in read_ledger(ledger_path):
        if rec.get("corpus") == corpus or rec.get("kind", "prescriptions") != "prescriptions":
            continue
        for ct, d in (rec.get("by_change_type") or {}).items():
            x = prior.setdefault(ct, {"n": 0, "hits": 0, "batches": set()})
            x["n"] += d.get("n", 0)
            x["hits"] += d.get("hits", 0)
            x["batches"].add(rec.get("batch_id"))
    prior_out = {ct: {"n": x["n"], "hits": x["hits"], "batches": len(x["batches"]),
                      "hit_rate": round(x["hits"] / x["n"], 4) if x["n"] else None} for ct, x in sorted(prior.items())}
    n_total = sum(a["n"] for a in acc.values())
    notes = ("%s. This run verified %d prescription(s) on this corpus%s. %s With so few verified prescriptions per change "
             "type the loop reports its hit rate and declines to act on it: nothing is de-weighted until a change type "
             "has at least %d. Hit rates and prediction errors are measured against the organisers' replay simulator, "
             "not real deployments." % (HIT_DEFINITION[0].upper() + HIT_DEFINITION[1:], n_total,
                                        "" if not unverified else "; not verified: %s" % "; ".join(unverified),
                                        ("Prior cycles on other corpora are listed separately and are not part of these "
                                         "numbers." if prior_out else "No prior cycles on other corpora are recorded."),
                                        MIN_N_TO_DOWNWEIGHT))
    sa = {"cycles": cycles, "prescription_accuracy": acc, "downweighted": down, "notes": notes,
          "hit_definition": HIT_DEFINITION, "unverified": list(unverified), "corpus": corpus,
          "prior_cycles_on_other_corpora": prior_out}
    run_ids = sorted(r for d in by.values() for r in d["run_ids"])
    record = None
    if by:
        record = {"kind": "prescriptions", "corpus": corpus, "hit_definition": HIT_DEFINITION,
                  "batch_id": hashlib.sha256(json.dumps([corpus, run_ids]).encode()).hexdigest()[:16],
                  "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "by_change_type": {ct: {"n": d["n"], "hits": d["hits"], "prediction_errors": d["errors"]}
                                     for ct, d in by.items()}}
    return sa, record


def append_batch(ledger_path, record):
    """Append a batch once: re-running the same corpus with the same replay results adds nothing."""
    if not ledger_path or not record:
        return False
    if any(r.get("batch_id") == record["batch_id"] for r in read_ledger(ledger_path)):
        return False
    os.makedirs(os.path.dirname(os.path.abspath(ledger_path)), exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return True
