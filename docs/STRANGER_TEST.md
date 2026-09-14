# The 30-second stranger test

The Screen is scored on one question: *"can a stranger read a finding, see the evidence, and
approve or reject the fix?"* That is not a question you can answer about your own work — you know
what the screen means. So run it for real, on someone who does not.

**This is the single highest-value thirty minutes available before the demo**, because it is the
only way to find out whether the fifteen points are actually there.

---

## How to run it

**Who:** someone not on this team. Any background. The less they know about AI agents, the better
the test. Three people is enough; the second and third rarely surprise you after the first.

**Setup:** `python screen/serve.py --report nexus-loop/out/loop-report.json`, page open at the top,
browser full screen. Have `python docs/reset_decisions.py` run first so the buttons are showing.

**Say exactly this, and nothing else:**

> "You run an AI support agent for a bank. This screen is telling you something. Take thirty
> seconds and then I'll ask you three questions."

**Start a stopwatch. Say nothing for thirty seconds.** Do not point. Do not explain what they are
looking at. The urge to help is the thing that invalidates the test.

**Then ask, in this order, and write down what they actually say:**

1. "What broke?"
2. "Who has to fix it?"
3. "What are you being asked to decide?"

**Then, one more, after the thirty seconds are up:**

4. "Point at any number on the screen. What does it mean, and how do we know it?"
   *(They should be able to click it and read the answer. If they do not realise numbers are
   clickable, that is a finding — the affordance is too quiet.)*

---

## Scoring it

| | Pass |
|---|---|
| Q1 | They describe the problem in their own words without using a metric name. "People asking about the new card aren't getting answers" passes. "The KB miss rate is 100%" means they read the evidence section, not the headline — the title is not doing its job. |
| Q2 | They say something equivalent to the owner chip. |
| Q3 | They describe the action, not "approve it". If they cannot say what would change, `asking_approval_for` is too vague. |
| Q4 | They find the popover within about ten seconds. |

**Three of four is a pass. Two or fewer means fix the screen, not the test.**

---

## If they fail

Record what they said verbatim — the exact wrong answer tells you which element misled them.

| They said | Likely cause | Fix |
|---|---|---|
| Something about the mix of traffic, or a dismissed item | `WHAT WE THREW AWAY` is being read as the finding | The finding needs more vertical separation from it |
| A metric name | The title is not landing; they skipped to the evidence | Shorten the title; check no jargon crept in |
| "I don't know who fixes it" | The owner chip is not prominent enough | It is a chip, not a table row, for this reason — make it bigger |
| "Approve the thing" | `asking_approval_for` is too abstract | It should name the action and its alternative |
| Nothing at all / froze | Too much above the fold | Cut a section out of the first viewport |

---

## Record of runs

Fill this in. An empty table on demo day means the test was not run, and "we ran it on ourselves"
is not a data point.

| Date | Who (role, not name) | Q1 | Q2 | Q3 | Q4 | What they actually said | What we changed |
|---|---|---|---|---|---|---|---|
| | | | | | | | |
| | | | | | | | |
| | | | | | | | |
