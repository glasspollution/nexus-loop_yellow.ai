# Nexus Loop — what is real, what is stubbed, what breaks at 100×

One page, as asked. Faking things in six days is fine; hiding it is not.

---

## What is real

Everything below runs on the corpus, from one command, with no human in the loop until the
approve button.

| | |
|---|---|
| **Detection** | One changepoint test over every metric × cohort series (~1,400 of them on the practice corpus), overdispersion-adjusted, plus breadth, composition and explain-away tests. No thresholds tuned per scenario. |
| **Cohorting** | The slice of traffic is found, not assumed. No tenant, intent, agent or tool name appears anywhere in the detection code — a generality check searches for 27 such literals on every run and fails the build if it finds one. |
| **Diagnosis** | Cause class by runtime layer, attributed to a configuration change by joining `config_timeline` on the day the controlled field flips for exactly that cohort. |
| **Dismissals** | The lookalikes are examined and written off in prose, with the measured tell that proves each one is not a regression. Silence is not dismissal, so they are emitted even when nothing else fires. |
| **Coverage** | Measured per tenant per series from the corpus, not read from the catalog. |
| **Calibration** | Agreement with the human labels in `labels/`, computed strictly within one judge version. |
| **Refusals** | Three, with the event that would have to exist, its grain, its fields and the team that owns emitting it. |
| **Replay** | Real HTTP calls to the organisers' replay service. The before/after numbers, the golden-set results and the run ids in the report are what it returned. |
| **The screen** | Reads the report and writes the human decision back into it, re-validating against the schema before saving. |

**Scale it runs at:** 80,252 sessions, 883,764 execution steps, 365,065 turns, 16 configuration
changes. About 30 seconds cold, from `python nexus-loop/run.py --kit kit`.

---

## What is stubbed or simulated

| | |
|---|---|
| **The replay service is a simulator.** | It is the organisers' `replay/serve.py`, seeded from ground truth. It is not production traffic and it is not a live experiment. Identical requests return identical results. Every before/after figure on the screen carries that caveat on the page, not in a footnote. |
| **The screen reads a static file.** | It does not stream and nothing is live. Re-running the pipeline and reloading is the entire refresh mechanism. |
| **No authentication.** | Whoever opens the page can sign a decision. The name on a decision is typed, not verified. In a real deployment this is SSO and the approval record carries an identity the system did not have to be told. |
| **The standard is not mined.** | `standard[]` is empty. The intended method — top decile of resolved, milestone-complete sessions per cohort within one judge version — is the only framing that catches a regression whose outcome metric never moves, and we detect that fault another way instead. |
| **The abandonment-reason judge is not built.** | A09 asks *why* people gave up. How many is measured; why is a judgement. We refuse it rather than answer it, and the refusal names what would be needed. |
| **Self-assessment is one cycle.** | Three observations, one per change class. The report gives the counts and explicitly declines to compute a hit rate from them. |
| **Synthetic data only.** | Every number here comes from one generator family. No production logs have been near this. |

### Three things we could have claimed and did not

- **A calibration figure for the A09 judge.** The example reports in the kit reuse the
  quality-rubric agreement for it. `labels/` contains no abandonment-reason labels at all, so no
  agreement can be computed and none is claimed.
- **A hit rate.** From n=1 per change class, 100% is arithmetic, not evidence.
- **A prediction error on two of three fixes.** We predicted a change in the mechanism we detected
  on; the replay reports the outcome. Subtracting one from the other gives a confident-looking
  number that means nothing, so it is left out with the reason stated.

### One place the system uses judgement rather than deriving from data

Mapping the operator's questions in `asks.md` to metrics — A01, A04, A06, A09 — is hand-authored.
It interprets human language, which is the legitimate use of judgement under Rule 1. Everything
downstream of it is computed.

### Where we disagree with the catalog, and why

The catalog states that `v2_flow` sessions emit no `tool_call`, `kb_lookup` or `guardrail` steps.
In the corpus only `tool_call` is absent — `v2_flow` emits 10,997 `kb_lookup` rows. We report the
catalog's 0.72 / 0.93 for the tool metrics, where it is correct and independently reproduced from
the data, and we measure coverage from the corpus for everything else rather than propagating a
figure that would understate what we can see. A number invented in the modest direction is still
invented.

---

## What breaks at 100×

100× is roughly 8 million conversations and 88 million steps per run.

**First to break: the loader.** It is a single-pass, in-memory build of a dense
`sessions × metrics × 2` counter matrix, plus a ~70 MB pickle cache per kit. At 100× that matrix
does not fit in memory on one machine. The fix is not exotic — the counters are additive, so the
pass shards by tenant-day and reduces — but it is the thing that fails first and it fails hard,
not slowly.

**Second: cohort enumeration.** The scan is one changepoint test per metric × cohort series and
the cohort space grows with the number of distinct values per dimension. At 100× the series count
grows faster than the data does, and the multiple-comparisons burden grows with it. The z
threshold was chosen for this corpus size and would have to be recalibrated, or replaced with a
false-discovery-rate procedure, or the scan restricted to cohorts above a volume floor. We know of
two real faults it already misses at this scale — a tool error ramp peaking at z=3.81 and a channel
abandonment ramp — and lowering the threshold to catch them raises the false-alarm rate. That
trade has not been made; it is a product decision, not a tuning one.

**Third: the cardinality budget.** We refuse a breakdown above 200 distinct values. At 100× the
fields currently under budget will cross it, and the budget is a fixed number in a catalog rather
than a function of the data. It should be a rate, not a constant.

**Fourth: judged metrics.** Judging scales linearly in cost and every judged number needs
calibration within its judge version. At 100× you sample rather than judge everything, and the
honest reporting of that sample's coverage becomes a bigger part of the product than it is here.

**What does not break:** the detection mathematics is scale-free — changepoint statistics on
counters care about counts, not rows. Attribution is a join against 16 configuration rows.
Diagnosis is per incident, and incidents do not grow with traffic. The screen renders one finding.

**Honest about the testing:** all of the above is reasoning about the implementation, not a
measurement. We have not run this at 100×. The largest thing it has been run on is 80,252 sessions.

---

## What we would not claim to a judge

- Diagnosis generalises less well than detection. On an independent benchmark of 16 fault types
  the system never saw, it localises 14 of 16 to the exact cohort but gets the cause right on 11.
  Detection is the strong half.
- Every recall number we quote counts only exact-cohort matches. An earlier version of our own
  evaluator let a tenant-wide finding match any fault and reported 8/8 where the truth was 6/8.
- The machine score is 55.00/55 on the practice corpus and on three freshly generated sealed
  corpora. The sealed run is the only score that exists, and we have not seen it.
