#!/usr/bin/env python3
"""Resolve the project directory by searching for features.json or progress.md.

Walks up from the given start directory (or cwd) to find the directory containing
project tracking files. This ensures agents always write to the correct location
regardless of their current working directory.

Usage:
    python3 scripts/resolve_project_dir.py [--start-dir DIR]

Exit codes:
    0 - Project directory found, printed to stdout
    1 - No project directory found
"""

import argparse
import sys
from pathlib import Path

MARKER_FILES = ["features.json", "progress.md"]
WRONG_DIRS = [".ghs", "node_modules", ".git", "__pycache__"]


def find_project_dir(start_dir: Path) -> "Path | None":
    """Walk up from start_dir to find the directory containing marker files.

    Skips known non-project directories like .ghs and node_modules.
    Returns None if no marker files are found in any parent directory.
    """
    current = start_dir.resolve()

    while current != current.parent:
        if current.name in WRONG_DIRS:
            current = current.parent
            continue

        for marker in MARKER_FILES:
            if (current / marker).exists():
                return current

        current = current.parent

    # Check root directory too
    if current.name not in WRONG_DIRS:
        for marker in MARKER_FILES:
            if (current / marker).exists():
                return current

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Resolve the ghs project directory"
    )
    parser.add_argument(
        "--start-dir",
        "-s",
        default=None,
        help="Directory to start searching from (default: current directory)",
    )
    args = parser.parse_args()

    start = Path(args.start_dir) if args.start_dir else Path.cwd()
    project_dir = find_project_dir(start)

    if project_dir is None:
        print(
            "Error: No project directory found. No features.json or progress.md in any parent directory. "
            "Run /ghs:init to create a new project.",
            file=sys.stderr,
        )
        return 1

    print(str(project_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
