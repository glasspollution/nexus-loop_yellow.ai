import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(ROOT)
PRACTICE_KIT = os.path.join(WORKSPACE, "kit")
TOOLS = os.path.join(WORKSPACE, "tools", "nexus-loop-kit")
sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def practice():
    """Full pipeline on the practice kit, once per test session (uses the loader cache)."""
    if not os.path.isdir(PRACTICE_KIT):
        pytest.skip("practice kit not found at %s" % PRACTICE_KIT)
    from nexus.pipeline import _json_default, analyse
    res = analyse(PRACTICE_KIT, cache_dir=os.path.join(ROOT, ".cache"))
    res["report_json"] = json.loads(json.dumps(res["report"], default=_json_default))
    return res
