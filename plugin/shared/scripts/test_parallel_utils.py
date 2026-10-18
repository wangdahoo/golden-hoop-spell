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


if __name__ == "__main__":
    unittest.main()
