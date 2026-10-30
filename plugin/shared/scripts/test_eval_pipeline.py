#!/usr/bin/env python3
"""Tests for the read-only ghs lifecycle audit engine."""

import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from eval_pipeline import load_cases, run_audit, verify_workdir  # noqa: E402


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


class EvalPipelineCaseTests(unittest.TestCase):
    def write_case(self, root, name, *, artifacts=None, fixture_files=None,
                   verifier="ok", timeout=None):
        directory = root / name
        (directory / "fixture").mkdir(parents=True)
        case = {
            "schema_version": 1,
            "name": name,
            "title": f"Example {name}",
        }
        if timeout is not None:
            case["verify_timeout_seconds"] = timeout
        (directory / "case.json").write_text(
            json.dumps(case), encoding="utf-8"
        )
        (directory / "brief.md").write_text("Fix the fixture.\n", encoding="utf-8")
        (directory / "verify.py").write_text(
            "\n".join([
                "from pathlib import Path",
                "import sys",
                "",
                "artifact = Path(sys.argv[1]) / 'calc.py'",
                f"value = artifact.read_text(encoding='utf-8').strip()",
                f"if value != '{verifier}':",
                "    print('calc value mismatch')",
                "    sys.exit(1)",
                "sys.exit(0)",
            ]) + "\n",
            encoding="utf-8",
        )
        (directory / "expected_artifacts.json").write_text(
            json.dumps({
                "schema_version": 1,
                "artifacts": artifacts if artifacts is not None else [
                    {"path": "calc.py", "sha256": None},
                ],
            }), encoding="utf-8",
        )
        fixture_files = fixture_files if fixture_files is not None else {
            "calc.py": "ok\n",
        }
        for path, content in fixture_files.items():
            (directory / "fixture" / path).write_text(content, encoding="utf-8")
        return directory

    def test_load_cases_parses_valid_case_and_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_case(root, "z-case")
            self.write_case(root, "a-case")
            cases, errors = load_cases(root, {"z-case", "z-case", "a-case"})
            self.assertEqual(errors, [])
            self.assertEqual([case.name for case in cases], ["a-case", "z-case"])
            self.assertEqual(cases[0].title, "Example a-case")
            self.assertEqual(cases[0].verify_timeout_seconds, 120)
            self.assertEqual(
                cases[0].expected_artifacts,
                (type(cases[0].expected_artifacts[0])("calc.py", None),),
            )
            self.assertTrue(cases[0].fixture_dir.is_dir())

    def test_case_without_hidden_verify_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_case(root, "missing-verifier")
            (root / "missing-verifier" / "verify.py").unlink()
            self.write_case(root, "missing-expected")
            (root / "missing-expected" / "expected_artifacts.json").unlink()
            cases, errors = load_cases(root, None)
            self.assertEqual(cases, [])
            self.assertEqual([error.name for error in errors], [
                "missing-expected", "missing-verifier",
            ])
            self.assertFalse(all(error.case_valid for error in errors))
            self.assertTrue(any("verify.py" in error.errors[0] for error in errors))
            self.assertTrue(any(
                "expected_artifacts.json" in error.errors[0] for error in errors
            ))

    def test_expected_artifact_paths_are_rejected_when_unsafe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_case(root, "absolute-path", artifacts=[
                {"path": "/repo/secret", "sha256": None},
            ])
            self.write_case(root, "parent-path", artifacts=[
                {"path": "../secret", "sha256": None},
            ])
            cases, errors = load_cases(root, None)
            self.assertEqual(cases, [])
            self.assertEqual([error.name for error in errors], [
                "absolute-path", "parent-path",
            ])
            self.assertTrue(all(
                "safe relative POSIX path" in error.errors[0] for error in errors
            ))

    def test_verify_case_reports_pass_and_failure_tails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_dir = self.write_case(root, "tail-case")
            cases, errors = load_cases(root, {"tail-case"})
            self.assertEqual(errors, [])
            passing = Path(tmp) / "passing-workdir"
            failing = Path(tmp) / "failing-workdir"
            shutil.copytree(case_dir / "fixture", passing)
            shutil.copytree(case_dir / "fixture", failing)
            (failing / "calc.py").write_text("broken\n", encoding="utf-8")
            passed = verify_workdir(cases[0], passing)
            failed = verify_workdir(cases[0], failing)
            self.assertTrue(passed.passed)
            self.assertEqual(passed.verifier_exit_code, 0)
            self.assertFalse(passed.timed_out)
            self.assertFalse(failed.passed)
            self.assertEqual(failed.verifier_exit_code, 1)
            self.assertIn("calc value mismatch", failed.output_tail)

    def test_verify_case_checks_artifacts_before_hidden_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_dir = self.write_case(root, "artifact-case", artifacts=[
                {"path": "calc.py", "sha256": hashlib.sha256(b"other").hexdigest()},
            ])
            cases, errors = load_cases(root, {"artifact-case"})
            self.assertEqual(errors, [])
            workdir = Path(tmp) / "workdir"
            shutil.copytree(case_dir / "fixture", workdir)
            outcome = verify_workdir(cases[0], workdir)
            self.assertFalse(outcome.passed)
            self.assertIsNone(outcome.verifier_exit_code)
            self.assertEqual(outcome.output_tail, "")
            self.assertEqual(len(outcome.artifact_errors), 1)


if __name__ == "__main__":
    unittest.main()
