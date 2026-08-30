"""What-if / scenario evaluation.

Fork the world model, apply (or not) an action plan, roll forward, and compare
legality + fatigue outcomes — the decision-support loop that schedulers use
before committing: "what happens if we do nothing vs. do this plan?"
"""
import copy
from typing import Dict, List, Optional

from .fatigue import ELEVATED, FatigueModel, HIGH
from .legality import build_duties, evaluate
from .model import World
from .recovery import _apply
from .risk import uncovered_flights
from .rules import RuleEngine

EXECUTABLE = ("reserve", "swap", "surgery", "relieve", "deadhead", "cancel")


def scenario(w: World, engine: RuleEngine, plan: Optional[List[dict]] = None,
             label: str = "do nothing",
             fatigue: Optional[FatigueModel] = None) -> dict:
    w2 = copy.deepcopy(w)
    applied = 0
    if plan:
        for p in plan:
            if p.get("kind") not in EXECUTABLE or not p.get("legality_ok"):
                continue
            if p["kind"] == "relieve" and not (p.get("crew_id") or p.get("relieved_crew")):
                continue
            if p["kind"] != "relieve" and p["kind"] != "cancel" and not p.get("crew_id"):
                continue
            _apply(w2, p)
            applied += 1
    checks = evaluate(w2, engine)
    un = uncovered_flights(w2, checks)
    result = {
        "label": label,
        "applied": applied,
        "violations": sum(1 for c in checks.values() if c.worst == "violation"),
        "at_risk": sum(1 for c in checks.values() if c.worst == "at_risk"),
        "uncovered": len([f for f, r in un if not f.cancelled]),
        "reserve_callouts": sum(1 for p in (plan or []) if p.get("kind") == "reserve"),
        "cancellations": sum(len(w2.pairing(p["pairing_id"]).flight_ids)
                             for p in (plan or [])
                             if p.get("kind") == "cancel" and p.get("legality_ok")),
    }
    if fatigue is not None:
        duties = build_duties(w2)
        rows = []
        total, n = 0.0, 0
        for c in w2.crews:
            st = fatigue.run(c, duties.get(c.id, []))
            total += st.index
            n += 1
            rows.append({"crew_id": c.id, "index": st.index, "level": st.level})
        result["fatigue"] = {
            "mean": round(total / n, 1) if n else 0.0,
            "max": max((r["index"] for r in rows), default=0.0),
            "elevated": sum(1 for r in rows if r["level"] == "elevated"),
            "high": sum(1 for r in rows if r["level"] == "high"),
            "top": sorted(rows, key=lambda r: -r["index"])[:5],
        }
    return result


def whatif(w: World, engine: RuleEngine, plan: List[dict],
           fatigue: Optional[FatigueModel] = None) -> dict:
    base = scenario(w, engine, None, "do nothing", fatigue)
    action = scenario(w, engine, plan, "action plan", fatigue)
    deltas = {k: action[k] - base[k] for k in ("violations", "at_risk", "uncovered")}
    return {"do_nothing": base, "plan": action, "deltas": deltas}