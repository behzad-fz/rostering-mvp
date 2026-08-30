#!/usr/bin/env python3
"""Unit tests for the Phase-0 rule engine. Hand-computed cases against the
implemented (verified + approximated) limits.

Run:  python3 test_rules.py        (from rostering-mvp/)
  or: python3 -m unittest proto.test_rules
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proto.model import Crew, DutyEvent      # noqa: E402
from proto.rules import AT_RISK_MIN, RuleEngine  # noqa: E402
from proto.timeutil import hm                 # noqa: E402


def duty(crew_id, day, sh, sm, eh, em, segments, flight_min, pairing="T"):
    return DutyEvent(crew_id=crew_id, pairing_id=pairing, day=day,
                     start=hm(day, sh, sm), end=hm(day, eh, em),
                     segments=segments, flight_min=flight_min)


class TestFdp(unittest.TestCase):
    def setUp(self):
        self.eng = RuleEngine("FAR117")

    def test_ok_duty(self):
        # report 08:00, 2 segments, ~8h duty -> plenty of margin (limit 13 h)
        c = Crew("CREW-OK", "SFO", "P")
        cc = self.eng.check(c, [duty("CREW-OK", 0, 8, 0, 16, 0, 2, 300)])
        self.assertTrue(cc.ok, cc.violations)

    def test_fdp_violation(self):
        # report 05:00 (exact Table B 0500-0559, 4 segments) -> limit 12 h;
        # duty of 12.5 h must violate
        c = Crew("CREW-BAD", "SFO", "P")
        cc = self.eng.check(c, [duty("CREW-BAD", 0, 5, 0, 17, 30, 4, 480)])
        rules = [v.rule_id for v in cc.violations]
        self.assertIn("FAR117.fdp-per-duty", rules)
        v = next(v for v in cc.violations if v.rule_id == "FAR117.fdp-per-duty")
        self.assertEqual(v.severity, "violation")
        self.assertLess(v.margin_min, 0)

    def test_at_risk_duty(self):
        # report 06:00 (exact Table B 0600-0659, 3 segments -> 12 h),
        # duty 11 h 15 m -> margin +45 min => at_risk (below AT_RISK_MIN)
        c = Crew("CREW-AT", "SFO", "P")
        cc = self.eng.check(c, [duty("CREW-AT", 0, 6, 0, 17, 15, 3, 380)])
        v = next((v for v in cc.violations if v.rule_id == "FAR117.fdp-per-duty"), None)
        self.assertIsNotNone(v)
        self.assertEqual(v.severity, "at_risk")
        self.assertTrue(0 <= v.margin_min < AT_RISK_MIN)


class TestRest(unittest.TestCase):
    def test_rest_violation(self):
        eng = RuleEngine("FAR117")
        c = Crew("CREW-R", "SFO", "P")
        events = [duty("CREW-R", 1, 10, 0, 23, 30, 2, 300),
                  duty("CREW-R", 2, 8, 0, 16, 0, 2, 300)]  # 8.5 h rest
        cc = eng.check(c, events)
        v = next((v for v in cc.violations if v.rule_id == "FAR117.rest-min"), None)
        self.assertIsNotNone(v)
        self.assertEqual(v.severity, "violation")


class TestAccumulators(unittest.TestCase):
    def test_flight_672h(self):
        eng = RuleEngine("FAR117")
        c = Crew("CREW-FT", "SFO", "P", hist_flight_672h=99 * 60)
        cc = eng.check(c, [duty("CREW-FT", 0, 8, 0, 12, 0, 2, 120)])  # +2h -> 101h
        self.assertIn("FAR117.ft-672h", [v.rule_id for v in cc.violations])

    def test_duty_168h(self):
        eng = RuleEngine("FAR117")
        c = Crew("CREW-DU", "SFO", "P", hist_duty_168h=59 * 60)
        cc = eng.check(c, [duty("CREW-DU", 0, 8, 0, 11, 0, 2, 150)])  # +3h duty -> 62h
        self.assertIn("FAR117.duty-168h", [v.rule_id for v in cc.violations])


class TestExactTables(unittest.TestCase):
    """Locks the FAR 117 Table B/C values fetched from eCFR (2025-01-01)."""

    def setUp(self):
        self.eng = RuleEngine("FAR117")

    def limit(self, h, m, segs, aug=False, cls=1, pilots=3):
        return self.eng.fdp_limit_min(hm(0, h, m), segs, augmented=aug,
                                      aug_class=cls, aug_pilots=pilots)

    def test_table_b_spot_values(self):
        self.assertEqual(self.limit(2, 0, 5), 9 * 60)          # 0000-0359 any segs
        self.assertEqual(self.limit(4, 0, 5), 9 * 60)          # 0400-0459, 5 segs
        self.assertEqual(self.limit(4, 0, 2), 10 * 60)         # 0400-0459, 2 segs
        self.assertEqual(self.limit(5, 0, 4), 12 * 60)         # 0500-0559, 4
        self.assertEqual(self.limit(8, 0, 2), 14 * 60)         # 0700-1159, 2
        self.assertEqual(self.limit(8, 0, 7), 11.5 * 60)       # 0700-1159, 7+ -> 11.5h
        self.assertEqual(self.limit(20, 0, 5), 10 * 60)        # 1700-2159, 5
        self.assertEqual(self.limit(22, 0, 3), 10 * 60)        # 2200-2259, 3
        self.assertEqual(self.limit(23, 0, 4), 9 * 60)         # 2300-2359, 4

    def test_table_c_spot_values(self):
        self.assertEqual(self.limit(8, 0, 2, aug=True, cls=1, pilots=3), 17 * 60)
        self.assertEqual(self.limit(8, 0, 2, aug=True, cls=1, pilots=4), 19 * 60)
        self.assertEqual(self.limit(8, 0, 2, aug=True, cls=3, pilots=3), 15 * 60)
        self.assertEqual(self.limit(3, 0, 2, aug=True, cls=2, pilots=4), 15.5 * 60)

    def test_unacclimated_reduction(self):
        self.assertEqual(
            self.eng.fdp_limit_min(hm(0, 8, 0), 2, acclimated=False),
            self.limit(8, 0, 2) - 30)


class TestEasaTable(unittest.TestCase):
    """EASA FTL Annex III Table 2 (max daily FDP, acclimatised) — values from
    the official Regulation (EU) 83/2014 PDF (EUR-Lex), extracted this build."""

    def setUp(self):
        self.eng = RuleEngine("EASA-FTL")

    def test_peak_band(self):
        # 06:00-13:29 start
        self.assertEqual(self.eng.fdp_limit_min(hm(0, 8, 0), 2), 780)    # 13:00
        self.assertEqual(self.eng.fdp_limit_min(hm(0, 8, 0), 3), 750)    # 12:30
        self.assertEqual(self.eng.fdp_limit_min(hm(0, 8, 0), 5), 690)    # 11:30
        self.assertEqual(self.eng.fdp_limit_min(hm(0, 8, 0), 9), 570)    # 09:30
        self.assertEqual(self.eng.fdp_limit_min(hm(0, 8, 0), 12), 540)   # capped at 10+

    def test_evening_and_midnight_wrap(self):
        self.assertEqual(self.eng.fdp_limit_min(hm(0, 18, 0), 2), 660)   # 17:00-04:59 band
        self.assertEqual(self.eng.fdp_limit_min(hm(0, 23, 0), 3), 630)   # 10:30
        self.assertEqual(self.eng.fdp_limit_min(hm(0, 2, 0), 4), 600)    # 10:00 (wrap row)

    def test_early_morning_subbands(self):
        self.assertEqual(self.eng.fdp_limit_min(hm(0, 5, 10), 2), 720)   # 12:00
        self.assertEqual(self.eng.fdp_limit_min(hm(0, 5, 20), 3), 705)   # 11:45
        self.assertEqual(self.eng.fdp_limit_min(hm(0, 5, 50), 2), 765)   # 12:45

    def test_mid_afternoon(self):
        self.assertEqual(self.eng.fdp_limit_min(hm(0, 14, 45), 3), 705)  # 11:45

    def test_easa_legal_crew(self):
        c = Crew("CREW-EASA", "SFO", "P")
        cc = self.eng.check(c, [duty("CREW-EASA", 0, 6, 0, 17, 15, 3, 380)])
        v = next((v for v in cc.violations if v.rule_id == "EASA-FTL.fdp-per-duty"), None)
        self.assertIsNone(v)   # duty 11h15 < 12h30 limit -> legal


class TestEasa(unittest.TestCase):
    def test_year_cap(self):
        eng = RuleEngine("EASA-FTL")
        c = Crew("CREW-Y", "SFO", "P", hist_flight_365d=899 * 60)
        cc = eng.check(c, [duty("CREW-Y", 0, 8, 0, 12, 0, 2, 120)])  # +2h -> 901h
        self.assertIn("EASA-FTL.ft-year", [v.rule_id for v in cc.violations])

    def test_28d_cap(self):
        eng = RuleEngine("EASA-FTL")
        c = Crew("CREW-28", "SFO", "P", hist_flight_672h=99 * 60)
        cc = eng.check(c, [duty("CREW-28", 0, 8, 0, 12, 0, 2, 120)])
        self.assertIn("EASA-FTL.ft-28d", [v.rule_id for v in cc.violations])


if __name__ == "__main__":
    unittest.main(verbosity=2)