#!/usr/bin/env python3
"""Display current project status from features.json and progress.md."""

import argparse
import json
from pathlib import Path


def read_features_json(filepath: Path):
    """Read and parse features.json."""
    if not filepath.exists():
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def read_progress_md(filepath: Path, last_n=5):
    """Read last N sessions from progress.md."""
    if not filepath.exists():
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    sessions = content.split("## Session")
    return sessions[1 : last_n + 1] if len(sessions) > 1 else []


def format_feature_status(features):
    """Format feature status summary."""
    status_counts = {"pending": 0, "in_progress": 0, "completed": 0, "blocked": 0}

    for feature in features:
        status = feature.get("status", "pending")
        status_counts[status] = status_counts.get(status, 0) + 1

    return status_counts


def main():
    parser = argparse.ArgumentParser(description="Display current project status")
    parser.add_argument(
        "--project-dir",
        "-p",
        default=".",
        help="Project directory (default: current directory)",
    )
    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()

    features_path = project_dir / "features.json"
    progress_path = project_dir / "progress.md"

    if not features_path.exists():
        print("❌ features.json not found. Run init-project.py first.")
        return 1

    print("=== Project Status ===\n")

    features_data = read_features_json(features_path)

    if features_data:
        project = features_data.get("project", {})
        print(f"📦 Project: {project.get('name', 'Unknown')}")
        print(f"📝 Description: {project.get('description', 'No description')}")
        print(f"📅 Created: {project.get('created_at', 'Unknown')}")
        print()

        sprints = features_data.get("sprints", [])

        if not sprints:
            print("⚠️  No sprints defined yet. Run Sprint Agent to plan features.")
            return 0

        for sprint in sprints:
            sprint_id = sprint.get("id", "unknown")
            sprint_name = sprint.get("name", "Unnamed Sprint")
            sprint_status = sprint.get("status", "planning")
            features = sprint.get("features", [])

            status_emoji = {
                "planning": "📋",
                "in_progress": "🚀",
                "completed": "✅",
                "on_hold": "⏸️",
            }.get(sprint_status, "❓")

            print(f"{status_emoji} Sprint: {sprint_name} ({sprint_id})")
            print(f"   Status: {sprint_status}")
            print(f"   Goal: {sprint.get('goal', 'No goal defined')}")
            print()

            status_counts = format_feature_status(features)

            print(f"   Features:")
            print(f"     ✅ Completed:    {status_counts['completed']}")
            print(f"     🚧 In Progress:  {status_counts['in_progress']}")
            print(f"     ⏳ Pending:      {status_counts['pending']}")
            print(f"     🚫 Blocked:      {status_counts['blocked']}")
            print(f"     ━━━━━━━━━━━━━━━━━━━━")
            print(f"     📊 Total:        {len(features)}")
            print()

            if status_counts["in_progress"] > 0:
                in_progress = [f for f in features if f.get("status") == "in_progress"]
                for feat in in_progress:
                    print(
                        f"   🔨 Working on: {feat.get('title', 'Unknown')} ({feat.get('id', '')})"
                    )

            if status_counts["pending"] > 0:
                pending = [f for f in features if f.get("status") == "pending"]
                if pending:
                    next_feature = pending[0]
                    print(
                        f"   ▶️  Next up: {next_feature.get('title', 'Unknown')} ({next_feature.get('id', '')})"
                    )

            print()

    sessions = read_progress_md(progress_path)
    if sessions:
        print("📜 Recent Sessions:")
        for session in sessions[:3]:
            lines = session.strip().split("\n")[:3]
            for line in lines:
                if line.strip():
                    print(f"   {line.strip()}")
        print()

    return 0


if __name__ == "__main__":
    exit(main())
