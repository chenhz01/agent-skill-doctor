#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
graph.py — cross-reference dependency graph for agent skill libraries
(agent-skill-doctor v0.2)

Answers: which skills are load-bearing (referenced by others), and which are
orphans (nobody references them, they reference nobody) — candidates for
archive or promotion.

Edge rule: a skill A references skill B when any .md file inside A mentions
B's name with word boundaries (so `skill-b` does not match `skill-bb`).

stdlib only.
"""
import datetime
import json
import os
import re

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.S)
_NAME_RE = re.compile(r"^name:\s*(.+)$", re.M)
_DESC_RE = re.compile(r"^description:\s*(.+)$", re.M)


def parse_skill(md_path):
    with open(md_path, encoding="utf-8", errors="ignore") as fh:
        text = fh.read()[:4000]
    fm = _FM_RE.match(text)
    name, desc = os.path.basename(os.path.dirname(md_path)), ""
    if fm:
        m = _NAME_RE.search(fm.group(1))
        name = m.group(1).strip() if m else name
        m = _DESC_RE.search(fm.group(1))
        desc = m.group(1).strip()[:160] if m else ""
    return name, desc


def build(root):
    nodes, folders = {}, {}
    for entry in sorted(os.listdir(root)):
        sd = os.path.join(root, entry)
        if entry.startswith(".") or not os.path.isdir(sd):
            continue
        md = os.path.join(sd, "SKILL.md")
        if not os.path.isfile(md):
            continue
        name, desc = parse_skill(md)
        nodes[name] = {"desc": desc, "refs": []}
        folders[name] = sd

    for name, folder in folders.items():
        body = []
        for cur, _dirs, fs in os.walk(folder):
            for f in fs:
                if f.endswith(".md"):
                    try:
                        with open(os.path.join(cur, f), encoding="utf-8", errors="ignore") as fh:
                            body.append(fh.read())
                    except OSError:
                        continue
        blob = "\n".join(body)[:200000]
        for other in nodes:
            if other != name and re.search(r"[^\w-]" + re.escape(other) + r"[^\w-]", blob):
                nodes[name]["refs"].append(other)

    edges = [{"from": n, "to": r} for n, d in nodes.items() for r in d["refs"]]
    inbound = {e["to"] for e in edges}
    orphans = sorted(n for n, d in nodes.items() if not d["refs"] and n not in inbound)
    return {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "total": len(nodes),
        "edges": edges,
        "orphans": orphans,
        "top_referenced": sorted(
            inbound,
            key=lambda t: (-sum(1 for e in edges if e["to"] == t), t))[:8],
    }
