# Verification — how to check every claim in this repository

Everything in the pitch documents is reproducible from this repo. This file
tells you exactly how to re-run each claim and what the expected result is.

## Quick checks (local)

```sh
cd rostering-mvp
python3 -m unittest discover -s . -p 'test_*.py'   # 47 tests, all pass
python3 run_demo.py                                # FAR 117 demo
python3 run_demo.py --regime EASA-FTL              # EASA demo
python3 bench.py                                   # 48-case benchmark grid
```

## Claimed numbers and how they are produced

| Claim | How to verify | Expected |
|---|---|---|
| 47 automated tests pass | `unittest discover` above | `Ran 47 tests ... OK` |
| Demo: 3 violating crews → 0, uncovered 16 → 0 | `python3 run_demo.py` (what-if section) | plan: violations=0, uncovered=0 |
| Benchmark: 48 cases, coverage closed everywhere | `python3 bench.py` → `out/bench_results.json` | `summary.total_uncovered_after == 0`, `"cases": 48` |
| Violation-free plans in 46/48 | same JSON | exactly 2 cases with `plan.violations > 0` (`.../d720/...`), each with a `cancel`-kind proposal |
| Worst-case recovery ≤0.9 s | `max_runtime_ms` in the JSON | ≤ 900 ms (14-day scale-up cases) |
| FAR 117 tables exact (eCFR) | `test_rules.py::TestExactTables` + `TestEasaTable` | spot-values locked against the fetched values |
| EASA Annex III Table 2 exact | `TestEasaTable` (values from the official PDF) | spot-values locked (e.g. 09:00 start, 2 sectors = 780 min) |
| EASA duty accumulators 60/110/190 h | `TestEasa.test_14d_duty_cap` + engine params | verified from ORO.FTL.210 text |
| No proposal is ever illegal | property tests `TestRecovery.test_proposals_nonempty_and_legal`, `TestBench.test_plan_never_worse_than_do_nothing_across_quick_grid` | pass |

## Rule-value provenance

- **FAR 117** (14 CFR part 117): fetched from the eCFR XML API,
  `full/2025-01-01/title-14.xml?part=117`; Tables B/C encoded verbatim in
  `proto/rules.py` (`TABLE_B`, `TABLE_C`); cumulative limits in `FAR117_PARAMS`.
- **EASA FTL** (Regulation (EU) No 83/2014): official EUR-Lex PDFs committed
  under `docs/` (`Regulation - 83_2014 - EN - EUR-Lex.pdf`,
  `CELEX_32014R0083_EN_TXT.pdf`); Annex III Table 2 / Tables 3-4 and the
  ORO.FTL.210 duty limits + ORO.FTL.235 rest periods were extracted from the
  PDF text (`docs/easa-ftl-annex-iii-extracted.txt`) and encoded in
  `EASA_TABLE2/3/4` and `EASA_PARAMS`.

## Understanding the honest limits

1. **Synthetic data.** The demo world is generated, deterministic, and small
   (4 bases, 7 days; two 14-day scale-up cases in the bench). Real-carrier
   validation is the Phase 0 shadow run.
2. **Two extreme cases recommend cancellation.** Under 12-hour delays on legs
   that slide through the legality-critical pairing, *no* legally-crewable
   option exists; the engine says so explicitly (`cancel` proposal) and the
   truncated crew duty remains flagged. That is a feature, not a bug.
3. **At-risk is not a violation.** Proposals may place a crew inside the
   60-minute comfort margin (at-risk); the margin is surfaced, never hidden.
4. **Simplifications flagged in code:** rest variants (FAR 117.25 reduced
   rest; EASA away-from-base/recovery rest), report/debrief buffers, the
   company flight-time guardrail (`co.ft-per-fdp`), EASA extension schemes,
   and the toy fatigue model.

## Reproducibility

- Python ≥ 3.9, **stdlib only** — no third-party packages required.
- Deterministic: fixed world, fixed grids, seeded-free generation; the picker
  node cap can trade optimality for time, never legality (flagged `capped`).
- CI (`.github/workflows/ci.yml`) runs the unit tests + bench smoke + install
  on every push for Python 3.9 and 3.12.