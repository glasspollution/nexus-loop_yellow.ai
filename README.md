# Nexus Loop — Yellow.ai TechQuest

An autonomous improvement loop for AI agent deployments. It reads eight weeks of an agent's logs and writes
`loop-report.json`: what broke, in which slice of traffic, why, which config change is behind it, what it cost,
which lookalikes are not problems, and which questions cannot be measured.

| Path | What it is |
|---|---|
| [`nexus-loop/`](nexus-loop/README.md) | the system (engineering half, 55 machine points): code, tests, validation |
| [`NEXUS_LOOP_HANDOFF.md`](NEXUS_LOOP_HANDOFF.md) | the research: technique, failure log, conformance audit, definition of done |

## Setup

The organisers' kit is not included in this repository. Place it next to `nexus-loop/`:

```
<this repo>/
├── kit/                   the practice kit (catalog.json, corpus/, labels/, asks.md, ground_truth/)
├── tools/nexus-loop-kit/  generate.py, score.py, verify.py, schema/, replay/
├── nexus-loop/
└── NEXUS_LOOP_HANDOFF.md
```

```bash
pip install -r nexus-loop/requirements.txt
python nexus-loop/run.py --kit kit
```

## Status

- Scores **55.00 / 55** on the practice kit and on 3 fresh sealed corpora.
- Passes all 53 checks in the definition of done; see [`nexus-loop/README.md`](nexus-loop/README.md).
- **Not built:** the approve/reject screen, standard mining, replay verification and the A09 judge.
