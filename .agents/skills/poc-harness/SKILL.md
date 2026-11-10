---
name: poc-harness
description: Write or revise a proof-of-concept harness for one security candidate of this repository, following the harness contract, without running it. Use when the user asks for a harness or PoC for a named candidate fingerprint. Do not use to approve a candidate or to execute a harness.
---

# PoC harness for one candidate

A harness is code that will run only after the owner approves it, inside the sandbox of `security/pipeline/verify.py`. Writing it is not running it.

1. Read the candidate in `security/candidates/candidates.json` (its `validation_plan.local` says what to drive and what to observe) and the harness contract in `security/DESIGN.md` section 4.
2. Read the two existing harnesses under `security/pipeline/poc/` as the pattern.
3. Re-read every source location the candidate cites before you rely on it.
4. Write `security/pipeline/poc/<slug>/poc.py` and `poc.json`. `<slug>` is the fingerprint with every character outside `[A-Za-z0-9._-]` replaced by `_`.
   - Dummy data only, created under `--scratch`. No real credentials, no external hosts.
   - Stop at the first observation that proves the boundary result. No persistence, no concealment, no expansion.
   - Implement both `--mode exploit` and `--mode control`. The control drives the same path with a benign input and must not show the observation.
   - Print exactly one `POC_RESULT {"observed": true|false, "detail": ...}` line. Exit 0 when observed, 3 when not, 4 when a dependency is missing.
   - Write nothing outside `--scratch`.
5. Check syntax only: `python3 -m py_compile security/pipeline/poc/<slug>/poc.py`. **Do not run the harness.**
6. Mark it as a draft in `poc.json` (`"status": "draft, never executed"`), run `python3 security/pipeline/verify.py list` to confirm the candidate now shows `not_approved`, and run the pipeline tests.
7. Tell the user, in Korean, what the harness does and observes, that it has not been executed, and the command they would run themselves to approve it. Do not run that command.

Editing a harness after approval makes the approval stale by design; say so if the candidate was already approved.
