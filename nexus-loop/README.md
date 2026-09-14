# Nexus Loop — engineering half (the 55 machine points)

Reads eight weeks of an AI agent deployment's logs and writes **`loop-report.json`**, the report the
TechQuest problem statement asks for. It says what broke, in which slice of traffic, why, which config
change is behind it, what it cost, who must act, which lookalikes are *not* problems, and which questions
cannot be measured at all. It runs **unattended on a kit it has never seen**, which is how day 6 is scored.

The technique, the research behind it and every design decision are in
[`../NEXUS_LOOP_HANDOFF.md`](../NEXUS_LOOP_HANDOFF.md). This folder is that handoff implemented.

---

## Run it

```bash
pip install -r requirements.txt
python run.py --kit ../kit                                   # practice kit
python run.py --kit /path/to/day6-kit --out out/day6 --team "<team name>"
```

| Output | What it is |
|---|---|
| `out/loop-report.json` | **the deliverable**, valid against `tools/nexus-loop-kit/schema/loop-report.schema.json` |
| `out/incidents.json` | flat list of incidents (used by the benchmark evaluator) |

| Exit code | Meaning |
|---|---|
| 0 | report written, schema valid, report contract satisfied |
| 1 | report **still written**, but it failed the schema or contract checks (printed) |
| 2 | the kit could not be read |

Score it with the organisers' unchanged script:

```bash
cd ../tools/nexus-loop-kit
python score.py --report ../../nexus-loop/out/loop-report.json --ground-truth ../../kit/ground_truth/ground_truth.json
```

The pipeline never reads ground truth. A day-6 kit (no `ground_truth*` folder) runs cold in about 25 seconds.

---

## Layout

```
nexus-loop/
├── run.py                    CLI: kit -> loop-report.json, validated
├── requirements.txt          numpy, jsonschema (runtime); pytest (tests)
├── nexus/                    the system
│   ├── config.py             every detection parameter (handoff 14.2)
│   ├── loader.py      stage 1  catalog-derived metrics, discovered dimensions + version fields, per-session arrays,
│   │                           coverage, calibration, cardinality budgets; content-keyed cache
│   ├── detect.py      stage 2  one changepoint test over every metric x cohort (overdispersion, frozen baseline,
│   │                           day-level support, peer baselines for newborn cohorts)
│   ├── multiscale.py  stage 2  3- and 7-day windows, scale-consistent persistence
│   ├── cohorts.py              cohort masks, daily series, counterfactual window test
│   ├── incidents.py   stage 3  breadth -> global drivers -> composition -> explanation forest -> examined non-regressions
│   ├── diagnose.py    stage 4  runtime layer -> cause class; config-row / version-flip attribution
│   ├── report.py               impact blocks, honesty fields, gaps, refusals, prescriptions -> report
│   ├── validate.py             schema gate + report-contract checks
│   ├── pipeline.py             analyse(kit) and output writing
│   └── schema/               vendored copy of the kit's loop-report.schema.json
├── tests/                    pytest: fast unit + practice-kit contract + generality (about 20 s)
└── validation/               end-to-end proof, run through the real CLI
    ├── make_corpora.py       fresh sealed corpora (organisers' generator + verify.py), clean corpus, day-6 layout
    ├── run_all.py            the definition of done (handoff 13.3) -> results/summary.md
    ├── equivalence.py        packaged code == researched code (same incidents, same report)
    ├── benchmark/            independent fault-injection benchmark: 4 corpora, 16 novel faults, evaluator
    ├── baselines/research/   outputs of the frozen research code, for equivalence
    ├── data/                 generated corpora (git-ignored)
    └── results/              run outputs + summary (git-ignored)
```

---

## Verify it

```bash
python -m pytest -q tests                 # fast
python validation/make_corpora.py         # once: builds validation/data/
python validation/run_all.py              # the definition of done, end to end
python validation/equivalence.py          # packaged code reproduces the research outputs exactly
```

---

## How it maps to what is scored

| score.py criterion | Points | Where it comes from |
|---|---|---|
| Diagnostic accuracy: right problem, slice, cause, change, lag | 20 | `detect` + `incidents` + `diagnose`; regression windows start 2 days before detected onset |
| Specificity: no false alarms on lookalikes, dismissed explicitly | 15 | `incidents`: load, traffic-mix and judge-version events emitted as non-regressions with cause `load` / `traffic_mix` / `judge_change` |
| Loop completeness | 8 | metrics + linked diagnoses + linked prescriptions with `predicted_delta` (capped at 8) |
| Honesty: fidelity and coverage everywhere, calibration < 1.00, the refusal | 12 | `report`: per-tenant tool coverage (legacy flow emits no steps), calibration within one judge version, A11 gap spec from the catalog, A04 measured / A09 judged |

What the problem statement also asks for in this half, beyond score.py:

- **Schema-valid report.** Gated in `validate.py`.
- **Every regression carries an impact block.** Each block has a checkable derivation that names its baseline (peer traffic for a cohort with no before-period, the cohort's own past otherwise), an audience, and one plain sentence on what happens if nobody acts.
- **Over-budget breakdowns refused, with the budget cited.** Recorded in every metric's `plan.refused_breakdowns` and in `system_notes`.
- **A09 judged, with no borrowed calibration.** The kit has no abandonment-reason labels, so no calibration is claimed. A `REQUIRES_NEW_JUDGE` gap names the judgment event and the labels that would be needed.

---

## What is real, what is stubbed

| | Status |
|---|---|
| Detection, localisation, diagnosis, attribution, lookalike dismissal | real, computed from the logs |
| Impact, coverage, calibration, refusals, gap specs | real, computed from the logs and the catalog |
| Ask -> metric mapping (A01, A04, A06, A09) and A09 -> capability | hand-authored planner step |
| A09 abandonment-reason judge | **not built**: no labels exist to calibrate it (declared in the report) |
| Standard mining, replay verification, self-assessment (Tasks 02-04) | **not built**; loop score is already at its cap without them |
| Screen with APPROVE / REJECT write-back | **not built**; the pipeline never writes `approval`, only the screen may |

Known limits (handoff 12 and 9.3):
- **Subtle gradual ramps can be missed.**
- **Diagnosis is weaker than detection on fault types never seen** (test split 4/8 cause).
- **Tested on synthetic data only**, from one generator family.

---

## Validation results

Last full run: `validation/run_all.py` **53 checks, 0 failed**; `validation/equivalence.py` **PASS**; `pytest` **16 passed**.

| Check (handoff 13.3) | Result |
|---|---|
| Day-6 layout (no ground truth, cold cache) through `run.py` | exit 0 in 30 s |
| score.py on practice + 3 fresh sealed corpora (`delta-fresh-one`, `echo-fresh-two`, `foxtrot-fresh-three`, each passing `verify.py`) | **55.00 / 55** on all four: accuracy 20, specificity 15, loop 8, honesty 12 |
| Schema + report contract | valid on every kit (practice, sealed ×3, day-6 layout, clean, benchmark ×4) |
| Exactly one regression per planted fault | 3/3 on every scored corpus |
| Clean corpus (planted faults and load days removed) | 0 regressions, 5 dismissals |
| Independent benchmark (16 novel fault types never planted by the generator) | 14/16 exact cohort, 11/16 correct cause, 12/12 planted, 4/4 benign, 0 decoy false alarms, 0 false positives |
| No planted cohort literal in detection code | 27 literals searched, none found |
| Packaged code vs research outputs (13 corpora) | incidents and reports identical |

Note: the loader caches about 70 MB per kit in `.cache/` (safe to delete; keyed on the kit's path and file stats).
