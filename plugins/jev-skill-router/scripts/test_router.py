"""Committed tests for scripts/jev-route.py. Run: python3 scripts/test_router.py"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "jev_route_mod", os.path.join(HERE, "jev-route.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load()
heuristic_rank = _mod.heuristic_rank
jev_request = _mod.jev_request
prefilter = _mod.prefilter
score_skill = _mod.score_skill

CATALOG = {
    "skills": [
        {"id": "zereight-review", "activation": "on",
         "description": "code review for PR feedback, correctness and edge cases"},
        {"id": "plantuml-skill", "activation": "on",
         "description": "diagrams, sequence diagrams, render PlantUML to images"},
        {"id": "bankx-jira", "activation": "off",
         "description": "Jira issue lookup for BankX"},
    ]
}


class RouterTest(unittest.TestCase):
    def setUp(self):
        self.skills = CATALOG["skills"]

    def test_prefilter_finds_review(self):
        got = prefilter("please review this PR diff", self.skills)
        self.assertEqual(got[0]["id"], "zereight-review")

    def test_prefilter_finds_diagram_skill(self):
        got = prefilter("draw a sequence diagram as PNG", self.skills)
        self.assertEqual(got[0]["id"], "plantuml-skill")

    def test_prefilter_empty_on_no_overlap(self):
        self.assertEqual(prefilter("xyzzy plugh qwerty", self.skills), [])

    def test_heuristic_scores_bounded(self):
        ranked = heuristic_rank("review this PR", self.skills)
        self.assertEqual(ranked[0]["score"], 1.0)
        self.assertTrue(all(0 <= r["score"] <= 1 for r in ranked))

    def test_jev_request_shape(self):
        body = jev_request("review this PR", self.skills[:2])
        self.assertIn("model", body)
        self.assertEqual(body["state"], "review this PR")
        self.assertEqual(set(body["questions"]),
                         {"zereight-review", "plantuml-skill"})
        self.assertTrue(all(q.get("type") == "noul" and "instructions" in q
                            for q in body["questions"].values()))

    def test_cli_end_to_end(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(CATALOG, fh)
            path = fh.name
        try:
            proc = subprocess.run(
                [sys.executable, os.path.join(HERE, "jev-route.py"),
                 "review this PR", "--catalog", path, "--top", "2"],
                capture_output=True, text=True, check=False)
        finally:
            os.unlink(path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ranked = json.loads(proc.stdout)
        self.assertEqual(ranked[0]["id"], "zereight-review")


if __name__ == "__main__":
    unittest.main()
