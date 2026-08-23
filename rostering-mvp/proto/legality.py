"""Legality evaluation: build per-crew duties and run the rule engine."""
from typing import Dict, List

from .model import Crew, DutyEvent, Flight, Pairing, World
from .rules import CrewCheck, RuleEngine

REPORT_BUFFER_DEFAULT = 60
DEBRIEF_DEFAULT = 15


def pairing_duty(w: World, p: Pairing, crew_id: str, report_buffer: int = REPORT_BUFFER_DEFAULT,
                 debrief: int = DEBRIEF_DEFAULT) -> DutyEvent:
    flights = [w.flight(fid) for fid in p.flight_ids]
    first, last = flights[0], flights[-1]
    cancelled = [f.id for f in flights if f.cancelled]
    return DutyEvent(
        crew_id=crew_id,
        pairing_id=p.id,
        day=first.day,
        start=first.eff_dep - report_buffer,
        end=last.eff_arr + debrief,
        segments=len(flights),
        flight_min=sum(f.block_min for f in flights),
        cancelled_flight_ids=cancelled,
    )


def build_duties(w: World, report_buffer: int = REPORT_BUFFER_DEFAULT,
                 debrief: int = DEBRIEF_DEFAULT) -> Dict[str, List[DutyEvent]]:
    duties: Dict[str, List[DutyEvent]] = {}
    for crew_id, pid in w.assignments:
        p = w.pairing(pid)
        duties.setdefault(crew_id, []).append(pairing_duty(w, p, crew_id, report_buffer, debrief))
    return duties


def evaluate(w: World, engine: RuleEngine,
             report_buffer: int = REPORT_BUFFER_DEFAULT,
             debrief: int = DEBRIEF_DEFAULT) -> Dict[str, CrewCheck]:
    duties = build_duties(w, report_buffer, debrief)
    checks: Dict[str, CrewCheck] = {}
    for crew in w.crews:
        checks[crew.id] = engine.check(crew, duties.get(crew.id, []))
    return checks


def crew_duties(w: World, crew_id: str) -> List[DutyEvent]:
    return [pairing_duty(w, w.pairing(pid), crew_id) for cid, pid in w.assignments if cid == crew_id]