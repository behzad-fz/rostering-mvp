# Disruption Recovery Engine — Phase 0 Prototype

A runnable, stdlib-only (Python 3.9+) prototype of the **legality engine + risk
radar** that opens the *disruption-recovery wedge* described in
[`recovery-engine-architecture.md`](../recovery-engine-architecture.md).

It demonstrates, end to end, the Phase-0 capabilities of the plan:

1. **World model** — a deterministic 7-day synthetic airline (flights,
   pairings, crews, reserves) built by `proto/schedule_gen.py`.
2. **Rule engine** — FAR 117 and EASA-FTL regimes with **verified cumulative
   limits** and clearly-marked approximations for per-duty tables.
3. **Legality evaluation** — per-crew duty timelines + accumulator checks.
4. **Disruption simulation** — delays with propagation through pairings,
   plus cancellations.
5. **Risk radar** — ranked at-risk crews, uncovered flights, reserve gaps.
6. **Reports** — `out/report.json`, plus self-contained dark dashboards
   (`out/report_baseline.html`, `out/report_disrupted.html`).
7. **Recovery proposals** (Phase 1/2) — legality-validated reserve callouts
   and crew swaps chosen by an **exact CP-style picker** over the whole
   candidate pool (each crew used at most once), plus **pairing surgery** that
   splits over-long pairings so the broken crew keeps a legal prefix and a
   fresh crew takes the suffix. Applied on a copy of the world to measure how
   many gaps close.

## Run it

```sh
python3 run_demo.py                 # FAR 117 regime (default)
python3 run_demo.py --regime EASA-FTL --delay-min 180
python3 run_demo.py --days 7 --seed 42
```

Tests (17 across `test_rules.py` + `test_recovery.py`):

```sh
python3 -m unittest discover -s . -p 'test_*.py'
```

## What you'll see

The synthetic schedule is *mostly* legal, with baked-in findings the radar
should surface:

- `P-SFO-0` — a long 4-leg duty (report 05:00 → ends 17:15) → **FDP violation**
  before any disruption; the day-2 SFO delay pushes it further over.
- `P-SFO-1` — a near-max duty (margin +15 min) → **at risk**; the delay can
  tip it into violation.
- `P-SFO-3` — pre-existing flight-time accumulator at 99 h/28 d → the 100 h
  cap trips.
- `P-LAX-2` — pre-existing duty accumulator at 59 h/7 d → the 60 h cap trips.
- One cancelled return flight → **uncovered flight + reserve-gap** line.
- **Recovery proposals** for the gaps: the picker allocates reserve callouts
  (and a swap when day-3 reserves conflict) across all five fixable gaps;
  pairing surgery splits the over-long X pairing (P-SFO-0 keeps legs 1–2,
  P-SFO-4 covers legs 3–4). Applying the seven proposals cuts uncovered
  non-cancelled flights 14 → 0 and violating crews 3 → 0. The tricky case —
  two broken crews sharing one pairing — is closed by a **release**: P-SFO-3
  is taken off the pairing (which stays covered by the reserve) so her
  accumulator exposure heals without double-crewing anyone.

## Verified vs. approximated rules

**Verified against primary sources** (see `airline-rostering-research.md` §5.1):

| Rule | Verified value |
|---|---|
| FAR 117 flight time | 100 h / 672 h · **1,000 h / 365 d** |
| FAR 117 duty | 60 h / 168 h · 190 h / 672 h |
| EASA FTL flight time | 100 h / 28 d · 900 h / year · 1,000 h / 12 mo |

**Approximations (flagged in code — verify before production):** per-duty FDP
table (FAR 117 Table B trend), minimum rest (10 h / 12 h), report & debrief
buffers (60 / 15 min), per-FDP flight-time cap (8 h / 9 h), EASA duty
accumulators. The eCFR API was rate-limiting during this build; re-fetch
`14 CFR part 117` tables (`/api/versioner/v1/full/<date>/title-14.xml?part=117`)
and encode the real Table B/C cells.

## Layout

```
rostering-mvp/
  run_demo.py            # end-to-end demo runner
  test_rules.py          # hand-computed unit tests
  proto/
    __init__.py
    model.py             # Flight/Crew/Pairing/DutyEvent/World
    timeutil.py          # day+minute time helpers
    rules.py             # RuleEngine (FAR117 | EASA-FTL)
    schedule_gen.py      # deterministic synthetic schedule
    legality.py          # duties + evaluate()
    disrupt.py           # delay/cancellation + propagation
    risk.py              # risk scores, uncovered flights, reserve gaps
    report.py            # JSON + HTML dashboards
  out/                   # generated reports (gitignore-able)
```

## Implemented vs. next

**Implemented (Phase 2 core):**
- **Exact CP-style picker** (`solve_picker` in `proto/recovery.py`) — one
  action per gap, each crew used at most once, maximizing covered gaps then
  minimizing action score. Deterministic branch-and-bound; tiny instances run
  in milliseconds. For production scale, swap the DFS for a real MIP/CP engine
  (OR-Tools, Gurobi) — the interface is the same.
- **Pairing surgery** (`find_surgery`) — splits an over-long pairing at leg
  boundary k; the legality-broken crew keeps a legal prefix and a fresh
  crew (reserve/swap) takes the suffix. This turned the previously *refused*
  X-long case into a fixable proposal.
- **Knock-on / shared-pairing relief** (`secondary_relief`) — after the main
  selection, crews still in violation (the second broken crew on a
  double-crewed pairing, or a crew overloaded by a swap) are relieved:
  release-without-replacement when the pairing is already covered, else
  re-crew with a legality-clean taker. Validated end-to-end: the relieved crew
  must heal, the taker must stay fully legal, and no previously-ok crew may
  break.

**Next:**
- **Deadhead / reposition actions** with cost modeling once reserves run out
  at the affected base.
- **Real rule packs** — encode actual FAR 117 Table B/C and a carrier's CBA as
  versioned, regression-tested rule packs (re-fetch eCFR when rate limits
  clear: `/api/versioner/v1/full/<date>/title-14.xml?part=117`).
- **Data contract** — replace `schedule_gen` with the feed-adapters spec from
  the architecture document (SFTP/file/API adapters, per-feed staleness).
- **What-if / fatigue** — fork the world model, roll forward, and surface
  fatigue-model margins (bio-mathematical model integration point).