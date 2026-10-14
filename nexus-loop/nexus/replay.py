"""Stage 8: verify proposed fixes on the organisers' replay service (Task 03; product handoff section 8).

Policy, enforced by construction:
  * a request is built ONLY from a regression finding's own tenant, cohort keys and window, with change = {type,
    target} (the description is part of the service's random seed, so it is never sent), and the frozen golden set;
  * one call per eligible prescription; no automatic second attempt after `no_effect`, no rewording, no budget
    resets, no reading of the shared /log, no probing of cohorts or windows that are not findings;
  * every response is cached on disk under a hash of (endpoint, corpus, request), so a re-run spends nothing, and
    every network call is appended to a ledger;
  * an unreachable endpoint, an exhausted budget or a malformed response produces NO verification row and a note -
    a verification is never fabricated;
  * the service's verdict is kept as returned; a separate gate state records whether the golden set held.
Every number the service returns is a simulation and is labelled as one.
"""
import datetime
import hashlib
import json
import math
import os
import urllib.error
import urllib.request

DEFAULT_MAX_CALLS = 8
STOP_AT_USED = 28           # leave the rest of the 40-run budget for human-approved re-verification and the demo
VERDICTS = ("improved", "no_effect", "regressed")
REPLAY_METRICS = ("resolution_rate", "median_turns")
NO_EFFECT_MEANING = ("no_effect means the change did not address a cause the replay models in this cohort and window, "
                     "or there was nothing to fix; it neither confirms nor refutes the diagnosis")
SIMULATION_NOTE = ("before, after, golden-set result and sessions_replayed come from the organisers' replay simulator; "
                   "no conversation was re-run and none of these values is measured from the corpus")


def _canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"))


def corpus_id(kit, report):
    mp = os.path.join(kit or "", "manifest.json")
    if os.path.exists(mp):
        return "manifest:" + hashlib.sha256(open(mp, "rb").read()).hexdigest()[:16]
    return "corpus:" + hashlib.sha256(_canon([report.get("corpus"), len(report.get("findings", []))]).encode()).hexdigest()[:16]


def eligible(prescription, finding):
    if finding is None or not finding.get("is_regression"):
        return False, "not linked to a regression finding"
    if prescription.get("change_type") == "no_action":
        return False, "no_action proposes no change, so there is nothing to replay"
    if not (finding.get("cohort") or {}):
        return False, "the finding has no cohort key; the replay can only verify a fix on a named slice"
    return True, ""


def build_request(team, finding, prescription, golden_ids):
    w = finding.get("window") or {}
    cohort = dict(finding["cohort"])
    cohort["from_day"] = int(w.get("from_day", 0))
    cohort["to_day"] = int(w.get("to_day", 0)) + 1          # report windows are inclusive; the service's to_day is not
    return {"team": team, "tenant": finding["tenant"],
            "change": {"type": prescription["change_type"], "target": prescription["target"]},
            "cohort": cohort, "golden_set": list(golden_ids or [])}


def request_key(endpoint, corpus, body):
    b = {k: v for k, v in body.items() if k != "team"}
    return hashlib.sha256(_canon([endpoint.rstrip("/") if endpoint else None, corpus, b]).encode()).hexdigest()


def predicted_replay_delta(prescription, before):
    rp = prescription.get("replay_prediction") or {}
    H, D, phi = rp.get("healthy_level"), rp.get("in_window_level"), rp.get("gap_fraction")
    if before is None or H is None or D is None or phi is None:
        return None
    if rp.get("metric") == "median_turns":
        return phi * before * (H / D - 1.0) if D else None
    return phi * (H - before)


def gate(verdict, golden_pass):
    if verdict == "improved" and golden_pass is True:
        return "candidate", "the replay improved the metric and the golden set held"
    if verdict == "improved" and golden_pass is False:
        return "blocked_golden_set", ("the replay improved the metric but broke golden-set conversations; at 20-30 "
                                      "golden conversations a correct fix fails this by chance about 4-6% of the time")
    if verdict == "improved":
        return "candidate_unguarded", "the replay improved the metric but no golden set was checked"
    return "not_supported_by_replay", NO_EFFECT_MEANING


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _http(url, body=None, timeout=20):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ledger(cache_dir, record):
    if not cache_dir:
        return
    os.makedirs(cache_dir, exist_ok=True)
    with open(os.path.join(cache_dir, "ledger.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _finite_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _response_problem(resp, golden_count, expected_metric=None):
    """Return why a replay result is unsafe to use, or None when it is complete and coherent."""
    if not isinstance(resp, dict):
        return "replay response was not a JSON object"
    if not isinstance(resp.get("run_id"), str) or not resp["run_id"].startswith("rp_"):
        return "replay response carried no valid run id"
    if resp.get("verdict") not in VERDICTS:
        return "replay response carried an invalid verdict"
    metric = resp.get("metric")
    if metric not in REPLAY_METRICS:
        return "replay response carried an invalid metric"
    if expected_metric is not None and metric != expected_metric:
        return "replay response metric did not match the prescription's replay metric"
    before, after = resp.get("before"), resp.get("after")
    if not _finite_number(before) or not _finite_number(after):
        return "replay response carried invalid before/after values"
    if before < 0 or after < 0 or (metric == "resolution_rate" and (before > 1 or after > 1)):
        return "replay response carried out-of-range before/after values"
    golden = resp.get("golden_set")
    if not isinstance(golden, dict):
        return "replay response carried invalid golden-set data"
    replayed, regressed, passed = golden.get("replayed"), golden.get("regressed"), golden.get("pass")
    if any(not isinstance(x, int) or isinstance(x, bool) or x < 0 for x in (replayed, regressed)):
        return "replay response carried invalid golden-set counts"
    if replayed != golden_count or regressed > replayed:
        return "replay response carried inconsistent golden-set counts"
    expected_pass = regressed == 0 if replayed else None
    if passed is not expected_pass:
        return "replay response carried an inconsistent golden-set verdict"
    runs_used = resp.get("runs_used")
    if runs_used is not None and (not isinstance(runs_used, int) or isinstance(runs_used, bool) or runs_used < 0):
        return "replay response carried an invalid runs-used count"
    sessions = resp.get("sessions_replayed")
    if sessions is not None and (not isinstance(sessions, int) or isinstance(sessions, bool) or sessions < 0):
        return "replay response carried an invalid sessions-replayed count"
    return None


def _read_cache(path):
    try:
        with open(path, encoding="utf-8") as fh:
            cached = json.load(fh)
    except (OSError, ValueError, RecursionError) as exc:
        return None, "cached replay response is unreadable (%s); not retried because its call may have counted" % \
            str(exc)[:80]
    if not isinstance(cached, dict) or "response" not in cached:
        return None, "cached replay record is malformed; not retried because its call may have counted"
    if not isinstance(cached["response"], dict):
        return None, "cached replay response was not a JSON object; not retried because its call may have counted"
    return cached["response"], None


def _claim_attempt(path, record):
    """Atomically leave a durable marker before POSTing, so an ambiguous call is never repeated."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        return False, "a prior replay attempt has no usable cached response; not retried because it may have counted"
    except OSError as exc:
        return False, "could not persist the replay attempt marker (%s); call not sent" % str(exc)[:80]
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return True, None


def _write_cache(path, record):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def verify(report, golden_sets, endpoint=None, team="nexus-loop", cache_dir=None, corpus=None, max_calls=DEFAULT_MAX_CALLS,
           timeout=20):
    """Returns (verifications, notes, trace). Never raises on network problems."""
    findings = {f["id"]: f for f in report.get("findings", [])}
    diagnoses = {d["id"]: d for d in report.get("diagnoses", [])}
    verifications, notes, trace = [], [], []
    calls, network_ok, stopped = 0, None, None
    for p in report.get("prescriptions", []):
        f = findings.get((diagnoses.get(p.get("diagnosis_id")) or {}).get("finding_id"))
        ok, why = eligible(p, f)
        row = {"prescription_id": p["id"], "fix_id": p.get("fix_id"), "change_type": p.get("change_type")}
        if not ok:
            trace.append(dict(row, status="skipped", reason=why))
            continue
        gs = golden_sets.get(f["tenant"], {})
        body = build_request(team, f, p, gs.get("session_ids"))
        expected_metric = (p.get("replay_prediction") or {}).get("metric")
        key = request_key(endpoint, corpus, body)
        row["request"] = body
        path = os.path.join(cache_dir, "%s.json" % key) if cache_dir else None
        attempt_path = os.path.join(cache_dir, "%s.attempt.json" % key) if cache_dir else None
        resp, cached = None, False
        if path and os.path.exists(path):
            resp, why = _read_cache(path)
            cached = resp is not None
        elif attempt_path and os.path.exists(attempt_path):
            why = "a prior replay attempt has no usable cached response; not retried because it may have counted"
        elif not endpoint:
            why = "no replay endpoint configured (run.py --replay-url)"
        elif stopped:
            why = stopped
        elif calls >= max_calls:
            why = "the per-run call cap (%d) was reached" % max_calls
        else:
            if network_ok is None:
                try:
                    _http(endpoint.rstrip("/") + "/health", timeout=timeout)
                    network_ok = True
                except (urllib.error.URLError, OSError, ValueError) as exc:
                    network_ok, stopped = False, "replay endpoint unreachable (%s)" % str(exc)[:80]
            if network_ok:
                claimed, claim_problem = (True, None)
                if attempt_path:
                    claimed, claim_problem = _claim_attempt(
                        attempt_path, {"at": _now(), "endpoint": endpoint, "key": key,
                                       "prescription_id": p["id"], "corpus": corpus, "state": "attempting"})
                if not claimed:
                    why = claim_problem
                else:
                    try:
                        calls += 1
                        resp = _http(endpoint.rstrip("/") + "/replay", body, timeout=timeout)
                    except (urllib.error.URLError, OSError, ValueError) as exc:
                        resp, stopped = None, "replay call failed (%s); not retried, because the call may have been counted" \
                                              % str(exc)[:80]
                        _ledger(cache_dir, {"at": _now(), "endpoint": endpoint, "key": key,
                                                   "prescription_id": p["id"], "error": str(exc)[:200]})
                    if resp is None:
                        why = stopped
                    elif not isinstance(resp, dict):
                        why = "replay response was not a JSON object; discarded and not retried because the call counted"
                        _ledger(cache_dir, {"at": _now(), "endpoint": endpoint, "key": key,
                                                   "prescription_id": p["id"], "error": why})
                        stopped, resp = "replay service returned a malformed response; further calls stopped", None
                    elif resp.get("error"):
                        _ledger(cache_dir, {"at": _now(), "endpoint": endpoint, "key": key,
                                                   "prescription_id": p["id"], "error": resp.get("error")})
                        if resp.get("error") == "run_budget_exhausted":
                            stopped = "the replay budget is exhausted (%s of %s used)" % (resp.get("used"), resp.get("budget"))
                        why, resp = "replay error: %s" % resp.get("error"), None
                    elif resp is not None:
                        problem = _response_problem(resp, len(body["golden_set"]), expected_metric)
                        if problem:
                            why = problem + "; discarded and not retried because the call counted"
                            _ledger(cache_dir, {"at": _now(), "endpoint": endpoint, "key": key,
                                                       "prescription_id": p["id"], "error": why})
                            stopped, resp = "replay service returned a malformed response; further calls stopped", None
                        else:
                            _ledger(cache_dir, {"at": _now(), "endpoint": endpoint, "key": key,
                                                       "run_id": resp["run_id"], "runs_used": resp.get("runs_used"),
                                                       "verdict": resp.get("verdict"), "prescription_id": p["id"],
                                                       "corpus": corpus})
                            if path:
                                _write_cache(path, {"endpoint": endpoint, "corpus": corpus, "request": body,
                                                    "response": resp, "at": _now()})
                                try:
                                    os.unlink(attempt_path)
                                except OSError:
                                    pass
                            if (resp.get("runs_used") or 0) >= STOP_AT_USED:
                                stopped = "stopped at %d runs used to keep the rest of the budget for people" % resp["runs_used"]
            else:
                why = stopped
        if resp is not None:
            problem = _response_problem(resp, len(body["golden_set"]), expected_metric)
            if problem:
                why, resp = "%s; cached result discarded without a retry" % problem, None
        if resp is None:
            notes.append("%s not verified: %s" % (p["id"], why))
            trace.append(dict(row, status="unverified", reason=why, request_sha256=key))
            continue
        verdict = resp["verdict"]
        golden = resp["golden_set"]
        g, g_why = gate(verdict, golden.get("pass"))
        v = {"prescription_id": p["id"], "replay_run_id": resp["run_id"], "metric": resp.get("metric"),
             "before": resp.get("before"), "after": resp.get("after"), "golden_set_pass": golden.get("pass"),
             "verdict": verdict, "simulated": True, "simulation_note": SIMULATION_NOTE,
             "golden_set_version": gs.get("golden_set_version"), "golden_set_replayed": golden.get("replayed"),
             "golden_set_regressed": golden.get("regressed"), "sessions_replayed_simulated": resp.get("sessions_replayed"),
             "replayed_window": [body["cohort"]["from_day"], body["cohort"]["to_day"] - 1],
             "gate": g, "gate_reason": g_why, "request_sha256": key, "from_cache": cached,
             "runs_used": resp.get("runs_used"), "fix_id": p.get("fix_id")}
        if verdict == "no_effect":
            v["no_effect_meaning"] = NO_EFFECT_MEANING
        observed = (resp.get("after") - resp.get("before")) if None not in (resp.get("after"), resp.get("before")) else None
        pred = predicted_replay_delta(p, resp.get("before"))
        if pred is not None and observed is not None:
            v["predicted_delta"] = round(pred, 4)
            v["observed_delta"] = round(observed, 4)
            v["prediction_error"] = round(pred - observed, 4)
        verifications.append(v)
        trace.append(dict(row, status="verified", run_id=resp["run_id"], from_cache=cached, verdict=verdict, gate=g))
    if verifications:
        notes.append(SIMULATION_NOTE)
    return verifications, notes, trace
