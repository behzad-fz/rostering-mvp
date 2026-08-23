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
        # report 05:00 (start band 05-06), 3+ segments -> limit 11 h;
        # duty of 12.5 h must violate
        c = Crew("CREW-BAD", "SFO", "P")
        cc = self.eng.check(c, [duty("CREW-BAD", 0, 5, 0, 17, 30, 4, 480)])
        rules = [v.rule_id for v in cc.violations]
        self.assertIn("FAR117.fdp-per-duty", rules)
        v = next(v for v in cc.violations if v.rule_id == "FAR117.fdp-per-duty")
        self.assertEqual(v.severity, "violation")
        self.assertLess(v.margin_min, 0)

    def test_at_risk_duty(self):
        # report 07:00 (band 07-12, 3+ segments -> 12 h), duty 11 h 25 m
        # -> margin +35 min => at_risk (below AT_RISK_MIN)
        c = Crew("CREW-AT", "SFO", "P")
        cc = self.eng.check(c, [duty("CREW-AT", 0, 7, 0, 18, 25, 4, 460)])
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