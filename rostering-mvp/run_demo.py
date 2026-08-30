#!/usr/bin/env python3
"""Run the Phase-0 demo end-to-end:

  1. Build a deterministic 7-day synthetic airline world.
  2. Evaluate baseline legality (RuleEngine) — expect a few baked-in
     violations/at-risk crews.
  3. Simulate a disruption (delay the SFO morning bank + cancel one return).
  4. Re-evaluate, rank risk, find uncovered flights and reserve gaps.
  5. Emit out/report.json, out/report_baseline.html, out/report_disrupted.html.

Usage:
    python3 run_demo.py [--days 7] [--seed 42] [--regime FAR117|EASA-FTL]
                        [--delay-min 150]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proto.contract import to_contract_json, validate_contract    # noqa: E402
from proto.disrupt import apply_cancellation, apply_delay          # noqa: E402
from proto.fatigue import FatigueModel                            # noqa: E402
from proto.foresight import whatif                                # noqa: E402
from proto.legality import evaluate                                # noqa: E402
from proto.recovery import generate                                # noqa: E402
from proto.report import emit_html, emit_json, snapshot            # noqa: E402
from proto.risk import rank_crews, uncovered_flights               # noqa: E402
from proto.rules import AT_RISK_MIN, RuleEngine                    # noqa: E402
from proto.schedule_gen import build_world                         # noqa: E402
from proto.timeutil import tod                               # noqa: E402


def pick_targets(w, day: int, origin: str, max_hour: int):
    return [f for f in w.flights
            if f.day == day and f.origin == origin and (f.dep % 1440) < max_hour * 60]


def print_radar(label, snap):
    s = snap["summary"]
    print(f"\n=== {label} ===")
    print(f"  crews={s['crews']} flights={s['flights']} duties={s['duties']} | "
          f"OK={s['ok']} at-risk={s['at_risk']} violations={s['violations']} "
          f"uncovered={s['uncovered']}")
    print("  rule breakdown:", s["rule_breakdown"])
    print("  top risk crews:")
    for c in snap["crews"][:8]:
        print(f"    {c['id']:<12} {c['worst']:<9} score={c['score']:<6} "
              f"margin={c['min_margin_min']:+.0f}m  {c['violations'][0]['message'] if c['violations'] else ''}")
    if snap["uncovered"]:
        print("  uncovered flights:")
        for u in snap["uncovered"]:
            print(f"    {u['id']} D{u['day']} {u['from']}->{u['to']} [{u['reason']}]")
    if snap["gaps"]:
        print("  reserve gaps:")
        for k, v in snap["gaps"].items():
            print(f"    {k}: {len(v)} -> {v[0]}")


def main():
    ap = argparse.ArgumentParser(description="Phase-0 legality engine + risk radar demo")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--regime", choices=["FAR117", "EASA-FTL"], default="FAR117")
    ap.add_argument("--delay-min", type=int, default=150)
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    engine = RuleEngine(args.regime)
    w = build_world(days=args.days, seed=args.seed)

    # ---- baseline -------------------------------------------------------
    base_checks = evaluate(w, engine)
    base_snap = snapshot(w, base_checks, args.regime)
    print_radar("BASELINE (pre-disruption)", base_snap)

    # ---- disruption: delay the SFO morning bank on day 2 ----------------
    targets = pick_targets(w, day=2, origin="SFO", max_hour=9)
    if not targets:
        raise SystemExit("no targets found — schedule generation changed")
    touched = apply_delay(w, [f.id for f in targets], args.delay_min)
    print(f"\ndisruption: delayed {len(targets)} SFO morning flights by "
          f"{args.delay_min} min; {touched} flights changed after propagation")

    # cancel an SFO-bound return to create a coverage gap
    cancels = [f for f in w.flights
               if f.day == 2 and f.origin == "LAX" and f.dest == "SFO"]
    if cancels:
        pick = sorted(cancels, key=lambda f: f.dep)[0]
        apply_cancellation(w, pick.id)
        print(f"cancelled {pick.id} (D{pick.day} {tod(pick.dep)}) to model a coverage gap")

    dis_checks = evaluate(w, engine)
    dis_snap = snapshot(w, dis_checks, args.regime)
    print_radar("DISRUPTED (post-delay/cancellation)", dis_snap)

    # ---- Phase-1: recovery proposals ---------------------------------------
    proposals, outcome = generate(w, engine, dis_checks)
    print("\n=== RECOVERY PROPOSALS ===")
    for p in proposals:
        crew = p.get("crew_id") or "—"
        print(f"  [{p['kind']:<8}] {p['pairing_id']:<12} crew={crew:<12} "
              f"score={p['score']:<5} ok={p['legality_ok']} — {p['note']}")
    print("  outcome:", outcome)

    # ---- what-if: do nothing vs. action plan --------------------------------
    wf = whatif(w, engine, proposals, FatigueModel())
    dn, pl = wf["do_nothing"], wf["plan"]
    print("\n=== WHAT-IF (do nothing vs. action plan) ===")
    print(f"  do nothing: violations={dn['violations']} at-risk={dn['at_risk']} "
          f"uncovered={dn['uncovered']} | fatigue mean={dn['fatigue']['mean']} "
          f"high={dn['fatigue']['high']}")
    print(f"  plan:       violations={pl['violations']} at-risk={pl['at_risk']} "
          f"uncovered={pl['uncovered']} | fatigue mean={pl['fatigue']['mean']} "
          f"high={pl['fatigue']['high']} (deltas {wf['deltas']})")
    print("  top fatigue crews after plan:",
          [(r['crew_id'], r['index'], r['level']) for r in pl['fatigue']['top'][:5]])

    # ---- feed-contract export (dogfood: the demo world must conform) --------
    payload = to_contract_json(w)
    problems = validate_contract(payload)
    with open(os.path.join(args.out, "contract_sample.json"), "w") as fh:
        json.dump(payload, fh, indent=2)
    print("\nfeed-contract sample written to",
          os.path.join(args.out, "contract_sample.json"),
          f"({len(payload['flights'])} flights, {len(payload['crews'])} crews, "
          f"{len(payload['pairings'])} pairings) — "
          f"{'VALID' if not problems else problems}")

    # ---- emit reports -----------------------------------------------------
    os.makedirs(args.out, exist_ok=True)
    emit_json(os.path.join(args.out, "report.json"),
              {"meta": {"regime": args.regime, "delay_min": args.delay_min,
                        "days": args.days, "seed": args.seed,
                        "delayed_flights": [f.id for f in targets]},
               "baseline": base_snap,
               "disrupted": {**dis_snap, "proposals": proposals,
                             "recovery_outcome": outcome, "whatif": wf}})
    emit_html(os.path.join(args.out, "report_baseline.html"), "baseline", base_snap)
    emit_html(os.path.join(args.out, "report_disrupted.html"), "disrupted", dis_snap,
              proposals=proposals, whatif=wf)
    print("\nreports written under", os.path.abspath(args.out),
          "(report.json, report_baseline.html, report_disrupted.html)")


if __name__ == "__main__":
    main()