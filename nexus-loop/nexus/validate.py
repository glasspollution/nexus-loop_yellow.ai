"""The report gate (handoff 13.2 fix 5 and 13.3).

`schema_errors` checks loop-report.json against the kit's schema (vendored in nexus/schema/).
`contract_problems` checks what the schema cannot express but the problem statement and score.py require.
Both are generic: neither needs ground truth.
"""
import json
import os

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema", "loop-report.schema.json")
APPROVAL_FIELDS = ("verdict", "decided_by", "reason", "at")


def schema_errors(rep, schema_path=SCHEMA_PATH):
    """List of 'path: message' strings, or None when jsonschema is not installed (nothing was checked)."""
    try:
        import jsonschema
    except ImportError:
        return None
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    validator = jsonschema.validators.validator_for(schema)(schema)
    errs = sorted(validator.iter_errors(rep), key=lambda e: [str(p) for p in e.absolute_path])
    return ["%s: %s" % ("/".join(str(p) for p in e.absolute_path) or "<root>", e.message) for e in errs]


def contract_problems(rep):
    out = []
    metrics = rep.get("metrics") or []
    if not metrics:
        out.append("no metrics declared")
    for m in metrics:
        if not m.get("fidelity") or (m.get("coverage") or {}).get("value") is None:
            out.append("metric %s lacks fidelity or coverage.value" % m.get("id"))
        agreement = (m.get("calibration") or {}).get("agreement")
        if agreement is not None and agreement >= 0.995:
            out.append("metric %s reports calibration %.3f; human labels disagree, so this is a bug" % (m.get("id"), agreement))
        if m.get("fidelity") == "judged" and m.get("calibration") is None and "calibration" not in (
                (m.get("plan") or {}).get("filter", "").lower()):
            out.append("judged metric %s publishes no calibration and does not say why" % m.get("id"))

    findings = {f["id"]: f for f in rep.get("findings") or []}
    diagnoses = {d["id"]: d for d in rep.get("diagnoses") or []}
    for f in findings.values():
        if f.get("is_regression"):
            for key in ("impact", "audience", "if_nothing_changes"):
                if not f.get(key):
                    out.append("regression %s has no %s" % (f["id"], key))
            if f.get("impact") and not f["impact"].get("derivation"):
                out.append("regression %s impact shows no derivation" % f["id"])
        elif not f.get("not_a_regression_because"):
            out.append("dismissed finding %s does not say why it is not a regression" % f["id"])
    for d in diagnoses.values():
        if d.get("finding_id") not in findings:
            out.append("diagnosis %s references missing finding %s" % (d["id"], d.get("finding_id")))

    for p in rep.get("prescriptions") or []:
        if p.get("diagnosis_id") not in diagnoses:
            out.append("prescription %s references missing diagnosis %s" % (p["id"], p.get("diagnosis_id")))
        if (p.get("predicted_delta") or {}).get("to") is None:
            out.append("prescription %s has no predicted_delta.to" % p["id"])
        if "approval" in p:
            a = p["approval"] or {}
            if any(not isinstance(a.get(k), str) or not a.get(k) for k in APPROVAL_FIELDS):
                out.append("prescription %s approval must carry %s as non-empty strings (written by the screen only)"
                           % (p["id"], ", ".join(APPROVAL_FIELDS)))

    for v in rep.get("verifications") or []:
        if not str(v.get("replay_run_id", "")).startswith("rp_"):
            out.append("verification for %s has no real replay_run_id" % v.get("prescription_id"))

    for g in rep.get("gaps") or []:
        if g.get("verdict") in ("NOT_MEASURABLE", "REQUIRES_NEW_JUDGE") and not (g.get("required_event") or {}).get("fields"):
            out.append("gap %s (%s) names no required event fields" % (g.get("ask_id"), g.get("verdict")))
    return out
