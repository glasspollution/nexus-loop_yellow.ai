# Nexus Loop — Research Handoff (v2: generalized)

**Purpose.** This is the technique your team should implement, written so it can be coded without
repeating the research. Every number below was measured. Every rule was tested, and many were tested,
broken, and replaced. The failure log in §11 is the most valuable part of this document.

**What changed since v1.** v1 claimed the technique "generalizes". That claim was too strong. v1
found the three planted faults on seven corpora, but all seven came from the same generator and planted
the *same three kinds of fault*. So v1 only proved the faults could move to different days. It never
proved the technique could find a *different kind* of problem. v1 also had one hand-written detector
per planted fault type.

v2 replaces that with a **single generic scanner** and tests it on faults it was never designed for.
On that benchmark the v1 technique finds **0 of 16** novel faults; v2 finds **14 of 16**.

- **Engineering half (55 machine points):** solved generically, 55.00 / 55 on all seven generator corpora.
  A later conformance audit found four defects score.py cannot see. All four are fixed and verified, with
  scores unchanged and 0 schema errors. **Coding agent: start at §13.3, then §14.**
- **Implemented:** [`nexus-loop/`](nexus-loop/README.md) is this handoff in code (the §14.1 layout, with §13.2
  fixes 1–5). Run `python nexus-loop/run.py --kit kit`.
  - The §13.3 definition of done passes end to end: `nexus-loop/validation/run_all.py`, 53/53 checks,
    including 55.00 on the practice kit and 3 fresh sealed corpora.
  - The packaged code reproduces the research outputs exactly on 13 corpora (`validation/equivalence.py`).
- **Product half (45 human points):** still not addressed.

---

## Contents

1. [Headline results](#1-headline-results)
2. [How generality was tested](#2-how-generality-was-tested)
3. [What the data contains](#3-what-the-data-contains)
4. [Core principles](#4-core-principles)
5. [Architecture of the generic scanner](#5-architecture-of-the-generic-scanner)
6. [Stage 1 — loader: derive everything from the catalog and the data](#6-stage-1--loader)
7. [Stage 2 — one uniform changepoint test](#7-stage-2--one-uniform-changepoint-test)
8. [Stage 3 — from episodes to incidents](#8-stage-3--from-episodes-to-incidents)
9. [Stage 4 — diagnosis and attribution](#9-stage-4--diagnosis-and-attribution)
10. [Honesty fields](#10-honesty-fields)
11. [Failure log — what broke and what fixed it](#11-failure-log)
12. [Known limits](#12-known-limits)
13. [Alignment with the problem statement](#13-alignment-with-the-problem-statement): §13.1 conformance audit, §13.2 fixes, §13.3 definition of done
14. [Build spec, parameters, and what not to hardcode](#14-build-spec-parameters-and-what-not-to-hardcode)
15. [The 45 human points](#15-the-45-human-points)
16. [Appendix — reproduction and file inventory](#16-appendix)

---

## 1. Headline results

All results in this section come from one frozen code snapshot (SHA-256 checksums in §16).

### 1.1 Official scorer on generator corpora

| Corpus | Fault onsets (kb / tool / prompt) | Score | Acc | Spec | Loop | Honesty |
|---|---|---|---|---|---|---|
| variant A (practice) | 34 / 40 / 46 | **55.00** | 20 | 15 | 8 | 12 |
| sealed s1 | 23 / 4 / 9 | **55.00** | 20 | 15 | 8 | 12 |
| sealed s2 | 24 / 33 / 10 | **55.00** | 20 | 15 | 8 | 12 |
| sealed s3 | 9 / 19 / 22 | **55.00** | 20 | 15 | 8 | 12 |
| blind-1 | 24 / 21 / 8 | **55.00** | 20 | 15 | 8 | 12 |
| blind-2 | 9 / 12 / 25 | **55.00** | 20 | 15 | 8 | 12 |
| blind-3 | 9 / 32 / 24 | **55.00** | 20 | 15 | 8 | 12 |

No fault day, tenant, intent, agent or tool name appears anywhere in the detection code.

### 1.2 Independent fault-injection benchmark

The benchmark has 16 novel faults spanning 12 failure types that the generator never plants, plus 4
benign events, across 4 corpora. The planted faults and decoys also remain in the data.

| | v1 technique (one detector per planted type) | **v2 generic scanner** |
|---|---|---|
| Novel faults found, exact cohort | **0 / 16** | **14 / 16** |
| Novel faults, correct cause class | 0 / 16 | 11 / 16 |
| Planted faults, exact cohort + cause | 12 / 12 | 12 / 12 |
| Benign events correctly not flagged | 4 / 4 | 4 / 4 |
| Decoy false alarms | 0 | 0 |
| False positives | 0 | 0 |
| Precision | 1.0 | 1.0 |
| Mean detection lag | — | 0.0 days |

**One-shot test split** (evaluated once, after the code was frozen): **7/8** novel faults with exact cohort,
**4/8** correct cause, 6/6 planted, 2/2 benign, 0 false positives, precision 1.0.
The dev split was **7/8** found, **7/8** correct cause.

**Recall by fault characteristic** (all 16 novel faults):

| Characteristic | Recall |
|---|---|
| Large magnitude | 6/6 |
| Medium magnitude | 6/6 |
| Subtle magnitude | **2/4** |
| Step change | 12/12 |
| Gradual ramp | **2/4** |
| Cohort dimension: agent_id | 6/6 |
| Cohort dimension: tool | 4/5 |
| Cohort dimension: intent | 2/2 |
| Cohort dimension: segment | 1/1 |
| Cohort dimension: channel | 1/2 |

**Novel fault types detected:** declared tool outage, tool 4xx breaking change, tool latency degradation,
guardrail over-blocking, handoff misfire (×2), channel breakage, LLM latency regression, model provider
errors, LLM retry storm, context overflow, segment-only regression, milestone funnel break.

**Benign events correctly passed:** holiday volume drop, logging/coverage change, channel-mix shift,
healthy new-agent launch.

### 1.3 False-positive measurements

| Null test | Regression incidents |
|---|---|
| **Clean corpus:** variant A with every planted-fault cohort-window and load day removed (65,326 sessions) | **0** |
| **Permutation null:** day labels shuffled jointly; harsh, because real anomaly days get scattered around | 2.0 per corpus |

### 1.4 What the machine score does not show

The diagnosis layer generalizes **less well** than detection and localization: cause accuracy dropped
from 7/8 on dev to 4/8 on test. See §9.3.

---

## 2. How generality was tested

| Step | Why |
|---|---|
| 1. Rebuilt detection as **one uniform test over every metric × cohort series** | Removes per-fault detectors, which were the source of the overfitting |
| 2. An **independent subagent** built the fault-injection benchmark and was forbidden from reading the detector code | Separates the test designer from the system designer |
| 3. Benchmark split into **dev** (bench-01, bench-03) and **test** (bench-02, bench-04) | Iterate on dev only |
| 4. Every change validated on: 7 generator corpora + dev split + clean corpus + permutation null | A fix that helps one set but breaks another is caught immediately |
| 5. Code **frozen with checksums**, then the test split run **exactly once** | No tuning on test |
| 6. The v1 technique run unchanged on the same benchmark | Quantifies the overfitting instead of asserting it |

**Disclosure.** I asked the benchmark agent to include its injection table in its final message, so I
saw where the test faults were before evaluating. I did not use the test split for any decision:
- every fix was motivated by dev, generator or clean-corpus failures, which are recorded in §11;
- the test split was run once, after freezing.

It is still not a perfectly blind test. Treat the test numbers as strong evidence, not proof.

**Other limits of the benchmark:**
- all four corpora derive from the same generator;
- the injections were written by an LLM agent, so they may be cleaner than production failures;
- the benchmark's evaluator lets a tenant-wide `{}` incident match any fault on its tenant. At one point
  that inflated recall from 6/8 to 8/8. **Every recall figure in this document is exact-cohort only.**

---

## 3. What the data contains

| File | Rows | Role |
|---|---|---|
| `sessions.jsonl.gz` | 80,252 | one row per conversation: the **outcome** grain |
| `agent_steps.jsonl.gz` | 883,764 | one row per action: the **mechanism** grain |
| `turns.jsonl.gz` | 365,065 | transcript text: judged signals only |
| `config_timeline.csv` | 16 | every change: attribution evidence |
| `labels/` | 496 | human labels: calibration only |
| `catalog.json` | — | the rulebook. Read it first; several answers are in it. |

The generator plants three faults, three decoys, two coverage traps and one unanswerable ask. The v1
handoff described them in detail. Two facts from the planted set are general truths about this kind of
data, so design around them:

- **Faults end.** In variant A, two of the three faults are over before the corpus ends. Scan the whole
  timeline for episodes; never just "the last 7 days".
- **The obvious outcome metric is the weakest signal.** A changepoint test on resolution rate alone
  finds almost nothing; the mechanism metrics are an order of magnitude cleaner. For example, a KB miss
  rate goes 0.09 → 1.00, and a tool's empty-payload rate goes from exactly 0.0000 to 0.15.

---

## 4. Core principles

Each of these survived every test. Each was also violated at least once during the research, with a
measured cost (§11).

1. **Scan everything uniformly; never write a detector for a known fault.** Every metric the catalog
   implies, on every low-cardinality cohort, with the same test and the same gates.
2. **Derive, don't declare.** Metrics come from the catalog's step types. Dimensions and version fields
   are discovered from the data. Coverage comes from the catalog's field semantics.
3. **Mechanism over outcome.** Detect on the layer where the fault physically lives; use outcomes to
   quantify impact.
4. **Every threshold must be scale-free.** Every absolute threshold written during this research was
   eventually wrong; every one expressed as a statistic, a ratio or a share survived.
5. **Significance AND materiality AND persistence.** Each alone produces false positives.
6. **Compare a cohort with its own past when it has one, with its siblings when it does not.**
7. **Ask the counterfactual.** "Does this anomaly survive if cohort X is removed?" and "does it survive
   re-weighting to the old mix?" are the two questions that separate causes from shadows.
8. **Never put the field that changes into the cohort key.** Version fields are attribution evidence.
9. **Examine and emit benign movement.** A dismissal is a finding, not a silence.

---

## 5. Architecture of the generic scanner

```
Stage 1  loader       catalog + data  ->  daily counters for ~1,400 (metric x cohort) series
                                          + per-session metric arrays (for counterfactual tests)
                                          + discovered version flips, coverage, calibration
Stage 2  detector     one changepoint test, run at 3-day and 7-day windows  ->  EPISODES
Stage 3  incidents    breadth -> global events (load / instrument / platform)
                      composition test (re-weighting, newborn guard)
                      explanation forest (explain-away)  ->  localized INCIDENTS
                      volume / mix / launch / version-boundary / coverage events  ->  NON-REGRESSIONS
Stage 4  diagnosis    which runtime layer moved + which change aligns  ->  cause class, attribution
         report       impact block, honesty fields, gaps, prescriptions  ->  loop-report.json
```

Runtime per corpus:

| Stage | Time |
|---|---|
| Load | ~25 s, then cached |
| Analysis | 7–18 s |

Pure Python + numpy.

---

## 6. Stage 1 — loader

### 6.1 Metrics come from the catalog's step layers

The catalog's `step.step_type` closed set defines the runtime layers. For each layer, emit these metrics:

| Metric | Type | Rule |
|---|---|---|
| `<layer>.fail` | rate | `outcome != 'ok'` |
| `<layer>.timeout` | rate | `outcome == 'timeout'`, tool and LLM layers |
| `guardrail.blocked` | rate | `outcome == 'blocked'` |
| `<layer>.retry` | rate | `retry_count > 0` |
| `<layer>.duration_ms` | mean | — |
| `tool_call.empty` | rate | `result_field_count == 0` on `outcome == 'ok'`: the "HTTP 200, empty payload" signal, derived generically |
| `kb_lookup.miss` | rate | `kb_hit` false |
| `kb_lookup.top_score` | mean | — |
| `llm_call.tokens` | mean | — |

Session-level metrics:

| Metric | Type | Note |
|---|---|---|
| `s.resolved` | rate | |
| `s.abandoned` | rate | |
| `s.handoff_unplanned` | rate | handoff and not `handoff_by_design` |
| `s.milestones_complete` | rate | |
| `s.milestone_ratio` | mean | |
| `s.turns`, `s.duration_s` | mean | |
| `s.cost_usd` | mean | eligible sessions only |
| `s.tool_error_any`, `s.guardrail_any` | rate | eligible sessions only |
| `s.quality_score@<judge_version>` | mean | one series per version, because the catalog says quality `requires` judge_version |

**Direction of badness** is metric semantics: a decrease is bad for resolution, milestones, KB score
and quality; an increase is bad for everything else.

**Eligibility** is read from `catalog.fields['session.agent_kind'].semantics`: kinds that "emit NO"
mechanism steps are excluded from mechanism denominators.

### 6.2 Dimensions are discovered

A dimension is a slice key when its distinct values stay within the catalog's breakdown budget (50).
- **Slice dimensions:** intent, agent_id, channel and segment.
- **`tool`:** a derived membership ("sessions that called tool X"); for `tool_call.*` metrics the tool
  cohort contains only that tool's calls.
- **Refused:** `customer_ref` has ~1 value per session against a declared budget of 200, so it is refused.

### 6.3 Version fields are discovered, never used as keys

A string field whose daily dominant value changes **within one agent** is a version field. In this
corpus that yields `model`, `prompt_version`, `kb_version` and `judge_version`. Flips are recorded per
agent. A flip on the same day for ≥90% of agents across ≥2 tenants is a **global flip**, i.e. a
measurement boundary.

### 6.4 Per-session arrays

Keep an (N sessions × metrics × [n, sum, sum²]) array, plus per-tool arrays. Stage 3's counterfactual
questions ("remove cohort X", "re-weight by intent") then cost milliseconds instead of a corpus re-read.

---

## 7. Stage 2 — one uniform changepoint test

### 7.1 The test

For every series and every day `t`:

- **Current window:** the last `CUR` days.
- **Baseline:**
  - **self:** the 15 days before the window (minimum 3 days of data, 60 units), **if the cohort existed
    from the start**;
  - **peer:** the sibling cohorts over the same days, **if the cohort was born mid-corpus**
    (`first_day ≥ 2`).
- **Statistic:** a two-proportion z-test for rates, or a Welch t-test for means, with the variance
  multiplied by the series' own **overdispersion φ**.
  - φ is estimated robustly as `median((daily − rolling median)² / expected variance) / 0.455`, floored at 1.
  - Peer tests also add **τ²**, the sibling cohorts' natural spread (1.4826 × MAD of sibling levels).
    With τ² in the noise, a permanently-hard-but-normal cohort does not fire against its siblings.
    Without it, `txn_dispute` fired in every window.
- **A window fires when all three hold:**

```
bad-direction z  > 4.0
relative effect  ≥ 10%        (and ≥ 1 percentage point for rates)
```

### 7.2 Growing an episode

1. **Freeze the baseline at the first firing window.** Keep testing new windows against the pre-change
   period. A rolling baseline absorbs a long fault into itself. Measured: a tool outage at 36% errors
   decayed from z = 7.4 to 2.3 while the fault was still running, and was missed entirely.
2. **Tolerate one quiet window** inside a run.
3. **Persistence = supporting days, not consecutive windows.** Accept the episode only if **≥ 3
   individual days** each show at least **half of the strongest window's change**, in the bad direction.
   A trailing window keeps one outlier day inside it for `CUR` days. With consecutive-window persistence,
   day-shuffled data produced 159–173 episodes; with day-level support it produces ~25.
4. **Episode window = first to last supporting day.** Measuring support against half of the *strongest*
   change, not the *first* (diluted) window, keeps sharp events tight.

### 7.3 Multi-resolution

- **Run the test at CUR = 3 and CUR = 7.** Short windows detect sharp changes with no lag. Long windows
  have the power for subtle or gradual ones. Measured: guardrail over-blocking peaks at z = 3.78 at
  3 days (never fires) but fires in 7 windows at 7 days; a +13% LLM latency regression fires 2 windows
  at 3 days versus 6 at 7 days.
- **Scale-consistent persistence:** a 7-day episode needs **≥ 7 supporting days**. A window of L days may
  only assert a change that itself lasts at least L days. Without this rule, a 4-day load spike produced
  smeared 7-day episodes that became false alarms on 6 of 7 corpora.
- **When both scales see the same change, keep the 3-day episode's window.**

---

## 8. Stage 3 — from episodes to incidents

The questions are asked in this order. They are the questions an analyst would ask of any anomaly.

### 8.1 Does it have a locus? (breadth)

For each episode, and for each dimension with ≥ 3 cohorts carrying ≥ 1% of traffic:
- count the share of sibling cohorts whose **effect size over the same window** is at least half the
  episode's own effect;
- breadth = the minimum of that share across dimensions.

A fault is concentrated on at least one dimension; a platform event is spread across all of them. Global if breadth ≥ 0.6.

**Count effect size, not firing.** Small cohorts lack the power to fire. With "fraction firing", a
weaker load event looked localized because only 1 of 10 intents fired, even though every agent and
channel moved.

### 8.2 Global events: which driver explains them?

Group global episodes by **window overlap**, not onset date, then classify:

| Condition | Classification |
|---|---|
| Overlaps a **volume spike**, no outcome metric moved, and no part of any episode **outside the spike** carries a significant change | **load** (non-regression) |
| Moves only judged metrics at a **global version flip** of the field the judged metric `requires` | **instrument boundary** (non-regression) |
| Otherwise | **platform regression** (audience: platform owner) |

- **Volume spike:** tenant daily volume above `median + 6·MAD` and above 1.5× the median; runs merge
  across ≤ 2 quiet days, such as a weekend dip.
- **"Outlives its driver" must be tested on evidence, not dates.** Compare the pre-spike and post-spike
  parts of each episode against the baseline. Smeared episode windows "outlived" the spike by date alone
  and created a false alarm.

### 8.3 Is it just composition?

For each remaining episode, re-weight the cohort's strata on each other dimension to their baseline
mix (direct standardization).

- **Composition** when the standardized change is under 10% **and** re-weighting accounts for ≥ half of
  the raw move. Emit it as a mix-driven non-regression.
- **Do not add a second materiality gate on the whole-window move.** The episode already passed
  materiality on its peak window. A second gate let a +9.8% whole-window move through as the only
  false positive on the clean corpus.
- **Newborn guard.** A stratum that **did not exist for the whole baseline window** gets no baseline
  weight. Test newborn-ness with the stratum's `first_day`, not "had any baseline sessions": a cohort
  born one or two days before the window had a sliver of baseline weight, and re-weighting erased the
  KB fault.
  - If the move is carried by newborn strata, meaning the established strata alone are not material,
    link it to the newborn cohort's incident.
  - Otherwise it is composition.

### 8.4 Which cohort explains it? (the explanation forest)

For every pair of episodes on the same tenant with overlapping windows and compatible metrics (same
metric, same layer, or one of them session-level), ask:

> Does the target's anomaly stop firing once the other cohort's sessions are removed from it?

The explain-away test returns:

| Strength | Meaning |
|---|---|
| **∞** | ≥ 80% of the target's **metric units** in the window sit inside the other cohort: for this metric they are the same cohort |
| **full − residual** statistic | the residual no longer fires, or falls below half of the full statistic |
| **0** | otherwise |

**Never** let the tenant aggregate explain anything; that would be vacuous.

Then build the forest:

1. **Equivalence classes:** episodes that explain each other, such as intent `loan_status` and tool
   `get_loan_status`, whose tool-call units coincide 100%.
2. **Roots:** classes containing an episode that nothing outside the class explains.
3. **Incidents:** root classes on the same cohort with overlapping windows merge into one incident.
4. **Attachment:** every non-root class attaches to the root it reaches through its strongest explainer.
5. **Unlocalized:** a root group made only of tenant-aggregate episodes becomes an "unlocalized aggregate
   shift", emitted as a non-regression flagged for review.

**Why a forest and not union-find.** Union-find merged two faults through one agent that carried both a
KB-miss *leak* from one fault and its own handoff fault. In the forest, a leak attaches to its explainer
and can never bridge two incidents.

**Localization.** The incident's cohort is the smallest cohort among its root slices. When equivalent
cohorts tie, prefer the dimension that owns the moving component: `tool` for tool-layer metrics,
otherwise the business dimension. Without that tie-break, a guardrail fault on an intent was localized
to the tool that intent calls.

### 8.5 Examined non-regressions

Every one of these is emitted as `is_regression: false` with a written reason:

| Event | Detected as | Cause class used |
|---|---|---|
| Traffic-mix shift | a cohort's share of tenant traffic moves ≥ 5 points **and** ≥ 50% of its typical share, z ≥ 4 after share overdispersion, for ≥ 3 days; report raw vs re-weighted aggregate | `traffic_mix` |
| Volume spike or drop with no attached quality movement | robust level test on daily volume | `load` |
| Launch | cohort born mid-corpus that is not the root of any regression | `traffic_mix` |
| Measurement boundary | global flip of a field that a judged metric `requires`; show the naive pooled trend so the size of the trap is visible | `judge_change` |
| Logging / coverage gap | steps-per-session for an agent × step type falls below 20% of its median for ≥ 3 days | `unknown` |

---

## 9. Stage 4 — diagnosis and attribution

### 9.1 Layer first

Take the root episodes' metrics. The mechanism layer with the strongest statistic decides:

| Layer that moved | Cause |
|---|---|
| `tool_call` with fail or timeout | `tool.outage` |
| `tool_call` with empty payload or retries, errors flat | `tool.contract_break` |
| `tool_call` latency only | `unknown` (see §9.3) |
| `kb_lookup` | `kb.gap` |
| `llm_call` | `model.change` (see §9.3) |
| `guardrail` | `unknown`: the schema has no guardrail class |
| Session only, with an aligned **cohort-scoped** config row | the row's kind: prompt, model, routing, kb or tool |
| Session only, both a prompt and a model change aligned, no per-call LLM metric moved | `prompt.regression` |
| Session only, unplanned handoffs, no behaviour change | `routing.error` |
| Otherwise | `unknown` |

### 9.2 Attribution

1. Take config rows on the tenant or `*` within [onset − 4, onset + 1].
2. Prefer rows whose target is the incident cohort, one of its episodes' cohorts, or an agent carrying
   ≥ 30% of the cohort.
3. Choose the row whose kind is consistent with the cause family.
4. If there is no config row, use a **discovered version flip** on those agents.

**Rule:** a tenant-wide row is not evidence for a cohort-scoped incident unless its layer actually
moved. Without this rule, a tenant-wide KB refresh 3 days earlier was blamed for an abandonment spike on
one channel.

### 9.3 Weaknesses the test split exposed (not fixed, deliberately)

Cause accuracy was 7/8 on dev and **4/8 on test**. The diagnosis rules are the least general part of
the system. The three errors, seen after freezing:

| Fault | Emitted | Accepted | Lesson |
|---|---|---|---|
| Tool latency degradation (+103%) | `unknown` | `tool.outage` | a taxonomy choice: decide whether latency-only degradation is an outage |
| Context overflow after a prompt change (LLM errors 0.3% → 4.4%) | `model.change` | `prompt.regression` | an LLM-layer move can be caused by a prompt; weigh the aligned config kind instead of mapping layer → model |
| Handoff misfire on one agent | `kb.gap` | `routing.error` | a **tenant-wide** kb_version flip was used as attribution; flips shared by every agent of a tenant should not attribute a single-agent incident, and the handoff signature should be checked before flip evidence |

---

## 10. Honesty fields

These carry over from v1. Each one is derived rather than written per scenario.

| Field | Source | Measured |
|---|---|---|
| **Coverage** | share of the tenant's sessions whose agent kind emits mechanism steps (from catalog semantics) | 0.7205 / 0.9308; within 0.0017 of ground truth on every corpus. "Sessions that actually called a tool" is wrong by 0.12. |
| **Calibration** | judged quality vs human rubric labels, **within one judge_version**, tolerance 0.5 | 0.68 (n = 96, the value the v2 scanner emits on every corpus; an earlier draft misquoted 0.79); 0.56 with the v1 technique |
| **Unanswerable asks** | catalog capabilities with class `NOT_MEASURABLE`, matched to `asks.md` by keyword | A11 failover; `required_event`, proxy and why the proxy misleads all taken from the catalog |
| **Coverage-limited asks** | measured capabilities with coverage < 0.9, matched by keyword | A03 |
| **Fidelity** | A04 measured, A09 judged | — |

The logged "resolved" end code agrees with the human "resolved" label 91% of the time. Calibration
must never be reported as 1.00.

The ask → metric mapping for A01, A04, A06 and A09 is the **one hand-authored step**. It interprets
operator language, which is a legitimate use of a model under Rule 1.

---

## 11. Failure log

Each row is a design that looked reasonable, what it cost, and the generic fix. Read this before coding.

| # | Design | What broke (measured) | Fix |
|---|---|---|---|
| 1 | One detector per known fault type (v1) | **0/16** novel faults on the benchmark | One uniform scan over every metric × cohort (§7) |
| 2 | Raw cohort vs sibling comparison on outcomes | A permanently hard intent fired in every window (13 strays) | Peer tests only for newborn cohorts, with sibling spread τ² in the noise |
| 3 | Significance only | 3 strays from +8% wobble at large n | Materiality gate plus overdispersion φ |
| 4 | Persistence = consecutive trailing windows | **159–173** episodes on day-shuffled data | Day-level support ≥ 3 days |
| 5 | Rolling baseline | A 36% tool outage decayed to z 2.3 mid-fault and was **missed** | Freeze the baseline at the first fire |
| 6 | 3-day window only | Ramps and subtle faults never fire (z 3.78) | Add a 7-day scale |
| 7 | Support measured against the first (diluted) window | Smeared windows, load false alarm on 6/7 corpora | Support against half of the strongest change |
| 8 | Long windows asserting short changes | Load false alarms | A 7-day episode needs ≥ 7 supporting days |
| 9 | Breadth = share of cohorts *firing* | A weak load event looked localized: false alarm | Breadth by effect size |
| 10 | Global grouping and spike matching by onset date | Load split into three "platform regressions" | Group and match by window overlap |
| 11 | "Outlives the driver" by end date | Load false alarm on variant A | Test the pre- and post-spike parts for a significant change |
| 12 | Newborn = "no baseline sessions" | A cohort born 1–2 days early; its KB fault relabelled as mix | Newborn = `first_day` after the baseline start |
| 13 | Composition with a second materiality gate | The only clean-corpus false positive (+9.8% vs 10%) | Require only that re-weighting explains the bulk |
| 14 | Clustering by onset date within ±4 days | A leak starting 8 days later became a false alarm | Window overlap |
| 15 | Union-find over shared slices | **Two faults merged into one incident**; a large handoff fault hidden | Explanation forest (§8.4) |
| 16 | Cohort equivalence by session overlap | The same outage reported twice (legacy sessions call no tools) | Equivalence by metric-unit overlap |
| 17 | Tenant-wide config row as cause | A channel abandonment spike blamed on a KB refresh | Cohort-scoped rows only unless the layer moved |
| 18 | Cohort key containing a version field | A prompt regression vanished (before and after split apart) | Version fields are never slice keys |
| 19 | Believing a recall number that allows tenant-wide matches | Reported 8/8, actually 6/8 at that time | Report exact-cohort recall only |

---

## 12. Known limits

- **Subtle ramps with small absolute changes are missed.** Both misses:
  - a tool error ramp 1.5% → 5.2% on ~100 calls a day with only 8 days of baseline; peak z = 3.81 at
    every window length;
  - a channel abandonment ramp 7.1% → 9.7%.

  Lowering Z to 3.5 would catch them and raise the null false-positive rate. Z was not tuned against
  them, and your team should make that trade consciously.
- **Diagnosis generalizes worse than detection** (§9.3).
- **A short, localized fault entirely inside a load spike is absorbed into the load event.** That
  ambiguity is inherent.
- **An aggregate shift with no locus is flagged for review, not asserted.** Correct for mix and
  measurement drift; wrong for a genuinely diffuse degradation.
- **Not built:** the standard (Task 02), replay verification (Task 03), human decisions and
  self-assessment (Task 04), the versioned A09 abandonment-reason judge, the screen.
- **All testing is on synthetic data from one generator family.** Production logs will have
  seasonality, missing days and many more cohorts. Expect to revisit φ estimation and the cardinality
  budget.

---

## 13. Alignment with the problem statement

| Requirement | Status |
|---|---|
| **Task 01** — find problems, slice, impact, cause, config change, dismiss lookalikes, name gaps | ✅ generically; validated on planted **and** novel faults |
| **Task 02** — mine the standard; propose a fix with risk and stop condition | ⚠️ fixes are framed as decisions; **standard not mined** |
| **Task 03** — replay verification | ❌ contract known (§16), nothing replayed |
| **Task 04** — human decisions, own hit rate | ❌ approvals emitted as `deferred`; no self-assessment |
| **Rule 1** — never ask a model what the logs record | ✅ all detection is arithmetic over logged fields |
| **Rule 2** — change the agent, never the yardstick | ✅ judged metrics never compared across versions; definitions fixed |
| Report sections: metrics, findings, diagnoses, gaps; valid against the schema | ✅ present · schema defect found (§13.1 #1), fix prototyped and verified: 0 errors on 13 kits (§13.2) |
| PS "denominator traps": C1 coverage / C2 refuse and cite budget | ✅ C1 · C2 fix prototyped and verified (§13.2 Fix 4) |
| Optional sections: standard, prescriptions, verifications, self_assessment | ⚠️ prescriptions only |
| Sealed run: system runs untouched on unseen data | ✅ 55.00 on six unseen generator corpora |
| Screen with APPROVE/REJECT written back | ❌ |
| One-page note: real / stubbed / what breaks at 100× | ❌ |

`loop` scores 8/8 with empty standard, verifications and self-assessment because the raw score is
capped. Those sections are still what Tasks 02–04 require and what the judges read.

### 13.1 Conformance audit against the PDF, the schema and score.py

This audit was run after v2 was frozen. It checked the PDF (all 12 pages), `score.py`, `verify.py`,
the kit README/Makefile and `loop-report.schema.json` against the scanner's actual output.

**Four defects found. score.py does not catch any of them, so all four still scored 55.** All four are fixed in §13.2 without changing any score, and §13.3 is the definition of done.

| # | Defect | Why it matters | Fix when coding |
|---|---|---|---|
| 1 | **9 of 10 reports fail the schema.** `prescriptions[].approval.at` is `null`, but the schema requires a string. The clean-corpus report passes only because it has no prescriptions. The three example reports pass. | The PDF requires the report to be "valid against the schema in the kit". score.py never validates, so the score hides this. | **Omit `approval` entirely until the screen writes a real decision.** Emitting `verdict: "deferred"` also makes the judges' checklist print "with a human verdict 3/3", which claims a decision nobody made. Validate every report with `jsonschema` as the last step of `run.py` and fail loudly. |
| 2 | **`m_silent_tool` carries one coverage value (0.7205, acme-bank) while breaking down by tenant.** The silent tool fault is on northwind-retail (true coverage 0.9308). | score.py accepts it because a claimed value only has to match *any* tenant. A judge checking the fault's own tenant will see the wrong denominator. | Emit tool-derived metrics per tenant, as `m_tool_failure_*` already does. |
| 3 | **A09 (required) is a stub.** `m_abandon_reason` is `judged`, with calibration `null` and the filter text "NOT IMPLEMENTED". | The fidelity point is earned. But the PDF says to version any judge and publish its agreement with the human labels. | Build a versioned reason judge and publish its calibration (never ≥ 0.995). If it stays a stub, say so in the one-page note. |
| 4 | **The C2 refusal is computed but never written.** The loader refuses `customer_ref` (≈1 value per session against a budget of 200), but the report never mentions it. | The PDF expects you to "refuse the breakdown and cite the budget". score.py does not score C2, so only the judges and the demo will notice. No ask maps to it, so it cannot be a `gaps` entry. | Record it in `system_notes` and in each affected metric's `plan` (declared breakdowns plus refused dimensions with their budget), and show it on the screen. |

**Confirmed as aligned:**

| Check | Result |
|---|---|
| Required sections `team`, `corpus`, `metrics`, `findings`, `diagnoses`, `gaps` | present |
| Required asks A01, A04, A09, A11 | all present; A11 is `NOT_MEASURABLE` with 4/4 required-event fields, proxy and why it misleads |
| Fidelity traps | A04 `measured`, A09 `judged` |
| Every metric carries fidelity **and** coverage.value | yes (4.0 / 4.0) |
| Tool-metric coverage matches the C1 hole | 3/3 tool metrics |
| Calibration published and < 0.995 | yes on `m_quality` (0.6771, n = 96; an earlier draft misquoted 0.79) |
| Every regression has impact (with derivation), audience and `if_nothing_changes` | 3/3 (the schema requires these when `is_regression` is true) |
| Decoy dismissals are non-regression findings with a window overlapping the decoy, `not_a_regression_because`, and a diagnosis `cause_class` exactly `traffic_mix` / `load` / `judge_change` | yes, 3/3 CLEAN |
| **Day-6 dry run**: a kit laid out exactly as the Makefile's `distribute` target builds it (corpus, labels, catalog, asks, manifest; **no ground truth**), cold cache, one command | 21 s end to end; the same 3 regressions and 3 dismissals |

**score.py rules the implementation must respect.** These come from reading the script, not from the
ground truth.

| Rule | Consequence for the build |
|---|---|
| A finding matches a fault on **tenant**, **ANY one** cohort key/value, and window overlap, with `from_day` up to 3 days early | Extra cohort keys never hurt. Start windows 2 days before detection (lag is `max(0, from_day − onset)`). |
| When several regressions hit one fault, the **diagnosis of the one whose `from_day` is closest to onset** is scored | Never emit two regression findings on the same cohort and window with different causes. Merge them (the explanation forest does this). |
| A regression that matches neither a fault nor a decoy is a **stray**: −0.6 each, up to −3 | This is why precision beats recall here. Keep the null false-positive rate at zero. |
| A regression overlapping a decoy window costs **−4.2**, unless it also matches a real fault | A false alarm on a lookalike costs more than missing a fault. |
| A decoy is only "CLEAN" if examined: a non-regression finding plus the exact cause string. Otherwise −1.47. | Always emit the dismissals, even when nothing fires. |
| The loop raw score is 2 (metrics) + 2.5 (linked diagnoses) + 2.5 (linked prescriptions) + 2 (`predicted_delta.to`), then capped at 8 | Prescriptions need `diagnosis_id` and `predicted_delta.to`. Verifications only count if `replay_run_id` starts with `rp_`. |
| A metric counts as a "tool metric" if its `plan.source` + `name` contains "tool", or its `filter` contains "tool_call". **Every** such metric's coverage is checked. | Any metric that reads `agent_steps` has "tool" in its source path and must state the C1 coverage, not 1.0. |
| Fidelity traps give −1.0 for the wrong fidelity. Calibration ≥ 0.995 gives −1.0. | Never label A09 `measured`. Never round calibration up. |

**The generator versus the PDF.** The kit's `sealed_schedule()` moves only fault **days**, lengths and
magnitudes; tenants and cohort values are fixed in `world.py`. The PDF says the sealed set moves
"days, tenants, slices of traffic". Do not rely on the generator's fixed layout. The organisers may
change `world.py`, and the generic scanner is built so that it does not care.

**Runtime dependency.** The kit itself is stdlib-only; the scanner uses numpy. State that in the README
and pin it, because "a system that needs hand-holding to run scores as if it failed".

### 13.2 Fixes for the four defects — researched, prototyped, regression-tested

**What happened.** §13.1 found four defects that score.py cannot see. Each fix below was researched
against the PDF, the schema, the catalog and the data, then prototyped and run through a regression
harness before being written here.

- **Scope of the change:** only the report layer. Detection, incidents and diagnosis were not
  touched, and the frozen files still match the §16.1 checksums.
- **Prototype:** `fixproto/make_report_fix.py` builds `fixproto/gscan_report.py` from the frozen copy
  by exact string replacement. Read that script as the patch; a plain `diff` shows the whole file
  changed only because of line endings.
- **Harness:** `fixproto/run_fix.py`.

#### Regression evidence: nothing that worked before broke

| Check | Kits | Result |
|---|---|---|
| Incidents byte-identical to the frozen run (detection untouched) | variant A, s1–s3, blind ×3, clean, day6sim, bench-01, bench-03 | **11 / 11 identical** (bench-02/04 had no frozen copy; covered by the benchmark row) |
| Report valid against `loop-report.schema.json` | all 13 | **0 errors** (was 9 of 10 failing) |
| score.py total **and every section score** equal before vs after | the 7 corpora with ground truth | **55.00 → 55.00**, sections identical on all 7 |
| Independent benchmark (`bench/evaluate_all.py --split all`) | bench-01..04 | **unchanged:** 14/16 exact, 11/16 cause, test 7/8 exact / 4/8 cause, 12/12 planted, 4/4 benign, 0 decoy FA, 0 FP |
| Clean corpus | kit-clean | 0 regressions, schema-valid |
| Judges' checklist "with a human verdict" | variant A, s1–s3, blind ×3 | **0/3**, the truthful value (it was a false 3/3) |

Why no score moved: score.py never reads `approval`, `refused_breakdowns` or an A09 gap. The tool-metric
coverage check passes when *any* claimed value matches, and it now passes on 4/4 tool metrics instead
of 3/3. The A09 fidelity check reads the metric first, which is still `judged`.

#### Fix 1: schema failure on `approval.at`

- **Root cause:** every prescription was emitted with a placeholder
  `approval: {"verdict": "deferred", …, "at": null}`. The schema types `at` as `string`.
- **Fix:** **do not emit `approval` at all.** Only the approval gate on the screen writes it, and when it
  does it writes all four fields:
  ```json
  "approval": {"verdict": "accepted | rejected | deferred", "decided_by": "<name>",
               "reason": "<why, in words>", "at": "2026-09-19T11:20:00Z"}
  ```
- **Write-back rule:** the screen loads `loop-report.json`, sets `prescriptions[i].approval`,
  re-validates against the schema, and only then saves. A rejection with a reason is a valid, fully
  scored answer.
- **Never:** write `at: null`, or emit `deferred` from the pipeline to fill the slot. Either one makes
  the checklist claim a human decision nobody made.

#### Fix 2: silent-tool metric carried the wrong tenant's coverage

- **Root cause:** a single `m_silent_tool` took `min(coverage)` (0.7205, acme-bank) while the silent
  tool fault lives on northwind-retail (true coverage 0.9308).
- **Fix:** emit one metric per tenant discovered in the data, `m_silent_tool_<tenant>`, with that
  tenant's coverage, `excluded: ["agent_kind in (<kinds that emit no steps>)"]`, and the tenant in the
  filter. This is the same pattern as `m_tool_failure_<tenant>`.
- **General rule:** any metric computed from `agent_steps` is per tenant, with that tenant's
  eligible-session share as its coverage. Never blend and never take the min or max.

#### Fix 3: A09 was a stub with no honest calibration

**Research finding: why no judge can be calibrated on this kit.**
- **No labels:** `labels/` holds `outcome_labels.jsonl` (human_resolved, human_handoff_by_design) and
  `rubric_scores.jsonl` (human_quality 1–5). **Neither file has any abandonment-reason label.**
- **No signal in the transcripts:** the last user turn of a session is drawn from the same ~11 filler
  phrases at the same rates whatever the outcome. "still waiting", "no that's not it", "thanks" and
  "ok" are each about 8–9% of resolved, abandoned *and* handed-off sessions (63,745 / 4,653 / 11,854
  sessions profiled on variant A). A frustration judge would therefore return noise.
- **Do not copy the example reports.** Their `calibration {agreement: 0.71, n: 96}` on A09 re-uses the
  *quality-rubric* agreement. That publishes a calibration for a question it never measured, which is
  exactly the dishonesty the Honesty criterion and Rule 1 target.

**Fix, as prototyped:**
1. **Keep `m_abandon_reason` as `fidelity: "judged"`.** The ask's own shape note says calling it
   measured is wrong, and score.py's fidelity trap gives +0.75 for judged and −1.0 otherwise.
2. **Set `calibration: null`, and say why in `plan.filter`:** the measured abandoned count, the judge
   version name, and "no human abandonment-reason labels, so agreement cannot be computed and none is
   claimed".
3. **Add `plan.alternatives_offered`:** `session_end = 'abandoned'` alone is measured, but it answers
   *how many*, not *why*.
4. **Add a gap derived from the catalog, not hand-written per kit.** Every capability whose
   `class` is `requires_new_judge` (the catalog declares `abandonment_reason` that way) produces:
   ```json
   {"ask_id": "A09", "verdict": "REQUIRES_NEW_JUDGE", "why": "<capability.note>",
    "nearest_proxy": "session_end = 'abandoned' (measured)",
    "why_the_proxy_misleads": "it counts everyone who left, including users who got their answer and stopped replying",
    "required_event": {"name": "abandonment_reason_judgment", "grain": "session",
                       "fields": ["session_id", "judge_version", "reason", "confidence"],
                       "owner": "platform team",
                       "calibration_needs": "human abandonment-reason labels on a sample of abandoned sessions, per judge_version"}}
   ```
   The ask → capability link (`A09 → abandonment_reason`) is the same hand-authored planner step as
   the ask → metric mapping.

**If you build the judge anyway (for the demo):**
- **What it reads:** only transcript text (`user_text`), never logged facts. Reading `session_end`
  or handoff flags would break Rule 1.
- **Versioning:** version it (`abandon_reason_v1`) and stamp that version on every output.
- **Unattended runs:** it must finish with no network and no API key. If it is LLM-backed, cache the
  results and fall back to "not judged", never to a crash.
- **Calibration:** publish it only if labels exist, computed like `m_quality`: within one judge version,
  with the tolerance stated, never rounded to ≥ 0.995.
- **Disclosure:** say in the one-page note that on this kit the judge cannot be validated.

#### Fix 4: the C2 refusal was computed but never written

- **Root cause:** the loader already compares each field's distinct count against its
  `cardinality_budget` from the catalog (`C["cardinality"]`, with `refused: true` when over budget), but
  the report never used the result.
- **Fix (generic, nothing named):**
  - Every metric's `plan` gets a `refused_breakdowns` list built from `C["cardinality"]`. The schema
    sets no `additionalProperties: false` on `plan`, so the extra key is valid.
  - `system_notes` ends with the same list.
  - The planner must also **reject** any requested breakdown on a refused field, with the budget cited,
    rather than truncating. The catalog's `cardinality_budgets._rule` says exactly this.
- **Output on variant A:** `session.custom_dims.customer_ref: 80252 distinct values exceeds its
  cardinality budget of 200 - refused, not truncated`.
- **Show it on the screen and in the demo:** it is the second refusal the judges look for.

#### Fix 5: a schema gate so this cannot recur

- `run.py` always writes the report first, then validates it with `jsonschema` against
  `<kit tools>/schema/loop-report.schema.json`.
- It prints every error path and exits non-zero if any exist.
- **Write before validating.** On the sealed run a report with one bad field still scores, while no
  report scores nothing.
- Pin `numpy` and `jsonschema` in `requirements.txt`. Run the same validation in the screen's write-back.

#### What these fixes do not change

- **Diagnosis weaknesses stay in place.** The §9.3 weaknesses on novel fault types remain, and they
  do not affect the three planted fault types (12/12).
- **Tasks 02–04 are still unbuilt.** Loop is already at its capped 8/8 without them, but the judges
  read them (§15).

### 13.3 Definition of done for the 55 machine points (hand this to the coding agent)

Part 1 counts as solved only when **every** line passes on the new code:

| # | Acceptance test | Pass condition |
|---|---|---|
| 1 | `python run.py --kit <dir>` on a kit with **no** `ground_truth*` folder (the Makefile `distribute` layout) | writes `loop-report.json` unattended in < 60 s |
| 2 | Schema validation of the written report | 0 errors |
| 3 | `score.py` on variant A **and** on ≥ 3 fresh `generate.py --sealed "<new phrase>"` corpora (run `verify.py` on each first) | 55.00 on every one: accuracy 20, specificity 15, loop 8, honesty 12 |
| 4 | Clean corpus (`work/kit-clean`) | 0 regression findings; the three dismissal findings are still emitted |
| 5 | Benchmark `bench/evaluate_all.py --split all` | ≥ 14/16 exact, 12/12 planted, 4/4 benign, 0 decoy false alarms, 0 false positives |
| 6 | Prescriptions | no `approval` key until the screen writes one; checklist "with a human verdict" equals the real decisions |
| 7 | Metrics | every metric has `fidelity` and `coverage.value`; tool-derived metrics are per tenant with C1 coverage; `calibration.agreement` never ≥ 0.995; A04 `measured`; A09 `judged` |
| 8 | Gaps | A11 `NOT_MEASURABLE` with the catalog's `required_event` fields, proxy and why it misleads; A09 `REQUIRES_NEW_JUDGE` |
| 9 | Refusals | `plan.refused_breakdowns` and `system_notes` list every over-budget field |
| 10 | Generality | no tenant, intent, agent, tool name or fault day appears in detection, incident or diagnosis code |
| 11 | Regressions on the real faults | exactly one regression finding per fault cohort and window, with `window.from_day` = detected onset − 2 |

---

## 14. Build spec, parameters, and what not to hardcode

### 14.1 Modules

```
nexus/
  loader.py      §6   counters + per-session arrays + discovered versions, coverage, calibration
  detect.py      §7   uniform test; frozen baseline; day support; scales 3 and 7
  incidents.py   §8   breadth -> global events -> composition -> explanation forest -> non-regressions
  diagnose.py    §9   layer -> cause; attribution (fix the §9.3 weaknesses here)
  report.py      §10  impact blocks, honesty fields, gaps, prescriptions -> loop-report.json
                      (apply §13.2 fixes 1-4; start from fixproto/gscan_report.py, not frozen_v1/)
  validate.py    §13.2 fix 5: jsonschema gate after writing; also used by the screen's write-back
  standard.py         NOT BUILT
  replay.py           NOT BUILT
run.py                one command: python run.py --kit <dir>
screen/               NOT BUILT
```

### 14.2 Parameters

All of these were set on variant A, the dev split and the generator corpora, **not** on the test split.

| Parameter | Value | Meaning |
|---|---|---|
| `Z` | 4.0 | bad-direction statistic after φ (and τ²) |
| `MATERIAL_REL` / `MATERIAL_ABS` | 0.10 / 0.01 | relative effect; absolute effect for rates |
| scales | 3 and 7 days | current window lengths |
| `BASE` | 15 days | self-baseline length (minimum 3 days, 60 units) |
| `MIN_N_CUR` | 30 | units in the current window |
| `DAY_MIN_N` | 5 | units for a day to count as support |
| `MIN_RUN` | 3 | firing windows and supporting days (7 supporting days at scale 7) |
| `SUPPORT_FRAC` | 0.5 | a supporting day carries ≥ half the strongest change |
| `NEWBORN_DAY` | 2 | a cohort first seen on/after this day uses peer baselines |
| global breadth | 0.6 | share of sibling cohorts with comparable effect, min over dimensions |
| equivalence | 0.8 | metric-unit overlap that makes two cohorts the same |
| window tolerance | 3 days | overlap tolerance for grouping and explain-away |
| volume spike | > median + 6·MAD and > 1.5× median | tenant daily volume |
| share shift | ≥ 5 pts, ≥ 50% of typical, z ≥ 4 | traffic-mix event |
| newborn share guard | 1% | current-window share of newborn strata |

### 14.3 What not to hardcode

v1 said the three cohort keys (`premium_card_info`, `order_status`/`get_order_status`,
`acme_main_v3`), the cause classes and the coverage values were "safe to hardcode" because they never
changed across generated corpora. That was true of the generator and **false as a technique**.

Hardcoding them would score on day 6 and find nothing else. The generic scanner scores the same 55.00
without them.

What remains legitimate to take from the environment:

| Item | Why it is legitimate |
|---|---|
| Schema vocabularies (cause classes, change types, gap verdicts) | they are the output contract |
| The exact dismissal strings `traffic_mix` / `load` / `judge_change` | output contract |
| Catalog semantics: capabilities, `requires`, budgets, agent-kind semantics | the catalog is the declared rulebook |
| Start every regression window 2 days before detection | the scorer's lag rule makes early starts free |

---

## 15. The 45 human points

Unchanged from v1 and still the largest remaining opportunity. From the PDF: a Level 1 system with an
excellent screen and decision layer scores about **70**; a Level 3 system with neither scores about **58**.

| Area | Points | What earns them |
|---|---|---|
| **Decision quality** | 18 | impact blocks with the baseline named and justified; audience; a plain-language "if nothing changes". The scanner already emits these. |
| **Screen** | 15 | one page: finding → evidence (every number with definition, fidelity, coverage) → proposed fix → **APPROVE / REJECT written back into `loop-report.json`**; dismissed and refused items listed |
| **Framing** | 12 | open on the operator's problem; show the lookalike you ignored; **script the refusal** of A11; state coverage aloud; bring the one-page note |

Also in the product half:
- **Standard (Task 02):** top decile of resolved, milestone-complete sessions per cohort within one
  judge version. This frames the prompt regression as a deviation from the deployment's own best work.
- **Replay (Task 03):** the prompt-regression cohort key must be `agent_id` (an intent key silently
  returns `no_effect`). Identical requests return identical results. 40 runs per team string.
- **Self-assessment (Task 04):** predicted vs actual delta per change type. With one cycle, report it and
  decline to act on it.

---

## 16. Appendix

### 16.1 Frozen code (SHA-256)

```
31a283bd91f6c75cba5f3222b98a8212949f9c824c17be1c9eba3c37a520c0f5  gscan_detect.py
47c1bc0ce3e51999f2ba9ecf9486ca0898050dab74567b622616b361ff3461dc  gscan_incidents.py
80c797dc9703668edd2fd3e3e42ee818bdddd47d2ac2b7c168660c7a961f6da5  gscan_load.py
9a6358be6325fc80a1e0422a0674716b4312acb4a50ee79b0bdbab21303d898c  gscan_multiscale.py
6cae491bc6f937f20e517ee18961b5cb13935238810da8aa0abedf58cc5a5c55  gscan_report.py
8893171e2763cb20e3a8b6fd06e04a2131b5ccdd6d602c4d90bf016725838cb4  gscan_run2.py
```

These are research instrumentation in the session scratchpad (`frozen_v1/`), not production code.

Report-layer fixes (§13.2), built from the frozen copy; the detection files above are unchanged:

```
13d5fb4858519d74a16703b11feab133fc2359886a0ba2522c5625bab9639850  fixproto/gscan_report.py      (patched report module)
5583d90d35e2653e94db707ac3d6f65a7b61d6e81fc9e6609cdbe97f03f7e564  fixproto/make_report_fix.py   (the patch, as exact replacements)
fa530bef466e708b9e02b0a1ce6fc64b227e03e9ffe8d41412fa77350b0214a5  fixproto/run_fix.py           (regression harness)
```

### 16.2 Reproduce

```bash
python gscan_run2.py <kit> [<kit> ...]      # incidents + report, scored when ground truth exists
python gscan_run2.py --null <kit>           # episode null and full-pipeline permutation null
python bench/evaluate_all.py --incidents-dir gout --split dev|test|all
python generate.py --sealed "any phrase" --out <dir>   # make your own unseen corpus
```

### 16.3 Scratchpad inventory

| File | What it is |
|---|---|
| `gscan_load.py`, `gscan_detect.py`, `gscan_multiscale.py`, `gscan_incidents.py`, `gscan_report.py`, `gscan_run2.py` | the generic scanner (§5–§10) |
| `bench/` | independent benchmark: 4 corpora, answer keys, evaluator (self-tested) |
| `work/kit-clean/` | variant A with planted fault cohort-windows and load days removed (the clean null) |
| `work/kit-s1..s3`, `work/blind-*` | generator corpora used for official scoring |
| `build_report.py`, `gen_harness.py`, `d1_guard.py`, `old_method_bench.py` | the v1 technique and its benchmark run (0/16) |
| `gscan_trace.py`, `dbg_*.py` | decision tracing used to diagnose §11 |

### 16.4 Replay contract (verified in v1)

```
POST /replay  {"team","tenant","change":{"type","target","description"},
               "cohort":{"<key>":"<value>","from_day":N,"to_day":M},"golden_set":[...]}
```

- A wrong fix class returns `no_effect`, indistinguishable from "nothing wrong here".
- The second accepted fix class gives a partial lift.
- Blunt changes aimed at a healthy cohort break the golden set.
