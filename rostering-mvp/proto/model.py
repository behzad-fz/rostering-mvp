"""Core data model for the Phase-0 prototype.

All times are absolute horizon minutes (see timeutil).
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class Flight:
    id: str
    day: int
    dep: int            # scheduled departure (absolute minutes)
    arr: int            # scheduled arrival
    origin: str
    dest: str
    delay: int = 0
    cancelled: bool = False

    @property
    def eff_dep(self) -> int:
        return self.dep if self.cancelled else self.dep + self.delay

    @property
    def eff_arr(self) -> int:
        return self.arr if self.cancelled else self.arr + self.delay

    @property
    def block_min(self) -> int:
        return self.arr - self.dep


@dataclass
class Crew:
    id: str
    base: str
    group: str          # 'P' pilot | 'FA' flight attendant
    seniority: int = 0
    # Pre-existing accumulator history (minutes), used to exercise the
    # cumulative window rules on a 7-day horizon.
    hist_flight_672h: int = 0      # flight minutes in any 672-hour window     (FAR 117: <= 100 h)
    hist_flight_365d: int = 0      # flight minutes in the 365-day window      (FAR 117: <= 1000 h)
    hist_duty_168h: int = 0        # duty minutes in any 168-hour window       (FAR 117: <= 60 h)
    hist_duty_672h: int = 0        # duty minutes in any 672-hour window       (FAR 117: <= 190 h)


@dataclass
class Pairing:
    id: str
    flight_ids: List[str]


@dataclass
class DutyEvent:
    """A computed duty for one crew (report->debrief), from one pairing."""
    crew_id: str
    pairing_id: str
    day: int
    start: int          # report time = first flight dep - report buffer
    end: int            # debrief time = last flight arr + debrief buffer
    segments: int
    flight_min: int     # sum of scheduled block minutes on this duty
    cancelled_flight_ids: List[str] = field(default_factory=list)


@dataclass
class World:
    flights: List[Flight] = field(default_factory=list)
    crews: List[Crew] = field(default_factory=list)
    pairings: List[Pairing] = field(default_factory=list)
    assignments: List[Tuple[str, str]] = field(default_factory=list)  # (crew_id, pairing_id)
    reserves: Dict[int, List[str]] = field(default_factory=dict)      # day -> crew ids on standby

    _flight_map: Dict[str, Flight] = field(default_factory=dict, init=False)

    def index(self) -> None:
        self._flight_map = {f.id: f for f in self.flights}

    def flight(self, fid: str) -> Flight:
        return self._flight_map[fid]

    def pairing(self, pid: str) -> Pairing:
        for p in self.pairings:
            if p.id == pid:
                return p
        raise KeyError(pid)