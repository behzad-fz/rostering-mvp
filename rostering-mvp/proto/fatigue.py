"""Fatigue indicator — a simplified, explainable duty-intensity model.

NOT a validated bio-mathematical model (SAFTE/FAID/FAST are the real
integration targets, per the architecture doc). This toy scores duty load on a
0-100 index so schedules can be compared and sustained-load crews flagged:

  per duty:     + 1.0  per duty hour
                + 0.5  per hour the duty starts before 07:00 (early start)
                + 0.25 per hour of duty time in 22:00-04:00 (night window)
                + 0.15 per hour of duty beyond 10 h (long day)
  between:      rest weighted higher if it covers the night window
                (22:00-04:00 per the toy model)     -> 0.08/min-h
                otherwise rest                      -> 0.05/min-h
                rest < 10 h               -> +2.0 per missing hour
  clamp 0..100; levels: <55 ok, 55-69 elevated, >=70 high.

Deterministic and cheap; every weight is documented so it can be tuned or
replaced by a licensed model.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .model import Crew, DutyEvent
from .timeutil import DAY, local


@dataclass
class FatigueState:
    crew_id: str
    index: float = 0.0
    level: str = "ok"
    duty_count: int = 0
    contributions: List[str] = field(default_factory=list)
    key_items: List[str] = field(default_factory=list)

    @property
    def flags(self) -> List[str]:
        out = []
        if self.level == "high":
            out.append("high fatigue — review this crew before further duty")
        elif self.level == "elevated":
            out.append("elevated fatigue — monitor")
        return out


ELEVATED = 55.0
HIGH = 70.0
NIGHT_START, NIGHT_END = 22 * 60, 4 * 60          # minutes of day 22:00-04:00
EARLY_START = 7 * 60                               # penalty before 07:00
LONG_DAY = 10 * 60                                 # duty beyond 10 h
MIN_REST_OK = 10 * 60                              # below this: penalty


def _night_overlap(start: int, end: int) -> int:
    """Minutes of [start,end) falling in the night window (across midnight)."""
    total = 0
    for day_off in (0, DAY):                        # handle wrap at midnight
        ns = NIGHT_START + day_off
        ne = NIGHT_END + day_off + DAY
        lo, hi = max(start, ns), min(end, ne)
        if lo < hi:
            total += hi - lo
    return total


class FatigueModel:
    def run(self, crew: Crew, duties: List[DutyEvent]) -> FatigueState:
        ds = sorted(duties, key=lambda d: (d.start, d.pairing_id))
        st = FatigueState(crew_id=crew.id, duty_count=len(ds))
        index = 0.0
        for d in ds:
            hours = (d.end - d.start) / 60.0
            index += hours                                    # base duty load
            st.contributions.append(f"duty {hours:.1f}h -> +{hours:.1f}")
            start_hour = local(d.start)[1]
            if start_hour < 7:
                p = (7 - start_hour) * 0.5
                index += p
                st.contributions.append(f"early start {start_hour:02d}:00 -> +{p:.1f}")
            night = _night_overlap(d.start, d.end) / 60.0
            if night > 0:
                p = night * 0.25
                index += p
                st.contributions.append(f"night {night:.1f}h -> +{p:.1f}")
            if d.end - d.start > LONG_DAY:
                p = ((d.end - d.start) - LONG_DAY) / 60.0 * 0.15
                index += p
                st.contributions.append(f"long day -> +{p:.1f}")
        for prev, nxt in zip(ds, ds[1:]):
            rest = nxt.start - prev.end
            if rest < MIN_REST_OK:
                p = (MIN_REST_OK - rest) / 60.0 * 2.0
                index += p
                st.contributions.append(f"short rest {rest / 60:.1f}h -> +{p:.1f}")
            # recovery: rest hours capped at 14, weighted by physiological night
            capped = min(rest / 60.0, 14.0)
            night = _night_overlap(prev.end, nxt.start) / 60.0
            rec = capped * (0.08 if night >= 6 else 0.05)
            index -= rec
            st.contributions.append(f"rest {rest / 60:.1f}h -> -{rec:.2f}")
        st.index = round(max(0.0, min(index, 100.0)), 1)
        st.level = ("high" if st.index >= HIGH else
                    "elevated" if st.index >= ELEVATED else "ok")
        st.key_items = [c for c in st.contributions
                if re.search(r"[+-]\d+(?:\.\d+)?$", c)]
        return st