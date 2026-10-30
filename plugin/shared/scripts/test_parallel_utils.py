#!/usr/bin/env python3
"""Unit tests for parallel_utils.py.

Covers the ensure_ascii defect on the stdout JSON protocol: feature
titles and error paths containing non-ASCII must be emitted as literal
characters, never \\uXXXX escapes.

Run directly:
    command python3 plugin/shared/scripts/test_parallel_utils.py

No pytest dependency. Uses only the standard unittest module.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

FEATURES = {
    "project": {"name": "demo", "description": "演示项目", "created_at": "2026-10-18"},
    "plans": [
        {
            "id": "p1",
            "name": "并行演示计划",
            "status": "in_progress",
            "features": [
                {
                    "id": "p1-feat-001",
                    "title": "刷新校验逻辑",
                    "status": "pending",
                    "files_affected": ["src/session.py"],
                    "dependencies": [],
                }
            ],
        }
    ],
    "metadata": {"version": "1.0.0", "last_updated": "2026-10-18"},
}


def run_cli(args):
    cmd = [sys.executable, str(SCRIPT_DIR / "parallel_utils.py")] + args
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return proc.returncode, proc.stdout, proc.stderr


class ParallelOutputLiteralChineseTests(unittest.TestCase):
    def test_ready_feature_title_is_literal(self):
        """Ready-feature JSON on stdout keeps Chinese titles literal."""
        with tempfile.TemporaryDirectory() as tmp:
            ghs = Path(tmp) / ".ghs"
            ghs.mkdir()
            (ghs / "features.json").write_text(
                json.dumps(FEATURES, ensure_ascii=False), encoding="utf-8"
            )
            rc, out, err = run_cli(["--project-dir", tmp])
            self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
            self.assertIn("刷新校验逻辑", out)
            self.assertNotIn("\\u", out, "titles must not be escaped as \\uXXXX")

    def test_error_path_keeps_chinese_dir_literal(self):
        """The missing-features.json error JSON keeps a Chinese path literal."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "中文项目目录"
            project.mkdir()
            rc, out, err = run_cli(["--project-dir", str(project)])
            self.assertEqual(rc, 1, f"stdout={out!r}\nstderr={err!r}")
            self.assertIn("中文项目目录", out)
            self.assertNotIn("\\u", out)


class PlanSelectionGuardTests(unittest.TestCase):
    """Without --plan-id, multiple plans must be a hard error (exit 2 on
    stderr), never a silent plans[0] guess."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name)
        (self.project / ".ghs").mkdir(parents=True)

    def write_features(self, plan_ids):
        plans = [
            {
                "id": pid,
                "name": f"plan {pid}",
                "status": "in_progress",
                "features": [
                    {"id": f"{pid}-feat-001", "title": "t", "status": "pending"}
                ],
            }
            for pid in plan_ids
        ]
        data = {"project": {"name": "demo"}, "plans": plans}
        (self.project / ".ghs" / "features.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def run_cli(self, *extra):
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "parallel_utils.py"),
            "--project-dir",
            str(self.project),
        ] + list(extra)
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_multiple_plans_without_plan_id_errors(self):
        self.write_features(["pa", "pb"])
        rc, out, err = self.run_cli()
        self.assertEqual(rc, 2)
        self.assertIn("pa", err)
        self.assertIn("pb", err)
        self.assertIn("--plan-id", err)
        self.assertNotIn("ready_features", out)  # stdout stays clean

    def test_single_plan_without_plan_id_defaults(self):
        self.write_features(["only"])
        rc, out, err = self.run_cli()
        self.assertEqual(rc, 0, err)
        self.assertIn("ready_features", out)

    def test_explicit_plan_id_wins(self):
        self.write_features(["pa", "pb"])
        rc, out, err = self.run_cli("--plan-id", "pb")
        self.assertEqual(rc, 0, err)
        self.assertIn("pb-feat-001", out)
        self.assertNotIn("pa-feat-001", out)


if __name__ == "__main__":
    unittest.main()
