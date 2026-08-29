#!/usr/bin/env python3
"""Tests for the benchmark / sensitivity harness.
Run:  python3 -m unittest discover -s . -p 'test_*.py'
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bench as benchmod  # noqa: E402


class TestBench(unittest.TestCase):
    def test_single_case_metrics_sane(self):
        r = benchmod.run_case("FAR117", "bank", 180, "SFO", 2, 6, 1)
        self.assertLessEqual(r["plan"]["violations"], r["do_nothing"]["violations"])
        self.assertLessEqual(r["plan"]["uncovered"], r["do_nothing"]["uncovered"])
        self.assertGreaterEqual(r["closure_pct"], 0.0)
        self.assertGreaterEqual(r["runtime_ms"], 0.0)
        self.assertIn("covered", r["picker"])

    def test_plan_never_worse_than_do_nothing_across_quick_grid(self):
        for case in benchmod.build_grid(quick=True):
            r = benchmod.run_case(*case)
            self.assertLessEqual(r["plan"]["violations"],
                                 r["do_nothing"]["violations"], r["case"])
            self.assertLessEqual(r["plan"]["uncovered"],
                                 r["do_nothing"]["uncovered"], r["case"])

    def test_control_case_is_no_disruption(self):
        r = benchmod.run_case("FAR117", "bank", 0, "SFO", 2, 0, 0)
        # no disruption applied: do-nothing equals the baked-in baseline
        self.assertEqual(r["do_nothing"]["uncovered"],
                         r["plan"]["uncovered"] + r["uncovered_closed"])
        self.assertGreaterEqual(r["uncovered_closed"], 0)

    def test_targeted_stress_increases_damage(self):
        calm = benchmod.run_case("FAR117", "bank", 0, "SFO", 2, 0, 0)
        stressed = benchmod.run_case("FAR117", "targeted", 240, "SFO", 2, 0, 1)
        # delaying the legality-critical crews must make things worse without
        # a plan, and the plan must still close everything
        self.assertGreater(stressed["do_nothing"]["uncovered"],
                           calm["do_nothing"]["uncovered"])
        self.assertEqual(stressed["plan"]["uncovered"], 0)

    def test_emit_reports(self):
        with tempfile.TemporaryDirectory() as td:
            grid = benchmod.build_grid(quick=True)[:3]
            results = [benchmod.run_case(*c) for c in grid]
            benchmod.emit_reports(results, benchmod.summarize(results), td)
            self.assertTrue(os.path.exists(os.path.join(td, "bench_results.json")))
            self.assertTrue(os.path.exists(os.path.join(td, "bench_report.html")))


if __name__ == "__main__":
    unittest.main(verbosity=2)