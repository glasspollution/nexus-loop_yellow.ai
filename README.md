# Nexus Loop — Yellow.ai TechQuest

An autonomous improvement loop for AI agent deployments. It reads eight weeks of an agent's logs and writes
`loop-report.json`: what broke, in which slice of traffic, why, which config change is behind it, what it cost,
which lookalikes are not problems, and which questions cannot be measured.

| Path | What it is |
|---|---|
| [`nexus-loop/`](nexus-loop/README.md) | the system (engineering half, 55 machine points): code, tests, validation |
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

## Status

- Scores **55.00 / 55** on the practice kit and on 3 fresh sealed corpora.
- Passes all 53 checks in the definition of done; see [`nexus-loop/README.md`](nexus-loop/README.md).
- **Not built:** the approve/reject screen, standard mining, replay verification and the A09 judge.
