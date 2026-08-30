# Speaker Notes — Presenting the Crew Recovery Pitch

For whoever presents the one-pager (or the technical brief) to stakeholders,
investors, or an airline OCC. Tuned for a **7–10 minute** talk with time for
Q&A. Bullets are lines to say out loud, not slides to read.

---

## Before you present

- Open ahead of time, on your machine:
  - `rostering-mvp/out/report_disrupted.html` — the full dashboard (risk radar,
    recovery proposals, what-if section)
  - `rostering-mvp/out/bench_report.html` — the 46-case benchmark table
- Have ready to run live (each prints in seconds): `python3 run_demo.py`,
  `python3 bench.py --quick`
- Write three numbers on a card — you will quote them repeatedly:
  **46/46 · 0.5 s · 3 → 0** (scenarios closed, worst-case recovery time,
  violations before → after).

---

## 0. The hook (30 s)

> "When a day goes wrong — weather, ATC, a broken aircraft — an airline has
> minutes to re-rostering crews legally, and most airlines still do it with
> spreadsheets and phone calls. We built the engine that doesn't."

- Pause. Don't explain yet. Hook first, then problem.

## 1. The problem (60 s)

- Crew is the **#2 cost after fuel** — 10–20% of operating expense, hundreds
  of millions a year at the big carriers. (Keep it directional; offer the
  research doc for sources.)
- The systems airlines run on are **20–40 years old**: nightly batch
  optimization, rigid rules, no real-time recovery, no mobile.
- A disruption invalidates the roster in minutes; **crew legality is the most
  time-critical resource** in the operation — bust a limit and you cascade
  into uncovered flights, cancellations, fatigue violations.
- With the **pilot shortage**, roster quality is now also a *retention* lever.

## 2. The wedge (45 s)

- "We are not asking anyone to replace their core planning system. We plug in
  beside it: **read their data, show risk, propose legal fixes, human
  approves.**"
- Why disruption recovery first: **fastest measured ROI** (avoided
  delay/cancellation cost), lowest integration risk, and it builds the trust
  you need before anyone lets you near the core.

## 3. What we built (90–120 s) — demo talking points

- Show the disrupted dashboard. Point, don't read:
  1. **Risk radar** — "crews about to break a limit, flights about to lose
     coverage, reserve gaps. This alone is Phase 0 — read-only, 4 weeks to
     shadow-run."
  2. **Recovery proposals** — "every row was validated against the real
     regulation before it was suggested. Reserve, swap, deadhead, split the
     pairing, release the crew."
  3. **What-if table** — "do nothing leaves 3 violations and 16 uncovered
     flights; the plan takes both to zero. That's the decision the scheduler
     makes evidence-based instead of by gut."
- Mention the rule engine is built on the **exact FAR 117 tables fetched from
  government sources**, not on folklore — and that what we don't model is
  flagged, not hidden.

## 4. The proof (60 s) — show bench_report.html

- "46 scenarios, from calm to 12-hour mass delays, worst case 38 uncovered
  flights and 10 crews in violation."
- "Every single one closes to zero — and the worst case takes about
  **half a second**."
- "That's decision support at the speed the problem moves. Batch systems
  couldn't, and wouldn't, be trusted to."
- (If live: run `python3 run_demo.py` and point at the what-if block.)

## 5. Moat, business case, ask (60 s)

- Moat in one line: "Every competitor has to rebuild the rule layers we've
  verified and tested — and keep them updated jurisdiction by jurisdiction."
- Business case in one line: "Priced per crew, paid for by one bad disruption
  season."
- Ask: "A pilot carrier for a 4-week read-only shadow run, plus 2–3 engineers
  and one domain SME. The scarce hire is the OR engineer; the non-negotiable
  hire is someone who has sat in a crew scheduling room."

## 6. Close (15 s)

> "The gap between what legacy systems deliver and what's possible has never
> been wider, and the shortage of crews means the cost of waiting keeps
> rising. We're ready to prove it on your data."

---

## Q&A prep — likely questions, suggested answers

**"Wouldn't this be cheaper to build in-house?"**
Cheap to sketch, expensive to finish: the moat is the verified, regression-tested
rule packs and the solver ladder (surgery/relief/deadhead) — years of domain
edge case work, not an integration project. Our repo is public-ready; compare
your bill against what it takes to replicate.

**"What about liability if a suggestion is wrong?"**
We position as decision support: human approval, immutable audit, explicit
"not covered" states, read-only Phase 0. The liability sits in the advice
layer, bounded — that's a product decision, not an oversight.

**"Why not let the incumbent do it?"**
Incumbents are batch-era platforms monetizing lock-in; their recovery modules
re-run the same pipeline nightly. Nothing stops them in principle — but the
time-to-market and the innovation-market fit are on our side.

**"Is the legality engine really right?"**
The FAR 117 numbers come from eCFR (2025-01-01), locked by unit tests; what
we approximate (rest variants, EASA Annex III, buffers) is listed in the docs.
A pilot carrier's rule-owner would sign off before Phase 1.

**"How do you get my data?"**
A versioned feed contract — files/REST/queue/CDC, whichever you expose. Phase 0
is read-only; write-back is opt-in with a rollback journal and kill switch.

**"What does a pilot actually look like?"**
4 weeks: we ingest one base's schedule and show the legality radar; the
scheduling team shadows it alongside their own checks. If it's not accurate,
we stop.

**"What's your team?"**
(Your answer, tailored — recommended: 1 OR engineer, 1 backend, 1 frontend,
part-time ex-scheduler SME; partners: licensed fatigue model, anchor carrier.)

**"How is this different from a rescheduling optimizer?"**
Off-the-shelf optimizers assume a clean plan and legal inputs. Ours is built
around legality as the hard constraint that breaks first, with recovery
actions (surgery, relief, deadhead) that keep every proposal legal.

**"What's the pricing?"**
SaaS per crew + implementation + rule-pack maintenance, with the wedge priced
against measured disruption savings; details per pilot.

**"Who else is doing this?"**
Point tools (bid assistants, roster viewers) and niche suites exist — no one
has yet shipped the legality-first, real-time, explainable full wedge. The
plan (research doc §8) documents the competitive field honestly.

**"What if the demo is synthetic?"**
That's the point of Phase 0: the engine is real; the data is not yours yet.
The contract and shadow run are designed to de-risk exactly that.

**"How fast can we start?"**
Phase 0 data feeds + shadow run: 4 weeks from data access.

---

## Presentation tips

- **One metric per slide.** If you feel you're overloading, drop to the card
  numbers (46/46 · 0.5 s · 3 → 0).
- **Demo live if possible** — the whole loop prints in ~15 s. If the network
  fails, the pre-opened HTML files are the fallback; never rely on live
  generation alone.
- **For OCC audiences**, lead with the legality model and the read-only
  shadow run; save commercials for the end. **For investors**, lead with the
  #2-cost problem and the pilot-shortage timing.
- **Stay honest about limits** — it's the fastest way to build credibility
  with people who've been burned by software demos.