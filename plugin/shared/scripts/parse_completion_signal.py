#!/usr/bin/env python3
"""Parse completion signal from background subagent output.

Reads raw text emitted by a background subagent (e.g. ghs:code Parallel Mode
implementation agent) and determines whether the subagent reported success or
failure via the single-line signal protocol:

    FEATURE COMPLETE: <feature_id>
    FEATURE BLOCKED: <feature_id> - <reason>

Subagents occasionally deviate from the protocol (mixed case, Chinese variants,
natural-language phrasing, forgetting to emit the signal, wrapping it in
markdown bold). This helper applies four strategies in priority order so the
dispatcher never has to re-grep the text itself.

Usage:
    command python3 parse_completion_signal.py --feature-id s1-feat-002 --stdin < raw.txt
    command python3 parse_completion_signal.py --feature-id s1-feat-002 \\
        --input-file path/to/raw.txt --min-length 50
    command python3 parse_completion_signal.py --feature-id s1-feat-002 \\
        --input-string "FEATURE COMPLETE: s1-feat-002"

Output: a single JSON object on stdout with the following shape:
    {
      "status": "completed" | "blocked" | "unknown",
      "feature_id": "<id>",
      "reason": "<reason text, or null>",     # non-null only for blocked
      "strategy": "exact_signal" | "case_insensitive"
                | "natural_language" | "none",
      "raw_signal_line": "<stripped signal line, or null>",
      "warnings": ["...", "..."],
      "meta": {
        "feature_id": "s1-feat-002",
        "input_length": 1234
      }
    }

Exit codes:
    0 - signal detected (status == completed or blocked)
    1 - signal not detected (status == unknown)
    2 - invalid arguments / IO error
"""

import argparse
import json
import re
import sys
from pathlib import Path


# Default minimum raw-input length. The completion-signal protocol itself is a
# single line, but a near-empty response (no commit log, no description) is
# treated as unknown rather than risk a false-positive natural-language match.
DEFAULT_MIN_LENGTH = 50

# Maximum characters of trailing context to scan when extracting a reason from
# natural-language blocked signals (e.g. "Feature X is blocked because lint
# fails and tests don't compile"). Keeps the reason field bounded.
NATURAL_LANGUAGE_REASON_WINDOW = 200

# Markdown emphasis markers we strip from candidate signal lines so that
# `**FEATURE COMPLETE: <id>**` matches the same way as the bare line.
_EMPHASIS_CHARS = "*_`"


def _strip_emphasis(line: str) -> str:
    """Strip leading/trailing markdown emphasis characters from a line.

    Lets `**FEATURE COMPLETE: <id>**` and `_FEATURE COMPLETE: <id>_` match the
    same regexes as the bare signal line.
    """
    return line.strip().strip(_EMPHASIS_CHARS).strip()


def _extract_reason_from_signal_line(line: str, feature_id: str) -> "str | None":
    """Extract the `- <reason>` tail from a blocked-signal line.

    Works on both exact and case-insensitive matches. Returns None if no
    ` - ` separator is present (treated as blocked without a reason).
    """
    # Drop everything up to and including the feature_id, then look for the
    # ` - ` (or ` — ` / ` -- `) separator that introduces the reason.
    after_id = line.split(feature_id, 1)
    if len(after_id) < 2:
        return None
    tail = after_id[1].strip()
    if not tail:
        return None
    # Accept dash variants: ASCII hyphen, en/em dash, double-hyphen.
    m = re.match(r"(?:--|—|–|-)\s*(.+)$", tail)
    if not m:
        return None
    return m.group(1).strip() or None


def _strategy_exact(
    text: str, feature_id: str
) -> "tuple[str | None, str | None, str | None, list[str]]":
    """STRATEGY 1: literal `FEATURE (COMPLETE|BLOCKED): <id>` on its own line.

    Returns (status, reason, raw_signal_line, warnings). status is None when
    no match is found.
    """
    warnings: "list[str]" = []
    pattern = re.compile(
        r"^FEATURE\s+(COMPLETE|BLOCKED):\s*" + re.escape(feature_id) + r"\b.*$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return None, None, None, warnings
    outcome = match.group(1).upper()  # "COMPLETE" or "BLOCKED"
    raw_line = match.group(0).strip()
    if outcome == "COMPLETE":
        return "completed", None, raw_line, warnings
    reason = _extract_reason_from_signal_line(raw_line, feature_id)
    if reason is None:
        warnings.append("blocked signal has no reason text")
    return "blocked", reason, raw_line, warnings


def _strategy_case_insensitive(
    text: str, feature_id: str
) -> "tuple[str | None, str | None, str | None, list[str]]":
    """STRATEGY 2: tolerate case variation in FEATURE/COMPLETE/BLOCKED.

    Matches `Feature Complete`, `feature complete`, etc. Requires the
    feature_id to still match exactly (it's a key, not prose).
    """
    warnings: "list[str]" = []
    pattern = re.compile(
        r"^feature\s+(complete|blocked):\s*" + re.escape(feature_id) + r"\b.*$",
        re.MULTILINE | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None, None, None, warnings
    outcome = match.group(1).upper()
    raw_line = match.group(0).strip()
    warnings.append("case-insensitive match")
    if outcome == "COMPLETE":
        return "completed", None, raw_line, warnings
    reason = _extract_reason_from_signal_line(raw_line, feature_id)
    if reason is None:
        warnings.append("blocked signal has no reason text")
    return "blocked", reason, raw_line, warnings


# Natural-language patterns. Each entry: (compiled_regex, outcome, reason_group)
# where reason_group is the capture group index holding the reason text (None
# for completed matches, an int for blocked matches).
_NATURAL_LANGUAGE_PATTERNS = [
    # English completion phrasings.
    (
        re.compile(
            r"(?:i\s+(?:have\s+|'ve\s+)?(?:finished|completed|done)|"
            r"(?:feature|task)\s+(?:is\s+)?(?:done|complete|finished))\s*[:\.]?\s*"
            + r"(?:feature\s+)?(?P<id>{id})\b".format(id=r"PLACEHOLDER"),
            re.IGNORECASE,
        ),
        "completed",
        None,
    ),
    (
        re.compile(
            r"(?P<id>{id})\s+is\s+(?:done|complete|finished)\b".format(
                id=r"PLACEHOLDER"
            ),
            re.IGNORECASE,
        ),
        "completed",
        None,
    ),
    # English blocked phrasings.
    (
        re.compile(
            r"(?P<id>{id})\s+is\s+blocked\s+(?:because\s+)?(?P<reason>.+)$".format(
                id=r"PLACEHOLDER"
            ),
            re.IGNORECASE | re.MULTILINE,
        ),
        "blocked",
        "reason",
    ),
    (
        re.compile(
            r"(?:i\s+(?:have\s+)?(?:blocked|halted|stopped\s+at))\s+(?:feature\s+)?"
            r"(?P<id>{id})\s*(?P<reason>.+)$".format(id=r"PLACEHOLDER"),
            re.IGNORECASE | re.MULTILINE,
        ),
        "blocked",
        "reason",
    ),
    # Chinese completion phrasings.
    (
        re.compile(
            r"(?:特性|功能|任务)\s*完成\s*[:：]\s*(?P<id>{id})\b".format(
                id=r"PLACEHOLDER"
            )
        ),
        "completed",
        None,
    ),
    # Chinese blocked phrasings.
    (
        re.compile(
            r"(?:特性|功能|任务)\s*(?:阻塞|卡住|未完成|失败)\s*[:：]\s*(?P<id>{id})"
            r"\s*(?:[-—–\-：:])?\s*(?P<reason>.+)$"
            .format(id=r"PLACEHOLDER")
        ),
        "blocked",
        "reason",
    ),
]


def _strategy_natural_language(
    text: str, feature_id: str
) -> "tuple[str | None, str | None, str | None, list[str]]":
    """STRATEGY 3: permissive natural-language phrasings.

    Lower accuracy than the strict strategies. Used only as a fallback so a
    subagent that forgot the protocol but clearly stated its outcome still
    resolves. Always records a warning naming the matched pattern.
    """
    warnings: "list[str]" = []
    escaped_id = re.escape(feature_id)
    for idx, (template, outcome, reason_group) in enumerate(
        _NATURAL_LANGUAGE_PATTERNS, start=1
    ):
        # Each template was compiled with a literal PLACEHOLDER where the
        # feature_id regex should go. Re-compile per call with the real id.
        pattern_src = template.pattern.replace("PLACEHOLDER", escaped_id)
        flags = template.flags
        try:
            pattern = re.compile(pattern_src, flags)
        except re.error:
            continue
        match = pattern.search(text)
        if not match:
            continue
        raw_line = match.group(0).strip()
        # Truncate the captured raw line so an over-eager natural-language
        # pattern doesn't dump the entire rest of the response into JSON.
        if len(raw_line) > NATURAL_LANGUAGE_REASON_WINDOW:
            raw_line = raw_line[:NATURAL_LANGUAGE_REASON_WINDOW] + "..."
        warnings.append(f"natural language fallback: pattern #{idx}")
        if outcome == "completed":
            return "completed", None, raw_line, warnings
        # outcome == "blocked"
        reason = (
            match.group(reason_group).strip()
            if reason_group and reason_group in match.groupdict()
            else None
        )
        if not reason:
            warnings.append("natural-language blocked signal has no reason text")
            reason = None
        return "blocked", reason, raw_line, warnings
    return None, None, None, warnings


def parse_signal(raw_text: str, *, feature_id: str, min_length: int) -> dict:
    """Parse raw_text and return the JSON-serializable result dict."""
    warnings: "list[str]" = []

    if len(raw_text) < min_length:
        warnings.append(
            f"raw input below min-length ({len(raw_text)} < {min_length})"
        )
        return {
            "status": "unknown",
            "feature_id": feature_id,
            "reason": None,
            "strategy": "none",
            "raw_signal_line": None,
            "warnings": warnings,
            "meta": {
                "feature_id": feature_id,
                "input_length": len(raw_text),
            },
        }

    # Pre-process: strip markdown emphasis on each non-empty line so signals
    # wrapped in **bold** or _italic_ match the same regexes.
    stripped_lines = [
        _strip_emphasis(line) if line.strip() else line
        for line in raw_text.splitlines()
    ]
    stripped_text = "\n".join(stripped_lines)

    strategies = [
        ("exact_signal", lambda: _strategy_exact(stripped_text, feature_id)),
        (
            "case_insensitive",
            lambda: _strategy_case_insensitive(stripped_text, feature_id),
        ),
        (
            "natural_language",
            lambda: _strategy_natural_language(raw_text, feature_id),
        ),
    ]

    for strategy_name, runner in strategies:
        status, reason, raw_line, strat_warnings = runner()
        if status is None:
            continue
        warnings.extend(strat_warnings)
        return {
            "status": status,
            "feature_id": feature_id,
            "reason": reason,
            "strategy": strategy_name,
            "raw_signal_line": raw_line,
            "warnings": warnings,
            "meta": {
                "feature_id": feature_id,
                "input_length": len(raw_text),
            },
        }

    # No strategy matched.
    warnings.append(
        "no signal pattern matched (exact/case-insensitive/natural-language)"
    )
    return {
        "status": "unknown",
        "feature_id": feature_id,
        "reason": None,
        "strategy": "none",
        "raw_signal_line": None,
        "warnings": warnings,
        "meta": {
            "feature_id": feature_id,
            "input_length": len(raw_text),
        },
    }


def _read_input(args) -> str:
    """Read raw text from one of the three input sources."""
    sources_provided = sum(
        1 for flag in (args.stdin, args.input_file, args.input_string) if flag
    )
    if sources_provided == 0:
        raise ValueError(
            "no input source provided; pass exactly one of "
            "--stdin / --input-file / --input-string"
        )
    if sources_provided > 1:
        raise ValueError(
            "multiple input sources provided; pass exactly one of "
            "--stdin / --input-file / --input-string"
        )
    if args.stdin:
        return sys.stdin.read()
    if args.input_file:
        path = Path(args.input_file)
        if not path.exists():
            raise FileNotFoundError(f"input file not found: {path}")
        return path.read_text(encoding="utf-8")
    if args.input_string is not None:
        return args.input_string
    raise ValueError("no input source provided")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse completion signal from background subagent output."
    )
    parser.add_argument(
        "--feature-id",
        required=True,
        help="Feature ID to match in the completion signal (e.g. s1-feat-002)",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read raw text from stdin",
    )
    parser.add_argument(
        "--input-file",
        default=None,
        help="Read raw text from the given file path",
    )
    parser.add_argument(
        "--input-string",
        default=None,
        help="Read raw text from the given string literal",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=DEFAULT_MIN_LENGTH,
        help=(
            "Minimum acceptable raw input length (default: "
            f"{DEFAULT_MIN_LENGTH}); below this the result is unknown"
        ),
    )
    try:
        args = parser.parse_args()
        raw_text = _read_input(args)
    except (ValueError, FileNotFoundError, OSError, argparse.ArgumentError) as exc:
        print(f"parse_completion_signal: error: {exc}", file=sys.stderr)
        return 2

    try:
        result = parse_signal(
            raw_text,
            feature_id=args.feature_id,
            min_length=args.min_length,
        )
    except Exception as exc:  # pragma: no cover - defensive catch-all
        print(f"parse_completion_signal: error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] in ("completed", "blocked"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
