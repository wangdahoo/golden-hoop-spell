#!/usr/bin/env python3
"""Read-modify-write a ghs-plan status file (.ghs/plans/*-status.json).

The ghs-plan dispatcher mutates plan status exclusively through this script.
Inline `python -c` snippets are forbidden: multi-line `-c` bodies get wrapped
into a temporary batch script by the Windows shell and fail unpredictably,
and hand-rolled full-file rewrites risk silently dropping fields. This helper
performs a strict read-modify-write (unknown fields are preserved verbatim),
always saves UTF-8 (atomic replace), and refreshes `updated_at` on every call.

Usage:
    command python3 update_plan_status.py \
        --file <PROJECT_DIR>/.ghs/plans/{date}-{slug}-status.json \
        --set status=revising

    command python3 update_plan_status.py --file <status.json> \
        --set status=pending_approval --set final_fix_pending=false

    command python3 update_plan_status.py --file <status.json> --bump-retry plan

Settable keys (--set KEY=VALUE, repeatable, combinable in one call):
    status                     designing | reviewing | revising |
                               pending_approval | approved | aborted
    lane                       light | full
    plan_file                  string
    context_file               string
    reject_count               non-negative integer
    final_fix_pending          true | false
    accepted_with_fail         true | false
    keep_raw_on_success        true | false
    retry_counts.plan          non-negative integer
    retry_counts.review        non-negative integer
    retry_counts.context_snapshot  non-negative integer
    updated_at                 string (explicit value; otherwise auto-refreshed)

--bump-retry KIND increments retry_counts[KIND] by 1 (a missing key counts as 0).
`updated_at` is refreshed automatically on every mutating call unless it is set
explicitly via --set updated_at=<value>.

Output: a single ASCII confirmation line on stdout.

Exit codes:
    0 - status file updated
    2 - invalid arguments / missing file / malformed JSON / IO error
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from ghs_compat import force_utf8_stdio

STATUS_VALUES = (
    "designing",
    "reviewing",
    "revising",
    "pending_approval",
    "approved",
    "aborted",
)
LANE_VALUES = ("light", "full")
RETRY_KINDS = ("plan", "review", "context_snapshot")
BOOL_KEYS = ("final_fix_pending", "accepted_with_fail", "keep_raw_on_success")
INT_KEYS = ("reject_count",)
STR_KEYS = ("plan_file", "context_file", "updated_at")

RETRY_PREFIX = "retry_counts."


def _parse_bool(key: str, raw: str) -> bool:
    lowered = raw.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise ValueError(f"{key}: expected 'true' or 'false', got {raw!r}")


def _parse_int(key: str, raw: str) -> int:
    try:
        value = int(raw.strip(), 10)
    except ValueError:
        raise ValueError(f"{key}: expected an integer, got {raw!r}") from None
    if value < 0:
        raise ValueError(f"{key}: expected a non-negative integer, got {raw!r}")
    return value


def parse_set_item(item: str) -> "tuple[str, object]":
    """Parse one KEY=VALUE token into a validated (key path, typed value) pair.

    Raises ValueError on unknown keys, bad enums, or mistyped values so a
    dispatcher typo cannot silently corrupt the status file.
    """
    key, sep, raw = item.partition("=")
    key = key.strip()
    if not sep or not key:
        raise ValueError(f"--set expects KEY=VALUE, got {item!r}")
    if key == "status":
        if raw not in STATUS_VALUES:
            raise ValueError(
                f"status: must be one of {' | '.join(STATUS_VALUES)}, got {raw!r}"
            )
        return key, raw
    if key == "lane":
        if raw not in LANE_VALUES:
            raise ValueError(
                f"lane: must be one of {' | '.join(LANE_VALUES)}, got {raw!r}"
            )
        return key, raw
    if key in BOOL_KEYS:
        return key, _parse_bool(key, raw)
    if key in INT_KEYS:
        return key, _parse_int(key, raw)
    if key.startswith(RETRY_PREFIX):
        kind = key[len(RETRY_PREFIX):]
        if kind not in RETRY_KINDS:
            raise ValueError(
                f"{key}: retry kind must be one of {' | '.join(RETRY_KINDS)}"
            )
        return key, _parse_int(key, raw)
    if key in STR_KEYS:
        if not raw.strip():
            raise ValueError(f"{key}: value must not be empty")
        return key, raw
    raise ValueError(
        f"unknown key {key!r}; settable keys: status, lane, plan_file, "
        "context_file, reject_count, final_fix_pending, accepted_with_fail, "
        "keep_raw_on_success, retry_counts.<plan|review|context_snapshot>, "
        "updated_at"
    )


def apply_sets(data: dict, parsed_sets) -> "list[str]":
    """Apply validated (key, value) pairs onto data; return the mutated key names."""
    mutated = []
    for key, value in parsed_sets:
        if key.startswith(RETRY_PREFIX):
            kind = key[len(RETRY_PREFIX):]
            data.setdefault("retry_counts", {})[kind] = value
        else:
            data[key] = value
        mutated.append(key)
    return mutated


def apply_bump_retry(data: dict, kind: str) -> str:
    """Increment retry_counts[kind] by 1 (missing key counts as 0). Returns key name."""
    retry = data.setdefault("retry_counts", {})
    current = retry.get(kind, 0)
    if isinstance(current, bool) or not isinstance(current, int):
        raise ValueError(f"retry_counts.{kind}: existing value is not an integer")
    retry[kind] = current + 1
    return f"retry_counts.{kind}"


def write_status(path: Path, data: dict) -> None:
    """Serialize data as UTF-8 JSON and atomically replace the status file.

    ensure_ascii=False keeps non-ASCII values as literal UTF-8 characters
    (never \\u escapes), matching the repo-wide JSON storage convention.
    """
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def main() -> int:
    force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description=(
            "Read-modify-write a ghs-plan status JSON file "
            "(.ghs/plans/*-status.json)."
        )
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to the plan status JSON file",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        dest="sets",
        metavar="KEY=VALUE",
        help=(
            "Set one field (repeatable): status, lane, plan_file, context_file, "
            "reject_count, final_fix_pending, accepted_with_fail, "
            "keep_raw_on_success, retry_counts.<kind>, updated_at"
        ),
    )
    parser.add_argument(
        "--bump-retry",
        choices=RETRY_KINDS,
        default=None,
        help="Increment retry_counts.<kind> by 1",
    )
    try:
        args = parser.parse_args()
        parsed_sets = [parse_set_item(item) for item in args.sets]
    except (ValueError, argparse.ArgumentError) as exc:
        print(f"update_plan_status: error: {exc}", file=sys.stderr)
        return 2

    if not parsed_sets and args.bump_retry is None:
        print(
            "update_plan_status: error: nothing to do; "
            "pass --set KEY=VALUE and/or --bump-retry KIND",
            file=sys.stderr,
        )
        return 2

    path = Path(args.file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(
            f"update_plan_status: error: status file not found: {path}",
            file=sys.stderr,
        )
        return 2
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(
            f"update_plan_status: error: cannot read status file: {exc}",
            file=sys.stderr,
        )
        return 2
    if not isinstance(data, dict):
        print(
            "update_plan_status: error: status file must contain a JSON object",
            file=sys.stderr,
        )
        return 2

    try:
        mutated = apply_sets(data, parsed_sets)
        if args.bump_retry is not None:
            mutated.append(apply_bump_retry(data, args.bump_retry))
    except ValueError as exc:
        print(f"update_plan_status: error: {exc}", file=sys.stderr)
        return 2

    if "updated_at" not in dict(parsed_sets):
        data["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        mutated.append("updated_at")

    try:
        write_status(path, data)
    except OSError as exc:
        print(
            f"update_plan_status: error: cannot write status file: {exc}",
            file=sys.stderr,
        )
        return 2

    # Single ASCII confirmation line (keys only — values stay off the console).
    print(f"OK updated {len(mutated)} field(s): {', '.join(mutated)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
