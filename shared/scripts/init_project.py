#!/usr/bin/env python3
"""Initialize ghs tracking files for a project."""

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

        output_file = output_dir / ".ghs" / "features.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(features_data, f, indent=2)

        return output_file
    else:
        raise FileNotFoundError(f"Template not found: {template_path}")


def ensure_gitignore(output_dir: Path):
    """Add .ghs to .gitignore if not already present."""
    gitignore_path = output_dir / ".gitignore"
    entry = ".ghs"

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
        ghs_dir = output_dir / ".ghs"
        ghs_dir.mkdir(parents=True, exist_ok=True)
        output_file = ghs_dir / "progress.md"
        shutil.copy(template_path, output_file)
        return output_file
    else:
        raise FileNotFoundError(f"Template not found: {template_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Initialize ghs tracking files"
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
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force overwrite of existing .ghs tracking files",
    )

    args = parser.parse_args()

    output_dir = Path(args.project_dir or args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    project_description = args.description or f"{args.project_name} project"

    # Check for existing .ghs files unless --force is passed
    if not args.force:
        existing_files = []
        features_path = output_dir / ".ghs" / "features.json"
        progress_path = output_dir / ".ghs" / "progress.md"
        if features_path.exists():
            existing_files.append(str(features_path.relative_to(output_dir)))
        if progress_path.exists():
            existing_files.append(str(progress_path.relative_to(output_dir)))
        if existing_files:
            print("Error: The following .ghs files already exist:")
            for f in existing_files:
                print(f"  - {f}")
            print("Use --force to overwrite existing files.")
            return 1

    print(f"=== Initializing GHS ===")
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
            print(f"✓ Updated {gitignore_file.name} (added .ghs)")
        else:
            print(f"  {gitignore_file.name} already contains .ghs")

        print()
        print("Next: Run Sprint Agent to define features.")

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
