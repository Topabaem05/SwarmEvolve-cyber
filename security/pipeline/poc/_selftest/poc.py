#!/usr/bin/env python3
"""Pipeline self-test harness. It touches no target code.

It checks, from inside the sandbox, that the controls the runner promises actually hold:
no network, a minimal environment, a read-only target, and a writable scratch directory.

exploit mode: write a marker in scratch after every control check passes -> observed.
control mode: do not write the marker -> not observed.
"""
import argparse
import json
import os
import socket
import sys

ALLOWED_ENV = {"PATH", "LANG", "HOME", "TMPDIR", "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE", "PYTHONHASHSEED",
               "LC_CTYPE", "PWD", "SHLVL", "_", "HOSTNAME"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("exploit", "control"), required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--scratch", required=True)
    args = ap.parse_args()

    checks = {}

    # 1. No network: an outbound TCP connection must fail.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed
        checks["network_blocked"] = False
    except OSError:
        checks["network_blocked"] = True
    finally:
        s.close()

    # 2. Minimal environment: nothing outside the allowlist, so no inherited credentials.
    extra = sorted(set(os.environ) - ALLOWED_ENV)
    checks["environment_minimal"] = not extra

    # 3. Read-only target.
    probe = os.path.join(args.target, ".selftest_write_probe")
    try:
        with open(probe, "w") as f:
            f.write("x")
        os.unlink(probe)
        checks["target_read_only"] = False
    except OSError:
        checks["target_read_only"] = True

    # 4. Scratch is writable.
    marker = os.path.join(args.scratch, "selftest_marker")
    observed = False
    if args.mode == "exploit" and all(checks.values()):
        try:
            with open(marker, "w") as f:
                f.write("ok")
            observed = os.path.exists(marker)
        except OSError:
            observed = False

    detail = {"checks": checks, "unexpected_env": extra}
    print("POC_RESULT " + json.dumps({"observed": observed, "detail": detail}))
    if args.mode == "exploit" and not all(checks.values()):
        sys.exit(1)  # a broken sandbox is an error, not a "not observed"
    sys.exit(0 if observed else 3)


if __name__ == "__main__":
    main()
