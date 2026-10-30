#!/usr/bin/env python3
"""Materialize a plan document's task tail into features.json.

Parses the frozen contract header (## Global Constraints) and the task-card
tail (### Task {N} blocks) from an approved plan document and appends a plan
object with deterministically derived features to .ghs/features.json.

Three-state routing (stdout JSON):
    parsed        -> features written
    no_task_zone  -> no task cards found (caller should use /ghs:to-features)
    malformed     -> task tail violates the serialization contract (caller
                     re-dispatches the designer for a targeted task-tail
                     rewrite; contract header and design body stay frozen)

Usage:
    command python3 tasks_to_features.py --project-dir <PROJECT_DIR> \
        --plan-file <PROJECT_DIR>/docs/ghs/plans/{plan_file}

Exit codes: 0 parsed; 1 no_task_zone / malformed; 2 IO or argument errors.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from ghs_compat import force_utf8_stdio

TASK_HEADING_RE = re.compile(r"^### Task (\d+): (.+)$", re.MULTILINE)
PLAN_NUM_RE = re.compile(r"^p(\d+)$")
SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)

# Path heuristics, checked in order; first hit wins, else "core".
CATEGORY_RULES = [
    ("ui/", "ui"),
    ("api/", "api"),
    ("auth/", "auth"),
    ("data/", "data"),
    ("infra/", "infra"),
]

MAX_ANCHORS = 5
NAME_MAX_CHARS = 40

# Spec §5 P2 bans empty judgements outright; these are the named offenders.
EMPTY_CRITERION_RE = re.compile(
    r"^(works correctly|works fine|测试通过|测试正常|passes|ok|通过)$",
    re.IGNORECASE,
)


def extract_section(text: str, title: str) -> str:
    """Return the body of a `## {title}` section (until the next `## ` heading)."""
    match = re.search(rf"^## {re.escape(title)}\s*$", text, re.MULTILINE)
    if not match:
        return ""
    rest = text[match.end():]
    next_heading = re.search(r"^## ", rest, re.MULTILINE)
    return (rest[: next_heading.start()] if next_heading else rest).strip()


def extract_global_constraints(plan_text: str) -> list:
    """Verbatim lines of the contract header's Global Constraints (bullet marker stripped)."""
    body = extract_section(plan_text, "Global Constraints")
    # Task cards are H3, so a light-lane plan (no design body) never closes the
    # section with another `## ` heading — stop at the first `### ` instead.
    body = re.split(r"^### ", body, maxsplit=1, flags=re.MULTILINE)[0]
    return [
        re.sub(r"^-\s+", "", l).strip()
        for l in body.splitlines()
        if l.strip()
    ]


def derive_plan_name(plan_text: str) -> str:
    """First sentence of ## Intent, truncated to NAME_MAX_CHARS."""
    body = extract_section(plan_text, "Intent")
    first_line = next((l.strip() for l in body.splitlines() if l.strip()), "")
    # CJK terminators split unconditionally; ASCII ones only at whitespace/EOL,
    # so dots inside identifiers ("session.refresh()") and versions ("v1.2") survive.
    sentence = re.split(r"[。？！]|[.!?](?:\s+|$)", first_line, maxsplit=1)[0].strip()
    return sentence[:NAME_MAX_CHARS]


def parse_anchor_line(line: str) -> str:
    """Normalize one `- {subject}: {criterion}` / `- [UNDEFINED-INPUT] ...` line."""
    return line.strip()[2:].strip()  # strip leading "- "


def parse_task_cards(plan_text: str):
    """Parse the task tail. Returns (cards, error_reason).

    A card is a dict with keys: number, title, files (list), interfaces (str),
    points (str), anchors (list of verbatim strings).
    """
    matches = list(TASK_HEADING_RE.finditer(plan_text))
    if not matches:
        return None, "no task zone: no `### Task {N}:` headings found"
    # The task tail must be the LAST zone: no `## ` section heading after the first card.
    first = matches[0]
    if re.search(r"^## ", plan_text[first.end():], re.MULTILINE):
        return None, "malformed: a `## ` section heading appears after the task tail"

    cards = []
    for idx, match in enumerate(matches):
        if int(match.group(1)) != idx + 1:
            return None, f"malformed: task numbers must be sequential from 1 (got Task {match.group(1)} at position {idx + 1})"
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(plan_text)
        body = plan_text[match.end():end]

        files_m = re.search(r"^- Files:[ \t]*(.+)$", body, re.MULTILINE)
        points_m = re.search(r"^- Points:[ \t]*(.*?)(?=^- Anchors:|\Z)", body, re.MULTILINE | re.DOTALL)
        interfaces_m = re.search(r"^- Interfaces:[ \t]*(.*?)(?=^- Points:|^- Anchors:|\Z)", body, re.MULTILINE | re.DOTALL)
        anchors_m = re.search(r"^- Anchors:[ \t]*\n((?:^[ \t]*- .+$\n?)*)", body, re.MULTILINE)

        if not files_m:
            return None, f"malformed: Task {idx + 1} missing '- Files:'"
        if not points_m or not points_m.group(1).strip():
            return None, f"malformed: Task {idx + 1} missing '- Points:'"
        if not anchors_m:
            return None, f"malformed: Task {idx + 1} missing '- Anchors:'"

        files = [f.strip() for f in files_m.group(1).split(",") if f.strip()]
        if not files:
            return None, f"malformed: Task {idx + 1} has an empty Files list"

        anchors = [parse_anchor_line(l) for l in anchors_m.group(1).strip().splitlines() if l.strip()]
        if not (1 <= len(anchors) <= MAX_ANCHORS):
            return None, f"malformed: Task {idx + 1} has {len(anchors)} anchors (must be 1-{MAX_ANCHORS}); splitting the task is the fix"
        for anchor in anchors:
            if anchor.startswith("[UNDEFINED-INPUT]"):
                if ":" not in anchor:
                    return None, f"malformed: Task {idx + 1} UNDEFINED-INPUT anchor without criterion: {anchor!r}"
                continue
            criterion = anchor.split(":", 1)[1].strip() if ":" in anchor else ""
            # Trailing punctuation must not launder a banned empty judgement.
            if not criterion or EMPTY_CRITERION_RE.match(criterion.rstrip("。？！.!?…")):
                return None, f"malformed: Task {idx + 1} anchor with an empty judgement (forbidden per spec): {anchor!r}"

        cards.append({
            "number": idx + 1,
            "title": match.group(2).strip(),
            "files": files,
            "interfaces": interfaces_m.group(1).strip() if interfaces_m else "",
            "points": points_m.group(1).strip(),
            "anchors": anchors,
        })
    return cards, None


def derive_category(files: list) -> str:
    # Rule order wins over file order: a task touching ui/ and api/ is ui.
    for needle, category in CATEGORY_RULES:
        for path in files:
            if needle in path:
                return category
    return "core"


def build_features(cards: list, constraints: list, plan_id: str) -> list:
    features = []
    prev_id = None
    for i, card in enumerate(cards, start=1):
        fid = f"{plan_id}-feat-{i:03d}"
        notes = card["interfaces"]
        if notes:
            notes += "\n\n"
        notes += "参考 plan 文档（plan_ref）的 Design 节获取设计决定与理由。"
        features.append({
            "id": fid,
            "category": derive_category(card["files"]),
            "priority": "medium",
            "title": card["title"],
            "description": card["points"],
            "acceptance_criteria": list(constraints) + list(card["anchors"]),
            "technical_notes": notes,
            "status": "pending",
            "dependencies": [prev_id] if prev_id else [],
            "estimated_complexity": "medium",
            "files_affected": card["files"],
        })
        prev_id = fid
    return features


def emit(payload: dict, exit_code: int) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def main() -> int:
    force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Materialize a plan document's task tail into features.json"
    )
    parser.add_argument("--project-dir", "-p", required=True)
    parser.add_argument("--plan-file", required=True,
                        help="Approved plan file under docs/ghs/plans/")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    plan_file = Path(args.plan_file).resolve()
    features_path = project_dir / ".ghs" / "features.json"

    if not plan_file.exists():
        print(f"tasks_to_features: error: plan file not found: {plan_file}", file=sys.stderr)
        return 2
    if not features_path.exists():
        print(f"tasks_to_features: error: features.json not found at {features_path}", file=sys.stderr)
        return 2

    try:
        plan_ref = plan_file.relative_to(project_dir).as_posix()
    except ValueError:
        print(f"tasks_to_features: error: plan file is outside project dir: {plan_file}", file=sys.stderr)
        return 2

    plan_text = plan_file.read_text(encoding="utf-8")
    constraints = extract_global_constraints(plan_text)
    cards, reason = parse_task_cards(plan_text)
    if cards is None:
        if reason.startswith("no task zone"):
            return emit({"status": "no_task_zone", "reason": reason}, 1)
        return emit({"status": "malformed", "reason": reason}, 1)

    try:
        with open(features_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"tasks_to_features: error: cannot read features.json: {e}", file=sys.stderr)
        return 2

    numbers = [
        int(m.group(1))
        for p in data.get("plans", [])
        for m in [PLAN_NUM_RE.match(str(p.get("id", "")))]
        if m
    ]
    plan_number = (max(numbers) + 1) if numbers else 1
    plan_id = f"p{plan_number}"

    plan_obj = {
        "id": plan_id,
        "name": derive_plan_name(plan_text),
        "status": "in_progress",
        "plan_ref": plan_ref,
        "created_at": datetime.now().strftime("%Y-%m-%d"),
        "features": build_features(cards, constraints, plan_id),
    }

    data.setdefault("plans", []).append(plan_obj)
    data.setdefault("metadata", {})["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    with open(features_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return emit({
        "status": "parsed",
        "plan_id": plan_id,
        "feature_ids": [feat["id"] for feat in plan_obj["features"]],
    }, 0)


if __name__ == "__main__":
    sys.exit(main())
