# Technical Brief — Disruption Recovery Engine
## For the CTO / Head of Operations Control

> **In one paragraph.** A decision-support overlay for crew scheduling during
> irregular operations. It consumes your existing schedule/pairing/roster
> state through a versioned feed contract, maintains a real-time legality
> model over the exact regulations (FAR 117 Tables B/C from eCFR; EASA FTL
> cumulative limits from EUR-Lex), detects crews about to break legality and
> flights about to lose coverage, and generates **ranked, legality-validated
> recovery proposals in seconds** — every proposal human-approved, fully
> explained, and audited. It never replaces your core planning system, never
> auto-executes, and degrades to read-only visibility when feeds go stale.

---

## 1. System overview

```
 Incumbent systems           Recovery Engine (ours)                      Egress
 ┌─────────────────────┐    ┌──────────┬──────────┬───────────────┐    ┌───────────┐
 │ Pairing/Roster      │───▶│ Ingestion│ Legality │ Detection &   │───▶│ Scheduler │
 │ OCC / Flight Ops    │    │ & World  │ Engine   │ severity      │    │ workbench │
 │ Crew tracking       │    │ Model    │ (rules)  │               │    ├───────────┤
 │ Aircraft recovery   │    ├──────────┼──────────┴───────────────┤───▶│ OCC APIs /│
 │ External feeds      │───▶│ Recourse │ picker · surgery · relief│    │ crew apps │
 │ (weather/ATC)       │    │ + what-if│ deadhead (cost-modeled)  │───▶│ audit /   │
 └─────────────────────┘    └──────────┴──────────────────────────┘    │ regulator │
 (via feed adapters,         deterministic · explainable ·            └───────────┘
  per the data contract)      human-in-the-loop)
```

## 2. Integration model — how it attaches to your stack

- **Phase 0 is read-only:** we ingest planned + operational state and publish a
  "legality risk radar" — no write-back, no decision authority.
- **Feed contract** (`contract/README.md`, `crew-recovery-contract/1.0`): one
  versioned schema for flights, pairings, crews, reserves; adapters normalize
  whatever your sources provide (files/SFTP, REST, message queue, CDC on the
  legacy DB — screen-scraping explicitly last resort).
- **Staleness policy:** every feed carries a generation timestamp; per-feed
  staleness telemetry drives graceful degradation to read-only (no stale
  proposals).
- **Write-back** (Phase 1+, opt-in): two-phase staging → approve with
  checksums and a rollback journal; a kill switch to read-only.

## 3. Legality & rules — the core trust surface

- **Exact FAR 117:** per-duty FDP tables **B and C** (10 start-time bands × 7
  segment columns for unaugmented; rest-facility class × pilot count for
  augmented) plus cumulative limits (100 h/672 h, 1,000 h/365 d, 60 h/168 h,
  190 h/672 h) — fetched from eCFR (14 CFR part 117, 2025-01-01), verified in
  this project's research, and locked by unit tests.
- **EASA FTL:** cumulative flight-time limits exact (100 h/28 d, 900 h/yr,
  1,000 h/12 mo); **Annex III Table 2 (per-duty FDP) exact**, plus Tables 3/4
  (unknown acclimatisation / FRM) and the duty accumulators (60 h/7 d ·
  110 h/14 d · 190 h/28 d) — all encoded from the official regulation PDF,
  committed under `rostering-mvp/docs/`.
- **Explicit simplifications (flagged in code, not hidden):** minimum-rest
  variants (10 h standard modeled; FAR 117.25 reduced-rest, EASA away-from-
  base ≥10 h rest + 36 h recovery rest and reduced-rest schemes not modeled),
  report/debrief buffers (60/15 min), a company flight-time guardrail
  (`co.ft-per-fdp`, explicitly *not* a FAR 117 limit).
- **Rule-pack governance:** versioned rule packs per jurisdiction/contract,
  regression corpus on every change, "why legal/illegal" audit API,
  immutable audit log — positioned for regulator and union review.

## 4. Recovery engine

- **Action ladder, every action validated end-to-end through the RuleEngine
  before it is proposed:** reserve callout (10) → crew swap (20) → deadhead /
  reposition with travel-cost model (40 + travel/60) → **pairing surgery**
  (split an over-long duty at leg N: the broken crew keeps a legal prefix, a
  fresh crew takes the suffix — validated to actually *heal* the crew) →
  **knock-on relief** (release a still-broken crew only while the pairing
  stays staffed; otherwise re-crew with a legal taker) → **explicit `cancel`
  recommendation** when no legal crewing option exists at all (12 h delays).
  Legality = no violations; **at-risk (legal but tight) takers are permitted
  and surfaced with margins** — never hidden.
- **Selection:** an exact CP-style picker (one action per gap, each crew used
  at most once, maximizing covered gaps then minimizing cost). Surgery-
  requiring gaps claim crews FIRST (taker starvation is impossible).
  Deterministic branch-and-bound with a **node cap (250 k) and per-gap
  candidate cap (14)** so mass-disruption states degrade gracefully — capped
  runs still close coverage fully; flagged `picker.capped`.
- **Complexity note:** pure-Python DFS is prototype-grade; production swaps in
  OR-Tools/Gurobi at the same interface (the benchmark quantified why: 16 M
  DFS nodes / 7.5 s before the cap → ≤1.0 s after, incl. 14-day horizons).

## 5. What-if & fatigue

- Scenario evaluator: fork the world, apply or skip a plan, and compare
  legality, coverage, reserve usage, and fatigue — before committing anything.
- Fatigue is a documented *toy* model (night duty, early starts, long days,
  short rests) behind a narrow interface; integration point for a licensed
  SAFTE/FAID/FAST-class model. Not safety-claiming.

## 6. Performance (measured, this build)

| Metric | Value |
|---|---|
| Full pipeline (world → radar → recovery → what-if), mean | **171 ms** |
| Worst case (12 h mass delay, 14-day horizon, 47 uncovered / 7 violations) | **≤1.0 s** |
| Coverage closed (48-scenario grid incl. 14-day scale-ups) | **48/48 → 0 uncovered** |
| Violation-free plans | **46/48** (the 2 most extreme 12 h-delay cases keep one crew exposure and explicitly recommend cancellation) |
| Legality validation per candidate | microseconds (batch) |
| Determinism | same inputs → same outputs (node cap may trade optimality for time, never legality) |

## 7. Reliability & safety posture

- **Decision support, not control:** approval workflows, human-in-the-loop,
  immutable audit trails. This is deliberate: it keeps certification/liability
  exposure bounded to the advice layer.
- **Deterministic + reproducible** outputs (auditable, unionable).
- **Graceful degradation:** read-only radar if feeds stale; no silent
  assumptions ("not covered" is an explicit state).

## 8. Deployment & ops (forward view)

Cloud-native microservices (managed K8s, Postgres + event stream), API-first
with an OCC integration layer, multi-tenant from day one, sandbox environment
running the full stack on simulated data, and observability on proposal
latency, legality-breach near-misses, and scheduler adoption.

## 9. What we need from you (pilot engagement)

1. Feed exposure decision: which sources, at what latency (files/API/queue)?
2. OCC workflow slot: where our decision layer sits without breaking authority.
3. Rule pack: FAR 117 vs EASA + which CBA we encode first, and who owns rule
   interpretation sign-off.
4. Fatigue model: which FRMS/biomathematical model your medical dept trusts.
5. Baseline data: your measured crew-attributable delay/cancellation cost
   (needed to contract on KPIs).

## 10. Roadmap & exit criteria (from the architecture doc)

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 0 (wk 1–4) | Feed ingestion + legality risk radar (read-only) | Scheduler team confirms radar accuracy in a 2-week shadow run |
| 1 (wk 5–14) | Proposal engine + write-back API | ≥50% acceptance of proposals in month 1; zero illegality from our proposals |
| 2 (wk 15–20) | What-if/fatigue + approval hierarchy | What-if used in ≥1 real decision/week; fatigue margins on ≥95% of proposals |
| 3 (21+) | Second jurisdiction/carrier, crew mobile view | Multi-carrier validation; roadmap to full platform |

## 11. Honest limitations (current prototype)

- Synthetic, deterministic 7-day schedule — not your data (the data contract +
  Phase 0 shadow run is exactly the de-risking step).
- Absent-crew coverage gaps (a pairing with no crew at all) are not yet
  flagged as uncovered — only legality-broken crews are.
- Toy fatigue model; EASA Annex III per-duty placeholder; rest variants
  simplified. All flagged, none hidden.

## Appendix — verified limits (primary sources)

- FAR 117 flight time: 100 h / 672 h · 1,000 h / 365 d · duty 60 h / 168 h ·
  190 h / 672 h — [eCFR 14 CFR part 117](https://www.ecfr.gov/current/title-14/chapter-I/subchapter-G/part-117)
- EASA flight time: 100 h / 28 d · 900 h / yr · 1,000 h / 12 mo —
  [EUR-Lex CELEX 32014R0083](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32014R0083)