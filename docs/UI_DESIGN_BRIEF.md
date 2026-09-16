# Loop Desk — UI/UX design prompt

Paste the block below into Stitch or Lovable. Read the two notes first — they change what you
should ask for.

> **Note 1 — the brand yellow is a placeholder.** I could not reach yellow.ai from this
> environment to read the exact value. `#FFCE00` below is a stand-in. Before you paste, open
> yellow.ai, inspect the primary button or logo lockup in DevTools, and replace every
> `#FFCE00` with the real hex. Everything else in the palette is built to work around whatever
> yellow you drop in.
>
> **Note 2 — this is a skin, not a replacement.** The screen that exists today is one
> self-contained HTML file plus a stdlib server, and its `POST /decision` write-back into
> `loop-report.json` is the most checkable claim in the submission. Generated React will not
> carry that. Treat whatever Stitch or Lovable produces as a **visual system to port** — the
> palette, type scale, spacing, component shapes — into the existing page. If you do adopt the
> generated app wholesale, the write-back endpoint and its schema re-validation must survive
> intact, and you must have it working with two days to spare, not two hours.

---

## THE PROMPT

```
Design a professional enterprise web application called LOOP DESK.

## What it is

An AI-agent operations product. A bank runs a customer-service AI agent on WhatsApp. Loop Desk
reads eight weeks of that agent's own logs and hands an operations lead a short queue of
investigated, tested, signed-off decisions — and tells them, out loud, what it could not see.

It is NOT an observability dashboard. A dashboard hands you a chart and the work. This hands you
a decision and asks you to sign it. Every screen should feel like a case file on a desk, not a
monitoring wall.

The primary user is an Agent Operations Lead. Non-technical. Owns the deployment's health, not its
code. Their job is triage and decision, not exploration. They have ten minutes and a queue.

## Brand and visual direction

Match Yellow.ai's design language: bright signature yellow, near-black, generous whitespace,
rounded cards, clean geometric sans-serif, soft shadows, calm and confident. Enterprise, not
playful — this is a change-management surface where people approve edits to a production agent.

Design tokens — use these exactly:

  --brand-yellow:    #FFCE00   /* signature accent */
  --brand-yellow-dk: #E0B400   /* hover / pressed */
  --ink:             #10131A   /* primary text, primary buttons */
  --ink-2:           #4A5158   /* secondary text */
  --ink-3:           #767E88   /* labels, metadata */
  --bg:              #FAFAF7   /* warm off-white page ground */
  --surface:         #FFFFFF   /* cards */
  --rule:            #E6E8EC   /* hairlines */
  --good:            #1F6B43   /* improved / accepted */
  --warn:            #8A5A09   /* deferred / caution */
  --bad:             #A8321F   /* rejected / regressed */

Critical colour rules, non-negotiable:
- Yellow is for brand presence, focus rings, active nav, the left rail of the current case, and
  highlighting one key figure. NEVER yellow text on white — it fails contrast.
- Primary buttons are near-black (--ink) with white text, not yellow. Yellow on a decision button
  reads as a warning and is too low-contrast to be accessible.
- Yellow may be a solid fill behind near-black text (--ink on --brand-yellow) — that combination
  is high contrast and is the signature move. Use it for the brand bar and one hero accent.
- Status is NEVER communicated by colour alone. Every state carries an icon AND a word:
  "✓ Improved", "✕ Rejected", "● Still running", "⏸ Deferred".
- Body text minimum 4.5:1 contrast. Large figures minimum 3:1.

Type: a geometric grotesque — Inter, or similar. Scale: 40px hero figures / 30px page title /
15px body / 13px secondary / 11.5px uppercase tracked labels (0.1em). Numbers in a tabular
variant so columns align.

Shape: 12px radius on cards, 8px on controls, pill on chips. Shadows soft and low —
0 1px 2px rgba(16,19,26,.04), 0 8px 24px rgba(16,19,26,.06) on overlays only.

Motion: 150ms ease. NO animation on a decision state change — motion on an approval surface reads
as unserious. The only animated thing in the product is the loading state.

Layout target: 1440×900 desktop first. Must not break at 1024px.

## Screens

### 1. THE BRIEF — the landing page

A calm morning overview. Reference: a "features section with company workflow" layout for the
hero band, and a stats bento grid below it.

Top: a greeting band on solid brand yellow with near-black text.
  "Good morning, Shekhar."
  "Eight weeks of your agent's logs, read overnight. Three things need your decision."
  Small metadata row, monospace, muted: corpus · report build hash · generated timestamp ·
  "schema valid ✓"

Then a STATS BENTO — asymmetric grid, not equal tiles. One large tile, several small. Each tile
is a number, a plain-English label, and a small provenance chip. Content:
  - LARGE: "3 decisions waiting for you" — with the three case titles listed beneath as links
  - "3,943 conversations affected"
  - "329 didn't resolve that should have"
  - "635 handed to a human nobody staffed"
  - "$194.05 spent on them"
  - "3 lookalikes examined and dismissed"
  - "3 questions we refused to answer"
  - A distinct tile, styled differently from the rest: "Coverage — 72% acme-bank · 93%
    northwind-retail" with the caption "stated per tenant, never blended".

Every numeral on every tile is a button. Clicking opens a popover with: what it is, how we know it
(measured / derived / judged), what share of traffic can produce it, calibration if judged, and
the query that computed it. This is a hard requirement and applies on every screen.

Then an AREA CHART derived from the loop data. X axis is day 0–55. Plot daily conversation volume
as a soft area. Over it, shade the windows where faults ran as vertical bands in muted yellow,
each labelled. Real windows to render:
  days 33–44  Premium Card enquiries
  days 38–51  the get_order_status tool
  days 44–55  the acme_main_v3 agent
And in a lighter, dashed treatment, the three dismissed lookalikes: days 9–20, 22–31, 28–55.
Caption beneath, important: "Two of these three faults had already ended before anyone looked. A
dashboard showing the last seven days finds one of three."
One chart in the entire product. This is it. No second chart anywhere.

Then THE QUEUE — a reorderable list. Drag-to-reorder cards, each showing the case title in plain
English, the tenant, how long it ran, and the number of conversations. Default order is by
conversations affected, and the sort rule is stated in words above the list: "Ordered by
conversations affected. Drag to reorder your own queue." The system must never display an invented
priority or severity score — the ordering rule is always named.

Primary CTA: "Start deciding →".

### 2. THE DESK — the decision screen. This is the important one.

ONE case fills the viewport. There is no list view here and no way back to a table. Navigation
between cases is a small "‹ prev · 1 of 3 · next ›" control in the top bar only.

Top: a slim near-black system bar — product name, tenant, corpus, counts
("3 to decide · 3 dismissed · 3 refused · 0 signed off"), build hash in monospace, and the
prev/next control.

Then, in order down the page:

STATUS RAIL — a full-width tinted strip with icon and words:
  "● Ended — ran 10 days and stopped on day 44. Nobody was told."
Yellow left border 3px when the case is undecided; green when accepted; amber when rejected.

TITLE — 30px, plain English, max 26 characters per line, no metric names, no cohort keys:
  "Customers asking about Premium Card enquiries are not getting a useful answer."
Below it, small and muted: "acme-bank · Premium Card enquiries"

FOUR HERO FIGURES — exactly four, 40px, each with a left rule and a plain label. Four can be
absorbed at a glance; seven cannot.
  230 conversations affected | 4.3% of acme-bank traffic | 102 didn't resolve that should have
  | 10 days before anyone could act
For a case where the outcome metric did not move, the third figure becomes spend instead, and a
callout appears directly beneath: "Resolution did not move. That gap is 0.78 percentage points
against a sampling error of 1.12 on 1,224 conversations — inside the noise. This costs money and
customer time, not resolutions."

"IF NOBODY ACTS" — a bordered callout on a pale yellow tint, flag icon, one plain sentence stating
a daily rate, not a total.

A PROGRESS TRACKER — reference: an order-tracking / shipment-progress component, horizontal, five
steps with connecting line and per-step state. Label the steps in operator language, NEVER in
system language:
  "Found it" → "Explained it" → "Proposed a fix" → "Tested it" → "Your call"
The fifth step is the live one and pulses subtly until a decision is recorded.
Do not use the words Detection, Diagnosis, Prescription or Verification anywhere a user can see.

OWNER + ASK — two columns. Left: "WHO HAS TO ACT" with near-black pill chips (Agent Builder,
Business Owner). Right: "DECISION ASKED OF YOU" with one imperative sentence.

"WHAT WE MEASURED" — evidence rows. One claim per row, never a table of twelve metrics. Each row:
metric name in plain English, the value as a large clickable numeral, "vs X baseline", a horizontal
comparison bar (a div with a width, not a charting library), and beneath it a provenance chip line
— "⬤ Measured · covers 100% of acme-bank · intent=premium_card_info". Then, inline and always
visible, never behind a tooltip, the baseline justification as two lines of prose in a left-ruled
block: "Baseline: peer traffic. This cohort has no before-period. It appears for the first time
inside this window, so comparing it with its own past would find nothing no matter how well tuned
the detector is — it was born broken."
A "Show the full working" disclosure beneath reveals the derivation string in monospace.

"WHY IT HAPPENED" — the attributed config change as a prominent line
("Day 34 · kb change"), then an amber chip reading "◐ Attributed — consistent with cause, not
proved". Never render the word "caused". Then a muted paragraph explaining the attribution, and a
left-ruled "If we are wrong:" block.
A disclosure here uses an AGENT-TRACE / AI-TOOL-CALL treatment: a vertical timeline of the steps
the system actually ran to reach this conclusion — each step a collapsible row with a name, a
duration, and its inputs and outputs in monospace. This is where "show your working" lives.

"WHAT WE PROPOSE" — the fix in plain words, a predicted-delta line with both numbers clickable,
and a bordered "⛔ PRE-COMMITTED STOP CONDITION" callout: "We would not ship this if the
golden-set replay regresses any known-good conversation, or the business confirms this product
line is being withdrawn."

"DID IT WORK" — one result card per replay. Header with icon and word ("✓ Improved"), plus chips
for "golden set clean" or "golden set regressed". Body is one plain sentence of what happened.
If the pre-committed stop condition fired, the card turns amber regardless of the headline result
and carries a bold line: "This change improved the cohort and still broke 1 of 50 known-good
conversations. We said we would not ship if that happened. Recommendation: do not ship as
proposed." Include a separate, visually secondary card for a fix that was tested and did NOT work,
labelled "alternative we tested" — reporting a failed attempt is deliberate, not an error state.
Footer line, muted, always present: "ⓘ This ran on the organisers' replay simulator against
recorded traffic, not on production."

THE DECISION GATE — three buttons, in this order and these weights:
  [ ACCEPT FIX ] near-black filled, primary
  [ REJECT ] outlined, turns red-tinted on hover
  [ DEFER — need more information ] outlined, quiet
No keyboard shortcut approves anything. Approving a change to a production agent must cost a
deliberate click.
Clicking any of them opens a confirm dialog that shows, in monospace, exactly what is about to be
written:
  writes to   loop-report.json → prescriptions[p1].approval
  verdict     rejected
  change      kb.add on premium_card_info
  against     report build sha256:6f4e5f1f…
  then        re-validated against the schema before it is saved
The dialog requires a name and a reason. Offer one-click reason chips plus free text. A reason is
mandatory on all three verdicts, not just rejection.
After confirming, show the written JSON — before and after — so the operator can see the file
changed. A rejection must render as a FINISHED decision, not an error state: same visual weight as
an acceptance, reason displayed in full.

"WHAT WE THREW AWAY" — the dismissed lookalikes. Each: a grey "✕ dismissed" chip, the plain-English
title, an amber cause chip, the scope and window, and the full dismissal reasoning as a paragraph.
A disclosure reveals the measurements. These must be visible on the page, not behind a tab.

"WHAT WE CANNOT SEE" — the refusals. Permanently on the page, never a tab or a modal. For each:
the operator's question in quotation marks at 15.5px as the heading, a verdict chip
("NOT MEASURABLE" in red tint, "NEEDS A NEW JUDGE" in amber), then the explanation, then — and
this is the part that matters most — a left-ruled block: "The tempting answer is
llm_call.retry_count > 0 — but those are quality retries, not failovers. Reporting them would show
a small non-zero rate that reads as 'failover is working', when failover does not exist."
Then a near-black monospace code block, rendered as a real multi-line block:
    event failover {
      from_target,
      to_target,
      reason,
      recovered
    }
    grain: step   owner: conversation-runtime
Caption: "That turns a gap into a ticket for a named team."

DECISION TRAIL — reference: an audit-log component. A vertical timeline of every decision recorded
against this case, newest last, never overwritten. Each entry: verdict, who, absolute timestamp
(never "2 hours ago" — audit trails do not use relative time), reason in full, and the report build
hash it was signed against. Changing a decision appends a new entry and both remain visible.

FOOTER — a dashed-border strip, always present:
"🔒 Metric definitions, the judge version and the good-conversation standard are frozen. This
system proposes changes to the agent, never to the yardstick. Every number on this page is read
from a static report file; the screen does not stream."

### 3. LOADING STATE

While the report loads, a centred ambient loader — soft, slow, particle-or-cloud-like, in brand
yellow on the off-white ground. Beneath it, cycling status lines in monospace:
  "Reading 80,252 conversations…"
  "883,764 execution steps…"
  "Testing 1,400 metric × cohort series…"
  "Ruling out lookalikes…"
This is the only place in the product with meaningful animation.

## Hard non-goals — do not design these

- No findings list or table as a home screen. The Brief hands off to one case at a time.
- No filters, search, sort controls, or date pickers. The system already did the analysis; those
  are "go find it yourself" affordances and this product's promise is the opposite.
- No severity score out of 100. No invented priority number. Ordering rules are named in words.
- No second chart. One area chart on the Brief, and comparison bars that are divs with widths.
- No chat interface.
- No "re-run" or "refresh" button anywhere.
- No login, roles, settings, dark mode, or mobile layout.
- No live or streaming anything.
- No relative timestamps.
- No em-dash-heavy marketing copy. The tone is a competent colleague briefing you, not a product
  page.

## Data contract

Bind every screen to this JSON. These are the real key names — do not invent fields.

Top level: team, corpus, system_notes, coverage_measured, metrics[], standard[], findings[],
diagnoses[], prescriptions[], verifications[], gaps[], self_assessment, report_build

findings[] (a regression):
  id, tenant, cohort{}, metric, window{from_day,to_day}, is_regression, evidence[] (strings),
  cohort_label, title_plain, status_plain,
  metric_plain{plain,definition,fidelity,unit,higher_is_better},
  observed, expected, severity,
  impact{conversations_affected, share_of_traffic, downstream{would_have_resolved_at_baseline,
    unplanned_handoffs, abandoned}, cost_usd, days_running, derivation, impact_type, outcome_note},
  baseline{type, basis, value, justification},
  if_nothing_changes, audience[]

findings[] (a dismissal) has a DIFFERENT shape — no impact, no audience, no observed/expected:
  id, tenant, cohort{}, metric, window{}, is_regression:false, evidence[], cohort_label,
  title_plain, status_plain, metric_plain{}, severity, not_a_regression_because

diagnoses[]: id, finding_id, cause_class, confidence, attribution_confidence_plain,
  attribution_plain, attributed_change{kind,day}, evidence[]

prescriptions[]: id, diagnosis_id, change_type, target, description, autonomy_rung,
  predicted_delta{metric,from,to}, predicted_delta_plain{},
  decision{asking_approval_for, risk_if_diagnosis_wrong, would_not_ship_if},
  approval{verdict, decided_by, reason, at}    ← written by the screen only

verifications[]: prescription_id, replay_run_id, metric, before, after, golden_set_pass, verdict,
  plain, caveat, stop_condition_triggered, stop_condition_note, is_alternative, alternative_note

gaps[]: ask_id, verdict, why, nearest_proxy, why_the_proxy_misleads,
  required_event{name, grain, fields[], owner}

metrics[]: id, name, ask_id, grain, fidelity, coverage{value,basis,excluded[]},
  calibration{agreement,n,basis}, plan{source,filter,denominator,breakdowns[]}

Join order: findings.id ← diagnoses.finding_id; diagnoses.id ← prescriptions.diagnosis_id;
prescriptions.id ← verifications.prescription_id.

Rendering rules tied to the data:
- approval.verdict is one of exactly: accepted, rejected, deferred. Never the word "approved".
- Render a rate as a percentage ("100%"), money as currency, a score as a decimal. Never show a
  rate as "1".
- Never show more decimal places than the coverage supports. If coverage is below 95%, round.
- If a calibration figure is ≥ 0.995, render it as "⚠ Suspiciously perfect — investigate", not as
  a good score.
- The number of cases, dismissals and refusals varies. The layout must hold with zero regressions
  (show a proper empty state: "Nothing in this deployment needs a decision"), with one, and with
  nine.
- Never hardcode a day number, tenant name, cohort value, metric name or count into the design.
  Every one of them changes between runs.
```

---

## After you get the output

1. Take the palette, type scale, spacing and component shapes. Port them into
   `screen/index.html`, which already renders all of this from the real report.
2. Keep `POST /decision` and its schema re-validation exactly as they are.
3. Re-run `python docs/judge_check.py` — it checks section names, the three verdicts, the absence
   of a severity score, colour-independence and the self-contained constraint. It should stay at
   0 failed.
4. Re-run the stranger test in `docs/STRANGER_TEST.md` on the new visuals. A prettier screen that
   a stranger understands less is a worse screen.
