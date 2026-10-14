"""Stage 7: prescriptions framed as decisions (Task 02; product handoff section 7).

A prescription is what a human is asked to approve, filled only with numbers from the decision packet and the
attributed config row:
  * the change type follows the diagnosed cause, with the alternative a human should weigh and `no_action` priced;
  * `no_action` is the primary proposal only when there is nothing measurable to fix, or no layer explains the move;
  * `predicted_delta` is stated on the metric the replay service measures (resolution rate, or median turns for a
    prompt regression) as a declared fraction of the measured gap, so it can later be compared with the replay;
  * the decision block says what is being approved, the honest risk if the diagnosis is wrong, what should stop the
    change, and the real trade-off. A reasoned rejection is a first-class answer.
Nothing here names a tenant, cohort or day; the knowledge-base topics are counted from the users' own first messages.
"""
import gzip
import hashlib
import json
import os
from collections import Counter

from .diagnose import FIX

ALTERNATIVE = {"kb.gap": "kb.synonym", "tool.contract_break": "tool.fallback", "tool.outage": "tool.validate",
               "prompt.regression": "revert", "model.change": "prompt.edit"}
GAP_FRACTION = 0.8          # declared prior share of the measured gap a correct fix closes; never fitted to the replay
AUTONOMY = {"kb.add": "L1", "kb.synonym": "L2", "prompt.edit": "L1", "revert": "L1", "tool.validate": "L2",
            "tool.fallback": "L2", "routing.change": "L1", "no_action": "L0"}


def replay_metric(cause):
    return "median_turns" if str(cause).startswith("prompt") else "resolution_rate"


def fix_id(tenant, cohort, cause, change_type, target):
    return "fx_" + hashlib.sha256(json.dumps([tenant, cohort, cause, change_type, target], sort_keys=True)
                                  .encode()).hexdigest()[:12]


def config_note(C, att):
    for r in C.get("config") or []:
        try:
            if int(r.get("day")) == int(att["day"]) and r.get("kind") == att.get("kind") and r.get("target") == att.get("target"):
                return r.get("note") or ""
        except (TypeError, ValueError):
            continue
    return ""


def first_messages(C, session_ids, limit=5):
    """What these users asked, verbatim: their first message, counted (deterministic; no model involved)."""
    path = os.path.join(C.get("kit", ""), "corpus", "turns.jsonl.gz")
    if not session_ids or not os.path.exists(path):
        return []
    want, cnt = set(session_ids), Counter()
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if '"turn_index": 1,' not in line and '"turn_index":1,' not in line:
                continue
            r = json.loads(line)
            if r.get("session_id") in want and r.get("turn_index") == 1 and r.get("user_text"):
                cnt[r["user_text"].strip().lower()] += 1
    return [{"message": m, "conversations": n} for m, n in cnt.most_common(limit)]


def _i(x):
    return "n/a" if x is None else "{:,}".format(int(round(x)))


def _pct(x):
    return "n/a" if x is None else "%.1f%%" % (100 * x)


def _money(x):
    return "n/a" if x is None else "$%.2f" % x


def _decision(ct, inc, p, att, note, topics, cohort_txt):
    per_day = max(1, p["days"])
    lost, hx = p["lost"], p["handoffs_excess"]
    t = p["turns"]
    cost_day = (p["cost"]["excess"] or 0) / per_day
    min_day = (p["minutes_extra"] or 0) / per_day
    ended = p["status"]["state"] == "ended"
    stop_clause = (" It stopped on day %d without a recorded fix, so this protects against it coming back." %
                   p["status"]["recovery_day"]) if ended else ""
    asked = "; ".join("'%s' (%d)" % (x["message"], x["conversations"]) for x in topics) if topics else ""
    if ct == "kb.add":
        return {
            "asking_approval_for": "Add knowledge-base content that answers %s questions. %s of %s conversations looked "
                                   "something up and found no confident document; they resolved at %s against %s for "
                                   "comparable traffic.%s%s" % (cohort_txt, _i(p["hit"]), _i(p["n"]), _pct(p["r_C"]),
                                                               _pct(p["r_B"]), (" What users asked first: " + asked + ".")
                                                               if asked else "", stop_clause),
            "risk_if_diagnosis_wrong": "If retrieval rather than missing content is the fault, resolution stays near %s and "
                                       "about %s resolutions keep being lost. If the unanswered questions are policy "
                                       "(fees, eligibility), published content states an answer nobody approved."
                                       % (_pct(p["r_C"]), _i(lost)),
            "would_not_ship_if": "the business owner cannot sign off the answers (then a scripted handoff is the honest "
                                 "fix); or the replay does not lift resolution toward %s; or the replay breaks the golden "
                                 "set; or the miss rate is already back at its baseline on the latest days"
                                 % _pct(p["r_B"]),
            "trade_off": "launch speed against approving what the agent is allowed to say"}
    if ct == "kb.synonym":
        return {
            "asking_approval_for": "Map the phrasings used in %s conversations to existing knowledge-base documents, with "
                                   "no new content.%s" % (cohort_txt, stop_clause),
            "risk_if_diagnosis_wrong": "If the existing documents do not answer these questions, the agent answers "
                                       "confidently with the wrong document, which is worse than a miss because it no "
                                       "longer hands off.",
            "would_not_ship_if": "retrieval confidence rises but resolution does not; or any golden-set conversation "
                                 "changes its answer",
            "trade_off": "cheaper and faster than new content, at the risk of confident wrong answers"}
    if ct == "tool.validate":
        return {
            "asking_approval_for": "Treat a successful %s response with nothing in it as a failure and take the existing "
                                   "fallback path instead of answering from an empty result. %s of %s conversations got "
                                   "such a response; they resolved at %s against %s for the rest.%s"
                                   % (inc["value"] if inc["dim"] == "tool" else "tool", _i(p["hit"]), _i(p["n"]),
                                      _pct(p["r_hit"]), _pct(p["r_nothit"]), stop_clause),
            "risk_if_diagnosis_wrong": "If an empty response is sometimes a valid answer (nothing found), the guard turns a "
                                       "correct answer into a failure for up to %s customers and sends them to a human. It "
                                       "also hides the upstream defect unless rejected responses are counted and reported "
                                       "to the service owner." % _i(p["hit"]),
            "would_not_ship_if": "the service owner confirms an empty response is valid, or ships their own fix; or the "
                                 "replay does not lift resolution toward %s; or the replay breaks the golden set"
                                 % _pct(p["r_B"]),
            "trade_off": "fixing it on our side now against waiting for the service owner"}
    if ct == "tool.fallback":
        return {
            "asking_approval_for": "When the tool behind %s fails, answer from the fallback path instead of apologising. "
                                   "%s of %s conversations were affected.%s" % (cohort_txt, _i(p["hit"]), _i(p["n"]),
                                                                              stop_clause),
            "risk_if_diagnosis_wrong": "If failures depend on the data rather than being transient, the fallback serves stale "
                                       "or wrong information to up to %s customers." % _i(p["hit"]),
            "would_not_ship_if": "the fallback data is older than the business accepts for this journey; or the replay "
                                 "does not lift resolution; or the golden set breaks",
            "trade_off": "availability against freshness of the answer"}
    if ct in ("prompt.edit", "revert"):
        tgt, frm, new, dday = ((att.get("target"), att.get("from"), att.get("to"), att.get("day")) if att else
                               ("the agent", "the previous version", "the current version", "?"))
        purpose = ("; its stated purpose: '%s'" % note) if note else ""
        base = ("Median turns went from %s to %s, cost per conversation from %s to %s, and resolution is %s against %s "
                "(lost resolutions %s, 95%% range %s to %s)." % (t["median_baseline"], t["median"],
                                                                "$%.4f" % (p["cost"]["per_conversation_baseline"] or 0),
                                                                "$%.4f" % (p["cost"]["per_conversation"] or 0),
                                                                _pct(p["r_C"]), _pct(p["r_B"]), _i(lost),
                                                                _i(p["lost_ci"][0]), _i(p["lost_ci"][1])))
        price = ("record that the business accepts about %s a day and %s customer-minutes a day as the price of keeping it"
                 % (_money(cost_day), _i(min_day)))
        if ct == "prompt.edit":
            return {
                "asking_approval_for": "Edit %s's prompt %s (introduced on day %s, replacing %s%s) so it stops adding "
                                       "back-and-forth, while keeping what the change was for. %s%s"
                                       % (tgt, new, dday, frm, purpose, base, stop_clause),
                "risk_if_diagnosis_wrong": "If the longer conversations are what makes the new wording work, trimming them "
                                           "undoes what the change was for; the logs measure resolution, not mistakes "
                                           "prevented. If turns rose for another reason, the edit changes nothing while "
                                           "about %s a day keeps being spent." % _money(cost_day),
                "would_not_ship_if": "the replay does not bring median turns back toward %s; or the replay breaks the "
                                     "golden set; or the business owner rules the extra confirmations a requirement - in "
                                     "which case reject it and %s" % (t["median_baseline"], price),
                "trade_off": "customer time and cost against what the prompt change was for"}
        return {
            "asking_approval_for": "Roll %s back from %s to %s (the change made on day %s%s). %s"
                                   % (tgt, new, frm, dday, purpose, base),
            "risk_if_diagnosis_wrong": "A rollback restores the old behaviour immediately but loses everything the change "
                                       "was for; if the change was not the cause, nothing improves and the wanted change is "
                                       "gone. Blunt changes also break conversations they were not aimed at.",
            "would_not_ship_if": "resolution under the new version is measurably higher than before; or the change carries "
                                 "a compliance or security fix; or the slice already recovered while still on the new "
                                 "version",
            "trade_off": "a certain rollback against losing the change's purpose"}
    if ct == "routing.change":
        return {
            "asking_approval_for": "Change routing for %s so the %s conversations handed to a human beyond the usual rate "
                                   "stay with the agent.%s" % (cohort_txt, _i(hx), stop_clause),
            "risk_if_diagnosis_wrong": "Routing is blunt: customers who genuinely need a person stop getting one, and "
                                       "healthy traffic moves too.",
            "would_not_ship_if": "any golden-set regression; or the handoff split was a deliberate staffing decision",
            "trade_off": "containment against access to a human"}
    return {
        "asking_approval_for": "Make no change to %s and record the decision with its measured price: %s lost resolutions "
                               "(95%% range %s to %s), %s excess handoffs, %s extra spend over %d days; status: %s."
                               % (cohort_txt, _i(lost), _i(p["lost_ci"][0]), _i(p["lost_ci"][1]), _i(hx),
                                  _money(p["cost"]["excess"]), p["days"], p["status"]["state"]),
        "risk_if_diagnosis_wrong": "If there is a real problem and it is still live, that price keeps accruing.",
        "would_not_ship_if": "(revisit) the status changes to recurring, the daily rate grows, or a new config change "
                             "touches this slice",
        "trade_off": "accepting a known, measured cost against an unproven change"}


def prescribe(C, inc, p, standard_rows=None):
    """One prescription for a regression incident, or None when there is no packet."""
    if p is None:
        return None
    cause = inc["cause_class"]
    att = inc.get("attributed_change") or None
    note = config_note(C, att) if att else ""
    cohort_txt = p["where"]
    material = (p["lost_ci"][0] > 0 or p["handoffs_ci"][0] > 0
                or max(p["turns"]["relative"] or 0, p["cost"]["relative"] or 0) >= 0.10)
    if cause not in FIX:
        ct, why = "no_action", ("no runtime layer explains this move, so any change would be a guess; the right next "
                                "step is instrumentation, not a change to the agent")
    elif not material:
        ct, why = "no_action", "nothing customers or costs show has moved measurably, so there is nothing to fix yet"
    else:
        ct, why = FIX[cause], None
    if ct in ("prompt.edit", "revert", "routing.change") and att and att.get("target"):
        target = att["target"]
    else:
        target = inc["value"] if inc["dim"] not in (None, "__all__") else inc["tenant"]
    topics = []
    if ct in ("kb.add", "kb.synonym"):
        S = C["S"]
        from .cohorts import smask
        from .impact import hit_mask
        mk = smask(C, inc["tenant"], inc["dim"], inc["value"])
        hit, _ = hit_mask(C, inc, mk)
        sel = mk & hit & (S["day"] >= p["onset"]) & (S["day"] <= p["end"])
        topics = first_messages(C, [str(x) for x in S["sid"][sel]])
    metric = replay_metric(cause)
    if metric == "median_turns":
        D_ = p["turns"]["median"] if p["turns"]["median"] is not None else p["turns"]["mean"]
        H = p["turns"]["median_baseline"] if p["turns"]["median_baseline"] is not None else p["turns"]["mean_baseline"]
    else:
        D_, H = p["r_C"], p["r_B"]
    to = D_ if ct == "no_action" else D_ + GAP_FRACTION * (H - D_)
    decision = _decision(ct, inc, p, att, note, topics, cohort_txt)
    if why:
        decision["why_no_action"] = why
    alts = []
    if ct != "no_action" and ALTERNATIVE.get(cause):
        alt = ALTERNATIVE[cause]
        alts.append({"change_type": alt, **{k: v for k, v in _decision(alt, inc, p, att, note, topics, cohort_txt).items()
                                          if k in ("asking_approval_for", "trade_off", "risk_if_diagnosis_wrong")}})
    if ct != "no_action":
        alts.append({"change_type": "no_action",
                     **{k: v for k, v in _decision("no_action", inc, p, att, note, topics, cohort_txt).items()
                        if k in ("asking_approval_for", "trade_off")}})
    mech = p["mechanism"]
    out = {"change_type": ct, "target": target, "fix_id": fix_id(inc["tenant"], inc["cohort"], cause, ct, target),
           "description": ("%s for %s (%s)" % ({"kb.add": "Add missing knowledge-base content",
                                                 "kb.synonym": "Map user phrasings to existing documents",
                                                 "tool.validate": "Reject empty tool responses and use the fallback path",
                                                 "tool.fallback": "Answer from the fallback path when the tool fails",
                                                 "prompt.edit": "Edit the prompt to remove the added back-and-forth",
                                                 "revert": "Roll back the attributed change",
                                                 "routing.change": "Change the routing rule",
                                                 "no_action": "Make no change"}[ct], cohort_txt, target)),
           "autonomy_rung": AUTONOMY[ct],
           "predicted_delta": {"metric": metric, "from": round(D_, 4), "to": round(to, 4)},
           "replay_prediction": {"metric": metric, "in_window_level": round(D_, 4), "healthy_level": round(H, 4),
                                 "gap_fraction": GAP_FRACTION if ct != "no_action" else 0.0,
                                 "formula": ("predicted replay delta = gap_fraction x before x (healthy / in-window - 1)"
                                             if metric == "median_turns" else
                                             "predicted replay delta = gap_fraction x (healthy - before)"),
                                 "basis": "healthy and in-window levels measured from the corpus against the finding's "
                                          "named baseline (%s); the gap fraction is a declared prior, not fitted to the "
                                          "replay service" % p["baseline"]["label"]},
           "mechanism_prediction": {"metric": mech["metric"], "from": mech["current"], "to": mech["baseline"]},
           "decision": decision, "alternatives": alts, "owner": p["audience"][0], "status_at_proposal": p["status"]["state"],
           "user_first_messages": topics, "standard_gap": standard_rows or []}
    return out
