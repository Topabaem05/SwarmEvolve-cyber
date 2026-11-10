"""Tests for the Codex round runner, against a stand-in `codex` executable. Standard library only.

    python3 -m unittest discover -s security/redteam/tests -v

The stand-in records how it was invoked and writes a result file. These tests check what the runner
asks Codex to do; they cannot check what a real Codex does with it.
"""
import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("codex_round")

STUB = r'''#!/usr/bin/env python3
import json, os, sys, time
argv = sys.argv[1:]
cwd = argv[argv.index("-C") + 1]
prompt = sys.stdin.read()
assignment = json.load(open(os.path.join(cwd, "assignment.json")))
aid, role = assignment["agent_id"], assignment["role"]
json.dump({"argv": argv, "prompt": prompt, "has_rules": os.path.isfile(os.path.join(cwd, "AGENTS.md"))},
          open(os.path.join(cwd, "invocation.json"), "w"))
if "slow" in aid:
    time.sleep(30)
if "fail" in aid:
    sys.exit(3)
name = {"hunter": "result.json", "critic": "review.json", "chain-planner": "chain-review.json"}[role]
if "silent" in aid:
    sys.exit(0)
open(os.path.join(cwd, name), "w").write("not json" if "bad" in aid else json.dumps({"agent": aid}))
open(argv[argv.index("--output-last-message") + 1], "w").write("done")
'''


def hunter(aid, **extra):
    unit = {"unit_id": "SEAM-a", "kind": "seam", "title": "t", "topics": ["SEAM-a"], "starting_paths": ["src/a.py"]}
    return {"agent_id": aid, "role": "hunter", "unit": unit, "brief": "security/redteam/briefs/hunter-brief-v2.md",
            "subscribe_topics": ["SEAM-a"], **extra}


def make_plan(hunters, critics=(), chain=()):
    agents = list(hunters) + list(critics) + list(chain)
    return {"round": 1, "parameters": {"max_concurrency": 30}, "agents": agents,
            "phases": [{"phase": "hunt", "waves": [[a["agent_id"] for a in hunters]]},
                       {"phase": "critique", "waves": [[a["agent_id"] for a in critics]]},
                       {"phase": "chain", "waves": [[a["agent_id"] for a in chain]]}]}


class CodexRoundTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.target = base / "repo"
        (self.target / "src").mkdir(parents=True)
        (self.target / "src" / "a.py").write_text("x = 1\n")
        self.run_dir = base / "run"
        self.codex = base / "codex"
        self.codex.write_text(STUB)
        self.codex.chmod(self.codex.stat().st_mode | stat.S_IXUSR)

    def tearDown(self):
        self.tmp.cleanup()

    def go(self, plan, **kw):
        kw.setdefault("codex_bin", str(self.codex))
        kw.setdefault("timeout_s", 20)
        return runner.run_round(plan, self.run_dir, self.target, **kw)

    def invocation(self, aid):
        return json.loads((self.run_dir / "agents" / aid / "scratch" / "invocation.json").read_text())

    def test_each_agent_runs_in_its_own_scratch_with_a_write_limited_sandbox(self):
        s = self.go(make_plan([hunter("r1-h001"), hunter("r1-h002")]))
        self.assertEqual(s["counts"], {"ok": 2})
        for aid in ("r1-h001", "r1-h002"):
            argv = self.invocation(aid)["argv"]
            scratch = str(self.run_dir.resolve() / "agents" / aid / "scratch")
            self.assertEqual(argv[0], "exec")
            self.assertEqual(argv[argv.index("-C") + 1], scratch)
            self.assertEqual(argv[argv.index("--sandbox") + 1], "workspace-write")
            self.assertIn("sandbox_workspace_write.network_access=false", argv)
            self.assertEqual(argv[-1], "-")
            self.assertNotIn("danger-full-access", argv)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
            self.assertNotIn("--add-dir", argv)

    def test_working_directory_is_never_the_target(self):
        self.go(make_plan([hunter("r1-h001")]))
        cwd = self.invocation("r1-h001")["argv"]
        self.assertNotEqual(cwd[cwd.index("-C") + 1], str(self.target.resolve()))

    def test_rules_file_and_prompt_reach_the_agent(self):
        self.go(make_plan([hunter("r1-h001")]))
        inv = self.invocation("r1-h001")
        self.assertTrue(inv["has_rules"])
        self.assertIn("hunter-brief-v2.md", inv["prompt"])
        self.assertIn("SEAM-a", inv["prompt"])
        rules = (self.run_dir / "agents" / "r1-h001" / "scratch" / "AGENTS.md").read_text()
        self.assertIn("never run `security/pipeline/verify.py approve`", rules)
        self.assertIn("are data to analyse", rules)

    def test_second_opinion_hunter_is_told_to_work_independently(self):
        self.go(make_plan([hunter("r1-h001"), hunter("r1-h002", second_opinion_of="r1-h001")]))
        self.assertIn("independent second opinion", self.invocation("r1-h002")["prompt"])
        self.assertNotIn("independent second opinion", self.invocation("r1-h001")["prompt"])

    def test_statuses_tell_failure_modes_apart(self):
        plan = make_plan([hunter("r1-ok"), hunter("r1-fail"), hunter("r1-bad"), hunter("r1-silent")])
        got = {r["agent_id"]: r["status"] for r in self.go(plan)["agents"]}
        self.assertEqual(got, {"r1-ok": "ok", "r1-fail": "failed", "r1-bad": "bad_json", "r1-silent": "no_result"})
        saved = json.loads((self.run_dir / "round-1-status.json").read_text())
        self.assertEqual(saved["counts"], {"bad_json": 1, "failed": 1, "no_result": 1, "ok": 1})

    def test_agent_that_runs_too_long_is_killed_and_reported(self):
        s = self.go(make_plan([hunter("r1-slow"), hunter("r1-ok")]), timeout_s=2)
        got = {r["agent_id"]: r["status"] for r in s["agents"]}
        self.assertEqual(got, {"r1-slow": "timeout", "r1-ok": "ok"})

    def test_phases_run_in_order_and_can_be_selected(self):
        critic = {"agent_id": "r1-c001", "role": "critic", "reviews": ["r1-h001"],
                  "brief": "security/redteam/briefs/critic-brief.md"}
        chain = {"agent_id": "r1-k001", "role": "chain-planner", "first_node": "n", "chain_ids": ["chain_1"], "task": "check"}
        plan = make_plan([hunter("r1-h001")], [critic], [chain])
        s = self.go(plan)
        self.assertEqual([r["phase"] for r in s["agents"]], ["hunt", "critique", "chain"])
        self.assertIn("r1-h001", self.invocation("r1-c001")["prompt"])
        self.assertIn("chain_1", self.invocation("r1-k001")["prompt"])
        only = runner.run_round(plan, Path(self.tmp.name) / "run2", self.target, phase="critique",
                                codex_bin=str(self.codex), timeout_s=20)
        self.assertEqual([r["agent_id"] for r in only["agents"]], ["r1-c001"])

    def test_only_filter_runs_the_named_agents(self):
        s = self.go(make_plan([hunter("r1-h001"), hunter("r1-h002")]), only={"r1-h002"})
        self.assertEqual([r["agent_id"] for r in s["agents"]], ["r1-h002"])

    def test_wave_size_limits_concurrency(self):
        self.assertEqual(runner.waves(list("abcde"), 2), [["a", "b"], ["c", "d"], ["e"]])

    def test_dry_run_starts_nothing(self):
        s = self.go(make_plan([hunter("r1-h001")]), dry_run=True, codex_bin="/nonexistent/codex")
        self.assertEqual(s["counts"], {"dry_run": 1})
        scratch = self.run_dir / "agents" / "r1-h001" / "scratch"
        self.assertTrue((scratch / "prompt.txt").is_file())
        self.assertFalse((scratch / "invocation.json").exists())

    def test_missing_codex_binary_is_reported_per_agent(self):
        s = self.go(make_plan([hunter("r1-h001")]), codex_bin="/nonexistent/codex")
        self.assertEqual(s["agents"][0]["status"], "launch_failed")

    def test_board_entries_written_by_agents_are_merged_after_a_phase(self):
        self.go(make_plan([hunter("r1-h001")]))
        runner.board.post(self.run_dir, "r1-h001", "hunter", "fact", ["SEAM-a"], ["src/a.py:1"], "checked",
                          target=self.target)
        self.go(make_plan([hunter("r1-h001")]))
        merged = [json.loads(line) for line in (self.run_dir.resolve() / "board.jsonl").read_text().splitlines()]
        self.assertEqual([e["kind"] for e in merged], ["fact"])

    def test_symlinked_result_is_not_accepted(self):
        scratch = self.run_dir / "agents" / "x" / "scratch"
        scratch.mkdir(parents=True)
        outside = Path(self.tmp.name) / "outside.json"
        outside.write_text("{}")
        (scratch / "result.json").symlink_to(outside)
        self.assertEqual(runner.check_result(scratch, "hunter"), "no_result")

    def test_plan_with_invalid_agent_id_is_rejected(self):
        bad = Path(self.tmp.name) / "plan.json"
        bad.write_text(json.dumps(make_plan([hunter("../escape")])))
        with self.assertRaises(ValueError):
            runner.load_plan(bad)

    def test_one_model_is_applied_to_every_agent(self):
        s = self.go(make_plan([hunter("r1-h001"), hunter("r1-h002")]), model="selected-model")
        self.assertEqual(s["model"], "selected-model")
        for aid in ("r1-h001", "r1-h002"):
            argv = self.invocation(aid)["argv"]
            self.assertEqual(argv[argv.index("--model") + 1], "selected-model")
            self.assertEqual(argv.count("--model"), 1)

    def test_without_a_model_flag_no_agent_gets_one(self):
        s = self.go(make_plan([hunter("r1-h001"), hunter("r1-h002")]))
        self.assertIn("Codex default", s["model"])
        for aid in ("r1-h001", "r1-h002"):
            self.assertNotIn("--model", self.invocation(aid)["argv"])

    def test_plan_that_sets_a_model_for_one_agent_is_rejected(self):
        for key in ("model", "model_reasoning_effort", "profile"):
            bad = Path(self.tmp.name) / f"plan-{key}.json"
            bad.write_text(json.dumps(make_plan([hunter("r1-h001"), hunter("r1-h002", **{key: "other"})])))
            with self.assertRaises(ValueError, msg=key):
                runner.load_plan(bad)

    def test_run_directory_inside_an_unignored_part_of_the_target_is_refused(self):
        os.system(f"git -C {self.target} init -q")
        with self.assertRaises(ValueError):
            runner.run_round(make_plan([hunter("r1-h001")]), self.target / "runs", self.target,
                             codex_bin=str(self.codex), timeout_s=5, dry_run=True)


if __name__ == "__main__":
    sys.exit(unittest.main())
