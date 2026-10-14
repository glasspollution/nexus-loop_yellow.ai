"""One call from a kit directory to a loop report. No ground truth is read anywhere in the pipeline.

detect -> diagnose -> decision packets -> standard + golden set -> prescriptions -> replay verification
-> self-assessment, all unattended. The only human step is the approval gate (decisions.py / server.py).
"""
import json
import os
import shutil

from . import decisions, screen
from .incidents import build
from .loader import load_counters
from .multiscale import scan_multi
from .replay import DEFAULT_MAX_CALLS, corpus_id, verify
from .report import build_product, incidents_json, report
from .selfassess import append_batch, assess
from .validate import contract_problems, schema_errors

REPORT_NAME = decisions.REPORT
GENERATED_NAME = decisions.GENERATED
INCIDENTS_NAME = "incidents.json"
REQUIRED_KIT_FILES = ("catalog.json", "corpus/sessions.jsonl.gz", "corpus/agent_steps.jsonl.gz")


def check_kit(kit):
    missing = [f for f in REQUIRED_KIT_FILES if not os.path.exists(os.path.join(kit, f))]
    if missing:
        raise FileNotFoundError("%s is not a Nexus Loop kit; missing: %s" % (kit, ", ".join(missing)))


def analyse(kit, cache_dir=None, cfg=None, team="nexus-loop", replay_url=None, replay_team=None, replay_cache=None,
            max_replay_calls=DEFAULT_MAX_CALLS, ledger=None, run_replay=True):
    """Run every stage on `kit`. Returns counters, episodes, incidents, the product layer and the report dict."""
    kit = os.path.abspath(kit)
    check_kit(kit)
    counters = load_counters(kit, cache_dir=cache_dir)
    episodes = scan_multi(counters, cfg)
    incidents = build(counters, episodes, cfg)
    product = build_product(counters, incidents)
    rep = report(counters, incidents, team=team, product=product)
    corpus = corpus_id(kit, rep)
    if run_replay:
        verifications, notes, trace = verify(rep, product["golden_sets"], endpoint=replay_url,
                                             team=replay_team or team, cache_dir=replay_cache, corpus=corpus,
                                             max_calls=max_replay_calls)
    else:
        verifications, notes, trace = [], [], []
    rep["verifications"] = verifications
    unverified = ["%s not verified: %s" % (t["prescription_id"], t["reason"]) for t in trace if t["status"] == "unverified"]
    if run_replay:
        sa, record = assess(rep, corpus, unverified, ledger)
        rep["self_assessment"] = sa
    else:
        record = None
        rep["self_assessment"] = {"cycles": 0, "prescription_accuracy": {}}
    if notes:
        rep["system_notes"] += " Replay: " + " ".join(notes)
    return {"counters": counters, "episodes": episodes, "incidents": incidents, "product": product, "report": rep,
            "replay_trace": trace, "ledger_record": record, "corpus_id": corpus}


def _json_default(o):
    return o.item() if hasattr(o, "item") else str(o)


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, default=_json_default)
    return path


def write_outputs(result, out_dir, ledger=None):
    """Write the untouched generated report, apply any recorded human decisions into loop-report.json, and write the
    screen's data. Returns the paths written."""
    gen = write_json(os.path.join(out_dir, GENERATED_NAME), result["report"])
    rp = os.path.join(out_dir, REPORT_NAME)
    try:
        decisions.materialise(out_dir)
    except decisions.DecisionError:
        shutil.copyfile(gen, rp)         # an invalid report is still written, exactly as generated; run.py reports why
    ip = write_json(os.path.join(out_dir, INCIDENTS_NAME), incidents_json(result["incidents"]))
    write_json(os.path.join(out_dir, "golden_set.json"), result["product"]["standard_manifest"])
    write_json(os.path.join(out_dir, "definitions.json"), result["report"]["definitions"])
    write_json(os.path.join(out_dir, "replay_trace.json"), {"corpus": result["corpus_id"], "trace": result["replay_trace"]})
    screen.write(out_dir)
    if ledger and result.get("ledger_record"):
        append_batch(ledger, result["ledger_record"])
    return {"generated": gen, "report": rp, "incidents": ip, "screen": os.path.join(out_dir, screen.SCREEN_FILE)}


def validate_file(path):
    with open(path, encoding="utf-8") as fh:
        rep = json.load(fh)
    return schema_errors(rep), contract_problems(rep)
