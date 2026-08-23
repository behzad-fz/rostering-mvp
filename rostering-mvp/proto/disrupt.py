"""Disruption simulation: delays, cancellations, and propagation through
pairings.

Propagation model: a delayed first leg slides the rest of the rotation with a
minimum turn time floor — eff_dep(next) = max(scheduled + accrued delay,
arr(prev) + MIN_TURN_MIN). This preserves duty length (delays stretch the day,
they don't compress it) and lets schedule pressure accumulate realistically.
"""
from typing import List

from .model import Flight, World

MIN_TURN_MIN = 40  # realistic minimum ground/turn time at the gate


def apply_delay(w: World, flight_ids: List[str], delay_min: int) -> int:
    """Delay the given flights by delay_min and propagate through their
    pairings. Returns the number of flights whose timing changed."""
    touched = 0
    for fid in flight_ids:
        f = w.flight(fid)
        if f.cancelled:
            continue
        f.delay = max(f.delay, delay_min)
        touched += 1
        touched += _propagate_pairing(w, f, delay_min)
    return touched


def _propagate_pairing(w: World, first: Flight, delay_min: int) -> int:
    """Slide the remaining legs of every pairing containing `first`."""
    touched = 0
    for p in w.pairings:
        ids = p.flight_ids
        if first.id not in ids:
            continue
        idx = ids.index(first.id)
        prev = w.flight(ids[idx])
        for j in range(idx + 1, len(ids)):
            cur = w.flight(ids[j])
            # departure = max(scheduled + accrued delay, prev arrival + min turn)
            eff_dep = max(cur.dep + prev.delay, prev.eff_arr + MIN_TURN_MIN)
            new_delay = eff_dep - cur.dep
            if new_delay <= 0:
                break
            cur.delay = max(cur.delay, new_delay)
            prev = cur
            touched += 1
    return touched


def apply_cancellation(w: World, flight_id: str) -> None:
    f = w.flight(flight_id)
    f.cancelled = True
    f.delay = 0