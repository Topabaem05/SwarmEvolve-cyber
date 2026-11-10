"""Tests for the approval gate and verdict rules. Standard library only.

    python3 -m unittest discover -s security/pipeline/tests -v
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("verify", Path(__file__).resolve().parents[1] / "verify.py")
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)

FP = "demo/sample-candidate"


def attempt(mode, outcome):
    return {"mode": mode, "outcome": outcome}


class DecideTests(unittest.TestCase):
    def test_reproduced_needs_every_exploit_run_and_a_clean_control(self):
        runs = [attempt("exploit", "observed")] * 3 + [attempt("control", "not_observed")]
        self.assertEqual(verify.decide(runs)[0], "reproduced")

    def test_control_showing_the_observable_is_inconclusive(self):
        runs = [attempt("exploit", "observed")] * 3 + [attempt("control", "observed")]
        self.assertEqual(verify.decide(runs)[0], "inconclusive")

    def test_flaky_exploit_is_inconclusive(self):
        runs = [attempt("exploit", "observed"), attempt("exploit", "not_observed"), attempt("control", "not_observed")]
        self.assertEqual(verify.decide(runs)[0], "inconclusive")

    def test_never_observed_is_not_reproduced(self):
        runs = [attempt("exploit", "not_observed")] * 3 + [attempt("control", "not_observed")]
        self.assertEqual(verify.decide(runs)[0], "not_reproduced")

    def test_probe_failure_blocks_even_if_other_runs_observed(self):
        runs = [attempt("exploit", "observed"), attempt("exploit", "sandbox_probe_failed")]
        self.assertEqual(verify.decide(runs), ("blocked", "sandbox_control_not_established"))

    def test_missing_dependency_blocks(self):
        self.assertEqual(verify.decide([attempt("exploit", "dependency_missing")])[0], "blocked")

    def test_timeout_is_inconclusive(self):
        self.assertEqual(verify.decide([attempt("exploit", "timeout")])[0], "inconclusive")


class ApprovalGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.root = root
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text("print('v1')\n")
        self.candidate = {
            "fingerprint": FP, "verdict": "needs_validation", "title": "demo",
            "trace": [{"kind": "sink", "file": "src/app.py", "line": 1, "scope": "module", "description": "d"}],
            "evidence": [{"file": "src/app.py", "line": 1, "description": "d"}],
        }
        sec = root / "security"
        (sec / "candidates").mkdir(parents=True)
        (sec / "candidates" / "candidates.json").write_text(json.dumps({"candidates": [self.candidate]}))
        self.saved = {k: getattr(verify, k) for k in ("ROOT", "SEC", "CANDIDATES", "APPROVALS", "POC_DIR", "EVIDENCE")}
        verify.ROOT, verify.SEC = root, sec
        verify.CANDIDATES = sec / "candidates" / "candidates.json"
        verify.APPROVALS = sec / "approvals" / "approvals.json"
        verify.POC_DIR = sec / "pipeline" / "poc"
        verify.EVIDENCE = sec / "evidence"

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(verify, k, v)
        self.tmp.cleanup()

    def write_harness(self, body="print('POC_RESULT {\"observed\": false}')\n"):
        d = verify.harness_dir(FP)
        d.mkdir(parents=True, exist_ok=True)
        (d / "poc.py").write_text(body)

    def approve(self):
        entry = {"fingerprint": FP, "scope": verify.SCOPE, "approved_by": "owner", "approved_at": "t"}
        entry.update(verify.binding(FP, self.candidate))
        verify.APPROVALS.parent.mkdir(parents=True, exist_ok=True)
        verify.APPROVALS.write_text(json.dumps({"approvals": [entry]}))

    def state(self):
        return verify.approval_state(FP, self.candidate)[0]

    def test_no_harness(self):
        self.assertEqual(self.state(), "harness_missing")

    def test_harness_without_approval(self):
        self.write_harness()
        self.assertEqual(self.state(), "not_approved")

    def test_approved(self):
        self.write_harness()
        self.approve()
        self.assertEqual(self.state(), "approved")

    def test_harness_edit_after_approval_is_stale(self):
        self.write_harness()
        self.approve()
        self.write_harness("import os\n")
        self.assertEqual(self.state(), "stale")

    def test_new_harness_file_after_approval_is_stale(self):
        self.write_harness()
        self.approve()
        (verify.harness_dir(FP) / "extra.py").write_text("x = 1\n")
        self.assertEqual(self.state(), "stale")

    def test_cited_source_change_after_approval_is_stale(self):
        self.write_harness()
        self.approve()
        (self.root / "src" / "app.py").write_text("print('v2')\n")
        self.assertEqual(self.state(), "stale")

    def test_candidate_record_change_after_approval_is_stale(self):
        self.write_harness()
        self.approve()
        self.candidate["title"] = "changed"
        self.assertEqual(self.state(), "stale")

    def test_revoked_approval_does_not_count(self):
        self.write_harness()
        self.approve()
        data = json.loads(verify.APPROVALS.read_text())
        data["approvals"][0]["revoked"] = True
        verify.APPROVALS.write_text(json.dumps(data))
        self.assertEqual(self.state(), "not_approved")

    def test_approval_with_another_scope_does_not_count(self):
        self.write_harness()
        self.approve()
        data = json.loads(verify.APPROVALS.read_text())
        data["approvals"][0]["scope"] = "something-else"
        verify.APPROVALS.write_text(json.dumps(data))
        self.assertEqual(self.state(), "not_approved")

    def test_unapproved_candidate_is_never_executed(self):
        marker = self.root / "executed"
        self.write_harness(f"open({str(marker)!r}, 'w').write('x')\n")
        rec = verify.verify_one(FP, self.candidate, "unshare", None, 1, self.root / "ev")
        self.assertEqual((rec["verdict"], rec["reason"]), ("blocked", "approval_not_approved"))
        self.assertEqual(rec["attempts"], [])
        self.assertFalse(marker.exists())

    def test_stale_approval_is_never_executed(self):
        marker = self.root / "executed"
        self.write_harness()
        self.approve()
        self.write_harness(f"open({str(marker)!r}, 'w').write('x')\n")
        rec = verify.verify_one(FP, self.candidate, "unshare", None, 1, self.root / "ev")
        self.assertEqual((rec["verdict"], rec["reason"]), ("blocked", "approval_stale"))
        self.assertFalse(marker.exists())

    def test_no_backend_blocks(self):
        self.write_harness()
        self.approve()
        rec = verify.verify_one(FP, self.candidate, None, None, 1, self.root / "ev")
        self.assertEqual((rec["verdict"], rec["reason"]), ("blocked", "no_sandbox_backend_available"))

    def test_approve_command_refuses_to_run_without_a_terminal(self):
        import argparse
        self.write_harness()
        args = argparse.Namespace(fingerprint=FP, by="owner", note=None)
        with self.assertRaises(SystemExit) as ctx:  # the test runner has no terminal, like a coding agent
            verify.cmd_approve(args)
        self.assertEqual(ctx.exception.code, 2)
        self.assertFalse(verify.APPROVALS.exists())
        self.assertEqual(self.state(), "not_approved")

    def test_symlink_in_harness_dir_is_refused(self):
        self.write_harness()
        (verify.harness_dir(FP) / "link").symlink_to("/etc/passwd")
        with self.assertRaises(SystemExit):
            verify.hash_tree(verify.harness_dir(FP))

    def test_cited_file_outside_repo_is_refused(self):
        self.candidate["evidence"][0]["file"] = "../../etc/passwd"
        with self.assertRaises(SystemExit):
            verify.hash_cited_files(self.candidate)


if __name__ == "__main__":
    sys.exit(unittest.main())
