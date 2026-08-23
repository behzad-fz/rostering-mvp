# Airline Crew Rostering — Modern Platform: Research, Architecture & Prototype

A self-contained project exploring whether a modern airline crew-rostering
platform can beat the legacy incumbents — from market research to a runnable,
stdlib-only prototype of the disruption-recovery wedge.

## Contents

| Path | What it is |
|---|---|
| `airline-rostering-research.md` | Full opportunity research: the legacy vendor landscape, the scheduling science, regulation/fatigue/labor constraints (with FAR 117 & EASA FTL limits **verified against primary sources**), gap analysis, business case, go-to-market. |
| `recovery-engine-architecture.md` | Build blueprint for the wedge product: cloud-native architecture, rule engine, optimizer design, MVP phases with exit criteria, KPIs, risks, team plan. |
| `rostering-mvp/` | Runnable prototype — see its [`README.md`](rostering-mvp/README.md): synthetic 7-day airline, FAR 117 / EASA-FTL legality engine, disruption simulation, risk radar, and Phase-2 recovery (exact picker + pairing surgery) with JSON + HTML dashboards. |

## Quickstart

```sh
cd rostering-mvp
python3 run_demo.py                # FAR 117 regime, disruption + recovery
python3 run_demo.py --regime EASA-FTL --delay-min 180
python3 -m unittest discover -s . -p 'test_*.py'   # 14 tests
```

Open `rostering-mvp/out/report_disrupted.html` for the dashboard.

## What the prototype demonstrates

- A **legality engine** over cumulative limits verified from primary sources,
  with clearly-marked approximations for per-duty tables.
- A **risk radar**: ranked at-risk crews, rule findings with margins,
  uncovered flights, reserve gaps.
- **Recovery that respects legality**: an exact picker over the candidate
  pool and pairing surgery — applied on a copy of the world, it cuts
  uncovered non-cancelled flights 14 → 2 and violating crews 3 → 1 in the
  demo scenario, and never proposes anything illegal.

## Status & roadmap

- Phase 0 (detection / risk radar) — done
- Phase 1 (recourse generation) — done (greedy, superseded)
- Phase 2 (exact picker + pairing surgery) — done (prototype-grade)
- Next: deadhead modeling, shared-pairing relief, real rule packs (FAR 117
  Table B/C, a carrier's CBA), feed-adapters data contract, what-if/fatigue.
  See `rostering-mvp/README.md` for details.

## License

No license chosen yet — this is research/prototype material; decide before
sharing externally.