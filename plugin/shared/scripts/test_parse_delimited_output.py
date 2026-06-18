#!/usr/bin/env python3
"""Unit tests for parse_delimited_output.py.

Covers the 17 cases enumerated in plan §3.2 Q6, including the 5 added during
Round 2 review (multi_kind_pairs, nested_code_fence, additional_files_read,
review_with_verdict_pass, review_with_verdict_fail).

Run directly:
    command python3 plugin/shared/scripts/test_parse_delimited_output.py

No pytest dependency. Uses only the standard unittest module.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Make parse_delimited_output importable as a sibling module.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import parse_delimited_output as helper  # noqa: E402

# Long enough body to clear the default 200-char min length.
LONG_BODY = (
    "# Plan Title\n\n"
    "## Background\n"
    "This section explains why we are doing this work and what motivates it.\n\n"
    "## Goals\n"
    "Goal one is to ship the helper. Goal two is to make it deterministic.\n\n"
    "## Architecture\n"
    "We expose a single Python entry point that takes raw text and emits JSON.\n"
    "Strategies are tried in priority order and the first one that yields enough\n"
    "content wins.\n"
)
assert len(LONG_BODY) >= 200, f"LONG_BODY too short: {len(LONG_BODY)}"


def run_cli(args, stdin_text=None):
    """Run the helper as a subprocess and return (returncode, parsed_json_or_None, stderr)."""
    cmd = [sys.executable, str(SCRIPT_DIR / "parse_delimited_output.py")] + args
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


class ParseHelperUnitTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # 1. exact_delimiter success — plan kind
    # ------------------------------------------------------------------
    def test_01_exact_match_plan(self):
        raw = f"<<<PLAN_START>>>\n{LONG_BODY}\n<<<PLAN_END>>>\nPLAN DESIGN COMPLETE\n"
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal="PLAN DESIGN COMPLETE",
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["strategy"], "exact_delimiter")
        self.assertEqual(result["completion_signal"], "PLAN DESIGN COMPLETE")
        self.assertIsNone(result["verdict"])
        self.assertIn("# Plan Title", result["content"])

    # ------------------------------------------------------------------
    # 2. exact_delimiter success — review kind
    # ------------------------------------------------------------------
    def test_02_exact_match_review(self):
        raw = f"<<<REVIEW_START>>>\n{LONG_BODY}\n<<<REVIEW_END>>>\n"
        result = helper.parse_raw(
            raw,
            kind="review",
            start_token="<<<REVIEW_START>>>",
            end_token="<<<REVIEW_END>>>",
            min_length=150,
            completion_signal="REVIEW COMPLETE",
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["strategy"], "exact_delimiter")

    # ------------------------------------------------------------------
    # 3. exact_delimiter success — context_snapshot kind
    # ------------------------------------------------------------------
    def test_03_exact_match_context_snapshot(self):
        body = (
            "## Repo Layout\n"
            "- src/ contains the core helpers\n"
            "- tests/ covers them\n"
            "- docs/ holds the architecture notes\n"
            "- entry point is run.sh in the project root\n"
        )
        raw = f"<<<CONTEXT_SNAPSHOT_START>>>\n{body}\n<<<CONTEXT_SNAPSHOT_END>>>\n"
        result = helper.parse_raw(
            raw,
            kind="context_snapshot",
            start_token="<<<CONTEXT_SNAPSHOT_START>>>",
            end_token="<<<CONTEXT_SNAPSHOT_END>>>",
            min_length=100,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["strategy"], "exact_delimiter")
        self.assertIn("Repo Layout", result["content"])

    # ------------------------------------------------------------------
    # 4. normalized_delimiter — Chinese variant 《《PLAN_START》》
    # ------------------------------------------------------------------
    def test_04_normalized_chinese_quotes(self):
        raw = f"《《PLAN_START》》\n{LONG_BODY}\n《《PLAN_END》》\n"
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "fallback_used")
        self.assertEqual(result["strategy"], "normalized_delimiter")

    # ------------------------------------------------------------------
    # 5. normalized_delimiter — extra spaces <<< PLAN_START >>>
    # ------------------------------------------------------------------
    def test_05_normalized_extra_whitespace(self):
        raw = f"<<< PLAN_START >>>\n{LONG_BODY}\n<<< PLAN_END >>>\n"
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "fallback_used")
        self.assertEqual(result["strategy"], "normalized_delimiter")

    # ------------------------------------------------------------------
    # 6. normalized_delimiter — fewer brackets <<PLAN_START>>
    # ------------------------------------------------------------------
    def test_06_normalized_fewer_brackets(self):
        raw = f"<<PLAN_START>>\n{LONG_BODY}\n<<PLAN_END>>\n"
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "fallback_used")
        self.assertEqual(result["strategy"], "normalized_delimiter")

    # ------------------------------------------------------------------
    # 7. code_fence — bare code-fence wrap, exact_delimiter inside
    # ------------------------------------------------------------------
    def test_07_code_fence_wrapped_exact_inside(self):
        raw = f"```\n<<<PLAN_START>>>\n{LONG_BODY}\n<<<PLAN_END>>>\n```\n"
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal=None,
        )
        # STRATEGY 1 should still win on the outer text since the literal
        # delimiters are present in the raw text.
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["strategy"], "exact_delimiter")

    # ------------------------------------------------------------------
    # 8. code_fence — pure fence, no delimiters
    # ------------------------------------------------------------------
    def test_08_pure_code_fence(self):
        raw = f"```\n{LONG_BODY}\n```\n"
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "fallback_used")
        self.assertEqual(result["strategy"], "code_fence")

    # ------------------------------------------------------------------
    # 9. nested code fence — exact_delimiter still wins
    # ------------------------------------------------------------------
    def test_09_nested_code_fence_exact_still_wins(self):
        # A nested python fence mentions the delimiter as a string literal,
        # while a real delimiter pair follows. STRATEGY 1 must pick the real
        # pair, not get confused by the literal.
        raw = (
            "```python\n"
            'TOKENS = {"start": "<<<PLAN_START>>>", "end": "<<<PLAN_END>>>"}\n'
            "```\n\n"
            f"<<<PLAN_START>>>\n{LONG_BODY}\n<<<PLAN_END>>>\n"
        )
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["strategy"], "exact_delimiter")
        self.assertIn("# Plan Title", result["content"])

    # ------------------------------------------------------------------
    # 10. whole_body — pure markdown fallback
    # ------------------------------------------------------------------
    def test_10_pure_markdown_whole_body(self):
        raw = LONG_BODY
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "fallback_used")
        self.assertEqual(result["strategy"], "whole_body")
        self.assertIn("# Plan Title", result["content"])

    # ------------------------------------------------------------------
    # 11. whole_body — legacy <thinking>...</thinking>
    # ------------------------------------------------------------------
    def test_11_legacy_thinking_tag(self):
        raw = f"<thinking>internal reasoning here</thinking>\n{LONG_BODY}\n"
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "fallback_used")
        self.assertEqual(result["strategy"], "whole_body")
        self.assertNotIn("internal reasoning here", result["content"])
        self.assertNotIn("<thinking>", result["content"])

    # ------------------------------------------------------------------
    # 12. whole_body — antml thinking tag
    # ------------------------------------------------------------------
    def test_12_antml_thinking_tag(self):
        raw = (
            "<antml:thinking>anthropic-internal chain of thought</antml:thinking>\n"
            f"{LONG_BODY}\n"
        )
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "fallback_used")
        self.assertEqual(result["strategy"], "whole_body")
        self.assertNotIn("anthropic-internal chain of thought", result["content"])
        self.assertNotIn("<antml:thinking>", result["content"])

    # ------------------------------------------------------------------
    # 13. malformed — only thinking tags, no real content
    # ------------------------------------------------------------------
    def test_13_thinking_only_is_malformed(self):
        raw = (
            "<thinking>I am just thinking out loud and not producing any "
            "deliverable content for the dispatcher.</thinking>\n"
        )
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "malformed")
        self.assertEqual(result["strategy"], "none")

    # ------------------------------------------------------------------
    # 14. malformed — only completion signal
    # ------------------------------------------------------------------
    def test_14_completion_signal_only_is_malformed(self):
        raw = "PLAN DESIGN COMPLETE\n"
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal="PLAN DESIGN COMPLETE",
        )
        self.assertEqual(result["status"], "malformed")
        self.assertEqual(result["strategy"], "none")
        self.assertEqual(result["completion_signal"], "PLAN DESIGN COMPLETE")

    # ------------------------------------------------------------------
    # 15. empty — delimiters present but content too short
    # ------------------------------------------------------------------
    def test_15_too_short_between_is_empty(self):
        raw = "<<<PLAN_START>>>\nhi\n<<<PLAN_END>>>\n"
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["strategy"], "none")

    # ------------------------------------------------------------------
    # 16. multi_kind_pairs — review kind picks only REVIEW pair
    # ------------------------------------------------------------------
    def test_16_multi_kind_pairs_review(self):
        raw = (
            f"<<<PLAN_START>>>\n{LONG_BODY}\n<<<PLAN_END>>>\n\n"
            f"<<<REVIEW_START>>>\n{LONG_BODY}\n<<<REVIEW_END>>>\n"
            "REVIEW COMPLETE | Verdict: PASS | Severe: 0 Medium: 0 Optimization: 1\n"
        )
        result = helper.parse_raw(
            raw,
            kind="review",
            start_token="<<<REVIEW_START>>>",
            end_token="<<<REVIEW_END>>>",
            min_length=150,
            completion_signal="REVIEW COMPLETE",
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["strategy"], "exact_delimiter")
        self.assertEqual(result["verdict"], "PASS")
        # PLAN delimiters must not appear in the extracted REVIEW content.
        self.assertNotIn("PLAN_START", result["content"])

    # ------------------------------------------------------------------
    # 17. additional_files_read — trailing marker is stripped
    # ------------------------------------------------------------------
    def test_17_additional_files_read_stripped(self):
        raw = (
            f"<<<PLAN_START>>>\n{LONG_BODY}\n<<<PLAN_END>>>\n"
            "PLAN DESIGN COMPLETE\n"
            "ADDITIONAL FILES READ: a.py, b.py, c.py\n"
        )
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal="PLAN DESIGN COMPLETE",
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["strategy"], "exact_delimiter")
        self.assertNotIn("ADDITIONAL FILES READ", result["content"])
        self.assertNotIn("a.py", result["content"])


class ParseHelperVerdictTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # review_with_verdict_pass
    # ------------------------------------------------------------------
    def test_review_with_verdict_pass(self):
        raw = (
            f"<<<REVIEW_START>>>\n{LONG_BODY}\n<<<REVIEW_END>>>\n"
            "REVIEW COMPLETE | Verdict: PASS | Severe: 0 Medium: 0 Optimization: 1\n"
        )
        result = helper.parse_raw(
            raw,
            kind="review",
            start_token="<<<REVIEW_START>>>",
            end_token="<<<REVIEW_END>>>",
            min_length=150,
            completion_signal="REVIEW COMPLETE",
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(
            result["completion_signal"],
            "REVIEW COMPLETE | Verdict: PASS | Severe: 0 Medium: 0 Optimization: 1",
        )

    # ------------------------------------------------------------------
    # review_with_verdict_fail
    # ------------------------------------------------------------------
    def test_review_with_verdict_fail(self):
        raw = (
            f"<<<REVIEW_START>>>\n{LONG_BODY}\n<<<REVIEW_END>>>\n"
            "REVIEW COMPLETE | Verdict: FAIL | Severe: 2 Medium: 1 Optimization: 0\n"
        )
        result = helper.parse_raw(
            raw,
            kind="review",
            start_token="<<<REVIEW_START>>>",
            end_token="<<<REVIEW_END>>>",
            min_length=150,
            completion_signal="REVIEW COMPLETE",
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["verdict"], "FAIL")

    # ------------------------------------------------------------------
    # review_verdict_missing — verdict field is null when absent
    # ------------------------------------------------------------------
    def test_review_verdict_missing(self):
        raw = (
            f"<<<REVIEW_START>>>\n{LONG_BODY}\n<<<REVIEW_END>>>\n"
            "REVIEW COMPLETE\n"
        )
        result = helper.parse_raw(
            raw,
            kind="review",
            start_token="<<<REVIEW_START>>>",
            end_token="<<<REVIEW_END>>>",
            min_length=150,
            completion_signal="REVIEW COMPLETE",
        )
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["verdict"])


class ParseHelperCompletionSignalTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # completion_signal — leading whitespace tolerated
    # ------------------------------------------------------------------
    def test_completion_signal_leading_whitespace(self):
        raw = (
            f"<<<PLAN_START>>>\n{LONG_BODY}\n<<<PLAN_END>>>\n"
            "    PLAN DESIGN COMPLETE\n"
        )
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal="PLAN DESIGN COMPLETE",
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["completion_signal"], "PLAN DESIGN COMPLETE")

    # ------------------------------------------------------------------
    # completion_signal — line with trailing content still matches
    # ------------------------------------------------------------------
    def test_completion_signal_with_trailing_content(self):
        raw = (
            f"<<<PLAN_START>>>\n{LONG_BODY}\n<<<PLAN_END>>>\n"
            "REVIEW COMPLETE | Verdict: FAIL | Severe: 1 Medium: 2 Optimization: 3\n"
        )
        result = helper.parse_raw(
            raw,
            kind="review",
            start_token="<<<REVIEW_START>>>",
            end_token="<<<REVIEW_END>>>",
            min_length=150,
            completion_signal="REVIEW COMPLETE",
        )
        # No REVIEW delimiters present — whole_body or code_fence fallback may
        # fire. We only care that the completion_signal was captured with
        # trailing content preserved.
        self.assertIsNotNone(result["completion_signal"])
        self.assertIn("Verdict: FAIL", result["completion_signal"])


class ParseHelperGenericKindTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # generic mode with explicit start/end tokens
    # ------------------------------------------------------------------
    def test_generic_kind_explicit_tokens(self):
        raw = f"<BEGIN>\n{LONG_BODY}\n<END>\n"
        result = helper.parse_raw(
            raw,
            kind="generic",
            start_token="<BEGIN>",
            end_token="<END>",
            min_length=200,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["strategy"], "exact_delimiter")
        self.assertIn("# Plan Title", result["content"])


class ParseHelperInputSourceTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # --input-string
    # ------------------------------------------------------------------
    def test_input_string_via_cli(self):
        raw = f"<<<PLAN_START>>>\n{LONG_BODY}\n<<<PLAN_END>>>\n"
        rc, parsed, _ = run_cli(
            [
                "--kind", "plan",
                "--input-string", raw,
                "--min-length", "200",
                "--completion-signal", "PLAN DESIGN COMPLETE",
            ]
        )
        self.assertEqual(rc, 0)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["status"], "ok")
        self.assertEqual(parsed["strategy"], "exact_delimiter")

    # ------------------------------------------------------------------
    # --input-file
    # ------------------------------------------------------------------
    def test_input_file_via_cli(self):
        raw = f"<<<PLAN_START>>>\n{LONG_BODY}\n<<<PLAN_END>>>\n"
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        try:
            rc, parsed, _ = run_cli(
                [
                    "--kind", "plan",
                    "--input-file", tmp_path,
                    "--min-length", "200",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed["status"], "ok")
        finally:
            os.unlink(tmp_path)

    # ------------------------------------------------------------------
    # --stdin
    # ------------------------------------------------------------------
    def test_stdin_via_cli(self):
        raw = f"<<<PLAN_START>>>\n{LONG_BODY}\n<<<PLAN_END>>>\n"
        rc, parsed, _ = run_cli(
            [
                "--kind", "plan",
                "--stdin",
                "--min-length", "200",
            ],
            stdin_text=raw,
        )
        self.assertEqual(rc, 0)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["status"], "ok")


class ParseHelperMinLengthBoundaryTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # min-length boundary — content slightly below MIN_LEN triggers empty
    # ------------------------------------------------------------------
    def test_min_length_boundary_triggers_empty(self):
        # Build a body just under the threshold.
        short_body = "Short plan body that is only one paragraph and well under min.\n"
        self.assertLess(len(short_body), 200)
        raw = f"<<<PLAN_START>>>\n{short_body}\n<<<PLAN_END>>>\n"
        result = helper.parse_raw(
            raw,
            kind="plan",
            start_token="<<<PLAN_START>>>",
            end_token="<<<PLAN_END>>>",
            min_length=200,
            completion_signal=None,
        )
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["strategy"], "none")


class ParseHelperExitCodeTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # exit code 0 on ok / fallback_used
    # ------------------------------------------------------------------
    def test_exit_code_zero_on_ok(self):
        raw = f"<<<PLAN_START>>>\n{LONG_BODY}\n<<<PLAN_END>>>\n"
        rc, parsed, _ = run_cli(
            ["--kind", "plan", "--input-string", raw, "--min-length", "200"]
        )
        self.assertEqual(rc, 0)

    def test_exit_code_zero_on_fallback_used(self):
        raw = f"```\n{LONG_BODY}\n```\n"
        rc, parsed, _ = run_cli(
            ["--kind", "plan", "--input-string", raw, "--min-length", "200"]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(parsed["status"], "fallback_used")

    # ------------------------------------------------------------------
    # exit code 1 on empty / malformed
    # ------------------------------------------------------------------
    def test_exit_code_one_on_malformed(self):
        raw = "<thinking>only thinking</thinking>\n"
        rc, parsed, _ = run_cli(
            ["--kind", "plan", "--input-string", raw, "--min-length", "200"]
        )
        self.assertEqual(rc, 1)
        self.assertEqual(parsed["status"], "malformed")

    # ------------------------------------------------------------------
    # exit code 2 on argument error (no input source)
    # ------------------------------------------------------------------
    def test_exit_code_two_on_no_input(self):
        rc, _, stderr = run_cli(["--kind", "plan"])
        self.assertEqual(rc, 2)
        self.assertIn("error", stderr.lower())

    # ------------------------------------------------------------------
    # exit code 2 when --kind generic without explicit tokens
    # ------------------------------------------------------------------
    def test_exit_code_two_generic_without_tokens(self):
        rc, _, stderr = run_cli(
            ["--kind", "generic", "--input-string", "hello"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("error", stderr.lower())


if __name__ == "__main__":
    unittest.main()
