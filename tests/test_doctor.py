#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent-skill-doctor test suite.

Mutation-testing flavored: the negative fixture MUST produce FAILs (and the
CLI MUST exit 3 on it), the positive fixture MUST come back clean (exit 0).
A doctor that cannot catch a sick skill is worse than no doctor.
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(ROOT, "fixtures")
GOOD = os.path.join(FIX, "good-skill")
BAD = os.path.join(FIX, "broken-skill")

sys.path.insert(0, ROOT)
import doctor  # noqa: E402
import radar  # noqa: E402


class T1DoctorLibrary(unittest.TestCase):
    def test_good_skill_clean(self):
        findings = doctor.run(GOOD)
        fails = [f for f in findings if f["level"] == "FAIL"]
        self.assertEqual(fails, [], "positive fixture must have zero FAIL: %s" % fails)
        self.assertEqual([f["level"] for f in findings if f["level"] == "WARN"], [],
                         "positive fixture should be fully clean (no warns)")

    def test_broken_skill_caught(self):
        findings = doctor.run(BAD)
        fails = [f["item"] for f in findings if f["level"] == "FAIL"]
        self.assertIn("frontmatter: description missing", fails)
        self.assertIn("referenced file missing", fails)
        self.assertTrue(any("compile" in i for i in fails), "syntax error must be caught: %s" % fails)

    def test_missing_dir_rejected(self):
        with self.assertRaises(SystemExit) as cm:
            doctor.main(["/nonexistent/definitely-gone", "--json"])
        self.assertEqual(cm.exception.code, 1)


class T2DoctorCLI(unittest.TestCase):
    def _run(self, *args):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "doctor.py")] + list(args),
                           capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout

    def test_positive_exit_zero(self):
        rc, out = self._run(GOOD)
        self.assertEqual(rc, 0, "clean skill must exit 0, got %d: %s" % (rc, out))

    def test_negative_exit_three(self):
        rc, out = self._run(BAD)
        self.assertEqual(rc, 3, "sick skill must exit 3, got %d: %s" % (rc, out))

    def test_json_parseable(self):
        rc, out = self._run(GOOD, "--json")
        self.assertEqual(rc, 0)
        d = json.loads(out)
        self.assertEqual(d["status"], "PASS")
        self.assertEqual(d["skill"], "good-skill")

    def test_all_mode_counts_both(self):
        rc, out = self._run("--all", FIX, "--json")
        self.assertEqual(rc, 0)
        d = json.loads(out)
        self.assertEqual(d["count"], 2)
        by_name = {r["skill"]: r for r in d["results"]}
        self.assertEqual(by_name["good-skill"]["status"], "PASS")
        self.assertEqual(by_name["broken-skill"]["status"], "FAIL")


class T3Radar(unittest.TestCase):
    def test_form_typing(self):
        rows = {r["skill"]: r for r in (radar.scan_skill(sd) for sd in radar.iter_skills(FIX))}
        self.assertEqual(rows["good-skill"]["form"], "CODE")
        self.assertGreaterEqual(rows["good-skill"]["test_files"], 1)
        self.assertEqual(rows["broken-skill"]["form"], "CODE")
        self.assertGreaterEqual(rows["broken-skill"]["fail"], 3)

    def test_queue_puts_pain_first(self):
        rows = [radar.scan_skill(sd) for sd in radar.iter_skills(FIX)]
        q = radar.rank(rows)
        self.assertEqual(q[0]["skill"], "broken-skill",
                         "sick CODE skill must rank above healthy one")

    def test_summary_consistent(self):
        rc, out = self._radar_json()
        self.assertEqual(rc, 0)
        d = json.loads(out)
        self.assertEqual(d["count"], 2)
        self.assertEqual(d["summary"]["code"] + d["summary"]["doc"], 2)
        self.assertEqual(d["summary"]["code_without_tests"], 1,
                         "broken-skill is CODE with no tests")

    def _radar_json(self):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "radar.py"), FIX, "--json"],
                           capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout


if __name__ == "__main__":
    unittest.main(verbosity=2)
