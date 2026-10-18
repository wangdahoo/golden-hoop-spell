#!/usr/bin/env python3
"""Unit tests for tasks_to_features.py.

Run directly:
    command python3 plugin/shared/scripts/test_tasks_to_features.py

No pytest dependency. Uses only the standard unittest module.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import tasks_to_features as t2f  # noqa: E402


PLAN_ID_RE = t2f.PLAN_NUM_RE


def write_plan(directory, body):
    plan_file = Path(directory) / "docs" / "ghs" / "plans" / "2026-10-17-demo.md"
    plan_file.parent.mkdir(parents=True, exist_ok=True)
    plan_file.write_text(body, encoding="utf-8")
    return plan_file


SAMPLE_PLAN = """# Demo Plan

> SCOPE CONTRACT — frozen at kickoff.

## Intent
重构会话刷新逻辑以消除过期 token 崩溃。

## Goals
- 刷新接口拒绝过期 token

## Non-Goals
- 不改登录流程

## Anti-Goals
- 即使刷新能跑但引入新依赖也算失败

## Decisions
- 沿用现有 session 模块

## Open Space
- 日志措辞由实现方定

## Global Constraints
- Python 3.10+
- 禁止新增第三方依赖

## Current State
session 模块位于 src/session.py。

## Design
刷新入口集中到 refresh()。

## Assumptions
None

## Risks
None

### Task 1: 刷新校验
- Files: src/session.py, tests/test_session.py
- Interfaces: refresh(token: str) -> Session
- Points: 过期 token 直接 401，不落库
- Anchors:
  - test_refresh_rejects_expired: 过期 token 返回 401 且不落库
  - [UNDEFINED-INPUT] 畸形 token: 返回 400 不崩溃

### Task 2: 文案
- Files: src/messages.py
- Interfaces: EXPIRED_TEXT: str
- Points: 替换过期提示文案
- Anchors:
  - npm test -- --filter messages: 无失败
"""

FEATURES_EMPTY = {"project": {"name": "demo", "description": "d", "created_at": "2026-10-17"}, "plans": [], "metadata": {"version": "1.0.0", "last_updated": ""}}


def run_cli(project_dir, plan_file):
    cmd = [
        sys.executable, str(SCRIPT_DIR / "tasks_to_features.py"),
        "--project-dir", str(project_dir), "--plan-file", str(plan_file),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    parsed = json.loads(proc.stdout) if proc.stdout.strip() else None
    return proc.returncode, parsed, proc.stderr


class TasksToFeaturesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / ".ghs").mkdir()
        feats = self.project / ".ghs" / "features.json"
        feats.write_text(json.dumps(FEATURES_EMPTY), encoding="utf-8")
        prog = self.project / ".ghs" / "progress.md"
        prog.write_text("# Log\n\n## Sessions\n\n<!-- new entries above -->\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_01_happy_path(self):
        plan = write_plan(self.project, SAMPLE_PLAN)
        code, out, err = run_cli(self.project, plan)
        self.assertEqual(code, 0, err)
        self.assertEqual(out["status"], "parsed")
        self.assertEqual(out["plan_id"], "p1")
        self.assertEqual(out["feature_ids"], ["p1-feat-001", "p1-feat-002"])
        data = json.loads((self.project / ".ghs" / "features.json").read_text(encoding="utf-8"))
        plan_obj = data["plans"][0]
        self.assertEqual(plan_obj["id"], "p1")
        self.assertEqual(plan_obj["status"], "in_progress")
        self.assertEqual(plan_obj["plan_ref"], str(plan.relative_to(self.project)).replace("\\", "/"))
        f1, f2 = plan_obj["features"]
        self.assertEqual(f1["id"], "p1-feat-001")
        self.assertTrue(f1["acceptance_criteria"][0].startswith("Python 3.10+"))
        self.assertIn("test_refresh_rejects_expired", f1["acceptance_criteria"][-2])
        self.assertIn("[UNDEFINED-INPUT]", f1["acceptance_criteria"][-1])
        self.assertEqual(f1["dependencies"], [])
        self.assertEqual(f2["dependencies"], ["p1-feat-001"])
        self.assertEqual(f1["status"], "pending")
        self.assertIn("refresh(token: str) -> Session", f1["technical_notes"])
        self.assertEqual(f1["category"], "core")

    def test_02_plan_number_increments(self):
        data = json.loads(json.dumps(FEATURES_EMPTY))
        data["plans"] = [{"id": "p1", "features": []}, {"id": "p3", "features": []}]
        (self.project / ".ghs" / "features.json").write_text(json.dumps(data), encoding="utf-8")
        plan = write_plan(self.project, SAMPLE_PLAN)
        code, out, _ = run_cli(self.project, plan)
        self.assertEqual(code, 0)
        self.assertEqual(out["plan_id"], "p4")
        self.assertTrue(out["feature_ids"][0].startswith("p4-feat-"))

    def test_03_category_heuristic(self):
        body = SAMPLE_PLAN.replace("- Files: src/session.py, tests/test_session.py",
                                   "- Files: src/api/routes.py, web/ui/App.tsx")
        plan = write_plan(self.project, body)
        _, out, _ = run_cli(self.project, plan)
        data = json.loads((self.project / ".ghs" / "features.json").read_text(encoding="utf-8"))
        self.assertEqual(data["plans"][0]["features"][0]["category"], "ui")

    def test_04_no_task_zone(self):
        plan = write_plan(self.project, SAMPLE_PLAN.split("### Task 1")[0])
        before = (self.project / ".ghs" / "features.json").read_text(encoding="utf-8")
        code, out, _ = run_cli(self.project, plan)
        self.assertEqual(code, 1)
        self.assertEqual(out["status"], "no_task_zone")
        self.assertEqual((self.project / ".ghs" / "features.json").read_text(encoding="utf-8"), before)

    def test_05_malformed_missing_anchors(self):
        body = SAMPLE_PLAN.replace("  - test_refresh_rejects_expired: 过期 token 返回 401 且不落库\n", "") \
                          .replace("  - [UNDEFINED-INPUT] 畸形 token: 返回 400 不崩溃\n", "")
        plan = write_plan(self.project, body)
        code, out, _ = run_cli(self.project, plan)
        self.assertEqual(code, 1)
        self.assertEqual(out["status"], "malformed")
        self.assertIn("Task 1", out["reason"])

    def test_06_malformed_empty_criterion(self):
        body = SAMPLE_PLAN.replace("test_refresh_rejects_expired: 过期 token 返回 401 且不落库",
                                   "test_refresh_rejects_expired: works correctly")
        plan = write_plan(self.project, body)
        code, out, _ = run_cli(self.project, plan)
        self.assertEqual(out["status"], "malformed")

    def test_07_malformed_too_many_anchors(self):
        extra = "\n".join(f"  - test_x{i}: 断言{i}" for i in range(5))
        body = SAMPLE_PLAN.replace("  - test_refresh_rejects_expired",
                                   extra + "\n  - test_refresh_rejects_expired")
        plan = write_plan(self.project, body)
        code, out, _ = run_cli(self.project, plan)
        self.assertEqual(out["status"], "malformed")
        self.assertIn("anchors", out["reason"].lower())

    def test_08_malformed_nonsequential(self):
        body = SAMPLE_PLAN.replace("### Task 2:", "### Task 3:")
        plan = write_plan(self.project, body)
        code, out, _ = run_cli(self.project, plan)
        self.assertEqual(out["status"], "malformed")

    def test_09_name_from_intent(self):
        plan = write_plan(self.project, SAMPLE_PLAN)
        run_cli(self.project, plan)
        data = json.loads((self.project / ".ghs" / "features.json").read_text(encoding="utf-8"))
        self.assertEqual(data["plans"][0]["name"], "重构会话刷新逻辑以消除过期 token 崩溃")

    def test_10_progress_entry(self):
        plan = write_plan(self.project, SAMPLE_PLAN)
        run_cli(self.project, plan)
        prog = (self.project / ".ghs" / "progress.md").read_text(encoding="utf-8")
        self.assertIn("## Feature Planning -", prog)
        self.assertIn("p1", prog.split("## Feature Planning -", 1)[1].split("##", 1)[0])
        self.assertLess(prog.index("## Feature Planning -"), prog.index("<!-- new entries above -->"))

    def test_11_light_lane_constraints_stop_at_task_tail(self):
        body = """# Light Plan

## Intent
Fix the login crash.

## Global Constraints
- All tests must pass
- No new dependencies

### Task 1: Fix login crash
- Files: src/auth/login.py
- Interfaces: refresh(session) -> Session
- Points: Fix the expired-token crash
- Anchors:
  - refresh: expired token returns 401
"""
        plan = write_plan(self.project, body)
        code, out, err = run_cli(self.project, plan)
        self.assertEqual(code, 0, err)
        data = json.loads((self.project / ".ghs" / "features.json").read_text(encoding="utf-8"))
        criteria = data["plans"][0]["features"][0]["acceptance_criteria"]
        self.assertEqual(criteria, [
            "All tests must pass",
            "No new dependencies",
            "refresh: expired token returns 401",
        ])

    def test_12_plan_file_outside_project_dir_exits_2(self):
        outside = Path(self._tmp.name).parent / "outside-plan.md"
        outside.write_text(SAMPLE_PLAN, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "tasks_to_features.py"),
                 "--project-dir", str(self.project), "--plan-file", str(outside)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(proc.stdout.strip(), "")
            self.assertIn("error", proc.stderr.lower())
        finally:
            outside.unlink(missing_ok=True)

    def test_13_corrupt_features_json_exits_2(self):
        (self.project / ".ghs" / "features.json").write_text("{broken", encoding="utf-8")
        plan = write_plan(self.project, SAMPLE_PLAN)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "tasks_to_features.py"),
             "--project-dir", str(self.project), "--plan-file", str(plan)],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertIn("error", proc.stderr.lower())

    def test_14_name_sentence_boundaries(self):
        # ASCII dots inside identifiers/version numbers are not sentence ends.
        body = SAMPLE_PLAN.replace(
            "重构会话刷新逻辑以消除过期 token 崩溃。",
            "Fix session.refresh() crash in v1.2.")
        plan = write_plan(self.project, body)
        run_cli(self.project, plan)
        data = json.loads((self.project / ".ghs" / "features.json").read_text(encoding="utf-8"))
        self.assertEqual(data["plans"][-1]["name"], "Fix session.refresh() crash in v1.2")
        # CJK terminators still split mid-line.
        body = SAMPLE_PLAN.replace("重构会话刷新逻辑以消除过期 token 崩溃。",
                                   "修复登录崩溃。保持兼容。")
        plan = write_plan(self.project, body)
        run_cli(self.project, plan)
        data = json.loads((self.project / ".ghs" / "features.json").read_text(encoding="utf-8"))
        self.assertEqual(data["plans"][-1]["name"], "修复登录崩溃")

    def test_15_empty_criterion_trailing_punctuation(self):
        # Trailing punctuation must not launder a banned empty judgement.
        for variant in ("works correctly.", "works correctly!", "测试通过。", "ok."):
            body = SAMPLE_PLAN.replace(
                "test_refresh_rejects_expired: 过期 token 返回 401 且不落库",
                f"test_refresh_rejects_expired: {variant}")
            plan = write_plan(self.project, body)
            _, out, _ = run_cli(self.project, plan)
            self.assertEqual(out["status"], "malformed", variant)
            self.assertIn("empty judgement", out["reason"], variant)


if __name__ == "__main__":
    unittest.main()
