"""The swarm runs on one model. These checks fail if a config file starts choosing models per agent.

    python3 -m unittest discover -s security/redteam/tests -v
"""
import json
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODEL_KEYS = ("model", "model_reasoning_effort", "model_provider", "profile")


class OneModelPerSwarmTests(unittest.TestCase):
    def test_custom_agents_do_not_choose_a_model(self):
        files = sorted((ROOT / ".codex" / "agents").glob("*.toml"))
        self.assertTrue(files)
        for f in files:
            data = tomllib.loads(f.read_text(encoding="utf-8"))
            self.assertEqual({"name", "description", "developer_instructions"}, set(data), f.name)

    def test_project_config_sets_no_model_and_no_subagent_default(self):
        data = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        self.assertNotIn("model", data)
        self.assertNotIn("default_subagent_model", data.get("agents", {}))
        self.assertNotIn("default_subagent_reasoning_effort", data.get("agents", {}))

    def test_shipped_plan_has_no_per_agent_model(self):
        plan = json.loads((ROOT / "security" / "redteam" / "plans" / "round-1.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["model_policy"]["mode"], "same-model")
        for agent in plan["agents"]:
            self.assertFalse(set(MODEL_KEYS) & set(agent), agent["agent_id"])


if __name__ == "__main__":
    unittest.main()
