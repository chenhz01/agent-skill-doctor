#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doctor.py — Agent Skill health selfcheck (part of agent-skill-doctor)

Static, offline, read-only health checks for a single agent skill directory
(the de-facto SKILL.md layout used by OpenAI / Anthropic / community skill
ecosystems):

  1. Frontmatter integrity --- block exists; `name` present and (warn) equal
     to the directory name; `description` non-empty; `version` declared (warn)
  2. Referenced files exist  --- backtick-quoted repo-relative paths in
     SKILL.md (scripts/..., data/..., bin/..., memory/..., assets/...,
     templates/...) must actually exist
  3. Scripts compile         --- .py via py_compile; .js via `node --check`
     (skipped with a SKIP finding if node is unavailable)

Usage:
  python doctor.py <skill_dir>            # human-readable report
  python doctor.py <skill_dir> --json     # machine-readable (stdout)
  python doctor.py --all <skills_root>    # every child dir that has SKILL.md

Exit codes: 0 = all clean, 3 = findings (FAIL and/or WARN), 1 = runtime error.
"""
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile

VERSION = "0.1.0"

REF_DIRS = ("scripts", "data", "bin", "memory", "assets", "templates")
REF_RE = re.compile(
    r"`((?:\./)?(" + "|".join(REF_DIRS) + r")/[A-Za-z0-9_\-./]+)`"
)


def check_frontmatter(skill_dir, findings):
    p = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(p):
        findings.append({"level": "FAIL", "item": "SKILL.md missing", "detail": p})
        return None
    text = open(p, encoding="utf-8", errors="ignore").read()
    if not text.lstrip().startswith("---"):
        findings.append({"level": "FAIL", "item": "frontmatter missing",
                         "detail": "does not start with ---"})
        return None
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        findings.append({"level": "FAIL", "item": "frontmatter not closed",
                         "detail": "missing closing ---"})
        return None
    fm = m.group(1)
    name = ""
    nm = re.search(r"^name:\s*(\S+)", fm, re.M)
    if not nm:
        findings.append({"level": "FAIL", "item": "frontmatter: name missing", "detail": ""})
    else:
        name = nm.group(1).strip()
        expect = os.path.basename(skill_dir)
        if name != expect:
            findings.append({"level": "WARN", "item": "name != directory name",
                             "detail": "name=%s dir=%s" % (name, expect)})
    dm = re.search(r"^description:\s*(.+)", fm, re.M)
    if not dm or not dm.group(1).strip():
        findings.append({"level": "FAIL", "item": "frontmatter: description missing", "detail": ""})
    if not re.search(r"^version:\s*\S+", fm, re.M):
        findings.append({"level": "WARN", "item": "frontmatter: version not declared",
                         "detail": "no version pin for asset tracking"})
    return name


def check_refs(skill_dir, findings):
    text = open(os.path.join(skill_dir, "SKILL.md"), encoding="utf-8", errors="ignore").read()
    refs = {m[0] for m in REF_RE.findall(text)}  # findall yields (ref, dir) tuples
    for r in sorted(refs):
        rel = r[2:] if r.startswith("./") else r
        if not os.path.exists(os.path.join(skill_dir, rel)):
            findings.append({"level": "FAIL", "item": "referenced file missing", "detail": r})


def iter_code_files(skill_dir):
    out = []
    for sub in ("scripts", "data", "bin"):
        sp = os.path.join(skill_dir, sub)
        if os.path.isdir(sp):
            for cur, _dirs, fs in os.walk(sp):
                out += [os.path.join(cur, f) for f in fs if f.endswith((".py", ".js"))]
    try:
        for f in os.listdir(skill_dir):
            fp = os.path.join(skill_dir, f)
            if os.path.isfile(fp) and f.endswith((".py", ".js")):
                out.append(fp)
    except OSError:
        pass
    return out


def check_scripts(skill_dir, findings):
    node = shutil.which("node")
    for fp in iter_code_files(skill_dir):
        rel = os.path.relpath(fp, skill_dir)
        try:
            if fp.endswith(".py"):
                py_compile.compile(fp, doraise=True,
                                   cfile=os.path.join(tempfile.gettempdir(), "_asdoc.pyc"))
            else:
                if not node:
                    findings.append({"level": "SKIP", "item": "node unavailable, syntax check skipped",
                                     "detail": rel})
                    continue
                subprocess.run([node, "--check", fp], capture_output=True, timeout=20, check=True)
        except Exception as e:
            findings.append({"level": "FAIL", "item": "script does not compile",
                             "detail": "%s: %s" % (rel, e)})


def run(skill_dir):
    findings = []
    check_frontmatter(skill_dir, findings)
    if os.path.isfile(os.path.join(skill_dir, "SKILL.md")):
        check_refs(skill_dir, findings)
    check_scripts(skill_dir, findings)
    return findings


def summarize(skill_dir, findings):
    fails = [f for f in findings if f["level"] == "FAIL"]
    return {
        "tool": "agent-skill-doctor", "version": VERSION,
        "skill": os.path.basename(skill_dir),
        "status": "PASS" if not findings else ("FAIL" if fails else "FINDINGS"),
        "fail": len(fails),
        "warn": sum(1 for f in findings if f["level"] == "WARN"),
        "skip": sum(1 for f in findings if f["level"] == "SKIP"),
        "findings": findings,
    }


def main(argv):
    args = list(argv)
    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    try:
        if args and args[0] == "--all":
            root = args[1]
            results = []
            for name in sorted(os.listdir(root)):
                sd = os.path.join(root, name)
                if os.path.isdir(sd) and os.path.isfile(os.path.join(sd, "SKILL.md")):
                    results.append(summarize(sd, run(sd)))
            payload = {"skills_root": root, "count": len(results), "results": results}
            if as_json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                for r in results:
                    print("[%s] %s  FAIL=%d WARN=%d SKIP=%d"
                          % (r["skill"], r["status"], r["fail"], r["warn"], r["skip"]))
            sys.exit(0)
        if not args:
            print("usage: python doctor.py <skill_dir> [--json] | --all <skills_root>")
            sys.exit(1)
        skill_dir = args[0]
        if not os.path.isdir(skill_dir):
            print("not a directory: %s" % skill_dir)
            sys.exit(1)
        out = summarize(skill_dir, run(skill_dir))
        if as_json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print("[%s] %s  FAIL=%d WARN=%d SKIP=%d"
                  % (out["skill"], out["status"], out["fail"], out["warn"], out["skip"]))
            for f in out["findings"]:
                print("  [%s] %s  %s" % (f["level"], f["item"], f["detail"][:90]))
        sys.exit(0 if not out["findings"] else 3)
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"error": "%s: %s" % (type(e).__name__, e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
