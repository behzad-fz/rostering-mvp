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

from proto.legality import evaluate                 # noqa: E402
from proto.recovery import generate, measure        # noqa: E402
from proto.risk import uncovered_flights            # noqa: E402
from proto.rules import RuleEngine                  # noqa: E402
from proto.schedule_gen import build_world          # noqa: E402


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
        self.assertEqual(outcome["proposals_applied"], 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)