#!/usr/bin/env python3
"""Approval-gated PoC verification runner for security candidates.

    python3 security/pipeline/verify.py list
    python3 security/pipeline/verify.py approve <fingerprint> --by <github-login>
    python3 security/pipeline/verify.py run --all-approved [--backend auto|docker|unshare]
    python3 security/pipeline/verify.py selftest

Rules this runner enforces (see security/DESIGN.md):

1. No approval, no execution. A PoC harness runs only when security/approvals/approvals.json holds an
   approval for that fingerprint.
2. An approval is bound to what was reviewed: the harness files, the candidate record, and the target
   source files the candidate cites. If any of them changes, the approval is stale and nothing runs.
3. Fail closed. The harness runs only inside a sandbox whose controls were established for this run:
   no network, an empty allowlisted environment, a read-only target, scratch-only writes, and resource
   and wall-clock limits. If a control cannot be established, the result is `blocked`.
4. Evidence is captured output only. Nothing the harness writes is copied out of the scratch directory.

Standard library only. The runner never installs anything and never contacts the network.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEC = ROOT / "security"
CANDIDATES = SEC / "candidates" / "candidates.json"
APPROVALS = SEC / "approvals" / "approvals.json"
POC_DIR = SEC / "pipeline" / "poc"
EVIDENCE = SEC / "evidence"

FINGERPRINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$")
SELFTEST = "_selftest"
SCOPE = "sandboxed-poc-execution"
RESULT_PREFIX = "POC_RESULT "
MAX_CAPTURE = 64 * 1024  # bytes of stdout/stderr kept per attempt

# Harness exit codes.
EXIT_OBSERVED, EXIT_NOT_OBSERVED, EXIT_DEP_MISSING = 0, 3, 4
# Exit code the unshare wrapper uses when a sandbox probe fails.
EXIT_PROBE_FAILED = 97

DEFAULT_LIMITS = {"wall_s": 120, "cpu_s": 60, "memory_mb": 2048, "fsize_mb": 64, "pids": 128}
SAFE_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
    "PYTHONHASHSEED": "0",
}


def die(msg, code=2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def slug(fingerprint):
    return re.sub(r"[^A-Za-z0-9._-]", "_", fingerprint)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_candidates():
    data = load_json(CANDIDATES, {"candidates": []})
    out = {}
    for c in data.get("candidates", []):
        fp = c.get("fingerprint", "")
        if not FINGERPRINT_RE.match(fp):
            die(f"invalid fingerprint in candidates.json: {fp!r}")
        if fp in out:
            die(f"duplicate fingerprint in candidates.json: {fp}")
        out[fp] = c
    return out


def harness_dir(fingerprint):
    return POC_DIR / (SELFTEST if fingerprint == SELFTEST else slug(fingerprint))


def hash_tree(directory):
    """sha256 over the sorted relative paths and contents of every regular file in `directory`."""
    if not directory.is_dir():
        return None
    h = hashlib.sha256()
    for p in sorted(directory.rglob("*")):
        if p.is_symlink():
            die(f"symlink not allowed in a harness directory: {p}")
        if "__pycache__" in p.parts or not p.is_file():
            continue
        h.update(p.relative_to(directory).as_posix().encode() + b"\0")
        h.update(p.read_bytes() + b"\0")
    return h.hexdigest()


def cited_files(candidate):
    files = {e.get("file") for e in candidate.get("trace", []) + candidate.get("evidence", [])}
    return sorted(f for f in files if f)


def hash_cited_files(candidate):
    """sha256 over the target source files the candidate cites, so an approval tracks the reviewed code."""
    h = hashlib.sha256()
    for rel in cited_files(candidate):
        p = (ROOT / rel).resolve()
        if ROOT.resolve() not in p.parents:
            die(f"cited file escapes the repository: {rel}")
        h.update(rel.encode() + b"\0")
        h.update((p.read_bytes() if p.is_file() else b"<missing>") + b"\0")
    return h.hexdigest()


def binding(fingerprint, candidate):
    return {
        "harness_sha256": hash_tree(harness_dir(fingerprint)),
        "candidate_sha256": sha256_bytes(json.dumps(candidate, sort_keys=True, ensure_ascii=False).encode()),
        "cited_files_sha256": hash_cited_files(candidate),
    }


def find_approval(fingerprint):
    for a in load_json(APPROVALS, {"approvals": []}).get("approvals", []):
        if a.get("fingerprint") == fingerprint and a.get("scope") == SCOPE and not a.get("revoked"):
            return a
    return None


def approval_state(fingerprint, candidate):
    """Return (state, detail): approved | not_approved | stale | harness_missing."""
    current = binding(fingerprint, candidate)
    if current["harness_sha256"] is None:
        return "harness_missing", f"no harness directory {harness_dir(fingerprint).relative_to(ROOT)}"
    approval = find_approval(fingerprint)
    if approval is None:
        return "not_approved", "no approval entry"
    stale = [k for k, v in current.items() if approval.get(k) != v]
    if stale:
        return "stale", "changed since approval: " + ", ".join(stale)
    return "approved", f"approved by {approval.get('approved_by')} at {approval.get('approved_at')}"


def git_head():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


# ---------------------------------------------------------------------------------------------------
# Sandbox backends
# ---------------------------------------------------------------------------------------------------

def pick_backend(requested):
    def docker_ok():
        return shutil.which("docker") and subprocess.run(
            ["docker", "info"], capture_output=True).returncode == 0

    def unshare_ok():
        needed = ("unshare", "setpriv", "prlimit", "timeout", "mount")
        if not all(shutil.which(t) for t in needed):
            return False
        return subprocess.run(["unshare", "--user", "--map-root-user", "--net", "--mount", "true"],
                              capture_output=True).returncode == 0

    if requested == "docker":
        return "docker" if docker_ok() else None
    if requested == "unshare":
        return "unshare" if unshare_ok() else None
    return "docker" if docker_ok() else ("unshare" if unshare_ok() else None)


def harness_argv(python, harness_path, mode, target, scratch):
    # -I: isolated mode. No PYTHON* variables, no user site, script directory not on sys.path.
    return [python, "-I", str(harness_path), "--mode", mode, "--target", str(target), "--scratch", str(scratch)]


def docker_command(image, fingerprint, mode, scratch, limits):
    rel = harness_dir(fingerprint).relative_to(ROOT).as_posix()
    cmd = [
        "docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", "65534:65534",
        "--pids-limit", str(limits["pids"]), "--memory", f"{limits['memory_mb']}m", "--memory-swap",
        f"{limits['memory_mb']}m", "--cpus", "1",
        "--ulimit", f"fsize={limits['fsize_mb'] * 1024 * 1024}", "--ulimit", f"cpu={limits['cpu_s']}",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "-v", f"{ROOT}:/target:ro", "-v", f"{scratch}:/scratch:rw", "-w", "/scratch",
    ]
    env = dict(SAFE_ENV, HOME="/scratch", TMPDIR="/scratch")
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]
    # /opt/venv/bin/python is where .oss-scanner/Dockerfile installs the pinned environment.
    cmd += [image, "timeout", "--kill-after=5", str(limits["wall_s"])]
    cmd += harness_argv("/opt/venv/bin/python", f"/target/{rel}/poc.py", mode, "/target", "/scratch")
    return cmd, None


UNSHARE_SCRIPT = r"""
set -eu
mount --make-rprivate /
mount --bind "$SBX_SCRATCH" "$SBX_SCRATCH"
# Remount every other mount point read-only. Best effort here; the write probes below decide.
awk '{print $5}' /proc/self/mountinfo | sort -r | while IFS= read -r mp; do
  case "$mp" in "$SBX_SCRATCH"|"$SBX_SCRATCH"/*) continue ;; esac
  mount -o remount,ro,bind "$mp" 2>/dev/null || true
done
for p in "$SBX_TARGET" /tmp /var/tmp /dev/shm "$SBX_HOST_HOME"; do
  [ -d "$p" ] || continue
  if ( : > "$p/.sbx_probe_$$" ) 2>/dev/null; then
    echo "SANDBOX_PROBE_FAIL writable outside scratch: $p" >&2
    exit 97
  fi
done
if ! ( : > "$SBX_SCRATCH/.sbx_probe" ) 2>/dev/null; then
  echo "SANDBOX_PROBE_FAIL scratch not writable" >&2
  exit 97
fi
rm -f "$SBX_SCRATCH/.sbx_probe"
# /proc is mounted fresh for this namespace (--mount-proc), so /proc/net/dev lists only its interfaces.
if [ ! -r /proc/net/dev ] || [ -n "$(awk -F: 'NR>2 {gsub(/ /,"",$1); if ($1 != "lo") print $1}' /proc/net/dev)" ]; then
  echo "SANDBOX_PROBE_FAIL non-loopback network interface present" >&2
  exit 97
fi
cd "$SBX_SCRATCH"
exec env -i $SBX_ENV HOME="$SBX_SCRATCH" TMPDIR="$SBX_SCRATCH" \
  setpriv --bounding-set=-all --inh-caps=-all --no-new-privs \
  prlimit --cpu="$SBX_CPU" --as="$SBX_AS" --fsize="$SBX_FSIZE" --nofile=256 --core=0 \
  timeout --kill-after=5 "$SBX_WALL" "$@"
"""


def unshare_command(fingerprint, mode, scratch, limits):
    harness = harness_dir(fingerprint) / "poc.py"
    cmd = ["unshare", "--user", "--map-root-user", "--net", "--mount", "--pid", "--fork", "--kill-child",
           "--mount-proc", "sh", "-c", UNSHARE_SCRIPT, "sbx"]
    cmd += harness_argv(sys.executable, harness, mode, ROOT, scratch)
    # Only these variables reach the wrapper script; the harness itself starts from `env -i`.
    env = {
        "PATH": SAFE_ENV["PATH"],
        "SBX_SCRATCH": str(scratch), "SBX_TARGET": str(ROOT), "SBX_HOST_HOME": os.path.expanduser("~"),
        "SBX_ENV": " ".join(f"{k}={shlex.quote(v)}" for k, v in SAFE_ENV.items()),
        "SBX_CPU": str(limits["cpu_s"]), "SBX_AS": str(limits["memory_mb"] * 1024 * 1024),
        "SBX_FSIZE": str(limits["fsize_mb"] * 1024 * 1024), "SBX_WALL": str(limits["wall_s"]),
    }
    return cmd, env


def run_attempt(backend, image, fingerprint, mode, limits):
    scratch = Path(tempfile.mkdtemp(prefix="poc-scratch-"))
    os.chmod(scratch, 0o777)  # the docker backend runs the harness as uid 65534
    try:
        if backend == "docker":
            cmd, env = docker_command(image, fingerprint, mode, scratch, limits)
        else:
            cmd, env = unshare_command(fingerprint, mode, scratch, limits)
        try:
            proc = subprocess.run(cmd, env=env, capture_output=True, timeout=limits["wall_s"] + 60,
                                  stdin=subprocess.DEVNULL)
            rc, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            rc, out, err = 124, e.stdout or b"", e.stderr or b""
    finally:
        shutil.rmtree(scratch, ignore_errors=True)  # nothing is promoted out of scratch
    out_text = out[:MAX_CAPTURE].decode("utf-8", "replace")
    err_text = err[:MAX_CAPTURE].decode("utf-8", "replace")
    parsed = None
    for line in reversed(out_text.splitlines()):
        if line.startswith(RESULT_PREFIX):
            try:
                parsed = json.loads(line[len(RESULT_PREFIX):])
            except ValueError:
                parsed = None
            break
    if rc == EXIT_PROBE_FAILED or "SANDBOX_PROBE_FAIL" in err_text:
        outcome = "sandbox_probe_failed"
    elif rc == EXIT_DEP_MISSING:
        outcome = "dependency_missing"
    elif rc in (124, 137):
        outcome = "timeout"
    elif isinstance(parsed, dict) and isinstance(parsed.get("observed"), bool) and rc in (EXIT_OBSERVED,
                                                                                         EXIT_NOT_OBSERVED):
        # The exit code and the result line must agree; a mismatch is a harness defect.
        outcome = "observed" if (parsed["observed"] and rc == EXIT_OBSERVED) else (
            "not_observed" if (not parsed["observed"] and rc == EXIT_NOT_OBSERVED) else "harness_error")
    else:
        outcome = "harness_error"
    return {"mode": mode, "exit_code": rc, "outcome": outcome, "result": parsed,
            "stdout": out_text, "stderr": err_text}


def decide(attempts):
    """Reduce exploit and control attempts to one verdict."""
    exploit = [a for a in attempts if a["mode"] == "exploit"]
    control = [a for a in attempts if a["mode"] == "control"]
    outcomes = {a["outcome"] for a in attempts}
    if "sandbox_probe_failed" in outcomes:
        return "blocked", "sandbox_control_not_established"
    if "dependency_missing" in outcomes:
        return "blocked", "dependency_missing_in_sandbox"
    if outcomes & {"timeout", "harness_error"}:
        return "inconclusive", "harness_error_or_timeout"
    if any(a["outcome"] == "observed" for a in control):
        return "inconclusive", "control_run_also_showed_the_observable"
    if exploit and all(a["outcome"] == "observed" for a in exploit):
        return "reproduced", f"observed in {len(exploit)}/{len(exploit)} exploit runs, 0/{len(control)} control runs"
    if exploit and all(a["outcome"] == "not_observed" for a in exploit):
        return "not_reproduced", "the observable did not appear in any exploit run"
    return "inconclusive", "exploit runs disagree"


def verify_one(fingerprint, candidate, backend, image, attempts_n, evidence_root, require_approval=True):
    record = {
        "fingerprint": fingerprint,
        "title": candidate.get("title"),
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source_ref": git_head(),
        "binding": binding(fingerprint, candidate),
        "backend": backend,
        "image": image if backend == "docker" else None,
        "attempts": [],
    }
    state, detail = approval_state(fingerprint, candidate)
    record["approval"] = {"state": state, "detail": detail}
    spec = load_json(harness_dir(fingerprint) / "poc.json", {})
    limits = dict(DEFAULT_LIMITS, **spec.get("limits", {}))
    record["limits"] = limits
    record["allowlisted_env"] = sorted(list(SAFE_ENV) + ["HOME", "TMPDIR"])

    if state == "harness_missing":
        record["verdict"], record["reason"] = "blocked", "harness_missing"
    elif require_approval and state != "approved":
        record["verdict"], record["reason"] = "blocked", f"approval_{state}"
    elif backend is None:
        record["verdict"], record["reason"] = "blocked", "no_sandbox_backend_available"
    elif backend == "docker" and not image:
        record["verdict"], record["reason"] = "blocked", "docker_backend_needs_--image"
    else:
        for _ in range(attempts_n):
            record["attempts"].append(run_attempt(backend, image, fingerprint, "exploit", limits))
        if spec.get("control", True):
            record["attempts"].append(run_attempt(backend, image, fingerprint, "control", limits))
        record["verdict"], record["reason"] = decide(record["attempts"])

    record["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    stamp = record["started_at"].replace(":", "").replace("-", "").replace("+0000", "Z")
    out_dir = evidence_root / slug(fingerprint) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "result.json", "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
        f.write("\n")
    record["evidence_path"] = str(out_dir / "result.json")
    return record


# ---------------------------------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------------------------------

def cmd_list(args):
    rows = []
    for fp, c in sorted(load_candidates().items()):
        state, detail = approval_state(fp, c)
        rows.append({"fingerprint": fp, "verdict": c.get("verdict"), "approval": state, "detail": detail,
                     "title": c.get("title")})
    if args.approved:
        rows = [r for r in rows if r["approval"] == "approved"]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    for r in rows:
        print(f"{r['approval']:<16} {r['fingerprint']:<48} {r['title']}")
        if r["approval"] in ("stale",):
            print(f"{'':<16} {r['detail']}")
    return 0


def cmd_approve(args):
    candidates = load_candidates()
    if args.fingerprint not in candidates:
        die(f"unknown fingerprint: {args.fingerprint}")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$", args.by):
        die("--by must be a GitHub login")
    bound = binding(args.fingerprint, candidates[args.fingerprint])
    if bound["harness_sha256"] is None:
        die(f"no harness to approve: {harness_dir(args.fingerprint).relative_to(ROOT)}/ does not exist. "
            "Write and review the harness first; an approval covers exact harness content.")
    data = load_json(APPROVALS, {"approvals": []})
    data["approvals"] = [a for a in data.get("approvals", []) if a.get("fingerprint") != args.fingerprint]
    entry = {"fingerprint": args.fingerprint, "scope": SCOPE, "approved_by": args.by,
             "approved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
             "note": args.note or ""}
    entry.update(bound)
    data["approvals"].append(entry)
    data["approvals"].sort(key=lambda a: a["fingerprint"])
    APPROVALS.parent.mkdir(parents=True, exist_ok=True)
    with open(APPROVALS, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"recorded approval for {args.fingerprint} by {args.by}")
    print("Commit and push security/approvals/approvals.json to the default branch to start verification.")
    return 0


def cmd_run(args):
    candidates = load_candidates()
    if args.all_approved:
        targets = [fp for fp, c in sorted(candidates.items()) if approval_state(fp, c)[0] == "approved"]
    else:
        if args.fingerprint not in candidates:
            die(f"unknown fingerprint: {args.fingerprint}")
        targets = [args.fingerprint]
    backend = pick_backend(args.backend)
    evidence_root = Path(args.evidence_dir).resolve() if args.evidence_dir else EVIDENCE
    results = []
    for fp in targets:
        r = verify_one(fp, candidates[fp], backend, args.image, args.attempts, evidence_root)
        results.append(r)
        print(f"{r['verdict']:<16} {fp:<48} {r['reason']}")
    summary = [{k: r[k] for k in ("fingerprint", "verdict", "reason", "evidence_path")} for r in results]
    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
    if not targets:
        print("no approved candidates; nothing was executed")
    # Exit 0 when the pipeline itself worked; verdicts are data, not failures.
    return 0


def cmd_selftest(args):
    """Prove the sandbox controls with a harness that touches no target code."""
    backend = pick_backend(args.backend)
    candidate = {"fingerprint": SELFTEST, "title": "pipeline self-test", "trace": [], "evidence": []}
    with tempfile.TemporaryDirectory(prefix="poc-selftest-") as tmp:
        r = verify_one(SELFTEST, candidate, backend, args.image, 2, Path(tmp), require_approval=False)
    print(f"backend={backend} verdict={r['verdict']} reason={r['reason']}")
    for a in r["attempts"]:
        print(f"  {a['mode']:<8} {a['outcome']:<14} {json.dumps(a['result'])}")
        if a["outcome"] not in ("observed", "not_observed"):
            print("    stderr:", a["stderr"].strip()[-400:])
    return 0 if r["verdict"] == "reproduced" else 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="show candidates and their approval state")
    s.add_argument("--approved", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("approve", help="record an approval bound to the current harness, record and source")
    s.add_argument("fingerprint")
    s.add_argument("--by", required=True, help="GitHub login of the approver")
    s.add_argument("--note")
    s.set_defaults(fn=cmd_approve)

    s = sub.add_parser("run", help="run approved harnesses in the sandbox and write evidence")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--fingerprint")
    g.add_argument("--all-approved", action="store_true")
    s.add_argument("--backend", choices=("auto", "docker", "unshare"), default="auto")
    s.add_argument("--image", help="docker image built from .oss-scanner/Dockerfile")
    s.add_argument("--attempts", type=int, default=3, help="exploit runs per candidate (default 3)")
    s.add_argument("--evidence-dir")
    s.add_argument("--summary", help="write a JSON summary to this path")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("selftest", help="check the sandbox controls without touching target code")
    s.add_argument("--backend", choices=("auto", "docker", "unshare"), default="auto")
    s.add_argument("--image")
    s.set_defaults(fn=cmd_selftest)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
