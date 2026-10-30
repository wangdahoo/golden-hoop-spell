#!/usr/bin/env python3
"""Tests for the read-only ghs lifecycle audit engine."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from eval_pipeline import run_audit  # noqa: E402


PROJECT = {
    "project": {"name": "demo", "description": "demo", "created_at": "2026-10-31"},
    "metadata": {"version": "1.0.0", "last_updated": "2026-10-31"},
}


def feature(feature_id, status="completed", files=None, dependencies=None):
    return {
        "id": feature_id,
        "title": "Example",
        "description": "Example feature",
        "status": status,
        "files_affected": files or [],
        "dependencies": dependencies or [],
    }


def write_features(path, plans):
    data = dict(PROJECT)
    data["plans"] = plans
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def write_plan_artifacts(project, plan_id="p1", status="approved", lane="full",
                         plan_name="2026-10-31-demo.md", review="PASS"):
    plans = project / ".ghs" / "plans"
    plans.mkdir(parents=True)
    body = "> SCOPE CONTRACT — frozen at kickoff.\n"
    if lane == "light":
        body += "\n### Task 1: Demo\n- Anchors:\n- test: behavior holds\n"
    else:
        body += "\n## Design\nComplete.\n"
    (plans / plan_name).write_text(body, encoding="utf-8")
    (plans / f"{plan_name}-status.json").write_text(json.dumps({
        "plan_file": plan_name, "status": status, "lane": lane,
        "accepted_with_fail": False,
    }), encoding="utf-8")
    if lane == "full":
        signal = f"REVIEW COMPLETE | Verdict: {review} | Unwarranted: 0 Severe: 0 Medium: 0 Optimization: 1"
        (plans / f"{plan_name}.review.md").write_text(signal + "\n", encoding="utf-8")
    docs = project / "docs" / "ghs" / "plans"
    docs.mkdir(parents=True)
    (docs / plan_name).write_text(body, encoding="utf-8")


def init_git(project, feature_id):
    def git(*args):
        subprocess.run(["git", "-C", str(project), *args], check=True,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    git("init")
    git("config", "user.email", "audit@example.com")
    git("config", "user.name", "Audit Test")
    (project / "src").mkdir()
    (project / "src" / "demo.py").write_text("value = 1\n", encoding="utf-8")
    git("add", ".ghs/features.json", "src/demo.py")
    git("commit", "-m", f"feat(scripts): demo change (Feature: {feature_id})")


class EvalPipelineAuditTests(unittest.TestCase):
    def test_audit_valid_full_lifecycle_reports_no_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_plan_artifacts(project)
            write_features(project / ".ghs" / "features.json", [{
                "id": "p1", "name": "Demo plan", "status": "completed",
                "plan_ref": "docs/ghs/plans/2026-10-31-demo.md",
                "features": [feature("p1-feat-001", files=["src/demo.py"])],
            }])
            init_git(project, "p1-feat-001")
            report = run_audit(project)
            self.assertEqual(report["summary"]["errors"], 0,
                             json.dumps(report, ensure_ascii=False, indent=2))
            self.assertTrue(report["passed"])
            self.assertTrue(report["zero_write_verified"])
            self.assertEqual([stage["id"] for stage in report["stages"]],
                             ["plan", "features", "commits", "archive"])

    def test_audit_plan_contract_review_failures_are_located(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_plan_artifacts(project, plan_id="p1", status="revising", review="FAIL")
            write_features(project / ".ghs" / "features.json", [{
                "id": "p1", "name": "Demo", "status": "in_progress",
                "plan_ref": "docs/ghs/plans/2026-10-31-demo.md",
                "features": [feature("p1-feat-001", "pending")],
            }])
            report = run_audit(project)
            plan = next(stage for stage in report["stages"] if stage["id"] == "plan")
            checks = {(check["id"], check["plan_id"]): check for check in plan["checks"]}
            self.assertFalse(checks[("plan-terminal-status", "p1")]["passed"])
            self.assertFalse(checks[("plan-review-pass", "p1")]["passed"])
            self.assertEqual(report["summary"]["errors"], len([
                check for stage in report["stages"] for check in stage["checks"]
                if not check["passed"] and check["severity"] == "error"
            ]))

    def test_audit_feature_commit_and_archive_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_plan_artifacts(project)
            write_features(project / ".ghs" / "features.json", [{
                "id": "p1", "name": "Demo", "status": "completed",
                "plan_ref": "docs/ghs/plans/2026-10-31-demo.md",
                "features": [
                    feature(
                        "p1-feat-001", dependencies=["p1-feat-999"],
                        files=["src/demo.py"],
                    ),
                    feature("p1-feat-002"),
                ],
            }])
            archive = project / ".ghs" / "archived" / "p0_demo_1"
            archive.mkdir(parents=True)
            (archive / "features.json").write_text(json.dumps({
                "project": PROJECT["project"],
                "archived_plan": {
                    "id": "p0", "name": "Old", "status": "in_progress",
                    "plan_ref": "docs/ghs/plans/old.md",
                    "features": [feature("p0-feat-001", "pending")],
                },
            }), encoding="utf-8")
            init_git(project, "p1-feat-001")
            report = run_audit(project)
            by_stage = {stage["id"]: stage for stage in report["stages"]}
            feature_checks = by_stage["features"]["checks"]
            commit_checks = by_stage["commits"]["checks"]
            self.assertTrue(any(
                check.get("feature_id") == "p1-feat-001" and check["id"] == "feature-dependency"
                for check in feature_checks
            ))
            self.assertFalse(any(
                check.get("feature_id") == "p1-feat-001" and check["id"] == "feature-commit-files"
                for check in commit_checks
            ))
            self.assertTrue(any(
                check.get("feature_id") == "p1-feat-002" and check["id"] == "feature-commit"
                for check in commit_checks
            ))
            self.assertTrue(any(
                check.get("plan_id") == "p0" and check["id"] == "archive-plan-completed"
                for check in by_stage["archive"]["checks"]
            ))

    def test_audit_light_lane_and_zero_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_plan_artifacts(project, lane="light")
            write_features(project / ".ghs" / "features.json", [{
                "id": "p1", "name": "Demo", "status": "in_progress",
                "plan_ref": "docs/ghs/plans/2026-10-31-demo.md",
                "features": [feature("p1-feat-001", "pending")],
            }])
            watched = [
                project / ".ghs" / "features.json",
                project / ".ghs" / "plans" / "2026-10-31-demo.md",
                project / ".ghs" / "plans" / "2026-10-31-demo.md-status.json",
            ]
            before = {path: path.stat().st_mtime_ns for path in watched}
            report = run_audit(project)
            plan = next(stage for stage in report["stages"] if stage["id"] == "plan")
            self.assertFalse(any(check["id"] == "plan-review-artifact" for check in plan["checks"]))
            self.assertTrue(all(check["passed"] for check in plan["checks"] if check["id"].startswith("light-")))
            self.assertTrue(report["zero_write_verified"])
            self.assertEqual(before, {path: path.stat().st_mtime_ns for path in watched})
            rc = subprocess.run([
                sys.executable, str(SCRIPT_DIR / "eval_pipeline.py"),
                "audit", "--project-dir", str(project),
            ], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(rc.returncode, 1)
            payload = json.loads(rc.stdout)
            self.assertFalse(payload["passed"])


if __name__ == "__main__":
    unittest.main()
