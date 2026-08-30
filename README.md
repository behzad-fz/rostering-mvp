# Airline Crew Rostering — Modern Platform: Research, Architecture & Prototype

A self-contained project exploring whether a modern airline crew-rostering
platform can beat the legacy incumbents — from market research to a runnable,
stdlib-only prototype of the disruption-recovery wedge.

## Contents

| Path | What it is |
|---|---|
| `pitch-one-pager.md` | Stakeholder/investor one-pager: the problem, the wedge, prototype proof (48/48 coverage closure, ≤0.9 s worst-case), moat, business case, and the 90-day ask. |
| `pitch-technical-cto.md` | Technical brief for a CTO / head of OCC: architecture, integration model, legality/rule-pack detail, solver ladder, performance numbers, reliability posture, pilot engagement and exit criteria. |
| `pitch-speaker-notes.md` | Speaker notes for presenting: timed walkthrough with scripted lines, live-demo talking points, Q&A prep (12 likely questions), and audience-specific tips. |
| `airline-rostering-research.md` | Full opportunity research: the legacy vendor landscape, the scheduling science, regulation/fatigue/labor constraints (with FAR 117 & EASA FTL limits **verified against primary sources**), gap analysis, business case, go-to-market. |
| `recovery-engine-architecture.md` | Build blueprint for the wedge product: cloud-native architecture, rule engine, optimizer design, MVP phases with exit criteria, KPIs, risks, team plan. |
| `rostering-mvp/` | Runnable prototype — see its [`README.md`](rostering-mvp/README.md): synthetic 7-day airline, FAR 117 / EASA-FTL legality engine, disruption simulation, risk radar, and Phase-2 recovery (exact picker + pairing surgery) with JSON + HTML dashboards. |

## Quickstart

```sh
cd rostering-mvp
python3 run_demo.py                # FAR 117 regime, disruption + recovery
python3 run_demo.py --regime EASA-FTL --delay-min 180
python3 bench.py                   # 48-case benchmark / sensitivity sweep
python3 -m unittest discover -s . -p 'test_*.py'   # 47 tests
```

Open `rostering-mvp/out/report_disrupted.html` for the dashboard.

## What the prototype demonstrates

- A **legality engine** over verified FAR 117 / EASA FTL limits — including
  the **exact FAR 117 Table B/C** (fetched from eCFR) and the **exact EASA
  Annex III Table 2** (from the official regulation PDF); remaining
  simplifications (rest variants, EASA Tables 3/4 + extensions, buffers,
  company flight-time guardrail) are flagged in code.
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
- **Benchmark / sensitivity suite** (`rostering-mvp/bench.py`): a 48-case
  sweep across delay size, burst, target mode, cancellations, and 14-day
  scale-ups — coverage closed in every case (0 uncovered), violation-free in
  46/48 (the two most extreme 12 h-delay cases recommend cancellation),
  worst-case recovery ≤0.9 s.

## Status & roadmap

- Phase 0 (detection / risk radar) — done
- Phase 1 (recourse generation) — done (greedy, superseded by Phase 2)
- Phase 2 (exact picker, pairing surgery, relief, deadhead) — done (prototype-grade)
- Exact FAR 117 Table B/C rule pack, what-if/fatigue, feed contract — done
- Benchmark / sensitivity suite (48-case grid incl. 14-day scale-ups, 100%
  coverage closure, ≤0.9 s/case) — done
- Exact EASA Annex III Tables 2/3/4 + verified duty accumulators (60/110/190 h)
  and home-base rest (official PDF committed under `rostering-mvp/docs/`) — done
- CI + packaging (`pyproject.toml`, GitHub Actions workflow, `scripts/check.sh`) — done
- Next: EASA extension schemes (in-flight rest, split duty, reduced-rest),
  a real CBA rule pack, licensed fatigue model integration, OR-Tools/Gurobi
  at scale. See `rostering-mvp/README.md`.

## License

No license chosen yet — this is research/prototype material; decide before
sharing externally.