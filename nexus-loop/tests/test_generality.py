"""No planted-fault knowledge in the detection code (handoff 14.3)."""
import json
import os
import re

import pytest

from conftest import PRACTICE_KIT, ROOT

DETECTION = ("config.py", "loader.py", "detect.py", "multiscale.py", "cohorts.py", "incidents.py", "diagnose.py")
KEYS = {"tenant", "intent", "agent_id", "tool", "tool_name", "channel", "segment"}


def _literals(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in KEYS and isinstance(v, str) and v not in ("", "*"):
                out.add(v)
            _literals(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _literals(v, out)
    return out


def test_detection_code_names_no_cohort_from_the_answer_key():
    gt_path = os.path.join(PRACTICE_KIT, "ground_truth", "ground_truth.json")
    if not os.path.exists(gt_path):
        pytest.skip("practice ground truth not found")
    literals = _literals(json.load(open(gt_path, encoding="utf-8")), set())
    assert literals
    for src in DETECTION:
        text = open(os.path.join(ROOT, "nexus", src), encoding="utf-8").read()
        found = [lit for lit in literals if re.search(r"""["']%s["']""" % re.escape(lit), text)]
        assert not found, "%s names %s" % (src, found)


def test_pipeline_never_opens_ground_truth():
    for src in os.listdir(os.path.join(ROOT, "nexus")):
        if src.endswith(".py"):
            assert "ground_truth" not in open(os.path.join(ROOT, "nexus", src), encoding="utf-8").read(), src
