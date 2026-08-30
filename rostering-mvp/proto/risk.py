"""Risk scoring and the risk-radar view.

Phase-0 scope: turn per-crew legality checks + disrupted flights into a ranked
"who is in danger / what is uncovered" picture for schedulers.
"""
from typing import Dict, List, Tuple

from .model import World
from .rules import CrewCheck, Violation

SEVERITY_ORDER = {"violation": 2, "at_risk": 1, "ok": 0}


def risk_score(check: CrewCheck) -> float:
    """Crew risk score: sum of negative margins for violations plus the
    at-risk shortfall. Higher = worse."""
    score = 0.0
    for v in check.violations:
        if v.severity == "violation":
            score += max(1.0, -v.margin_min / 15.0)
        else:  # at_risk: how far below the 60-min comfort threshold
            score += (60.0 - v.margin_min) / 15.0
    return round(score, 1)


def rank_crews(checks: Dict[str, CrewCheck]) -> List[Tuple[str, CrewCheck, float]]:
    rows = [(cid, c, risk_score(c)) for cid, c in checks.items() if not c.ok]
    rows.sort(key=lambda r: (SEVERITY_ORDER[r[1].worst], r[1].min_margin, r[2]))
    return rows


def uncovered_flights(w: World, checks: Dict[str, CrewCheck]) -> List[Tuple[object, str]]:
    """Flights that cannot be covered: cancelled, or a pairing with ANY
    assigned crew whose legality is broken (a pairing needs both its pilot
    and cabin crews). Returns (flight, reason)."""
    from collections import defaultdict
    out: List[Tuple[object, str]] = []
    crews_of_pairing: Dict[str, List[str]] = defaultdict(list)
    for cid, pid in w.assignments:
        crews_of_pairing[pid].append(cid)
    for p in w.pairings:
        crew_ids = crews_of_pairing.get(p.id, [])
        broken = [cid for cid in crew_ids
                  if checks.get(cid) and checks[cid].worst == "violation"]
        for fid in p.flight_ids:
            f = w.flight(fid)
            if f.cancelled:
                out.append((f, "cancelled"))
            elif not crew_ids:
                out.append((f, "no crew assigned"))
            elif broken:
                out.append((f, f"crew {', '.join(broken)} legality broken"))
    return out


def reserve_gaps(w: World, checks: Dict[str, CrewCheck],
                 uncovered: List[Tuple[object, str]]) -> Dict[str, List[str]]:
    """Per (day, base): uncovered flights vs reserve crews available."""
    from collections import defaultdict
    gaps: Dict[str, List[str]] = defaultdict(list)
    available: Dict[Tuple[int, str], int] = {}
    for day, crew_ids in w.reserves.items():
        for cid in crew_ids:
            crew = next((c for c in w.crews if c.id == cid), None)
            if crew is not None:
                base = crew.base
                key = (day, base)
                available[key] = available.get(key, 0) + (0 if checks.get(cid, None) and
                                                          checks[cid].worst == "violation" else 1)
    for f, reason in uncovered:
        if f.cancelled:
            continue          # nothing to cover for a flight that is not operating
        key = (f.day, f.origin)
        key2 = (f.day, f.dest)
        key = key if key in available else key2
        avail = available.get(key, 0)
        if avail <= 0:
            gaps.setdefault(f"day {f.day} @ {f.origin}", []).append(
                f"{f.id} ({reason}) — no reserve available")
        else:
            available[key] -= 1
            gaps.setdefault(f"day {f.day} @ {f.origin}", []).append(
                f"{f.id} ({reason}) — reserve would cover")
    return dict(gaps)


def summary(w: World, checks: Dict[str, CrewCheck],
            uncovered: List[Tuple[object, str]]) -> Dict[str, object]:
    counts = {"violation": 0, "at_risk": 0, "ok": 0}
    viols: List[Violation] = []
    for c in checks.values():
        counts[c.worst] += 1
        viols.extend(c.violations)
    from collections import Counter
    return {
        "crews": len(checks),
        "flights": len(w.flights),
        "duties": sum(1 for cid, _ in w.assignments),
        "violations": counts["violation"],
        "at_risk": counts["at_risk"],
        "ok": counts["ok"],
        "rule_breakdown": _rule_breakdown(viols),
        "uncovered": len(uncovered),
        "uncovered_reasons": dict(Counter(reason for _f, reason in uncovered)),
    }


def _rule_breakdown(violations: List[Violation]) -> Dict[str, int]:
    from collections import Counter
    return dict(Counter(v.rule_id for v in violations))