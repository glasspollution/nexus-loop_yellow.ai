"""Shared paths and helpers for the validation scripts."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                   # nexus-loop/
WORKSPACE = os.path.dirname(ROOT)                              # folder holding kit/ and tools/
PRACTICE_KIT = os.path.join(WORKSPACE, "kit")
TOOLS = os.path.join(WORKSPACE, "tools", "nexus-loop-kit")
DATA = os.path.join(HERE, "data")
RESULTS = os.path.join(HERE, "results")
BENCHMARK = os.path.join(HERE, "benchmark")
BASELINES = os.path.join(HERE, "baselines", "research")

sys.path.insert(0, ROOT)


def utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def find_ground_truth(kit):
    for rel in ("ground_truth/ground_truth.json", "ground_truth_SEALED/ground_truth.json"):
        p = os.path.join(kit, rel)
        if os.path.exists(p):
            return p
    return None


def score(report_path, ground_truth_path):
    """Run the organisers' score.py unchanged; return its --json output."""
    out = subprocess.run([sys.executable, "score.py", "--report", os.path.abspath(report_path),
                          "--ground-truth", os.path.abspath(ground_truth_path), "--json"],
                         cwd=TOOLS, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise RuntimeError("score.py failed: %s" % out.stderr[-800:])
    return json.loads(out.stdout)
