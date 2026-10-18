#!/usr/bin/env python3
"""Unit tests for archive_plans.py.

Covers the ensure_ascii defect: .ghs JSON artifacts (the active
features.json rewrite and per-plan archive files) must keep non-ASCII
content as literal characters, never \\uXXXX escapes.

Run directly:
    command python3 plugin/shared/scripts/test_archive_plans.py

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
    "project": {"name": "demo", "description": "演示项目描述", "created_at": "2026-10-18"},
    "plans": [
        {
            "id": "p1",
            "name": "归档演示计划",
            "status": "completed",
            "features": [
                {
                    "id": "p1-feat-001",
                    "title": "已完成特性",
                    "description": "中文特性描述",
                    "status": "completed",
                }
            ],
        },
        {
            "id": "p2",
            "name": "保留计划",
            "status": "in_progress",
            "features": [
                {"id": "p2-feat-001", "title": "进行中特性", "status": "pending"}
            ],
        },
    ],
    "metadata": {"version": "1.0.0", "last_updated": "2026-10-18"},
}


def run_cli(project_dir):
    cmd = [
        sys.executable, str(SCRIPT_DIR / "archive_plans.py"),
        "--project-dir", str(project_dir),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return proc.returncode, proc.stdout, proc.stderr


class ArchiveKeepsLiteralChineseTests(unittest.TestCase):
    def test_archiving_keeps_chinese_literal_in_all_json(self):
        """Archived copy AND the rewritten active features.json keep 中文 literal."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            ghs = project / ".ghs"
            ghs.mkdir()
            (ghs / "features.json").write_text(
                json.dumps(FEATURES, ensure_ascii=False), encoding="utf-8"
            )
            (ghs / "progress.md").write_text(
                "# Log\n\n## Sessions\n\n<!-- new entries above -->\n", encoding="utf-8"
            )
            rc, out, err = run_cli(project)
            self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")

            # Archived plan copy (archive_plans.py site: archive_plan_files)
            archives = list((ghs / "archived").glob("*/features.json"))
            self.assertEqual(len(archives), 1, f"expected one archive, got {archives}")
            archived_text = archives[0].read_text(encoding="utf-8")
            self.assertIn("归档演示计划", archived_text)
            self.assertIn("中文特性描述", archived_text)
            self.assertNotIn("\\u", archived_text)

            # Rewritten active features.json (archive_plans.py main flow)
            active_text = (ghs / "features.json").read_text(encoding="utf-8")
            active = json.loads(active_text)
            self.assertEqual(
                [p["id"] for p in active["plans"]], ["p2"], "completed plan must be removed"
            )
            self.assertIn("进行中特性", active_text)
            self.assertIn("演示项目描述", active_text)
            self.assertNotIn("\\u", active_text)


if __name__ == "__main__":
    unittest.main()
