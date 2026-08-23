"""Rule engine — Phase-0 subset of FAR 117 / EASA FTL.

VERIFIED limits (fetched from primary sources in the research pass):
  FAR 117 (14 CFR part 117, eCFR):
    - flight time:  100 h in any 672 consecutive hours;  1,000 h in any 365 days
    - duty hours:    60 h in any 168 consecutive hours;   190 h in any 672 h
  EASA FTL (Reg (EU) No 83/2014, EUR-Lex CELEX 32014R0083):
    - flight time:  100 h / 28 consecutive days; 900 h / calendar year; 1,000 h / 12 months

APPROXIMATIONS (flagged — verify against the primary texts before production use):
  - the per-duty FDP table (approximation of FAR 117 Table B, acclimated,
    unaugmented 2-pilot; augmented = +3 h trend from Table C)
  - per-FDP flight-time cap (8 h unaugmented / 9 h augmented)
  - minimum rest (10 h FAR 117 / 12 h EASA), report & debrief buffers,
    and EASA duty-accumulator values
"""
from dataclasses import dataclass, field
from typing import List, Optional

from .model import Crew, DutyEvent
from .timeutil import DAY

HOUR = 60
AT_RISK_MIN = 60  # margin below this (but >= 0) => "at risk"

# Per-duty FDP limit (hours) by local start hour: (h0, h1, fdp_1_2seg, fdp_3plus)
TABLE_B_APPROX = [
    (0, 4, 9.0, 8.0),
    (5, 6, 12.0, 11.0),
    (7, 12, 13.0, 12.0),
    (13, 16, 12.0, 11.0),
    (17, 21, 11.0, 10.0),
    (22, 23, 9.0, 8.0),
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
                      augmented: bool = False, acclimated: bool = True) -> int:
        """Approximation of FAR 117 Table B (acclimated, unaugmented)."""
        hour = (start_mod_1440 % DAY) // 60
        row = TABLE_B_APPROX[0]
        for h0, h1, v12, v3p in TABLE_B_APPROX:
            if h0 <= hour <= h1:
                row = (h0, h1, v12, v3p)
                break
        val = row[2] if segments <= 2 else row[3]
        if augmented:
            val += 3.0      # Table C trend (approximation)
        if not acclimated:
            val -= 0.5      # 117.13(b): -30 min
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
            v = self._mk(f"{self.p['regime']}.ft-per-fdp",
                         ft_lim - d.flight_min,
                         f"{d.pairing_id}: flight time {d.flight_min // 60}h vs cap {ft_lim // 60}h")
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