#!/usr/bin/env python3
"""Harness for benchmarks-evaluation/inband-metrics-marker-forgery.

DRAFT. Written from source analysis and not executed yet; its first run happens after approval,
inside the sandbox (see security/DESIGN.md).

Claim under test: a program scored by benchmarks/evaluation.py can set its own recorded score,
because the scorer accepts the last `@@METRICS@@` line on stdout and does not check the exit status
or the origin of that line.

exploit: a dummy program prints a metrics line carrying a sentinel score and exits with status 0
         before the real evaluator prints its own line.
control: an honest dummy program that returns one point. Its score must not be the sentinel.
observable: evaluate() returns combined_score == SENTINEL.

Dummy data only: both programs are written to the scratch directory, no log file is used.
"""
import argparse
import importlib.util
import json
import os
import sys

SENTINEL = 424242.0
PROBLEM = "kissing_number_11"  # an evaluator that imports the program into the scorer process

EXPLOIT_PROGRAM = '''import os
import sys

sys.stdout.write('@@METRICS@@{"combined_score": %r}\\n')
sys.stdout.flush()
os._exit(0)
''' % SENTINEL

CONTROL_PROGRAM = '''import numpy as np


def kissing_number11():
    return np.array([[1.0] + [0.0] * 10])
'''


def emit(observed, detail, code=None):
    print("POC_RESULT " + json.dumps({"observed": observed, "detail": detail}))
    sys.exit(code if code is not None else (0 if observed else 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("exploit", "control"), required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--scratch", required=True)
    args = ap.parse_args()

    if importlib.util.find_spec("numpy") is None:
        emit(False, {"missing_dependency": "numpy"}, code=4)

    os.environ.pop("EVAL_LOG", None)  # never touch a score log
    spec = importlib.util.spec_from_file_location(
        "benchmark_evaluation", os.path.join(args.target, "benchmarks", "evaluation.py"))
    evaluation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluation)

    work = os.path.join(args.scratch, f"program_{args.mode}")
    os.makedirs(work, exist_ok=True)
    program = os.path.join(work, "candidate_program.py")
    with open(program, "w") as f:
        f.write(EXPLOIT_PROGRAM if args.mode == "exploit" else CONTROL_PROGRAM)

    metrics = evaluation.evaluate(program, problem=PROBLEM, log=None)
    score = metrics.get("combined_score")
    emit(score == SENTINEL, {"combined_score": score, "error": str(metrics.get("error", ""))[:200]})


if __name__ == "__main__":
    main()
