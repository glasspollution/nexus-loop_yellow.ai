# Demo-day runbook

Exact commands, in order. Everything is local — no network, no accounts, no external service.
A system that needs hand-holding to run scores as if it failed, so this is written to be followed
by whoever is holding the laptop, not by whoever wrote it.

---

## T-60 min — the sealed run

```bash
cd <repo>
pip install -r nexus-loop/requirements.txt          # numpy, jsonschema, pytest

# THE deliverable. One command, unattended, ~30s cold.
python nexus-loop/run.py --kit <SEALED-KIT> --out out/day6 --team "<TEAM NAME>"
```

Exit code **0** means written, schema-valid and contract-clean. **1** means it was written but
failed a check — the problems are printed, read them. **2** means the kit could not be read: check
the path points at the folder containing `catalog.json` and `corpus/`, not at `corpus/` itself.

**Do not edit the output by hand. Not once, not for a typo.** It must be the system's own output.

Score it:

```bash
cd tools/nexus-loop-kit
python score.py --report ../../out/day6/loop-report.json \
                --ground-truth <SEALED-GROUND-TRUTH>       # organisers provide, if at all
```

## T-40 min — verification (optional, and it spends shared budget)

Only if the organisers' replay endpoint is up. **40 attempts for the whole team, and this uses one
per prescription plus one for the deliberate blunt probe.** Agree with the team before running it.

```bash
# if the organisers run it, point at theirs; otherwise locally:
python tools/nexus-loop-kit/replay/serve.py --kit <SEALED-KIT> --port 8719 &

python nexus-loop/run.py --kit <SEALED-KIT> --out out/day6 --team "<TEAM NAME>" \
       --replay http://127.0.0.1:8719
```

Add `--no-blunt-probe` to save one attempt. You lose the "fix that did not work" beat if you do.

If the endpoint is down or the budget is spent, **do nothing**: the report keeps
`verifications: []` and the screen says "Not verified" in plain words. That is an honest state and
the demo still works — Beat 6 becomes thirty seconds about why a fix with no evidence is a hope.

## T-20 min — the screen

```bash
python docs/reset_decisions.py --report out/day6/loop-report.json   # clear rehearsal decisions
python screen/serve.py --report out/day6/loop-report.json --port 8080
```

Open `http://127.0.0.1:8080`. Check, in this order:

1. The system bar reads **`0 signed off`**. If it does not, `reset_decisions.py` did not run.
2. The hero numbers are populated, not `--`.
3. `WHAT WE THREW AWAY` lists the dismissals.
4. `WHAT WE CANNOT SEE` lists the refusals **and** the cardinality refusal at the bottom.
5. Click one numeral. A popover opens with a definition and a coverage figure.
6. Full-screen the browser. Zoom to **100%** — not 90, not 110.

## T-10 min — read the numbers you are about to say

```bash
python docs/demo_numbers.py --report out/day6/loop-report.json
```

Fill every `[BRACKET]` in `DEMO_SCRIPT.md` from this output. **Do not say a number from memory.**
Days, tenants, cohorts, counts and the headline metric all move on the sealed corpus.

---

## During the demo

- Browser full screen, one tab. Close everything else. Notifications off.
- The terminal is needed only if someone asks to see the file; have it open on a second desktop
  showing the repo root.
- **Do not re-run the pipeline during the demo.** The screen reads a file; the file is already there.
- **Do not press the replay button.** There isn't one, and that is deliberate — repeat probes
  return identical seeded numbers and every call is logged to the organisers.

---

## If something goes wrong

| Symptom | Do this |
|---|---|
| Screen shows "No report to read." | The `--report` path is wrong. `python screen/serve.py --report out/day6/loop-report.json`. Check the file exists first with `ls`. |
| Port 8080 already in use | `python screen/serve.py --port 8081 ...` and open the new port. |
| Buttons missing, receipt showing | A rehearsal decision is still in the file. `python docs/reset_decisions.py` and reload. |
| Approve/reject returns an error | Read it — it is telling the truth. "report_has_changed" means the pipeline was re-run after the page loaded: **reload the page** and decide again. |
| Hero numbers show `--` | That finding has no impact block. Use `‹ prev / next ›` to move to one that does; not every finding carries one. |
| `Did it work` says "Not verified" | Expected when replay was not run. Say so out loud — it is an honest state, not a bug. Do not start the replay mid-demo. |
| The page looks unstyled | The HTML did not load fully. Hard reload (Ctrl/Cmd-Shift-R). It is one self-contained file, so there is nothing else to fail. |
| Browser cannot reach 127.0.0.1 | A proxy is intercepting localhost. Set `NO_PROXY=127.0.0.1,localhost` and restart the browser. |
| Replay returns `run_budget_exhausted` | The team's 40 attempts are gone. Nothing to do — present the results already in the report. |
| Everything is broken | Fall back to the committed practice-corpus report: `python screen/serve.py --report nexus-loop/out/loop-report.json`. Say clearly that you are showing the practice corpus because the sealed run failed. **Say it; do not let it be discovered.** |

---

## Submission checklist

- [ ] `out/day6/loop-report.json` — produced by `run.py`, **never hand-edited**
- [ ] It contains at least one `prescriptions[].approval` written by the screen during the demo
- [ ] The complete system, including `screen/`
- [ ] `docs/ONE_PAGE_NOTE.md` — what is real, what is stubbed, what breaks at 100×
- [ ] The report validates: `python -c "import json,sys; sys.path.insert(0,'nexus-loop'); from nexus.validate import schema_errors, contract_problems; d=json.load(open('out/day6/loop-report.json')); print(schema_errors(d) or 'schema ok', contract_problems(d) or 'contract ok')"`
