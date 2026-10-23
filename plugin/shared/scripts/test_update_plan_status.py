#!/usr/bin/env python3
"""Unit tests for update_plan_status.py.

Pins the Windows-robust status mutation contract: strict read-modify-write
(unknown fields preserved), UTF-8 on disk, per-kind retry increments, enum /
type validation, and a single-line ASCII confirmation on stdout — even under
a legacy GBK console (PYTHONIOENCODING=gbk).

Run directly:
    command python3 plugin/shared/scripts/test_update_plan_status.py

No pytest dependency. Uses only the standard unittest module.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Make update_plan_status importable as a sibling module.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import update_plan_status as helper  # noqa: E402

FULL_STATUS = {
    "plan_file": "2026-10-19-demo.md",
    "context_file": "2026-10-19-demo-context.md",
    "status": "designing",
    "lane": "full",
    "retry_counts": {"plan": 0, "review": 0, "context_snapshot": 0},
    "reject_count": 0,
    "final_fix_pending": False,
    "accepted_with_fail": False,
    "keep_raw_on_success": False,
    "created_at": "2026-10-19T10:00:00",
    "updated_at": "2000-01-01T00:00:00",
}

TS_RE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"


def run_cli(args, env_extra=None):
    """Run update_plan_status.py as a subprocess.

    Returns (returncode, stdout, stderr). Output is always decoded as UTF-8
    (errors=replace) regardless of the parent console encoding.
    """
    cmd = [sys.executable, str(SCRIPT_DIR / "update_plan_status.py")] + args
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


class UpdatePlanStatusCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "status.json"

    def write_status(self, data):
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def read_status(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # status transitions preserve the rest of the file
    # ------------------------------------------------------------------
    def test_set_status_preserves_other_fields(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(["--file", str(self.path), "--set", "status=revising"])
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        data = self.read_status()
        self.assertEqual(data["status"], "revising")
        # Everything else survives the read-modify-write untouched.
        self.assertEqual(data["lane"], "full")
        self.assertEqual(
            data["retry_counts"], {"plan": 0, "review": 0, "context_snapshot": 0}
        )
        self.assertEqual(data["reject_count"], 0)
        self.assertFalse(data["final_fix_pending"])
        self.assertEqual(data["created_at"], "2026-10-19T10:00:00")

    # ------------------------------------------------------------------
    # per-kind retry increment
    # ------------------------------------------------------------------
    def test_bump_retry_increments_only_target_kind(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(["--file", str(self.path), "--bump-retry", "plan"])
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        data = self.read_status()
        self.assertEqual(data["retry_counts"]["plan"], 1)
        self.assertEqual(data["retry_counts"]["review"], 0)
        self.assertEqual(data["retry_counts"]["context_snapshot"], 0)

    def test_bump_retry_missing_key_starts_at_one(self):
        data = json.loads(json.dumps(FULL_STATUS))
        del data["retry_counts"]
        self.write_status(data)
        rc, out, err = run_cli(
            ["--file", str(self.path), "--bump-retry", "context_snapshot"]
        )
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        self.assertEqual(self.read_status()["retry_counts"]["context_snapshot"], 1)

    def test_set_retry_counts_direct_reset(self):
        data = json.loads(json.dumps(FULL_STATUS))
        data["retry_counts"]["plan"] = 1
        self.write_status(data)
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "retry_counts.plan=0"]
        )
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        self.assertEqual(self.read_status()["retry_counts"]["plan"], 0)

    # ------------------------------------------------------------------
    # boolean / int / string / lane fields
    # ------------------------------------------------------------------
    def test_boolean_fields(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(
            [
                "--file", str(self.path),
                "--set", "final_fix_pending=true",
                "--set", "accepted_with_fail=true",
                "--set", "keep_raw_on_success=true",
            ]
        )
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        data = self.read_status()
        self.assertIs(data["final_fix_pending"], True)
        self.assertIs(data["accepted_with_fail"], True)
        self.assertIs(data["keep_raw_on_success"], True)

    def test_reject_count_stored_as_int(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "reject_count=2"]
        )
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        self.assertEqual(self.read_status()["reject_count"], 2)

    def test_set_lane(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(["--file", str(self.path), "--set", "lane=light"])
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        self.assertEqual(self.read_status()["lane"], "light")

    def test_multiple_sets_single_call(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(
            [
                "--file", str(self.path),
                "--set", "status=pending_approval",
                "--set", "final_fix_pending=false",
            ]
        )
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        data = self.read_status()
        self.assertEqual(data["status"], "pending_approval")
        self.assertIs(data["final_fix_pending"], False)

    def test_set_context_file_string(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "context_file=2026-10-20-x-context.md"]
        )
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        self.assertEqual(
            self.read_status()["context_file"], "2026-10-20-x-context.md"
        )

    # ------------------------------------------------------------------
    # updated_at handling
    # ------------------------------------------------------------------
    def test_updated_at_auto_refreshed(self):
        self.write_status(FULL_STATUS)  # seeded with 2000-01-01T00:00:00
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "status=reviewing"]
        )
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        data = self.read_status()
        self.assertNotEqual(data["updated_at"], "2000-01-01T00:00:00")
        self.assertRegex(data["updated_at"], TS_RE)

    def test_explicit_updated_at_overrides_auto(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "updated_at=2001-02-03T04:05:06"]
        )
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        self.assertEqual(self.read_status()["updated_at"], "2001-02-03T04:05:06")

    # ------------------------------------------------------------------
    # read-modify-write, not rebuild
    # ------------------------------------------------------------------
    def test_unknown_fields_preserved(self):
        data = json.loads(json.dumps(FULL_STATUS))
        data["custom_extension"] = {"keep": "me"}
        self.write_status(data)
        rc, out, err = run_cli(["--file", str(self.path), "--set", "status=approved"])
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        self.assertEqual(self.read_status()["custom_extension"], {"keep": "me"})

    # ------------------------------------------------------------------
    # UTF-8 on disk
    # ------------------------------------------------------------------
    def test_utf8_roundtrip_chinese_values(self):
        data = json.loads(json.dumps(FULL_STATUS))
        data["plan_file"] = "2026-10-19-中文计划.md"
        self.write_status(data)
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "status=reviewing"]
        )
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        raw = self.path.read_text(encoding="utf-8")  # strict UTF-8 decode
        # Literal UTF-8 characters on disk, never \\u escapes.
        self.assertIn("中文计划", raw)
        self.assertNotIn("\\u", raw)
        self.assertEqual(self.read_status()["plan_file"], "2026-10-19-中文计划.md")

    # ------------------------------------------------------------------
    # validation errors leave the file untouched
    # ------------------------------------------------------------------
    def test_unknown_key_rejected(self):
        original = json.dumps(FULL_STATUS, ensure_ascii=False, indent=2)
        self.path.write_text(original, encoding="utf-8")
        rc, out, err = run_cli(["--file", str(self.path), "--set", "bogus=1"])
        self.assertEqual(rc, 2)
        self.assertIn("error", err.lower())
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_removed_status_enum_rejected(self):
        original = json.dumps(FULL_STATUS, ensure_ascii=False, indent=2)
        self.path.write_text(original, encoding="utf-8")
        rc, out, err = run_cli(["--file", str(self.path), "--set", "status=rejected"])
        self.assertEqual(rc, 2)
        self.assertIn("error", err.lower())
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_bad_bool_rejected(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "final_fix_pending=yes"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("error", err.lower())

    def test_bad_int_rejected(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "reject_count=many"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("error", err.lower())

    def test_bad_retry_kind_rejected(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "retry_counts.designer=1"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("error", err.lower())

    def test_missing_file_is_error(self):
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "status=reviewing"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("not found", err)

    def test_malformed_json_is_error(self):
        self.path.write_text("{not json", encoding="utf-8")
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "status=reviewing"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("error", err.lower())

    def test_non_object_json_is_error(self):
        self.path.write_text("[1, 2, 3]", encoding="utf-8")
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "status=reviewing"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("error", err.lower())

    def test_no_mutation_args_is_error(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(["--file", str(self.path)])
        self.assertEqual(rc, 2)
        self.assertIn("nothing to do", err.lower())

    # ------------------------------------------------------------------
    # output contract: single ASCII confirmation line
    # ------------------------------------------------------------------
    def test_stdout_is_single_ascii_line(self):
        self.write_status(FULL_STATUS)
        rc, out, err = run_cli(
            [
                "--file", str(self.path),
                "--set", "status=pending_approval",
                "--bump-retry", "review",
            ]
        )
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        self.assertEqual(out.strip().count("\n"), 0)
        self.assertTrue(out.strip().isascii(), f"stdout must be ASCII: {out!r}")
        self.assertIn("OK", out)
        self.assertIn("status", out)
        self.assertIn("retry_counts.review", out)
        self.assertIn("updated_at", out)

    def test_gbk_stdout_no_crash(self):
        """GBK stdout (PYTHONIOENCODING=gbk) + Chinese field values → no crash.

        The confirmation line lists keys only, so it is pure ASCII and safe on
        any console codepage; the payload goes to disk as UTF-8.
        """
        data = json.loads(json.dumps(FULL_STATUS))
        data["plan_file"] = "2026-10-19-中文计划.md"
        self.write_status(data)
        rc, out, err = run_cli(
            ["--file", str(self.path), "--set", "status=reviewing"],
            env_extra={"PYTHONIOENCODING": "gbk"},
        )
        self.assertEqual(rc, 0, f"stdout={out!r}\nstderr={err!r}")
        self.assertNotIn(
            "UnicodeEncodeError", err, "child must not crash on GBK stdout"
        )
        self.assertIn("OK", out)


class ParseSetItemUnitTests(unittest.TestCase):
    def test_status_enum_parses(self):
        self.assertEqual(
            helper.parse_set_item("status=aborted"), ("status", "aborted")
        )

    def test_bool_parses_case_insensitive(self):
        self.assertEqual(
            helper.parse_set_item("keep_raw_on_success=True"),
            ("keep_raw_on_success", True),
        )

    def test_reject_count_parses_int(self):
        self.assertEqual(helper.parse_set_item("reject_count=3"), ("reject_count", 3))

    def test_retry_counts_dotted_path_parses(self):
        self.assertEqual(
            helper.parse_set_item("retry_counts.review=0"), ("retry_counts.review", 0)
        )

    def test_negative_int_rejected(self):
        with self.assertRaises(ValueError):
            helper.parse_set_item("reject_count=-1")

    def test_missing_equals_rejected(self):
        with self.assertRaises(ValueError):
            helper.parse_set_item("status")

    def test_unknown_key_rejected(self):
        with self.assertRaises(ValueError):
            helper.parse_set_item("statuss=approved")


if __name__ == "__main__":
    unittest.main()
