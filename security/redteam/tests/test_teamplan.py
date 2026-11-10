"""Tests for the team planner. Standard library only.

    python3 -m unittest discover -s security/redteam/tests -v
"""
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


teamplan = load("teamplan")
board = load("board")

REGISTRY = {"seams": [
    {"seam_id": "SEAM-a", "invariant_ids": ["INV-a"], "candidate_locations": ["src/app/server.py:3"], "hypothesis": "h"},
    {"seam_id": "SEAM-b", "invariant_ids": ["INV-b"], "candidate_locations": ["src/app/store.py:1"], "hypothesis": "h"},
]}
LEDGER = [{"coverage_id": "x::y", "status": "deferred", "surface": "core", "starting_paths": ["src/core"]},
          {"coverage_id": "p::q", "status": "covered", "surface": "done", "starting_paths": ["src/app"]}]


class TeamPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.write("src/app/server.py", "import subprocess\n" + "x = 1\n" * 50)
        self.write("src/app/store.py", "import pickle\npickle.load(f)\n" + "y = 2\n" * 30)
        self.write("src/core/engine.py", "z = 3\n" * 400)
        self.write("src/core/util.py", "w = 4\n" * 20)
        self.write("src/tests/test_x.py", "t = 1\n" * 500)
        self.write("src/app/data.bin", "\0" * 10)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def plan(self, **kw):
        kw.setdefault("scope", ("src",))
        kw.setdefault("registry", REGISTRY)
        kw.setdefault("ledger", LEDGER)
        return teamplan.plan(self.repo, **kw)

    def test_excluded_directories_and_non_code_files_are_not_measured(self):
        r = self.plan()
        self.assertEqual(r["codebase"]["files"], 4)
        paths = {p for a in r["agents"] if a["role"] == "hunter" for p in a["unit"]["starting_paths"]}
        self.assertFalse(any("tests" in p or p.endswith(".bin") for p in paths))

    def test_small_codebase_is_raised_to_the_floor_with_second_opinions(self):
        r = self.plan(min_team=30)
        self.assertGreaterEqual(r["sizing"]["team"], 30)
        self.assertGreater(r["sizing"]["second_opinion_hunters"], 0)
        seconds = [a for a in r["agents"] if a.get("second_opinion_of")]
        self.assertEqual(len(seconds), r["sizing"]["second_opinion_hunters"])
        ids = {a["agent_id"] for a in r["agents"]}
        self.assertTrue(all(a["second_opinion_of"] in ids for a in seconds))
        # the first second opinions go to the highest-priority units: the seams
        self.assertEqual(seconds[0]["unit"]["kind"], "seam")

    def test_team_is_hunters_plus_critics_plus_chain(self):
        r = self.plan(min_team=1, critic_ratio=3)
        z = r["sizing"]
        self.assertEqual(z["critics"], math.ceil(z["hunters"] / 3))
        self.assertEqual(z["team"], z["hunters"] + z["critics"] + z["chain_investigators"])
        self.assertEqual(z["team"], len(r["agents"]))

    def test_larger_codebase_needs_more_hunters(self):
        small = self.plan(min_team=1, weight_per_hunter=300)["sizing"]["hunters"]
        for i in range(12):
            self.write(f"src/core/more_{i}.py", "q = 1\n" * 250)
        large = self.plan(min_team=1, weight_per_hunter=300)["sizing"]["hunters"]
        self.assertGreater(large, small)

    def test_riskier_code_gets_smaller_shards(self):
        self.write("src/core/sinks.py", "import pickle\n" + "pickle.load(f)\n" * 40)
        calm = self.plan(min_team=1, weight_per_hunter=300, risk_weight=0)["demand"]["shard_units"]
        risky = self.plan(min_team=1, weight_per_hunter=300, risk_weight=40)["demand"]["shard_units"]
        self.assertGreater(risky, calm)

    def test_file_heavier_than_the_budget_is_split_into_line_ranges(self):
        r = self.plan(min_team=1, weight_per_hunter=100)
        parts = [a["unit"] for a in r["agents"] if a["role"] == "hunter" and a["unit"].get("part")
                 and a["unit"]["starting_paths"] == ["src/core/engine.py"]]
        self.assertEqual(sorted(p["part"] for p in parts), ["1/4", "2/4", "3/4", "4/4"])
        ranges = sorted(p["approx_nonblank_line_range"] for p in parts)
        self.assertEqual((ranges[0][0], ranges[-1][1]), (1, 400))
        self.assertTrue(all(ranges[i][1] + 1 == ranges[i + 1][0] for i in range(3)))  # contiguous, no overlap

    def test_ceiling_defers_shards_before_seams_and_reports_them(self):
        r = self.plan(min_team=1, max_team=4, weight_per_hunter=100)
        self.assertLessEqual(r["sizing"]["team"], 4)
        self.assertTrue(r["deferred_units"])
        self.assertTrue(all(u["kind"] == "shard" for u in r["deferred_units"]))
        kept = [a["unit"]["kind"] for a in r["agents"] if a["role"] == "hunter"]
        self.assertIn("seam", kept)
        planned = len(kept) + len(r["deferred_units"])
        d = r["demand"]
        self.assertEqual(planned, d["seam_units"] + d["lead_units"] + d["deferred_units"] + d["shard_units"])

    def test_only_deferred_ledger_units_become_work(self):
        r = self.plan(min_team=1)
        self.assertEqual(r["demand"]["deferred_units"], 1)

    def test_every_hunter_has_exactly_one_critic(self):
        r = self.plan(min_team=30)
        hunters = [a["agent_id"] for a in r["agents"] if a["role"] == "hunter"]
        reviewed = [h for a in r["agents"] if a["role"] == "critic" for h in a["reviews"]]
        self.assertEqual(sorted(reviewed), sorted(hunters))

    def test_agent_ids_are_valid_and_unique(self):
        r = self.plan(min_team=40)
        ids = [a["agent_id"] for a in r["agents"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(teamplan.AGENT_RE.match(i) and board.AGENT_RE.match(i) for i in ids))

    def test_waves_respect_the_concurrency_limit_and_cover_everyone(self):
        r = self.plan(min_team=30, max_concurrency=7)
        in_waves = [i for ph in r["phases"] for w in ph["waves"] for i in w]
        self.assertTrue(all(len(w) <= 7 for ph in r["phases"] for w in ph["waves"]))
        self.assertEqual(sorted(in_waves), sorted(a["agent_id"] for a in r["agents"]))
        self.assertEqual([ph["phase"] for ph in r["phases"]], ["hunt", "critique", "chain"])

    def test_chain_groups_add_investigators_up_to_the_cap(self):
        chains = {"candidates": [{"chain_id": f"c{i}", "ordered_node_ids": [f"n{i}", "t"],
                                  "status": "blocked_on_unconfirmed_components"} for i in range(5)]}
        self.assertEqual(self.plan(min_team=1, chains=chains, chain_top_k=3)["sizing"]["chain_investigators"], 3)
        self.assertEqual(self.plan(min_team=1, chains=chains, chain_mode="ready-only")["sizing"]["chain_investigators"], 0)

    def test_unowned_board_lead_becomes_a_unit_and_owned_one_does_not(self):
        run = Path(self.tmp.name) / "run"
        board.post(run, "r1-h001", "hunter", "lead", ["NEW-TOPIC"], ["src/core/util.py:1"], "look at the loader")
        board.post(run, "r1-h001", "hunter", "lead", ["SEAM-a"], [], "already owned seam")
        entries = board.load_all(run)[0]
        r = self.plan(min_team=1, board_entries=entries)
        leads = [a["unit"] for a in r["agents"] if a["role"] == "hunter" and a["unit"]["kind"] == "lead"]
        self.assertEqual(len(leads), 1)
        self.assertEqual((leads[0]["topics"], leads[0]["starting_paths"]), (["NEW-TOPIC"], ["src/core/util.py"]))

    def test_units_finished_in_an_earlier_round_are_not_planned_again(self):
        first = self.plan(min_team=1)
        run = Path(self.tmp.name) / "run"
        owner = next(a for a in first["agents"] if a["role"] == "hunter" and a["unit"]["unit_id"] == "SEAM-a")
        result = run / "agents" / owner["agent_id"] / "scratch" / "result.json"
        result.parent.mkdir(parents=True)
        result.write_text("{}")
        done = teamplan.completed_units(first, run)
        self.assertEqual(done, {"SEAM-a"})
        second = self.plan(min_team=1, round_no=2, done=done)
        units = [a["unit"]["unit_id"] for a in second["agents"] if a["role"] == "hunter"]
        self.assertNotIn("SEAM-a", units)
        self.assertTrue(all(a["agent_id"].startswith("r2-") for a in second["agents"]))

    def test_floor_above_ceiling_is_an_error(self):
        with self.assertRaises(ValueError):
            self.plan(min_team=50, max_team=40)

    def test_planning_is_deterministic(self):
        self.assertEqual(self.plan(min_team=30), self.plan(min_team=30))


if __name__ == "__main__":
    unittest.main()
