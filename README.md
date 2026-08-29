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
python3 -m unittest discover -s . -p 'test_*.py'   # 31 tests
```

Open `rostering-mvp/out/report_disrupted.html` for the dashboard.

## What the prototype demonstrates

- A **legality engine** over verified FAR 117 / EASA FTL limits — including
  the **exact FAR 117 Table B/C per-duty FDP tables** (fetched from eCFR);
  remaining simplifications (rest variants, EASA Annex III per-duty scheme,
  buffers, company flight-time guardrail) are flagged in code.
- A **risk radar**: ranked at-risk crews, rule findings with margins,
  uncovered flights, reserve gaps.
- **Recovery that respects legality**: an exact picker over the candidate
  pool, pairing surgery, knock-on relief, and deadhead modeling — applied on a
  copy of the world, it cuts uncovered non-cancelled flights 16 → 0 and
  violating crews 3 → 0 in the demo scenarios, and never proposes anything
  illegal.
- **What-if / fatigue + feed contract**: a scenario evaluator compares
  "do nothing vs. the action plan" (legality, coverage, fatigue), and a
  versioned feed contract is dogfooded by the demo export.

## Status & roadmap

- Phase 0 (detection / risk radar) — done
- Phase 1 (recourse generation) — done (greedy, superseded by Phase 2)
- Phase 2 (exact picker, pairing surgery, relief, deadhead) — done (prototype-grade)
- Exact FAR 117 Table B/C rule pack, what-if/fatigue, feed contract — done
- Next: EASA Annex III per-duty scheme, a real CBA rule pack, licensed fatigue
  model integration, OR-Tools/Gurobi at scale. See `rostering-mvp/README.md`.

## License

No license chosen yet — this is research/prototype material; decide before
sharing externally.