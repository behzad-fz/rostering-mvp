"""Disruption simulation: delays, cancellations, and propagation through
pairings. The prototype models simple time-based propagation: a delayed leg
pushes subsequent legs of the same pairing only by the unabsorbed remainder
after scheduled turn buffers.
"""
from typing import List

from .model import Flight, World


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
    """Push the unabsorbed remainder of a delay through subsequent legs of
    every pairing containing `first`."""
    touched = 0
    for p in w.pairings:
        ids = p.flight_ids
        if first.id not in ids:
            continue
        idx = ids.index(first.id)
        for j in range(idx + 1, len(ids)):
            prev = w.flight(ids[j - 1])
            cur = w.flight(ids[j])
            # scheduled turn buffer between the two legs
            gap = cur.dep - prev.arr
            # how much of the accumulated delay is still unabsorbed
            carry = prev.delay - gap if prev.delay is not None else 0
            if carry <= 0:
                break
            cur.delay = max(cur.delay, carry)
            touched += 1
    return touched


def apply_cancellation(w: World, flight_id: str) -> None:
    f = w.flight(flight_id)
    f.cancelled = True
    f.delay = 0