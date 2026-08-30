"""Feed-contract export: serialize a World into the carrier-feed contract
shape described in contract/README.md.

Dogfooding rule: the synthetic schedule generator must be able to emit a
contract-conformant snapshot — whatever a real carrier's adapters would push
into the recovery engine. If the demo world can't export cleanly, the contract
(or the generator) is wrong.
"""
from typing import Any, Dict

from .model import World

SCHEMA = "crew-recovery-contract/1.0"


def to_contract_json(w: World) -> Dict[str, Any]:
    crew_ids_by_pairing: Dict[str, list] = {p.id: [] for p in w.pairings}
    for cid, pid in w.assignments:
        crew_ids_by_pairing.setdefault(pid, []).append(cid)

    return {
        "schema": SCHEMA,
        "flights": [
            {"id": f.id, "day": f.day, "dep_min": f.dep, "arr_min": f.arr,
             "origin": f.origin, "dest": f.dest,
             "delay_min": f.delay, "cancelled": f.cancelled}
            for f in w.flights
        ],
        "crews": [
            {"id": c.id, "base": c.base, "group": c.group, "seniority": c.seniority,
             "hist_flight_672h": c.hist_flight_672h, "hist_flight_365d": c.hist_flight_365d,
             "hist_duty_168h": c.hist_duty_168h, "hist_duty_336h": c.hist_duty_336h,
             "hist_duty_672h": c.hist_duty_672h}
            for c in w.crews
        ],
        "pairings": [
            {"id": p.id, "flight_ids": p.flight_ids,
             "crew_ids": sorted(crew_ids_by_pairing.get(p.id, []))}
            for p in w.pairings
        ],
        "reserves": [
            {"day": d, "crew_id": cid} for d, crew_ids in sorted(w.reserves.items())
            for cid in sorted(crew_ids)
        ],
    }


def validate_contract(payload: Dict[str, Any]) -> list:
    """Cheap structural checks; returns a list of problems (empty = ok)."""
    problems = []
    if payload.get("schema") != SCHEMA:
        problems.append("schema mismatch")
    for f in payload.get("flights", []):
        for key in ("id", "day", "dep_min", "arr_min", "origin", "dest"):
            if key not in f:
                problems.append(f"flight {f.get('id')}: missing {key}")
    for p in payload.get("pairings", []):
        if not p.get("crew_ids"):
            problems.append(f"pairing {p.get('id')}: no crew assigned")
    return problems