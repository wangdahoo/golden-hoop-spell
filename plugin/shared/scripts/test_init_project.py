#!/usr/bin/env python3
"""Unit tests for init_project.py.

Covers three bugs found while dogfooding on zh-CN Windows:
1. `print("✓")` crashes with UnicodeEncodeError when stdout uses a legacy
   CJK encoding (e.g. cp936/GBK) — init must survive and still create
   every tracking file.
2. `ensure_gitignore` appends a duplicate `.ghs` entry when .gitignore
   already ignores the directory via a variant rule (`.ghs/`, `/.ghs/`).
3. A failure midway through init leaves partially created files behind,
   forcing the next run to pass --force — init must clean up after itself.

Run directly:
    command python3 plugin/shared/scripts/test_init_project.py

No pytest dependency. Uses only the standard unittest module.
"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Make init_project importable as a sibling module.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import init_project as init  # noqa: E402


def run_cli(args, env_extra=None):
    """Run init_project.py as a subprocess; return (returncode, stdout, stderr)."""
    cmd = [sys.executable, str(SCRIPT_DIR / "init_project.py")] + args
    env = dict(os.environ)
    env.update(env_extra or {})
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


class InitEncodingTests(unittest.TestCase):
    def test_init_survives_gbk_stdout(self):
        """Init must exit 0 and create all files even when stdout is GBK."""
        with tempfile.TemporaryDirectory() as tmp:
            rc, out, err = run_cli(
                ["proj", "--project-dir", tmp],
                env_extra={"PYTHONIOENCODING": "gbk"},
            )
            self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
            self.assertTrue((Path(tmp) / ".ghs" / "features.json").exists())
            self.assertTrue((Path(tmp) / ".ghs" / "progress.md").exists())


class EnsureGitignoreTests(unittest.TestCase):
    def test_directory_style_entry_not_duplicated(self):
        """An existing `.ghs/` rule must satisfy ensure_gitignore (no duplicate)."""
        with tempfile.TemporaryDirectory() as tmp:
            gitignore = Path(tmp) / ".gitignore"
            original = "# project rules\n.ghs/\n"
            gitignore.write_text(original, encoding="utf-8")
            rc, out, err = run_cli(
                ["proj", "--project-dir", tmp],
                env_extra={"PYTHONIOENCODING": "utf-8"},
            )
            self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
            self.assertEqual(
                gitignore.read_text(encoding="utf-8"),
                original,
                "ensure_gitignore must not append .ghs when .ghs/ is present",
            )


class PartialInitCleanupTests(unittest.TestCase):
    def test_failure_midway_removes_created_files(self):
        """If creation fails midway, files created during this run are removed."""
        with tempfile.TemporaryDirectory() as tmp:
            argv = ["init_project.py", "proj", "--project-dir", tmp]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                sys, "stdout", new=io.StringIO()
            ), mock.patch.object(
                init, "create_progress_md", side_effect=RuntimeError("boom")
            ):
                rc = init.main()
            self.assertEqual(rc, 1)
            self.assertFalse(
                (Path(tmp) / ".ghs" / "features.json").exists(),
                "features.json left behind after a failed init",
            )


class JsonLiteralEncodingTests(unittest.TestCase):
    def test_chinese_description_stored_as_literal_characters(self):
        """Non-ASCII description must be stored as characters, not \\uXXXX escapes."""
        with tempfile.TemporaryDirectory() as tmp:
            rc, out, err = run_cli(
                ["proj", "--description", "中文描述：自举测试", "--project-dir", tmp],
                env_extra={"PYTHONIOENCODING": "utf-8"},
            )
            self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
            text = (Path(tmp) / ".ghs" / "features.json").read_text(encoding="utf-8")
            self.assertIn("中文描述：自举测试", text)
            self.assertNotIn("\\u", text, "non-ASCII must not be escaped as \\uXXXX")


if __name__ == "__main__":
    unittest.main()
