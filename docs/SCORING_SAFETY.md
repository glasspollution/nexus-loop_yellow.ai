# Scoring safety: what the product layer may and may not touch

The engineering half scores **55.00 / 55** on the practice corpus and on three freshly generated
sealed corpora. Every machine point is already held.

> **Nothing in the product layer can raise the machine score. It can only lower it.**

So the product half works under a contract. This is that contract, derived by reading
`tools/nexus-loop-kit/score.py` line by line, and it is why the changes are shaped the way they
are.

---

## Safe

- **New keys, anywhere.** Top level, or as siblings inside any finding, diagnosis, prescription,
  metric or gap. `score.py` never enumerates keys — every read is a `.get()` on a fixed list — and
  the schema sets `additionalProperties: false` nowhere. Emitted reports already carried undeclared
  keys (`plan.refused_breakdowns`, `calibration.basis`) before this layer existed.
- **Rewriting the content of prose strings** — `decision.*`, `description`, `system_notes`,
  `gaps[].why`. None are scored by string value.
- **Writing `prescriptions[i].approval`** with all four fields as non-empty strings. This is the
  one write the schema, the contract checker and the judges' checklist all sanction.

## Never

| Rule | Why |
|---|---|
| **Never re-order `metrics[]`** | `score_honesty` resolves the fidelity traps with `ms[0]` — the *first* metric for an ask id decides. `m_tool_failure_*` (measured) must stay ahead of the derived A04 metrics or honesty loses **1.75**. |
| **Never add or remove entries** in `findings[]`, `metrics[]`, `diagnoses[]`, `gaps[]` | A stray `is_regression: true` costs up to **−3.0**. Two gaps sharing an `ask_id` silently shadow each other. |
| **Never change an enum, cohort key or value, `window.from_day`, `ask_id`, `verdict`, or `required_event.fields`** | All are exact-match scored. The cohort key alone is worth more than everything else combined. |
| **Never write a partial `approval`** | `contract_problems` requires `verdict, decided_by, reason, at` as non-empty strings. A null `at` fails the schema and makes the checklist claim a decision nobody made. |
| **Never strip `gaps[].nearest_proxy` / `why_the_proxy_misleads`** | Worth 0.5 together. |
| **Never let the pipeline write an `approval`** | Only the screen may. Two tests enforce it. A pre-filled verdict is a fabricated human decision. |

## The regression gate — run after any change to the report

```bash
python nexus-loop/run.py --kit kit
cd tools/nexus-loop-kit && python score.py \
  --report ../../nexus-loop/out/loop-report.json \
  --ground-truth ../../kit/ground_truth/ground_truth.json      # must read 55.00 / 55

python -m pytest -q nexus-loop/tests                            # 16 passed
python nexus-loop/validation/run_all.py                         # 53 checks, 0 failed
python nexus-loop/validation/equivalence.py                     # PASS
```

**`equivalence.py` is the one that matters most.** If it reports `incidents: IDENTICAL` then
detection and diagnosis are untouched, whatever else changed. If a deliberate report change makes
the *report* half differ, refresh the baselines — never the incidents ones:

```bash
python nexus-loop/validation/refresh_baselines.py --check     # see what would change
python nexus-loop/validation/refresh_baselines.py
```

---

## Where the product layer actually earns points

All 45 of them are human-scored, and none of them are in the machine's 55:

| | Points | Where |
|---|---|---|
| Decision Quality | 18 | Prose *inside* `loop-report.json` — impact blocks, baseline justifications, `if_nothing_changes`, `audience`, and the three `decision.*` fields. Judges read the file. |
| The Screen | 15 | `screen/` — one page, evidence visible, every number carrying its definition, and a write-back the judges can verify by opening the file. |
| Framing | 12 | `docs/DEMO_SCRIPT.md` and `docs/ONE_PAGE_NOTE.md`. Four behaviours, roughly three points each, every one a yes/no entirely within our control. |

The scorer prints an unscored checklist that the judges then grade. Before this layer it read
`with a human verdict 0/3`. That line is what the screen exists to move.
