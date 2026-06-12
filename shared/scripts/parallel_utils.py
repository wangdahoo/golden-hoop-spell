#!/usr/bin/env python3
"""Parallel feature batching utilities for ghs:code parallel mode.

Reads features.json, identifies ready features (all dependencies met),
detects circular dependencies, and builds conflict-free batches for
parallel execution. Outputs JSON to stdout — stateless and deterministic.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple


def read_features_json(filepath: Path) -> Optional[Dict]:
    """Read and parse features.json."""
    if not filepath.exists():
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def detect_cycles(
    features: List[Dict], feature_index: Dict[str, Dict]
) -> List[List[str]]:
    """Detect circular dependencies in the feature dependency graph.

    Uses iterative DFS with white/gray/black coloring to find all cycles.
    Returns a list of cycles, where each cycle is a list of feature IDs
    forming the loop.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {}
    cycles = []
    path = []
    path_set = set()

    def dfs(node: str) -> None:
        color[node] = GRAY
        path.append(node)
        path_set.add(node)

        feat = feature_index.get(node, {})
        for dep in feat.get("dependencies", []):
            if dep not in feature_index:
                continue
            if color.get(dep) == GRAY:
                # Found a cycle — extract it from the path
                cycle_start = path.index(dep)
                cycles.append(path[cycle_start:])
            elif color.get(dep, WHITE) == WHITE:
                dfs(dep)

        path.pop()
        path_set.discard(node)
        color[node] = BLACK

    for feat in features:
        fid = feat.get("id", "")
        if color.get(fid, WHITE) == WHITE:
            dfs(fid)

    return cycles


def get_ready_features(
    features_data: Dict, sprint_id: Optional[str] = None
) -> Tuple[List[Dict], List[Dict], List[List[str]], List[str]]:
    """Identify features whose dependencies are all completed.

    Args:
        features_data: Parsed features.json content.
        sprint_id: Optional sprint ID to filter by. If None, uses the
                   first active sprint found.

    Returns:
        Tuple of:
        - ready_features: List of feature dicts with all deps completed.
        - skipped: List of feature dicts that are not ready (deps unmet,
                   wrong status, or blocked by cycles).
        - cycles: List of detected circular dependency chains.
        - cycle_feature_ids: Set of feature IDs involved in any cycle.
    """
    sprints = features_data.get("sprints", [])
    sprint = None

    if sprint_id:
        for s in sprints:
            if s.get("id") == sprint_id:
                sprint = s
                break
    else:
        # Use the first in_progress sprint, or the first sprint
        for s in sprints:
            if s.get("status") == "in_progress":
                sprint = s
                break
        if sprint is None and sprints:
            sprint = sprints[0]

    if sprint is None:
        return [], [], [], []

    features = sprint.get("features", [])

    # Build index and completed set
    feature_index = {f.get("id", ""): f for f in features if f.get("id")}
    completed_ids = {
        f.get("id") for f in features if f.get("status") == "completed"
    }

    # Detect cycles
    cycles = detect_cycles(features, feature_index)
    cycle_feature_ids = set()
    for cycle in cycles:
        cycle_feature_ids.update(cycle)

    ready = []
    skipped = []

    for feat in features:
        fid = feat.get("id", "")
        status = feat.get("status", "")

        # Only pending features can be ready
        if status != "pending":
            skipped.append(feat)
            continue

        # Skip features involved in dependency cycles
        if fid in cycle_feature_ids:
            skipped.append(feat)
            continue

        # Check all dependencies are completed
        deps = feat.get("dependencies", [])
        deps_met = all(
            dep_id in completed_ids or
            (dep_id not in feature_index and dep_id in completed_ids)
            for dep_id in deps
        )

        if deps_met:
            ready.append(feat)
        else:
            skipped.append(feat)

    return ready, skipped, cycles, list(cycle_feature_ids)


def build_parallel_batches(
    ready_features: List[Dict], max_parallel: int = 5
) -> List[List[Dict]]:
    """Group non-conflicting ready features into parallel batches.

    Uses a file-overlap-descending sort heuristic: features that touch
    more files are placed first, which tends to spread conflicting
    features across batches more effectively.

    Features with overlapping files_affected are never placed in the
    same batch to avoid merge conflicts during parallel execution.

    Args:
        ready_features: Features with all dependencies met.
        max_parallel: Maximum features per batch.

    Returns:
        List of batches, where each batch is a list of feature dicts.
    """
    if not ready_features:
        return []

    # Sort by number of files_affected descending (heuristic for better
    # batching — high-overlap features get placed first and spread out)
    sorted_features = sorted(
        ready_features,
        key=lambda f: len(f.get("files_affected", [])),
        reverse=True,
    )

    batches = []
    assigned = set()

    for feat in sorted_features:
        fid = feat.get("id", "")
        if fid in assigned:
            continue

        feat_files = set(feat.get("files_affected", []))

        # Try to place in an existing batch
        placed = False
        for batch in batches:
            if len(batch) >= max_parallel:
                continue

            # Check for file conflicts with features already in batch
            has_conflict = False
            for existing in batch:
                existing_files = set(existing.get("files_affected", []))
                if feat_files & existing_files:
                    has_conflict = True
                    break

            if not has_conflict:
                batch.append(feat)
                assigned.add(fid)
                placed = True
                break

        # If no existing batch fits, start a new one
        if not placed:
            batches.append([feat])
            assigned.add(fid)

    return batches


def main():
    parser = argparse.ArgumentParser(
        description="Identify ready features and build parallel batches "
                    "from features.json"
    )
    parser.add_argument(
        "--project-dir",
        "-p",
        default=".",
        help="Project directory (default: current directory)",
    )
    parser.add_argument(
        "--max-parallel",
        "-m",
        type=int,
        default=5,
        help="Maximum features per batch (default: 5)",
    )
    parser.add_argument(
        "--sprint-id",
        "-s",
        default=None,
        help="Sprint ID to analyze (default: first active sprint)",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    features_path = project_dir / ".ghs" / "features.json"

    if not features_path.exists():
        json.dump(
            {
                "error": f"features.json not found at {features_path}",
                "ready_features": [],
                "batches": [],
                "skipped": [],
                "cycles": [],
                "cycle_feature_ids": [],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 1

    try:
        features_data = read_features_json(features_path)
    except json.JSONDecodeError as e:
        json.dump(
            {
                "error": f"Invalid JSON in features.json: {e}",
                "ready_features": [],
                "batches": [],
                "skipped": [],
                "cycles": [],
                "cycle_feature_ids": [],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 1

    if features_data is None:
        json.dump(
            {
                "error": "Could not read features.json",
                "ready_features": [],
                "batches": [],
                "skipped": [],
                "cycles": [],
                "cycle_feature_ids": [],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 1

    ready, skipped, cycles, cycle_feature_ids = get_ready_features(
        features_data, sprint_id=args.sprint_id
    )

    batches = build_parallel_batches(ready, max_parallel=args.max_parallel)

    # Format output — feature summaries instead of full feature dicts
    def summarize_feature(feat: Dict) -> Dict:
        return {
            "id": feat.get("id", ""),
            "title": feat.get("title", ""),
            "status": feat.get("status", ""),
            "files_affected": feat.get("files_affected", []),
            "dependencies": feat.get("dependencies", []),
        }

    output = {
        "ready_features": [summarize_feature(f) for f in ready],
        "batches": [
            [summarize_feature(f) for f in batch] for batch in batches
        ],
        "skipped": [summarize_feature(f) for f in skipped],
        "cycles": cycles,
        "cycle_feature_ids": cycle_feature_ids,
    }

    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
