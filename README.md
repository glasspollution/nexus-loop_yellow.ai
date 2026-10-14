# Nexus Loop

**An autonomous improvement loop for AI agent deployments**, built for Yellow.ai's TechQuest problem statement
series (Product Development & Agentic AI track), September 2026.

Point it at eight weeks of logs from an AI chat agent it has never seen. With no human in the loop until the very
last step, it works out:
- what broke, in which slice of traffic, and why;
- which config change caused it, and what it is costing;
- which scary-looking movements are *not* problems;
- which questions cannot be answered from the data at all.

It then proposes a fix for each problem, tests the fix on a replay simulator, and puts it in front of a person to
approve or reject.

**Results:**
- **55 / 55** on the machine-scored half, on the practice data and on every unseen corpus tested.
- **14 / 16** novel fault types found on an independent benchmark.
- **0** false alarms throughout.

---

## The problem statement

Companies run AI agents in production, for example a bank's support agent on WhatsApp. Every model call, tool
call, knowledge-base lookup and handoff is logged. Yet when something breaks, a human usually finds out from a
customer complaint, reads transcripts by hand, edits a prompt and hopes. In the organisers' words, the deployment
*records almost everything it does and learns nothing from it*, because the improvement loop is closed by a person
moving between six tools.

**The challenge was to build that loop.** It has four tasks:

| Task | What it asks |
|---|---|
| 01 Detection & diagnosis | Find the real problems: the affected slice, their impact, their cause, and the config change behind them. Dismiss the lookalikes in writing. Name what cannot be measured |
| 02 Standard & fix | Mine what "good" looks like from the deployment's own best conversations, and propose a fix with its risk |
| 03 Verification | Test the fix on the organisers' replay service, with 40 runs per team. A wrong fix returning "no effect" is a valid result |
| 04 Decision & self-assessment | Record a human approve/reject on every fix, and keep a record of the system's own hit rate |

**The deliverables:**
- **`loop-report.json`**, a schema-valid report produced by the system without edits. It is scored by a script,
  worth 55 points.
- **A screen** an operator who was not on the team can read and act from. It is judged by people, worth
  45 points.

**The data** is a synthetic kit with two tenants (a bank and a retailer) over 56 days:
- 80k conversations;
- 884k agent steps;
- 365k transcript turns;
- a config timeline;
- sparse CSAT ratings and human labels;
- a catalog describing every field.

**What the data hides:**

- **3 real problems, each built to beat a lazy approach:**
  - A product launches with nothing about it in the knowledge base. The slice is "born broken", so it has no
    *before* period to compare against.
  - An API starts returning empty payloads while reporting success. The error rate stays flat.
  - A prompt change doubles conversation length without changing the resolution rate. No outcome alert ever
    fires.
- **3 lookalikes**, where flagging one costs more than missing a real problem:
  - A traffic-mix shift.
  - A 4× load spike.
  - A change of judge version that drops "quality" on both tenants on the same day.
- **Honesty traps:**
  - A question with no answer, "what is our failover rate?", when no failover mechanism exists.
  - Legacy traffic that logs no tool calls, so naive denominators are wrong.
  - A near-unique field that must be refused as a breakdown key.

**The rules:**
1. Never ask a language model something the logs already record.
2. Change the agent, never the yardstick.

Every number must carry its *fidelity* (measured, judged or derived), its *coverage*, and, for judged numbers,
its *calibration* against human labels. A calibration of 1.00 counts as a bug.

**Day 6 is a sealed run.** The system runs untouched on a new dataset with the problems moved to different
days, tenants and slices. *"A system that needs hand-holding to run scores as if it failed."*

---

## What we built

One command runs the full loop unattended in about 20–30 seconds:

```
kit → load → detect → incidents → diagnose → impact → standard → prescribe → replay → human gate → self-assess
```

| Stage | What it does |
|---|---|
| **Load** | Derives metrics and slices from the kit's own catalog rather than from hand-written lists. That is about 1,400 metric × slice time series per kit. Version fields (model, prompt, KB, judge) are discovered and kept as evidence, never as slice keys, because splitting on a version field makes a regression vanish |
| **Detect** | **One uniform changepoint test over every series, with no detector per known fault.** It is a z-test or t-test with variance inflated by each series' measured overdispersion, and gates for significance, materiality and persistence. It runs on 3-day and 7-day windows, against a baseline frozen at first firing. A slice born mid-corpus is compared with its siblings on the same days |
| **Incidents** | Asks the questions an analyst would ask of any anomaly: does it have a locus, or did everything move? Is it load, a traffic-mix shift (re-weighted to the old mix), or an instrument change? Does another anomaly explain it away? Benign movement is emitted as a dismissed lookalike, never silently dropped |
| **Diagnose** | Names the runtime layer that moved (tool, KB, LLM, guardrail, handoff) as the cause class, then attributes the config change or version flip that lines up with it |
| **Impact** | Turns each finding into a decision packet: conversations exposed, resolutions lost (with a 95% range), excess handoffs, time and spend, a named baseline and why it was chosen, the owner, severity, and what happens if nothing changes |
| **Standard** | Mines exemplar conversations from the deployment's own best work and freezes a golden set that every fix must not break |
| **Prescribe** | Frames each fix as a decision: what is being approved, its risk if the diagnosis is wrong, when *not* to ship, alternatives, and a predicted effect |
| **Replay** | Verifies each fix on the organisers' simulator, with a cache and ledger so a re-run never spends budget twice |
| **Human gate** | Approve, reject or defer on the screen or from the CLI. Decisions are bound to the content of the fix and written back into the report; the generated report itself is never edited |
| **Self-assess** | Tracks the system's guard-qualified hit rate, and says plainly that one example per fix type is too small to claim anything |

**No LLM is called anywhere.** Every number is arithmetic over logged fields, which is how the system complies with
rule 1.

**The screen** is a React + TypeScript app backed by `screen.json`. The browser does no arithmetic, so every figure
is exactly what the engine computed, and every number carries its definition, fidelity and coverage on hover. It
shows each issue's cost, evidence, diagnosis and proposed fix, plus the replay proof and an approve/reject form. A
"lookalikes ruled out" panel and an "about this analysis" panel cover refusals, coverage and what is real versus
simulated.

**Stack:** Python 3 + NumPy and `jsonschema` for the engine; React 19, TypeScript, Vite and Tailwind for the screen;
and a standard-library Python HTTP server for the backend.

---

## Results

### On the practice data

**Real problems found: 3 of 3, at 0 days' lag**

| Problem | What the system found |
|---|---|
| Knowledge gap | The KB miss rate went to 100% on a newly launched intent. Resolution fell to 30.9% against 75.8% for peer intents, about 103 resolutions lost. Attributed to the KB release on day 34 |
| Silent tool failure | 13.75% of "successful" order-status calls returned empty payloads, against 0.00% before, while the declared error rate stayed at 1.6%. About 217 resolutions lost. Attributed to the tool upgrade from 3.2.0 to 3.3.0 |
| Prompt regression | Mean turns rose from 4.5 to 7.0 and cost per conversation rose 84%, with resolution flat. Attributed to prompt p_v4 |

**Lookalikes dismissed: 3 of 3, with reasons**

| Lookalike | Why it was dismissed |
|---|---|
| Load spike | Traffic was 3.8× its usual volume. Latency rose, but nothing outlived the surge |
| Traffic-mix shift | Raw resolution rose 2.3 points, but fell 2.0 points once re-weighted to the old mix |
| Judge-version change | The ruler changed, not the agent, so judged scores are only compared within one version |

**Refusals**
- *"What is our failover rate?"* is refused as not measurable. The report specifies the `failover` event that would
  need to exist, and explains why the nearest proxy would give a false good-news number.
- *"Break it down by customer_ref"* is refused because 80,252 distinct values exceed the cardinality budget of 200.

**Fixes on replay:** all three proposed fixes improved their target metric on the simulator, and the 25-conversation
golden set held. That used 3 of the 40 allowed runs.

### Generalisation

| Test | Result |
|---|---|
| Official `score.py` on practice and 6 fresh corpora (faults on new days) | **55.00 / 55** on every one |
| Day-6 stress test: 4 corpora with problems moved to new tenants and slices, one fully renamed | **55.00 / 55** on all 4 |
| Independent benchmark: 16 faults of 12 kinds the generator never plants, built by a separate agent without access to our code | **14 / 16** at the exact slice, 0 false positives |
| Held-out half of that benchmark, run once on frozen code | 7 / 8, 0 false positives |
| Clean corpus with every fault removed | 0 regressions flagged |

**The lesson that shaped the design:** the first version had one hand-written detector per known fault type. It
scored 55/55 on seven corpora and found **0 of 16** novel faults. All seven corpora came from the same generator, so
a perfect score had only shown that faults could move days, not that new kinds could be found. Replacing it with a
single generic scanner kept 55/55 and raised novel-fault recall to 14/16. Along the way, every absolute threshold we
wrote eventually broke, and every scale-free statistical one survived.

### Known limits

These are stated openly:
- The 2 missed novel faults are subtle, gradual ramps.
- Diagnosis is rule-based, and misclassifies 5 of 16 novel causes.
- Replay numbers are simulator outputs.
- Patch generation, deployment and authentication are not built.
- Everything was tested on synthetic data from one generator family.

---

## Run it

```bash
cd nexus-loop
pip install -r requirements.txt

# the loop, unattended (add --replay-url to verify fixes on a replay service)
python run.py --kit ../kit --out out/practice

# local replay service for practice (the organisers' script)
python ../tools/nexus-loop-kit/replay/serve.py --kit ../kit --port 8719
python run.py --kit ../kit --out out/practice --replay-url http://localhost:8719

# the approval gate: the screen's backend, or the command line
python server.py --out out/practice --port 8765
python decide.py --out out/practice --list
python decide.py --out out/practice --prescription p3 --verdict rejected --by "Ops lead" --reason "..."
```

`run.py` writes these into `--out`:

| File | What it is |
|---|---|
| `loop-report.generated.json` | The system's output, never modified afterwards |
| `loop-report.json` | The deliverable: the generated report plus recorded human decisions, schema-valid |
| `screen.json` | Everything the screen shows, with every number's definition resolved |
| `decisions.jsonl` | Append-only human decisions |

It exits with one of these codes:
- **0:** the reports are written and valid.
- **1:** the reports are written, but a check failed, and the failure is printed.
- **2:** the kit could not be read.

The pipeline never reads ground truth.

### Verify it

```bash
cd nexus-loop
python -m pytest -q tests                 # about 30 s; includes a live replay server and the decision API
python validation/make_corpora.py         # once: builds validation/data/
python validation/run_all.py              # end-to-end checks through the real CLI
python validation/equivalence.py          # detection still equals the frozen research outputs
```

---

## Layout

```
kit/                     practice kit provided by the organisers (synthetic data, catalog, asks)
tools/nexus-loop-kit/    organisers' scorer, replay service, schema and starter
nexus-loop/
├── run.py               CLI: the whole loop, unattended
├── server.py            screen backend: /api/screen, /api/report, POST /api/decisions
├── decide.py            the approval gate from the command line
├── nexus/
│   ├── loader.py        catalog-derived metrics, slices, version fields, coverage
│   ├── detect.py        one changepoint test over every metric × slice
│   ├── multiscale.py    3- and 7-day windows
│   ├── cohorts.py       cohort masks, daily series, counterfactual window test
│   ├── incidents.py     breadth → global drivers → composition → explanation forest → dismissals
│   ├── diagnose.py      runtime layer → cause class; config / version-flip attribution
│   ├── measure.py       one-window arithmetic for every displayed number
│   ├── impact.py        decision packets
│   ├── definitions.py   definitions registry; catalog-vs-data contradictions
│   ├── standard.py      exemplars and the frozen golden set
│   ├── prescribe.py     fixes framed as decisions
│   ├── replay.py        replay client with cache, ledger and budget stops
│   ├── decisions.py     approval write-back bound to fix content
│   ├── selfassess.py    hit-rate ledger
│   ├── screen.py        screen.json
│   ├── report.py        assembles loop-report.json
│   ├── pipeline.py      kit → outputs
│   └── validate.py      schema gate + report contract
├── screen/              React app (screen/dist/ is prebuilt)
├── tests/               pytest: units, practice report, generality, product half
└── validation/          end-to-end proof through the real CLI, plus the novel-fault benchmark
```

---

## Team

Built for the Yellow.ai TechQuest by Shekhar Suman (IIT Patna), Romir and Anvitha.
