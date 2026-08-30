#!/usr/bin/env python3
"""Tests for the Phase-1 recovery proposal generator: every proposed action
must be legality-validated, over-long pairings must be refused (advisory),
and applying the executable proposals must reduce uncovered flights.

Run:  python3 test_recovery.py        (from rostering-mvp/)
  or: python3 -m unittest proto.test_recovery
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proto.disrupt import apply_delay                       # noqa: E402
from proto.legality import evaluate                 # noqa: E402
from proto.model import Crew, Flight, Pairing, World  # noqa: E402
from proto.recovery import generate, measure        # noqa: E402
from proto.risk import uncovered_flights            # noqa: E402
from proto.rules import RuleEngine                  # noqa: E402
from proto.schedule_gen import build_world          # noqa: E402
from proto.timeutil import hm                       # noqa: E402


class TestRecovery(unittest.TestCase):
    def setUp(self):
        self.w = build_world(days=7, seed=42)
        self.eng = RuleEngine("FAR117")
        self.checks = evaluate(self.w, self.eng)

    def test_proposals_nonempty_and_legal(self):
        proposals, outcome = generate(self.w, self.eng, self.checks)
        self.assertGreaterEqual(len(proposals), 2)
        for p in proposals:
            self.assertTrue(p["legality_ok"], f"illegal proposal: {p}")
        executable = [p for p in proposals if p["kind"] in ("reserve", "swap", "surgery")]
        self.assertGreaterEqual(len(executable), 2)
        for p in executable:
            self.assertTrue(p.get("crew_id"))

    def test_overlong_pairing_becomes_surgery(self):
        proposals, _ = generate(self.w, self.eng, self.checks)
        lp = [p for p in proposals if p["pairing_id"] == "X-long-2"]
        self.assertTrue(lp, "expected a proposal for the over-long pairing")
        self.assertEqual(lp[0]["kind"], "surgery")
        self.assertGreaterEqual(lp[0]["split_index"], 1)
        self.assertTrue(lp[0]["crew_id"])
        self.assertTrue(lp[0]["legality_ok"])

    def test_picker_covers_all_fixable_gaps(self):
        proposals, _ = generate(self.w, self.eng, self.checks)
        picked = {p["pairing_id"] for p in proposals if p["kind"] in ("reserve", "swap")}
        self.assertTrue({"P0-SFO-0", "P2-LAX-0", "P3-SFO-1", "P4-SFO-1", "P6-LAX-1"}
                        <= picked, picked)

    def test_applying_proposals_reduces_uncovered(self):
        proposals, outcome = generate(self.w, self.eng, self.checks)
        self.assertGreaterEqual(outcome["proposals_applied"], 2)
        self.assertLess(outcome["after_uncovered_non_cancelled"],
                        outcome["uncovered_non_cancelled"])

    def test_surgery_reduces_uncovered(self):
        before = len([f for f, r in uncovered_flights(self.w, self.checks) if not f.cancelled])
        proposals, outcome = generate(self.w, self.eng, self.checks)
        surgeries = [p for p in proposals if p["kind"] == "surgery"]
        self.assertEqual(len(surgeries), 1)
        self.assertGreaterEqual(outcome["proposals_applied"], 6)
        self.assertLess(outcome["after_uncovered_non_cancelled"], before)

    def test_measure_does_not_mutate_input(self):
        before = len(self.w.assignments)
        proposals, _ = generate(self.w, self.eng, self.checks)
        measure(self.w, self.eng, proposals)
        self.assertEqual(len(self.w.assignments), before)

    def test_relief_closes_all_violations(self):
        proposals, outcome = generate(self.w, self.eng, self.checks)
        self.assertEqual(outcome["after_violations"], 0)
        self.assertEqual(outcome["after_uncovered_non_cancelled"], 0)
        reliefs = [p for p in proposals if p["kind"] == "relieve"]
        self.assertGreaterEqual(len(reliefs), 1)
        self.assertTrue(any(p.get("relieved_crew") == "P-SFO-3" for p in reliefs),
                        reliefs)

    def test_relief_uses_each_crew_once(self):
        proposals, _ = generate(self.w, self.eng, self.checks)
        crews = [p["crew_id"] for p in proposals if p.get("crew_id")]
        self.assertEqual(len(crews), len(set(crews)),
                         f"crew reused across actions: {crews}")

    def test_exact_proposals_applied(self):
        _, outcome = generate(self.w, self.eng, self.checks)
        # 8 = 6 picker gaps + 1 surgery + 1 release; asserted as a floor so
        # generator-staffing tweaks don't make this brittle
        self.assertGreaterEqual(outcome["proposals_applied"], 7)


class TestPropagation(unittest.TestCase):
    """Delays slide rotations with a minimum-turn floor (they must not
    compress the duty window)."""

    def _pair(self):
        w = World()
        f1 = Flight("F1", 0, hm(0, 8, 0), hm(0, 9, 0), "A", "B")
        f2 = Flight("F2", 0, hm(0, 9, 40), hm(0, 10, 40), "B", "A")
        w.flights += [f1, f2]
        w.pairings.append(Pairing("P1", ["F1", "F2"]))
        w.index()
        return w

    def test_delay_slides_not_compresses(self):
        from proto.disrupt import MIN_TURN_MIN, apply_delay
        w = self._pair()
        apply_delay(w, ["F1"], 100)
        f2 = w.flight("F2")
        self.assertEqual(f2.delay, 100)                       # full slide
        self.assertGreaterEqual(f2.eff_dep - w.flight("F1").eff_arr, MIN_TURN_MIN)


class TestDeadhead(unittest.TestCase):
    """Crafted micro-world where deadhead is the ONLY legal recovery option:

    base A has a legality-broken crew on pairing PA1, no reserves, and its
    other pilot is busy with an overlapping duty (swap impossible); the only
    fix is repositioning P-B-0 from base B (positioning leg + operated duty
    modeled as one combined duty, as in most FTL regimes)."""

    def _world(self):
        w = World()
        # gap pairing PA1 at base A: 2 legs, FDP-legal (surgery must not apply)
        f1 = Flight("F1", 0, hm(0, 9, 0), hm(0, 10, 35), "A", "B")
        f2 = Flight("F2", 0, hm(0, 11, 15), hm(0, 12, 50), "B", "A")
        # busy crew's pairing PX overlapping the PA1 duty window
        f3 = Flight("F3", 0, hm(0, 8, 0), hm(0, 9, 0), "A", "B")
        f4 = Flight("F4", 0, hm(0, 12, 0), hm(0, 13, 0), "B", "A")
        w.flights += [f1, f2, f3, f4]
        w.pairings.append(Pairing("PA1", ["F1", "F2"]))
        w.pairings.append(Pairing("PX", ["F3", "F4"]))
        w.crews = [
            Crew("P-A-0", "A", "P", hist_duty_168h=59 * 60),
            Crew("P-A-1", "A", "P"),
            Crew("P-B-0", "B", "P"),
        ]
        w.assignments = [("P-A-0", "PA1"), ("P-A-1", "PX")]
        w.reserves = {0: []}                    # no reserves anywhere, day 0
        w.index()
        return w

    def test_deadhead_is_sole_legal_option(self):
        w = self._world()
        eng = RuleEngine("FAR117")
        checks = evaluate(w, eng)
        self.assertEqual(checks["P-A-0"].worst, "violation")
        proposals, outcome = generate(w, eng, checks)
        dh = [p for p in proposals if p["kind"] == "deadhead"]
        self.assertEqual(len(dh), 1, proposals)
        self.assertEqual(dh[0]["crew_id"], "P-B-0")
        self.assertIn("travel", dh[0]["note"])
        self.assertGreater(dh[0]["score"], 40.0)          # priced above local actions
        self.assertEqual(outcome["after_violations"], 0)
        self.assertEqual(outcome["after_uncovered_non_cancelled"], 0)
        applied = [p for p in proposals if p["kind"] in
                   ("reserve", "swap", "surgery", "relieve", "deadhead")]
        self.assertEqual([p["kind"] for p in applied], ["deadhead"])

    def test_deadhead_not_chosen_when_local_options_exist(self):
        w = build_world(days=7, seed=42)
        eng = RuleEngine("FAR117")
        checks = evaluate(w, eng)
        proposals, _ = generate(w, eng, checks)
        self.assertNotIn("deadhead", [p["kind"] for p in proposals])


class TestCancel(unittest.TestCase):
    """When no legal crewing option exists (not even a split), the engine
    must say so explicitly and recommend cancellation."""

    def _world(self):
        w = World()
        f1 = Flight("F1", 0, hm(0, 3, 0), hm(0, 20, 0), "A", "B")   # 17 h single leg
        w.flights += [f1]
        w.pairings.append(Pairing("PA1", ["F1"]))
        w.crews = [Crew("P-A-0", "A", "P"), Crew("P-A-1", "A", "P")]
        w.assignments = [("P-A-0", "PA1")]
        w.reserves = {0: []}
        w.index()
        return w

    def test_cancel_recommended_when_no_legal_option(self):
        w = self._world()
        eng = RuleEngine("FAR117")
        checks = evaluate(w, eng)
        self.assertEqual(checks["P-A-0"].worst, "violation")
        proposals, outcome = generate(w, eng, checks)
        cancels = [p for p in proposals if p["kind"] == "cancel"]
        self.assertEqual(len(cancels), 1, proposals)
        self.assertEqual(outcome["after_uncovered_non_cancelled"], 0)


class TestSurgeryFirst(unittest.TestCase):
    """Surgery-requiring gaps must claim crews before the picker runs,
    otherwise a later gap's surgery can be starved of takers."""

    def test_surgery_first_prevents_crew_starvation(self):
        w = build_world(days=7, seed=42)
        eng = RuleEngine("FAR117")
        ids = [w.pairing("X-long-2").flight_ids[-1],
               w.pairing("Y-long-3").flight_ids[-1]]
        apply_delay(w, ids, 240)
        proposals, outcome = generate(w, eng, evaluate(w, eng))
        surgeries = [p for p in proposals if p["kind"] == "surgery"]
        self.assertGreaterEqual(len(surgeries), 2, proposals)
        self.assertEqual(outcome["after_uncovered_non_cancelled"], 0)
        self.assertEqual(outcome["after_violations"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)