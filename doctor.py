#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doctor.py — Agent Skill health selfcheck (part of agent-skill-doctor)

Subcommands (v0.2):

  python doctor.py check <skill_dir> [--json]
      Static, offline, read-only health checks for one skill:
        1. Frontmatter integrity --- block exists; `name` present and (warn)
           equal to the directory name; `description` non-empty; `version`
           declared (warn)
        2. Referenced files exist --- backtick-quoted repo-relative paths in
           SKILL.md must actually exist
        3. Scripts compile --- .py via py_compile; .js via `node --check`
  python doctor.py check --all <skills_root> [--json]
      Run check on every child dir that has SKILL.md.
  python doctor.py ledger <skills_root> [--baseline prev.json] [--json]
      Integrity ledger: one entry per skill with a sha16 content fingerprint;
      with --baseline, prints a changed/added/removed tamper report.
  python doctor.py graph <skills_root> [--json]
      Cross-reference dependency graph: edges, top-referenced, orphans.

Backward compatible: `python doctor.py <skill_dir>` still means `check`.

Exit codes: check -> 0 clean / 3 findings / 1 error;
            ledger, graph -> 0 ok / 1 error.
"""
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile

try:
    import graph as graph_mod
    import ledger as ledger_mod
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import graph as graph_mod
    import ledger as ledger_mod

VERSION = "0.2.0"

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


def _emit(payload, as_json, human_lines):
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in human_lines:
            print(line)


def _run_check(args, as_json):
    if args and args[0] == "--all":
        root = args[1]
        results = []
        for name in sorted(os.listdir(root)):
            sd = os.path.join(root, name)
            if os.path.isdir(sd) and os.path.isfile(os.path.join(sd, "SKILL.md")):
                results.append(summarize(sd, run(sd)))
        payload = {"tool": "agent-skill-doctor", "version": VERSION,
                   "skills_root": root, "count": len(results), "results": results}
        _emit(payload, as_json, [
            "[%s] %s  FAIL=%d WARN=%d SKIP=%d"
            % (r["skill"], r["status"], r["fail"], r["warn"], r["skip"])
            for r in results])
        sys.exit(0)
    if not args:
        print("usage: python doctor.py check <skill_dir> [--json] | "
              "check --all <root> | ledger <root> [--baseline f] | graph <root>")
        sys.exit(1)
    skill_dir = args[0]
    if not os.path.isdir(skill_dir):
        print("not a directory: %s" % skill_dir)
        sys.exit(1)
    out = summarize(skill_dir, run(skill_dir))
    _emit(out, as_json,
          ["[%s] %s  FAIL=%d WARN=%d SKIP=%d"
           % (out["skill"], out["status"], out["fail"], out["warn"], out["skip"])]
          + ["  [%s] %s  %s" % (f["level"], f["item"], f["detail"][:90])
             for f in out["findings"]])
    sys.exit(0 if not out["findings"] else 3)


def _run_ledger(args, as_json):
    baseline_path = None
    if "--baseline" in args:
        i = args.index("--baseline")
        baseline_path = args[i + 1]
        del args[i:i + 2]
    if not args:
        print("usage: python doctor.py ledger <skills_root> [--baseline prev.json] [--json]")
        sys.exit(1)
    root = args[0]
    if not os.path.isdir(root):
        print("not a directory: %s" % root)
        sys.exit(1)
    ledger = ledger_mod.build(root)
    payload = {"tool": "agent-skill-doctor-ledger", "version": VERSION, **ledger}
    human = ["ledger: %d skills, errors=%d" % (ledger["total"], len(ledger["errors"]))]
    if baseline_path:
        with open(baseline_path, encoding="utf-8") as fh:
            old = json.load(fh)
        diff = ledger_mod.diff_baseline(old, ledger)
        payload["diff"] = diff
        human += ["vs baseline: +%d added / -%d removed / ~%d changed / =%d unchanged"
                  % (len(diff["added"]), len(diff["removed"]),
                     len(diff["changed"]), len(diff["unchanged"]))]
        for k in ("added", "removed", "changed"):
            if diff[k]:
                human.append("  %s: %s" % (k, ", ".join(diff[k])))
    _emit(payload, as_json, human)
    sys.exit(0)


def _run_graph(args, as_json):
    if not args:
        print("usage: python doctor.py graph <skills_root> [--json]")
        sys.exit(1)
    root = args[0]
    if not os.path.isdir(root):
        print("not a directory: %s" % root)
        sys.exit(1)
    g = graph_mod.build(root)
    payload = {"tool": "agent-skill-doctor-graph", "version": VERSION, **g}
    human = ["graph: %d nodes, %d edges, orphans=%d"
             % (g["total"], len(g["edges"]), len(g["orphans"]))]
    if g["top_referenced"]:
        human.append("  top-referenced: %s" % ", ".join(g["top_referenced"]))
    if g["orphans"]:
        human.append("  orphans: %s" % ", ".join(g["orphans"]))
    _emit(payload, as_json, human)
    sys.exit(0)


def main(argv):
    args = list(argv)
    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    try:
        cmd = "check"
        rest = args
        if args and args[0] in ("check", "ledger", "graph"):
            cmd = args[0]
            rest = args[1:]
        if cmd == "ledger":
            _run_ledger(rest, as_json)
        if cmd == "graph":
            _run_graph(rest, as_json)
        _run_check(rest, as_json)
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"error": "%s: %s" % (type(e).__name__, e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
