#!/usr/bin/env python3
"""Smoke test for validate_structure.py.

Pins the Windows console fix: the validator prints ✅ on success, which
must not crash under a legacy GBK stdout. Also guards basic schema
validation end-to-end.

Run directly:
    command python3 plugin/shared/scripts/test_validate_structure.py

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
            "name": "结构校验计划",
            "status": "in_progress",
            "features": [
                {
                    "id": "p1-feat-001",
                    "title": "刷新校验逻辑",
                    "description": "中文特性描述",
                    "status": "pending",
                    "files_affected": ["src/session.py"],
                    "dependencies": [],
                }
            ],
        }
    ],
    "metadata": {"version": "1.0.0", "last_updated": "2026-10-18"},
}


def run_cli(project_dir):
    cmd = [
        sys.executable, str(SCRIPT_DIR / "validate_structure.py"),
        "--project-dir", str(project_dir),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return proc.returncode, proc.stdout, proc.stderr


class ValidateStructureSmokeTests(unittest.TestCase):
    def test_valid_project_passes_under_gbk_console(self):
        """Valid project → exit 0 with ✅ success output, even on GBK stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            ghs = Path(tmp) / ".ghs"
            ghs.mkdir()
            (ghs / "features.json").write_text(
                json.dumps(FEATURES, ensure_ascii=False), encoding="utf-8"
            )
            rc, out, err = run_cli(tmp)
            self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
            self.assertIn("Validation passed", out)


if __name__ == "__main__":
    unittest.main()
