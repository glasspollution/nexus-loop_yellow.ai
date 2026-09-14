"""Operator-facing language: the product half of the report.

Everything here is GENERATED AT RUNTIME from the cause class and the measured values. Nothing is
hand-written about a specific finding, because the sealed run is unattended on a corpus nobody has
seen: a sentence naming a day, a tenant or a cohort would be wrong the moment the data moves.

Three jobs:

  1. ``series()``    - the missing join. A finding names a raw series (``kb_lookup.miss``); the
                       metrics block names declared ids (``m_containment``). Nothing links them, so
                       the screen cannot say what a number means, how it was measured, or what share
                       of traffic can produce it. This resolves any series name, including ones this
                       corpus has never emitted, by composing prefix and suffix.
  2. ``title()`` / ``cohort_label()`` - plain English for an operator who has never seen the system.
                       No metric names, no cohort keys, no architecture vocabulary.
  3. The decision prose - ``asking_approval_for``, ``risk_if_diagnosis_wrong``, ``would_not_ship_if``.
                       The schema requires all three. They are what "could an operator act on this"
                       is actually asking, so they are written per cause class and per change type,
                       never as one boilerplate line reused everywhere.

Nothing here changes a number, a cohort key, an enum, a window or an ask id. It only adds and
rewrites prose. See ``docs/SCORING_SAFETY.md``.
"""

import re

# --------------------------------------------------------------------------------------------
# 1. The series registry: raw series name -> what an operator should be told about that number.
# --------------------------------------------------------------------------------------------
#
# Series names are composed, not enumerated:
#     session level   s.<field>                      e.g. s.resolved, s.cost_usd
#     judged          s.quality_score@<judge_version>
#     step level      <step_type>.<suffix>           e.g. tool_call.empty, kb_lookup.miss
#     composition     share:<dimension>
#     instrumentation coverage:<step_type>
#
# so the resolver handles the parts and degrades to an honest generic description rather than
# rendering a raw key at an operator. `basis` is how coverage must be resolved for this number:
# "session" means every session can produce it (coverage 1.0); "step" means it is computed from
# agent_steps and therefore carries its tenant's eligible-session share, never a blended figure.

_SESSION = {
    "s.resolved": ("Resolution rate", "measured", "session",
                   "Share of conversations that ended resolved.", True),
    "s.milestones_complete": ("Journey completion rate", "measured", "session",
                              "Share of conversations that reached every milestone their intent "
                              "defines in the catalog.", True),
    "s.milestone_ratio": ("Journey progress", "derived", "session",
                          "Average share of an intent's milestones reached before the conversation "
                          "ended.", True),
    "s.handoff_unplanned": ("Unplanned handoffs", "measured", "session",
                            "Share of conversations handed to a human where handoff_by_design is "
                            "false - a person the journey never intended to involve.", False),
    "s.abandoned": ("Abandonment rate", "measured", "session",
                    "Share of conversations the customer left without resolving. How many gave up "
                    "is measured; why they gave up is not - see the refused questions.", False),
    "s.turns": ("Exchanges per conversation", "measured", "session",
                "Number of back-and-forth turns before the conversation ended.", False),
    "s.duration_s": ("Conversation length", "measured", "session",
                     "Wall-clock seconds from first to last turn.", False),
    "s.cost_usd": ("Cost per conversation", "measured", "step",
                   "Model spend per conversation, summed over its llm_call steps. Only agents that "
                   "emit llm_call steps record cost at all, so this carries its tenant's coverage "
                   "and is never blended across tenants.", False),
    "s.tool_error_any": ("Conversations hitting a tool error", "derived", "step",
                         "Share of conversations with at least one tool call that did not return "
                         "ok. Declared failures only - a tool returning HTTP 200 with an empty "
                         "body is counted as a success here, by definition.", False),
    "s.guardrail_any": ("Conversations hitting a guardrail", "measured", "step",
                        "Share of conversations where at least one guardrail step fired.", False),
}

_SUFFIX = {
    "fail": ("failure rate", "measured",
             "Share of {what} steps whose outcome was not ok. This is the DECLARED failure rate: "
             "it believes what the step reported.", False),
    "timeout": ("timeout rate", "measured", "Share of {what} steps that timed out.", False),
    "blocked": ("blocked rate", "measured", "Share of {what} steps that were blocked.", False),
    "retry": ("retry rate", "measured",
              "Share of {what} steps with retry_count above zero. These are quality retries against "
              "the same target, not failover to an alternate - see the refused questions.", False),
    "empty": ("empty-response rate", "derived",
              "Share of {what} steps that returned ok with zero fields in the payload. Derived, not "
              "declared: the step reports success, so every error-rate metric reads flat while this "
              "one moves.", False),
    "miss": ("miss rate", "measured",
             "Share of {what} steps that came back with no confident hit.", False),
    "top_score": ("best match score", "measured",
                  "Confidence of the best {what} match, 0 to 1.", True),
    "duration_ms": ("response time", "measured",
                    "Milliseconds a {what} step took to return.", False),
    "tokens": ("tokens used", "measured", "Tokens consumed by {what} steps.", False),
}

_STEP_NOUN = {
    "tool_call": "tool call", "kb_lookup": "knowledge-base lookup", "llm_call": "model call",
    "guardrail": "guardrail", "handoff": "handoff", "turn": "turn",
}

_DIM_NOUN = {
    "intent": "question type", "tool": "tool", "agent_id": "agent", "channel": "channel",
    "segment": "customer segment", "tool_name": "tool",
}


def _pretty(token):
    """premium_card_info -> 'Premium Card Info'. Used only where a raw key would otherwise show."""
    return re.sub(r"[_\-]+", " ", str(token or "")).strip().title()


# Trailing tokens that only duplicate the noun we are about to append ("... enquiries"). Anything
# load-bearing (status, locator, dispute) is kept - we are trimming noise, not guessing meaning.
_REDUNDANT_TAIL = ("info", "enquiry", "inquiry", "enquiries", "inquiries", "query", "queries")


def _intent_words(value):
    parts = re.split(r"[_\-]+", str(value or "").strip())
    if len(parts) > 1 and parts[-1].lower() in _REDUNDANT_TAIL:
        parts = parts[:-1]
    return " ".join(parts).title()


def series(name):
    """Resolve any series name to operator-facing metadata.

    Returns ``{name, plain, definition, fidelity, basis, higher_is_better}``. ``basis`` is
    "session" or "step" and tells the screen which coverage figure applies. Never raises, and never
    hands back a raw key as the display name.
    """
    raw = str(name or "")

    if raw in _SESSION:
        plain, fid, basis, defn, up = _SESSION[raw]
        return {"name": raw, "plain": plain, "definition": defn, "fidelity": fid,
                "basis": basis, "higher_is_better": up}

    # judged quality, versioned: s.quality_score@v1
    if raw.startswith("s.quality_score"):
        _, _, ver = raw.partition("@")
        return {"name": raw, "plain": "Judged quality" + (" (rubric %s)" % ver if ver else ""),
                "definition": ("A model's 1-5 quality score for the conversation, under rubric "
                               "version %s. Judged, not measured: it is an opinion about meaning, "
                               "and it is comparable only with other scores from the same rubric "
                               "version." % (ver or "unknown")),
                "fidelity": "judged", "basis": "session", "higher_is_better": True}

    # composition of traffic: share:intent
    if raw.startswith("share:"):
        dim = raw.split(":", 1)[1]
        return {"name": raw, "plain": "Share of traffic by %s" % _DIM_NOUN.get(dim, dim),
                "definition": ("What proportion of this tenant's conversations each %s accounts "
                               "for. A change here moves every aggregate without anything getting "
                               "better or worse." % _DIM_NOUN.get(dim, dim)),
                "fidelity": "derived", "basis": "session", "higher_is_better": None}

    # instrumentation coverage: coverage:kb_lookup
    if raw.startswith("coverage:"):
        st = raw.split(":", 1)[1]
        noun = _STEP_NOUN.get(st, _pretty(st).lower())
        return {"name": raw, "plain": "%s logging coverage" % noun.capitalize(),
                "definition": ("Share of conversations whose agent emits %s steps at all. A drop "
                               "here is a logging change, not a service change: metrics derived "
                               "from those steps lose coverage and must say so." % noun),
                "fidelity": "derived", "basis": "session", "higher_is_better": True}

    # the launch pseudo-series, used when a cohort has no history to regress from
    if raw == "launch":
        return {"name": raw, "plain": "New to this deployment", "definition":
                ("This cohort did not exist before the window, so it has no past to be compared "
                 "with. It is measured against peer cohorts over the same days instead."),
                "fidelity": "derived", "basis": "session", "higher_is_better": None}

    # step level: <step_type>.<suffix>
    if "." in raw:
        st, _, suf = raw.partition(".")
        noun = _STEP_NOUN.get(st, _pretty(st).lower() or "step")
        if suf in _SUFFIX:
            plain, fid, defn, up = _SUFFIX[suf]
            return {"name": raw, "plain": "%s %s" % (noun.capitalize(), plain),
                    "definition": defn.format(what=noun), "fidelity": fid, "basis": "step",
                    "higher_is_better": up}
        return {"name": raw, "plain": "%s %s" % (noun.capitalize(), _pretty(suf).lower()),
                "definition": ("Measured on %s steps in the agent's execution log." % noun),
                "fidelity": "measured", "basis": "step", "higher_is_better": None}

    return {"name": raw, "plain": _pretty(raw) or "Unnamed measure",
            "definition": "Computed from the deployment's own logs.",
            "fidelity": "derived", "basis": "session", "higher_is_better": None}


# --------------------------------------------------------------------------------------------
# 2. Plain English for cohorts and findings
# --------------------------------------------------------------------------------------------

def cohort_label(dim, value, tenant=None):
    """A phrase an operator can read. Never renders a bare key."""
    if not dim or dim == "__all__" or not value or value == "__all__":
        return "this deployment" if not tenant or tenant == "*" else "all %s traffic" % tenant
    v = _pretty(value)
    if dim == "intent":
        return "%s enquiries" % _intent_words(value)
    if dim in ("tool", "tool_name"):
        return "the %s tool" % value
    if dim == "agent_id":
        return "the %s agent" % value
    if dim == "channel":
        return "%s conversations" % v.lower()
    if dim == "segment":
        return "%s customers" % v.lower()
    return "%s %s" % (v, _DIM_NOUN.get(dim, dim))


# Two phrasings per cause: one for when the cohort IS the thing being blamed (the tool, the agent),
# one for when the cohort is the traffic affected by it. Saying "a tool behind the X tool" reads as
# a machine assembling a sentence, which is exactly the impression the title exists to avoid.
_TITLE = {
    "kb.gap": ("Customers asking about {label} are not getting a useful answer.",
               "Customers asking about {label} are not getting a useful answer."),
    "tool.contract_break": ("A tool behind {label} reports success while returning nothing.",
                            "{Label} reports success while returning nothing."),
    "tool.outage": ("A tool behind {label} is failing outright.",
                    "{Label} is failing outright."),
    "prompt.regression": ("Conversations in {label} got longer and more expensive without getting better.",
                          "Conversations handled by {label} got longer and more expensive without "
                          "getting better."),
    "model.change": ("A model change altered how {label} behaves.",
                     "A model change altered how {label} behaves."),
    "routing.error": ("Conversations in {label} are being sent to the wrong place.",
                      "Conversations routed through {label} are being sent to the wrong place."),
}

_DISMISS_TITLE = {
    "traffic_mix": "The mix of questions changed - the totals moved, the service did not.",
    "load": "Traffic ran far above normal and the platform slowed down, then recovered.",
    "judge_change": "The quality-scoring rubric changed version - the scores moved, the agents did not.",
    "unknown": "Something moved that we could not pin to any cohort.",
}

# dimensions where the cohort names the component being blamed rather than the traffic affected
_SUBJECT_DIMS = ("tool", "tool_name", "agent_id")


def title(cause_class, label, is_regression=True, dim=None):
    """One plain sentence. No metric name, no cohort key, no architecture vocabulary."""
    if not is_regression:
        tpl = _DISMISS_TITLE.get(cause_class)
        if tpl:
            return tpl
        return "%s looked like a problem and is not one." % (label[:1].upper() + label[1:])
    pair = _TITLE.get(cause_class)
    if pair:
        tpl = pair[1] if dim in _SUBJECT_DIMS else pair[0]
        return tpl.format(label=label, Label=label[:1].upper() + label[1:])
    return "Service quality dropped in %s." % label


def status_line(is_regression, from_day, to_day, corpus_days=None, days_running=None):
    """The episode reframe: a fault with a start and an end, and whether anyone was told.

    Never hardcodes a day count - every number comes from the report. ``days_running`` is the
    impact block's figure and wins when present: the scan window deliberately opens before onset,
    so the window span and the duration are not the same number and must not be shown as one.
    """
    days = int(days_running) if days_running else max(1, int(to_day) - int(from_day) + 1)
    ended = corpus_days is not None and int(to_day) < int(corpus_days) - 1
    if not is_regression:
        return "Examined over days %d-%d and dismissed" % (from_day, to_day)
    if ended:
        return ("Ended - ran %d days and stopped on day %d. Nobody was told." % (days, to_day))
    return ("Still running - %d days so far, and it has not stopped." % days)


# --------------------------------------------------------------------------------------------
# 3. Baseline justification - the sentence the Decision Quality points are actually about
# --------------------------------------------------------------------------------------------

def baseline_justification(mode, peers=(), from_day=None, lookback=20):
    if mode == "peer":
        base = ("This cohort has no before-period. It appears for the first time inside this "
                "window, so comparing it with its own past would find nothing no matter how well "
                "tuned the detector is - it was born broken.")
        if peers:
            return (base + " We compare it instead with %s, which share its milestone chain in the "
                    "catalog and so are asked to do the same work." % ", ".join(peers))
        return base + " We compare it instead with sibling cohorts over the same days."
    return ("Clean history exists before this started, so the cohort is its own best control: its "
            "own %d days before day %s, which removes any difference between cohorts from the "
            "comparison." % (lookback, from_day))


def outcome_note(res, bres, lost, excess_per_day, metric_plain="Resolution"):
    """Emitted only when the mechanism moved and the outcome did not.

    This is the sentence that separates reading your own data from pattern-matching a template: for
    a fault whose outcome metric never moves, claiming lost resolutions is simply false.
    """
    return ("%s did not move: %.4f against a baseline of %.4f, which is noise. This fault costs "
            "money and customer time, not resolutions - about $%.2f a day in extra spend, and "
            "longer conversations for the same result. Reporting it as lost resolutions would be "
            "false." % (metric_plain, res, bres, excess_per_day))


# --------------------------------------------------------------------------------------------
# 4. The decision block. All three fields are schema-required; all three are read by judges.
# --------------------------------------------------------------------------------------------

_ASK = {
    "kb.add": "Publish knowledge-base content covering {label}, so the agent has something to "
              "answer from.",
    "kb.synonym": "Add the phrasings customers actually use for {label} to the retrieval index, so "
                  "existing content is found.",
    "prompt.edit": "Edit the prompt behind {label} to remove the extra confirmation steps it "
                   "gained, keeping the wording that carries a compliance purpose.",
    "tool.validate": "Make {label} check the payload it gets back and treat an empty response as a "
                     "failure instead of a success.",
    "tool.fallback": "Give {label} a fallback path so a customer is not left with an empty answer "
                     "when the primary source returns nothing.",
    "routing.change": "Change how {label} is routed so these conversations reach somewhere that can "
                      "resolve them.",
    "revert": "Revert the change behind {label} to the version that was running before.",
    "no_action": "Record that {label} needs no change.",
}

_ALT = {
    "kb.add": "reject and route these questions to a human queue instead",
    "kb.synonym": "reject and have the content team rewrite the source articles instead",
    "prompt.edit": "reject and keep the current wording if it was added deliberately",
    "tool.validate": "reject and take it up with the team that owns the upstream service",
    "tool.fallback": "reject if there is no second source of truth to fall back to",
    "routing.change": "reject and fix the underlying cause instead of redirecting",
    "revert": "reject and fix forward instead",
    "no_action": "reject and investigate further",
}

_RISK = {
    "kb.gap": ("Low, and recoverable. The likeliest alternative is that these questions are "
               "genuinely outside this agent's scope - in which case the content is added, nothing "
               "regresses, the number simply does not move, and the right answer is a routing rule "
               "instead. No existing behaviour changes either way."),
    "tool.contract_break": ("Moderate. The likeliest alternative is that an empty payload is a "
                            "legitimate upstream state - 'no records found' rather than a failure. "
                            "Validation would then convert silent wrong answers into visible "
                            "errors: better for the customer, but the declared error rate will "
                            "rise and will look like a new problem to anyone watching that chart."),
    "tool.outage": ("Moderate. The likeliest alternative is that the failures are downstream of a "
                    "dependency this change does not touch, in which case the fix is inert and the "
                    "outage continues under a different error class."),
    "prompt.regression": ("Moderate, and partly a business call. The likeliest alternative is that "
                          "the extra confirmation turns were added deliberately, for safety or "
                          "compliance. Editing them back out would trade cost and customer time "
                          "for risk the business may have accepted on purpose - which is why this "
                          "is being asked rather than applied."),
    "model.change": ("Moderate. The likeliest alternative is that the model change is incidental "
                     "and the movement belongs to something that landed near it in time. Reverting "
                     "a model would then cost capability for no gain."),
    "routing.error": ("Moderate. The likeliest alternative is that the routing is correct and the "
                      "destination is what is failing, in which case redirecting traffic moves the "
                      "problem rather than fixing it."),
}

_STOP = {
    "kb.add": ("the golden-set replay regresses any known-good conversation, or the business "
               "confirms this product line is being withdrawn or repriced - in which case the "
               "answer is a routing rule, not new content nobody will maintain."),
    "kb.synonym": ("the golden-set replay regresses any known-good conversation, or the new "
                   "phrasings pull unrelated questions into this cohort, which would trade one "
                   "wrong answer for another."),
    "prompt.edit": ("the golden-set replay regresses any known-good conversation, or the wording "
                    "being removed turns out to carry a compliance sign-off - reverting that is a "
                    "compliance decision, not an engineering one."),
    "tool.validate": ("the golden-set replay regresses any known-good conversation, or the team "
                      "that owns the upstream service confirms an empty payload is an expected "
                      "state, in which case the agent's wording needs to change, not its checks."),
    "tool.fallback": ("the golden-set replay regresses any known-good conversation, or there is no "
                      "genuinely independent second source - a fallback to stale data would answer "
                      "confidently and wrongly, which is worse than answering nothing."),
    "routing.change": ("the golden-set replay regresses any known-good conversation, or the "
                       "receiving queue has no staffed capacity for the redirected volume."),
    "revert": ("the golden-set replay regresses any known-good conversation, or the change being "
               "reverted also carries a fix we would lose by rolling it back."),
    "no_action": "new evidence localises the movement to a cohort we can act on.",
}


def asking_approval_for(change_type, label):
    """One imperative sentence naming the action and its alternative. Never 'investigate further'."""
    action = _ASK.get(change_type, "Apply a {ct} change to {label}.".format(
        ct=change_type, label=label)).format(label=label)
    return "%s Or %s." % (action, _ALT.get(change_type, "reject and route it to the owning team"))


def risk_if_diagnosis_wrong(cause_class):
    return _RISK.get(cause_class, (
        "Moderate. The evidence points one way but this is circumstantial, not a controlled "
        "experiment. If the cause is something else, the change is inert and the number does not "
        "move - which the replay would show before anything reached a customer."))


def would_not_ship_if(change_type):
    """Deliberately pairs one technical and one business condition. A stop condition that is purely
    technical is a test; one that can also be triggered by the business is change management."""
    return "We would not ship this if " + _STOP.get(change_type, (
        "the golden-set replay regresses any known-good conversation, or the team that owns this "
        "surface has a reason to keep it as it is."))


def description(change_type, label, target):
    return "%s Target: %s." % (
        _ASK.get(change_type, "Apply a {ct} change to {label}.".format(ct=change_type, label=label)
                 ).format(label=label), target)


# --------------------------------------------------------------------------------------------
# 5. Attribution vocabulary. The screen must never render the word "caused".
# --------------------------------------------------------------------------------------------

def attribution_plain(att, confidence=None):
    if not att:
        return ("No configuration change lines up with this window, so we are not attributing it to "
                "one. The movement is measured; its trigger is not identified.")
    return ("A %s change landed on day %s and the field it controls flips for exactly this cohort "
            "on that day. That is strong circumstantial evidence, not a controlled experiment: we "
            "say attributed, not caused. The replay result is the closest thing to proof available."
            % (att.get("kind", "configuration"), att.get("day", "?")))
