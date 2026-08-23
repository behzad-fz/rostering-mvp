"""Deterministic synthetic schedule generator for the demo.

Builds a 7-day world: flights, pairings (day trips), crew assignments with
comfortable rest, plus deliberate baseline issues the risk radar should catch:
  - one crew with an over-limit duty (FDP violation)
  - one crew with a near-limit duty (at-risk)
  - crews with pre-existing accumulators near the cumulative caps
"""
from typing import Dict, List, Tuple

from .model import Crew, Flight, Pairing, World
from .timeutil import hm

BASES = ["SFO", "LAX", "DEN", "SEA"]

# Scheduled block minutes between city pairs (both directions).
BLOCK: Dict[Tuple[str, str], int] = {
    ("SFO", "LAX"): 95, ("LAX", "SFO"): 95,
    ("SFO", "SEA"): 120, ("SEA", "SFO"): 120,
    ("SFO", "DEN"): 155, ("DEN", "SFO"): 155,
    ("LAX", "SEA"): 165, ("SEA", "LAX"): 165,
    ("LAX", "DEN"): 145, ("DEN", "LAX"): 145,
    ("DEN", "SEA"): 135, ("SEA", "DEN"): 135,
}

# Duty windows per daily turn pattern. (dep_local, end_local) — kept under
# FDP limits for normal crews.
MORNING = {"dep": 7, "end": 15}
AFTERNOON = {"dep": 10, "end": 18}

PILOTS_PER_BASE = 8
FA_PER_BASE = 10
RESERVE_PILOTS = 2
RESERVE_FA = 4


def _partners(base: str, day: int) -> List[str]:
    others = [b for b in BASES if b != base]
    return [others[day % len(others)], others[(day + 1) % len(others)]]


def build_world(days: int = 7, seed: int = 42) -> World:
    w = World()

    # ---- flights & pairings ------------------------------------------------
    n = 0
    pairing_rows: List[Tuple[str, List[Flight], int]] = []  # (pairing_id, flights, day)
    for day in range(days):
        for bi, base in enumerate(BASES):
            partners = _partners(base, day)
            for slot, (partner, win) in enumerate(zip(partners, [MORNING, AFTERNOON])):
                dep = hm(day, win["dep"], (bi * 10 + slot * 5))
                blk = BLOCK[(base, partner)]
                f1 = Flight(f"F{n:04d}", day, dep, dep + blk, base, partner)
                n += 1
                ret_dep = f1.arr + 40
                f2 = Flight(f"F{n:04d}", day, ret_dep, ret_dep + blk, partner, base)
                n += 1
                w.flights.extend([f1, f2])
                pid = f"P{day}-{base}-{slot}"
                w.pairings.append(Pairing(pid, [f1.id, f2.id]))
                pairing_rows.append((pid, [f1, f2], day))

    w.index()

    # ---- crews --------------------------------------------------------------
    for base in BASES:
        for i in range(PILOTS_PER_BASE):
            c = Crew(f"P-{base}-{i}", base, "P", seniority=i)
            if base == "SFO" and i == 3:
                c.hist_flight_672h = 99 * 60      # 1 h below the 100 h / 28 d cap
            if base == "LAX" and i == 2:
                c.hist_duty_168h = 59 * 60        # 1 h below the 60 h / 7 d cap
            w.crews.append(c)
        for i in range(FA_PER_BASE):
            w.crews.append(Crew(f"FA-{base}-{i}", base, "FA", seniority=i))
        for i in range(RESERVE_PILOTS):
            w.crews.append(Crew(f"RP-{base}-{i}", base, "P", seniority=99))
        for i in range(RESERVE_FA):
            w.crews.append(Crew(f"RF-{base}-{i}", base, "FA", seniority=99))
        for day in range(days):
            w.reserves.setdefault(day, []).extend(
                [f"RP-{base}-{i}" for i in range(RESERVE_PILOTS)] +
                [f"RF-{base}-{i}" for i in range(RESERVE_FA)])

    # ---- assignments (round-robin, comfortably legal) -----------------------
    for base in BASES:
        day_pairings: Dict[int, List[Tuple[str, int]]] = {d: [] for d in range(days)}
        for pid, flights, day in pairing_rows:
            if flights[0].origin == base:
                day_pairings[day].append((pid, len(flights)))

        for group, label in (("P", PILOTS_PER_BASE), ("FA", FA_PER_BASE)):
            for i in range(label):
                crew_id = f"{group}-{base}-{i}"
                # two duties per crew, ~4 days apart
                d1 = i % days
                d2 = (i + 4) % days
                picks = []
                if day_pairings[d1]:
                    picks.append((d1, day_pairings[d1][i % len(day_pairings[d1])]))
                if day_pairings[d2]:
                    picks.append((d2, day_pairings[d2][(i + 1) % len(day_pairings[d2])]))
                for d, (pid, segs) in picks:
                    w.assignments.append((crew_id, pid))

    # ---- baseline issues ----------------------------------------------------
    w = _inject_issues(w)
    return w


def _inject_issues(w: World) -> World:
    """Overwrite a few flights/assignments to seed baseline violations/risk."""
    # 1) FDP violation: P-SFO-0 gets one long 4-leg duty starting 06:00 day 2.
    day = 2
    f0 = w.flights  # rebuild a custom pairing
    segs = [
        (day, 6, 0, "SFO", "LAX", 95),
        (day, 8, 25, "LAX", "SEA", 165),
        (day, 11, 20, "SEA", "DEN", 135),
        (day, 14, 25, "DEN", "SFO", 155),
    ]
    ids = []
    for i, (d, h, m, o, de, blk) in enumerate(segs):
        dep = hm(d, h, m)
        fid = f"X{i}-{day}"
        w.flights.append(Flight(fid, d, dep, dep + blk, o, de))
        ids.append(fid)
    pid = f"X-long-{day}"
    w.pairings.append(Pairing(pid, ids))
    # replace any prior assignment of P-SFO-0 this day
    w.assignments = [a for a in w.assignments if not (a[0] == "P-SFO-0" and a[1].startswith(f"P{day}-"))]
    w.assignments.append(("P-SFO-0", pid))
    w.index()

    # 2) At-risk: P-SFO-1 gets a 3-leg duty starting 08:00 day 3, ending
    #    ~18:45 — duty ~11.75 h vs the 12 h FDP limit at that start hour
    #    (deliberately long turns; flight time stays under the 8 h cap).
    day = 3
    segs2 = [
        (day, 8, 0, "SFO", "LAX", 95),
        (day, 11, 40, "LAX", "SEA", 165),
        (day, 16, 30, "SEA", "SFO", 120),
    ]
    ids2 = []
    for i, (d, h, m, o, de, blk) in enumerate(segs2):
        dep = hm(d, h, m)
        fid = f"Y{i}-{day}"
        w.flights.append(Flight(fid, d, dep, dep + blk, o, de))
        ids2.append(fid)
    pid2 = f"Y-long-{day}"
    w.pairings.append(Pairing(pid2, ids2))
    w.assignments = [a for a in w.assignments if not (a[0] == "P-SFO-1" and a[1].startswith(f"P{day}-"))]
    w.assignments.append(("P-SFO-1", pid2))
    w.index()
    return w