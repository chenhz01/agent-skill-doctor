#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent-skill-doctor test suite.

Mutation-testing flavored: the negative fixture MUST produce FAILs (and the
CLI MUST exit 3 on it), the positive fixture MUST come back clean (exit 0).
A doctor that cannot catch a sick skill is worse than no doctor.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(ROOT, "fixtures")
GOOD = os.path.join(FIX, "good-skill")
BAD = os.path.join(FIX, "broken-skill")

sys.path.insert(0, ROOT)
import doctor  # noqa: E402
import graph  # noqa: E402
import ledger  # noqa: E402
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


def _copy_fixtures(tmp):
    dst = os.path.join(tmp, "skills")
    shutil.copytree(FIX, dst)
    return dst


class T4Ledger(unittest.TestCase):
    def test_entries_have_stable_fingerprints(self):
        a = ledger.build(FIX)
        b = ledger.build(FIX)
        by = {s["dir"]: s for s in b["skills"]}
        self.assertEqual(a["total"], 2)
        for s in a["skills"]:
            self.assertRegex(s["sha16"], r"^[0-9a-f]{16}$")
            self.assertEqual(s["sha16"], by[s["dir"]]["sha16"],
                             "fingerprint must be deterministic across runs")

    def test_declared_version_extracted_and_garbage_rejected(self):
        rows = {s["dir"]: s for s in ledger.build(FIX)["skills"]}
        self.assertEqual(rows["good-skill"]["version"], "1.0.0")
        self.assertIsNone(rows["broken-skill"]["version"],
                          "no version declared -> must stay None, never guessed")

    def test_version_in_fence_is_not_the_skill_version(self):
        text = "Example:\n```\nLangGraph v0.2.0 released\n```\n"
        self.assertIsNone(ledger.extract_version(text),
                          "fenced tokens belong to external subjects")

    def test_all_checks_pass_on_good_skill(self):
        rows = {s["dir"]: s for s in ledger.build(FIX)["skills"]}
        self.assertEqual(rows["good-skill"]["score"], 4)
        self.assertEqual(rows["broken-skill"]["checks"]["has_version"], False)

    def test_tamper_report_bidirectional(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_fixtures(tmp)
            baseline = ledger.build(root)
            # tamper: modify good-skill, add new-skill, remove broken-skill
            with open(os.path.join(root, "good-skill", "SKILL.md"), "a",
                      encoding="utf-8") as fh:
                fh.write("\nTampered line.\n")
            os.makedirs(os.path.join(root, "new-skill"))
            with open(os.path.join(root, "new-skill", "SKILL.md"), "w",
                      encoding="utf-8") as fh:
                fh.write("---\nname: new-skill\ndescription: x\n---\n")
            shutil.rmtree(os.path.join(root, "broken-skill"))
            after = ledger.build(root)
            diff = ledger.diff_baseline(baseline, after)
            self.assertEqual(diff["changed"], ["good-skill"],
                             "tampered skill must show as changed")
            self.assertEqual(diff["added"], ["new-skill"])
            self.assertEqual(diff["removed"], ["broken-skill"])
            self.assertEqual(diff["unchanged"], [],
                             "after tamper nothing may be silently unchanged")


class T5Graph(unittest.TestCase):
    def _make_tree(self, tmp):
        root = os.path.join(tmp, "skills")
        os.makedirs(os.path.join(root, "skill-a"))
        os.makedirs(os.path.join(root, "skill-b"))
        os.makedirs(os.path.join(root, "skill-c"))
        with open(os.path.join(root, "skill-a", "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: skill-a\ndescription: a\n---\nUse skill-b for input.\n")
        with open(os.path.join(root, "skill-b", "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: skill-b\ndescription: b\n---\nStandalone.\n")
        with open(os.path.join(root, "skill-c", "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: skill-c\ndescription: c\n---\nLoner.\n")
        return root

    def test_edges_and_orphans(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = graph.build(self._make_tree(tmp))
            self.assertIn({"from": "skill-a", "to": "skill-b"}, g["edges"])
            self.assertEqual(g["orphans"], ["skill-c"],
                             "only the unlinked node is an orphan")

    def test_word_boundary_no_false_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_tree(tmp)
            with open(os.path.join(root, "skill-c", "SKILL.md"), "a", encoding="utf-8") as fh:
                fh.write("Mentions skill-bb, skill-bbx and skill-bb again.\n")
            g = graph.build(root)
            self.assertNotIn({"from": "skill-c", "to": "skill-b"}, g["edges"],
                             "skill-bb must not match skill-b (word boundary)")
            self.assertIn("skill-c", g["orphans"])


class T6SubcommandCLI(unittest.TestCase):
    def _run(self, *args):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "doctor.py")] + list(args),
                           capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout

    def test_ledger_subcommand(self):
        rc, out = self._run("ledger", FIX, "--json")
        self.assertEqual(rc, 0)
        d = json.loads(out)
        self.assertEqual(d["tool"], "agent-skill-doctor-ledger")
        self.assertEqual(d["total"], 2)

    def test_ledger_with_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_fixtures(tmp)
            base = os.path.join(tmp, "base.json")
            rc, out = self._run("ledger", root, "--json")
            with open(base, "w", encoding="utf-8") as fh:
                fh.write(out)
            with open(os.path.join(root, "good-skill", "SKILL.md"), "a", encoding="utf-8") as fh:
                fh.write("\nmore\n")
            rc, out = self._run("ledger", root, "--baseline", base, "--json")
            self.assertEqual(rc, 0)
            self.assertIn("good-skill", json.loads(out)["diff"]["changed"])

    def test_graph_subcommand(self):
        rc, out = self._run("graph", FIX, "--json")
        self.assertEqual(rc, 0)
        d = json.loads(out)
        self.assertEqual(d["total"], 2)

    def test_backward_compat_bare_dir_is_check(self):
        rc, out = self._run(GOOD)
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
