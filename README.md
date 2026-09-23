# agent-skill-doctor

Offline health checks and a structural pain-radar for **agent skill libraries** — the `SKILL.md` ecosystem used by OpenAI, Anthropic, and the open-source community.

You have 50, 100, maybe 200 skills. Nobody has run them since last month. A referenced script was renamed, a YAML frontmatter field went missing, a `.py` file rotted past a syntax change — and you only find out when the agent fails mid-task, in production, with a user watching. This tool catches all of that **before** the agent runs, in milliseconds, with zero network access.

```bash
python doctor.py <skill_dir>          # one skill: frontmatter, refs, script compile
python doctor.py --all <skills_root>  # every skill in your library
python radar.py   <skills_root>       # rank which skill deserves attention first
```

Exit codes are contract: `0` clean, `3` findings, `1` tool error — so you can wire it into CI in one line.

## What `doctor.py` checks

| Check | Level | Catches |
|---|---|---|
| Frontmatter integrity (`name`/`description`/`version`) | FAIL/WARN | silent skill-loading failures, unversioned assets |
| Backtick-referenced files exist (`scripts/…`, `data/…`, `bin/…`) | FAIL | renamed/moved scripts that break the skill at runtime |
| Every `.py` / `.js` compiles (`py_compile` / `node --check`) | FAIL | rotted scripts, mid-refactor leftovers |

## What `radar.py` ranks

Purely structural, no telemetry needed: **form typing** (CODE vs DOC — does the skill even ship testable scripts?), test/selftest presence, doctor findings, and a **pain queue** that puts sick CODE skills first, because a code skill you cannot test is the one that bites you. The thesis: most skills stop at "written"; the scarce resource is the second and third hands-on iteration — the radar tells you where those iterations pay off.

## Honest boundary (read this before forking)

This repo is the **structural half** of the system. It does *not* claim to answer the harder question — *"did this skill actually get better because someone used it?"* — and nothing here fakes that answer. Verdicts like "used, then improved, with evidence" require usage-trace ingestion and tamper-resistant evidence grading that we deliberately keep out of a public repo. See [Collaboration](#collaboration--the-checks-we-run-that-we-dont-ship) for what exists behind that line.

## Tests

10 tests, mutation-testing flavored: a broken fixture **must** FAIL (and exit 3), a clean fixture **must** PASS (and exit 0) — a doctor that cannot catch a sick skill is worse than no doctor.

```bash
python -m unittest discover -s tests -v
```

CI runs the suite on Ubuntu + Windows, Python 3.9 + 3.12, plus bidirectional CLI smoke. Zero third-party dependencies; Python 3.8+ stdlib only (node is optional, its absence is reported as `SKIP`, never as failure).

## Collaboration — the checks we run that we don't ship

Everything in this repo is free forever: read it, run it, fork it, and we will never chase you. The table below is the full map of what is open and what is not — published openly so you can decide in 30 seconds whether to ask for more.

| Tier | What it is | Concrete |
|---|---|---|
| 🌱 Open | everything in this repo | 2 tools (~330 lines), 10 tests, 2 fixtures, CI |
| 🔑 Partner | shipped on collaboration, not on request | library-wide adoption playbook; CI integration recipes for monorepos; evidence-graded maturity reports for your own skill library |
| 💎 Never shipped | stays in-house regardless | the evidence-grading engine that answers "did it improve after use", its tamper-resistance design, and the gap-ticket state machine that turns findings into a closed loop |

Why keep those back? Because the structural checks in this repo can only see *today's files* — the locked part answers *what happened over the lifetime of the skill*, using host-level write snapshots and content fingerprints. That machinery is tightly coupled to our own runtime and leaks operational details we are not willing to publish; it is **not in this repository** and the open half does not pretend to reproduce it. Partners get the interface and the methodology, not the recipe.

**How to ask.** Write to hcac4735@agent.qq.com (or shanlun2029@outlook.com if you are overseas — reachability of the first address abroad is not guaranteed, the second is). Include two things: (1) what you are building and where agent skills sit in it, (2) which tier you want and what you already tried. A one-line message gets a one-line reply; substantive ones get an answer within 48h.

**Not a fit** if you want a hosted SaaS, a dashboard, or someone to run your library for you. **A fit** if you maintain 30+ skills and structural checks alone stopped being enough. If a check here fails on a layout you believe is valid, open an issue describing the failure mode — the sharpest cases go into the next release, with credit.

## License

MIT — see [LICENSE](LICENSE).
