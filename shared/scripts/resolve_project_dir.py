#!/usr/bin/env python3
"""Resolve the project directory by searching for .ghs/features.json or .ghs/progress.md.

Walks up from the given start directory (or cwd) to find the directory containing
the .ghs project tracking folder. This ensures agents always write to the correct location
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

GHS_DIR = ".ghs"
MARKER_FILES = ["features.json", "progress.md"]


def find_project_dir(start_dir: Path) -> "Path | None":
    """Walk up from start_dir to find the directory containing .ghs/ with marker files.

    Returns None if no marker files are found in any parent directory.
    """
    current = start_dir.resolve()

    while current != current.parent:
        ghs = current / GHS_DIR
        if ghs.is_dir():
            for marker in MARKER_FILES:
                if (ghs / marker).exists():
                    return current

        current = current.parent

    # Check root directory too
    ghs = current / GHS_DIR
    if ghs.is_dir():
        for marker in MARKER_FILES:
            if (ghs / marker).exists():
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
            "Error: No project directory found. No .ghs/features.json or .ghs/progress.md in any parent directory. "
            "Run /ghs:init to create a new project.",
            file=sys.stderr,
        )
        return 1

    print(str(project_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
