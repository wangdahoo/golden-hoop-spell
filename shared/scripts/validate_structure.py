#!/usr/bin/env python3
"""Validate features.json structure and schema."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple

# ID format patterns
SPRINT_ID_PATTERN = re.compile(r"^s\d{1,4}$")
FEATURE_ID_PATTERN = re.compile(r"^s\d{1,4}-feat-\d{3}$")


def validate_project_section(data: Dict) -> List[str]:
    """Validate project section."""
    errors = []
    project = data.get("project", {})

    required_fields = ["name", "description", "created_at"]
    for field in required_fields:
        if field not in project:
            errors.append(f"Missing project.{field}")

    return errors


def validate_sprint_id_format(sprint_id: str, sprint_idx: int) -> List[str]:
    """Validate sprint ID matches the required format ^s\\d{1,4}$."""
    errors = []
    if not SPRINT_ID_PATTERN.match(sprint_id):
        errors.append(
            f"Sprint {sprint_idx}: invalid sprint ID format '{sprint_id}' "
            f"(must match ^s\\d{{1,4}}$, e.g. s1, s12, s1234)"
        )
    return errors


def validate_feature_id_format(feature_id: str, feature_idx: int) -> List[str]:
    """Validate feature ID matches the required format ^s\\d{1,4}-feat-\\d{3}$."""
    errors = []
    if not FEATURE_ID_PATTERN.match(feature_id):
        errors.append(
            f"Feature {feature_idx}: invalid feature ID format '{feature_id}' "
            f"(must match ^s\\d{{1,4}}-feat-\\d{{3}}$, e.g. s1-feat-001)"
        )
    return errors


def validate_feature_prefix_consistency(
    feature_id: str, sprint_id: str, feature_idx: int
) -> List[str]:
    """Validate that the sprint number prefix in feature ID matches parent sprint ID."""
    errors = []
    sprint_match = SPRINT_ID_PATTERN.match(sprint_id)
    feature_match = FEATURE_ID_PATTERN.match(feature_id)
    if sprint_match and feature_match:
        sprint_num = sprint_id[1:]  # strip leading 's'
        feature_prefix = feature_id.split("-feat-")[0][1:]  # get number before '-feat-'
        if sprint_num != feature_prefix:
            errors.append(
                f"Feature {feature_idx}: feature ID '{feature_id}' prefix "
                f"does not match parent sprint '{sprint_id}' "
                f"(sprint number {sprint_num} vs feature prefix {feature_prefix})"
            )
    return errors


def validate_feature(feature: Dict, feature_idx: int, sprint_id: str = "") -> Tuple[List[str], List[str]]:
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

    # Feature ID prefix consistency with parent sprint
    if feature_id and sprint_id:
        errors.extend(
            validate_feature_prefix_consistency(feature_id, sprint_id, feature_idx)
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


def validate_sprint(sprint: Dict, sprint_idx: int) -> Tuple[List[str], List[str]]:
    """Validate a single sprint.

    Returns a tuple of (errors, warnings).
    """
    errors = []
    warnings = []

    required_fields = ["id", "name", "status"]
    for field in required_fields:
        if field not in sprint:
            errors.append(f"Sprint {sprint_idx}: missing '{field}'")

    # Sprint ID format validation
    sprint_id = sprint.get("id", "")
    if sprint_id:
        errors.extend(validate_sprint_id_format(sprint_id, sprint_idx))

    valid_statuses = ["planning", "in_progress", "completed", "on_hold"]
    status = sprint.get("status", "")
    if status and status not in valid_statuses:
        errors.append(f"Sprint {sprint_idx}: invalid status '{status}'")

    features = sprint.get("features", [])
    if not isinstance(features, list):
        errors.append(f"Sprint {sprint_idx}: 'features' must be an array")
    else:
        for idx, feature in enumerate(features):
            feat_errors, feat_warnings = validate_feature(feature, idx, sprint_id)
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

    errors.extend(validate_project_section(data))

    sprints = data.get("sprints", [])
    if not isinstance(sprints, list):
        errors.append("'sprints' must be an array")
    else:
        for idx, sprint in enumerate(sprints):
            sprint_errors, sprint_warnings = validate_sprint(sprint, idx)
            errors.extend(sprint_errors)
            warnings.extend(sprint_warnings)

    return errors, warnings


def main():
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
