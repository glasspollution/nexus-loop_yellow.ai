# Nexus Loop — 10-minute demo script

**Two people.** One narrates, one drives. The narrator never touches the keyboard.

**Every number is in [BRACKETS].** Read them off the screen, or off
`python docs/demo_numbers.py`, on the day. Days, tenants, cohorts, counts and even which metric is
the headline all move on the sealed corpus. A number memorised on day 5 is a wrong number on day 6.

**Before you start:** `python docs/reset_decisions.py` — rehearsal writes real decisions into the
real file, and if they are still there the screen opens on a receipt instead of the buttons.

**The four things Framing is scored on.** They are yes/no and entirely inside your control:
open on the problem · show the refusal · state coverage out loud · admit what was faked.
They are Beats 0, 8, 1+9, and 9. **If you are running long, cut Beat 3 and Beat 5. Never cut Beat 8.**

---

## BEAT 0 · 0:00–0:45 · The operator's problem
**Screen:** nothing. Blank, or one line of text. No architecture diagram, no logo, no product name.

> "A bank runs an AI agent on WhatsApp. Two months ago, something in it broke. They found out from
> a customer complaint. Somebody then guessed what had changed, read transcripts by hand, edited a
> prompt, and hoped. Nobody ever checked whether the fix worked.
>
> Every fact needed to do that properly was already in the logs. Nobody had built the thing that
> reads them."

**Transition:** *"This is what it looks like when something does."*

> **Scored:** did the demo open on the problem? Secured in forty-five seconds. Do not put a diagram
> on the screen to 'set up' this beat — that is the single most common way to lose these points.

---

## BEAT 1 · 0:45–2:15 · The finding
**Screen:** the finding page. Hero numbers and `IF NOBODY ACTS` visible without scrolling.

> "One screen. One decision. [CONVERSATIONS] conversations — [SHARE]% of this bank's traffic.
> [LOST] people asked about [COHORT] and did not get an answer. [HANDOFFS] of them ended up with a
> human who was never staffed for it.
>
> And look at the top of the screen: **[STATUS — e.g. 'it ran ten days and stopped on day forty-four'].
> It already ended. Nobody ever knew it happened.** A dashboard showing you the last seven days
> finds none of this. This system reports episodes, with a start and an end — not current state.
>
> One number before we go on: every tool figure you will see on this tenant covers **[COVERAGE]%**
> of its conversations. Not a sample — the other [100-COVERAGE]% runs on an older flow that cannot
> produce the number at all."

**Transition:** *"Before I tell you why this happened — three other things in this data also looked
like problems."*

> **Scored:** Decision Quality (could an operator act, is the impact scaled and real).
> **This is coverage mention 1 of 2.**

---

## BEAT 2 · 2:15–3:15 · The lookalike we correctly ignored
**Screen:** scroll to `WHAT WE THREW AWAY`. Open the traffic-mix one.

> "A marketing campaign pushed [N]× the normal volume into an easy question type. The aggregate
> containment number went **up**. Good news, on any dashboard.
>
> We still call it not-a-problem — because once you standardise for the mix, it is flat. Every
> individual cohort is unchanged. The improvement is an artifact of what people happened to ask.
>
> We examined all [N] lookalikes and dismissed each one **in writing**, with the measurement that
> proves it. Staying quiet about something is not the same as dismissing it."

**Transition:** *"So — the one we did flag. Why did it happen?"*

> **Scored:** Specificity, and the biggest trust moment in the demo. If you only have time for one
> lookalike, use the one where the number got *better* — resisting good news is the strongest
> signal available.

---

## BEAT 3 · 3:15–4:15 · The diagnosis and the baseline *(cut this first if long)*
**Screen:** `WHAT WE MEASURED`. Point at the bar and the baseline paragraph underneath it.

> "[METRIC] is at [VALUE] against a baseline of [BASELINE].
>
> Now look at which baseline we used — **peer traffic, not this cohort's own history.** That is
> deliberate. [Read the baseline justification off the screen: this cohort has no before-period,
> it was born broken.] Any detector comparing it to its own past is not badly tuned — it is
> structurally blind to this.
>
> And every number on this page is a button." *(driver clicks one)* "Definition, how we know it,
> what share of traffic can produce it, and the query that computed it."

**Transition:** *"We can also point at the change that did it."*

---

## BEAT 4 · 4:15–5:00 · The configuration change
**Screen:** `WHY IT HAPPENED`.

> "Day [DAY]. A [KIND] change. And the field that change controls flips for exactly this cohort on
> exactly that day.
>
> We say **attributed**, not caused. The screen says so too — 'consistent with cause, not proved'.
> This is strong circumstantial evidence, not a controlled experiment, and we are not going to
> dress it up as one."

**Transition:** *"Here is what we are asking a human to approve."*

---

## BEAT 5 · 5:00–5:45 · The proposed fix *(cut this second if long)*
**Screen:** `WHAT WE PROPOSE`, including the stop condition.

> "[Read `asking_approval_for` off the screen.] Predicted: [FROM] to about [TO].
>
> And before we ran anything, we wrote down what would stop us shipping it." *(point at the stop
> condition)* "Notice it has two halves: one technical, one commercial. Fixes get blocked for
> business reasons, and a system that can only express technical conditions cannot hold that."

**Transition:** *"Does it actually work? We tested it."*

---

## BEAT 6 · 5:45–6:45 · Proof, including the fix that failed
**Screen:** `DID IT WORK`.

> "Replayed on [N] recorded conversations: [METRIC] went [BEFORE] to [AFTER]. [GOLDEN] known-good
> conversations replayed alongside it.
>
> And be clear what you are looking at — that is the organisers' replay simulator, not production
> traffic. That sentence is on the screen, not in a footnote."

**If a stop condition fired** *(check `demo_numbers.py` — it did on the practice corpus)*:
> "Now this is the interesting one. The fix worked **and** it broke [N] of the known-good
> conversations. We pre-committed to not shipping if that happened. So the system's own
> recommendation flips to *do not ship as proposed*. It is holding itself to a condition it wrote
> down before it saw the result."

**Then scroll to the alternative:**
> "We also tested the blunter option — reverting outright instead of the narrow change. It came
> back **no effect**, and it broke [N] golden-set conversations. We are showing you that because it
> failed. That is a result, and it is why the system proposes the specific fix rather than the
> obvious one."

**Transition:** *"Now the part that matters. A human decides."*

> **This beat is worth more than a second success story.** A team that only shows things working
> has not demonstrated that it would tell you when they do not.

---

## BEAT 7 · 6:45–8:00 · The approval gate — **demo the REJECTION first**
**Screen:** click `REJECT`. Pick a reason chip. Type a rationale. Confirm. Then `view the change`.

> "Reject. Reason: [e.g. 'our own stop condition fired — the replay broke a known-good
> conversation'.] Confirm.
>
> And here is the file." *(the diff modal is now open)* "The decision is written into
> `loop-report.json`, at `prescriptions[p1].approval` — the verdict, who decided, when, why, and
> the build hash of the evidence they were looking at. If the report is regenerated, a decision
> made against the old evidence is refused.
>
> The system does not get to ship anything. It gets to ask. **A rejection with a good reason is as
> complete an answer as an approval**, and the record has to show both."

*(Driver: close, then `change decision` → ACCEPT, to show the audit trail appends rather than
overwrites. Only if you are on time.)*

> **Scored:** The Screen — the single most checkable claim you make. Judges will open the file.
> Open it for them first.

---

## BEAT 8 · 8:00–8:50 · The question we refused — **never cut this**
**Screen:** `WHAT WE CANNOT SEE`, full panel.

> "An operator asked us: *what is our failover rate?* We refuse to answer it. This runtime has no
> failover mechanism, so no failover event is ever logged. There is nothing to count.
>
> Now — there is a tempting answer. There is a retry-count field sitting right there. We could
> report it, and we would get a small, comfortable number that reads as *failover is working fine*.
> **The seductive wrong answer is the reassuring one.**
>
> So instead we specify the event that would have to exist." *(point at the spec)* "Name, grain,
> four fields, and the team that owns emitting it. That turns a gap into a ticket.
>
> There are two more on this panel. One we refuse because the reason someone gave up is a
> judgement, not a measurement, and we have no labels to calibrate a judge against. One we refuse
> because a per-customer breakdown has [N] distinct values against a budget of [BUDGET] — so we
> refuse it rather than silently return the top two hundred and let it look like an answer."

**Transition:** *"Two more things and we are done."*

> **Scored:** the PS calls this the most memorable thirty seconds available. Give it the full
> forty-five and say the 'seductive wrong answer' line in those words.

---

## BEAT 9 · 8:50–9:30 · Coverage out loud, and what is faked
**Screen:** the one-page note.

> "Coverage, out loud, once more: the tool numbers you saw cover **[COVERAGE]%** of this tenant's
> conversations and **[COVERAGE2]%** of the other one. We never blend them — a single number would
> describe neither deployment.
>
> And what is faked, before you ask. The screen reads a static file; it does not stream. Replay is
> the organisers' simulator, not production. There is no authentication — the name on that decision
> is typed, not verified. The standard is not mined. The self-assessment has one cycle, so we report
> the counts and refuse to compute a hit rate from them.
>
> At a hundred times this scale, the single-pass in-memory loader is what breaks first, and the
> detection threshold would have to be recalibrated for the multiple-comparison burden. The
> detection mathematics itself is scale-free. That is all in the one-page note.
>
> Faking things in six days is fine. Hiding it is not."

> **This is coverage mention 2 of 2, and the 'admit what was faked' point. Say it before anyone
> asks — stated is scored, inferred is not.**

---

## BEAT 10 · 9:30–10:00 · Close
**Screen:** back to the finding, receipt visible.

> "Everything you have just seen came from one command, against a corpus this system had never been
> run on, with no human involved until the reject button.
>
> An agent deployment records almost everything it does and learns nothing from it, because the
> loop is closed by a person moving between six tools. **We built the loop instead.**"

---

## Questions you will get, and the honest answers

| Question | Answer |
|---|---|
| "Is your judge accurate?" | "It agrees with human reviewers [CAL]% of the time on n=[N], within a single judge version. We never pool across the rubric change. And if it came back 1.00 we would treat that as a bug — human labellers disagree with each other about 7.5% of the time." |
| "Could you approve something by accident?" | "No keyboard shortcut, and a confirm step that shows you exactly what will be written before it is written." |
| "How do you know the fix worked?" | "We do not know it works in production. We know what the organisers' simulator returned on recorded traffic, and that is on the screen next to the number." |
| "Why not just alert on resolution rate?" | "One of these three faults never moves it. [Point at the outcome note.] We detect on the mechanism and confirm on the outcome — and where the outcome does not move, we say so instead of claiming lost conversations." |
| "What does it miss?" | "Gradual ramps below our threshold — we know of two. Lowering the threshold catches them and raises the false-alarm rate. That trade is a product decision and we have not made it. Also: diagnosis generalises less well than detection — 14 of 16 exact cohorts on unseen fault types, 11 of 16 correct causes." |
| "What is your score?" | "55 out of 55 on the practice corpus and on three freshly generated sealed ones. But the sealed run is the only score that exists and we have not seen it." |
| "Why three verdict buttons?" | "Because the schema has three, and because the real operator's job is approve, reject, or escalate. Deferring with a reason is a legitimate outcome and the record should be able to hold it." |

---

## Rehearsal checklist — run twice, with a stopwatch

- [ ] `python docs/reset_decisions.py` has been run
- [ ] Both people know who drives and who talks
- [ ] Total under **10:00**, measured, not estimated
- [ ] First 45 seconds contain no screen and no architecture
- [ ] A coverage percentage is said out loud **twice**
- [ ] A rejection is demonstrated **before** an approval
- [ ] The JSON diff is opened on screen
- [ ] The refusal beat runs **≥ 40 seconds**
- [ ] The phrase *"the seductive wrong answer is the reassuring one"* is said
- [ ] What is faked is stated **before** anyone asks
- [ ] Every spoken number was read from the current report, not from this file
