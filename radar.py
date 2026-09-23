#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar.py — structural maturity radar (part of agent-skill-doctor)

Scan a directory of agent skills and rank "which one deserves the second
hands-on iteration". Purely structural: no usage telemetry, no host-specific
evidence stores — this is the open-source half.

Form typing:
  CODE  the skill ships executable scripts (scripts/data/bin or top-level
        .py/.js) -> improvements can be tested, code-level loop is possible
  DOC   prose only -> "improvement" means editing text; nothing is falsifiable

Per-skill signals (all read-only):
  - form (CODE/DOC), #code files, #test files (test_* / *_test / tests dir)
  - selftest hook present in any script (--selftest / selftest())
  - frontmatter complete (name/description/version)
  - doctor findings folded in (FAIL/WARN counts)

Usage:
  python radar.py <skills_root>             # human-readable table + queue
  python radar.py <skills_root> --json      # machine-readable (stdout)

Exit codes: 0 = ran, 1 = runtime error.
"""
import json
import os
import sys

try:
    import doctor  # same directory
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import doctor

CODE_EXT = (".py", ".js", ".mjs", ".sh", ".ps1", ".ts")
TEST_HINTS = ("test_", "_test.", "tests", "selftest")


def is_test_file(fn):
    low = fn.lower()
    return any(h in low for h in TEST_HINTS)


def scan_skill(sd):
    code, tests, has_selftest = 0, 0, False
    for fp in doctor.iter_code_files(sd):
        code += 1
        if is_test_file(os.path.basename(fp)):
            tests += 1
        try:
            with open(fp, encoding="utf-8", errors="ignore") as fh:
                src = fh.read()
        except OSError:
            continue
        if "--selftest" in src or "def selftest" in src or "runSelftest" in src:
            has_selftest = True
    findings = doctor.run(sd)
    fails = sum(1 for f in findings if f["level"] == "FAIL")
    warns = sum(1 for f in findings if f["level"] == "WARN")
    try:
        mtime = max(
            os.stat(os.path.join(cur, f)).st_mtime
            for cur, _d, fs in os.walk(sd) for f in fs
        )
    except (ValueError, OSError):
        mtime = 0.0
    return {
        "skill": os.path.basename(sd),
        "form": "CODE" if code else "DOC",
        "code_files": code,
        "test_files": tests,
        "selftest": has_selftest,
        "fail": fails,
        "warn": warns,
        "mtime": mtime,
    }


def iter_skills(root):
    for name in sorted(os.listdir(root)):
        sd = os.path.join(root, name)
        if os.path.isdir(sd) and os.path.isfile(os.path.join(sd, "SKILL.md")):
            yield sd


def rank(rows):
    """Pain queue first: CODE skills with zero tests/selftest and findings,
    then DOC skills (nothing falsifiable), healthy CODE last."""
    def key(r):
        pain = 0
        if r["form"] == "CODE":
            pain -= 4
            if not r["test_files"] and not r["selftest"]:
                pain -= 2
            if r["fail"]:
                pain -= 2
        return (pain, r["warn"], -r["mtime"], r["skill"])
    return sorted(rows, key=key)


def main(argv):
    args = [a for a in argv if a != "--json"]
    as_json = len(args) != len(argv)
    if not args:
        print("usage: python radar.py <skills_root> [--json]")
        sys.exit(1)
    root = args[0]
    if not os.path.isdir(root):
        print("not a directory: %s" % root)
        sys.exit(1)
    rows = [scan_skill(sd) for sd in iter_skills(root)]
    queue = rank(rows)
    payload = {"tool": "agent-skill-doctor-radar", "skills_root": root,
               "count": len(rows),
               "summary": {
                   "code": sum(1 for r in rows if r["form"] == "CODE"),
                   "doc": sum(1 for r in rows if r["form"] == "DOC"),
                   "code_without_tests": sum(1 for r in rows
                                             if r["form"] == "CODE"
                                             and not r["test_files"] and not r["selftest"]),
                   "with_findings": sum(1 for r in rows if r["fail"] or r["warn"]),
               },
               "queue": queue}
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        s = payload["summary"]
        print("scanned %d skills | CODE=%d DOC=%d | CODE w/o tests=%d | with findings=%d"
              % (len(rows), s["code"], s["doc"], s["code_without_tests"], s["with_findings"]))
        print("\nPain queue (top 20) — highest pain first:")
        for r in queue[:20]:
            flag = "!" if r["fail"] else ("w" if r["warn"] else " ")
            print("  [%s] %-5s %-30s code=%d tests=%d selftest=%s fail=%d warn=%d"
                  % (flag, r["form"], r["skill"], r["code_files"],
                     r["test_files"], "Y" if r["selftest"] else "N", r["fail"], r["warn"]))
    sys.exit(0)


if __name__ == "__main__":
    main(sys.argv[1:])
