#!/usr/bin/env python3
"""Unit tests for update_features.py.

Pins the features.json status mutation contract: strict read-modify-write
(unknown fields preserved), enum validation aligned with validate_structure,
blocked-reason enforcement, stale blocked_reason cleanup, plan completion
state computation, and single-line ASCII stdout — even under a legacy GBK
console (PYTHONIOENCODING=gbk).

Run directly:
    command python3 plugin/shared/scripts/test_update_features.py

No pytest dependency. Uses only the standard unittest module.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Make update_features importable as a sibling module.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import update_features as helper  # noqa: E402

PLAN_P1 = {
    "id": "p1",
    "name": "demo plan",
    "status": "in_progress",
    "features": [
        {"id": "p1-feat-001", "title": "done feat", "status": "completed"},
        {"id": "p1-feat-002", "title": "todo feat", "status": "pending"},
        {
            "id": "p1-feat-003",
            "title": "stuck feat",
            "status": "blocked",
            "blocked_reason": "waiting for API",
        },
    ],
    "custom_keep": "keep-me",
}


def make_features(plans):
    return {"project": {"name": "demo"}, "plans": plans}


class UpdateFeaturesCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.feat_path = self.tmp / "features.json"
        self.feat_path.write_text(
            json.dumps(make_features([PLAN_P1]), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def run_cli(self, args, cwd=None):
        cmd = [sys.executable, str(SCRIPT_DIR / "update_features.py")] + args
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr

    def reload_data(self):
        return json.loads(self.feat_path.read_text(encoding="utf-8"))

    # ---- --set-feature ----

    def test_set_feature_completed(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "p1-feat-002",
             "--status", "completed"]
        )
        self.assertEqual(rc, 0, err)
        self.assertIn("OK feature p1-feat-002 status=completed", out)
        data = self.reload_data()
        feat = data["plans"][0]["features"][1]
        self.assertEqual(feat["status"], "completed")
        self.assertEqual(data["plans"][0]["custom_keep"], "keep-me")  # unknown kept

    def test_set_feature_blocked_requires_reason(self):
        before = self.feat_path.read_bytes()
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "p1-feat-002",
             "--status", "blocked"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("--blocked-reason", err)
        self.assertEqual(before, self.feat_path.read_bytes())  # file untouched

    def test_set_feature_blocked_with_reason(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "p1-feat-002",
             "--status", "blocked", "--blocked-reason", "upstream broken"]
        )
        self.assertEqual(rc, 0, err)
        feat = self.reload_data()["plans"][0]["features"][1]
        self.assertEqual(feat["status"], "blocked")
        self.assertEqual(feat["blocked_reason"], "upstream broken")

    def test_set_feature_clears_stale_reason(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "p1-feat-003",
             "--status", "completed"]
        )
        self.assertEqual(rc, 0, err)
        feat = self.reload_data()["plans"][0]["features"][2]
        self.assertEqual(feat["status"], "completed")
        self.assertNotIn("blocked_reason", feat)

    def test_set_feature_invalid_enum(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "p1-feat-002",
             "--status", "done"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("must be one of", err)

    def test_set_feature_not_found(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "pX-feat-999",
             "--status", "completed"]
        )
        self.assertEqual(rc, 1)
        self.assertIn("not found", err)

    def test_set_feature_ambiguous_id(self):
        dup = {
            "id": "p2",
            "name": "other plan",
            "status": "in_progress",
            "features": [{"id": "p1-feat-001", "title": "dup", "status": "pending"}],
        }
        self.feat_path.write_text(
            json.dumps(make_features([PLAN_P1, dup]), ensure_ascii=False), encoding="utf-8"
        )
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "p1-feat-001",
             "--status", "completed"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("ambiguous", err)

    # ---- --set-plan ----

    def test_set_plan_completed(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-plan", "p1", "--status", "completed"]
        )
        self.assertEqual(rc, 0, err)
        self.assertIn("OK plan p1 status=completed", out)
        self.assertEqual(self.reload_data()["plans"][0]["status"], "completed")

    def test_set_plan_invalid_enum(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-plan", "p1", "--status", "done"]
        )
        self.assertEqual(rc, 2)

    def test_set_plan_not_found(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-plan", "pX", "--status", "completed"]
        )
        self.assertEqual(rc, 1)

    # ---- --plan-state ----

    def test_plan_state_can_complete(self):
        plan = {
            "id": "p9", "name": "all done", "status": "in_progress",
            "features": [{"id": "p9-feat-001", "title": "t", "status": "completed"}],
        }
        self.feat_path.write_text(
            json.dumps(make_features([plan]), ensure_ascii=False), encoding="utf-8"
        )
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--plan-state", "p9"]
        )
        self.assertEqual(rc, 0, err)
        state = json.loads(out)
        self.assertTrue(state["can_complete"])
        self.assertEqual(state["counts"]["completed"], 1)
        self.assertEqual(state["plan_id"], "p9")
        self.assertEqual(state["blocked_ids"], [])

    def test_plan_state_with_blocked(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--plan-state", "p1"]
        )
        self.assertEqual(rc, 0, err)
        state = json.loads(out)
        self.assertFalse(state["can_complete"])
        self.assertEqual(state["counts"]["blocked"], 1)
        self.assertEqual(state["counts"]["pending"], 1)
        self.assertEqual(state["blocked_ids"], ["p1-feat-003"])

    def test_plan_state_not_found(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--plan-state", "pX"]
        )
        self.assertEqual(rc, 1)
        self.assertIn("not found", err)

    # ---- default path resolution ----

    def test_default_path_via_project_dir(self):
        project = self.tmp / "proj"
        (project / ".ghs").mkdir(parents=True)
        (project / ".ghs" / "features.json").write_text(
            json.dumps(make_features([PLAN_P1]), ensure_ascii=False), encoding="utf-8"
        )
        rc, out, err = self.run_cli(
            ["--set-feature", "p1-feat-002", "--status", "completed"],
            cwd=str(project),
        )
        self.assertEqual(rc, 0, err)
        data = json.loads(
            (project / ".ghs" / "features.json").read_text(encoding="utf-8")
        )
        self.assertEqual(data["plans"][0]["features"][1]["status"], "completed")


class UpdateFeaturesUnitTests(unittest.TestCase):
    def test_locate_feature_ambiguous_raises_valueerror(self):
        data = make_features([
            {"id": "a", "features": [{"id": "dup", "status": "pending"}]},
            {"id": "b", "features": [{"id": "dup", "status": "pending"}]},
        ])
        with self.assertRaises(ValueError):
            helper.locate_feature(data, "dup")

    def test_locate_feature_missing_raises_keyerror(self):
        with self.assertRaises(KeyError):
            helper.locate_feature(make_features([PLAN_P1]), "nope")

    def test_compute_plan_state_mixed_counts(self):
        state = helper.compute_plan_state(make_features([PLAN_P1]), "p1")
        self.assertEqual(
            state["counts"],
            {"completed": 1, "in_progress": 0, "pending": 1, "blocked": 1},
        )
        self.assertFalse(state["can_complete"])


if __name__ == "__main__":
    unittest.main()
