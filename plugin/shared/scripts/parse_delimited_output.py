#!/usr/bin/env python3
"""Parse delimiter-based subagent output with multiple fallback strategies.

Reads raw text emitted by a subagent (Plan Designer, Plan Reviewer, or Explore)
and extracts the delimited payload, tolerating common protocol deviations such
as code-fence wrapping, Chinese-punctuation bracket swaps, missing brackets,
or pure-markdown fallback. Emits a JSON result describing which strategy won
plus verdict / completion-signal fields so the dispatcher never has to
re-parse the text itself.

Usage:
    command python3 parse_delimited_output.py --kind plan --stdin < raw.txt
    command python3 parse_delimited_output.py --kind review --input-file path/to/raw.txt \
        --completion-signal "REVIEW COMPLETE" --min-length 150
    command python3 parse_delimited_output.py --kind plan --input-string "..." \
        --completion-signal "PLAN DESIGN COMPLETE" --min-length 300
    command python3 parse_delimited_output.py --start-token "<BEGIN>" --end-token "<END>" \
        --input-string "..."

Output: a single JSON object on stdout with the following shape:
    {
      "status": "ok" | "fallback_used" | "empty" | "malformed",
      "content": "<extracted text or empty string>",
      "strategy": "exact_delimiter" | "normalized_delimiter" | "code_fence"
                  | "whole_body" | "none",
      "completion_signal": "<stripped signal line, including variables like "
                           "Verdict: PASS/FAIL, or null>",
      "verdict": "PASS" | "FAIL" | null,    # only for --kind review
      "warnings": ["...", "..."],
      "meta": {
        "kind": "plan",
        "input_length": 1234,
        "content_length": 567
      }
    }

Exit codes:
    0 - parsing succeeded (status == ok or fallback_used)
    1 - parsing failed (status == empty or malformed)
    2 - invalid arguments / IO error
"""

import argparse
import json
import re
import sys
from pathlib import Path


# Token name per --kind value (used to derive the delimiter labels).
TOKEN_BY_KIND = {
    "plan": "PLAN",
    "review": "REVIEW",
    "context_snapshot": "CONTEXT_SNAPSHOT",
}

# Default min length when --min-length not provided.
DEFAULT_MIN_LENGTH = 200

# Regex that pulls `Verdict: PASS` or `Verdict: FAIL` out of a review signal line.
VERDICT_RE = re.compile(r"Verdict:\s*(PASS|FAIL)")

# Marker that plan-designer prints at the end of its response; everything after
# it is metadata that must not leak into the extracted content.
ADDITIONAL_FILES_READ_MARKER = "ADDITIONAL FILES READ:"

# Regex variants used by STRATEGY 2 normalized_delimiter. The middle group is
# the literal token name (e.g. PLAN / REVIEW / CONTEXT_SNAPSHOT).
_NORMALIZED_TOKEN_LEFT = r"[<《「〖]+\s*"
_NORMALIZED_TOKEN_RIGHT = r"\s*[>》」〗]+"
_NORMALIZED_TOKEN_PARTS = (
    # token name may use underscore or just letters, mixed case tolerated
    r"(({token})(?:_?START)?)",
)


def _strip_thinking(text: str) -> str:
    """Strip legacy <thinking>...</thinking> and <antml:thinking>...</antml:thinking> blocks.

    On the modern extended-thinking API path the thinking payload is already
    peeled off by the SDK before this helper sees the text, in which case this
    function is a no-op (the regex simply does not match). The branch exists so
    that legacy integrations or third-party gateways which leak the tag back
    into the main response still get cleaned up.
    """
    pattern = re.compile(
        r"<(?:antml:)?thinking>.*?</(?:antml:)?thinking>",
        re.DOTALL | re.IGNORECASE,
    )
    # Also tolerate an unclosed thinking tag (rare but seen) by stripping
    # everything after it if no closing tag exists. The non-greedy pattern
    # above already handles the closed case.
    closed_stripped = pattern.sub("", text)
    # Drop a stray opening tag without a matching close, if any remains.
    open_only = re.compile(r"<(?:antml:)?thinking>.*", re.DOTALL | re.IGNORECASE)
    return open_only.sub("", closed_stripped)


def _strip_completion_signal(text: str, signal: str) -> "tuple[str, str | None]":
    """Strip the completion-signal line from text, returning (cleaned_text, signal_line).

    The signal is treated as a line-anchored prefix (per plan §3.3 Round 2 Medium #1):
        r'^\\s*' + re.escape(signal) + r'\\b.*$'  with re.MULTILINE
    The entire matching line (including any trailing variables like
    `| Verdict: PASS | Severe: 0 ...`) is captured and returned as signal_line.
    """
    if not signal:
        return text, None
    pattern = re.compile(
        r"^[ \t]*" + re.escape(signal) + r"\b.*$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return text, None
    signal_line = match.group(0).strip()
    cleaned = pattern.sub("", text)
    return cleaned, signal_line


def _strip_additional_files_read(text: str) -> str:
    """Strip everything from the ADDITIONAL FILES READ: marker onward.

    The plan-designer subagent appends an "ADDITIONAL FILES READ:" tail listing
    files it consulted; that metadata is not part of the plan body.
    """
    idx = text.find(ADDITIONAL_FILES_READ_MARKER)
    if idx == -1:
        return text
    return text[:idx].rstrip()


def _extract_verdict(signal_line: "str | None", raw_text: str) -> "str | None":
    """Extract Verdict: PASS|FAIL from the completion-signal line first, then the raw text tail."""
    if signal_line:
        m = VERDICT_RE.search(signal_line)
        if m:
            return m.group(1)
    # Fallback: scan the trailing ~600 chars of raw input for the verdict token.
    tail = raw_text[-600:] if len(raw_text) > 600 else raw_text
    m = VERDICT_RE.search(tail)
    if m:
        return m.group(1)
    return None


def _resolve_tokens(args) -> "tuple[str, str]":
    """Resolve (start_token, end_token) from args based on --kind / explicit overrides."""
    if args.start_token and args.end_token:
        return args.start_token, args.end_token
    if args.kind == "generic":
        # Generic mode requires explicit tokens.
        raise ValueError(
            "--start-token and --end-token are required when --kind=generic"
        )
    token_name = TOKEN_BY_KIND.get(args.kind)
    if token_name is None:
        raise ValueError(f"unknown --kind value: {args.kind!r}")
    start = f"<<<{token_name}_START>>>"
    end = f"<<<{token_name}_END>>>"
    return start, end


# ---------------------------------------------------------------------------
# Parsing strategies. Each returns (content, warnings) or (None, warnings).
# Callers must validate len(content.strip()) >= MIN_LEN before accepting.
# ---------------------------------------------------------------------------


def _strategy_exact(text: str, start_token: str, end_token: str):
    """STRATEGY 1: literal `<<<X_START>>>...<<<X_END>>>` extraction.

    When the raw text contains multiple candidate pairs (for example a code
    fence that quotes the delimiters as string literals followed by the real
    pair), pick the pair with the largest inner span. A literal-inside-fence
    pair always has a tiny gap (a few characters between two adjacent string
    literal occurrences), while the real pair surrounds the entire payload, so
    max-span selection reliably wins. The plan §3.3 STRATEGY 1 priority over
    STRATEGY 3 code_fence is preserved by trying this strategy first.
    """
    warnings = []
    start_positions = []
    search_from = 0
    while True:
        idx = text.find(start_token, search_from)
        if idx == -1:
            break
        start_positions.append(idx)
        search_from = idx + len(start_token)
    if not start_positions:
        return None, warnings

    best_content = None
    for start_idx in start_positions:
        content_start = start_idx + len(start_token)
        end_idx = text.find(end_token, content_start)
        if end_idx == -1:
            continue
        candidate = text[content_start:end_idx]
        if best_content is None or len(candidate) > len(best_content):
            best_content = candidate
    if best_content is None:
        return None, warnings
    return best_content, warnings


def _strategy_normalized(text: str, token_name: str):
    """STRATEGY 2: tolerate bracket punctuation / whitespace / case variations.

    Matches the kind-specific token only (e.g. PLAN) so a response that mixes
    multiple kinds does not cross-contaminate.
    """
    warnings = []
    token_re = re.escape(token_name)
    # Allow underscores / mixed case between the token name and START/END.
    start_pattern = re.compile(
        _NORMALIZED_TOKEN_LEFT
        + token_re
        + r"(?i:_?START)?"
        + _NORMALIZED_TOKEN_RIGHT
    )
    end_pattern = re.compile(
        _NORMALIZED_TOKEN_LEFT
        + token_re
        + r"(?i:_?END)?"
        + _NORMALIZED_TOKEN_RIGHT
    )
    start_match = start_pattern.search(text)
    if not start_match:
        return None, warnings
    end_match = end_pattern.search(text, start_match.end())
    if not end_match:
        return None, warnings
    content = text[start_match.end():end_match.start()]
    warnings.append(
        f"delimiter normalized: matched START at {start_match.start()}-{start_match.end()}, "
        f"END at {end_match.start()}-{end_match.end()}"
    )
    return content, warnings


def _strategy_code_fence(text: str, start_token: str, end_token: str):
    """STRATEGY 3: take the largest fenced code block.

    If the fence itself contains delimiters, defer to STRATEGY 1 on the fenced
    content so an exact-match win is not masked by fence wrapping.
    """
    warnings = []
    # Find all fenced blocks delimited by ``` or ~~~ (3 or more of same char).
    fence_pattern = re.compile(
        r"(?m)^(?P<fence>`{3,}|~{3,})[^\n]*\n(?P<body>.*?)(?P=fence)[^\n]*$",
        re.DOTALL,
    )
    blocks = list(fence_pattern.finditer(text))
    if not blocks:
        return None, warnings
    # Pick the largest block by body length.
    largest = max(blocks, key=lambda m: len(m.group("body")))
    body = largest.group("body")
    # If the fenced body contains literal delimiters, try STRATEGY 1 on it.
    inner = _strategy_exact(body, start_token, end_token)
    if inner[0] is not None:
        warnings.append("code_fence: inner exact-delimiter match used")
        return inner[0], warnings
    warnings.append("code_fence: largest fenced block returned as content")
    return body, warnings


def _strategy_whole_body(
    text: str,
    completion_signal: "str | None",
    kind: str,
    raw_text: str,
):
    """STRATEGY 4: take the whole body after stripping thinking / signal / extras."""
    warnings = ["whole_body fallback engaged"]
    cleaned = _strip_thinking(text)
    # Strip completion signal (signal_line captured for verdict extraction
    # but we use raw_text for that, so we ignore the returned value here).
    cleaned, _ = _strip_completion_signal(cleaned, completion_signal or "")
    cleaned = _strip_additional_files_read(cleaned)
    if not cleaned.strip():
        # Nothing usable left after stripping — return None so the orchestrator
        # does not classify this as a too-short hit (which would yield status
        # "empty"); instead it falls through to "malformed".
        warnings.append("whole_body: nothing left after stripping")
        return None, warnings
    return cleaned, warnings


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def parse_raw(
    raw_text: str,
    *,
    kind: str,
    start_token: str,
    end_token: str,
    min_length: int,
    completion_signal: "str | None",
) -> dict:
    """Parse raw_text and return the JSON-serializable result dict."""
    warnings: "list[str]" = []
    token_name = TOKEN_BY_KIND.get(kind, "")

    # Pre-extract completion signal from the WHOLE raw text regardless of which
    # strategy wins, so the dispatcher always sees a stable signal field.
    _, captured_signal_line = _strip_completion_signal(raw_text, completion_signal or "")

    # Try strategies in priority order.
    strategies = [
        ("exact_delimiter", lambda: _strategy_exact(raw_text, start_token, end_token)),
    ]
    if token_name:
        strategies.append(
            ("normalized_delimiter", lambda: _strategy_normalized(raw_text, token_name))
        )
    strategies.append(
        ("code_fence", lambda: _strategy_code_fence(raw_text, start_token, end_token))
    )
    strategies.append(
        (
            "whole_body",
            lambda: _strategy_whole_body(raw_text, completion_signal, kind, raw_text),
        )
    )

    found_short_content = False  # Tracks the empty-vs-malformed distinction.

    for strategy_name, runner in strategies:
        content, strat_warnings = runner()
        if content is None:
            continue
        warnings.extend(strat_warnings)
        if len(content.strip()) >= min_length:
            # Success — strip completion signal from the extracted content too
            # so a strategy that includes the trailing signal line still
            # produces clean output.
            content, _ = _strip_completion_signal(content, completion_signal or "")
            content = _strip_additional_files_read(content)
            status = "ok" if strategy_name == "exact_delimiter" else "fallback_used"
            verdict = (
                _extract_verdict(captured_signal_line, raw_text)
                if kind == "review"
                else None
            )
            return {
                "status": status,
                "content": content.strip(),
                "strategy": strategy_name,
                "completion_signal": captured_signal_line,
                "verdict": verdict,
                "warnings": warnings,
                "meta": {
                    "kind": kind,
                    "input_length": len(raw_text),
                    "content_length": len(content.strip()),
                },
            }
        # Strategy found something but too short.
        found_short_content = True
        warnings.append(
            f"{strategy_name}: extracted content too short "
            f"({len(content.strip())} < {min_length})"
        )

    # No strategy produced acceptable content.
    status = "empty" if found_short_content else "malformed"
    verdict = (
        _extract_verdict(captured_signal_line, raw_text)
        if kind == "review"
        else None
    )
    return {
        "status": status,
        "content": "",
        "strategy": "none",
        "completion_signal": captured_signal_line,
        "verdict": verdict,
        "warnings": warnings,
        "meta": {
            "kind": kind,
            "input_length": len(raw_text),
            "content_length": 0,
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
    # Defensive — should be unreachable given the count check above.
    raise ValueError("no input source provided")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse delimiter-based subagent output with fallback strategies."
    )
    parser.add_argument(
        "--kind",
        choices=["plan", "review", "context_snapshot", "generic"],
        default="generic",
        help="Delimiter family to extract (default: generic, requires --start-token/--end-token)",
    )
    parser.add_argument(
        "--start-token",
        default=None,
        help="Explicit start delimiter (overrides --kind; required for --kind=generic)",
    )
    parser.add_argument(
        "--end-token",
        default=None,
        help="Explicit end delimiter (overrides --kind; required for --kind=generic)",
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
        help=f"Minimum acceptable stripped content length (default: {DEFAULT_MIN_LENGTH})",
    )
    parser.add_argument(
        "--completion-signal",
        default=None,
        help="Completion-signal prefix to detect and strip (line-anchored, word-boundary)",
    )
    try:
        args = parser.parse_args()
        raw_text = _read_input(args)
        start_token, end_token = _resolve_tokens(args)
    except (ValueError, FileNotFoundError, OSError, argparse.ArgumentError) as exc:
        print(f"parse_delimited_output: error: {exc}", file=sys.stderr)
        return 2

    try:
        result = parse_raw(
            raw_text,
            kind=args.kind,
            start_token=start_token,
            end_token=end_token,
            min_length=args.min_length,
            completion_signal=args.completion_signal,
        )
    except Exception as exc:  # pragma: no cover - defensive catch-all
        print(f"parse_delimited_output: error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] in ("ok", "fallback_used"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
