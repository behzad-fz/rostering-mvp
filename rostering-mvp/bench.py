#!/usr/bin/env python3
"""Benchmark / sensitivity sweep for the recovery engine.

Runs the full pipeline (world -> disruption -> radar -> recovery -> what-if)
across a deterministic grid of disruption scenarios and reports how well the
recovery plan closes each one:

  - do nothing vs. plan (violations, at-risk, uncovered, fatigue)
  - action mix (reserve / swap / surgery / relief / deadhead)
  - picker cost (covered gaps, explored nodes)
  - wall-clock runtime per case

Usage:
    python3 bench.py               # full grid (FAR117 + EASA-FTL, ~80 cases)
    python3 bench.py --quick       # small smoke grid
    python3 bench.py --out out     # writes out/bench_results.json + bench_report.html
    python3 bench.py --regime FAR117 --delay 180 --base SFO --day 2 --burst 8 --cancels 1
"""
import argparse
import html
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proto.disrupt import apply_cancellation, apply_delay          # noqa: E402
from proto.fatigue import FatigueModel                            # noqa: E402
from proto.foresight import scenario                              # noqa: E402
from proto.legality import evaluate                               # noqa: E402
from proto.recovery import generate                               # noqa: E402
from proto.rules import RuleEngine                                # noqa: E402
from proto.schedule_gen import build_world                        # noqa: E402

EXECUTABLE = ("reserve", "swap", "surgery", "relieve", "deadhead", "cancel")


# ------------------------------------------------------------- disruption
def pick_burst(w, base: str, day: int, burst: int, min_hour: int = 5,
               max_hour: int = 22):
    flights = [f for f in w.flights
               if f.day == day and f.origin == base
               and min_hour * 60 <= (f.dep % 1440) <= max_hour * 60]
    return [f.id for f in sorted(flights, key=lambda f: f.dep)[:burst]]


def run_case(regime: str, mode: str, delay: int, base: str, day: int,
             burst: int, cancels: int, days: int = 7) -> dict:
    t0 = time.perf_counter()
    w = build_world(days=days)
    engine = RuleEngine(regime)

    if delay > 0:
        if mode == "targeted":
            # stress the legality-critical crews by extending the END of their
            # duty (delaying only each pairing's last leg — a full-rotation
            # delay would slide the start band later and compensate)
            ids = []
            for pid in ("X-long-2", "Y-long-3"):
                p = w.pairing(pid)
                ids.append(p.flight_ids[-1])
            apply_delay(w, ids, delay)
        elif burst > 0:
            ids = pick_burst(w, base, day, burst)
            apply_delay(w, ids, delay)
    if cancels:
        cand = [f for f in w.flights
                if f.day == day and f.dest == base and f.origin != base]
        for f in sorted(cand, key=lambda f: f.dep)[:cancels]:
            apply_cancellation(w, f.id)

    checks = evaluate(w, engine)
    proposals, outcome = generate(w, engine, checks)
    fatigue = FatigueModel()
    dn = scenario(w, engine, None, "do nothing", fatigue)
    pl = scenario(w, engine, proposals, "plan", fatigue)

    kinds = [p["kind"] for p in proposals if p["kind"] in EXECUTABLE]
    runtime_ms = round((time.perf_counter() - t0) * 1000, 1)

    def slim(s):
        return {"violations": s["violations"], "at_risk": s["at_risk"],
                "uncovered": s["uncovered"], "fatigue_mean": s["fatigue"]["mean"],
                "cancellations": s.get("cancellations", 0)}

    return {
        "case": f"{regime}/{mode}/{base}/D{day}/d{delay}/b{burst}/x{cancels}/w{days}",
        "regime": regime, "mode": mode, "base": base, "day": day,
        "delay_min": delay, "burst": burst, "cancels": cancels,
        "do_nothing": slim(dn), "plan": slim(pl),
        "violations_closed": dn["violations"] - pl["violations"],
        "uncovered_closed": dn["uncovered"] - pl["uncovered"],
        "closure_pct": round(100 * (dn["uncovered"] - pl["uncovered"])
                             / max(dn["uncovered"], 1), 1),
        "actions": len(kinds),
        "reserve_share": round(100 * kinds.count("reserve") / max(len(kinds), 1), 0),
        "picker": outcome["picker"],
        "runtime_ms": runtime_ms,
    }


# ------------------------------------------------------------------ grid
def build_grid(quick: bool = False):
    """Deterministic case grid. Mode 'bank' = delay the morning bank at a
    base (burst capped by flights available); mode 'targeted' = delay the
    legality-critical injected crews directly (X-long-2 / Y-long-3)."""
    grid = []
    regimes = ["FAR117"]
    bases, days = ["SFO", "LAX"], [2, 4]
    delays = [90, 180, 300] if quick else [90, 180, 300, 480, 720]
    for regime in regimes:
        grid.append((regime, "bank", 0, "SFO", 2, 0, 0))          # control
        for base in bases:
            for day in days:
                for delay in delays:
                    for burst in ([3, 6] if quick else [3, 8]):
                        grid.append((regime, "bank", delay, base, day, burst, 1))
        for delay in ([60, 180] if quick else [30, 60, 120, 240]):
            grid.append((regime, "targeted", delay, "SFO", 2, 0, 1))
        grid.append((regime, "bank", 300, "LAX", 2, 8, 2))         # double-cancel
        # scale-up: 14-day horizons on the legality-critical day
        grid.append((regime, "bank", 300, "SFO", 2, 8, 1, 14))
        grid.append((regime, "bank", 480, "LAX", 4, 8, 1, 14))
    return grid


# --------------------------------------------------------------- summary
def summarize(results: list) -> dict:
    closures = [r["closure_pct"] for r in results]
    unresolved = [r["plan"]["uncovered"] for r in results]
    runtimes = [r["runtime_ms"] for r in results]
    return {
        "cases": len(results),
        "mean_closure_pct": round(statistics.mean(closures), 1),
        "median_closure_pct": round(statistics.median(closures), 1),
        "worst_uncovered_remaining": max(unresolved),
        "total_uncovered_before": sum(r["do_nothing"]["uncovered"] for r in results),
        "total_uncovered_after": sum(unresolved),
        "total_actions": sum(r["actions"] for r in results),
        "mean_runtime_ms": round(statistics.mean(runtimes), 1),
        "max_runtime_ms": max(runtimes),
    }


# ----------------------------------------------------------------- emit
def emit_reports(results: list, summary: dict, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "bench_results.json"), "w") as fh:
        json.dump({"summary": summary, "results": results}, fh, indent=2)

    cards = [
        ("Cases", summary["cases"]), ("Mean closure", f"{summary['mean_closure_pct']}%"),
        ("Uncovered before/after", f"{summary['total_uncovered_before']} → "
                                   f"{summary['total_uncovered_after']}"),
        ("Total actions", summary["total_actions"]),
        ("Mean runtime", f"{summary['mean_runtime_ms']} ms"),
    ]
    card_html = "".join(
        f'<div class="card"><div class="num">{c[1]}</div><div class="lab">{c[0]}</div></div>'
        for c in cards)

    rows = []
    for r in results:
        cls = "b-ok" if r["plan"]["violations"] == 0 else "b-bad"
        rows.append(
            f'<tr class="{cls}"><td>{html.escape(r["case"])}</td>'
            f'<td>{r["do_nothing"]["violations"]}</td><td>{r["do_nothing"]["uncovered"]}</td>'
            f'<td>{r["plan"]["violations"]}</td><td>{r["plan"]["uncovered"]}</td>'
            f'<td>{r["closure_pct"]}%</td><td>{r["actions"]}</td>'
            f'<td>{r["reserve_share"]:.0f}%</td>'
            f'<td>{r["picker"]["covered"]}</td><td>{r["runtime_ms"]}</td></tr>')
    table = "\n".join(rows)

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Recovery Engine — Benchmark</title>
<style>
:root {{ color-scheme: dark; }}
body {{ font: 14px/1.45 -apple-system, "Segoe UI", Roboto, sans-serif; background:#0d1117; color:#e6edf3; margin:24px; }}
h1 {{ font-size:20px; }} h2 {{ font-size:15px; margin-top:26px; border-bottom:1px solid #21262d; padding-bottom:6px; }}
.cards {{ display:flex; gap:12px; flex-wrap:wrap; margin:14px 0; }}
.card {{ background:#161b22; border:1px solid #21262d; border-radius:10px; padding:12px 18px; text-align:center; }}
.card .num {{ font-size:22px; font-weight:700; }} .card .lab {{ color:#8b949e; font-size:11px; }}
table {{ border-collapse:collapse; width:100%; font-size:12px; margin:8px 0; }}
th, td {{ border:1px solid #21262d; padding:5px 8px; text-align:left; }}
th {{ background:#161b22; color:#8b949e; font-size:10px; text-transform:uppercase; }}
.b-ok td:first-child {{ color:#3fb950; }} .b-bad td:first-child {{ color:#f85149; }}
.note {{ background:#121d2f; border:1px solid #1f3a5f; border-radius:8px; padding:10px 14px; font-size:12px; color:#8fb7e8; margin-top:20px; }}
</style></head><body>
<h1>Disruption Recovery Engine — Benchmark &amp; Sensitivity</h1>
<div class="cards">{card_html}</div>
<h2>Cases (regime / base / day / delay / burst / cancels)</h2>
<table>
<tr><th>Case</th><th>DN viol</th><th>DN uncov</th><th>Plan viol</th><th>Plan uncov</th>
<th>Closure</th><th>Actions</th><th>Reserve share</th><th>Gaps covered</th><th>ms</th></tr>
{table}
</table>
<div class="note"><b>Setup.</b> Deterministic synthetic world (7 days; two scale-up cases run 14-day
horizons — note the <code>w14</code> suffix). Disruption = delay <code>burst</code> flights of
<code>base</code> on <code>day</code> by <code>delay_min</code> (rotation slide), plus <code>cancels</code>
cancellations. Do-nothing (DN) vs. legality-validated action plan (violations forbidden;
at-risk takers permitted and surfaced). Rules: exact FAR 117 (eCFR). Toy fatigue model.
Cases where no legal crewing option exists recommend cancellation (counted in the JSON).
Runtimes include world build + full recovery + what-if.</div>
</body></html>"""
    with open(os.path.join(out_dir, "bench_report.html"), "w") as fh:
        fh.write(doc)
    print("benchmark written to", os.path.join(out_dir, "bench_results.json"),
          "and", os.path.join(out_dir, "bench_report.html"))


# ---------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description="Benchmark / sensitivity sweep")
    ap.add_argument("--quick", action="store_true", help="small smoke grid")
    ap.add_argument("--out", default="out")
    ap.add_argument("--single", action="store_true",
                    help="run one case from --regime/--mode/--delay/--base/--day/--burst/--cancels")
    ap.add_argument("--regime", default="FAR117")
    ap.add_argument("--mode", default="bank", choices=["bank", "targeted"])
    ap.add_argument("--delay", type=int, default=180)
    ap.add_argument("--base", default="SFO")
    ap.add_argument("--day", type=int, default=2)
    ap.add_argument("--burst", type=int, default=8)
    ap.add_argument("--cancels", type=int, default=1)
    args = ap.parse_args()

    if args.single:
        grid = [(args.regime, args.mode, args.delay, args.base, args.day,
                 args.burst, args.cancels)]
    else:
        grid = build_grid(quick=args.quick)

    results = [run_case(*case) for case in grid]
    summary = summarize(results)

    print(f"{'CASE':<34}{'DN':>9}{'PLAN':>9}{'CLOS':>7}{'ACT':>5}{'MS':>8}")
    for r in results:
        print(f"{r['case']:<34}"
              f"{r['do_nothing']['uncovered']:>4}/{r['do_nothing']['violations']}"
              f"{r['plan']['uncovered']:>5}/{r['plan']['violations']}"
              f"{str(r['closure_pct']) + '%':>6}"
              f"{r['actions']:>6}{r['runtime_ms']:>8.0f}")
    print("\nsummary:", json.dumps(summary, indent=2))
    # the quick smoke grid must never clobber the canonical full-grid report
    # (scripts/check.sh runs --quick; the pitch numbers reference the full run)
    emit_reports(results, summary, args.out + ("_quick" if args.quick else ""))


if __name__ == "__main__":
    main()