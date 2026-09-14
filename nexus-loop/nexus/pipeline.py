"""One call from a kit directory to a loop report. No ground truth is read anywhere in the pipeline."""
import json
import os

from .incidents import build
from .loader import load_counters
from .multiscale import scan_multi
from .report import incidents_json, report

REPORT_NAME = "loop-report.json"
INCIDENTS_NAME = "incidents.json"
REQUIRED_KIT_FILES = ("catalog.json", "corpus/sessions.jsonl.gz", "corpus/agent_steps.jsonl.gz")


def check_kit(kit):
    missing = [f for f in REQUIRED_KIT_FILES if not os.path.exists(os.path.join(kit, f))]
    if missing:
        raise FileNotFoundError("%s is not a Nexus Loop kit; missing: %s" % (kit, ", ".join(missing)))


def analyse(kit, cache_dir=None, cfg=None, team="nexus-loop"):
    """Run every stage on `kit`. Returns counters, episodes, incidents and the report dict."""
    kit = os.path.abspath(kit)
    check_kit(kit)
    counters = load_counters(kit, cache_dir=cache_dir)
    episodes = scan_multi(counters, cfg)
    incidents = build(counters, episodes, cfg)
    return {"counters": counters, "episodes": episodes, "incidents": incidents,
            "report": report(counters, incidents, team=team)}


def _json_default(o):
    return o.item() if hasattr(o, "item") else str(o)


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, default=_json_default)
    return path


def write_outputs(result, out_dir):
    """Write loop-report.json and incidents.json; return their paths."""
    rp = write_json(os.path.join(out_dir, REPORT_NAME), result["report"])
    ip = write_json(os.path.join(out_dir, INCIDENTS_NAME), incidents_json(result["incidents"]))
    return rp, ip
