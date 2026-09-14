"""The deliverable on the practice kit: schema, report contract, honesty fields, refusals, and score.py."""
import json
import os
import re
import subprocess
import sys

import pytest

from conftest import PRACTICE_KIT, ROOT, TOOLS
from nexus.validate import contract_problems, schema_errors


def test_schema_and_contract(practice):
    rep = practice["report_json"]
    assert schema_errors(rep) == []
    assert contract_problems(rep) == []


def test_required_sections_and_asks(practice):
    rep = practice["report_json"]
    for key in ("team", "corpus", "metrics", "findings", "diagnoses", "gaps"):
        assert key in rep
    text = json.dumps(rep)
    for ask in ("A01", "A04", "A09", "A11"):
        assert '"%s"' % ask in text


def test_no_placeholder_approval(practice):
    assert all("approval" not in p for p in practice["report_json"]["prescriptions"])


def test_tool_metrics_per_tenant_with_their_own_coverage(practice):
    rep, cov = practice["report_json"], practice["counters"]["coverage"]
    tool = [m for m in rep["metrics"] if "tool_call" in m["plan"]["source"]]
    assert len(tool) == 2 * len(cov)
    for m in tool:
        tenant = re.search(r"tenant = '([^']+)'", m["plan"]["filter"]).group(1)
        assert m["coverage"]["value"] == cov[tenant]


def test_a09_judged_without_borrowed_calibration(practice):
    rep = practice["report_json"]
    a09 = next(m for m in rep["metrics"] if m["ask_id"] == "A09")
    assert a09["fidelity"] == "judged" and a09["calibration"] is None
    gap = next(g for g in rep["gaps"] if g["ask_id"] == "A09")
    assert gap["verdict"] == "REQUIRES_NEW_JUDGE" and gap["required_event"]["fields"]


def test_a11_refused_with_catalog_event(practice):
    rep, cat = practice["report_json"], practice["counters"]["catalog"]
    cap = next(c for c in cat["capabilities"] if c.get("class") == "NOT_MEASURABLE")
    gap = next(g for g in rep["gaps"] if g["ask_id"] == "A11")
    assert gap["verdict"] == "NOT_MEASURABLE"
    assert set(cap["required_event"]["fields"]) <= set(gap["required_event"]["fields"])


def test_over_budget_breakdown_refused(practice):
    rep = practice["report_json"]
    refused = [c["field"] for c in practice["counters"]["cardinality"] if c["refused"]]
    assert refused
    for m in rep["metrics"]:
        assert all(any(r.startswith(f) for r in m["plan"]["refused_breakdowns"]) for f in refused)
    assert all(f in rep["system_notes"] for f in refused)


def test_lookalikes_dismissed_with_the_scorer_strings(practice):
    rep = practice["report_json"]
    dismissed = {d["cause_class"] for d in rep["diagnoses"]
                 if not next(f for f in rep["findings"] if f["id"] == d["finding_id"])["is_regression"]}
    assert {"traffic_mix", "load", "judge_change"} <= dismissed


@pytest.mark.skipif(not os.path.exists(os.path.join(TOOLS, "score.py")), reason="score.py not found")
def test_cli_scores_55_on_practice(tmp_path):
    out = tmp_path / "out"
    p = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"), "--kit", PRACTICE_KIT, "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stdout[-2000:]
    s = subprocess.run([sys.executable, "score.py", "--report", str(out / "loop-report.json"), "--ground-truth",
                        os.path.join(PRACTICE_KIT, "ground_truth", "ground_truth.json"), "--json"],
                       cwd=TOOLS, capture_output=True, text=True, encoding="utf-8")
    assert json.loads(s.stdout)["machine_score"] == 55.0
