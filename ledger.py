#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ledger.py — integrity ledger for agent skill libraries (agent-skill-doctor v0.2)

Answers two questions, with evidence:

  1. What do I own?            -> one machine-readable entry per skill:
                                  name, version, deps, sha16 content fingerprint
  2. Can I prove it is untampered? -> sha16 per SKILL.md; run `--baseline`
                                  against a previous ledger and get an exact
                                  changed/added/removed report.

Fingerprint honesty rules (learned the hard way, kept as regression armor):
  - A version number must be *declared* (near a version cue), never guessed
    from shape -- a stray "12.5" in prose is a percentage, not v12.5.
  - Version tokens inside fenced code blocks belong to examples/external
    subjects, not to the skill. Strip fences first.
  - When in doubt: no version. Missing beats wrong.

stdlib only.
"""
import datetime
import hashlib
import io
import json
import os
import re

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.S)
_KV_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", re.M)
_FENCE_RE = re.compile(r"```.*?(?:```|$)|~~~.*?(?:~~~|$)", re.S)
_CUE_BEFORE = re.compile(
    r"(?:(?:version|ver\.?|release)\s*[:：=]?\s*|(?:^|[^\w])v\s*)$", re.I)
_CUE_AFTER = re.compile(r"^\s*版(?!本)")
_CUR_BEFORE = re.compile(r"[¥$€£￥]\s*$")
_UNIT_AFTER = re.compile(r"^\s*(?:%|％|\b(?:mA|ms|kg|GB|MB|KB|px|Hz|kHz|MHz|GHz|V|W|rem|pt|px)\b)", re.I)
_PATH_ADJ = re.compile(r"[\\/]$")
_ID_BEFORE = re.compile(r"[A-Za-z]$")
_SEG_CAND = re.compile(r"(?<![\d.])(\d{1,4}(?:\.\d{1,4}){0,3})(?![\d.])")


def _plausible(v, cue):
    parts = v.split(".")
    if len(parts) > 4 or not all(p.isdigit() for p in parts):
        return None
    if not cue:  # without a cue: 4 segments look like IPs, 1 segment like any number
        return None
    if len(parts[0]) > 3 or int(parts[0]) > 200:
        return None
    if len(parts) > 1 and any(len(p) > 4 for p in parts[1:]):
        return None
    return v


def extract_version(text):
    """Declared version only: needs a version cue within 24 chars before
    (version/ver./release/v) or immediately after (「N 版」). Fences stripped."""
    head = _FENCE_RE.sub(" ", text[:3000])
    for m in _SEG_CAND.finditer(head):
        s, e = m.start(1), m.end(1)
        before, after = head[max(0, s - 24):s], head[e:e + 8]
        if _PATH_ADJ.search(head[s - 1:s]) or head[e:e + 1] in ("/", "\\"):
            continue
        if _ID_BEFORE.search(head[s - 1:s]) and head[s - 1:s] not in ("v", "V"):
            continue
        if _CUR_BEFORE.search(before) or _UNIT_AFTER.match(after):
            continue
        if not (_CUE_BEFORE.search(before) or _CUE_AFTER.match(after)):
            continue
        v = _plausible(m.group(1), cue=True)
        if v:
            return v
    return None


def parse_frontmatter(text):
    m = _FM_RE.match(text)
    fm = {}
    if m:
        for kv in _KV_RE.finditer(m.group(1)):
            fm[kv.group(1).lower()] = kv.group(2).strip().strip("\"'")
    return fm


def extract_deps(text):
    deps = set(re.findall(r"(?:pip3? install)\s+([A-Za-z0-9_\-\. ]+)", text))
    deps |= set(re.findall(r"(?:npm install(?: -g)?|npx)\s+(@?[\w\-/@\.]+)", text))
    return sorted({d.strip() for dep in deps for d in dep.split() if d})[:10]


def sha16_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def scan_skill(skill_dir):
    sk = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(sk):
        return None
    try:
        text = io.open(sk, encoding="utf-8").read()
    except UnicodeDecodeError:
        text = io.open(sk, encoding="utf-8", errors="replace").read()
    fm = parse_frontmatter(text)
    scripts = []
    for sub in ("scripts", "bin", "data"):
        sp = os.path.join(skill_dir, sub)
        if os.path.isdir(sp):
            scripts += [f for _r, _d, fs in os.walk(sp) for f in fs
                        if f.endswith((".py", ".js", ".mjs", ".sh"))]
    scripts += [f for f in os.listdir(skill_dir)
                if os.path.isfile(os.path.join(skill_dir, f))
                and f.endswith((".py", ".js", ".mjs", ".sh"))]
    checks = {
        "has_description": bool(fm.get("description")),
        "has_version": bool(fm.get("version")) or extract_version(text) is not None,
        "has_script": bool(scripts),
        "no_placeholder": not re.search(r"TODO|FIXME|XXX", text),
    }
    st = os.stat(sk)
    return {
        "name": fm.get("name", os.path.basename(skill_dir)),
        "dir": os.path.basename(skill_dir),
        "version": fm.get("version") or extract_version(text),
        "description": (fm.get("description") or "")[:200],
        "deps": extract_deps(text),
        "scripts": len(scripts),
        "last_modified": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"),
        "sha16": sha16_text(text),
        "checks": checks,
        "score": sum(1 for v in checks.values() if v),
    }


def build(root):
    skills, errors = [], []
    for entry in sorted(os.listdir(root)):
        sd = os.path.join(root, entry)
        if entry.startswith(".") or not os.path.isdir(sd):
            continue
        row = scan_skill(sd)
        if row is None:
            errors.append({"skill": entry, "issue": "NO_SKILL_MD"})
            continue
        skills.append(row)
    return {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "root": root,
        "total": len(skills),
        "errors": errors,
        "skills": skills,
    }


def diff_baseline(old, new):
    """Tamper report keyed by skill dir; sha16 is the only truth for 'changed'."""
    o = {s["dir"]: s for s in old["skills"]}
    n = {s["dir"]: s for s in new["skills"]}
    return {
        "added": sorted(k for k in n if k not in o),
        "removed": sorted(k for k in o if k not in n),
        "changed": sorted(k for k in n if k in o and n[k]["sha16"] != o[k]["sha16"]),
        "unchanged": sorted(k for k in n if k in o and n[k]["sha16"] == o[k]["sha16"]),
    }
