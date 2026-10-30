#!/usr/bin/env python3
"""Unit tests for archive_plans.py.

Covers the ensure_ascii defect: .ghs JSON artifacts (the active
features.json rewrite and per-plan archive files) must keep non-ASCII
content as literal characters, never \\uXXXX escapes.

Also covers the full-snapshot archive semantics: the archived progress.md
is a lossless snapshot of the whole Sessions section ('**Plan**: N/A'
entries included), and the removal branch keeps unmatched entries.

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

import archive_plans  # noqa: E402

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


def build_progress_md():
    """A progress.md exercising every entry kind, newest first."""
    return (
        "# Project Progress Log\n"
        "\n"
        "Human-readable session record.\n"
        "\n"
        "---\n"
        "\n"
        "## Sessions\n"
        "\n"
        "## Session 1 - 2026-10-30\n"
        "**Agent**: Init Agent\n"
        "**Plan**: N/A\n"
        "**Feature**: N/A\n"
        "\n"
        "### Work Completed\n"
        "- NA-MARKER-INIT initialized the project skeleton\n"
        "\n"
        "## Feature Planning - 2026-10-30\n"
        "**Agent**: Plan Materializer\n"
        "**Plan**: p1 (source: docs/ghs/plans/demo.md)\n"
        "**Features**: 2 task(s) materialized\n"
        "\n"
        "## Session 2 - 2026-10-30\n"
        "**Agent**: Coding Agent\n"
        "**Plan**: p1\n"
        "**Feature**: p1-feat-001\n"
        "\n"
        "### Work Completed\n"
        "- P1-MARKER-CODE implemented p1-feat-001\n"
        "\n"
        "## Session 3 - 2026-10-30\n"
        "**Agent**: Coding Agent\n"
        "**Plan**: p2\n"
        "**Feature**: p2-feat-001\n"
        "\n"
        "### Work Completed\n"
        "- P2-MARKER-CODE implemented p2-feat-001\n"
    )


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


class ArchiveFolderSanitizationTests(unittest.TestCase):
    """Plan names containing Windows-illegal characters must not crash
    archiving (dogfood incident: NotADirectoryError on ':'). Folder names
    are sanitized; archived plan DATA keeps the original name verbatim."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name)
        self.archived = self.project / "archived"
        self.archived.mkdir(parents=True)

    def test_folder_name_sanitized_data_preserved(self):
        original_name = 'dogfood 修复:Windows/编码 "quoted" 计划'
        plan = {
            "id": "px",
            "name": original_name,
            "status": "completed",
            "features": [
                {"id": "px-feat-001", "title": "t", "status": "completed"}
            ],
        }
        features_data = {"project": {"name": "demo"}, "plans": [plan]}

        feat_path, _prog_path = archive_plans.archive_plan_files(
            plan, features_data, self.project, self.archived
        )

        folder = feat_path.parent
        self.assertTrue(folder.exists())
        self.assertTrue(folder.name.startswith("px_"))
        for ch in '\\/:*?"<>|':
            self.assertNotIn(ch, folder.name)
        # Archived DATA keeps the original name verbatim.
        archived = json.loads(feat_path.read_text(encoding="utf-8"))
        self.assertEqual(archived["archived_plan"]["name"], original_name)

    def test_empty_name_falls_back_to_plan_id(self):
        plan = {
            "id": "py",
            "name": '///:***',
            "status": "completed",
            "features": [
                {"id": "py-feat-001", "title": "t", "status": "completed"}
            ],
        }
        features_data = {"project": {"name": "demo"}, "plans": [plan]}
        feat_path, _prog_path = archive_plans.archive_plan_files(
            plan, features_data, self.project, self.archived
        )
        # All chars stripped -> sanitized part empty -> folder falls back to plan id.
        self.assertTrue(feat_path.parent.name.startswith("py_"))


class ArchiveFullSnapshotTests(unittest.TestCase):
    """The archived progress.md is a FULL snapshot of the Sessions section.

    Regression guard for the dogfood incident where the pick-style extractor
    dropped '**Plan**: N/A' entries (the p1 Init entry was lost on archive):
    selection-based extraction is retired, so every branch (reset and remove
    alike) must preserve N/A entries in the archived snapshot, and the
    removal branch must keep unmatched entries in the active file.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name)
        self.ghs = self.project / ".ghs"
        self.ghs.mkdir()
        self.progress_path = self.ghs / "progress.md"

    def _write_progress(self, content):
        self.progress_path.write_text(content, encoding="utf-8")

    def _write_features(self, plans):
        data = {
            "project": {"name": "demo"},
            "plans": plans,
            "metadata": {"version": "1.0.0", "last_updated": "2026-10-30"},
        }
        (self.ghs / "features.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    @staticmethod
    def _completed_plan(plan_id):
        return {
            "id": plan_id,
            "name": f"plan {plan_id}",
            "status": "completed",
            "features": [
                {"id": f"{plan_id}-feat-001", "title": "t", "status": "completed"}
            ],
        }

    @staticmethod
    def _in_progress_plan(plan_id):
        return {
            "id": plan_id,
            "name": f"plan {plan_id}",
            "status": "in_progress",
            "features": [
                {"id": f"{plan_id}-feat-001", "title": "t", "status": "pending"}
            ],
        }

    def test_extract_sessions_section_full_snapshot(self):
        """Full snapshot: the N/A session, Feature Planning and remaining-plan
        entries are all included, in original file order."""
        self._write_progress(build_progress_md())
        snapshot = archive_plans.extract_sessions_section(self.progress_path)

        # Every entry kind is present, including the N/A one.
        for marker in (
            "NA-MARKER-INIT",
            "## Feature Planning - 2026-10-30",
            "P1-MARKER-CODE",
            "P2-MARKER-CODE",
        ):
            self.assertIn(marker, snapshot)
        self.assertIn("**Plan**: N/A", snapshot)

        # The file header is not part of the section.
        self.assertNotIn("# Project Progress Log", snapshot)

        # Original file order preserved (newest first).
        positions = [
            snapshot.index("NA-MARKER-INIT"),
            snapshot.index("## Feature Planning - 2026-10-30"),
            snapshot.index("P1-MARKER-CODE"),
            snapshot.index("P2-MARKER-CODE"),
        ]
        self.assertEqual(positions, sorted(positions))

    def test_extract_sessions_section_falls_back_without_heading(self):
        """A missing '## Sessions' heading still yields all entries (no loss)."""
        content = build_progress_md().replace("## Sessions\n", "", 1)
        self.assertNotIn("## Sessions", content)
        self._write_progress(content)
        snapshot = archive_plans.extract_sessions_section(self.progress_path)
        self.assertIn("NA-MARKER-INIT", snapshot)
        self.assertIn("## Feature Planning - 2026-10-30", snapshot)
        self.assertIn("P2-MARKER-CODE", snapshot)

    def test_extract_sessions_section_empty_section_returns_empty_string(self):
        """An empty Sessions section returns '' so the `if sessions:` guard
        skips writing an archive progress.md."""
        self._write_progress("# Log\n\n## Sessions\n")
        self.assertEqual(
            archive_plans.extract_sessions_section(self.progress_path), ""
        )

    def test_archive_reset_branch_keeps_plan_na_entry(self):
        """Reset branch (no plans remain): the N/A entry is preserved in the
        archived full snapshot before the active file is reset to template."""
        self._write_progress(build_progress_md())
        self._write_features([self._completed_plan("p1")])

        archived = archive_plans.archive_completed_plans(self.project)
        self.assertEqual(len(archived), 1)

        archived_progress = list((self.ghs / "archived").glob("*/progress.md"))
        self.assertEqual(
            len(archived_progress), 1, "reset branch must still write the snapshot"
        )
        text = archived_progress[0].read_text(encoding="utf-8")
        # The N/A entry reached the archive in full (p1 Init entry regression).
        self.assertIn("**Plan**: N/A", text)
        self.assertIn("NA-MARKER-INIT", text)
        # Full snapshot also carries the other entries of the section.
        self.assertIn("## Feature Planning - 2026-10-30", text)
        self.assertIn("P1-MARKER-CODE", text)

        # The reset branch actually ran: active file is back to the template.
        active = self.progress_path.read_text(encoding="utf-8")
        self.assertNotIn("NA-MARKER-INIT", active)
        self.assertIn("## Sessions", active)

    def test_remove_branch_keeps_unmatched_entries(self):
        """Remove branch (plans remain): only the archived plan's entries are
        removed from the active file; N/A and remaining-plan entries stay,
        and the archived copy is still the full snapshot."""
        self._write_progress(build_progress_md())
        self._write_features(
            [self._completed_plan("p1"), self._in_progress_plan("p2")]
        )

        archived = archive_plans.archive_completed_plans(self.project)
        self.assertEqual(len(archived), 1)

        # Active file: N/A entry and remaining p2 entry kept...
        active = self.progress_path.read_text(encoding="utf-8")
        self.assertIn("**Plan**: N/A", active)
        self.assertIn("NA-MARKER-INIT", active)
        self.assertIn("P2-MARKER-CODE", active)
        # ...while the archived plan's entries are gone.
        self.assertNotIn("P1-MARKER-CODE", active)
        self.assertNotIn("## Feature Planning - 2026-10-30", active)

        # Archived copy is the FULL snapshot, not a pick-style extract.
        archived_progress = list((self.ghs / "archived").glob("*/progress.md"))
        self.assertEqual(len(archived_progress), 1)
        text = archived_progress[0].read_text(encoding="utf-8")
        self.assertIn("NA-MARKER-INIT", text)
        self.assertIn("## Feature Planning - 2026-10-30", text)
        self.assertIn("P1-MARKER-CODE", text)
        self.assertIn("P2-MARKER-CODE", text)


if __name__ == "__main__":
    unittest.main()
