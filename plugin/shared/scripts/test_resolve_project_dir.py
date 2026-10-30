#!/usr/bin/env python3
"""Tests for resolve_project_dir.py.

Pins the Windows console fix: on a legacy GBK stdout (PYTHONIOENCODING=gbk)
the resolved project directory - which may contain non-ASCII characters -
must still be emitted as UTF-8 without UnicodeEncodeError or mojibake.
Also covers the marker-file walk-up logic end-to-end.

Run directly:
    command python3 plugin/shared/scripts/test_resolve_project_dir.py

No pytest dependency. Uses only the standard unittest module.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))


def run_cli(args, cwd=None, env_extra=None):
    """Run resolve_project_dir.py as a subprocess.

    Returns (returncode, stdout, stderr). Output is always decoded as UTF-8
    (errors=replace) regardless of the parent console encoding, so UTF-8
    fidelity of the child output can be asserted.
    """
    cmd = [sys.executable, str(SCRIPT_DIR / "resolve_project_dir.py")] + args
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def make_project(root, marker="features.json"):
    """Create a `.ghs/` project tree under root and return its Path."""
    ghs = Path(root) / ".ghs"
    ghs.mkdir(parents=True)
    payload = "{}" if marker == "features.json" else "# log\n"
    (ghs / marker).write_text(payload, encoding="utf-8")
    return Path(root)


class ResolveProjectDirTests(unittest.TestCase):
    def test_finds_project_dir_from_nested_start(self):
        """Nested start dir inside a .ghs project → prints the project root."""
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            nested = Path(tmp) / "a" / "b"
            nested.mkdir(parents=True)
            rc, out, err = run_cli(["--start-dir", str(nested)])
            self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
            self.assertEqual(
                os.path.normcase(out.strip()),
                os.path.normcase(str(project.resolve())),
            )

    def test_walks_up_without_start_dir_via_cwd(self):
        """No --start-dir → falls back to the subprocess cwd."""
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp)
            nested = Path(tmp) / "x"
            nested.mkdir()
            rc, out, err = run_cli([], cwd=nested)
            self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
            self.assertEqual(
                os.path.normcase(out.strip()),
                os.path.normcase(str(project.resolve())),
            )

    def test_progress_md_marker_alone_is_enough(self):
        """A .ghs containing only progress.md still resolves."""
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(tmp, marker="progress.md")
            rc, out, err = run_cli(["--start-dir", tmp])
            self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
            self.assertEqual(
                os.path.normcase(out.strip()),
                os.path.normcase(str(project.resolve())),
            )

    def test_no_project_dir_exits_1(self):
        """No .ghs markers anywhere up the tree → exit 1 with a hint."""
        with tempfile.TemporaryDirectory() as tmp:
            rc, out, err = run_cli(["--start-dir", tmp])
            self.assertEqual(rc, 1, f"stdout={out!r}\nstderr={err!r}")
            self.assertIn("No project directory found", err)
            self.assertEqual(out.strip(), "")

    def test_gbk_stdout_outputs_utf8_without_error(self):
        """GBK stdout + non-ASCII project path → UTF-8 output, no crash.

        With PYTHONIOENCODING=gbk a script without force_utf8_stdio() would
        either raise UnicodeEncodeError or emit GBK bytes; both break this
        test (the UTF-8 decode in run_cli would yield mojibake instead of
        the literal Chinese directory name).
        """
        with tempfile.TemporaryDirectory() as tmp:
            inner = Path(tmp) / "中文项目目录"
            inner.mkdir()
            project = make_project(inner)
            nested = project / "sub"
            nested.mkdir()
            rc, out, err = run_cli(
                ["--start-dir", str(nested)],
                env_extra={"PYTHONIOENCODING": "gbk"},
            )
            self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
            self.assertNotIn(
                "UnicodeEncodeError", err, "child must not crash on GBK stdout"
            )
            # UTF-8 fidelity: the Chinese path segment survives the round trip.
            self.assertIn("中文项目目录", out)
            self.assertEqual(
                os.path.normcase(out.strip()),
                os.path.normcase(str(project.resolve())),
            )


if __name__ == "__main__":
    unittest.main()
