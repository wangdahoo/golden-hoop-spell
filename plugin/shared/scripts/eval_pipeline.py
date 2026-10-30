#!/usr/bin/env python3
"""Read-only lifecycle audit for a ghs-managed project.

This module will gain the benchmark runner in later tasks; the audit engine is
deliberately standalone so its report schema and exit contract stay stable.

Usage:
    command python3 eval_pipeline.py audit --project-dir <PROJECT_DIR>
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from ghs_compat import force_utf8_stdio

PLAN_ID_RE = re.compile(r"^p\d{1,4}$")
FEATURE_ID_RE = re.compile(r"^(p\d{1,4})-feat-\d{3}$")
CONTRACT_HEADER = "> SCOPE CONTRACT — frozen at kickoff."
REVIEW_SIGNAL_RE = re.compile(
    r"REVIEW COMPLETE\s*\|.*Verdict:\s*(PASS|FAIL)", re.IGNORECASE
)
VALID_FEATURE_STATUSES = {"pending", "in_progress", "completed", "blocked"}
VALID_PLAN_STATUSES = {"planning", "in_progress", "completed", "on_hold"}
TERMINAL_PLAN_STATUSES = {"approved", "aborted", "completed"}


def _read_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "file not found"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"cannot read JSON: {exc}"


def _check(
    check_id: str,
    passed: bool,
    message: str,
    *,
    severity: str = "error",
    plan_id: str | None = None,
    feature_id: str | None = None,
) -> dict:
    item = {
        "id": check_id,
        "severity": severity,
        "passed": passed,
        "message": message,
    }
    if plan_id is not None:
        item["plan_id"] = plan_id
    if feature_id is not None:
        item["feature_id"] = feature_id
    return item


def _snapshot(project_dir: Path) -> dict[str, tuple[int, int]]:
    """Capture path, size, and mtime for every regular audit-visible file."""
    result: dict[str, tuple[int, int]] = {}
    watched = [project_dir / ".ghs", project_dir / "docs" / "ghs" / "plans"]
    for root in watched:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            try:
                if not path.is_file():
                    continue
                stat = path.stat()
            except OSError:
                continue
            result[path.relative_to(project_dir).as_posix()] = (
                stat.st_size,
                stat.st_mtime_ns,
            )
    return result


def _load_trackers(project_dir: Path) -> tuple[dict | None, list[Path]]:
    active, error = _read_json(project_dir / ".ghs" / "features.json")
    if error:
        return None, []
    archive_dir = project_dir / ".ghs" / "archived"
    archived: list[Path] = []
    if archive_dir.is_dir():
        archived = sorted(archive_dir.glob("**/features.json"))
    return active, archived


def _plan_for_status(
    status: dict, plan_file: str, active: dict | None, archived: list[Path]
) -> tuple[str, dict | None, Path | None]:
    basename = Path(plan_file).name
    trackers: list[tuple[dict, Path]] = []
    if isinstance(active, dict):
        trackers.extend(
            (plan, Path(".ghs/features.json")) for plan in active.get("plans", [])
            if Path(str(plan.get("plan_ref", ""))).name == basename
        )
    for path in archived:
        data, _ = _read_json(path)
        if isinstance(data, dict) and isinstance(data.get("archived_plan"), dict):
            plan = data["archived_plan"]
            if Path(str(plan.get("plan_ref", ""))).name == basename:
                trackers.append((plan, path))
    if trackers:
        plan, path = trackers[0]
        return str(plan.get("id", "")), plan, path
    # A status file has no embedded plan id. Fall back to the filename prefix
    # only for reports where no tracker can be located.
    match = re.match(r"(p\d{1,4})-", basename)
    return match.group(1) if match else "", None, None


def _review_is_pass(text: str) -> tuple[bool, str]:
    match = REVIEW_SIGNAL_RE.search(text)
    if not match:
        return False, "review completion signal is missing or invalid"
    verdict = match.group(1).upper()
    if verdict != "PASS":
        return False, "review verdict is FAIL"
    required = {"Unwarranted": "0", "Severe": "0", "Medium": "0"}
    for label, expected in required.items():
        count_match = re.search(
            rf"{label}:\s*(\d+)", text[match.end():], re.IGNORECASE
        )
        if not count_match or count_match.group(1) != expected:
            return False, f"PASS review has a nonzero or missing {label} count"
    return True, "review signal is PASS with zero blocking findings"


def _audit_plans(project_dir: Path, active: dict | None, archived: list[Path]) -> list:
    checks: list = []
    plans_dir = project_dir / ".ghs" / "plans"
    candidates: list[dict] = []
    seen: set[str] = set()
    if plans_dir.is_dir():
        for status_path in sorted(plans_dir.glob("*-status.json")):
            data, error = _read_json(status_path)
            if error or not isinstance(data, dict):
                candidates.append({
                    "plan_id": status_path.stem,
                    "status": "",
                    "lane": "full",
                    "plan_file": "",
                    "accepted_with_fail": False,
                })
                checks.append(_check(
                    "plan-status-readable", False,
                    f"{status_path.name}: {error}", plan_id=status_path.stem,
                ))
                continue
            plan_file = str(data.get("plan_file", ""))
            if not plan_file:
                plan_id = status_path.stem
                checks.append(_check(
                    "plan-status-plan-file", False, "missing plan_file",
                    plan_id=plan_id,
                ))
                continue
            plan_id, plan, _ = _plan_for_status(
                data, plan_file, active, archived
            )
            candidates.append({
                "plan_id": plan_id,
                "status": str(data.get("status", "")),
                "lane": str(data.get("lane", "full")),
                "plan_file": plan_file,
                "accepted_with_fail": data.get("accepted_with_fail") is True,
            })
            seen.add(Path(plan_file).name)
    for path in archived:
        data, error = _read_json(path)
        if error or not isinstance(data, dict):
            checks.append(_check(
                "archived-tracker-readable", False,
                f"{path}: {error}",
            ))
            continue
        plan = data.get("archived_plan")
        if not isinstance(plan, dict):
            checks.append(_check(
                "archived-tracker-plan", False,
                f"{path.parent.name}: missing archived_plan",
            ))
            continue
        plan_ref = str(plan.get("plan_ref", ""))
        if Path(plan_ref).name in seen:
            continue
        candidates.append({
            "plan_id": str(plan.get("id", "")),
            "status": str(plan.get("status", "")),
            "lane": "full",
            "plan_file": plan_ref,
            "accepted_with_fail": False,
        })

    for item in candidates:
        plan_id = item["plan_id"]
        label = plan_id or Path(item["plan_file"]).stem
        if not PLAN_ID_RE.fullmatch(plan_id):
            checks.append(_check(
                "plan-id-format", False,
                f"plan id '{plan_id}' is missing or invalid", plan_id=plan_id,
            ))
        if item["status"] not in TERMINAL_PLAN_STATUSES:
            checks.append(_check(
                "plan-terminal-status", False,
                f"nonterminal plan status '{item['status']}'",
                plan_id=plan_id,
            ))
        plan_file = item["plan_file"]
        local_plan = plans_dir / plan_file
        repo_plan = project_dir / "docs" / "ghs" / "plans" / plan_file
        artifact = local_plan if local_plan.is_file() else repo_plan
        if not artifact.is_file():
            checks.append(_check(
                "plan-artifact", False,
                f"plan artifact not found: {plan_file}", plan_id=plan_id,
            ))
            contract_text = ""
        else:
            try:
                contract_text = artifact.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                checks.append(_check(
                    "plan-artifact-readable", False,
                    f"cannot read plan artifact: {exc}", plan_id=plan_id,
                ))
                contract_text = ""
        contract_ok = any(
            line.strip() == CONTRACT_HEADER
            for line in contract_text.splitlines()[:10]
        )
        if not contract_ok:
            checks.append(_check(
                "plan-contract-header", False,
                "contract title is missing or invalid", plan_id=plan_id,
            ))
        if item["lane"] == "light":
            body = contract_text
            checks.append(_check(
                "light-task-artifact", "### Task 1:" in body,
                "light plan must contain a Task 1 card",
                plan_id=plan_id,
            ))
            checks.append(_check(
                "light-anchors-artifact", "- Anchors:" in body,
                "light plan must contain an Anchors field",
                plan_id=plan_id,
            ))
            continue

        review_path = plans_dir / f"{plan_file}.review.md"
        if not review_path.is_file():
            checks.append(_check(
                "plan-review-artifact", False,
                f"review artifact not found: {review_path.name}",
                plan_id=plan_id,
            ))
            continue
        try:
            review_text = review_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            checks.append(_check(
                "plan-review-readable", False,
                f"cannot read review: {exc}", plan_id=plan_id,
            ))
            continue
        review_ok, review_message = _review_is_pass(review_text)
        if review_ok:
            checks.append(_check(
                "plan-review-pass", True, review_message, plan_id=plan_id,
            ))
        elif item["accepted_with_fail"]:
            checks.append(_check(
                "plan-review-accepted", False,
                f"user accepted residual findings: {review_message}",
                severity="warning", plan_id=plan_id,
            ))
        else:
            checks.append(_check(
                "plan-review-pass", False, review_message, plan_id=plan_id,
            ))
    return checks


def _audit_features(
    active: dict | None, archived: list[Path], project_dir: Path
) -> list:
    checks: list = []
    known_ids: set[str] = set()
    feature_records: list[tuple[dict, str, str]] = []
    if active is None:
        checks.append(_check(
            "features-json-readable", False, ".ghs/features.json is unreadable",
        ))
    else:
        if not isinstance(active.get("project"), dict):
            checks.append(_check(
                "features-project-section", False, "missing project object",
            ))
        if not isinstance(active.get("plans"), list):
            checks.append(_check(
                "features-plans-array", False, "plans must be an array",
            ))
        for plan in active.get("plans", []):
            if not isinstance(plan, dict):
                checks.append(_check("plan-object", False, "plan must be an object"))
                continue
            checks.extend(_validate_plan(plan, project_dir, feature_records))
    for path in archived:
        data, error = _read_json(path)
        if error or not isinstance(data, dict):
            checks.append(_check(
                "archived-tracker-readable", False, f"{path}: {error}",
            ))
            continue
        plan = data.get("archived_plan")
        if isinstance(plan, dict):
            checks.extend(_validate_plan(plan, project_dir, feature_records))
    for feature, plan_id, _ in feature_records:
        feature_id = str(feature.get("id", ""))
        if not feature_id:
            continue
        if feature_id in known_ids:
            checks.append(_check(
                "feature-id-unique", False,
                f"duplicate feature id '{feature_id}'",
                feature_id=feature_id,
            ))
        known_ids.add(feature_id)
    for feature, plan_id, _ in feature_records:
        feature_id = str(feature.get("id", ""))
        dependencies = feature.get("dependencies", [])
        if dependencies is None:
            dependencies = []
        if not isinstance(dependencies, list):
            checks.append(_check(
                "feature-dependencies", False, "dependencies must be an array",
                plan_id=plan_id, feature_id=feature_id,
            ))
            continue
        for dependency in dependencies:
            if dependency not in known_ids:
                checks.append(_check(
                    "feature-dependency", False,
                    f"dependency '{dependency}' is not resolvable",
                    plan_id=plan_id, feature_id=feature_id,
                ))
    return checks


def _validate_plan(
    plan: dict, project_dir: Path, records: list[tuple[dict, str, str]]
) -> list:
    checks: list = []
    plan_id = str(plan.get("id", ""))
    if not PLAN_ID_RE.fullmatch(plan_id):
        checks.append(_check(
            "plan-id-format", False, f"invalid plan id '{plan_id}'",
            plan_id=plan_id,
        ))
    if not isinstance(plan.get("name"), str):
        checks.append(_check(
            "plan-name", False, "plan name is missing", plan_id=plan_id,
        ))
    status = plan.get("status")
    if status not in VALID_PLAN_STATUSES:
        checks.append(_check(
            "plan-status-valid", False, f"invalid plan status '{status}'",
            plan_id=plan_id,
        ))
    plan_ref = plan.get("plan_ref")
    if not isinstance(plan_ref, str) or not plan_ref:
        checks.append(_check(
            "plan-ref", False, "plan_ref is missing", plan_id=plan_id,
        ))
    elif not (project_dir / plan_ref).is_file():
        checks.append(_check(
            "plan-ref-exists", False,
            f"plan_ref does not exist: {plan_ref}", plan_id=plan_id,
        ))
    features = plan.get("features")
    if not isinstance(features, list):
        checks.append(_check(
            "plan-features-array", False, "features must be an array",
            plan_id=plan_id,
        ))
        return checks
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            checks.append(_check(
                "feature-object", False, f"feature {index} is not an object",
                plan_id=plan_id,
            ))
            continue
        records.append((feature, plan_id, str(feature.get("id", ""))))
        checks.extend(_validate_feature(feature, plan_id, index))
    return checks


def _validate_feature(feature: dict, plan_id: str, index: int) -> list:
    checks: list = []
    feature_id = str(feature.get("id", ""))
    match = FEATURE_ID_RE.fullmatch(feature_id)
    if not match:
        checks.append(_check(
            "feature-id-format", False,
            f"invalid feature id '{feature_id}'", plan_id=plan_id,
            feature_id=feature_id or None,
        ))
    elif match.group(1) != plan_id:
        checks.append(_check(
            "feature-id-prefix", False,
            f"feature prefix does not match plan '{plan_id}'",
            plan_id=plan_id, feature_id=feature_id,
        ))
    for field in ("title", "description", "status"):
        if not isinstance(feature.get(field), str):
            checks.append(_check(
                f"feature-{field}", False, f"missing or invalid {field}",
                plan_id=plan_id, feature_id=feature_id or None,
            ))
    if feature.get("status") not in VALID_FEATURE_STATUSES:
        checks.append(_check(
            "feature-status-valid", False,
            f"invalid feature status '{feature.get('status')}'",
            plan_id=plan_id, feature_id=feature_id or None,
        ))
    priority = feature.get("priority")
    if priority is not None and priority not in {"high", "medium", "low"}:
        checks.append(_check(
            "feature-priority-valid", False, f"invalid priority '{priority}'",
            plan_id=plan_id, feature_id=feature_id,
        ))
    category = feature.get("category")
    if category is not None and category not in {
        "core", "ui", "api", "auth", "data", "infra"
    }:
        checks.append(_check(
            "feature-category-valid", False, f"invalid category '{category}'",
            plan_id=plan_id, feature_id=feature_id,
        ))
    files = feature.get("files_affected", [])
    if files is not None and not (
        isinstance(files, list) and all(isinstance(item, str) for item in files)
    ):
        checks.append(_check(
            "feature-files-affected", False,
            "files_affected must be an array of strings",
            plan_id=plan_id, feature_id=feature_id,
        ))
    return checks


def _git_run(project_dir: Path, args: list[str]) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    proc = subprocess.run(
        ["git", "-C", str(project_dir), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, shell=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _audit_commits(project_dir: Path, active: dict | None, archived: list[Path]) -> list:
    checks: list = []
    rc, top, stderr = _git_run(project_dir, ["rev-parse", "--show-toplevel"])
    if rc:
        checks.append(_check(
            "git-worktree", False,
            f"target is not inside a git work tree: {stderr.strip()}",
        ))
        return checks
    rc, output, stderr = _git_run(project_dir, ["log", "--all", "--format=%H%x1f%s"])
    if rc:
        checks.append(_check(
            "git-history", False,
            f"cannot read git history: {stderr.strip()}",
        ))
        return checks
    commits: list[tuple[str, str]] = []
    for line in output.splitlines():
        if "\x1f" in line:
            commits.append(tuple(line.split("\x1f", 1)))  # type: ignore[arg-type]
    records: list[tuple[dict, str]] = []
    if isinstance(active, dict):
        for plan in active.get("plans", []):
            if isinstance(plan, dict):
                records.extend(
                    (feature, str(plan.get("id", "")))
                    for feature in plan.get("features", [])
                    if isinstance(feature, dict)
                )
    for path in archived:
        data, _ = _read_json(path)
        plan = data.get("archived_plan") if isinstance(data, dict) else None
        if isinstance(plan, dict):
            records.extend(
                (feature, str(plan.get("id", "")))
                for feature in plan.get("features", [])
                if isinstance(feature, dict)
            )
    for feature, plan_id in records:
        if feature.get("status") != "completed":
            continue
        feature_id = str(feature.get("id", ""))
        matches = [(oid, subject) for oid, subject in commits if f"(Feature: {feature_id})" in subject]
        if not matches:
            checks.append(_check(
                "feature-commit", False,
                f"completed feature has no commit containing '(Feature: {feature_id})'",
                plan_id=plan_id, feature_id=feature_id,
            ))
            continue
        files = feature.get("files_affected", [])
        if not files:
            continue
        touched = False
        for oid, _ in matches:
            rc, changed, _ = _git_run(
                project_dir,
                ["diff-tree", "--no-commit-id", "--name-only", "--root", "-r", oid],
            )
            if rc == 0 and any(path in changed.splitlines() for path in files):
                touched = True
                break
        if not touched:
            checks.append(_check(
                "feature-commit-files", False,
                "feature commit does not touch a declared file",
                plan_id=plan_id, feature_id=feature_id,
            ))
    return checks


def _audit_archives(active: dict | None, archived: list[Path], project_dir: Path) -> list:
    checks: list = []
    active_plans = active.get("plans", []) if isinstance(active, dict) else []
    for path in archived:
        data, error = _read_json(path)
        if error or not isinstance(data, dict):
            continue
        plan = data.get("archived_plan")
        if not isinstance(plan, dict):
            continue
        plan_id = str(plan.get("id", ""))
        if plan.get("status") != "completed":
            checks.append(_check(
                "archive-plan-completed", False,
                f"archived plan status is '{plan.get('status')}'",
                plan_id=plan_id,
            ))
        features = plan.get("features", [])
        incomplete = [
            str(feature.get("id", index))
            for index, feature in enumerate(features)
            if not isinstance(feature, dict) or feature.get("status") != "completed"
        ]
        if incomplete:
            checks.append(_check(
                "archive-features-completed", False,
                "archived plan has incomplete features: " + ", ".join(incomplete),
                plan_id=plan_id,
            ))
        if any(str(item.get("id", "")) == plan_id for item in active_plans):
            checks.append(_check(
                "archive-id-not-active", False,
                f"plan '{plan_id}' remains in the active tracker",
                plan_id=plan_id,
            ))
        plan_ref = str(plan.get("plan_ref", ""))
        if plan_ref and not (
            (project_dir / ".ghs" / "plans" / Path(plan_ref).name).is_file()
            or (project_dir / plan_ref).is_file()
        ):
            checks.append(_check(
                "archive-plan-artifact", False,
                f"archived plan artifact not found: {plan_ref}",
                plan_id=plan_id,
            ))
    for plan in active_plans:
        if isinstance(plan, dict) and plan.get("status") == "completed":
            checks.append(_check(
                "completed-plan-unarchived", False,
                f"completed plan '{plan.get('id')}' is not archived",
                severity="warning", plan_id=str(plan.get("id", "")),
            ))
    return checks


def run_audit(project_dir: Path) -> dict:
    """Audit a target project without writing to it and return the report."""
    project_dir = project_dir.resolve()
    before = _snapshot(project_dir)
    active, archived = _load_trackers(project_dir)
    stages = [
        {"id": "plan", "checks": _audit_plans(project_dir, active, archived)},
        {"id": "features", "checks": _audit_features(active, archived, project_dir)},
        {"id": "commits", "checks": _audit_commits(project_dir, active, archived)},
        {"id": "archive", "checks": _audit_archives(active, archived, project_dir)},
    ]
    after = _snapshot(project_dir)
    zero_write_verified = before == after
    errors = sum(
        not check["passed"] and check["severity"] == "error"
        for stage in stages for check in stage["checks"]
    )
    warnings = sum(
        not check["passed"] and check["severity"] == "warning"
        for stage in stages for check in stage["checks"]
    )
    return {
        "schema_version": 1,
        "kind": "ghs-eval-audit",
        "project_dir": str(project_dir),
        "passed": errors == 0 and zero_write_verified,
        "zero_write_verified": zero_write_verified,
        "summary": {"errors": errors, "warnings": warnings},
        "stages": stages,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ghs evaluation pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit", help="read-only lifecycle audit")
    audit.add_argument(
        "--project-dir", "-p", default=".",
        help="Target project directory (default: current directory)",
    )
    return parser


def main() -> int:
    force_utf8_stdio()
    parser = _build_parser()
    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"eval_pipeline: error: project directory not found: {project_dir}", file=sys.stderr)
        return 2
    report = run_audit(project_dir)
    print(json.dumps(report, ensure_ascii=False))
    return 2 if not report["zero_write_verified"] else (0 if report["passed"] else 1)


if __name__ == "__main__":
    sys.exit(main())
