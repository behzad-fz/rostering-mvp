"""Rule engine — Phase-0 subset of FAR 117 / EASA FTL.

VERIFIED from primary sources (fetched this session):
  FAR 117 (14 CFR part 117, eCFR XML API, version 2025-01-01):
    - flight time:  100 h in any 672 consecutive hours;  1,000 h in any 365 days
    - duty hours:    60 h in any 168 consecutive hours;   190 h in any 672 h
    - per-duty FDP:  Table B (unaugmented) and Table C (augmented), exact
                     values encoded below
    - minimum rest: 10 h (FAR 117.25; reduced-rest variants not modeled)
  EASA FTL (Reg (EU) No 83/2014, EUR-Lex CELEX 32014R0083):
    - flight time:  100 h / 28 consecutive days; 900 h / calendar year; 1,000 h / 12 months

Remaining simplifications (flagged):
  - EASA's own Annex III per-duty FDP scheme is NOT encoded — the FAR 117
    table is used as a placeholder for the EASA-FTL regime
  - report (60 min) & debrief (15 min) buffers; EASA duty accumulators
  - 'co.ft-per-fdp': a company flight-time guardrail (8 h / 9 h augmented) —
    this is NOT a FAR 117 limit; FAR 117 governs duty via Table B/C
"""
from dataclasses import dataclass, field
from typing import List, Optional

from .model import Crew, DutyEvent
from .timeutil import DAY

HOUR = 60
AT_RISK_MIN = 60  # margin below this (but >= 0) => "at risk"

# FAR 117 Table B — Flight Duty Period: Unaugmented Operations (hours).
# Rows: (start-hour range, [FDP for 1, 2, 3, 4, 5, 6, 7+ segments]).
TABLE_B = [
    (0, 3, [9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0]),
    (4, 4, [10.0, 10.0, 10.0, 10.0, 9.0, 9.0, 9.0]),
    (5, 5, [12.0, 12.0, 12.0, 12.0, 11.5, 11.0, 10.5]),
    (6, 6, [13.0, 13.0, 12.0, 12.0, 11.5, 11.0, 10.5]),
    (7, 11, [14.0, 14.0, 13.0, 13.0, 12.5, 12.0, 11.5]),
    (12, 12, [13.0, 13.0, 13.0, 13.0, 12.5, 12.0, 11.5]),
    (13, 16, [12.0, 12.0, 12.0, 12.0, 11.5, 11.0, 10.5]),
    (17, 21, [12.0, 12.0, 11.0, 11.0, 10.0, 9.0, 9.0]),
    (22, 22, [11.0, 11.0, 10.0, 10.0, 9.0, 9.0, 9.0]),
    (23, 23, [10.0, 10.0, 10.0, 9.0, 9.0, 9.0, 9.0]),
]

# FAR 117 Table C — Flight Duty Period: Augmented Operations (hours).
# Rows: (start-hour range, {rest-facility class: (3 pilots, 4 pilots)}).
TABLE_C = [
    (0, 5, {1: (15.0, 17.0), 2: (14.0, 15.5), 3: (13.0, 13.5)}),
    (6, 6, {1: (16.0, 18.5), 2: (15.0, 16.5), 3: (14.0, 14.5)}),
    (7, 12, {1: (17.0, 19.0), 2: (16.5, 18.0), 3: (15.0, 15.5)}),
    (13, 16, {1: (16.0, 18.5), 2: (15.0, 16.5), 3: (14.0, 14.5)}),
    (17, 23, {1: (15.0, 17.0), 2: (14.0, 15.5), 3: (13.0, 13.5)}),
]

FAR117_PARAMS = {
    "regime": "FAR117",
    "ft_672h": 100 * HOUR,
    "ft_365d": 1000 * HOUR,
    "duty_168h": 60 * HOUR,
    "duty_672h": 190 * HOUR,
    "rest_min": 10 * HOUR,
    "report_buffer": 60,
    "debrief_buffer": 15,
    "ft_per_fdp": 8 * HOUR,
    "ft_per_fdp_aug": 9 * HOUR,
}

EASA_PARAMS = {
    "regime": "EASA-FTL",
    "ft_28d": 100 * HOUR,
    "ft_year": 900 * HOUR,
    "ft_12mo": 1000 * HOUR,
    "duty_168h": 60 * HOUR,   # approximation
    "duty_672h": 190 * HOUR,  # approximation
    "rest_min": 12 * HOUR,
    "fdp_max_h": 13.0,        # Annex III placeholder (see fdp_limit_min)
    "report_buffer": 60,
    "debrief_buffer": 15,
    "ft_per_fdp": 8 * HOUR,
    "ft_per_fdp_aug": 9 * HOUR,
}

REGIMES = {"FAR117": FAR117_PARAMS, "EASA-FTL": EASA_PARAMS}


@dataclass
class Violation:
    rule_id: str
    severity: str          # 'violation' | 'at_risk'
    message: str
    margin_min: float      # negative => violation


@dataclass
class CrewCheck:
    crew_id: str
    violations: List[Violation] = field(default_factory=list)
    total_flight_min: int = 0
    total_duty_min: int = 0
    duty_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def worst(self) -> str:
        if any(v.severity == "violation" for v in self.violations):
            return "violation"
        if self.violations:
            return "at_risk"
        return "ok"

    @property
    def min_margin(self) -> float:
        margins = [v.margin_min for v in self.violations]
        return min(margins) if margins else float("inf")


class RuleEngine:
    def __init__(self, regime: str = "FAR117", params: Optional[dict] = None):
        if regime not in REGIMES:
            raise ValueError(f"unknown regime {regime!r}; choose from {sorted(REGIMES)}")
        self.name = regime
        self.p = dict(REGIMES[regime])
        if params:
            self.p.update(params)

    # ------------------------------------------------------------------ FDP
    def fdp_limit_min(self, start_mod_1440: int, segments: int,
                      augmented: bool = False, acclimated: bool = True,
                      aug_class: int = 1, aug_pilots: int = 3) -> int:
        """FAR 117 / EASA per-duty FDP limit in minutes."""
        if self.name == "EASA-FTL":
            # Annex III encoding pending (EUR-Lex bot-blocked on last attempt).
            # Placeholder: basic daily FDP 13 h; the start-time/sector
            # gradient and augmented extensions must be encoded from the
            # regulation text when access is restored.
            val = float(self.p.get("fdp_max_h", 13.0))
            if not acclimated:
                val -= 0.5
            return int(round(val * HOUR))
        hour = (start_mod_1440 % DAY) // 60
        if augmented:
            row = TABLE_C[0]
            for h0, h1, grid in TABLE_C:
                if h0 <= hour <= h1:
                    row = grid
                    break
            col = row[aug_class]
            val = col[0] if aug_pilots == 3 else col[1]
        else:
            row = TABLE_B[0][2]
            for h0, h1, vals in TABLE_B:
                if h0 <= hour <= h1:
                    row = vals
                    break
            val = row[min(segments, 7) - 1]
        if not acclimated:
            val -= 0.5      # 117.13(b): unacclimated FDP reduced by 30 min
        return int(round(val * HOUR))

    def _mk(self, rule_id: str, margin: float, ok_msg: Optional[str] = None) -> Optional[Violation]:
        if margin >= AT_RISK_MIN:
            return None
        severity = "violation" if margin < 0 else "at_risk"
        if ok_msg is None:
            ok_msg = f"{rule_id}: margin {margin:+.0f} min"
        return Violation(rule_id=rule_id, severity=severity,
                         message=f"{ok_msg} (margin {margin:+.0f} min)", margin_min=margin)

    # ---------------------------------------------------------------- checks
    def check(self, crew: Crew, duties: List[DutyEvent]) -> CrewCheck:
        cc = CrewCheck(crew_id=crew.id)
        duties = sorted(duties, key=lambda d: (d.start, d.pairing_id))
        cc.duty_count = len(duties)
        cc.total_flight_min = sum(d.flight_min for d in duties)
        cc.total_duty_min = sum(d.end - d.start for d in duties)

        # Per-duty FDP and flight-time caps ---------------------------------
        for d in duties:
            duty_min = d.end - d.start
            lim = self.fdp_limit_min(d.start % DAY, d.segments)
            v = self._mk(f"{self.p['regime']}.fdp-per-duty",
                         lim - duty_min,
                         f"{d.pairing_id}: duty {duty_min // 60}h{duty_min % 60:02d} vs FDP limit {lim // 60}h")
            if v:
                cc.violations.append(v)
            ft_lim = self.p["ft_per_fdp"]
            # company flight-time guardrail — not a FAR 117 limit (FAR 117
            # governs duty via Table B/C); kept as an operator safety margin
            v = self._mk("co.ft-per-fdp",
                         ft_lim - d.flight_min,
                         f"{d.pairing_id}: flight time {d.flight_min // 60}h vs guardrail {ft_lim // 60}h")
            if v:
                cc.violations.append(v)

        # Minimum rest between consecutive duties ----------------------------
        for prev, nxt in zip(duties, duties[1:]):
            rest = nxt.start - prev.end
            v = self._mk(
                f"{self.p['regime']}.rest-min",
                rest - self.p["rest_min"],
                f"rest {rest // 60}h{rest % 60:02d} vs min {self.p['rest_min'] // 60}h",
            )
            if v:
                cc.violations.append(v)

        # Cumulative accumulators --------------------------------------------
        ft = cc.total_flight_min + crew.hist_flight_672h
        rule_ft28 = f"{self.name}.ft-672h" if self.name == "FAR117" else f"{self.name}.ft-28d"
        v = self._mk(rule_ft28,
                     self.p.get("ft_672h", self.p.get("ft_28d")) - ft,
                     f"flight time {ft // 60}h vs limit {(self.p.get('ft_672h', self.p.get('ft_28d'))) // 60}h")
        if v:
            cc.violations.append(v)

        if self.name == "FAR117":
            fty = cc.total_flight_min + crew.hist_flight_365d
            v = self._mk(f"{self.name}.ft-365d", self.p["ft_365d"] - fty,
                         f"flight time {fty // 60}h vs 365d limit {self.p['ft_365d'] // 60}h")
            if v:
                cc.violations.append(v)
        else:
            fty = cc.total_flight_min + crew.hist_flight_365d
            v = self._mk(f"{self.name}.ft-year", self.p["ft_year"] - fty,
                         f"flight time {fty // 60}h vs year limit {self.p['ft_year'] // 60}h")
            if v:
                cc.violations.append(v)

        du = cc.total_duty_min + crew.hist_duty_168h
        v = self._mk(f"{self.name}.duty-168h",
                     self.p["duty_168h"] - du,
                     f"duty {du // 60}h vs 168h limit {self.p['duty_168h'] // 60}h")
        if v:
            cc.violations.append(v)

        du28 = cc.total_duty_min + crew.hist_duty_672h
        v = self._mk(f"{self.name}.duty-672h",
                     self.p["duty_672h"] - du28,
                     f"duty {du28 // 60}h vs 672h limit {self.p['duty_672h'] // 60}h")
        if v:
            cc.violations.append(v)

        return cc