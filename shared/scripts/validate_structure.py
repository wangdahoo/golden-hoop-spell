#!/usr/bin/env python3
"""Validate features.json structure and schema."""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any


def validate_project_section(data: Dict) -> List[str]:
    """Validate project section."""
    errors = []
    project = data.get("project", {})

    required_fields = ["name", "description", "created_at"]
    for field in required_fields:
        if field not in project:
            errors.append(f"Missing project.{field}")

    return errors


def validate_feature(feature: Dict, feature_idx: int) -> List[str]:
    """Validate a single feature."""
    errors = []

    required_fields = ["id", "title", "description", "status"]
    for field in required_fields:
        if field not in feature:
            errors.append(f"Feature {feature_idx}: missing '{field}'")

    valid_statuses = ["pending", "in_progress", "completed", "blocked"]
    status = feature.get("status", "")
    if status and status not in valid_statuses:
        errors.append(f"Feature {feature_idx}: invalid status '{status}'")

    valid_priorities = ["high", "medium", "low"]
    priority = feature.get("priority", "")
    if priority and priority not in valid_priorities:
        errors.append(f"Feature {feature_idx}: invalid priority '{priority}'")

    valid_categories = ["core", "ui", "api", "auth", "data", "infra"]
    category = feature.get("category", "")
    if category and category not in valid_categories:
        errors.append(f"Feature {feature_idx}: invalid category '{category}'")

    return errors


def validate_sprint(sprint: Dict, sprint_idx: int) -> List[str]:
    """Validate a single sprint."""
    errors = []

    required_fields = ["id", "name", "status"]
    for field in required_fields:
        if field not in sprint:
            errors.append(f"Sprint {sprint_idx}: missing '{field}'")

    valid_statuses = ["planning", "in_progress", "completed", "on_hold"]
    status = sprint.get("status", "")
    if status and status not in valid_statuses:
        errors.append(f"Sprint {sprint_idx}: invalid status '{status}'")

    features = sprint.get("features", [])
    if not isinstance(features, list):
        errors.append(f"Sprint {sprint_idx}: 'features' must be an array")
    else:
        for idx, feature in enumerate(features):
            errors.extend(validate_feature(feature, idx))

    return errors


def validate_features_json(filepath: Path) -> List[str]:
    """Validate entire features.json structure."""
    errors = []

    if not filepath.exists():
        return [f"File not found: {filepath}"]

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    errors.extend(validate_project_section(data))

    sprints = data.get("sprints", [])
    if not isinstance(sprints, list):
        errors.append("'sprints' must be an array")
    else:
        for idx, sprint in enumerate(sprints):
            errors.extend(validate_sprint(sprint, idx))

    return errors


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

    features_path = project_dir / "features.json"

    print("=== Validating features.json ===\n")

    errors = validate_features_json(features_path)

    if errors:
        print("❌ Validation failed:\n")
        for error in errors:
            print(f"  • {error}")
        return 1
    else:
        print("✅ Validation passed!")
        print("   All required fields present")
        print("   All status values valid")
        print("   Structure is correct")
        return 0


if __name__ == "__main__":
    sys.exit(main())
