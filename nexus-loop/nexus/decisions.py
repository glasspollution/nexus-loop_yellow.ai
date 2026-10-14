"""Stage 9: the approval gate's write-back (Task 04; product handoff section 9).

The problem statement asks both for a report "produced by the system without edits" and for "the human decision
written back into the report". Three files reconcile the two:
  loop-report.generated.json   written only by run.py; never modified afterwards; its SHA-256 is recorded
  decisions.jsonl              append-only; one event per human decision (who, verdict, reason, when, on what)
  loop-report.json             generated report + the latest decision per fix, written by this module only

Decisions are bound to the fix's content, never to positional ids: a re-run that re-orders prescriptions keeps each
decision on its fix, and a decision made on a proposal whose content has since changed is NOT applied - it is
listed as needing re-confirmation. Every save is schema- and contract-validated first and written atomically.
The pipeline itself never writes `approval`.
"""
import copy
import datetime
import hashlib
import json
import os
import threading

from .validate import contract_problems, schema_errors

GENERATED, REPORT, DECISIONS = "loop-report.generated.json", "loop-report.json", "decisions.jsonl"
VERDICTS = ("accepted", "rejected", "deferred")
MAX_TEXT = 2000
_LOCK = threading.Lock()


class DecisionError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def _sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(path):
    with open(path, "rb") as fh:
        return _sha_bytes(fh.read())


def fingerprint(report, p):
    if p.get("fix_id"):
        return p["fix_id"]
    d = next((d for d in report.get("diagnoses", []) if d["id"] == p.get("diagnosis_id")), {})
    f = next((f for f in report.get("findings", []) if f["id"] == d.get("finding_id")), {})
    key = [f.get("tenant"), f.get("cohort"), d.get("cause_class"), p.get("change_type"), p.get("target")]
    return "fx_" + _sha_bytes(json.dumps(key, sort_keys=True).encode())[:12]


def proposal_sha(report, p):
    """Content the human saw: the prescription (minus the decision itself) and its replay evidence."""
    body = {k: v for k, v in p.items() if k not in ("approval", "approval_meta")}
    ver = [{k: v for k, v in x.items() if k not in ("from_cache", "runs_used")} for x in report.get("verifications", [])
           if x.get("prescription_id") == p.get("id")]
    return _sha_bytes(json.dumps([body, ver], sort_keys=True).encode())[:16]


def read_events(out_dir):
    path = os.path.join(out_dir, DECISIONS)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _load(out_dir, name):
    path = os.path.join(out_dir, name)
    if not os.path.exists(path):
        raise DecisionError(404, "%s not found in %s; run run.py first" % (name, out_dir))
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _clean(text, field):
    if not isinstance(text, str):
        raise DecisionError(400, "%s must be text" % field)
    t = text.strip()
    if not t:
        raise DecisionError(400, "%s is required: a decision needs a name and a reason" % field)
    return t[:MAX_TEXT]


def record(out_dir, prescription, verdict, decided_by, reason, seen_generated_sha=None, seen_proposal_sha=None,
           rebuild=None, now=None):
    """Record one human decision and re-materialise loop-report.json. `prescription` is its id or its fix_id."""
    if verdict not in VERDICTS:
        raise DecisionError(400, "verdict must be one of %s" % ", ".join(VERDICTS))
    decided_by, reason = _clean(decided_by, "decided_by"), _clean(reason, "reason")
    with _LOCK:
        gen = _load(out_dir, GENERATED)
        gen_sha = sha_file(os.path.join(out_dir, GENERATED))
        if seen_generated_sha and seen_generated_sha != gen_sha:
            raise DecisionError(409, "the report was regenerated after this screen was loaded; reload before deciding")
        p = next((x for x in gen.get("prescriptions", []) if prescription in (x.get("id"), x.get("fix_id"))), None)
        if p is None:
            raise DecisionError(404, "no prescription %r in the generated report" % prescription)
        psha = proposal_sha(gen, p)
        if seen_proposal_sha and seen_proposal_sha != psha:
            raise DecisionError(409, "this proposal changed after it was displayed; reload before deciding")
        ev = {"fingerprint": fingerprint(gen, p), "prescription_id": p["id"], "change_type": p.get("change_type"),
              "target": p.get("target"), "verdict": verdict, "decided_by": decided_by, "reason": reason,
              "at": now or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "generated_report_sha256": gen_sha, "proposal_sha": psha,
              "evidence_seen": [{"replay_run_id": v.get("replay_run_id"), "verdict": v.get("verdict"), "gate": v.get("gate")}
                                for v in gen.get("verifications", []) if v.get("prescription_id") == p["id"]]}
        events = read_events(out_dir)
        last = next((e for e in reversed(events) if e.get("fingerprint") == ev["fingerprint"]), None)
        duplicate = last is not None and all(last.get(k) == ev[k] for k in ("verdict", "decided_by", "reason", "proposal_sha"))
        if not duplicate:
            prepared = _prepare_materialisation(out_dir, events + [ev])
            with open(os.path.join(out_dir, DECISIONS), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev) + "\n")
            result = _commit_materialisation(out_dir, rebuild, *prepared)
        else:
            result = _materialise(out_dir, rebuild)
        result["event"] = last if duplicate else ev
        result["duplicate"] = duplicate
        return result


def materialise(out_dir, rebuild=None):
    with _LOCK:
        return _materialise(out_dir, rebuild)


def _materialise(out_dir, rebuild):
    return _commit_materialisation(out_dir, rebuild, *_prepare_materialisation(out_dir))


def _prepare_materialisation(out_dir, events=None):
    gen = _load(out_dir, GENERATED)
    gen_sha = sha_file(os.path.join(out_dir, GENERATED))
    latest = {}
    for ev in read_events(out_dir) if events is None else events:
        latest[ev["fingerprint"]] = ev
    out = copy.deepcopy(gen)
    applied, reconfirm = [], []
    for p in out.get("prescriptions", []):
        fp = fingerprint(gen, p)
        ev = latest.pop(fp, None)
        if not ev:
            continue
        psha = proposal_sha(gen, next(x for x in gen["prescriptions"] if x["id"] == p["id"]))
        if ev.get("proposal_sha") != psha:
            reconfirm.append({"prescription_id": p["id"], "fix_id": fp, "previous": {k: ev[k] for k in
                                                                                  ("verdict", "decided_by", "at")}})
            continue
        p["approval"] = {k: ev[k] for k in ("verdict", "decided_by", "reason", "at")}
        p["approval_meta"] = {"fix_id": fp, "proposal_sha": psha, "decided_on_generated_report_sha256":
                              ev.get("generated_report_sha256"),
                              "report_regenerated_since": ev.get("generated_report_sha256") != gen_sha}
        applied.append(p["id"])
    out["decision_log"] = {"generated_report": GENERATED, "generated_report_sha256": gen_sha, "decisions_file": DECISIONS,
                           "applied": applied, "needs_reconfirmation": reconfirm,
                           "orphaned": [{"fix_id": fp, "prescription_id": ev.get("prescription_id")}
                                        for fp, ev in latest.items()]}
    errs, probs = schema_errors(out), contract_problems(out)
    if errs or probs:
        raise DecisionError(422, "refusing to save an invalid report: %s" % "; ".join((errs or []) + probs)[:800])
    data = json.dumps(out, indent=1)
    result = {"report": REPORT, "applied": applied, "needs_reconfirmation": reconfirm,
              "orphaned": out["decision_log"]["orphaned"], "report_sha256": _sha_bytes(data.encode("utf-8"))}
    return out, data, result


def _commit_materialisation(out_dir, rebuild, out, data, result):
    path = os.path.join(out_dir, REPORT)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    with open(path, encoding="utf-8") as fh:
        if fh.read() != data:
            raise DecisionError(500, "read-back after save did not match; the decision was not saved")
    if rebuild:
        rebuild(out)
    return result
