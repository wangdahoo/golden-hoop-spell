#!/usr/bin/env python3
"""Archive completed sprint files to .ghs/archived directory."""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ARCHIVED_DIR = ".ghs/archived"
GHS_DIR = ".ghs"


def get_all_sprints(features_data: Dict) -> List[Dict]:
    """Get all sprints from features.json."""
    return features_data.get("sprints", [])


def get_completed_sprints(features_data: Dict) -> List[Dict]:
    """Get all completed sprints from features.json."""
    sprints = features_data.get("sprints", [])
    return [s for s in sprints if s.get("status") == "completed"]


def get_in_progress_sprint(features_data: Dict) -> Optional[Dict]:
    """Get the current in-progress sprint (if any)."""
    sprints = features_data.get("sprints", [])
    for sprint in sprints:
        if sprint.get("status") in ("in_progress", "planning"):
            return sprint
    return None


def create_archive_structure(project_dir: Path) -> Path:
    """Create the archive directory structure."""
    archived_path = project_dir / ARCHIVED_DIR
    archived_path.mkdir(parents=True, exist_ok=True)
    return archived_path


def archive_sprint_files(
    sprint: Dict, features_data: Dict, project_dir: Path, archived_path: Path
) -> Tuple[Path, Path]:
    """Archive a completed sprint's data.

    Returns:
        Tuple of (archived_features_path, archived_progress_path)
    """
    sprint_id = sprint.get("id", "unknown")
    sprint_name = sprint.get("name", "unnamed").replace(" ", "_").lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    archive_folder = archived_path / f"{sprint_id}_{sprint_name}_{timestamp}"
    archive_folder.mkdir(parents=True, exist_ok=True)

    archive_features = archive_folder / "features.json"
    archive_progress = archive_folder / "progress.md"

    archived_sprint_data = {
        "project": features_data.get("project", {}),
        "archived_sprint": sprint,
        "metadata": {
            "archived_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "original_sprint_id": sprint_id,
        },
    }

    with open(archive_features, "w", encoding="utf-8") as f:
        json.dump(archived_sprint_data, f, indent=2)

    progress_path = project_dir / GHS_DIR / "progress.md"
    if progress_path.exists():
        sessions = extract_sprint_sessions(progress_path, sprint_id)
        if sessions:
            with open(archive_progress, "w", encoding="utf-8") as f:
                f.write(f"# Progress Log - {sprint.get('name', sprint_id)}\n\n")
                f.write(f"Archived: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("---\n\n")
                f.write(sessions)

    return archive_features, archive_progress


def _entry_matches_sprint(entry: str, sprint_id: str) -> bool:
    """Check if a session entry belongs to a given sprint by inspecting only the
    title line and first few metadata lines — NOT the full body text.
    This prevents false positives when a session body mentions another sprint ID.
    """
    lines = entry.strip().split("\n")
    # Check the title line (first line) and up to the next 10 metadata lines
    header_lines = lines[:11]
    header_text = "\n".join(header_lines).lower()
    return sprint_id.lower() in header_text


def _split_entries(content: str) -> List[str]:
    """Split progress.md content by '## ' H2 headings, returning individual entries.
    Strips any leading content before the first H2 heading.
    """
    parts = re.split(r"^## ", content, flags=re.MULTILINE)
    entries = []
    for part in parts[1:]:  # Skip everything before the first H2 heading
        entries.append("## " + part)
    return entries


def extract_sprint_sessions(progress_path: Path, sprint_id: str) -> str:
    """Extract sessions related to a specific sprint from progress.md.

    Splits by all H2 headings (## Session, ## Sprint Planning,
    ## Parallel Orchestration, etc.) and matches sprint_id only in the
    title/metadata lines to avoid false positives from body text.
    """
    with open(progress_path, "r", encoding="utf-8") as f:
        content = f.read()

    entries = _split_entries(content)
    relevant_entries = []

    for entry in entries:
        if _entry_matches_sprint(entry, sprint_id):
            relevant_entries.append(entry)

    return "\n\n".join(relevant_entries)


def remove_archived_sprint(features_data: Dict, sprint_id: str) -> Dict:
    """Remove archived sprint from features.json."""
    sprints = features_data.get("sprints", [])
    features_data["sprints"] = [s for s in sprints if s.get("id") != sprint_id]
    features_data["metadata"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    return features_data


def get_progress_template() -> str:
    """Return the default progress.md template by reading from shared/assets/progress.md."""
    template_path = Path(__file__).parent.parent / "assets" / "progress.md"
    if template_path.exists():
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise FileNotFoundError(f"Progress template not found: {template_path}")


def reset_progress_md(progress_path: Path):
    """Reset progress.md to the default template."""
    with open(progress_path, "w", encoding="utf-8") as f:
        f.write(get_progress_template())


def remove_sprint_sessions(progress_path: Path, sprint_ids: List[str]):
    """Remove sessions belonging to the given sprint IDs from progress.md.

    Keeps all entries that do not match any of the given sprint IDs.
    Matching is done against title/metadata lines only to avoid false positives.
    """
    with open(progress_path, "r", encoding="utf-8") as f:
        content = f.read()

    entries = _split_entries(content)
    # Everything before the first H2 heading is the header
    parts = re.split(r"^## ", content, flags=re.MULTILINE)
    header = parts[0]

    remaining_entries = []

    for entry in entries:
        # Keep entries that don't match any of the archived sprint IDs
        if not any(_entry_matches_sprint(entry, sid) for sid in sprint_ids):
            remaining_entries.append(entry)

    with open(progress_path, "w", encoding="utf-8") as f:
        f.write(header)
        if remaining_entries:
            # Ensure proper separation between header and remaining entries
            if not header.endswith("\n\n"):
                f.write("\n\n" if header.endswith("\n") else "\n\n")
            f.write("\n\n".join(remaining_entries))


def archive_completed_sprints(
    project_dir: Path, dry_run: bool = False, force: bool = False
) -> List[Dict]:
    """Archive completed sprints or all sprints if force=True.

    Args:
        project_dir: Project directory path
        dry_run: If True, show what would be archived without making changes
        force: If True, archive all sprints regardless of status

    Returns:
        List of archived sprint info
    """
    features_path = project_dir / GHS_DIR / "features.json"
    progress_path = project_dir / GHS_DIR / "progress.md"

    if not features_path.exists():
        print("Error: features.json not found")
        return []

    with open(features_path, "r", encoding="utf-8") as f:
        features_data = json.load(f)

    if force:
        sprints_to_archive = get_all_sprints(features_data)
        if sprints_to_archive:
            print(f"Force archiving ALL {len(sprints_to_archive)} sprint(s)\n")
    else:
        sprints_to_archive = get_completed_sprints(features_data)

    if not sprints_to_archive:
        if force:
            print("No sprints found to archive.")
        else:
            print("No completed sprints to archive.")
        return []

    archived_path = create_archive_structure(project_dir)
    archived_info = []

    for sprint in sprints_to_archive:
        sprint_id = sprint.get("id", "unknown")
        sprint_name = sprint.get("name", "unknown")
        sprint_status = sprint.get("status", "unknown")

        print(f"Archiving sprint: {sprint_name} ({sprint_id})")
        print(f"  Status: {sprint_status}")

        if not dry_run:
            feat_path, prog_path = archive_sprint_files(
                sprint, features_data, project_dir, archived_path
            )
            features_data = remove_archived_sprint(features_data, sprint_id)

            print(f"  Created: {feat_path.parent}")
            archived_info.append(
                {
                    "sprint_id": sprint_id,
                    "sprint_name": sprint_name,
                    "sprint_status": sprint_status,
                    "archive_path": str(feat_path.parent),
                }
            )
        else:
            print(f"  [DRY RUN] Would archive to: {archived_path}/{sprint_id}_...")
            archived_info.append(
                {
                    "sprint_id": sprint_id,
                    "sprint_name": sprint_name,
                    "sprint_status": sprint_status,
                    "dry_run": True,
                }
            )

    if not dry_run and archived_info:
        with open(features_path, "w", encoding="utf-8") as f:
            json.dump(features_data, f, indent=2)
        print(
            f"\nUpdated features.json - removed {len(archived_info)} archived sprint(s)"
        )

        remaining_sprints = features_data.get("sprints", [])
        if not remaining_sprints:
            reset_progress_md(progress_path)
            print("Reset progress.md to default template")
        else:
            archived_sprint_ids = [
                info["sprint_id"] for info in archived_info
            ]
            remove_sprint_sessions(progress_path, archived_sprint_ids)
            print(
                f"Removed {len(archived_info)} archived sprint session(s) from progress.md "
                f"({len(remaining_sprints)} sprint(s) remaining)"
            )

    return archived_info


def main():
    parser = argparse.ArgumentParser(
        description="Archive completed sprint files to .ghs/archived"
    )
    parser.add_argument(
        "--project-dir",
        "-p",
        default=".",
        help="Project directory (default: current directory)",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be archived without making changes",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List completed sprints without archiving",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force archive ALL sprints (including incomplete)",
    )

    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()

    print("=== Sprint Archiver ===\n")
    print(f"Project directory: {project_dir}\n")

    if args.list:
        features_path = project_dir / GHS_DIR / "features.json"
        if not features_path.exists():
            print("Error: features.json not found")
            return 1

        with open(features_path, "r", encoding="utf-8") as f:
            features_data = json.load(f)

        if args.force:
            sprints = get_all_sprints(features_data)
            if not sprints:
                print("No sprints found.")
                return 0
            print("All sprints:\n")
        else:
            sprints = get_completed_sprints(features_data)
            if not sprints:
                print("No completed sprints found.")
                return 0
            print("Completed sprints:\n")

        for sprint in sprints:
            features = sprint.get("features", [])
            completed_features = len(
                [f for f in features if f.get("status") == "completed"]
            )
            status = sprint.get("status", "unknown")
            print(
                f"  - {sprint.get('name', 'unknown')} ({sprint.get('id')}) [{status}]"
            )
            print(f"    Features: {completed_features}/{len(features)} completed")
            print(f"    Goal: {sprint.get('goal', 'No goal defined')}")
            print()
        return 0

    archived = archive_completed_sprints(
        project_dir, dry_run=args.dry_run, force=args.force
    )

    if not archived:
        return 0

    print(f"\nArchived {len(archived)} sprint(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
