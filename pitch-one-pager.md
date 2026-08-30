# Crew Recovery, Rebuilt
## A legality-first disruption engine for airline crew scheduling

> **One line:** a modern, real-time re-rostering engine that fixes what 20-year-old
> batch crew systems can't — turning hours of manual spreadsheet firefighting into
> ranked, *provably legal* recovery proposals in under a minute.

---

## The problem

- Crew is an airline's **#2 cost after fuel** (~10–20% of operating expense; hundreds of millions/year at network carriers).
- The incumbent crew systems (Sabre AirCentre, Jeppesen, Lufthansa Systems NetLine/Crew, AD OPT …) were built 20–40 years ago: **nightly batch optimization, rigid rule engines, siloed data, no mobile, no real-time recovery**.
- Disruptions (weather, ATC, aircraft) invalidate rosters in **minutes** — and crew legality is the most time-critical resource in the operation. A legality break can cascade into uncovered flights, cancellations, and fatigue violations.
- The pain is measurable: avoidable crew-attributable delay/cancellation cost, reserve inefficiency, and — with the pilot shortage — **roster quality is a retention lever**.

## The wedge: disruption recovery

| Why this entry point | Why it wins |
|---|---|
| Asset-light: reads existing systems, never asks to replace the core | Trust-first: read-only legality visibility → ranked proposals → human approval |
| Fastest measured ROI: it pays for itself in avoided disruption cost | Sells to the OCC/scheduling office that feels the pain every day |

## What we built — a working prototype

A stdlib-only Python demo (`rostering-mvp/`) covering the full loop: synthetic airline → legality engine → disruption → risk radar → recovery → what-if.

- **Legality engine on the exact rules** — FAR 117 per-duty Tables B/C + cumulative limits **fetched from eCFR**; EASA Annex III Tables 2/3/4 + verified duty accumulators (60/110/190 h) **from the official regulation PDF**; simplifications explicitly flagged. The rule pack is the moat: versioned, regression-tested, jurisdiction/contract-switchable.
- **Risk radar** — legality-broken crews with margins, uncovered flights, reserve gaps.
- **Recovery action ladder — every proposal legality-validated**: reserve → swap → deadhead (cost-modeled) → pairing surgery (split an over-long duty) → knock-on relief → explicit cancellation recommendation when no legal crewing option exists. Legal-but-tight (at-risk) takers are permitted and surfaced with margins — **violations are never proposed**.
- **What-if** — "do nothing vs. this plan" for legality, coverage, and fatigue before any action is committed.
- **Benchmark (48 scenarios, incl. 14-day scale-ups):** do-nothing damage up to **47 uncovered flights / 7 violating crews** under 12-hour hub disruptions; the plan closes **coverage in all 48** (0 uncovered) and is **violation-free in 46**; the two most extreme 12 h-delay cases explicitly recommend cancellation; worst-case recovery **≤1.0 s**.

## The moat

1. **Exact, certified rule packs** (regulation + CBA constraints) with regression suites — the top barrier to entry, and the top asset once accumulated.
2. **Legality-before-optimality** — never proposes anything illegal; explainable outputs schedulers and unions can contest.
3. **Fatigue + fairness built in** — FRMS-model seam (SAFTE/FAID/FAST-class), quantified fairness, immutable audit trails for regulators and unions.
4. **A solver ladder incumbents don't have** — exact picker, surgery, relief; 14× runtime win from engineering the search (7.5 s → ≤1.0 s on 14-day horizons, coverage still fully closed).

## Business case

- **Price geometry:** SaaS per crew + implementation + rule-pack maintenance; wedge priced against measured disruption savings.
- **Payback narrative:** one bad disruption season pays for the tool.
- **Pipeline to full platform:** recovery engine (this) → bidding/trading crew-experience layer → full modern rostering suite for greenfield carriers.

## The ask — 90 days

1. **One pilot carrier** (LCC/regional/network): data access + OCC co-design → shadow-run the legality radar in ~4 weeks (Phase 0), proposals in ~10 more.
2. **Funding:** 2–3 engineers (one OR, one backend, one frontend) + a part-time domain SME (ex-airline crew scheduler — non-negotiable).
3. **Key hires/partners:** an OR engineer (the scarcest ingredient) and a licensed fatigue-model provider.

## Why now

- Pilot shortage + post-2020 attrition make **roster quality a retention weapon**; fatigue science (FRMS) is regulatory momentum, not a footnote.
- Cloud + modern OR tooling make **minute-scale re-optimization feasible for the first time** — the gap between what legacy batch systems deliver and what is possible has never been wider.

---

*Repo: research report (`airline-rostering-research.md`), architecture blueprint (`recovery-engine-architecture.md`), working prototype with 54 tests (`rostering-mvp/`; `python3 run_demo.py`) — all committed, CI'd, and reproducible.*