#!/usr/bin/env python3
"""Validate features.json structure and schema."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple

from ghs_compat import force_utf8_stdio

# ID format patterns
PLAN_ID_PATTERN = re.compile(r"^p\d{1,4}$")
FEATURE_ID_PATTERN = re.compile(r"^p\d{1,4}-feat-\d{3}$")


def validate_project_section(data: Dict) -> List[str]:
    """Validate project section."""
    errors = []
    project = data.get("project", {})

    required_fields = ["name", "description", "created_at"]
    for field in required_fields:
        if field not in project:
            errors.append(f"Missing project.{field}")

    return errors


def validate_plan_id_format(plan_id: str, plan_idx: int) -> List[str]:
    """Validate plan ID matches the required format ^p\\d{1,4}$."""
    errors = []
    if not PLAN_ID_PATTERN.match(plan_id):
        errors.append(
            f"Plan {plan_idx}: invalid plan ID format '{plan_id}' "
            f"(must match ^p\\d{{1,4}}$, e.g. p1, p12, p1234)"
        )
    return errors


def validate_feature_id_format(feature_id: str, feature_idx: int) -> List[str]:
    """Validate feature ID matches the required format ^p\\d{1,4}-feat-\\d{3}$."""
    errors = []
    if not FEATURE_ID_PATTERN.match(feature_id):
        errors.append(
            f"Feature {feature_idx}: invalid feature ID format '{feature_id}' "
            f"(must match ^p\\d{{1,4}}-feat-\\d{{3}}$, e.g. p1-feat-001)"
        )
    return errors


def validate_feature_prefix_consistency(
    feature_id: str, plan_id: str, feature_idx: int
) -> List[str]:
    """Validate that the plan number prefix in feature ID matches parent plan ID."""
    errors = []
    plan_match = PLAN_ID_PATTERN.match(plan_id)
    feature_match = FEATURE_ID_PATTERN.match(feature_id)
    if plan_match and feature_match:
        plan_num = plan_id[1:]  # strip leading 'p'
        feature_prefix = feature_id.split("-feat-")[0][1:]  # get number before '-feat-'
        if plan_num != feature_prefix:
            errors.append(
                f"Feature {feature_idx}: feature ID '{feature_id}' prefix "
                f"does not match parent plan '{plan_id}' "
                f"(plan number {plan_num} vs feature prefix {feature_prefix})"
            )
    return errors


def validate_feature(feature: Dict, feature_idx: int, plan_id: str = "") -> Tuple[List[str], List[str]]:
    """Validate a single feature.

    Returns a tuple of (errors, warnings).
    """
    errors = []
    warnings = []

    required_fields = ["id", "title", "description", "status"]
    for field in required_fields:
        if field not in feature:
            errors.append(f"Feature {feature_idx}: missing '{field}'")

    # Feature ID format validation
    feature_id = feature.get("id", "")
    if feature_id:
        errors.extend(validate_feature_id_format(feature_id, feature_idx))

    # Feature ID prefix consistency with parent plan
    if feature_id and plan_id:
        errors.extend(
            validate_feature_prefix_consistency(feature_id, plan_id, feature_idx)
        )

    valid_statuses = ["pending", "in_progress", "completed", "blocked"]
    status = feature.get("status", "")
    if status and status not in valid_statuses:
        errors.append(f"Feature {feature_idx}: invalid status '{status}'")

    # blocked_reason: warn if status is 'blocked' and no reason provided
    if status == "blocked" and "blocked_reason" not in feature:
        warnings.append(
            f"Feature {feature_idx}: status is 'blocked' but no 'blocked_reason' field "
            f"(recommended but not required)"
        )

    valid_priorities = ["high", "medium", "low"]
    priority = feature.get("priority", "")
    if priority and priority not in valid_priorities:
        errors.append(f"Feature {feature_idx}: invalid priority '{priority}'")

    valid_categories = ["core", "ui", "api", "auth", "data", "infra"]
    category = feature.get("category", "")
    if category and category not in valid_categories:
        errors.append(f"Feature {feature_idx}: invalid category '{category}'")

    return errors, warnings


def validate_plan(plan: Dict, plan_idx: int) -> Tuple[List[str], List[str]]:
    """Validate a single plan.

    Returns a tuple of (errors, warnings).
    """
    errors = []
    warnings = []

    required_fields = ["id", "name", "status"]
    for field in required_fields:
        if field not in plan:
            errors.append(f"Plan {plan_idx}: missing '{field}'")

    # Plan ID format validation
    plan_id = plan.get("id", "")
    if plan_id:
        errors.extend(validate_plan_id_format(plan_id, plan_idx))

    valid_statuses = ["planning", "in_progress", "completed", "on_hold"]
    status = plan.get("status", "")
    if status and status not in valid_statuses:
        errors.append(f"Plan {plan_idx}: invalid status '{status}'")

    features = plan.get("features", [])
    if not isinstance(features, list):
        errors.append(f"Plan {plan_idx}: 'features' must be an array")
    else:
        for idx, feature in enumerate(features):
            feat_errors, feat_warnings = validate_feature(feature, idx, plan_id)
            errors.extend(feat_errors)
            warnings.extend(feat_warnings)

    return errors, warnings


def validate_features_json(filepath: Path) -> Tuple[List[str], List[str]]:
    """Validate entire features.json structure.

    Returns a tuple of (errors, warnings).
    """
    errors = []
    warnings = []

    if not filepath.exists():
        return [f"File not found: {filepath}"], []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"], []

    if isinstance(data, dict) and "sprints" in data and "plans" not in data:
        errors.append(
            "old format detected (key 'sprints') — re-run /ghs:init to regenerate "
            ".ghs/features.json with the current schema"
        )

    errors.extend(validate_project_section(data))

    plans = data.get("plans", [])
    if not isinstance(plans, list):
        errors.append("'plans' must be an array")
    else:
        for idx, plan in enumerate(plans):
            plan_errors, plan_warnings = validate_plan(plan, idx)
            errors.extend(plan_errors)
            warnings.extend(plan_warnings)

    return errors, warnings


def main():
    force_utf8_stdio()

    parser = argparse.ArgumentParser(
        description="Validate features.json structure and schema"
    )
    parser.add_argument(
        "--project-dir",
        "-p",
        default=".",
        help="Project directory (default: current directory)",
    )
    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()

    features_path = project_dir / ".ghs" / "features.json"

    print("=== Validating features.json ===\n")

    errors, warnings = validate_features_json(features_path)

    if warnings:
        print("⚠️  Warnings:\n")
        for warning in warnings:
            print(f"  • {warning}")
        print()

    if errors:
        print("❌ Validation failed:\n")
        for error in errors:
            print(f"  • {error}")
        return 1
    else:
        print("✅ Validation passed!")
        print("   All required fields present")
        print("   All status values valid")
        print("   All ID formats valid")
        print("   Feature ID prefixes consistent")
        print("   Structure is correct")
        return 0


if __name__ == "__main__":
    sys.exit(main())
