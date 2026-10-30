# 计划状态闭环 + 两项实测 bug 修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `ghs-code` 收尾自动检测计划完成并（经确认）翻转计划状态、`ghs-archive` 兜底补翻，features.json 状态变更全部脚本化；顺带修复 `parallel_utils` 静默选错计划与 `archive_plans` 目录名非法字符崩溃。

**Architecture:** 新增 `update_features.py` 作为 features.json 状态唯一写入口（读写分离：`--set-feature`/`--set-plan` 写、`--plan-state` 判定），两个 SKILL.md 的收尾流程改为驱动该脚本；两个既有脚本各加一处防御（歧义报错 / 文件名消毒）。参照 `update_plan_status.py` 的成熟模式（read-modify-write、原子写、单行 ASCII stdout）。

**Tech Stack:** Python 3.10+ 标准库（argparse/json/tempfile/pathlib）、unittest（禁用 pytest）、Git Bash on Windows。

**Spec:** `docs/superpowers/specs/2026-10-24-plan-status-closed-loop-design.md`（本计划逐条落实该 spec，执行者需同时阅读）

## Global Constraints

- 所有 Python 执行一律 `command python3 -I <script>`；**禁止多行 `python -c`**（Windows shell 会把多行 `-c` 包装进临时 batch 脚本导致失败）。
- 脚本 stdout 仅单行 ASCII 确认行或单行 JSON；错误信息走 stderr、英文。
- 文件写入 UTF-8、`ensure_ascii=False`、2 空格缩进、临时文件 + `os.replace` 原子替换（照抄 `update_plan_status.write_status` 模式）。
- 状态枚举严格对齐 `validate_structure.py`：特性 `pending|in_progress|completed|blocked`（:96），计划 `planning|in_progress|completed|on_hold`（:139）。
- 测试只用 unittest；运行方式：仓库根目录 `command python3 -m unittest discover -s plugin/shared/scripts -v`。
- 语言政策：SKILL.md / references 改动用英文（LLM-facing）；文档叙述与 commit message 用中文。
- 提交信息 conventional 格式（`<type>(<scope>): 中文描述`），结尾加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 每个特性状态写入只在验证通过后执行；所有对既有文件的修改使用 Edit 工具精确替换，不整文件重写。

---

### Task 1: 新脚本 `update_features.py` + 测试

**Files:**
- Create: `plugin/shared/scripts/update_features.py`
- Create: `plugin/shared/scripts/test_update_features.py`

**Interfaces:**
- Consumes: `ghs_compat.force_utf8_stdio()`（已存在）、`resolve_project_dir.find_project_dir(start_dir: Path) -> Path | None`（已存在）。
- Produces（后续 Task 4/5 的 SKILL.md 引用其 CLI）:
  - `update_features.py --file <path> --set-feature <feature_id> --status pending|in_progress|completed|blocked [--blocked-reason "..."]` → stdout `OK feature <id> status=<status>`，exit 0
  - `update_features.py --file <path> --set-plan <plan_id> --status planning|in_progress|completed|on_hold` → stdout `OK plan <id> status=<status>`，exit 0
  - `update_features.py [--file <path>] --plan-state <plan_id>` → stdout 单行 JSON `{"plan_id":...,"counts":{"completed":N,"in_progress":N,"pending":N,"blocked":N},"can_complete":bool,"blocked_ids":[...]}`，exit 0
  - exit 1 = feature/plan id 不存在；exit 2 = 参数非法 / feature id 跨计划歧义 / 文件缺失或 JSON 损坏 / IO 错误
  - 模块级函数（测试直接调用）：`load_features(path) -> dict`、`write_features(path, data) -> None`、`locate_feature(data, feature_id) -> tuple[dict, dict]`（找不到 raise `KeyError`，歧义 raise `ValueError`）、`locate_plan(data, plan_id) -> dict`（找不到 raise `KeyError`）、`compute_plan_state(data, plan_id) -> dict`

- [ ] **Step 1: 写失败测试** — 新建 `plugin/shared/scripts/test_update_features.py`，内容如下（完整文件）：

```python
#!/usr/bin/env python3
"""Unit tests for update_features.py.

Pins the features.json status mutation contract: strict read-modify-write
(unknown fields preserved), enum validation aligned with validate_structure,
blocked-reason enforcement, stale blocked_reason cleanup, plan completion
state computation, and single-line ASCII stdout — even under a legacy GBK
console (PYTHONIOENCODING=gbk).

Run directly:
    command python3 plugin/shared/scripts/test_update_features.py

No pytest dependency. Uses only the standard unittest module.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Make update_features importable as a sibling module.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import update_features as helper  # noqa: E402

PLAN_P1 = {
    "id": "p1",
    "name": "demo plan",
    "status": "in_progress",
    "features": [
        {"id": "p1-feat-001", "title": "done feat", "status": "completed"},
        {"id": "p1-feat-002", "title": "todo feat", "status": "pending"},
        {
            "id": "p1-feat-003",
            "title": "stuck feat",
            "status": "blocked",
            "blocked_reason": "waiting for API",
        },
    ],
    "custom_keep": "keep-me",
}


def make_features(plans):
    return {"project": {"name": "demo"}, "plans": plans}


class UpdateFeaturesCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.feat_path = self.tmp / "features.json"
        self.feat_path.write_text(
            json.dumps(make_features([PLAN_P1]), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def run_cli(self, args, cwd=None):
        cmd = [sys.executable, str(SCRIPT_DIR / "update_features.py")] + args
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr

    def reload_data(self):
        return json.loads(self.feat_path.read_text(encoding="utf-8"))

    # ---- --set-feature ----

    def test_set_feature_completed(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "p1-feat-002",
             "--status", "completed"]
        )
        self.assertEqual(rc, 0, err)
        self.assertIn("OK feature p1-feat-002 status=completed", out)
        data = self.reload_data()
        feat = data["plans"][0]["features"][1]
        self.assertEqual(feat["status"], "completed")
        self.assertEqual(data["plans"][0]["custom_keep"], "keep-me")  # unknown kept

    def test_set_feature_blocked_requires_reason(self):
        before = self.feat_path.read_bytes()
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "p1-feat-002",
             "--status", "blocked"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("--blocked-reason", err)
        self.assertEqual(before, self.feat_path.read_bytes())  # file untouched

    def test_set_feature_blocked_with_reason(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "p1-feat-002",
             "--status", "blocked", "--blocked-reason", "upstream broken"]
        )
        self.assertEqual(rc, 0, err)
        feat = self.reload_data()["plans"][0]["features"][1]
        self.assertEqual(feat["status"], "blocked")
        self.assertEqual(feat["blocked_reason"], "upstream broken")

    def test_set_feature_clears_stale_reason(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "p1-feat-003",
             "--status", "completed"]
        )
        self.assertEqual(rc, 0, err)
        feat = self.reload_data()["plans"][0]["features"][2]
        self.assertEqual(feat["status"], "completed")
        self.assertNotIn("blocked_reason", feat)

    def test_set_feature_invalid_enum(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "p1-feat-002",
             "--status", "done"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("must be one of", err)

    def test_set_feature_not_found(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "pX-feat-999",
             "--status", "completed"]
        )
        self.assertEqual(rc, 1)
        self.assertIn("not found", err)

    def test_set_feature_ambiguous_id(self):
        dup = {
            "id": "p2",
            "name": "other plan",
            "status": "in_progress",
            "features": [{"id": "p1-feat-001", "title": "dup", "status": "pending"}],
        }
        self.feat_path.write_text(
            json.dumps(make_features([PLAN_P1, dup]), ensure_ascii=False), encoding="utf-8"
        )
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-feature", "p1-feat-001",
             "--status", "completed"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("ambiguous", err)

    # ---- --set-plan ----

    def test_set_plan_completed(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-plan", "p1", "--status", "completed"]
        )
        self.assertEqual(rc, 0, err)
        self.assertIn("OK plan p1 status=completed", out)
        self.assertEqual(self.reload_data()["plans"][0]["status"], "completed")

    def test_set_plan_invalid_enum(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-plan", "p1", "--status", "done"]
        )
        self.assertEqual(rc, 2)

    def test_set_plan_not_found(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--set-plan", "pX", "--status", "completed"]
        )
        self.assertEqual(rc, 1)

    # ---- --plan-state ----

    def test_plan_state_can_complete(self):
        plan = {
            "id": "p9", "name": "all done", "status": "in_progress",
            "features": [{"id": "p9-feat-001", "title": "t", "status": "completed"}],
        }
        self.feat_path.write_text(
            json.dumps(make_features([plan]), ensure_ascii=False), encoding="utf-8"
        )
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--plan-state", "p9"]
        )
        self.assertEqual(rc, 0, err)
        state = json.loads(out)
        self.assertTrue(state["can_complete"])
        self.assertEqual(state["counts"]["completed"], 1)
        self.assertEqual(state["plan_id"], "p9")
        self.assertEqual(state["blocked_ids"], [])

    def test_plan_state_with_blocked(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--plan-state", "p1"]
        )
        self.assertEqual(rc, 0, err)
        state = json.loads(out)
        self.assertFalse(state["can_complete"])
        self.assertEqual(state["counts"]["blocked"], 1)
        self.assertEqual(state["counts"]["pending"], 1)
        self.assertEqual(state["blocked_ids"], ["p1-feat-003"])

    def test_plan_state_not_found(self):
        rc, out, err = self.run_cli(
            ["--file", str(self.feat_path), "--plan-state", "pX"]
        )
        self.assertEqual(rc, 1)
        self.assertIn("not found", err)

    # ---- default path resolution ----

    def test_default_path_via_project_dir(self):
        project = self.tmp / "proj"
        (project / ".ghs").mkdir(parents=True)
        (project / ".ghs" / "features.json").write_text(
            json.dumps(make_features([PLAN_P1]), ensure_ascii=False), encoding="utf-8"
        )
        rc, out, err = self.run_cli(
            ["--set-feature", "p1-feat-002", "--status", "completed"],
            cwd=str(project),
        )
        self.assertEqual(rc, 0, err)
        data = json.loads(
            (project / ".ghs" / "features.json").read_text(encoding="utf-8")
        )
        self.assertEqual(data["plans"][0]["features"][1]["status"], "completed")


class UpdateFeaturesUnitTests(unittest.TestCase):
    def test_locate_feature_ambiguous_raises_valueerror(self):
        data = make_features([
            {"id": "a", "features": [{"id": "dup", "status": "pending"}]},
            {"id": "b", "features": [{"id": "dup", "status": "pending"}]},
        ])
        with self.assertRaises(ValueError):
            helper.locate_feature(data, "dup")

    def test_locate_feature_missing_raises_keyerror(self):
        with self.assertRaises(KeyError):
            helper.locate_feature(make_features([PLAN_P1]), "nope")

    def test_compute_plan_state_mixed_counts(self):
        state = helper.compute_plan_state(make_features([PLAN_P1]), "p1")
        self.assertEqual(
            state["counts"],
            {"completed": 1, "in_progress": 0, "pending": 1, "blocked": 1},
        )
        self.assertFalse(state["can_complete"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `command python3 -m unittest discover -s plugin/shared/scripts -p "test_update_features.py" -v`
Expected: ERROR/FAIL — `ModuleNotFoundError: No module named 'update_features'`（模块尚不存在）

- [ ] **Step 3: 实现脚本** — 新建 `plugin/shared/scripts/update_features.py`，内容如下（完整文件）：

```python
#!/usr/bin/env python3
"""Read-modify-write feature/plan status in .ghs/features.json.

ghs-code and ghs-archive mutate feature/plan status exclusively through this
script. Hand-editing features.json or inline `python -c` snippets are
forbidden: multi-line `-c` bodies get wrapped into a temporary batch script
by the Windows shell and fail unpredictably, and hand-rolled full-file
rewrites risk silently dropping fields. This helper performs a strict
read-modify-write (unknown fields are preserved verbatim), always saves
UTF-8 (atomic replace), and validates every status against the schema
enumerations enforced by validate_structure.py.

Usage:
    command python3 update_features.py \
        --file <PROJECT_DIR>/.ghs/features.json \
        --set-feature <feature_id> --status completed

    command python3 update_features.py \
        --set-feature <feature_id> --status blocked --blocked-reason "waiting for API"

    command python3 update_features.py --set-plan <plan_id> --status completed

    command python3 update_features.py --plan-state <plan_id>

Without --file, the features.json path is resolved via resolve_project_dir
(walk up from cwd to the nearest directory containing .ghs/).

Output:
    --set-feature / --set-plan: single ASCII confirmation line on stdout.
    --plan-state: single-line JSON on stdout:
        {"plan_id": "...", "counts": {"completed": N, "in_progress": N,
         "pending": N, "blocked": N}, "can_complete": <bool>,
         "blocked_ids": [...]}

Exit codes:
    0 - success
    1 - feature/plan id not found
    2 - invalid arguments / ambiguous feature id / missing or malformed
        features.json / IO error
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from ghs_compat import force_utf8_stdio
from resolve_project_dir import find_project_dir

FEATURE_STATUS_VALUES = ("pending", "in_progress", "completed", "blocked")
PLAN_STATUS_VALUES = ("planning", "in_progress", "completed", "on_hold")


def load_features(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"features.json not found: {path}")
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read features.json: {exc}") from None
    if not isinstance(data, dict):
        raise ValueError("features.json must contain a JSON object")
    return data


def write_features(path: Path, data: dict) -> None:
    """Serialize data as UTF-8 JSON and atomically replace the file.

    ensure_ascii=False keeps non-ASCII values as literal UTF-8 characters,
    matching the repo-wide JSON storage convention.
    """
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def locate_feature(data: dict, feature_id: str) -> "tuple[dict, dict]":
    """Return (plan, feature) for feature_id across plans[].features[].

    Raises KeyError when the id does not exist and ValueError when the id
    appears under more than one plan (ambiguous — refuse to guess).
    """
    hits = []
    for plan in data.get("plans", []):
        for feature in plan.get("features", []):
            if feature.get("id") == feature_id:
                hits.append((plan, feature))
    if not hits:
        raise KeyError(f"feature id not found: {feature_id}")
    if len(hits) > 1:
        owner_ids = ", ".join(p.get("id", "?") for p, _ in hits)
        raise ValueError(
            f"ambiguous feature id {feature_id!r}: present in plans ({owner_ids}); "
            "feature ids must be unique across plans"
        )
    return hits[0]


def locate_plan(data: dict, plan_id: str) -> dict:
    for plan in data.get("plans", []):
        if plan.get("id") == plan_id:
            return plan
    raise KeyError(f"plan id not found: {plan_id}")


def compute_plan_state(data: dict, plan_id: str) -> dict:
    """Return the plan completion state consumed by ghs-code/ghs-archive closings."""
    plan = locate_plan(data, plan_id)
    counts = {"completed": 0, "in_progress": 0, "pending": 0, "blocked": 0}
    blocked_ids = []
    for feature in plan.get("features", []):
        status = feature.get("status", "")
        if status in counts:
            counts[status] += 1
        if status == "blocked":
            blocked_ids.append(feature.get("id", ""))
    can_complete = (
        counts["completed"] >= 1
        and counts["pending"] == 0
        and counts["in_progress"] == 0
        and counts["blocked"] == 0
    )
    return {
        "plan_id": plan_id,
        "counts": counts,
        "can_complete": can_complete,
        "blocked_ids": blocked_ids,
    }


def main() -> int:
    force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Read-modify-write feature/plan status in .ghs/features.json."
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Path to features.json (default: resolve project dir from cwd)",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--set-feature", metavar="FEATURE_ID", default=None,
        help="Set one feature's status",
    )
    target.add_argument(
        "--set-plan", metavar="PLAN_ID", default=None,
        help="Set one plan's status",
    )
    target.add_argument(
        "--plan-state", metavar="PLAN_ID", default=None,
        help="Print the plan completion state as single-line JSON",
    )
    parser.add_argument(
        "--status",
        default=None,
        help=(
            "New status for --set-feature "
            f"({' | '.join(FEATURE_STATUS_VALUES)}) or --set-plan "
            f"({' | '.join(PLAN_STATUS_VALUES)})"
        ),
    )
    parser.add_argument(
        "--blocked-reason",
        default=None,
        help="Required with --set-feature --status blocked",
    )

    args = parser.parse_args()

    # --- argument cross-validation (exit 2, before touching any file) ---
    if (args.set_feature or args.set_plan) and not args.status:
        print(
            "update_features: error: --status is required with "
            "--set-feature/--set-plan",
            file=sys.stderr,
        )
        return 2
    if args.plan_state and args.status is not None:
        print(
            "update_features: error: --status is not valid with --plan-state",
            file=sys.stderr,
        )
        return 2
    if args.set_feature:
        if args.status not in FEATURE_STATUS_VALUES:
            print(
                f"update_features: error: --status must be one of "
                f"{' | '.join(FEATURE_STATUS_VALUES)}, got {args.status!r}",
                file=sys.stderr,
            )
            return 2
        if args.status == "blocked" and not (
            args.blocked_reason and args.blocked_reason.strip()
        ):
            print(
                "update_features: error: --blocked-reason is required with "
                "--status blocked",
                file=sys.stderr,
            )
            return 2
        if args.status != "blocked" and args.blocked_reason is not None:
            print(
                "update_features: error: --blocked-reason is only valid with "
                "--status blocked",
                file=sys.stderr,
            )
            return 2
    if args.set_plan and args.status not in PLAN_STATUS_VALUES:
        print(
            f"update_features: error: --status must be one of "
            f"{' | '.join(PLAN_STATUS_VALUES)}, got {args.status!r}",
            file=sys.stderr,
        )
        return 2
    if args.blocked_reason and not args.set_feature:
        print(
            "update_features: error: --blocked-reason is only valid with "
            "--set-feature",
            file=sys.stderr,
        )
        return 2

    # --- resolve features.json path ---
    if args.file:
        path = Path(args.file)
    else:
        project_dir = find_project_dir(Path.cwd())
        if project_dir is None:
            print(
                "update_features: error: no project directory found "
                "(no .ghs/ with features.json or progress.md in any parent "
                "directory)",
                file=sys.stderr,
            )
            return 2
        path = project_dir / ".ghs" / "features.json"

    try:
        data = load_features(path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"update_features: error: {exc}", file=sys.stderr)
        return 2

    # --- read-only branch ---
    if args.plan_state:
        try:
            state = compute_plan_state(data, args.plan_state)
        except KeyError as exc:
            print(f"update_features: error: {exc}", file=sys.stderr)
            return 1
        # ensure_ascii=True: ids are ASCII, keeps stdout single-line ASCII.
        print(json.dumps(state, ensure_ascii=True))
        return 0

    # --- mutation branches (locate BEFORE write so errors leave the file untouched) ---
    try:
        if args.set_feature:
            _plan, feature = locate_feature(data, args.set_feature)
            feature["status"] = args.status
            if args.status == "blocked":
                feature["blocked_reason"] = args.blocked_reason.strip()
            elif "blocked_reason" in feature:
                # A stale reason on a non-blocked feature would mislead status
                # consumers; drop it.
                del feature["blocked_reason"]
            print(f"OK feature {args.set_feature} status={args.status}")
        else:
            plan = locate_plan(data, args.set_plan)
            plan["status"] = args.status
            print(f"OK plan {args.set_plan} status={args.status}")
    except KeyError as exc:
        print(f"update_features: error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"update_features: error: {exc}", file=sys.stderr)
        return 2

    try:
        write_features(path, data)
    except OSError as exc:
        print(
            f"update_features: error: cannot write features.json: {exc}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

实现备注（给评审者）：`--set-feature` 把状态改离 `blocked` 时自动删除残留的 `blocked_reason`（spec 未规定；理由——残留 reason 会误导状态消费者，且 schema 注明该字段 `used_with_status: blocked`）。

- [ ] **Step 4: 运行测试确认通过**

Run: `command python3 -m unittest discover -s plugin/shared/scripts -p "test_update_features.py" -v`
Expected: OK，17 个测试全过

- [ ] **Step 5: 全量回归确认无破坏**

Run: `command python3 -m unittest discover -s plugin/shared/scripts -v`
Expected: OK（原 126 + 新 17 = 143 个测试全过）

- [ ] **Step 6: 提交**

```bash
git add plugin/shared/scripts/update_features.py plugin/shared/scripts/test_update_features.py
git commit -m "feat(scripts): 新增 update_features.py——features.json 状态变更唯一脚本入口

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: `parallel_utils.py` 多计划显式报错

**Files:**
- Modify: `plugin/shared/scripts/parallel_utils.py`（`get_ready_features` 约 95-102 行 else 分支、main 约 305-307 行调用处、`--plan-id` help 约 244 行）
- Test: `plugin/shared/scripts/test_parallel_utils.py`（文件末尾追加测试类）

**Interfaces:**
- Consumes: 现有 `get_ready_features(features_data: Dict, plan_id: Optional[str]) -> Tuple[List[Dict], List[Dict], List[List[str]], List[str]]`（签名不变）。
- Produces: 新异常类 `AmbiguousPlanError(ValueError)`；无 `--plan-id` 且 `plans[]` 条目数 > 1 时 `get_ready_features` raise `AmbiguousPlanError`，CLI 捕获后 stderr 报错并 exit 2（stdout 无输出）。

- [ ] **Step 1: 先确认调用面** — 确认没有其他调用方依赖旧的静默默认行为：

Run: `grep -rn "get_ready_features" plugin/ --include="*.py" --include="*.md"`
Expected: 仅 `parallel_utils.py`（定义 + main 调用）、`test_parallel_utils.py`、SKILL.md/references 文档提及。若发现其他 Python 调用方传多计划数据且不传 plan_id，停下来报告。

- [ ] **Step 2: 追加失败测试** — 在 `plugin/shared/scripts/test_parallel_utils.py` 文件末尾（`if __name__ == "__main__":` 之前）追加：

```python
class PlanSelectionGuardTests(unittest.TestCase):
    """Without --plan-id, multiple plans must be a hard error (exit 2 on
    stderr), never a silent plans[0] guess."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name)
        (self.project / ".ghs").mkdir(parents=True)

    def write_features(self, plan_ids):
        plans = [
            {
                "id": pid,
                "name": f"plan {pid}",
                "status": "in_progress",
                "features": [
                    {"id": f"{pid}-feat-001", "title": "t", "status": "pending"}
                ],
            }
            for pid in plan_ids
        ]
        data = {"project": {"name": "demo"}, "plans": plans}
        (self.project / ".ghs" / "features.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def run_cli(self, *extra):
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "parallel_utils.py"),
            "--project-dir",
            str(self.project),
        ] + list(extra)
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_multiple_plans_without_plan_id_errors(self):
        self.write_features(["pa", "pb"])
        rc, out, err = self.run_cli()
        self.assertEqual(rc, 2)
        self.assertIn("pa", err)
        self.assertIn("pb", err)
        self.assertIn("--plan-id", err)
        self.assertNotIn("ready_features", out)  # stdout stays clean

    def test_single_plan_without_plan_id_defaults(self):
        self.write_features(["only"])
        rc, out, err = self.run_cli()
        self.assertEqual(rc, 0, err)
        self.assertIn("ready_features", out)

    def test_explicit_plan_id_wins(self):
        self.write_features(["pa", "pb"])
        rc, out, err = self.run_cli("--plan-id", "pb")
        self.assertEqual(rc, 0, err)
        self.assertIn("pb-feat-001", out)
        self.assertNotIn("pa-feat-001", out)
```

- [ ] **Step 3: 运行新测试确认失败**

Run: `command python3 -m unittest discover -s plugin/shared/scripts -p "test_parallel_utils.py" -v`
Expected: `test_multiple_plans_without_plan_id_errors` FAIL（当前静默取 plans[0]，exit 0）——其余两个 PASS

- [ ] **Step 4: 实现** — 三处修改：

4a. 模块级（在 `get_ready_features` 定义之前）新增异常类：

```python
class AmbiguousPlanError(ValueError):
    """Raised when no plan_id is given and features.json holds multiple plans."""
```

4b. 替换 `get_ready_features` 的 else 分支（现 95-102 行）：

```python
    else:
        # No plan_id given: exactly one plan is unambiguous; multiple plans
        # must be a hard error so a silent plans[0] guess can never pick
        # the wrong plan (dogfood incident: user asked for p2, got p1).
        if len(plans) > 1:
            plan_ids = ", ".join(str(p.get("id", "?")) for p in plans)
            raise AmbiguousPlanError(
                f"multiple plans present ({plan_ids}); pass plan_id explicitly"
            )
        if plans:
            plan = plans[0]
```

同时更新该函数 docstring 中的一行（现 76-77 行）：

```python
        plan_id: Optional plan ID to filter by. If None, exactly one plan
                 is required (AmbiguousPlanError otherwise).
```

4c. main() 中包住调用处（现 305-307 行）：

```python
    try:
        ready, skipped, cycles, cycle_feature_ids = get_ready_features(
            features_data, plan_id=args.plan_id
        )
    except AmbiguousPlanError as e:
        print(f"parallel_utils: error: {e}", file=sys.stderr)
        return 2
```

4d. `--plan-id` 的 help 文本（现 244 行）改为：

```python
        help="Plan ID to analyze (required when features.json contains multiple plans)",
```

- [ ] **Step 5: 运行测试确认通过**

Run: `command python3 -m unittest discover -s plugin/shared/scripts -p "test_parallel_utils.py" -v`
Expected: OK（原有测试 + 新 3 个全过）

- [ ] **Step 6: 提交**

```bash
git add plugin/shared/scripts/parallel_utils.py plugin/shared/scripts/test_parallel_utils.py
git commit -m "fix(scripts): parallel_utils 多计划无 --plan-id 时显式报错，消灭静默选错计划

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: `archive_plans.py` 归档目录名消毒

**Files:**
- Modify: `plugin/shared/scripts/archive_plans.py`（`archive_plan_files` 约 56 行目录名派生处；顶部 imports 加 `re`）
- Test: `plugin/shared/scripts/test_archive_plans.py`（文件末尾追加测试类）

**Interfaces:**
- Consumes: 现有 `archive_plan_files(plan: Dict, features_data: Dict, project_dir: Path, archived_path: Path) -> Tuple[Path, Path]`（签名不变）。
- Produces: 模块级函数 `sanitize_filename_component(raw: str) -> str`（剔除 `[\\/:*?"<>|]` 与 ASCII 控制字符、空格转 `_`、转小写；可为空串——回退逻辑在调用点做，空则用 plan_id）。

- [ ] **Step 1: 追加失败测试** — 在 `plugin/shared/scripts/test_archive_plans.py` 文件末尾（`if __name__ == "__main__":` 之前）追加。先确认文件顶部 `SCRIPT_DIR` 赋值行之后有 `import archive_plans`（若无需补一行）：

```python
class ArchiveFolderSanitizationTests(unittest.TestCase):
    """Plan names containing Windows-illegal characters must not crash
    archiving (dogfood incident: NotADirectoryError on ':'). Folder names
    are sanitized; archived plan DATA keeps the original name verbatim."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name)
        self.archived = self.project / "archived"
        self.archived.mkdir(parents=True)

    def test_folder_name_sanitized_data_preserved(self):
        original_name = 'dogfood 修复:Windows/编码 "quoted" 计划'
        plan = {
            "id": "px",
            "name": original_name,
            "status": "completed",
            "features": [
                {"id": "px-feat-001", "title": "t", "status": "completed"}
            ],
        }
        features_data = {"project": {"name": "demo"}, "plans": [plan]}

        feat_path, _prog_path = archive_plans.archive_plan_files(
            plan, features_data, self.project, self.archived
        )

        folder = feat_path.parent
        self.assertTrue(folder.exists())
        self.assertTrue(folder.name.startswith("px_"))
        for ch in '\\/:*?"<>|':
            self.assertNotIn(ch, folder.name)
        # Archived DATA keeps the original name verbatim.
        archived = json.loads(feat_path.read_text(encoding="utf-8"))
        self.assertEqual(archived["archived_plan"]["name"], original_name)

    def test_empty_name_falls_back_to_plan_id(self):
        plan = {
            "id": "py",
            "name": '///:***',
            "status": "completed",
            "features": [
                {"id": "py-feat-001", "title": "t", "status": "completed"}
            ],
        }
        features_data = {"project": {"name": "demo"}, "plans": [plan]}
        feat_path, _prog_path = archive_plans.archive_plan_files(
            plan, features_data, self.project, self.archived
        )
        # All chars stripped -> sanitized part empty -> folder falls back to plan id.
        self.assertTrue(feat_path.parent.name.startswith("py_"))
```

- [ ] **Step 2: 运行新测试确认失败**

Run: `command python3 -m unittest discover -s plugin/shared/scripts -p "test_archive_plans.py" -v`
Expected: `test_folder_name_sanitized_data_preserved` ERROR — `NotADirectoryError: [WinError 267]`（复现 dogfood 崩溃；Windows 上 `:` 非法）

- [ ] **Step 3: 实现** — 两处修改：

3a. 顶部 imports 区加一行（与既有 import 风格一致）：

```python
import re
```

3b. 在 `archive_plan_files` 定义之前新增模块级函数：

```python
# Windows-illegal filename characters + ASCII control chars.
_ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_filename_component(raw: str) -> str:
    """Make a plan name safe for use in an archive folder name.

    Strips Windows-illegal characters and ASCII control chars, replaces
    spaces with underscores, lowercases. May return an empty string —
    callers fall back to the plan id.
    """
    return _ILLEGAL_FILENAME_CHARS.sub("", raw.replace(" ", "_")).lower()
```

3c. 替换 `archive_plan_files` 中的目录名派生行（现 56-59 行）：

```python
    plan_name = sanitize_filename_component(plan.get("name", ""))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Empty sanitized name (e.g. name was all illegal chars) falls back to plan id.
    archive_folder = archived_path / f"{plan_id}_{plan_name or plan_id}_{timestamp}"
```

注意：数据侧（`archived_plan_data` 中的 `plan` 原始字典）不动，归档数据保留原名。

- [ ] **Step 4: 运行测试确认通过**

Run: `command python3 -m unittest discover -s plugin/shared/scripts -p "test_archive_plans.py" -v`
Expected: OK（原有测试 + 新 2 个全过）

- [ ] **Step 5: 提交**

```bash
git add plugin/shared/scripts/archive_plans.py plugin/shared/scripts/test_archive_plans.py
git commit -m "fix(scripts): archive_plans 归档目录名消毒，修复 Windows 非法字符崩溃

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: `ghs-code/SKILL.md` 状态脚本化 + 计划完成检测

**Files:**
- Modify: `plugin/skills/ghs-code/SKILL.md`（4 处：Step 5 第 2 步、Step 5 末尾新增第 4 步、State Update Phase、并行 pre-flight 命令）

**Interfaces:**
- Consumes: Task 1 的 `update_features.py` CLI、Task 2 的 `--plan-id` 必传约定。
- Produces: SKILL.md 行为条款——所有 features.json 状态写入经 `update_features.py`；单特性与 `--parallel` 两模式收尾均含计划完成检测（AskUserQuestion 确认后翻转）。

本任务为纯文档任务（无测试可跑），每步用 Edit 精确替换，改完用 grep 断言验证。

- [ ] **Step 1: 替换单特性模式 Step 5 第 2 步**

old_string:
```
2. Update the feature status in `.ghs/features.json` (only change `status` field):
   - `completed` — all acceptance criteria met, tests pass
   - `blocked` — cannot proceed, document reason in `blocked_reason`
```

new_string:
```
2. Update the feature status via the helper (script-only, Windows-safe — NEVER hand-edit `.ghs/features.json`, NEVER use inline `python -c`; same rationale as `update_plan_status.py` in ghs-plan):
   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_features.py \
     --file <PROJECT_DIR>/.ghs/features.json \
     --set-feature <feature_id> --status completed
   ```
   - `completed` — all acceptance criteria met, tests pass
   - `blocked` — cannot proceed; append `--blocked-reason "<reason>"`
```

- [ ] **Step 2: Step 5 新增第 3 步（计划完成检测），原第 3 步顺延为第 4 步**

检测必须发生在 progress 条目写入**之前**，条目的 Next Steps 才能带上检测结果。

2a. old_string:
```
3. Update `.ghs/progress.md` with session summary at the **top** of the sessions section.
```
new_string:
```
3. **Plan completion check** — run:
   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_features.py \
     --file <PROJECT_DIR>/.ghs/features.json --plan-state <plan_id>
   ```
   - `"can_complete": true` → use AskUserQuestion:「该计划下全部特性已完成，是否将计划标记为 completed？」On confirm run `--set-plan <plan_id> --status completed`; on decline keep `in_progress`.
   - `false` → do NOT flip; report `counts` and `blocked_ids` to the user.
   Include the outcome (including "kept in_progress") in the session entry's Next Steps.

4. Update `.ghs/progress.md` with session summary at the **top** of the sessions section.
```

- [ ] **Step 3: 替换并行模式 State Update Phase**

old_string:
```
1. Update `.ghs/features.json` — completed features get `status: "completed"`, blocked get `status: "blocked"`
2. Add parallel orchestration summary to top of `.ghs/progress.md` sessions section
```

new_string:
```
1. For each parsed result, update the feature status via the helper (script-only — NEVER hand-edit `.ghs/features.json`, NEVER inline `python -c`):
   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_features.py \
     --file <PROJECT_DIR>/.ghs/features.json \
     --set-feature <feature_id> --status completed
   ```
   Use `--status blocked --blocked-reason "<reason>"` for blocked results.
2. **Plan completion check** — after all features in the plan are marked, run:
   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_features.py \
     --file <PROJECT_DIR>/.ghs/features.json --plan-state <plan_id>
   ```
   - `"can_complete": true` → use AskUserQuestion:「该计划下全部特性已完成，是否将计划标记为 completed？」On confirm run `--set-plan <plan_id> --status completed`; on decline keep `in_progress`.
   - `false` → do NOT flip; report `counts` (list `blocked_ids` if any) to the user.
3. Add parallel orchestration summary to top of `.ghs/progress.md` sessions section, recording the plan-completion outcome (including "kept in_progress") in Next Steps
```

- [ ] **Step 4: 并行 pre-flight 命令必传 `--plan-id`**

old_string:
```
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parallel_utils.py --project-dir "<PROJECT_DIR>" --max-parallel <N>
```

new_string:
```
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parallel_utils.py --project-dir "<PROJECT_DIR>" --plan-id <plan_id> --max-parallel <N>
```

- [ ] **Step 5: grep 断言验证**

Run:
```bash
grep -c "update_features.py" plugin/skills/ghs-code/SKILL.md
grep -c "Plan completion check" plugin/skills/ghs-code/SKILL.md
grep -n "Update the feature status in \`.ghs/features.json\`" plugin/skills/ghs-code/SKILL.md
grep -n "completed features get \`status: \"completed\"\`" plugin/skills/ghs-code/SKILL.md
grep -n -- "--plan-id <plan_id>" plugin/skills/ghs-code/SKILL.md
```
Expected: 依次 ≥4、2、无命中、无命中、≥1

- [ ] **Step 6: 提交**

```bash
git add plugin/skills/ghs-code/SKILL.md
git commit -m "docs(skills): ghs-code 状态写入脚本化并新增计划完成检测闭环

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: `ghs-archive/SKILL.md` 兜底翻转

**Files:**
- Modify: `plugin/skills/ghs-archive/SKILL.md`（「If No Completed Plans」小节整体替换）

**Interfaces:**
- Consumes: Task 1 的 `--plan-state` / `--set-plan` CLI。

- [ ] **Step 1: 整体替换「If No Completed Plans」小节**

old_string:
```
## If No Completed Plans

If there are no completed plans, tell the user. They may need to:
- Mark the plan as completed (all features done)
- Or use `/ghs:force-archive` if they want to archive regardless of status
```

new_string:
```
## If No Completed Plans

If there are no completed plans, probe each active plan first — the plan status may simply be stale (all features done, status never flipped):

1. For each plan in `.ghs/features.json`, run:
   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_features.py \
     --file <PROJECT_DIR>/.ghs/features.json --plan-state <plan_id>
   ```
2. If a plan reports `"can_complete": true` but the plan status is not `completed`, use AskUserQuestion:「计划 <plan_id> 全部特性已完成但状态未翻转，是否标记为 completed 并继续归档？」On confirm, run `--set-plan <plan_id> --status completed`, then re-run Step 1 (`archive_plans.py --list`) and continue the normal flow.
3. If every remaining plan still has pending/in_progress/blocked features, tell the user. They may need to:
   - Complete the remaining features first (`/ghs:code`)
   - Or use `/ghs:force-archive` if they want to archive regardless of status
```

- [ ] **Step 2: grep 断言验证**

Run:
```bash
grep -c "plan-state" plugin/skills/ghs-archive/SKILL.md
grep -n "Mark the plan as completed (all features done)" plugin/skills/ghs-archive/SKILL.md
```
Expected: ≥1、无命中

- [ ] **Step 3: 提交**

```bash
git add plugin/skills/ghs-archive/SKILL.md
git commit -m "docs(skills): ghs-archive 无 completed 计划时兜底探测并代为翻转

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: references 联动（coding-agent.md ×5、examples.md ×2）

**Files:**
- Modify: `plugin/shared/references/coding-agent.md`（275、278、328、329、338 行）
- Modify: `plugin/shared/references/examples.md`（291、299 行）

**Interfaces:**
- Consumes: Task 1 的 CLI。

- [ ] **Step 1: coding-agent.md 五处替换**

1° old_string:
```
     2. Update `.ghs/features.json` for `<feature_id>` with `status: "completed"`. Run lint/build to verify code quality. Verify acceptance criteria. Proceed to next feature.
```
new_string:
```
     2. Mark the feature completed via the helper: `command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_features.py --file <PROJECT_DIR>/.ghs/features.json --set-feature <feature_id> --status completed`. Run lint/build to verify code quality. Verify acceptance criteria. Proceed to next feature.
```

2° old_string:
```
   - **`blocked`** → Update `.ghs/features.json` with `status: "blocked"` and `blocked_reason: <reason from JSON>`. Record result and proceed.
```
new_string:
```
   - **`blocked`** → Mark blocked via the helper: `update_features.py --set-feature <feature_id> --status blocked --blocked-reason "<reason from JSON>"`. Record result and proceed.
```

3° old_string（表格行，仅改中间「Dispatcher behavior」列，行尾两列原样保留）:
```
| **Manually mark as completed** | Update `.ghs/features.json` with `status: "completed"`. Annotate `.ghs/progress.md` noting "manually marked after format deviation retry" | `.ghs/features.json` written; `.ghs/progress.md` annotated | Always available — but only choose this after manually verifying (commit log + file diff) |
```
new_string:
```
| **Manually mark as completed** | Run `update_features.py --set-feature <feature_id> --status completed`. Annotate `.ghs/progress.md` noting "manually marked after format deviation retry" | `.ghs/features.json` written; `.ghs/progress.md` annotated | Always available — but only choose this after manually verifying (commit log + file diff) |
```

4° old_string:
```
| **Manually mark as blocked** | Update `.ghs/features.json` with `status: "blocked"` + user-supplied `blocked_reason`. Annotate `.ghs/progress.md` | `.ghs/features.json` written; `.ghs/progress.md` annotated | Always available |
```
new_string:
```
| **Manually mark as blocked** | Run `update_features.py --set-feature <feature_id> --status blocked --blocked-reason "<user-supplied reason>"`. Annotate `.ghs/progress.md` | `.ghs/features.json` written; `.ghs/progress.md` annotated | Always available |
```

5° old_string:
```
1. **Update .ghs/features.json** — Completed features get `status: "completed"`, blocked get `status: "blocked"` with `blocked_reason`
```
new_string:
```
1. **Update feature statuses via `update_features.py`** (script-only; never hand-edit) — `--set-feature <feature_id> --status completed` for completed, `--status blocked --blocked-reason "<reason>"` for blocked
```

- [ ] **Step 2: examples.md 两处替换**

1° old_string（To-Features Workflow）:
```
5. Update `.ghs/features.json` and `.ghs/progress.md`
```
new_string:
```
5. Create the plan entry in `.ghs/features.json` (initial Write) and add the session entry to `.ghs/progress.md`; later status mutations go through `update_features.py`
```

2° old_string（Coding Agent Workflow）:
```
5. Update `.ghs/progress.md` and `.ghs/features.json`
```
new_string:
```
5. Update `.ghs/progress.md`; feature status via `update_features.py --set-feature`
```

- [ ] **Step 3: grep 断言验证**

Run:
```bash
grep -n "Update \`.ghs/features.json\`" plugin/shared/references/coding-agent.md
grep -n "Update \`.ghs/features.json\` and \`.ghs/progress.md\`" plugin/shared/references/examples.md
grep -c "update_features.py" plugin/shared/references/coding-agent.md plugin/shared/references/examples.md
```
Expected: 前两条无命中；第三条 coding-agent.md ≥5、examples.md ≥2

- [ ] **Step 4: 提交**

```bash
git add plugin/shared/references/coding-agent.md plugin/shared/references/examples.md
git commit -m "docs(references): coding-agent/examples 状态更新指令对齐 update_features.py

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: 全量验证（验收门）

**Files:** 无新改动（只验证）；若验证暴露问题，回到对应 Task 修复后重跑本任务。

- [ ] **Step 1: 全量测试**

Run: `command python3 -m unittest discover -s plugin/shared/scripts -v`
Expected: OK（原 126 + 新增 22 = 148 个全过，0 failures 0 errors）

- [ ] **Step 2: 插件校验**

Run: `claude plugin validate`
Expected: 通过，无新增 error

- [ ] **Step 3: 真实 .ghs 冒烟（只读操作）**

Run:
```bash
command python3 plugin/shared/scripts/update_features.py --plan-state p1
command python3 plugin/shared/scripts/validate_structure.py --project-dir .
```
Expected: 第一条输出单行 JSON（p1 有 pending 特性，`can_complete` 为 false 属正常）；第二条结构校验通过

- [ ] **Step 4: 对照 spec 验收标准逐条核对**

对照 `docs/superpowers/specs/2026-10-24-plan-status-closed-loop-design.md` 的 6 条验收标准，逐条给出 通过/不通过 结论；全部通过后向用户汇报。
