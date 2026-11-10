---
name: security-status
description: Report the current state of this repository's security audit — candidates and their approval state, chain hypotheses, deferred coverage, and whether the tooling tests pass. Use when the user asks what the audit found, what is pending, what can be verified next, or for a status summary. Do not use to run a red-team round, to write a harness, or to approve anything.
---

# Security status

Report facts from the repository. Run nothing from `benchmarks/` or `baselines/`.

1. Run these and read their output:
   - `python3 security/pipeline/verify.py list`
   - `python3 security/redteam/chains.py plan --capabilities security/redteam/registry/capabilities.json`
   - `python3 -m unittest discover -s security/pipeline/tests`
   - `python3 -m unittest discover -s security/redteam/tests`
2. Read `security/audit/run-1/REPORT.md` sections 4 and 7 for the leads and the deferred coverage.
3. Answer in Korean, in this order:
   - how many leads are `not_approved` (a harness exists, approval is pending), `harness_missing`, `approved`, `stale`;
   - which chain hypotheses exist and that all of them are blocked until their components are confirmed;
   - what was never investigated (deferred units);
   - test results, with the failing test names if any;
   - what the owner could do next.

Always state that the leads are unverified candidates from source analysis, not confirmed vulnerabilities. Never suggest that you can approve a candidate; show the command the owner would run.
