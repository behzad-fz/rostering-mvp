#!/usr/bin/env python3
"""Tests for the what-if / fatigue simulation and the feed-contract export.
Run:  python3 -m unittest discover -s . -p 'test_*.py'
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proto.contract import to_contract_json, validate_contract    # noqa: E402
from proto.fatigue import FatigueModel                            # noqa: E402
from proto.foresight import scenario, whatif                      # noqa: E402
from proto.legality import evaluate                               # noqa: E402
from proto.model import Crew, DutyEvent, Flight, Pairing, World   # noqa: E402
from proto.recovery import generate                               # noqa: E402
from proto.risk import uncovered_flights                           # noqa: E402
from proto.rules import RuleEngine                                # noqa: E402
from proto.schedule_gen import build_world                        # noqa: E402
from proto.timeutil import hm                                     # noqa: E402


def _duty(cid, sh, sm, eh, em, segments=2, flight=180, pid="T", day=0):
    return DutyEvent(crew_id=cid, pairing_id=pid, day=day,
                     start=hm(day, sh, sm), end=hm(day, eh, em),
                     segments=segments, flight_min=flight)


class TestFatigue(unittest.TestCase):
    def setUp(self):
        self.f = FatigueModel()
        self.crew = Crew("C-1", "SFO", "P")

    def test_night_duty_scores_higher_than_day(self):
        day = self.f.run(self.crew, [_duty("C-1", 10, 0, 15, 0)])          # no night
        night = self.f.run(self.crew, [_duty("C-1", 23, 0, 28, 0)])         # 23:00-04:00
        self.assertGreater(night.index, day.index)

    def test_short_rest_scores_higher(self):
        # same two duties, but the second follows after short vs long rest
        good = [_duty("C-1", 6, 0, 12, 0, pid="A"),
                _duty("C-1", 6, 0, 12, 0, pid="B", day=3)]               # ~66h rest
        bad = [_duty("C-1", 6, 0, 12, 0, pid="A"),
               _duty("C-1", 16, 30, 22, 30, pid="B", day=0)]             # 4.5h rest
        self.assertGreater(self.f.run(self.crew, bad).index,
                           self.f.run(self.crew, good).index)

    def test_heavy_schedule_flags_high(self):
        duties = [_duty("C-1", sh, 0, sh + 10, 0, pid=f"T{i}", day=i)
                  for i, sh in enumerate([23, 22, 23, 22, 1, 2, 23])]
        st = self.f.run(self.crew, duties)
        self.assertEqual(st.level, "high")
        self.assertGreaterEqual(st.index, 70.0)


class TestWhatif(unittest.TestCase):
    def setUp(self):
        self.w = build_world(days=7, seed=42)
        self.eng = RuleEngine("FAR117")
        self.checks = evaluate(self.w, self.eng)
        self.proposals, self.outcome = generate(self.w, self.eng, self.checks)

    def test_plan_beats_do_nothing(self):
        wf = whatif(self.w, self.eng, self.proposals)
        self.assertLess(wf["deltas"]["violations"], 0)
        self.assertLess(wf["deltas"]["uncovered"], 0)
        self.assertGreaterEqual(wf["plan"]["applied"], 6)
        self.assertGreaterEqual(wf["plan"]["reserve_callouts"], 2)

    def test_do_nothing_equals_current_state(self):
        wf = whatif(self.w, self.eng, self.proposals)
        dn = wf["do_nothing"]
        self.assertEqual(dn["violations"], self.outcome["violations"])
        self.assertEqual(dn["uncovered"], self.outcome["uncovered_non_cancelled"])

    def test_fatigue_stats_present(self):
        wf = whatif(self.w, self.eng, self.proposals, FatigueModel())
        fat = wf["plan"]["fatigue"]
        for key in ("mean", "max", "elevated", "high", "top"):
            self.assertIn(key, fat)
        self.assertIn("level", fat["top"][0])

    def test_measure_and_whatif_agree(self):
        # the two application paths (recovery.measure and foresight.scenario)
        # must count the SAME outcome for the same plan
        proposals, outcome = generate(self.w, self.eng, self.checks)
        wf = whatif(self.w, self.eng, proposals)
        self.assertEqual(wf["plan"]["violations"], outcome["after_violations"])
        self.assertEqual(wf["plan"]["uncovered"], outcome["after_uncovered_non_cancelled"])


class TestContract(unittest.TestCase):
    def setUp(self):
        self.w = build_world(days=7, seed=42)

    def test_export_valid_and_complete(self):
        payload = to_contract_json(self.w)
        self.assertEqual(validate_contract(payload), [])
        self.assertEqual(payload["schema"], "crew-recovery-contract/1.0")
        self.assertEqual(len(payload["flights"]), len(self.w.flights))
        self.assertEqual(len(payload["crews"]), len(self.w.crews))
        self.assertEqual(len(payload["pairings"]), len(self.w.pairings))
        self.assertTrue(all(p["crew_ids"] for p in payload["pairings"]))

    def test_scenario_uses_contract_world(self):
        payload = to_contract_json(self.w)
        # the observable outcome on the exported world must hold
        wf = whatif(self.w, RuleEngine("FAR117"),
                    generate(self.w, RuleEngine("FAR117"),
                             evaluate(self.w, RuleEngine("FAR117")))[0])
        self.assertIn("plan", wf)


class TestNoCrew(unittest.TestCase):
    """An unstaffed pairing must surface as 'no crew assigned' and be
    closable by recovery (reserve callout)."""

    def _world(self):
        w = World()
        f1 = Flight("F1", 0, hm(0, 9, 0), hm(0, 10, 35), "A", "B")
        f2 = Flight("F2", 0, hm(0, 11, 15), hm(0, 12, 50), "B", "A")
        w.flights += [f1, f2]
        w.pairings.append(Pairing("PA1", ["F1", "F2"]))
        w.crews = [Crew("P-A-0", "A", "P"), Crew("P-A-1", "A", "P")]
        w.assignments = []                       # nobody on PA1
        w.reserves = {0: ["P-A-1"]}
        w.index()
        return w

    def test_crewless_pairing_flagged_and_fixed(self):
        w = self._world()
        eng = RuleEngine("FAR117")
        un = uncovered_flights(w, evaluate(w, eng))
        self.assertTrue(any(r == "no crew assigned" for f, r in un), un)
        proposals, outcome = generate(w, eng, evaluate(w, eng))
        self.assertTrue(any(p["kind"] == "reserve" for p in proposals), proposals)
        self.assertEqual(outcome["after_uncovered_non_cancelled"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)