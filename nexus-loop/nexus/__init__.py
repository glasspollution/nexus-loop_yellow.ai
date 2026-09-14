"""Nexus Loop: read an agent deployment's logs, find what broke, explain why, refuse what cannot be measured.

Pipeline (handoff section 5):
    loader     -> daily counters for every metric x cohort + per-session arrays        (stage 1)
    detect     -> one uniform changepoint test over every series, at scales 3 and 7    (stage 2)
    incidents  -> breadth, global drivers, composition, explanation forest, benign     (stage 3)
    diagnose   -> runtime layer -> cause class, config / version-flip attribution      (stage 4)
    report     -> loop-report.json with honesty fields, gaps and refusals
    validate   -> schema gate + report-contract checks

Nothing in this package reads ground truth, and no tenant, intent, agent, tool or fault day is named in it.
"""

__version__ = "1.0.0"
