# Disruption Recovery Engine — Phase 0 Prototype

A runnable, stdlib-only (Python 3.9+) prototype of the **legality engine + risk
radar** that opens the *disruption-recovery wedge* described in
[`recovery-engine-architecture.md`](../recovery-engine-architecture.md).

It demonstrates, end to end, the Phase-0 capabilities of the plan:

1. **World model** — a deterministic 7-day synthetic airline (flights,
   pairings, crews, reserves) built by `proto/schedule_gen.py`.
2. **Rule engine** — FAR 117 and EASA-FTL regimes with **verified cumulative
   limits** and the **exact FAR 117 Table B/C** per-duty FDP tables (eCFR,
   2025-01-01); remaining simplifications are clearly flagged.
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
8. **What-if & fatigue** — a scenario evaluator compares *do nothing vs. the
   action plan* (legality + coverage + reserve usage + fatigue), and a
   documented toy fatigue model (night duty, early starts, long days, short
   rests) flags sustained-load crews; the real SAFTE/FAID/FAST-class model is
   the integration point.
9. **Feed contract** — `contract/README.md` specifies what a carrier's
   adapters must push in; `run_demo.py` dogfoods it by exporting
   `out/contract_sample.json` and validating it.

## Run it

```sh
python3 run_demo.py                 # FAR 117 regime (default)
python3 run_demo.py --regime EASA-FTL --delay-min 180
python3 run_demo.py --days 7 --seed 42
```

Tests (40 across `test_rules.py` + `test_recovery.py` + `test_extras.py` +
`test_bench.py`):

```sh
python3 -m unittest discover -s . -p 'test_*.py'
```

## Packaging & CI

- `pyproject.toml` — installable (`pip install -e .` → `rostering-demo` and
  `rostering-bench` console commands). License is **proprietary / unlicensed**
  until you choose one.
- `.github/workflows/ci.yml` (repo root) — Python 3.9 + 3.12: unit tests,
  benchmark smoke grid, install + CLI smoke, on every push/PR.
- `../scripts/check.sh` — the same checks locally without pip.
- `docs/` — committed legal sources for provenance: the official Regulation
  (EU) 83/2014 PDFs (EUR-Lex OJ + TXT export) and the extracted Annex III
  text used for the EASA Table 2 encoding.

## What you'll see

The synthetic schedule is *mostly* legal, with baked-in findings the radar
should surface:

- `P-SFO-0` — a long 4-leg duty reporting at 03:00 (→ ends 16:25, ~13 h 25 m
  vs the **9 h** limit from exact Table B at 0000-0359) → **FDP violation**
  before any disruption; the day-2 SFO delay slides the rotation and the
  violation survives into the 0500-0559 band (12 h limit).
- `P-SFO-1` — a near-max duty (margin +45 min vs exact Table B 0600-0659,
  3 segments, 12 h limit) → **at risk**; the delay can tip it into violation.
- `P-SFO-3` — pre-existing flight-time accumulator at 99 h/28 d → the 100 h
  cap trips.
- `P-LAX-2` — pre-existing duty accumulator at 59 h/7 d → the 60 h cap trips.
- One cancelled return flight → **uncovered flight + reserve-gap** line.
- **Recovery proposals** for the gaps: the picker allocates reserve callouts
  and swaps across six pairings; pairing surgery splits the over-long X
  pairing (P-SFO-0 keeps legs 1–2, a fresh crew covers legs 3–4); a release
  heals the second crew on the shared pairing. Applying the proposals cuts
  uncovered non-cancelled flights 16 → 0 and violating crews 3 → 0 in both
  the baseline and disrupted scenarios.
- **What-if** confirms the plan: do nothing leaves 3 violations / 16 uncovered;
  the plan takes both to zero (with reserve callouts, fatigue stats, and the
  most-loaded crews listed on the dashboard).

## Verified vs. approximated rules

**Verified against primary sources** (see `airline-rostering-research.md` §5.1):

| Rule | Verified value |
|---|---|
| FAR 117 flight time | 100 h / 672 h · **1,000 h / 365 d** |
| FAR 117 duty | 60 h / 168 h · 190 h / 672 h |
| FAR 117 per-duty FDP | **exact Table B/C** (eCFR, version 2025-01-01) |
| EASA FTL flight time | 100 h / 28 d · 900 h / year · 1,000 h / 12 mo |
| EASA per-duty FDP | **exact Annex III Table 2** (max daily FDP, acclimatised — Reg (EU) 83/2014) |

**Remaining simplifications (flagged in code):** minimum-rest variants (the
10 h standard is modeled; FAR 117.25 reduced-rest conditions are not), report &
debrief buffers (60 / 15 min), the company flight-time guardrail
(`co.ft-per-fdp` — *not* a FAR 117 limit), EASA duty accumulators, and the
EASA Annex III Tables 3/4 (unknown acclimatisation / FRM) plus the extension
schemes (+1 h twice per 7 days, in-flight rest, split duty).

## Benchmark & sensitivity (`bench.py`)

```sh
python3 bench.py            # 46-case grid (~10 s): bank delays up to 12 h,
                            # targeted legality-critical stress, double-cancel
python3 bench.py --quick    # smoke grid (~3 s)
python3 bench.py --single --delay 480 --burst 8   # one case
```

**Results (this build):** 46/46 cases fully closed — do-nothing damage spans up
to **38 uncovered flights / 10 violating crews** (12-hour SFO bank delays); the
action plan takes every case to **0 uncovered, 0 violations** using
reserve/swap/surgery/release. Mean runtime **213 ms**, worst **530 ms** (was
7.6 s before the picker node-cap: extreme states cap the search at 250 k nodes
and still close 100% — flagged as `picker.capped`). Outputs:
`out/bench_results.json` + `out/bench_report.html`.

**Two findings the sweep surfaced:** (1) the day-trip world has enough slack
that delays up to ~5 h rarely breach legality — legality pressure only appears
under 8-12 h slides or when a delay extends a *specific* crew's duty end;
(2) recovery cost grows with damage size (the DFS picker's search tree), which
is the argument for the OR-Tools/Gurobi swap at production scale.

## Layout

```
rostering-mvp/
  run_demo.py            # end-to-end demo runner
  bench.py               # benchmark / sensitivity sweep (46-case grid)
  test_rules.py          # rule-engine unit tests
  test_recovery.py       # recovery (picker/surgery/relief/deadhead) tests
  test_extras.py         # fatigue / what-if / contract tests
  test_bench.py          # benchmark harness tests
  contract/
    README.md            # feed-adapters data contract (v1.0 draft)
  proto/
    __init__.py
    model.py             # Flight/Crew/Pairing/DutyEvent/World
    timeutil.py          # day+minute time helpers
    rules.py             # RuleEngine (FAR117 | EASA-FTL) — exact Table B/C
    schedule_gen.py      # deterministic synthetic schedule (+staffing sweep)
    legality.py          # duties + evaluate()
    disrupt.py           # delay slide w/ min-turn floor, cancellations
    risk.py              # risk scores, uncovered flights, reserve gaps
    recovery.py          # exact picker, surgery, relief, deadhead
    fatigue.py           # toy duty-intensity model (documented weights)
    foresight.py         # what-if scenario evaluator
    contract.py          # feed-contract export + validation
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
- **Deadhead / reposition actions** — when a base has neither reserve nor a
  legal local swap, a legality-clean crew from another base can reposition:
  travel + operated duty modeled as one combined duty (as most FTL regimes
  treat deadhead). Priced by travel minutes (score 40 + travel/60), so the
  picker only chooses it as a last resort. Proven by a micro-world test where
  it is the *only* legal option; in the standard demo it is correctly never
  chosen because local options always suffice.
- **What-if & fatigue** (`proto/foresight.py`, `proto/fatigue.py`) — fork the
  world, apply or skip the plan, compare legality/coverage/fatigue; the fatigue
  model is deliberately a *toy* (documented weights) — swap it for a licensed
  SAFTE/FAID/FAST-class model via the same interface.
- **Feed contract** (`contract/README.md`, `proto/contract.py`) — versioned
  contract for planned/operational/crew/reserve feeds; the demo exports and
  validates a conformant sample (`out/contract_sample.json`), so a carrier's
  adapters have a concrete target to match.

**Next:**
- **EASA Annex III per-duty scheme** — encode from EUR-Lex when access is
  restored (bot-blocked last attempt); currently a documented flat 13 h
  placeholder. The verified EASA *cumulative* limits are already exact.
- **A real CBA rule pack** (seniority, custom bidding credits, reserve rules)
  as a versioned, regression-tested constraint pack.
- **Licensed fatigue model integration** and **OR-Tools/Gurobi** for the
  picker at production scale.