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
| 54 automated tests pass | `unittest discover` above | `Ran 54 tests ... OK` |
| Demo: 3 violating crews → 0, uncovered 16 → 0 | `python3 run_demo.py` (what-if section) | plan: violations=0, uncovered=0 |
| Benchmark: 48 cases, coverage closed everywhere | `python3 bench.py` → `out/bench_results.json` (the quick smoke grid writes to `out_quick/` so it never clobbers the canonical file) | `summary.total_uncovered_after == 0`, `"cases": 48` |
| Violation-free plans in 46/48 | same JSON | exactly 2 cases with `plan.violations > 0` (`.../d720/...`), each with a `cancel`-kind proposal |
| Worst-case recovery ≤1.0 s | `max_runtime_ms` in the JSON | ≤ 1000 ms (14-day scale-up cases; ~171 ms mean) |
| FAR 117 tables exact (eCFR) | `test_rules.py::TestExactTables` + `TestEasaTable` | spot-values locked against the fetched values |
| EASA Annex III Tables 2/3/4 exact | `TestEasaTable` (values from the official PDF) | spot-values locked (e.g. 09:00 start, 2 sectors = 780 min) |
| EASA duty accumulators 60/110/190 h + ft-12mo | `TestEasa.*` + `TestAuditFixes.test_ft_12mo_accumulator` | verified from ORO.FTL.210 text |
| No proposal is ever illegal | property tests `TestRecovery.test_proposals_nonempty_and_legal`, `TestBench.test_plan_never_worse_than_do_nothing_across_quick_grid` | pass |
| Audit-fix regressions | `TestAuditFixes` (dashboard escaping, contract cross-refs, unacclimated Table 3, ft-12mo, reason breakdown), `TestDeadheadTravel` (real block distances), `TestCancel`, `TestSurgeryFirst`, `TestNoCrew` | pass |

## Rule-value provenance

- **FAR 117** (14 CFR part 117): fetched from the eCFR XML API,
  `full/2025-01-01/title-14.xml?part=117`; Tables B/C encoded verbatim in
  `proto/rules.py` (`TABLE_B`, `TABLE_C`); cumulative limits in `FAR117_PARAMS`.
  An offline snapshot of the fetched XML is committed at
  `docs/far117-part-117-2025-01-01.xml` when eCFR access allows (the API was
  rate-limiting during some sessions — the encoding is test-locked either way;
  re-verify against a fresh fetch before pilot use).
  *Note on Table C:* an external review asserted different start-time bands
  (13:00-17:59 / 18:00-23:59); the bands in `TABLE_C` (…17:00-23:59) are the
  values literally printed by the eCFR 2025-01-01 XML this project fetched
  (see the committed snapshot / re-fetch): `0000-0559`, `0600-0659`,
  `0700-1259`, `1300-1659`, `1700-2359`. Spot-locks in `TestExactTables`.
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