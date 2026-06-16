#!/usr/bin/env python3
"""Unit tests for parse_completion_signal.py.

Covers the 15+ cases enumerated in plan §6.1 (single-line signal protocol):
exact / case-insensitive / extra-characters (negative) / Chinese / natural
language / thinking-tag wrapping / markdown bold wrapping / forgot-to-emit /
empty input / wrong feature_id / multi-feature coexistence.

Run directly:
    command python3 plugin/shared/scripts/test_parse_completion_signal.py

No pytest dependency. Uses only the standard unittest module.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

# Make parse_completion_signal importable as a sibling module.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import parse_completion_signal as helper  # noqa: E402

FEATURE_ID = "s3-feat-001"
OTHER_ID = "s3-feat-002"


def run_cli(args, stdin_text=None):
    """Run the helper as a subprocess and return (returncode, parsed_json, stderr)."""
    cmd = [sys.executable, str(SCRIPT_DIR / "parse_completion_signal.py")] + args
    proc = subprocess.run(
        cmd,
        input=stdin_text,
        capture_output=True,
        text=True,
    )
    parsed = None
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = None
    return proc.returncode, parsed, proc.stderr


def call(raw_text, feature_id=FEATURE_ID, min_length=50):
    """Convenience wrapper around helper.parse_signal."""
    return helper.parse_signal(
        raw_text, feature_id=feature_id, min_length=min_length
    )


class ParseSignalUnitTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # 1. exact_signal — completed
    # ------------------------------------------------------------------
    def test_01_exact_complete(self):
        raw = (
            "I implemented the helper and ran all tests.\n"
            f"FEATURE COMPLETE: {FEATURE_ID}\n"
        )
        result = call(raw)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["strategy"], "exact_signal")
        self.assertIsNone(result["reason"])
        self.assertEqual(result["feature_id"], FEATURE_ID)
        self.assertIn("FEATURE COMPLETE", result["raw_signal_line"])

    # ------------------------------------------------------------------
    # 2. exact_signal — blocked with reason
    # ------------------------------------------------------------------
    def test_02_exact_blocked_with_reason(self):
        raw = (
            "I tried but the linter fails on the new file.\n"
            f"FEATURE BLOCKED: {FEATURE_ID} - lint errors in foo.py\n"
        )
        result = call(raw)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["strategy"], "exact_signal")
        self.assertEqual(result["reason"], "lint errors in foo.py")
        self.assertIn("FEATURE BLOCKED", result["raw_signal_line"])

    # ------------------------------------------------------------------
    # 3. exact_signal — blocked without reason
    # ------------------------------------------------------------------
    def test_03_exact_blocked_no_reason(self):
        raw = (
            "I cannot complete this.\n"
            f"FEATURE BLOCKED: {FEATURE_ID}\n"
        )
        result = call(raw)
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["reason"])
        self.assertTrue(
            any("no reason" in w for w in result["warnings"]),
            f"expected 'no reason' warning, got {result['warnings']}",
        )

    # ------------------------------------------------------------------
    # 4. case_insensitive — lowercase
    # ------------------------------------------------------------------
    def test_04_case_insensitive_lowercase(self):
        raw = (
            "Done with the implementation.\n"
            f"feature complete: {FEATURE_ID}\n"
        )
        result = call(raw)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["strategy"], "case_insensitive")
        self.assertTrue(
            any("case-insensitive" in w for w in result["warnings"])
        )

    # ------------------------------------------------------------------
    # 5. case_insensitive — mixed case blocked
    # ------------------------------------------------------------------
    def test_05_case_insensitive_mixed_case_blocked(self):
        raw = (
            "Hit a wall.\n"
            f"Feature Blocked: {FEATURE_ID} - dependency missing\n"
        )
        result = call(raw)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["strategy"], "case_insensitive")
        self.assertEqual(result["reason"], "dependency missing")

    # ------------------------------------------------------------------
    # 6. Negative: extra 'D' (COMPLETED) — must not match
    # ------------------------------------------------------------------
    def test_06_extra_d_completed_is_unknown(self):
        raw = (
            "Some context for the response.\n"
            f"FEATURE COMPLETED: {FEATURE_ID}\n"
        )
        result = call(raw)
        # COMPLETED has an extra D; neither exact nor case-insensitive match.
        # Natural-language patterns also don't accept this exact phrase.
        self.assertEqual(result["status"], "unknown")

    # ------------------------------------------------------------------
    # 7. Negative: extra 'S' (COMPLETES) — must not match
    # ------------------------------------------------------------------
    def test_07_extra_s_completes_is_unknown(self):
        raw = (
            "Some context.\n"
            f"FEATURE COMPLETES: {FEATURE_ID}\n"
        )
        result = call(raw)
        self.assertEqual(result["status"], "unknown")

    # ------------------------------------------------------------------
    # 8. Chinese completion
    # ------------------------------------------------------------------
    def test_08_chinese_complete(self):
        raw = (
            "我已经完成了实现并通过测试。\n"
            f"特性完成: {FEATURE_ID}\n"
        )
        # Chinese chars are 1 char each in Python's len(); use a low
        # min-length so the strategy logic is what's tested, not the
        # threshold.
        result = call(raw, min_length=10)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["strategy"], "natural_language")
        self.assertTrue(
            any("natural language" in w for w in result["warnings"])
        )

    # ------------------------------------------------------------------
    # 9. Chinese blocked with reason
    # ------------------------------------------------------------------
    def test_09_chinese_blocked(self):
        raw = (
            "无法继续。\n"
            f"功能阻塞: {FEATURE_ID} 依赖缺失无法编译\n"
        )
        result = call(raw, min_length=10)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["strategy"], "natural_language")
        self.assertIsNotNone(result["reason"])
        self.assertIn("依赖", result["reason"])

    # ------------------------------------------------------------------
    # 10. Natural-language English — completed
    # ------------------------------------------------------------------
    def test_10_natural_language_complete(self):
        raw = (
            "All acceptance criteria are verified. "
            f"I have completed feature {FEATURE_ID} successfully.\n"
        )
        result = call(raw)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["strategy"], "natural_language")

    # ------------------------------------------------------------------
    # 11. Natural-language English — blocked with reason
    # ------------------------------------------------------------------
    def test_11_natural_language_blocked(self):
        raw = (
            "I cannot make progress. "
            f"Feature {FEATURE_ID} is blocked because lint errors remain.\n"
        )
        result = call(raw)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["strategy"], "natural_language")
        self.assertIsNotNone(result["reason"])
        self.assertIn("lint", result["reason"])

    # ------------------------------------------------------------------
    # 12. Signal inside <thinking> tag — still recognized
    # ------------------------------------------------------------------
    def test_12_signal_in_thinking_tag(self):
        # Per plan §6.1: thinking content is subagent reasoning visible to the
        # dispatcher as raw text, so the helper should detect the signal. The
        # signal is not at start of line so exact/case_insensitive can't match;
        # natural_language catches it via the "feature complete" alternative.
        raw = (
            f"<thinking>I'm done. FEATURE COMPLETE: {FEATURE_ID}</thinking>\n"
            "Let me write up the summary.\n"
        )
        result = call(raw)
        self.assertEqual(result["status"], "completed")
        # The signal is mid-line inside <thinking>, so exact/case_insensitive
        # (which anchor to line start) won't match. natural_language catches it.
        self.assertIn(
            result["strategy"],
            ("exact_signal", "case_insensitive", "natural_language"),
        )

    # ------------------------------------------------------------------
    # 13. Signal wrapped in markdown bold
    # ------------------------------------------------------------------
    def test_13_signal_in_markdown_bold(self):
        raw = (
            "Implementation finished.\n"
            f"**FEATURE COMPLETE: {FEATURE_ID}**\n"
        )
        result = call(raw)
        self.assertEqual(result["status"], "completed")
        self.assertIn(result["strategy"], ("exact_signal", "case_insensitive"))

    # ------------------------------------------------------------------
    # 14. Forgot to emit signal (just commit log)
    # ------------------------------------------------------------------
    def test_14_no_signal_forgot(self):
        raw = (
            "I committed the implementation. The diff includes the new file "
            "and the tests. All 32 unit tests pass.\n"
            # No FEATURE COMPLETE line at all.
        )
        result = call(raw)
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(
            len(result["warnings"]) > 0,
            "unknown result must record warnings",
        )

    # ------------------------------------------------------------------
    # 15. Empty input — below min-length
    # ------------------------------------------------------------------
    def test_15_empty_input_below_min_length(self):
        raw = "short"  # 5 chars < default 50
        result = call(raw, min_length=50)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["strategy"], "none")
        self.assertTrue(
            any("min-length" in w for w in result["warnings"])
        )

    # ------------------------------------------------------------------
    # 16. Wrong feature_id — must not match
    # ------------------------------------------------------------------
    def test_16_wrong_feature_id(self):
        raw = f"FEATURE COMPLETE: {OTHER_ID}\n" + "x" * 100
        result = call(raw, feature_id=FEATURE_ID)
        self.assertEqual(result["status"], "unknown")

    # ------------------------------------------------------------------
    # 17. Multi-feature coexistence — calling id1 sees only id1
    # ------------------------------------------------------------------
    def test_17_multi_feature_calling_first_id(self):
        raw = (
            f"FEATURE COMPLETE: {FEATURE_ID}\n"
            f"FEATURE BLOCKED: {OTHER_ID} - some reason\n"
        )
        result = call(raw, feature_id=FEATURE_ID)
        self.assertEqual(result["status"], "completed")
        self.assertNotIn(OTHER_ID, result.get("raw_signal_line", ""))

    # ------------------------------------------------------------------
    # 18. Multi-feature coexistence — calling id2 sees only id2
    # ------------------------------------------------------------------
    def test_18_multi_feature_calling_second_id(self):
        raw = (
            f"FEATURE COMPLETE: {FEATURE_ID}\n"
            f"FEATURE BLOCKED: {OTHER_ID} - some reason\n"
        )
        result = call(raw, feature_id=OTHER_ID)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "some reason")


class ParseSignalCliTests(unittest.TestCase):
    """End-to-end CLI tests covering exit codes and arg parsing."""

    def test_cli_exit_0_on_completed_via_stdin(self):
        rc, parsed, stderr = run_cli(
            ["--feature-id", FEATURE_ID, "--stdin"],
            stdin_text=(
                "I finished the work and committed.\n"
                f"FEATURE COMPLETE: {FEATURE_ID}\n"
            ),
        )
        self.assertEqual(rc, 0, f"stderr: {stderr}")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["status"], "completed")

    def test_cli_exit_1_on_unknown(self):
        rc, parsed, stderr = run_cli(
            ["--feature-id", FEATURE_ID, "--stdin"],
            stdin_text=(
                "Just a commit log without any signal line at all.\n"
            ),
        )
        self.assertEqual(rc, 1, f"stderr: {stderr}")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["status"], "unknown")

    def test_cli_exit_2_on_no_input(self):
        rc, parsed, stderr = run_cli(
            ["--feature-id", FEATURE_ID],
            stdin_text=None,
        )
        self.assertEqual(rc, 2)
        self.assertIn("error", stderr.lower())

    def test_cli_exit_2_on_missing_feature_id(self):
        # argparse exits with code 2 on missing required arg.
        rc, parsed, stderr = run_cli(
            ["--stdin"],
            stdin_text="anything",
        )
        self.assertEqual(rc, 2)

    def test_cli_input_file(self, tmp_path=None):
        # Use tempfile via subprocess for isolation.
        import tempfile
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False
        ) as f:
            f.write(
                "Implementation done.\n"
                f"FEATURE COMPLETE: {FEATURE_ID}\n"
            )
            path = f.name
        try:
            rc, parsed, stderr = run_cli(
                ["--feature-id", FEATURE_ID, "--input-file", path]
            )
            self.assertEqual(rc, 0, f"stderr: {stderr}")
            self.assertEqual(parsed["status"], "completed")
        finally:
            Path(path).unlink()

    def test_cli_input_string(self):
        rc, parsed, stderr = run_cli(
            [
                "--feature-id",
                FEATURE_ID,
                "--input-string",
                f"I cannot finish.\nFEATURE BLOCKED: {FEATURE_ID} - timeout",
            ]
        )
        self.assertEqual(rc, 0, f"stderr: {stderr}")
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["reason"], "timeout")

    def test_cli_min_length_default(self):
        # Default min-length is 50; a 10-char input must be unknown.
        rc, parsed, stderr = run_cli(
            ["--feature-id", FEATURE_ID, "--input-string", "short text"]
        )
        self.assertEqual(rc, 1, f"stderr: {stderr}")
        self.assertEqual(parsed["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
