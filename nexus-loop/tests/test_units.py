"""Fast checks that need no corpus."""
import json

from nexus.config import CFG, SCALES
from nexus.loader import _fingerprint, direction_of, is_bin
from nexus.validate import contract_problems, schema_errors


def test_parameters_match_handoff_14_2():
    assert CFG == dict(Z=4.0, MATERIAL_REL=0.10, MATERIAL_ABS=0.01, MIN_RUN=3, CUR=3, BASE=15, BASE_MIN_DAYS=3,
                       MIN_N_CUR=30, MIN_N_BASE=60, DAY_MIN_N=5, NEWBORN_DAY=2, PHI_WINDOW=7, SUPPORT_FRAC=0.5)
    assert SCALES == (3, 7)


def test_metric_kind_and_direction():
    assert is_bin("tool_call.empty") and is_bin("s.resolved") and not is_bin("s.turns")
    assert direction_of("s.resolved") == -1 and direction_of("s.turns") == +1
    assert direction_of("s.quality_score@v2") == -1


def test_cache_key_differs_for_same_folder_name_in_different_places(tmp_path):
    a, b = tmp_path / "one" / "kit", tmp_path / "two" / "kit"
    for d in (a, b):
        d.mkdir(parents=True)
        (d / "catalog.json").write_text("{}")
    assert _fingerprint(str(a)) != _fingerprint(str(b))


def _minimal_report():
    return {"team": "t", "corpus": "A",
            "metrics": [{"id": "m1", "ask_id": "A01", "fidelity": "measured", "grain": "session", "name": "x",
                         "coverage": {"value": 1.0, "basis": "b"},
                         "plan": {"source": "s", "filter": "f", "denominator": "d"}}],
            "findings": [{"id": "f1", "tenant": "t", "cohort": {}, "metric": "m", "window": {"from_day": 1, "to_day": 2},
                          "is_regression": False, "not_a_regression_because": "mix"}],
            "diagnoses": [{"id": "d1", "finding_id": "f1", "cause_class": "traffic_mix"}],
            "prescriptions": [], "gaps": []}


def test_gate_accepts_a_valid_minimal_report():
    rep = _minimal_report()
    assert schema_errors(rep) in ([], None)
    assert contract_problems(rep) == []


def test_gate_rejects_placeholder_approval_and_perfect_calibration():
    rep = _minimal_report()
    rep["findings"][0].update(is_regression=True)
    rep["prescriptions"] = [{"id": "p1", "diagnosis_id": "d1", "change_type": "kb.add", "target": "x",
                             "predicted_delta": {"metric": "m", "from": 0.3, "to": 0.8},
                             "decision": {"asking_approval_for": "a", "risk_if_diagnosis_wrong": "r", "would_not_ship_if": "w"},
                             "approval": {"verdict": "deferred", "decided_by": "pending", "reason": "none", "at": None}}]
    rep["metrics"][0]["calibration"] = {"agreement": 1.0, "n": 10}
    errs, probs = schema_errors(json.loads(json.dumps(rep))), contract_problems(rep)
    assert errs is None or any("approval/at" in e for e in errs)
    text = " ".join(probs)
    assert "approval" in text and "calibration" in text and "impact" in text
