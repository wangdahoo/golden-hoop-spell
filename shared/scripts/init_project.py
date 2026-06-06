#!/usr/bin/env python3
"""Initialize agent-harness tracking files for a project."""

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path


def create_features_json(project_name: str, project_description: str, output_dir: Path):
    """Create features.json from template."""
    template_path = Path(__file__).parent.parent / "assets" / "features.json"

    if template_path.exists():
        with open(template_path, "r", encoding="utf-8") as f:
            features_data = json.load(f)

        features_data["project"]["name"] = project_name
        features_data["project"]["description"] = project_description
        features_data["project"]["created_at"] = datetime.now().strftime("%Y-%m-%d")
        features_data["metadata"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")

        output_file = output_dir / "features.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(features_data, f, indent=2)

        return output_file
    else:
        raise FileNotFoundError(f"Template not found: {template_path}")


def ensure_gitignore(output_dir: Path):
    """Add .agent-harness to .gitignore if not already present."""
    gitignore_path = output_dir / ".gitignore"
    entry = ".agent-harness"

    if gitignore_path.exists():
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()
        lines = [line.strip() for line in content.splitlines()]
        if entry in lines:
            return gitignore_path, False
        with open(gitignore_path, "a", encoding="utf-8") as f:
            if content and not content.endswith("\n"):
                f.write("\n")
            f.write(f"{entry}\n")
        return gitignore_path, True
    else:
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(f"{entry}\n")
        return gitignore_path, True


def create_progress_md(output_dir: Path):
    """Create progress.md from template."""
    template_path = Path(__file__).parent.parent / "assets" / "progress.md"

    if template_path.exists():
        output_file = output_dir / "progress.md"
        shutil.copy(template_path, output_file)
        return output_file
    else:
        raise FileNotFoundError(f"Template not found: {template_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Initialize agent-harness tracking files"
    )
    parser.add_argument("project_name", help="Name of the project")
    parser.add_argument(
        "--description", "-d", default="", help="Project description (optional)"
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default=".",
        help="Output directory (default: current directory). Alias: --project-dir",
    )
    parser.add_argument(
        "--project-dir",
        "-p",
        default=None,
        help="Project directory (default: current directory). Alias for --output-dir",
    )

    args = parser.parse_args()

    output_dir = Path(args.project_dir or args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    project_description = args.description or f"{args.project_name} project"

    print(f"=== Initializing Agent Harness ===")
    print(f"Project: {args.project_name}")
    print(f"Output: {output_dir}")
    print()

    try:
        features_file = create_features_json(
            args.project_name, project_description, output_dir
        )
        print(f"✓ Created {features_file.name}")

        progress_file = create_progress_md(output_dir)
        print(f"✓ Created {progress_file.name}")

        gitignore_file, updated = ensure_gitignore(output_dir)
        if updated:
            print(f"✓ Updated {gitignore_file.name} (added .agent-harness)")
        else:
            print(f"  {gitignore_file.name} already contains .agent-harness")

        print()
        print("Next: Run Sprint Agent to define features.")

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
