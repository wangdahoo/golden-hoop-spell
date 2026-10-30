#!/usr/bin/env python3
"""Read-modify-write feature/plan status in .ghs/features.json.

ghs-code and ghs-archive mutate feature/plan status exclusively through this
script. Hand-editing features.json or inline `python -c` snippets are
forbidden: multi-line `-c` bodies get wrapped into a temporary batch script
by the Windows shell and fail unpredictably, and hand-rolled full-file
rewrites risk silently dropping fields. This helper performs a strict
read-modify-write (unknown fields are preserved verbatim), always saves
UTF-8 (atomic replace), and validates every status against the schema
enumerations enforced by validate_structure.py.

Usage:
    command python3 update_features.py \
        --file <PROJECT_DIR>/.ghs/features.json \
        --set-feature <feature_id> --status completed

    command python3 update_features.py \
        --set-feature <feature_id> --status blocked --blocked-reason "waiting for API"

    command python3 update_features.py --set-plan <plan_id> --status completed

    command python3 update_features.py --plan-state <plan_id>

Without --file, the features.json path is resolved via resolve_project_dir
(walk up from cwd to the nearest directory containing .ghs/).

Output:
    --set-feature / --set-plan: single ASCII confirmation line on stdout.
    --plan-state: single-line JSON on stdout:
        {"plan_id": "...", "counts": {"completed": N, "in_progress": N,
         "pending": N, "blocked": N}, "can_complete": <bool>,
         "blocked_ids": [...]}

Exit codes:
    0 - success
    1 - feature/plan id not found
    2 - invalid arguments / ambiguous feature id / missing or malformed
        features.json / IO error
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from ghs_compat import force_utf8_stdio
from resolve_project_dir import find_project_dir

FEATURE_STATUS_VALUES = ("pending", "in_progress", "completed", "blocked")
PLAN_STATUS_VALUES = ("planning", "in_progress", "completed", "on_hold")


def load_features(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"features.json not found: {path}")
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read features.json: {exc}") from None
    if not isinstance(data, dict):
        raise ValueError("features.json must contain a JSON object")
    return data


def write_features(path: Path, data: dict) -> None:
    """Serialize data as UTF-8 JSON and atomically replace the file.

    ensure_ascii=False keeps non-ASCII values as literal UTF-8 characters,
    matching the repo-wide JSON storage convention.
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


def locate_feature(data: dict, feature_id: str) -> "tuple[dict, dict]":
    """Return (plan, feature) for feature_id across plans[].features[].

    Raises KeyError when the id does not exist and ValueError when the id
    appears under more than one plan (ambiguous — refuse to guess).
    """
    hits = []
    for plan in data.get("plans", []):
        for feature in plan.get("features", []):
            if feature.get("id") == feature_id:
                hits.append((plan, feature))
    if not hits:
        raise KeyError(f"feature id not found: {feature_id}")
    if len(hits) > 1:
        owner_ids = ", ".join(p.get("id", "?") for p, _ in hits)
        raise ValueError(
            f"ambiguous feature id {feature_id!r}: present in plans ({owner_ids}); "
            "feature ids must be unique across plans"
        )
    return hits[0]


def locate_plan(data: dict, plan_id: str) -> dict:
    for plan in data.get("plans", []):
        if plan.get("id") == plan_id:
            return plan
    raise KeyError(f"plan id not found: {plan_id}")


def compute_plan_state(data: dict, plan_id: str) -> dict:
    """Return the plan completion state consumed by ghs-code/ghs-archive closings."""
    plan = locate_plan(data, plan_id)
    counts = {"completed": 0, "in_progress": 0, "pending": 0, "blocked": 0}
    blocked_ids = []
    for feature in plan.get("features", []):
        status = feature.get("status", "")
        if status in counts:
            counts[status] += 1
        if status == "blocked":
            blocked_ids.append(feature.get("id", ""))
    can_complete = (
        counts["completed"] >= 1
        and counts["pending"] == 0
        and counts["in_progress"] == 0
        and counts["blocked"] == 0
    )
    return {
        "plan_id": plan_id,
        "counts": counts,
        "can_complete": can_complete,
        "blocked_ids": blocked_ids,
    }


def main() -> int:
    force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Read-modify-write feature/plan status in .ghs/features.json."
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Path to features.json (default: resolve project dir from cwd)",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--set-feature", metavar="FEATURE_ID", default=None,
        help="Set one feature's status",
    )
    target.add_argument(
        "--set-plan", metavar="PLAN_ID", default=None,
        help="Set one plan's status",
    )
    target.add_argument(
        "--plan-state", metavar="PLAN_ID", default=None,
        help="Print the plan completion state as single-line JSON",
    )
    parser.add_argument(
        "--status",
        default=None,
        help=(
            "New status for --set-feature "
            f"({' | '.join(FEATURE_STATUS_VALUES)}) or --set-plan "
            f"({' | '.join(PLAN_STATUS_VALUES)})"
        ),
    )
    parser.add_argument(
        "--blocked-reason",
        default=None,
        help="Required with --set-feature --status blocked",
    )

    args = parser.parse_args()

    # --- argument cross-validation (exit 2, before touching any file) ---
    if (args.set_feature or args.set_plan) and not args.status:
        print(
            "update_features: error: --status is required with "
            "--set-feature/--set-plan",
            file=sys.stderr,
        )
        return 2
    if args.plan_state and args.status is not None:
        print(
            "update_features: error: --status is not valid with --plan-state",
            file=sys.stderr,
        )
        return 2
    if args.set_feature:
        if args.status not in FEATURE_STATUS_VALUES:
            print(
                f"update_features: error: --status must be one of "
                f"{' | '.join(FEATURE_STATUS_VALUES)}, got {args.status!r}",
                file=sys.stderr,
            )
            return 2
        if args.status == "blocked" and not (
            args.blocked_reason and args.blocked_reason.strip()
        ):
            print(
                "update_features: error: --blocked-reason is required with "
                "--status blocked",
                file=sys.stderr,
            )
            return 2
        if args.status != "blocked" and args.blocked_reason is not None:
            print(
                "update_features: error: --blocked-reason is only valid with "
                "--status blocked",
                file=sys.stderr,
            )
            return 2
    if args.set_plan and args.status not in PLAN_STATUS_VALUES:
        print(
            f"update_features: error: --status must be one of "
            f"{' | '.join(PLAN_STATUS_VALUES)}, got {args.status!r}",
            file=sys.stderr,
        )
        return 2
    if args.blocked_reason and not args.set_feature:
        print(
            "update_features: error: --blocked-reason is only valid with "
            "--set-feature",
            file=sys.stderr,
        )
        return 2

    # --- resolve features.json path ---
    if args.file:
        path = Path(args.file)
    else:
        project_dir = find_project_dir(Path.cwd())
        if project_dir is None:
            print(
                "update_features: error: no project directory found "
                "(no .ghs/ with features.json or progress.md in any parent "
                "directory)",
                file=sys.stderr,
            )
            return 2
        path = project_dir / ".ghs" / "features.json"

    try:
        data = load_features(path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"update_features: error: {exc}", file=sys.stderr)
        return 2

    # --- read-only branch ---
    if args.plan_state:
        try:
            state = compute_plan_state(data, args.plan_state)
        except KeyError as exc:
            print(f"update_features: error: {exc}", file=sys.stderr)
            return 1
        # ensure_ascii=True: ids are ASCII, keeps stdout single-line ASCII.
        print(json.dumps(state, ensure_ascii=True))
        return 0

    # --- mutation branches (locate BEFORE write so errors leave the file untouched) ---
    try:
        if args.set_feature:
            _plan, feature = locate_feature(data, args.set_feature)
            feature["status"] = args.status
            if args.status == "blocked":
                feature["blocked_reason"] = args.blocked_reason.strip()
            elif "blocked_reason" in feature:
                # A stale reason on a non-blocked feature would mislead status
                # consumers; drop it.
                del feature["blocked_reason"]
            print(f"OK feature {args.set_feature} status={args.status}")
        else:
            plan = locate_plan(data, args.set_plan)
            plan["status"] = args.status
            print(f"OK plan {args.set_plan} status={args.status}")
    except KeyError as exc:
        print(f"update_features: error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"update_features: error: {exc}", file=sys.stderr)
        return 2

    try:
        write_features(path, data)
    except OSError as exc:
        print(
            f"update_features: error: cannot write features.json: {exc}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
