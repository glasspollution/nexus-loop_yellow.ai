"""The product half on the practice kit: decision packets, evidence consistency, standard + golden set, prescriptions,
replay verification against the organisers' service, self-assessment, the approval write-back and the screen API."""
import copy
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from conftest import PRACTICE_KIT, TOOLS
from nexus import decisions, replay, screen, selfassess, standard
from nexus.pipeline import write_outputs
from nexus.validate import contract_problems, schema_errors

REPLAY_METRICS = {"resolution_rate", "median_turns"}


def _regressions(rep):
    return [f for f in rep["findings"] if f["is_regression"]]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_every_regression_carries_a_decision_packet(practice):
    rep = practice["report_json"]
    defs = {d["id"] for d in rep["definitions"]}
    regs = _regressions(rep)
    assert regs
    for f in regs:
        imp = f["impact"]
        ds = imp["downstream"]
        assert imp["conversations_affected"] > 0 and 0 < imp["share_of_traffic"] <= 1
        assert 0 <= ds["conversations_hit"] <= imp["conversations_affected"]
        assert ds["unplanned_handoffs"] <= ds["unplanned_handoffs_total"]
        lo, hi = ds["would_have_resolved_at_baseline_ci95"]
        assert lo <= ds["would_have_resolved_at_baseline"] + 1 and ds["would_have_resolved_at_baseline"] - 1 <= hi
        assert imp["baseline"]["kind"] in ("own_past", "peers_same_journey", "rest_of_tenant") and imp["baseline"]["why"]
        assert imp["status"]["state"] in ("ongoing", "ended", "persisting", "unknown") and imp["status"]["sentence"]
        assert "BASELINE:" in imp["derivation"] and "WINDOW:" in imp["derivation"]
        assert f["if_nothing_changes"] and f["severity"] in ("low", "medium", "high", "critical")
        for fig in imp["figures"]:
            assert fig["def"] in defs
            if fig.get("definition_ref"):
                assert fig["definition_ref"] in defs
        if imp["status"]["state"] == "ended":
            assert imp["projection"] is None
    assert len({tuple(f["audience"]) for f in regs}) > 1, "audience must follow the cause, not be a constant"


def test_evidence_is_self_consistent_and_stays_in_its_incident(practice):
    rep = practice["report_json"]
    for f in _regressions(rep):
        lo, hi = f["impact"]["windows"]["impact"]
        refs = f.get("evidence_refs")
        assert refs
        for r in refs:
            assert r["from"] <= hi and r["to"] >= min(lo, f["window"]["from_day"]), r["line"]
            if r["current"] is None or r["baseline"] is None:
                continue
            assert abs(r["change"]["abs"] - (r["current"] - r["baseline"])) < 1e-9
            if abs(r["baseline"]) < 1e-12:
                assert r["change"]["rel"] is None and "absent before" in r["line"]
            else:
                assert abs(r["change"]["rel"] - (r["current"] - r["baseline"]) / abs(r["baseline"])) < 1e-9
        assert all("+100%" not in line or "(+100%" in line for line in f["evidence"])


def test_finding_metric_and_observed_come_from_the_primary_window(practice):
    rep = practice["report_json"]
    for f in _regressions(rep):
        assert f["metric"] != "n/a" and "observed" in f and f["observed_basis"].startswith(f["metric"])


def test_prescriptions_are_decisions_on_the_replay_metric(practice):
    rep = practice["report_json"]
    diag = {d["id"]: d for d in rep["diagnoses"]}
    assert rep["prescriptions"]
    for p in rep["prescriptions"]:
        assert "approval" not in p and p["fix_id"].startswith("fx_")
        assert p["predicted_delta"]["metric"] in REPLAY_METRICS and p["predicted_delta"]["to"] is not None
        cause = diag[p["diagnosis_id"]]["cause_class"]
        assert (p["predicted_delta"]["metric"] == "median_turns") == cause.startswith("prompt")
        for key in ("asking_approval_for", "risk_if_diagnosis_wrong", "would_not_ship_if", "trade_off"):
            assert p["decision"][key]
        assert re.search(r"\d", p["decision"]["asking_approval_for"]), "the ask must carry the finding's own numbers"
        assert "{" not in p["description"]
        if p["change_type"] != "no_action":
            assert any(a["change_type"] == "no_action" for a in p["alternatives"])


def test_standard_and_golden_set_are_deterministic_and_frozen(practice):
    rep = practice["report_json"]
    assert rep["standard"] and all({"cohort", "metric", "best", "median"} <= set(s) for s in rep["standard"])
    gs = rep["standard_manifest"]["golden_sets"]
    sids = set(practice["counters"]["S"]["sid"].tolist())
    for ten, g in gs.items():
        assert 20 <= g["n"] <= 30 and set(g["session_ids"]) <= sids
        assert set(g["outcome_reviewed_ids"]) | set(g["machine_selected_ids"]) == set(g["session_ids"])
    entries, manifest, _ = standard.mine(practice["counters"], practice["incidents"])
    assert manifest["manifest_sha256"] == rep["standard_manifest"]["manifest_sha256"]
    # a newborn cohort's standard comes from its journey peers, never from its own broken days
    for f in _regressions(rep):
        if f["impact"]["baseline"]["kind"] == "peers_same_journey":
            gap = next(p for p in rep["prescriptions"] if p["diagnosis_id"] == "d" + f["id"][1:])["standard_gap"]
            assert gap and all("peers" in r["basis"] for r in gap)


def test_catalog_contradictions_are_reported_not_trusted(practice):
    rep = practice["report_json"]
    for c in rep["data_contradictions"]:
        assert c["steps"] > 0 and c["agent_kind"] in practice["counters"]["no_step_kinds"]
    if rep["data_contradictions"]:
        assert "Catalog vs data" in rep["system_notes"]


def test_decision_writeback(practice, tmp_path):
    out = str(tmp_path / "out")
    write_outputs(practice, out)
    gen_sha = decisions.sha_file(os.path.join(out, decisions.GENERATED))
    rep0 = json.load(open(os.path.join(out, decisions.REPORT), encoding="utf-8"))
    p1, p2 = rep0["prescriptions"][0], rep0["prescriptions"][-1]
    with pytest.raises(decisions.DecisionError) as e:
        decisions.record(out, p1["id"], "accepted", "ops lead", "   ")
    assert e.value.status == 400
    with pytest.raises(decisions.DecisionError) as e:
        decisions.record(out, p1["id"], "maybe", "ops lead", "x")
    assert e.value.status == 400
    with pytest.raises(decisions.DecisionError) as e:
        decisions.record(out, p1["id"], "accepted", "ops lead", "x", seen_proposal_sha="stale")
    assert e.value.status == 409
    for decided_by, reason in ((123, "x"), ("ops lead", ["not", "text"])):
        with pytest.raises(decisions.DecisionError) as e:
            decisions.record(out, p1["id"], "accepted", decided_by, reason)
        assert e.value.status == 400
    decisions.record(out, p1["id"], "accepted", "ops lead", "Every lookup in the slice missed; content is cheap.",
                     seen_generated_sha=gen_sha, rebuild=lambda r: screen.write(out, r))
    res = decisions.record(out, p2["fix_id"], "rejected", "ops lead", "Keeps the stated purpose of the change.",
                           rebuild=lambda r: screen.write(out, r))
    dup = decisions.record(out, p2["fix_id"], "rejected", "ops lead", "Keeps the stated purpose of the change.")
    assert dup["duplicate"] and len(decisions.read_events(out)) == 2
    rep = json.load(open(os.path.join(out, decisions.REPORT), encoding="utf-8"))
    assert schema_errors(rep) == [] and contract_problems(rep) == []
    got = {p["id"]: (p.get("approval") or {}).get("verdict") for p in rep["prescriptions"]}
    assert got[p1["id"]] == "accepted" and got[p2["id"]] == "rejected" and set(res["applied"]) == {p1["id"], p2["id"]}
    generated = json.load(open(os.path.join(out, decisions.GENERATED), encoding="utf-8"))
    assert all("approval" not in p for p in generated["prescriptions"]), "the system output is never edited"
    scr = json.load(open(os.path.join(out, screen.SCREEN_FILE), encoding="utf-8"))
    assert {c["approval"]["state"] for c in scr["findings"] if c["proposal"]} >= {"accepted", "rejected"}
    # a regenerated report that re-orders prescriptions keeps each decision on its own fix
    regen = copy.deepcopy(generated)
    regen["prescriptions"].reverse()
    json.dump(regen, open(os.path.join(out, decisions.GENERATED), "w", encoding="utf-8"), indent=1)
    decisions.materialise(out)
    rep2 = json.load(open(os.path.join(out, decisions.REPORT), encoding="utf-8"))
    by_fix = {p["fix_id"]: (p.get("approval") or {}).get("verdict") for p in rep2["prescriptions"]}
    assert by_fix[p1["fix_id"]] == "accepted" and by_fix[p2["fix_id"]] == "rejected"
    # a changed proposal is not approved by an old decision
    changed = copy.deepcopy(generated)
    next(p for p in changed["prescriptions"] if p["fix_id"] == p1["fix_id"])["decision"]["trade_off"] = "different"
    json.dump(changed, open(os.path.join(out, decisions.GENERATED), "w", encoding="utf-8"), indent=1)
    r3 = decisions.materialise(out)
    assert p1["id"] not in r3["applied"] and any(x["fix_id"] == p1["fix_id"] for x in r3["needs_reconfirmation"])


def test_decision_validation_failure_does_not_append_event(practice, tmp_path, monkeypatch):
    out = str(tmp_path / "out")
    write_outputs(practice, out)
    generated = json.load(open(os.path.join(out, decisions.GENERATED), encoding="utf-8"))
    p = generated["prescriptions"][0]
    monkeypatch.setattr(decisions, "schema_errors", lambda report: ["forced validation failure"])
    with pytest.raises(decisions.DecisionError) as exc:
        decisions.record(out, p["id"], "accepted", "Ops lead", "Evidence is sufficient.",
                         seen_proposal_sha=decisions.proposal_sha(generated, p))
    assert exc.value.status == 422
    assert decisions.read_events(out) == []


def test_selfassess_guard_qualified_hits_and_ledger(tmp_path):
    rep = {"prescriptions": [{"id": "p1", "change_type": "kb.add"}, {"id": "p2", "change_type": "kb.add"},
                             {"id": "p3", "change_type": "prompt.edit"}],
           "verifications": [{"prescription_id": "p1", "replay_run_id": "rp_1", "verdict": "improved",
                              "golden_set_pass": True, "prediction_error": -0.02},
                             {"prescription_id": "p2", "replay_run_id": "rp_2", "verdict": "improved",
                              "golden_set_pass": False, "prediction_error": 0.04},
                             {"prescription_id": "p3", "replay_run_id": "rp_3", "verdict": "no_effect",
                              "golden_set_pass": True}]}
    ledger = str(tmp_path / "ledger.jsonl")
    sa, rec = selfassess.assess(rep, "corpus-a", ["p4 not verified: endpoint unreachable"], ledger)
    assert sa["cycles"] == 1 and sa["downweighted"] == []
    assert sa["prescription_accuracy"]["kb.add"] == {"n": 2, "hits": 1, "hit_rate": 0.5, "mean_prediction_error": 0.01,
                                                     "prediction_error_units": sa["prescription_accuracy"]["kb.add"]["prediction_error_units"]}
    assert sa["prescription_accuracy"]["prompt.edit"]["hit_rate"] == 0.0
    assert selfassess.append_batch(ledger, rec) and not selfassess.append_batch(ledger, rec)
    same, _ = selfassess.assess(rep, "corpus-a", (), ledger)
    other, _ = selfassess.assess(rep, "corpus-b", (), ledger)
    assert same["prior_cycles_on_other_corpora"] == {} and other["prior_cycles_on_other_corpora"]["kb.add"]["n"] == 2
    assert other["cycles"] == 1, "prior cycles on other corpora never inflate this corpus's cycles"


@pytest.fixture(scope="module")
def replay_server():
    gt = os.path.join(PRACTICE_KIT, "ground_truth", "ground_truth.json")
    serve = os.path.join(TOOLS, "replay", "serve.py")
    if not (os.path.exists(gt) and os.path.exists(serve)):
        pytest.skip("replay service or practice ground truth not available")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, serve, "--kit", PRACTICE_KIT, "--port", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = "http://127.0.0.1:%d" % port
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/health", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    yield url
    proc.kill()


def _runs_used(url, team):
    return json.loads(urllib.request.urlopen(url + "/log").read())["used"].get(team, 0)


def test_replay_verifies_every_fix_and_never_spends_twice(practice, replay_server, tmp_path):
    rep = copy.deepcopy(practice["report_json"])
    gs = rep["standard_manifest"]["golden_sets"]
    cache = str(tmp_path / "cache")
    ver, notes, trace = replay.verify(rep, gs, replay_server, "pytest-team", cache, "practice", max_calls=8)
    fmap, dmap = {f["id"]: f for f in rep["findings"]}, {d["id"]: d for d in rep["diagnoses"]}
    eligible = [p for p in rep["prescriptions"] if p["change_type"] != "no_action"
                and fmap[dmap[p["diagnosis_id"]]["finding_id"]]["cohort"]]
    assert len(ver) == len(eligible) and _runs_used(replay_server, "pytest-team") == len(eligible)
    for v in ver:
        assert v["replay_run_id"].startswith("rp_") and v["simulated"] is True
        assert v["verdict"] == "improved", v
        assert v["gate"] in ("candidate", "blocked_golden_set") and "prediction_error" in v
    again, _, trace2 = replay.verify(rep, gs, replay_server, "pytest-team", cache, "practice", max_calls=8)
    assert [v["replay_run_id"] for v in again] == [v["replay_run_id"] for v in ver]
    assert all(v["from_cache"] for v in again) and _runs_used(replay_server, "pytest-team") == len(eligible)
    rep["verifications"] = ver
    sa, _ = selfassess.assess(rep, "practice")
    rep["self_assessment"] = sa
    assert schema_errors(rep) == [] and contract_problems(rep) == []


def test_replay_unreachable_fabricates_nothing(practice, tmp_path):
    rep = practice["report_json"]
    ver, notes, trace = replay.verify(rep, rep["standard_manifest"]["golden_sets"], "http://127.0.0.1:%d" % _free_port(),
                                      "t", str(tmp_path / "c"), "practice", timeout=2)
    assert ver == [] and notes and all(t["status"] in ("unverified", "skipped") for t in trace)
    ver, notes, _ = replay.verify(rep, rep["standard_manifest"]["golden_sets"], None, "t", None, "practice")
    assert ver == [] and any("no replay endpoint" in n for n in notes)


def test_screen_formats_verified_replay_values_without_changing_raw_values(practice):
    rep = copy.deepcopy(practice["report_json"])
    batch_screen = screen.build(rep)
    assert batch_screen["source"]["mode"] == "batch-artifact"
    assert batch_screen["source"]["report"] == "loop-report.json"
    resolution = next(p for p in rep["prescriptions"]
                      if p["predicted_delta"]["metric"] == "resolution_rate")
    turns = next(p for p in rep["prescriptions"]
                 if p["predicted_delta"]["metric"] == "median_turns")
    rep["verifications"] = [
        {"prescription_id": resolution["id"], "replay_run_id": "rp_rate", "metric": "resolution_rate",
         "before": 0.7123, "after": 0.8011, "observed_delta": 0.0888,
         "verdict": "improved", "gate": "candidate"},
        {"prescription_id": turns["id"], "replay_run_id": "rp_turns", "metric": "median_turns",
         "before": 7.25, "after": 5.10, "observed_delta": -2.15,
         "verdict": "improved", "gate": "candidate"},
    ]

    cards = {c["proposal"]["prescription_id"]: c for c in screen.build(rep)["findings"] if c["proposal"]}
    rate = cards[resolution["id"]]["verification"]
    assert (rate["metric_label"], rate["before_display"], rate["after_display"],
            rate["observed_delta_display"]) == ("Resolution rate", "71.2%", "80.1%", "+8.9 pp")
    assert (rate["before"], rate["after"], rate["observed_delta"]) == (0.7123, 0.8011, 0.0888)

    median = cards[turns["id"]]["verification"]
    assert (median["metric_label"], median["before_display"], median["after_display"],
            median["observed_delta_display"]) == ("Median turns", "7.25 turns", "5.10 turns", "-2.15 turns")
    assert (median["before"], median["after"], median["observed_delta"]) == (7.25, 5.10, -2.15)


def test_screen_keeps_unverified_replay_truthful(practice):
    rep = copy.deepcopy(practice["report_json"])
    prescription = rep["prescriptions"][0]
    reason = "no replay endpoint configured"
    rep["verifications"] = []
    rep["self_assessment"] = {"unverified": ["%s not verified: %s" % (prescription["id"], reason)]}

    card = next(c for c in screen.build(rep)["findings"]
                if c.get("proposal", {}).get("prescription_id") == prescription["id"])
    assert card["verification"] is None, "replay must not appear before approval"


def _single_replay_case():
    report = {
        "findings": [{"id": "f1", "is_regression": True, "tenant": "tenant-a", "cohort": {"intent": "billing"},
                      "window": {"from_day": 3, "to_day": 4}}],
        "diagnoses": [{"id": "d1", "finding_id": "f1"}],
        "prescriptions": [{"id": "p1", "fix_id": "fx_1", "diagnosis_id": "d1", "change_type": "kb.add",
                           "target": "billing article", "replay_prediction": {"metric": "resolution_rate",
                           "healthy_level": 0.8, "in_window_level": 0.5, "gap_fraction": 0.8}}],
    }
    golden = {"tenant-a": {"golden_set_version": "v1", "session_ids": ["s1"]}}
    return report, golden


def _cached_replay_path(cache, report, golden, endpoint="http://replay.invalid"):
    finding, prescription = report["findings"][0], report["prescriptions"][0]
    body = replay.build_request("team", finding, prescription, golden["tenant-a"]["session_ids"])
    return cache / (replay.request_key(endpoint, "corpus", body) + ".json")


def _valid_replay_response():
    return {"run_id": "rp_1", "verdict": "improved", "metric": "resolution_rate", "before": 0.5,
            "after": 0.7, "golden_set": {"replayed": 1, "regressed": 0, "pass": True},
            "runs_used": 1, "sessions_replayed": 10}


def test_replay_corrupt_and_malformed_cache_is_unverified_without_retry(tmp_path, monkeypatch):
    report, golden = _single_replay_case()
    endpoint = "http://replay.invalid"
    monkeypatch.setattr(replay, "_http", lambda *args, **kwargs: pytest.fail("cached calls must never hit the network"))
    valid = _valid_replay_response()
    malformed = [None, [], dict(valid, verdict="maybe"), dict(valid, metric="made_up"),
                 dict(valid, metric="median_turns", before=5.0, after=4.0),
                 dict(valid, before="0.5"), dict(valid, after=2.0), dict(valid, golden_set=[]),
                 dict(valid, golden_set={"replayed": 1, "regressed": 1, "pass": True})]
    for index, response in enumerate(malformed):
        cache = tmp_path / str(index)
        cache.mkdir()
        _cached_replay_path(cache, report, golden).write_text(json.dumps({"response": response}), encoding="utf-8")
        verifications, notes, trace = replay.verify(report, golden, endpoint, "team", str(cache), "corpus")
        assert verifications == [] and notes
        assert trace[0]["status"] == "unverified"
        assert "discarded" in trace[0]["reason"] or "not retried" in trace[0]["reason"]
    cache = tmp_path / "corrupt"
    cache.mkdir()
    _cached_replay_path(cache, report, golden).write_text("{not-json", encoding="utf-8")
    verifications, notes, trace = replay.verify(report, golden, endpoint, "team", str(cache), "corpus")
    assert verifications == [] and notes and trace[0]["status"] == "unverified"
    assert "unreadable" in trace[0]["reason"] and "not retried" in trace[0]["reason"]


def test_replay_failed_post_leaves_durable_no_retry_marker(tmp_path, monkeypatch):
    report, golden = _single_replay_case()
    calls = []

    def fail_post(url, body=None, timeout=20):
        calls.append((url, body))
        if body is None:
            return {"ok": True}
        raise urllib.error.URLError("ambiguous timeout")

    monkeypatch.setattr(replay, "_http", fail_post)
    cache = tmp_path / "cache"
    first, notes, trace = replay.verify(report, golden, "http://replay.invalid", "team", str(cache), "corpus")
    assert first == [] and len(calls) == 2 and list(cache.glob("*.attempt.json"))
    calls.clear()
    second, notes, trace = replay.verify(report, golden, "http://replay.invalid", "team", str(cache), "corpus")
    assert second == [] and calls == []
    assert "prior replay attempt" in trace[0]["reason"] and "not retried" in trace[0]["reason"]


def test_replay_malformed_live_response_is_not_cached_or_retried(tmp_path, monkeypatch):
    report, golden = _single_replay_case()
    responses = ([], dict(_valid_replay_response(), verdict="invented"),
                 dict(_valid_replay_response(), metric="median_turns", before=5.0, after=4.0))
    for index, response in enumerate(responses):
        calls = []

        def malformed(url, body=None, timeout=20):
            calls.append((url, body))
            return {"ok": True} if body is None else response

        monkeypatch.setattr(replay, "_http", malformed)
        cache = tmp_path / str(index)
        first, notes, trace = replay.verify(report, golden, "http://replay.invalid", "team", str(cache), "corpus")
        assert first == [] and len(calls) == 2 and trace[0]["status"] == "unverified"
        assert not _cached_replay_path(cache, report, golden).exists() and list(cache.glob("*.attempt.json"))
        calls.clear()
        second, notes, trace = replay.verify(report, golden, "http://replay.invalid", "team", str(cache), "corpus")
        assert second == [] and calls == [] and "not retried" in trace[0]["reason"]


def test_replay_health_failure_does_not_poison_later_attempt(tmp_path, monkeypatch):
    report, golden = _single_replay_case()
    cache = tmp_path / "cache"
    monkeypatch.setattr(replay, "_http", lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("down")))
    first, _, _ = replay.verify(report, golden, "http://replay.invalid", "team", str(cache), "corpus")
    assert first == [] and not list(cache.glob("*.attempt.json"))

    calls = []

    def recovered(url, body=None, timeout=20):
        calls.append((url, body))
        return {"ok": True} if body is None else _valid_replay_response()

    monkeypatch.setattr(replay, "_http", recovered)
    second, _, trace = replay.verify(report, golden, "http://replay.invalid", "team", str(cache), "corpus")
    assert len(second) == 1 and len(calls) == 2 and trace[0]["status"] == "verified"


def test_live_replay_mode_writes_no_cache_attempt_or_ledger(tmp_path, monkeypatch):
    report, golden = _single_replay_case()
    calls = []

    def successful(url, body=None, timeout=20):
        calls.append((url, body))
        return {"ok": True} if body is None else _valid_replay_response()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(replay, "_http", successful)
    verified, _, trace = replay.verify(report, golden, "http://replay.invalid", "session-team",
                                       cache_dir=None, corpus="corpus", max_calls=1)
    assert len(verified) == 1 and trace[0]["status"] == "verified" and len(calls) == 2
    assert list(tmp_path.iterdir()) == [], "non-persistent replay must not create a cache, marker, or ledger"


def test_server_api_keeps_decisions_ephemeral_and_replays_only_approval(practice, tmp_path):
    import server
    from nexus.live_session import LiveSession

    out = str(tmp_path / "srv")
    write_outputs(practice, out)
    before = {str(path.relative_to(out)): (path.read_bytes(), path.stat().st_mtime_ns)
              for path in (tmp_path / "srv").iterdir() if path.is_file()}
    replay_calls = []

    def fake_replay(report, golden_sets, **kwargs):
        replay_calls.append((copy.deepcopy(report), copy.deepcopy(golden_sets), kwargs))
        prescription = report["prescriptions"][0]
        result = {"prescription_id": prescription["id"], "replay_run_id": "rp_live_test",
                  "metric": "resolution_rate", "before": 0.5, "after": 0.7,
                  "observed_delta": 0.2, "verdict": "improved", "gate": "candidate",
                  "gate_reason": "the replay improved the metric and the golden set held",
                  "golden_set_pass": True, "simulated": True}
        return [result], [], [{"prescription_id": prescription["id"], "status": "verified"}]

    workflow = LiveSession.from_report(practice["report_json"], replay_url="http://replay.invalid",
                                       verifier=fake_replay, corpus_id=practice["corpus_id"])
    httpd = server.serve(out, "127.0.0.1", 0, None, workflow=workflow)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % port
    try:
        scr = json.loads(urllib.request.urlopen(base + "/api/screen").read())
        cards = [c for c in scr["findings"] if c["proposal"]]
        card, approved_card = cards[0], cards[1]
        assert card["impact"]["figures"][0]["definition"] and scr["disclosures"]["simulated"]
        assert scr["source"]["mode"] == "live-session" and scr["source"]["report"] == "session-memory"
        assert all(c["verification"] is None for c in cards)

        def post(body):
            req = urllib.request.Request(base + "/api/decisions", data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            try:
                return 200, json.loads(urllib.request.urlopen(req).read())
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read())

        code, _ = post(["not", "an", "object"])
        assert code == 400
        code, _ = post({"prescription_id": card["proposal"]["prescription_id"], "verdict": "accepted", "decided_by": "x"})
        assert code == 400
        code, body = post({"prescription_id": card["proposal"]["prescription_id"], "verdict": "rejected",
                           "decided_by": "Ops lead", "reason": "Needs business sign-off first."})
        assert code == 400 and "proposal_sha" in body["error"]
        for decided_by, reason in ((123, "valid reason"), ("Ops lead", ["not", "text"])):
            code, _ = post({"prescription_id": card["proposal"]["prescription_id"], "verdict": "rejected",
                            "decided_by": decided_by, "reason": reason,
                            "proposal_sha": card["proposal"]["proposal_sha"],
                            "generated_report_sha256": scr["source"]["generated_report_sha256"]})
            assert code == 400
        code, body = post({"prescription_id": card["proposal"]["prescription_id"], "verdict": "rejected",
                           "decided_by": "Ops lead", "reason": "Needs business sign-off first.",
                           "proposal_sha": card["proposal"]["proposal_sha"],
                           "generated_report_sha256": scr["source"]["generated_report_sha256"]})
        assert code == 200
        after = next(c for c in body["screen"]["findings"] if c["finding_id"] == card["finding_id"])
        assert after["approval"]["state"] == "rejected" and after["verification"] is None
        assert replay_calls == [], "reject must not run or apply a proposal"

        # A stale screen cannot race a later decision.
        code, _ = post({"prescription_id": approved_card["proposal"]["prescription_id"], "verdict": "accepted",
                        "decided_by": "Ops lead", "reason": "Proceed with the proposed change.",
                        "proposal_sha": approved_card["proposal"]["proposal_sha"],
                        "generated_report_sha256": scr["source"]["generated_report_sha256"]})
        assert code == 409 and replay_calls == []

        current = body["screen"]
        approved_card = next(c for c in current["findings"] if c["finding_id"] == approved_card["finding_id"])
        code, accepted = post({"prescription_id": approved_card["proposal"]["prescription_id"],
                               "verdict": "accepted", "decided_by": "Ops lead",
                               "reason": "Proceed with the proposed change.",
                               "proposal_sha": approved_card["proposal"]["proposal_sha"],
                               "generated_report_sha256": current["source"]["generated_report_sha256"]})
        assert code == 200 and len(replay_calls) == 1
        accepted_card = next(c for c in accepted["screen"]["findings"]
                             if c["finding_id"] == approved_card["finding_id"])
        assert accepted_card["approval"]["state"] == "accepted"
        assert accepted_card["verification"]["replay_run_id"] == "rp_live_test"
        assert accepted["result"]["replay_status"] == "completed"

        # Editing the approval receipt does not spend a second replay or lose
        # the outcome that was generated by the first approval.
        approved_screen = accepted["screen"]
        approved_card = next(c for c in approved_screen["findings"] if c["finding_id"] == approved_card["finding_id"])
        code, edited = post({"prescription_id": approved_card["proposal"]["prescription_id"],
                             "verdict": "accepted", "decided_by": "Ops lead",
                             "reason": "Approved after final review.",
                             "proposal_sha": approved_card["proposal"]["proposal_sha"],
                             "generated_report_sha256": approved_screen["source"]["generated_report_sha256"]})
        edited_card = next(c for c in edited["screen"]["findings"] if c["finding_id"] == approved_card["finding_id"])
        assert code == 200 and len(replay_calls) == 1
        assert edited_card["verification"]["replay_run_id"] == "rp_live_test"

        rep = json.loads(urllib.request.urlopen(base + "/api/report").read())
        assert {p.get("approval", {}).get("verdict") for p in rep["prescriptions"]} >= {"accepted", "rejected"}
        gen = json.loads(urllib.request.urlopen(base + "/api/report/generated").read())
        assert all("approval" not in p for p in gen["prescriptions"]) and gen["verifications"] == []
        assert len(json.loads(urllib.request.urlopen(base + "/api/decisions").read())) == 3
        after_files = {str(path.relative_to(out)): (path.read_bytes(), path.stat().st_mtime_ns)
                       for path in (tmp_path / "srv").iterdir() if path.is_file()}
        assert after_files == before, "live review must not mutate any output artifact"
    finally:
        httpd.shutdown()


def _raw_http(port, request):
    with socket.create_connection(("127.0.0.1", port), timeout=2) as conn:
        conn.sendall(request)
        conn.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    response = b"".join(chunks)
    return int(response.split(b" ", 2)[1]), response.split(b"\r\n\r\n", 1)[-1]


def test_server_rejects_bad_content_lengths_and_contains_static_paths(tmp_path):
    import server
    static = tmp_path / "static"
    sibling = tmp_path / "static-private"
    static.mkdir()
    sibling.mkdir()
    (static / "index.html").write_text("safe index", encoding="utf-8")
    (sibling / "secret.txt").write_text("do not serve", encoding="utf-8")
    httpd = server.serve(str(tmp_path / "out"), "127.0.0.1", 0, str(static))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        request = urllib.request.Request("http://127.0.0.1:%d/api/decisions" % port, method="OPTIONS")
        with pytest.raises(urllib.error.HTTPError) as preflight:
            urllib.request.urlopen(request)
        assert preflight.value.code == 405
        assert preflight.value.headers.get("Access-Control-Allow-Origin") is None
        code, _ = _raw_http(port, b"POST /api/decisions HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
        assert code == 411
        for value, expected in ((b"wat", 400), (b"-1", 400), (str(server.MAX_BODY + 1).encode(), 413)):
            code, _ = _raw_http(port, b"POST /api/decisions HTTP/1.1\r\nHost: localhost\r\nContent-Length: " +
                                value + b"\r\nConnection: close\r\n\r\n")
            assert code == expected
        code, body = _raw_http(port, b"GET /../static-private/secret.txt HTTP/1.1\r\nHost: localhost\r\n"
                                     b"Connection: close\r\n\r\n")
        assert code == 200 and b"safe index" in body and b"do not serve" not in body
    finally:
        httpd.shutdown()
