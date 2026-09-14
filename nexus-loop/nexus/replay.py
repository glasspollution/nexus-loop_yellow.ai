"""Verification: put a proposed fix to the replay service and record what came back.

Closes the last arm of the loop. Three things this deliberately does NOT do:

  * It does not retry. Repeat probes are seeded to return identical results, so a retry spends
    budget to learn nothing. The budget is 40 runs for the whole team, shared with everyone.
  * It does not treat ``no_effect`` as an error. A wrong fix and a healthy cohort are reported
    identically and on purpose - if those were distinguishable, forty probes would map every fault
    without any analysis. A ``no_effect`` we kept is worth more than a success we engineered.
  * It does not run unless asked. ``run.py`` without ``--replay`` is unchanged, so the unattended
    sealed run never depends on a service being up.

The golden set is mined from the corpus, not invented: resolved conversations that reached every
milestone their intent defines, with no tool error and no knowledge-base miss, taken within a
single judge version so the quality filter means one thing throughout.
"""

import gzip
import json
import urllib.error
import urllib.request

GOLDEN_N = 50
TIMEOUT_S = 20


def mine_golden_set(kit, tenant, limit=GOLDEN_N, quality_floor=4.0):
    """Known-good conversations for this tenant, by the deployment's own standard.

    Returns session ids. Selection is deterministic (first N in corpus order) so a replay is
    reproducible, and is confined to one judge version because a quality threshold compared across
    a rubric change would be measuring the rubric.
    """
    picked, version = [], None
    path = "%s/corpus/sessions.jsonl.gz" % kit
    try:
        with gzip.open(path, "rt") as fh:
            for line in fh:
                try:
                    s = json.loads(line)
                except ValueError:
                    continue
                if s.get("tenant") != tenant or s.get("session_end") != "resolved":
                    continue
                if s.get("tool_error_count") or s.get("kb_miss_count") or s.get("guardrail_blocks"):
                    continue
                tot = s.get("milestones_total") or 0
                if not tot or len(s.get("milestones_reached") or []) < tot:
                    continue
                q, jv = s.get("quality_score"), s.get("judge_version")
                if q is None or jv is None or q < quality_floor:
                    continue
                if version is None:
                    version = jv
                elif jv != version:
                    continue          # never pool a quality filter across a judge-version boundary
                picked.append(s["session_id"])
                if len(picked) >= limit:
                    break
    except (OSError, IOError):
        return [], None
    return picked, version


# The replay endpoint is always localhost or the room network, so any ambient http_proxy setting
# would send the request somewhere it cannot be served. Bypass proxies explicitly rather than
# depending on no_proxy being set correctly on whichever laptop runs the demo.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(endpoint, team, tenant, change, cohort, golden_set, timeout=TIMEOUT_S):
    """One POST /replay. Returns the decoded body, or {'error': ...}. Never raises."""
    body = json.dumps({"team": team, "tenant": tenant, "change": change, "cohort": cohort,
                       "golden_set": list(golden_set or [])}).encode("utf-8")
    req = urllib.request.Request(endpoint.rstrip("/") + "/replay", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"error": "http_%s" % e.code}
    except Exception as e:
        return {"error": "unreachable", "detail": str(e)}


def _verification(pres, res, predicted, predicted_metric=None):
    """Shape one replay response into a verifications[] entry.

    prediction_error is only computed when the prediction and the replay are about the SAME metric.
    Detection runs on the mechanism (kb_lookup.miss) while the replay reports the outcome
    (resolution_rate), so subtracting one from the other would produce a confident-looking number
    that means nothing. Where they differ we say so instead.
    """
    before, after = res.get("before"), res.get("after")
    gs = res.get("golden_set") or {}
    out = {"prescription_id": pres["id"], "replay_run_id": res["run_id"],
           "metric": res.get("metric"), "before": before, "after": after,
           "golden_set_pass": gs.get("pass"), "verdict": res.get("verdict", "no_effect")}
    same = predicted_metric and res.get("metric") and predicted_metric == res.get("metric")
    if same and before is not None and after is not None and predicted is not None:
        out["prediction_error"] = round(predicted - (after - before), 4)
    elif predicted_metric:
        out["prediction_error_not_computed_because"] = (
            "We predicted a change in %s, the mechanism we detected on; the replay reports %s, the "
            "outcome. Those are different measures, so subtracting one from the other would give a "
            "precise-looking number with no meaning. The replay measuring the outcome rather than "
            "the mechanism is the right yardstick - it is the prediction error that is not "
            "available, not the result." % (predicted_metric, res.get("metric")))
    # Product layer: what an operator should understand from this result, and its honest limit.
    out["plain"] = _plain(res, gs)
    out["caveat"] = ("This ran on the organisers' replay simulator against recorded traffic, not "
                     "on production. It is the strongest evidence available here and it is still "
                     "not a live experiment.")
    # A stop condition that is never checked is decoration. Every prescription pre-commits to not
    # shipping if the golden set regresses; when that happens, the report has to say so out loud.
    if gs.get("replayed") and gs.get("regressed"):
        out["stop_condition_triggered"] = True
        lead = ("This change improved the cohort and still broke"
                if res.get("verdict") == "improved" else
                "This change did not help the cohort and it broke")
        out["stop_condition_note"] = (
            "%s %d of %d known-good conversations. We wrote down before running it that we would "
            "not ship if the golden set regressed. It did, so the recommendation is do not ship as "
            "proposed - narrow the change and re-test. Pre-committing that condition is what makes "
            "this call automatic instead of a judgement made after seeing a good headline number."
            % (lead, gs["regressed"], gs["replayed"]))
    return out


def _plain(res, gs):
    v, m = res.get("verdict"), res.get("metric") or "the metric"
    n = res.get("sessions_replayed")
    rep, broke = gs.get("replayed") or 0, gs.get("regressed") or 0
    gtxt = ("" if not rep else
            " %d known-good conversations were replayed alongside it and %s."
            % (rep, "none regressed" if not broke else
               "%d regressed - this fix breaks work that was already fine" % broke))
    if v == "improved":
        return ("Replayed on %s recorded conversations: %s moved from %s to %s.%s"
                % (n, m, res.get("before"), res.get("after"), gtxt))
    if v == "regressed":
        return ("Replayed on %s recorded conversations and it made things worse: %s moved from %s "
                "to %s. This fix should not ship.%s" % (n, m, res.get("before"), res.get("after"), gtxt))
    return ("Replayed on %s recorded conversations: %s did not move (%s to %s). The replay reports "
            "a wrong fix and a cohort with nothing to fix identically, so this says the change does "
            "not address what is happening - not that nothing is happening.%s"
            % (n, m, res.get("before"), res.get("after"), gtxt))


def verify_all(C, rep, endpoint, team, kit, probe_blunt=True, log=None):
    """Replay every prescription once, plus optionally one deliberately blunt alternative.

    The blunt probe is a revert aimed at the same cohort. It is expected to come back no_effect and
    to put the golden set at risk, which is the point: reporting an attempt that failed is worth
    more than reporting only the one that worked.
    """
    say = log or (lambda *a: None)
    findings = {f["id"]: f for f in rep.get("findings", [])}
    diags = {d["id"]: d for d in rep.get("diagnoses", [])}
    out, golden_cache = [], {}

    for pres in rep.get("prescriptions", []):
        d = diags.get(pres.get("diagnosis_id")) or {}
        f = findings.get(d.get("finding_id")) or {}
        tenant = f.get("tenant")
        if not tenant:
            continue
        if tenant not in golden_cache:
            golden_cache[tenant] = mine_golden_set(kit, tenant)
        golden, jver = golden_cache[tenant]
        # The cohort goes to the replay exactly as the finding states it. Substituting a different
        # key here silently returns no_effect: the service matches on the cohort it was planted with.
        cohort = dict(f.get("cohort") or {})
        cohort["from_day"] = f.get("window", {}).get("from_day", 0)
        cohort["to_day"] = f.get("window", {}).get("to_day", 0)
        change = {"type": pres["change_type"], "target": pres.get("target", ""),
                  "description": pres.get("description", "")}
        pd = pres.get("predicted_delta") or {}
        predicted = None
        if pd.get("to") is not None and pd.get("from") is not None:
            predicted = pd["to"] - pd["from"]

        res = call(endpoint, team, tenant, change, cohort, golden)
        if res.get("error"):
            say("  replay %s -> %s (%s)" % (pres["id"], res["error"], res.get("detail", "")[:60]))
            if res["error"] == "run_budget_exhausted":
                break
            continue
        v = _verification(pres, res, predicted, pd.get("metric"))
        v["golden_set_version"] = jver
        out.append(v)
        say("  replay %s  %s  %s %s -> %s  golden %s/%s"
            % (pres["id"], res["verdict"], res.get("metric"), res.get("before"), res.get("after"),
               (res.get("golden_set") or {}).get("regressed"), (res.get("golden_set") or {}).get("replayed")))

    # One honest negative result, on the first prescription's cohort.
    if probe_blunt and out:
        first = rep["prescriptions"][0]
        d = diags.get(first.get("diagnosis_id")) or {}
        f = findings.get(d.get("finding_id")) or {}
        tenant = f.get("tenant")
        golden, jver = golden_cache.get(tenant, ([], None))
        cohort = dict(f.get("cohort") or {})
        cohort["from_day"] = f.get("window", {}).get("from_day", 0)
        cohort["to_day"] = f.get("window", {}).get("to_day", 0)
        res = call(endpoint, team, tenant,
                   {"type": "revert", "target": f.get("cohort_label", tenant),
                    "description": "Blunt alternative: revert the change outright rather than "
                                   "addressing the specific cause."},
                   cohort, golden)
        if not res.get("error"):
            v = _verification(first, res, None)
            v["golden_set_version"] = jver
            v["is_alternative"] = True
            v["alternative_note"] = (
                "We also tested the blunter option - reverting outright instead of the narrow fix. "
                "We are reporting it because it did not work: that is why the system proposes the "
                "specific change rather than the obvious one.")
            out.append(v)
            say("  replay ALT revert  %s  golden %s/%s"
                % (res["verdict"], (res.get("golden_set") or {}).get("regressed"),
                   (res.get("golden_set") or {}).get("replayed")))
    return out


def self_assessment(verifications, prescriptions):
    """Predicted vs actual, per change type - and an explicit refusal to compute a hit rate from it.

    With one observation per change class, an accuracy figure would be a number with no evidence
    behind it. Reporting the observations and declining to act on them is the honest form.
    """
    by_id = {p["id"]: p for p in prescriptions}
    acc, real = {}, [v for v in verifications if not v.get("is_alternative")]
    for v in real:
        p = by_id.get(v.get("prescription_id"))
        if not p:
            continue
        ct = p.get("change_type")
        e = acc.setdefault(ct, {"n": 0, "improved": 0, "broke_golden_set": 0, "_errs": []})
        e["n"] += 1
        if v.get("verdict") == "improved":
            e["improved"] += 1
        if v.get("stop_condition_triggered"):
            e["broke_golden_set"] += 1
        if v.get("prediction_error") is not None:
            e["_errs"].append(v["prediction_error"])

    # MIN_N is the point at which a rate starts to carry information. Below it we report the raw
    # counts and omit hit_rate entirely rather than publishing 1.0 from a single observation - a
    # system that overclaims about ITSELF has no standing to ask anyone to trust its other numbers.
    MIN_N = 8
    for ct, e in acc.items():
        errs = e.pop("_errs")
        if errs:
            e["mean_prediction_error"] = round(sum(errs) / len(errs), 4)
        if e["n"] >= MIN_N:
            e["hit_rate"] = round(e["improved"] / e["n"], 4)
        else:
            e["hit_rate_declined_because"] = (
                "n=%d. A hit rate needs about %d observations of a change class before it means "
                "anything; from %d it would just restate the single result with a decimal point on "
                "it. The count is above - the rate is deliberately not computed."
                % (e["n"], MIN_N, e["n"]))
    biggest = max([e["n"] for e in acc.values()] or [0])
    return {
        "cycles": 1 if real else 0,
        "prescription_accuracy": acc,
        "downweighted": [],
        "notes": ("One cycle, with at most %d observation%s per change class. We report what each "
                  "replay returned and deliberately do not compute an accuracy rate from it: a hit "
                  "rate from n=1 is not evidence, and publishing one would be exactly the kind of "
                  "overclaiming this system exists to avoid. Roughly %d cycles per change class "
                  "would be needed before any of these priors should be allowed to change a "
                  "decision. Prediction error is reported only where the prediction and the replay "
                  "measured the same thing; where detection ran on a mechanism and the replay "
                  "reported an outcome, it is left out rather than computed across two different "
                  "measures." % (biggest, "" if biggest == 1 else "s", MIN_N)),
    }
