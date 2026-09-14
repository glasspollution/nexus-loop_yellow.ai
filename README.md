# Nexus Loop — Yellow.ai TechQuest

An autonomous improvement loop for AI agent deployments. It reads eight weeks of an agent's logs and writes
`loop-report.json`: what broke, in which slice of traffic, why, which config change is behind it, what it cost,
which lookalikes are not problems, and which questions cannot be measured.

| Path | What it is |
|---|---|
| [`nexus-loop/`](nexus-loop/README.md) | the system (engineering half, 55 machine points): code, tests, validation |
| [`screen/`](screen/) | Loop Desk — the one screen, and the approve/reject write-back (15 points) |
| [`docs/`](docs/) | the one-page note, the demo script, the run-book and the checks (Framing, 12 points) |
| [`NEXUS_LOOP_HANDOFF.md`](NEXUS_LOOP_HANDOFF.md) | the research: technique, failure log, conformance audit, definition of done |

## Setup

Everything needed to run is in this repository, including the organisers' TechQuest day-1 kit:

```
<this repo>/
├── kit/                   the practice kit: catalog.json, corpus/, corpus_sample/, labels/, asks.md, ground_truth/
├── tools/nexus-loop-kit/  the organisers' tools: generate.py, score.py, verify.py, schema/, replay/, examples/
├── nexus-loop/            the solution
└── NEXUS_LOOP_HANDOFF.md
```

```bash
pip install -r nexus-loop/requirements.txt

# produce the report on the practice kit
python nexus-loop/run.py --kit kit

# score it with the organisers' script
cd tools/nexus-loop-kit
python score.py --report ../../nexus-loop/out/loop-report.json --ground-truth ../../kit/ground_truth/ground_truth.json
cd ../..

# verify everything (fast tests, then the full definition of done)
python -m pytest -q nexus-loop/tests
python nexus-loop/validation/make_corpora.py
python nexus-loop/validation/run_all.py
```

On day 6, point `--kit` at the sealed kit: `python nexus-loop/run.py --kit <day6-kit> --out out/day6 --team "<team>"`.

## The screen

One self-contained HTML page and a stdlib server. No libraries, no CDN, no build step.

```bash
python screen/serve.py --report nexus-loop/out/loop-report.json     # http://127.0.0.1:8080
```

It renders whatever the report says — no day, tenant, cohort, metric name or count is written into
the page — and ACCEPT / REJECT / DEFER writes `prescriptions[i].approval` back into the report,
re-validating against the schema before it saves. Verified against reports with 0, 3, 7 and 9
findings, and against two that predate the prose layer.

Optional: verify the proposed fixes against the organisers' replay service. This spends from a
budget of 40 attempts shared by the whole team, so it is off by default and the unattended run
never depends on a service being reachable.

```bash
python tools/nexus-loop-kit/replay/serve.py --kit kit --port 8719 &
python nexus-loop/run.py --kit kit --replay http://127.0.0.1:8719
```

## Before the demo

```bash
python docs/judge_check.py        # 63 mechanical rubric checks
python docs/demo_numbers.py       # the numbers to read out, from the report that will be on screen
python docs/reset_decisions.py    # clear rehearsal decisions so the buttons show
```

[`docs/RUNBOOK.md`](docs/RUNBOOK.md) has the exact demo-day sequence and what to do when something
breaks. [`docs/SCORING_SAFETY.md`](docs/SCORING_SAFETY.md) is the contract the product layer works
under — what may be touched and what may never be, because no product change can raise the machine
score and several could lower it.

## Status

- Scores **55.00 / 55** on the practice kit and on 3 fresh sealed corpora.
- Passes all 53 checks in the definition of done; see [`nexus-loop/README.md`](nexus-loop/README.md).
- The screen is built, and the approve/reject decision is written back into the report: the
  scorer's checklist moves from `with a human verdict 0/3` to `1/3` once a decision is recorded.
- Replay verification runs against the organisers' service, including one deliberately blunt fix
  reported honestly as `no_effect`.
- 63 of 63 mechanical rubric checks pass, on the practice corpus and on fresh sealed ones.
- **Still not built:** standard mining (`standard[]` is empty) and the A09 abandonment-reason
  judge, which is refused rather than guessed. Both are stated in
  [`docs/ONE_PAGE_NOTE.md`](docs/ONE_PAGE_NOTE.md) alongside what is stubbed and what breaks at
  100×.
