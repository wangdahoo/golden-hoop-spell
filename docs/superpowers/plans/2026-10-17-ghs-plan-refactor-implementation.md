# ghs:plan 契约化重构 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/superpowers/specs/2026-10-17-ghs-plan-refactor-design.md`（下称 spec）落地 P0-P6 + P2.5：契约头冻结、designer/reviewer 全面重写、tasks_to_features.py 机械物化、评审环硬封顶、入口分诊、sprint→to-features 正名。

**Architecture:** ghs:plan 重写为 7 阶段契约驱动流程（Phase 0-6，全新整数编号）；plan 文档 = dispatcher 冻结的契约头 + designer 设计体 + 任务卡序列化尾；审批归档后由 `tasks_to_features.py` 把任务卡确定性物化为 features.json 的 plan 对象，主链收敛为 plan → code。评审合并 builder-check 为四步协议，硬封顶 2-4 次模型调用。

**Tech Stack:** Claude Code 插件（skills + references + Python 脚本）；脚本仅用标准库（unittest、argparse、json、re、pathlib）。

**Spec:** `docs/superpowers/specs/2026-10-17-ghs-plan-refactor-design.md` — 本计划逐条论自 spec；执行者必须同时持有两份文档。spec §5/§7/§9 的模板、schema、判据表为逐字权威，本计划不再复制论证只给落地文案。

## Global Constraints（抄自 spec，逐字生效）

- 模型档位不设：全链子代理（designer / reviewer / 快照）一律 coding agent 默认模型，移除现状 `haiku` 指定；
- 语言政策：LLM-facing 提示词英文、人读文档/commit message 中文、代码标识符/日志/错误信息英文（仓库 CLAUDE.md）；
- Python 调用一律 `command python3`，禁止裸 `python3`（仓库 CLAUDE.md）；
- 反棘轮：每个新增必须对应一笔删减（各项对应删减见 spec §5，落地时不得只增不删）；
- 无向下兼容：schema 正名后老项目 re-init 即可，不写迁移代码；
- P2.5 验收 = `grep -ri sprint plugin/ README*.md` 归零（内部标识符一并置换，不豁免）；
- P7（code 侧评审席）纯预案，**不实施、零改动** ghs:code 的行为协议；
- commit 拆分（spec §7 裁定）：① P2.5 正名；② P0+P1；③ P2（脚本 + Phase 6 + parser）；④ P3+P4；⑤ P5+P6；
- 文档模板标题用英文固定词（与任务卡标签一致、解析器友好），内容遵循语言政策用中文；
- commit message 末尾追加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`（系统裁定）。

## 文件结构总览（最终态）

| 文件 | 动作 | 负责任务 |
|---|---|---|
| `plugin/skills/ghs-sprint/` → `plugin/skills/ghs-to-features/` | 目录改名 + frontmatter/SKILL.md 重写描述 | T1 |
| `plugin/shared/references/sprint-agent.md` → `features-agent.md` | 改名 + 内容正名 + schema 更新 | T1 |
| `plugin/shared/scripts/archive_sprint.py` → `archive_plans.py` | 改名 + 标识符正名 | T1 |
| `plugin/shared/scripts/validate_structure.py` | 正则 `s`→`p` + 旧格式提示 | T1 |
| `plugin/shared/scripts/status.py`、`parallel_utils.py`、`init_project.py` | 标识符/输出正名 | T1 |
| `plugin/shared/assets/features.json`、`progress.md` | schema 键名/模板标题正名 | T1 |
| `plugin/.claude-plugin/plugin.json`、根 `CLAUDE.md`、`README.md`、`README-zh.md` | 术语正名 | T1 |
| `plugin/skills/ghs-{code,archive,force-archive,status,init,plan}/SKILL.md` | 术语正名（T2-T5 会再重写 ghs-plan） | T1 |
| `plugin/shared/references/coding-agent.md`、`examples.md` | 术语正名 | T1 |
| `plugin/skills/ghs-plan/SKILL.md` | 分阶段重写为 Phase 0-6（790 行 → 约 600 行） | T2/T3/T4/T5 |
| `plugin/shared/references/plan-designer.md` | 全面重写（163 行 → 约 190 行） | T2 |
| `plugin/shared/references/plan-reviewer.md` | 全面重写（193 行 → 约 230 行） | T4 |
| `plugin/shared/scripts/tasks_to_features.py` | 新增（约 300 行） | T3 |
| `plugin/shared/scripts/test_tasks_to_features.py` | 新增（unittest，约 400 行） | T3 |
| `plugin/shared/scripts/parse_delimited_output.py` + 测试 | signal 行 Unwarranted 计数小改 | T3 |

---

### Task 1: P2.5 正名 — sprint → to-features / plan（独立 commit ①）

**Files:**
- 改名：`plugin/skills/ghs-sprint/` → `plugin/skills/ghs-to-features/`；`plugin/shared/references/sprint-agent.md` → `features-agent.md`；`plugin/shared/scripts/archive_sprint.py` → `archive_plans.py`
- 修改：`plugin/skills/{ghs-code,ghs-archive,ghs-force-archive,ghs-status,ghs-init,ghs-plan}/SKILL.md`、`plugin/shared/references/{coding-agent.md,examples.md}`、`plugin/shared/scripts/{validate_structure.py,status.py,parallel_utils.py,init_project.py}`、`plugin/shared/assets/{features.json,progress.md}`、`plugin/.claude-plugin/plugin.json`、根 `CLAUDE.md`、`README.md`、`README-zh.md`

**Interfaces:**
- Produces（后续任务依赖）：schema 键 `plans[]`、ID 格式 `p{N}` / `p{N}-feat-{NNN}`、正则 `^p\d{1,4}$` / `^p\d{1,4}-feat-\d{3}$`、CLI `archive_plans.py`（参数不变）、`parallel_utils.py --plan-id`、progress.md 模板标题 `## Feature Planning`、脚本名 `tasks_to_features.py` 将在 T3 对接的 features.json 结构即本任务产物。
- 行为零变更：所有脚本输入输出协议除键名/ID 字符外不变。

**全局置换映射表**（大小写不敏感，按序应用；每文件应用后须复查语境，勿盲替）：

| 旧 | 新 | 说明 |
|---|---|---|
| `ghs:sprint` / `/ghs:sprint` | `ghs:to-features` / `/ghs:to-features` | 技能名 |
| `ghs-sprint` | `ghs-to-features` | 目录名 |
| `sprint-agent.md` | `features-agent.md` | 引用文件名 |
| `archive_sprint.py` | `archive_plans.py` | 脚本名 |
| `--sprint-id` | `--plan-id` | CLI 参数 |
| `sprint_id` / `sprint-name` / `sprint_name` | `plan_id` / `plan-name` / `plan_name` | 标识符 |
| `sprints` | `plans` | JSON 键 + 变量 |
| `s{N}-feat-{NNN}`（含示例 `s1-feat-001` 等） | `p{N}-feat-{NNN}`（`p1-feat-001`） | ID 格式 |
| `^s\d{1,4}$` / `^s\d{1,4}-feat-\d{3}$` | `^p\d{1,4}$` / `^p\d{1,4}-feat-\d{3}$` | 正则 |
| `Sprint ID` / `sprint ID` | `Plan ID` / `plan ID` | 术语 |
| `Sprint Agent` | `To-Features Agent` | 角色名 |
| `archived_sprint` | `archived_plan` | 归档 JSON 键 |
| `## Sprint Planning` | `## Feature Planning` | progress.md 标题 |
| `**Sprint**:` | `**Plan**:` | progress.md 字段行 |
| `Sprint`（散文/标题） | `Plan`（上下文要求时 `Feature group`） | 术语 |
| `sprint`（散文） | `plan` | 术语 |

Python 函数名置换（`archive_plans.py`）：`get_all_sprints`→`get_all_plans`、`get_completed_sprints`→`get_completed_plans`、`get_in_progress_sprint`→`get_in_progress_plan`、`archive_sprint_files`→`archive_plan_files`、`_entry_matches_sprint`→`_entry_matches_plan`、`extract_sprint_sessions`→`extract_plan_sessions`、`remove_archived_sprint`→`remove_archived_plan`、`remove_sprint_sessions`→`remove_plan_sessions`、`archive_completed_sprints`→`archive_completed_plans`。（`validate_structure.py`：`validate_sprint_id_format`→`validate_plan_id_format`、`validate_sprint`→`validate_plan`、`SPRINT_ID_PATTERN`→`PLAN_ID_PATTERN`。`parallel_utils.py`：`get_ready_features` 的 `sprint_id` 参数名、`--sprint-id`/`-s` flag、输出不变。`status.py`：`sprints` 变量与打印文案。）

- [ ] **Step 1: 目录与文件改名**

```bash
cd /c/github/golden-hoop-spell
git mv plugin/skills/ghs-sprint plugin/skills/ghs-to-features
git mv plugin/shared/references/sprint-agent.md plugin/shared/references/features-agent.md
git mv plugin/shared/scripts/archive_sprint.py plugin/shared/scripts/archive_plans.py
```

- [ ] **Step 2: 逐文件置换（按映射表 + 下列各文件的定点重写）**

对映射表覆盖的一般情形用编辑工具逐处替换；以下文件除机械置换外有**定点重写块**，逐字使用：

**2a. `plugin/skills/ghs-to-features/SKILL.md`** — frontmatter 整块替换为：

```markdown
---
name: ghs:to-features
description: "Turn a plan document or raw requirements into atomic, implementable features in `.ghs/features.json`. Also use to modify existing plans — add features, change priorities, or replan."
---
```

标题 `# Sprint Planning` → `# Feature Planning`；正文其余按映射表置换（`sprint` → `plan`，"Archive Completed Sprints" 步骤名改为 "Archive Completed Plans"，`**ID format**` 行改 `p{N}-feat-{NNN}`、`**Sprint ID format**` → `**Plan ID format**`：`p{N}`）。progress 模板块中 `## Sprint Planning - YYYY-MM-DD` → `## Feature Planning - YYYY-MM-DD`、`**Agent**: Sprint Agent` → `**Agent**: To-Features Agent`、`**Sprint**:` → `**Plan**:`、`### Sprint Goal` → `### Plan Goal`。文件内 27 处全数清零。

**2b. `plugin/shared/references/features-agent.md`** — 标题 `# Sprint Agent Reference` → `# To-Features Agent Reference`；TOC/Workflow/术语按映射表；`### features.json Structure` 示例 JSON 键 `"sprints"` → `"plans"`、`"id": "string (required, unique, format: s{number})"` → `format: p{number}`；`Sprint Status Values` → `Plan Status Values`；`Note: Feature IDs follow the format ...` 行改 `p{N}-feat-{NNN}`；Output Requirements 的 progress 模板同步 2a 的标题三行。

**2c. `plugin/shared/scripts/archive_plans.py`** — docstring 改 `"Archive completed plan files to .ghs/archived directory."`；函数名按映射表；`archived_sprint_data` 字典键 `"archived_sprint"` → `"archived_plan"`、`"original_sprint_id"` → `"original_plan_id"`；所有用户可见打印（如 `=== Sprint Archiver ===` → `=== Plan Archiver ===`、`Archiving sprint:` → `Archiving plan:`、`No completed sprints to archive.` → `No completed plans to archive.`、`No sprints found to archive.` → `No plans found to archive.`、`Archived N sprint(s)` → `Archived N plan(s)`、`Goal: {sprint.get('goal', ...)}` 行的变量同步）。会话匹配逻辑（`_entry_matches_plan` 的 header 前 11 行 ID 匹配）算法不变。

**2d. `plugin/shared/scripts/validate_structure.py`** — 正则两行：

```python
PLAN_ID_PATTERN = re.compile(r"^p\d{1,4}$")
FEATURE_ID_PATTERN = re.compile(r"^p\d{1,4}-feat-\d{3}$")
```

错误文案同步（`must match ^p\d{1,4}$, e.g. p1, p12, p1234` / `must match ^p\d{1,4}-feat-\d{3}$, e.g. p1-feat-001`）。`validate_features_json` 中读键 `data.get("sprints", [])` → `data.get("plans", [])`，报错文案 `'sprints' must be an array` → `'plans' must be an array`。**新增旧格式检测**：JSON 解析后若含 `sprints` 键而不含 `plans` 键，在 errors 前追加提示（英文，日志语义）：

```python
    if isinstance(data, dict) and "sprints" in data and "plans" not in data:
        errors.append(
            "old format detected (key 'sprints') — re-run /ghs:init to regenerate "
            ".ghs/features.json with the current schema"
        )
```

**2e. `plugin/shared/scripts/status.py`** — `features_data.get("sprints", [])` → `"plans"`；打印 `No sprints defined yet. Run Sprint Agent to plan features.` → `No plans defined yet. Run /ghs:to-features to plan features.`；`Sprint: {name}` → `Plan: {name}`；`Unnamed Sprint` → `Unnamed Plan`；status_emoji 字典与值不变；`sprint.get('goal', ...)` 保留（plan 对象的 `goal` 散文字段在 T3 才删除，本任务行为零变更）。

**2f. `plugin/shared/scripts/parallel_utils.py`** — `--sprint-id`/`-s` → `--plan-id`/`-p` 冲突检查：`-p` 已被 `--project-dir` 占用，**短选项改 `-i`**（`--plan-id`/`-i`）；`get_ready_features(features_data, sprint_id=...)` 参数名 → `plan_id`；docstring/注释/帮助文案同步（`Sprint ID to analyze` → `Plan ID to analyze`）。

**2g. `plugin/shared/scripts/init_project.py`** — `print("Next: Run Sprint Agent to define features.")` → `print("Next: Run /ghs:to-features to define features.")`。

**2h. `plugin/shared/assets/features.json`** — `"sprints": []` → `"plans": []`；`_schema_docs._description` 中 `'sprints'` → `'plans'`；`feature_example_blocked` 的 `"id": "s1-feat-003"` → `"p1-feat-003"`、`"dependencies": ["s1-feat-001"]` → `["p1-feat-001"]`。

**2i. `plugin/shared/assets/progress.md`** — 模板块：`**Agent**: Sprint | Coding` → `**Agent**: To-Features | Coding`；`**Sprint**: [Sprint ID if applicable]` → `**Plan**: [Plan ID if applicable]`。

**2j. `plugin/.claude-plugin/plugin.json`** — description 改 `"A skill suite for iterative planning, feature breakdown, and disciplined code delivery with Claude Code"`。

**2k. 六个下游 SKILL.md**（ghs-code 15 处 / ghs-archive 16 / ghs-force-archive 14 / ghs-status 4 / ghs-init 3 / ghs-plan 1）：按映射表置换；特别注意 —
- `ghs-code/SKILL.md`：frontmatter description `current sprint plan` → `current plan`；`/ghs:sprint` 引用 → `/ghs:to-features`；`<sprint_id>` 路径占位符 → `<plan_id>`（`.ghs/parallel/<plan_id>/`）；`find your feature by id == "<feature_id>" under sprints[].features[]` → `plans[].features[]`；"No uncompleted sprint found" → `No uncompleted plan found`；progress 模板 `**Sprint**:` → `**Plan**:`。
- `ghs-archive/SKILL.md` / `ghs-force-archive/SKILL.md`：`archive_sprint.py` → `archive_plans.py`；标题 `# Archive Completed Sprints` → `# Archive Completed Plans`（force 同理 `# Force Archive All Plans`）；**措辞**：凡"归档对象"写成"已完成 plan 的 feature 组"（避免读成归档 plan 文档），如 `Move completed sprints from ...` → `Move completed plans' feature groups from ...`；归档目录示例 `<sprint-id>` → `<plan-id>`。
- `ghs-status/SKILL.md`：description `active sprint` → `active plan`；`If there are no sprints, suggest running /ghs:sprint` → `If there are no plans, suggest running /ghs:to-features`。
- `ghs-init/SKILL.md`：`Sprint and feature tracking` → `Plan and feature tracking`；`run /ghs:sprint` → `run /ghs:to-features`。
- `ghs-plan/SKILL.md`：Phase 4 结束语 `use /ghs:sprint to break the plan into features` → `use /ghs:to-features to break the plan into features`（1 处兜底建议语）。

**2l. `plugin/shared/references/coding-agent.md`（14 处）** — `Current sprint status` → `Current plan status`；`--sprint-id "<SPRING_ID>"` → `--plan-id "<PLAN_ID>"`（顺带修正原拼写 SPRING）；`.ghs/parallel/<sprint_id>/` → `<plan_id>`；`under sprints[].features[]` → `plans[].features[]`；progress 模板 `**Sprint**:` → `**Plan**:`；其余按映射表。

**2m. `plugin/shared/references/examples.md`（18 处）** — `## Example 1: Authentication Sprint` → `## Example 1: Authentication Plan`；示例 JSON `"sprints"` → `"plans"`、`"name": "Authentication Sprint"` → `"Authentication Plan"`、全部 `s1-feat-NNN` → `p1-feat-NNN`；`## Sprint Planning Session (progress.md)` → `## Feature Planning Session (progress.md)`，条目模板同步 2i；`### Sprint Agent Workflow` → `### To-Features Agent Workflow`，`[sprint-agent.md](sprint-agent.md)` → `[features-agent.md](features-agent.md)`；归档目录示例 `s1_authentication_sprint_20240120_143000` → `p1_authentication_plan_20240120_143000`。

**2n. 根 `README.md` / `README-zh.md`** — 管线描述改主链：`init` → `plan` → `code` → `status`/`archive`（中文版同构），`/ghs:to-features` 作为替代入口单列一行；技能表行名 `/ghs:sprint` → `/ghs:to-features`，描述改 "将 plan 文档或裸需求拆解为原子 feature"（英文版 "Turn a plan document or raw requirements into atomic features"）；`/ghs:init`/`/ghs:archive` 行的 sprint 术语 → plan（归档行措辞同 2k 的"feature 组"）；Quickstart 示例 `/ghs:sprint docs/ghs/plans/...` 行删除，主链示例改为 `/ghs:plan` 之后直接 `/ghs:code`。

**2o. 根 `CLAUDE.md`** — Project Overview 段 `sprint` breaks work into features → `to-features` turns plans into features（英文段保持英文）；Architecture 段管线描述 `plan` generates technical designs ... `sprint` breaks work into features → 主链 plan → code + to-features 兜底入口；Conventions 段 `Feature IDs follow s{N}-feat-{NNN} format` → `p{N}-feat-{NNN}`。

- [ ] **Step 3: 残留扫描归零验证**

```bash
grep -ri sprint plugin/ README.md README-zh.md | grep -v "^plugin/shared/scripts/validate_structure.py" | wc -l
grep -c "sprint" plugin/shared/scripts/validate_structure.py
```

Expected: 第一条 `0`（历史 docs/ 目录不在本闸门内，勿动）；第二条 `2` — 唯一登记例外：validate_structure.py 旧格式检测块的字面量 `"sprints"`（检测旧键必须字面写出；Step 2d 强制逐字使用，与归零门互斥，裁定保留检测块）。若第一条非零，逐条处理后再进下一步。

- [ ] **Step 4: 语法与功能冒烟**

```bash
command python3 -m py_compile plugin/shared/scripts/archive_plans.py plugin/shared/scripts/validate_structure.py plugin/shared/scripts/status.py plugin/shared/scripts/parallel_utils.py plugin/shared/scripts/init_project.py plugin/shared/scripts/parse_delimited_output.py plugin/shared/scripts/parse_completion_signal.py
```

Expected: 退出码 0，无输出。然后冒烟（临时目录，不污染仓库）：

```bash
SMOKE=$(mktemp -d)
command python3 plugin/shared/scripts/init_project.py smoke -p "$SMOKE"
command python3 plugin/shared/scripts/validate_structure.py -p "$SMOKE"
command python3 plugin/shared/scripts/status.py -p "$SMOKE"
command python3 plugin/shared/scripts/archive_plans.py --list -p "$SMOKE"
grep -c '"plans"' "$SMOKE/.ghs/features.json"
rm -rf "$SMOKE"
```

Expected: init 成功建 `.ghs/`；validate 打 `✅ Validation passed!`；status 打 `No plans defined yet...`；archive list 打 `No completed plans found.`；grep 计数 `1`。

- [ ] **Step 5: 现有测试回归**

```bash
command python3 plugin/shared/scripts/test_parse_delimited_output.py 2>&1 | tail -3
command python3 plugin/shared/scripts/test_parse_completion_signal.py 2>&1 | tail -3
```

Expected: 两个 `OK`（本任务未触碰这两个脚本，防误伤）。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(naming): sprint 正名为 to-features / plan（schema plans[]、ID p{N}、archive_plans.py，行为零变更）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: P0+P1 — 契约头 + designer 全面重写（commit ②）

**Files:**
- Rewrite: `plugin/shared/references/plan-designer.md`（全量替换）
- Modify: `plugin/skills/ghs-plan/SKILL.md`（frontmatter、Flow Overview、Core Concepts、Phase 0/1/2/3 全新；旧 Phase 2/3/4 机械改号为 4/5/6 携带，T3/T4 再替换）

**Interfaces:**
- Consumes: T1 的 `plans[]` schema 与 `/ghs:to-features` 名称。
- Produces: 契约头模板（下述逐字节）、status.json 新 schema、designer 派发模板、`<<<PLAN_START>>>` 协议不变、`SPLIT_SUGGESTED: {理由}` 信号（T4/T5 的评审映射与兜底引用它）。T3 的 `tasks_to_features.py` 解析本任务定义的任务卡序列化格式；T4 的评审协议①步以契约头为映射基准。

**对应删减（随本任务生效，防只增不删）**：designer 正文 Background/Goals/Scope 节退役（契约头替代）；per-step checkbox 剧本退役；Testing Strategy 节退役；修订日志节退役；"Collaborating with the Reviewer" 完备性文化退役；designer `QUESTION` 信号退役（改裁量文化）。

- [ ] **Step 1: 重写 `plugin/shared/references/plan-designer.md`**

用以下全文替换（LLM-facing，英文；标题固定词英文、正文示例遵语言政策可中文）：

````markdown
# Plan Designer Instruction Reference

## Role

You design the body of a technical plan that continues a frozen contract header.

**Constitutional rule**: A plan is the set of decisions the implementer cannot make alone.
Your readers have never seen the kickoff conversation: an implementer who will execute the
tasks, and a script that materializes the task tail into a feature tracker. The contract
header (Intent / Goals / Non-Goals / Anti-Goals / Decisions / Open Space / Global
Constraints) is already written and frozen — the dispatcher owns it. You never modify,
restate, or contradict it. Everything downstream of it is your output.

## The Contract Is the Scope Boundary

The contract header is the single source of scope truth:

- Every section you write must map to a contract entry (a Goal, a Decision, an Open Space
  item, or a Global Constraint). If you cannot name the contract entry a section serves,
  delete the section — adding it anyway is the failure mode called *Unwarranted*, and
  reviewers are instructed to delete it.
- If the contract is missing something the design genuinely needs, do NOT silently expand
  scope. Note it in Assumptions as a contract deficiency and proceed with the narrowest
  workable reading.
- Conflict between contract and your body text is always resolved by cutting the body.

## Decision Discipline (both directions are failures)

- **Under-decision**: any line an implementer cannot act on without guessing — `TBD`,
  "handle edge cases appropriately", "choose a suitable library", "add proper validation".
  Each one is a gap.
- **Over-decision**: transcription, not design — a full function body when the signature,
  file location, and acceptance anchors already determine it. If removing the code changes
  no decision, remove the code.
- **Detail-default presumption** (replaces the old "minimal change" exhortation — it is
  checkable): do not invent schemas, validation layers, fallback paths, or abstractions
  unless (a) the contract establishes them, or (b) the addition prevents one specific,
  nameable implementation error. When (b) holds, name the error in one line.

## Proportion Self-Check

No numeric threshold — a ruler instead: if your design body is many times longer than the
contract header plus the task tail combined, go section by section and ask: *is this a
decision, or a transcription?* Cut transcription. Design that restates the obvious costs
reviewer attention and hides the real decisions.

## Plan Body Structure

Fixed English headings, content in the project's documentation language. Omit any
subsection that has no decision to carry — never write a section for completeness.

```markdown
## Current State
{Only the pre-existing facts needed to justify decisions: module responsibilities,
 key constraints. Reference the context snapshot instead of copying it.}

## Design
{Decisions + one-line reason each. Optional subsections, use as needed:
 Overall Approach / Data Model / Interface Design (exact signatures) /
 Key Flows / Error Handling. Omit empty subsections entirely.}

## Assumptions
- [ASSUMPTION] {decision} — {one-line reason}
{Write "None" if there are no discretionary calls.}

## Risks
{Only risks that would change a decision. One-line mitigation each.}
```

Then the task tail — one card per task, strict serialization (a script parses it):

```markdown
### Task {N}: {title}
- Files: {exact paths, comma-separated}
- Interfaces: {exact signatures, may span multiple lines}
- Points: {implementation points at one-reasonable-thing granularity —
   if a point needs more than one sentence to state plainly, split the task}
- Anchors:
  - {test name}: {assertion essentials}
  - {command}: {expected output}
  - [UNDEFINED-INPUT] {input category}: {expected behavior without crashing}
```

### Task card rules (parser-strict)

1. Headings are exactly `### Task {N}: {title}` with sequential N starting at 1.
2. Files are exact repo-relative paths, comma-separated — no globs, no "etc".
3. Anchors: every task has at least one; at most five (more is the signal to split the
   task). Test anchors use the test function name; command anchors use a runnable command.
   Empty criteria are forbidden — "works correctly" or "测试通过" are not anchors.
4. `[UNDEFINED-INPUT]` marks input categories the plan deliberately leaves unspecified:
   the anchor records the required non-crashing behavior.
5. Task cards carry NO status field — execution status lives in the feature tracker, not
   the plan.

## Discretion Culture (QUESTION is retired)

Do not emit `QUESTION:` lines — the question channel is retired. Instead:

- If you can decide, decide, and record it as `- [ASSUMPTION] {decision} — {reason}` in
  the Assumptions section. The approval surface shows Assumptions to the user.
- Reserve Assumptions for calls that are genuinely discretionary. Do not launder obvious
  consequences of the contract as assumptions.
- A guess whose failure is expensive AND which the contract cannot resolve must still be
  made by you, explicitly marked — never silently.
- If the requirement spans multiple independent subsystems with no shared contract, do not
  design a mega-plan: end your output with a line
  `SPLIT_SUGGESTED: {reason + suggested sub-plan split}` instead of a task tail.

## Pre-Delivery Self-Check (self-audit; do not write this to the plan)

1. Every body section maps to a contract entry — no orphans?
2. Zero under-decisions: no line an implementer must guess?
3. Zero over-decisions: no transcription wearing design's clothes?
4. Every task has 1-5 anchors, all with non-empty criteria?
5. Assumptions list matches the discretionary calls you actually made?

## Using the Context Snapshot

Read the snapshot file first; only open raw project files when the snapshot lacks a
specific detail you need. If you read additional files, list them after your completion
signal (see below) so the snapshot can be extended.

## Output Format Requirements

The dispatcher extracts your plan by searching for the literal delimiters
`<<<PLAN_START>>>` and `<<<PLAN_END>>>`. If you deviate, the dispatcher must invoke a
fallback parser, retry, or ask the user — wasting a round. You MUST:

1. Output the delimiters EXACTLY as written: `<<<PLAN_START>>>` on its own line,
   `<<<PLAN_END>>>` on its own line.
2. Put ALL plan content between them. Your content starts at `## Current State` — the
   contract header is NOT yours to output.
3. **Do NOT wrap the delimiters or the content in a code fence.**
4. **Do NOT translate, transliterate, or modify the delimiter strings.**
5. Use the literal ASCII characters `<`, `>`, `_`.

### Correct example

<<<PLAN_START>>>
## Current State
...
## Design
...
## Assumptions
...
## Risks
...
### Task 1: ...
- Files: ...
- Anchors:
  - test_x: ...
<<<PLAN_END>>>
PLAN DESIGN COMPLETE

### Incorrect examples (DO NOT DO THESE)

- Code-fence wrapping, translated punctuation (`《《PLAN_START》》`), missing/extra
  brackets (`<<PLAN_START>>`, `<<<<PLAN_START>>>>`) — all force fallback parsing.

## Completion Signal

- Design complete: `PLAN DESIGN COMPLETE`
- Files read beyond the snapshot: `ADDITIONAL FILES READ: <file1>, <file2>, ...`
- Scope spans independent subsystems: `SPLIT_SUGGESTED: {reason + suggested split}`
````

- [ ] **Step 2: SKILL.md — frontmatter 与 Flow Overview**

Frontmatter description 整行替换为（English, LLM-facing）：

```
description: "Produce an executable technical plan through a contract-driven pipeline: the dispatcher freezes a scope contract with the user, a designer subagent writes the plan body against it, a reviewer enforces contract mapping, and approval materializes tasks into features automatically. Use whenever the user asks to create a technical plan, design a solution, or think through how to implement something before coding."
```

`## Flow Overview` 整块图替换为：

```
User describes requirement
  |
  v
[Phase 0] Init + entry triage ---- self-sufficient -> advise & exit (X)
  |                               ---- light lane  -> L (merge at Phase 6)
  v
[Phase 1] Context snapshot (subagent)
  v
[Phase 2] Contract freeze (dispatcher Write, user confirm)
  v
[Phase 3] Design (Plan subagent; body only)
  v
[Phase 4] Review (4-step protocol; targeted revise/re-review inner loop)
  v
[Phase 5] Approval (user) --reject x3--> suggest contract replay (back to Phase 2)
  v
[Phase 6] Archive + materialize (tasks_to_features.py) -> suggest /ghs:code
```

（注：Phase 0 的分诊三档在 T5 落地；本任务先落图与主线，self-sufficient/light 两行的行为节由 T5 补。）

- [ ] **Step 3: SKILL.md — Core Concepts 更新**

- `### Three Roles` 表加一行：`| **Contract** | Dispatcher authors, user confirms | Scope truth: six-piece contract header frozen at kickoff; body maps to it |`；designer 行责任改 "Design the plan body against the frozen contract (Current State / Design / Assumptions / Risks + task cards)"；reviewer 行责任改 "Enforce contract mapping, decision discipline, anchor completeness"。
- `### File Conventions` 表下加一句（英文）：`The plan file is created by the dispatcher in Phase 2 as the contract header; the designer only ever produces the body, which the dispatcher concatenates after the header — the contract never passes through the designer's hands.`
- `### State Tracking` 的 JSON 块与字段描述整体替换为：

```json
{
  "plan_file": "{date}-{slug}.md",
  "context_file": "{date}-{slug}-context.md",
  "status": "designing | reviewing | revising | pending_approval | approved | aborted",
  "lane": "light | full",
  "retry_counts": {"plan": 0, "review": 0, "context_snapshot": 0},
  "reject_count": 0,
  "final_fix_pending": false,
  "accepted_with_fail": false,
  "keep_raw_on_success": false,
  "created_at": "YYYY-MM-DDTHH:mm:ss",
  "updated_at": "YYYY-MM-DDTHH:mm:ss"
}
```

字段说明（英文，逐条）：六状态枚举（`rejected` 删除）；`lane` 随 Phase 0 分诊写入（T5 前恒 `full`）；`retry_counts` 每类子代理独立计数、持久化、成功解析归零（`MAX_RETRY = 1`）；`reject_count` = Phase 5 审批被拒累计，≥3 → 建议契约重放；`final_fix_pending` = 定向复审留残留时置 true，置位期间仅允许一次定向修订且不再复审，进入 `pending_approval` 或 `aborted` 时清除；`accepted_with_fail` 语义收窄为"复审后仍有残留且用户显式接受"；`keep_raw_on_success` 语义不变。**删除** `round`/`max_rounds`/`max_rounds_breaches` 的全部描述。补一句：`Contract freeze is not a state-machine state — the plan document itself is the truth.`
- 删除 `### Issue Severity Levels` 表上方至 `---` 之间不变；表加一行 Unwarranted（T4 评审协议正式启用，此处先落定义）：`| **Unwarranted** | Plan content that maps to no contract entry | A section with no Goal/Decision/Open-Space/Constraint sponsor |`，PASS 判据行改 `Pass criteria: zero Unwarranted, zero Severe, zero Medium issues.`

- [ ] **Step 4: SKILL.md — Phase 0（初始化，不含分诊）与 Phase 1（快照去 haiku）**

`### Phase 0: Initialization`：保留原步骤 1-4（resolve / requirement 确认 / mkdir / 生成 `{date}-{slug}`）；步骤 5 改为 `Initialize status file: Write the status JSON exactly per the schema in State Tracking, with "status": "designing" and "lane": "full".`（T5 把 lane 写活）。

`### Phase 0.5` 改号为 `### Phase 1: Context Snapshot Extraction`：

- 两处 spawn JSON 块各删除一行 `"model": "haiku",`；正文两处 `spawn general-purpose (model haiku)` / `spawn Explore (model haiku)` 去掉 `(model haiku)`。
- Handling 步骤 4 的 `retry_count` 字样统一为 `retry_counts.context_snapshot`（含 post-mortem raw 命名说明处）；`Proceed to Phase 1` → `Proceed to Phase 2`。
- 其余（模板、解析命令、Format Recovery 引用）逐字保留。

- [ ] **Step 5: SKILL.md — 新增 Phase 2 契约冻结**

在 Phase 1 之后插入完整小节：

````markdown
### Phase 2: Contract Freeze

The dispatcher owns the contract. The designer never sees the requirement conversation —
only the frozen header.

1. **Draft the six-piece contract** from the user's requirement description plus every
   clarification already settled in conversation: intent (why), goals (checkable, one per
   line), non-goals (explicit boundaries), anti-goals ("fails even if it ships" criteria),
   decisions made so far (mark anything not user-ratified with `[DISCRETIONARY]`), open
   space (explicitly left to the implementer), plus the `Global Constraints` section
   (one item per line, exact values verbatim — formats, compatibility promises, naming
   rules, ports; no prose).
2. **Confirm with the user** via AskUserQuestion — ONE question showing the full draft:
   "以上是本次计划的范围契约，有无需要修正的地方？" Options: "确认冻结" / "需要修正"。
   If the user requests corrections, revise in place and re-confirm (still the same
   single question). If Phase 0/1 already included a clarification AskUserQuestion round,
   ride this confirmation on that round's final exchange instead of adding a new one.
3. **Freeze = Write.** Create `{PROJECT_DIR}/.ghs/plans/{plan_file}` with EXACTLY this
   content (template verbatim; headings are fixed English tokens — parsers depend on
   them; body text follows the repo language policy):

```markdown
# {Plan Title}

> SCOPE CONTRACT — frozen at kickoff. 由 dispatcher 维护并经用户确认；
> 正文不得扩大本契约范围，冲突时删正文不删契约。

## Intent
{一段话：为什么做这件事}

## Goals
- {可检验的目标，一条一行}

## Non-Goals
- {明确不做的事，说清边界在哪}

## Anti-Goals
- {"即使做成了也算失败"的失败判据}

## Decisions
- {已定决策一条一行；未经用户拍板、由 designer/dispatcher 裁量的项标 [DISCRETIONARY]}

## Open Space
- {明确留给实现方裁量、plan 不做决定的部分}

## Global Constraints
{一行一条，逐字精确值：格式、兼容性承诺、命名规范、端口等；无散文}
```

4. Update `updated_at` in the status file. Proceed to Phase 3.
````

- [ ] **Step 6: SKILL.md — Phase 1 设计改号 Phase 3，派发模板全面重写**

旧 `### Phase 1: Plan Design (Round N)` 改号 `### Phase 3: Design`；引语改为 `Phase 3 runs on initial design; targeted revision after a FAIL is an inner loop of Phase 4 and re-dispatches this phase with findings.`。spawn 块 description 改 `"Design technical plan body"`。**Designer Instruction Template 整块替换**为：

```
You are a senior technical plan designer. Produce the BODY of a technical plan that continues a frozen contract header.

## Frozen Contract (FROZEN — do not modify, restate, or contradict; never output it)
<dispatcher pastes the full contract header read from <PROJECT_DIR>/.ghs/plans/<plan_file>>

## Project Context
- Project directory: <PROJECT_DIR>
- **Context snapshot**: <PROJECT_DIR>/.ghs/plans/<context_file>
  READ THIS FILE FIRST. It contains a condensed summary of architecture, tech stack,
  directory structure, and relevant code excerpts. Only read raw project files when the
  snapshot lacks a specific detail you need.

## Task Requirements
1. Read the context snapshot to understand the project.
2. Design the plan body: ## Current State / ## Design / ## Assumptions / ## Risks,
   followed by the task tail (### Task {N} cards, sequential from 1).
3. Your output starts at `## Current State` — the contract header is NOT yours to output;
   the dispatcher concatenates it ahead of your body.
4. Read ${CLAUDE_PLUGIN_ROOT}/shared/references/plan-designer.md and follow its decision
   discipline, task-card serialization rules, and discretion culture exactly.
5. If you read files beyond the snapshot, list them after your completion signal.

## Output Format Requirements (CRITICAL)
The dispatcher extracts your plan by searching for the literal delimiters `<<<PLAN_START>>>`
and `<<<PLAN_END>>>. If you deviate, the dispatcher must invoke a fallback parser, retry,
or ask the user — wasting a round. You MUST:
1. Output the delimiters EXACTLY as written: `<<<PLAN_START>>>` on its own line, `<<<PLAN_END>>>` on its own line.
2. Put ALL plan content between them, starting with `## Current State`.
3. **Do NOT wrap the delimiters or the content in a code fence.**
4. **Do NOT translate, transliterate, or modify the delimiter strings.**
5. Use the literal ASCII characters `<`, `>`, `_`.

### Correct example
<<<PLAN_START>>>
## Current State
...
### Task 1: ...
- Files: src/session.ts
- Anchors:
  - test_refresh_rejects_expired: 过期 token 返回 401 且不落库
<<<PLAN_END>>>
PLAN DESIGN COMPLETE

## Completion Signal
When done, output: "PLAN DESIGN COMPLETE"
If you read files beyond the context snapshot, list them as: "ADDITIONAL FILES READ: <file1>, <file2>, ..."
If the requirement spans multiple independent subsystems with no shared contract, output instead: "SPLIT_SUGGESTED: <reason + suggested sub-plan split>"
(Do NOT emit QUESTION lines — that channel is retired. Decide and mark [ASSUMPTION].)
```

**Handling Designer Feedback** 小节改造：

- 步骤 2（designer question pre-check）整段替换为：`**SPLIT_SUGGESTED pre-check**: If the response contains a line matching ^SPLIT_SUGGESTED:\s*(.+)$, use AskUserQuestion to let the user decide: 拆分（当前 plan 置 status: "aborted"，把建议的子 plan 划分告知用户，各自后续走完整流程）/ 合并（附用户理由，重派 designer，回到本 Phase 步骤 1）。`
- 新增拼接落盘规则（替换原 `Write content to the target file` 句）：`ok`/`fallback_used` 时 **dispatcher 以"契约头 + 正文"拼接覆盖写** `{plan_file}`：Read 现有文件得契约头（Phase 2 冻结内容，物理不经 designer），正文取解析 `content`；若正文以 `# {Plan Title}` 或重复契约头开头，剥离至 `## Current State` 起。`fallback_used` 时警告注释 prepend 到正文前、契约头之后。
- `retry_count` 字样 → `retry_counts.plan`；状态迁移句 `Update status to "reviewing"` 保留（分支前 Read status.json 的纪律 T5 统一补）。
- 保留旧 Format Recovery 引用与 `.raw` 落盘规则（`retry_counts` 键名替换随 Step 7 全局替换完成）。

- [ ] **Step 7: SKILL.md — 旧阶段改号携带 + 全局替换**

- 旧 `### Phase 2: Plan Review` → `### Phase 4: Review`；旧 `### Phase 2.5: Context Snapshot Update` → 并入 Phase 4 末尾为无编号小节 `#### Context Snapshot Update`；旧 `### Phase 3: User Approval` → `### Phase 5: Approval`；旧 `### Phase 4: Finalization` → `### Phase 6: Finalization`。这些节内容本任务**不改写**（T3/T4 替换），仅改号与内部互引（如 "Proceed to Phase 3" → "Proceed to Phase 4"、"Phase 2 FAIL" → "Phase 4 FAIL"）。已知的字段悬挂（旧文本仍提 `round`/`max_rounds_breaches`）为分支内中间态，T4 清除。
- 全文 `retry_count` → 对应 `retry_counts.<kind>`（plan/review/context_snapshot 三种），`Phase 0.5` 字样 → `Phase 1`。
- Key Constraints #2（max_rounds 软硬帽）整条删除；#1 "One question at a time" 追加例外句：`Exception: the Phase 4 builder-question round is a single batched AskUserQuestion (see Phase 4).`；#3/#4/#5/#6 保留，#5 的 PASS 判据句同步为 `zero Unwarranted, zero Severe, zero Medium`。

- [ ] **Step 8: 验证**

```bash
grep -c "haiku" plugin/skills/ghs-plan/SKILL.md
grep -c "QUESTION:" plugin/shared/references/plan-designer.md
grep -c "QUESTION" plugin/skills/ghs-plan/SKILL.md
grep -n "max_rounds\|MAX_BREACHES" plugin/skills/ghs-plan/SKILL.md | wc -l
grep -c "SCOPE CONTRACT" plugin/skills/ghs-plan/SKILL.md
grep -c "SPLIT_SUGGESTED" plugin/skills/ghs-plan/SKILL.md
command python3 -m py_compile plugin/shared/scripts/parse_delimited_output.py
command python3 plugin/shared/scripts/test_parse_delimited_output.py 2>&1 | tail -1
```

Expected 依次：`0`（haiku 归零）、`1`（designer 仅剩 "QUESTION is retired" 说明句——裁定：简报 verbatim 文本自身含该字面量，期望值 0 与之矛盾，以 1 为准）、`2`（过渡态：designer retired 行 + 携带 reviewer Handling pre-check 文本；T4 替换携带文本后清至 1）、`>0` 但全部位于 Phase 4/5 携带的旧文本内（T4 清零）、`≥1`、`≥2`、退出码 0、`OK`。

- [ ] **Step 9: Commit**

```bash
git add plugin/skills/ghs-plan/SKILL.md plugin/shared/references/plan-designer.md
git commit -m "feat(plan): P0+P1 契约冻结与 designer 重写（契约头模板、裁量文化、SPLIT_SUGGESTED、去 haiku）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: P2 — tasks_to_features.py + parser Unwarranted + SKILL.md Phase 6（commit ③）

**Files:**
- Create: `plugin/shared/scripts/tasks_to_features.py`
- Test: `plugin/shared/scripts/test_tasks_to_features.py`
- Modify: `plugin/shared/scripts/parse_delimited_output.py`（Unwarranted 计数）、`plugin/shared/scripts/test_parse_delimited_output.py`（追加用例）
- Modify: `plugin/skills/ghs-plan/SKILL.md`（携带版 Phase 6 → 归档+物化）

**Interfaces:**
- Consumes: T1 的 `plans[]` schema 与 `^p\d{1,4}$`/`^p\d{1,4}-feat-\d{3}$`；T2 的任务卡序列化格式与契约头模板。
- Produces: CLI `command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/tasks_to_features.py --project-dir <PROJECT_DIR> --plan-file <PROJECT_DIR>/docs/ghs/plans/{plan_file}`，stdout JSON `{"status": "parsed"|"no_task_zone"|"malformed", "plan_id": "...", "feature_ids": [...]}` 或 `{"status": ..., "reason": "..."}`；parser 新增 `unwarranted` 字段（仅 kind=review，int|null）供 T4 评审环读取。

- [ ] **Step 1: 编写失败测试 `plugin/shared/scripts/test_tasks_to_features.py`**

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
command python3 plugin/shared/scripts/test_tasks_to_features.py 2>&1 | tail -3
```

Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'tasks_to_features'`（或 ImportError）。

- [ ] **Step 3: 实现 `plugin/shared/scripts/tasks_to_features.py`**

```python
#!/usr/bin/env python3
"""Materialize a plan document's task tail into features.json.

Parses the frozen contract header (## Global Constraints) and the task-card
tail (### Task {N} blocks) from an approved plan document, appends a plan
object with deterministically derived features to .ghs/features.json, and
appends a minimal planning entry to .ghs/progress.md.

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
    return [
        re.sub(r"^-\s+", "", l).strip()
        for l in body.splitlines()
        if l.strip()
    ]


def derive_plan_name(plan_text: str) -> str:
    """First sentence of ## Intent, truncated to NAME_MAX_CHARS."""
    body = extract_section(plan_text, "Intent")
    first_line = next((l.strip() for l in body.splitlines() if l.strip()), "")
    sentence = re.split(r"[。？！.!?]", first_line, maxsplit=1)[0].strip()
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

        def field(name, content=body):
            m = re.search(rf"^- {name}:[ \t]*(.*)(?:\n(?:(?!- (?:Files|Interfaces|Points|Anchors):).)*)*", content, re.MULTILINE | re.DOTALL)
            return m

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
            if not criterion or EMPTY_CRITERION_RE.match(criterion):
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


def append_progress_entry(progress_path: Path, plan_id: str, count: int, plan_ref: str):
    marker = "## Feature Planning"
    today = datetime.now().strftime("%Y-%m-%d")
    entry = (
        f"{marker} - {today}\n"
        f"**Agent**: Plan Materializer\n"
        f"**Plan**: {plan_id} (source: {plan_ref})\n"
        f"**Features**: {count} task(s) materialized\n"
    )
    content = progress_path.read_text(encoding="utf-8") if progress_path.exists() else ""
    lines = content.splitlines(keepends=True)
    insert_at = len(lines)
    for i, line in enumerate(lines):
        if line.rstrip("\n").startswith("## Sessions"):
            insert_at = i + 1
            # Skip a trailing comment line right after the heading (template marker).
            if insert_at < len(lines) and lines[insert_at].strip().startswith("<!--"):
                insert_at += 1
            break
    lines.insert(insert_at, "\n" + entry)
    progress_path.write_text("".join(lines), encoding="utf-8")


def emit(payload: dict, exit_code: int) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def main() -> int:
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
    progress_path = project_dir / ".ghs" / "progress.md"

    if not plan_file.exists():
        print(f"tasks_to_features: error: plan file not found: {plan_file}", file=sys.stderr)
        return 2
    if not features_path.exists():
        print(f"tasks_to_features: error: features.json not found at {features_path}", file=sys.stderr)
        return 2

    plan_text = plan_file.read_text(encoding="utf-8")
    constraints = extract_global_constraints(plan_text)
    cards, reason = parse_task_cards(plan_text)
    if cards is None:
        if reason.startswith("no task zone"):
            return emit({"status": "no_task_zone", "reason": reason}, 1)
        return emit({"status": "malformed", "reason": reason}, 1)

    with open(features_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    numbers = [
        int(m.group(1))
        for p in data.get("plans", [])
        for m in [PLAN_NUM_RE.match(str(p.get("id", "")))]
        if m
    ]
    plan_number = (max(numbers) + 1) if numbers else 1
    plan_id = f"p{plan_number}"

    plan_ref = plan_file.relative_to(project_dir).as_posix()
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

    append_progress_entry(progress_path, plan_id, len(cards), plan_ref)

    return emit({
        "status": "parsed",
        "plan_id": plan_id,
        "feature_ids": [feat["id"] for feat in plan_obj["features"]],
    }, 0)


if __name__ == "__main__":
    sys.exit(main())
```

（实现注意：`parse_task_cards` 内未使用的 `field` 闭包不要带入最终代码——上面仅示意字段定位思路，最终实现以各 `re.search` 为准。）

- [ ] **Step 4: 运行测试至通过**

```bash
command python3 plugin/shared/scripts/test_tasks_to_features.py 2>&1 | tail -3
```

Expected: `OK`（10 个用例全过）。若有失败：先修脚本（测试为规格），不得改测试迁就实现。

- [ ] **Step 5: parser 增 Unwarranted 计数（先加测试）**

`plugin/shared/scripts/test_parse_delimited_output.py` 追加三个用例（类内）：

```python
    # ------------------------------------------------------------------
    # Unwarranted count extraction (review kind only)
    # ------------------------------------------------------------------
    def test_unwarranted_count_review(self):
        raw = (f"<<<REVIEW_START>>>\n{LONG_BODY}\n<<<REVIEW_END>>>\n"
               "REVIEW COMPLETE | Verdict: FAIL | Unwarranted: 2 Severe: 0 Medium: 1 Optimization: 0\n")
        result = helper.parse_raw(
            raw, kind="review",
            start_token="<<<REVIEW_START>>>", end_token="<<<REVIEW_END>>>",
            min_length=150, completion_signal="REVIEW COMPLETE",
        )
        self.assertEqual(result["unwarranted"], 2)

    def test_unwarranted_absent_is_none(self):
        raw = f"<<<REVIEW_START>>>\n{LONG_BODY}\n<<<REVIEW_END>>>\nREVIEW COMPLETE | Verdict: PASS | Severe: 0 Medium: 0 Optimization: 0\n"
        result = helper.parse_raw(
            raw, kind="review",
            start_token="<<<REVIEW_START>>>", end_token="<<<REVIEW_END>>>",
            min_length=150, completion_signal="REVIEW COMPLETE",
        )
        self.assertIsNone(result["unwarranted"])

    def test_unwarranted_ignored_for_plan_kind(self):
        raw = f"<<<PLAN_START>>>\nUnwarranted: 9\n{LONG_BODY}\n<<<PLAN_END>>>\n"
        result = helper.parse_raw(
            raw, kind="plan",
            start_token="<<<PLAN_START>>>", end_token="<<<PLAN_END>>>",
            min_length=200, completion_signal=None,
        )
        self.assertIsNone(result["unwarranted"])
```

运行确认新用例失败（`AttributeError`/KeyError — `unwarranted` 键不存在）：

```bash
command python3 plugin/shared/scripts/test_parse_delimited_output.py 2>&1 | tail -3
```

- [ ] **Step 6: 实现 parser 改动**

`parse_delimited_output.py` 三处：

1. `VERDICT_RE` 之后加：

```python
# Regex that pulls the Unwarranted count out of a review signal line:
# `REVIEW COMPLETE | Verdict: FAIL | Unwarranted: 2 Severe: 0 ...`
UNWARRANTED_RE = re.compile(r"Unwarranted:\s*(\d+)")
```

2. `_extract_verdict` 之后加：

```python
def _extract_unwarranted(signal_line: "str | None", raw_text: str) -> "int | None":
    """Extract the Unwarranted count from the completion-signal line, then the raw tail."""
    source = signal_line or (raw_text[-600:] if len(raw_text) > 600 else raw_text)
    m = UNWARRANTED_RE.search(source)
    return int(m.group(1)) if m else None
```

3. 两处构造返回 dict 的地方（成功路径与失败路径，即 `verdict` 赋值处旁边）各加一行，与其同款三元形式：

```python
            unwarranted_value = (
                _extract_unwarranted(captured_signal_line, raw_text)
                if kind == "review"
                else None
            )
```

并在 dict 字面量 `"verdict": verdict,` 后加 `"unwarranted": unwarranted_value,`（成功、失败两处都要；失败路径同样计算——signal 行在 malformed 时也可能已捕获）。docstring 的输出 shape 注释在 `"verdict"` 行后补一行：`"unwarranted": <int | null>,          # only for --kind review`。

- [ ] **Step 7: 测试回归**

```bash
command python3 plugin/shared/scripts/test_parse_delimited_output.py 2>&1 | tail -3
command python3 plugin/shared/scripts/test_tasks_to_features.py 2>&1 | tail -3
command python3 plugin/shared/scripts/test_parse_completion_signal.py 2>&1 | tail -3
```

Expected: 三个 `OK`。

- [ ] **Step 8: SKILL.md — Phase 6 替换为归档+物化**

将携带版 `### Phase 6: Finalization` 整节替换为：

````markdown
### Phase 6: Archive + Materialize

1. Copy the approved plan to the permanent archive:
   ```bash
   mkdir -p ${PROJECT_DIR}/docs/ghs/plans
   cp ${PROJECT_DIR}/.ghs/plans/${plan_file} ${PROJECT_DIR}/docs/ghs/plans/${plan_file}
   ```

2. **Check for accepted-with-fail marker**: Read the top of the plan file. If it contains a line matching `<!-- WARNING: accepted with unfixed issues`, set `ACCEPTED_WITH_FAIL = true` and extract the `<X>`/`<Y>` values; otherwise `false`.

3. Commit the archived plan. With the `accepted-with-fail` suffix when applicable:
   ```bash
   cd ${PROJECT_DIR} && git add docs/ghs/plans/${plan_file} && git commit -m "docs(plan): add technical plan - ${plan_file}"
   ```
   (`ACCEPTED_WITH_FAIL == true` 时消息追加后缀 `[accepted-with-fail; S=<X> M=<Y>]`。)

4. **Materialize the task tail** (plan 闭环 — 主链就此收敛为 plan → code):
   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/tasks_to_features.py \
     --project-dir <PROJECT_DIR> \
     --plan-file <PROJECT_DIR>/docs/ghs/plans/<plan_file>
   ```
   Read the JSON from stdout and branch on `status`:

   - **`parsed`**: features written. Report plan id and feature ids to the user.
   - **`no_task_zone`**: the plan has no task tail. Tell the user materialization was skipped and suggest `/ghs:to-features` to break the plan down by LLM instead.
   - **`malformed`**: **定点重写任务节** — 物化失败发生在审批归档之后，禁止全量重新生成（会静默作废已通过的评审）。Re-dispatch the designer (same Phase 3 dispatch, subagent_type Plan) with the FULL current plan file inlined as FROZEN plus this appendix appended:

     ```
     ## IMPORTANT: Targeted Task-Tail Rewrite
     Your previous task tail could not be parsed by the materializer:
     <reason from the parser JSON>
     Rewrite ONLY the task tail (the `### Task` cards) so it conforms to the
     serialization rules in plan-designer.md. Everything before the first
     `### Task` heading (design body) is FROZEN — reproduce it verbatim,
     unchanged. Output the FULL body again between the delimiters, starting at
     `## Current State`.
     ```

     On success, concatenate 契约头 + 新正文 and overwrite `${PROJECT_DIR}/.ghs/plans/${plan_file}` AND `docs/ghs/plans/${plan_file}` (both copies), then re-run the materializer command above. Still `malformed` after one targeted rewrite → AskUserQuestion with two options: 跳过物化（用户稍后走 `/ghs:to-features`）/ 再修一次任务节（重复本分支，仅限一次）。

5. Update status to `approved` (and write `"accepted_with_fail": true` if applicable). Report the archived plan path, feature count, and close with: suggest `/ghs:code` to start implementing the first feature.
````

- [ ] **Step 9: 验证**

```bash
grep -c "tasks_to_features" plugin/skills/ghs-plan/SKILL.md
grep -c "定点重写" plugin/skills/ghs-plan/SKILL.md
command python3 -m py_compile plugin/shared/scripts/tasks_to_features.py plugin/shared/scripts/parse_delimited_output.py
command python3 plugin/shared/scripts/test_tasks_to_features.py 2>&1 | tail -1
command python3 plugin/shared/scripts/test_parse_delimited_output.py 2>&1 | tail -1
```

Expected 依次：`≥2`（裁定：Phase 6 替换文本含 1 处 + 正文既有 1 处；第 3 处随 T5 轻档支路落地自然达到）、`≥1`、退出码 0、`OK`、`OK`。

- [ ] **Step 10: Commit**

```bash
git add plugin/shared/scripts/tasks_to_features.py plugin/shared/scripts/test_tasks_to_features.py plugin/shared/scripts/parse_delimited_output.py plugin/shared/scripts/test_parse_delimited_output.py plugin/skills/ghs-plan/SKILL.md
git commit -m "feat(plan): P2 任务尾机械物化（tasks_to_features.py 三态路由、per-feature 约束传播、parser Unwarranted 计数、Phase 6 归档+物化）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: P3+P4 — reviewer 重写 + 评审环硬封顶 + 审批/契约重放（commit ④）

**Files:**
- Rewrite: `plugin/shared/references/plan-reviewer.md`（全量替换）
- Modify: `plugin/skills/ghs-plan/SKILL.md`（Phase 4 携带文本 → 四步协议 + 内部修订/复审循环；Phase 5 → 新审批面 + reject/契约重放；Format Recovery 收窄；Key Constraints 清理）

**Interfaces:**
- Consumes: T2 的契约头模板与 status.json schema（`reject_count`/`final_fix_pending`/`retry_counts`）；T3 的 parser `unwarranted` 字段。
- Produces: signal 行格式 `REVIEW COMPLETE | Verdict: PASS|FAIL | Unwarranted: X Severe: Y Medium: Z Optimization: W`；`-review.md` 报告骨架六节；builder questions 三堆协议；T5 的 Phase 0 分诊引用评审①步契约映射作为兜底。

**对应删减（随本任务生效）**：多轮 revise 循环、breach/MAX_BREACHES、`rejected` 死枚举、max_rounds 协商、修订日志、12 项 checklist、Plan Summary 节、现行评审/审批分支树 ~70%、reviewer `QUESTION` 信号与 "one question at a time" 全局约束（改"单轮封顶、批式提问"）。

- [ ] **Step 1: 重写 `plugin/shared/references/plan-reviewer.md`**

用以下全文替换（LLM-facing，英文）：

````markdown
# Plan Reviewer Instruction Reference

## Role

You review a technical plan against its frozen scope contract. You are a gate, not a
coach: your job is to stop (a) scope the contract never authorized, (b) decisions an
implementer cannot execute, (c) tasks without verifiable anchors. You are also the
builder's advocate on one pass: you cold-read for the places where an implementer would
have to guess, and guessing wrong would be expensive.

## Reading Order

Read the plan file header-first: the contract header is the top of the document and is
the sole scope authority. Then the context snapshot. Only open raw project files to
verify a specific claim. Everything in the body must map to a contract entry — that
mapping is your first protocol step.

## Review Protocol (four steps, one pass)

### Step 4 — Builder questions (cold read, do this FIRST)

Read the plan cold, as the implementer would, hunting exactly one smell:
**the implementer would have to guess, and guessing wrong is expensive.** Sort every hit
into three piles:

1. **Contract already answers it** — cite the contract line verbatim and note where the
   body failed to absorb it (this is also a finding: see Step 1).
2. **The model can decide** — do not ask; note it as a candidate the designer should
   mark `[ASSUMPTION]` (or mark it yourself if it is obviously fine).
3. **Only the user can answer** — importance-ranked; these go in the report's
   Builder Questions section for the dispatcher to batch (max 5; each question ships
   with 2-4 mutually exclusive options and a recommended default).

Ability to derive the answer from the contract disqualifies pile 3. A guess whose
failure is cheap disqualifies it too.

### Step 1 — Contract mapping

For every major body section and every task card, name the contract entry it serves.
A section that maps to nothing is **Unwarranted** — a blocking finding whose fix is
always *delete the section*. The Current State section maps to Intent (understanding
what exists is in scope); do not flag it Unwarranted for that alone. If the body
genuinely needs something the contract never authorized but should have, that is NOT
Unwarranted — report it under Contract Deficiency for the user to decide; never expand
scope yourself.

### Step 2 — Bidirectional failure scan (same ruler as the designer)

- **Under-decision** (Severe): lines an implementer cannot act on — `TBD`, "handle edge
  cases appropriately", unspecified fallbacks. Fix direction: supply the decision.
- **Over-decision** (Medium): transcription — full function bodies where signature +
  location + anchors already determine everything. Fix direction: cut to decision level.
- **Detail-default presumption**: invented schemas / validation / fallbacks / abstraction
  layers must trace to a contract entry or prevent one nameable implementation error.
  Neither → Unwarranted.
- Quality issues surfaced along the way (races, security, wrong assumptions) are graded
  Severe/Medium/Optimization as usual.

### Step 3 — Anchor completeness

Every task card needs 1-5 anchors, each with a non-empty criterion. Test anchors name a
test; command anchors are runnable. Risky unspecified inputs must carry
`[UNDEFINED-INPUT]`. Missing anchors or empty criteria = Medium. Spot-check one anchor
per task against the codebase for reachability (does that test/command exist or is it
created by the task itself?).

## Severity Labels

| Level | Definition | Fix direction |
|---|---|---|
| Unwarranted | Maps to no contract entry | Delete the section (always) |
| Severe | Would cause bugs, or plan cannot achieve its stated goals | Supply the missing decision |
| Medium | Implementable but wrong path / transcription / missing anchors | Cut to decision level; add anchors |
| Optimization | Nice-to-have | Adopt or ignore |

**PASS = zero Unwarranted + zero Severe + zero Medium.** Optimization items do not
block. Every finding carries: location (section/task), one-line issue, fix direction.

## Report Format (fixed skeleton; headings are literals)

```markdown
# Plan Review Report

## Restatement
{Three sentences: what you understand the requirement to be. The approval surface shows
 this to the user to compare "what the reviewer understood" vs "what I asked for".}

## Contract Mapping
| Body section / task | Contract entry | Verdict |
|---|---|---|
{one row per major section and per task; unmapped rows are Unwarranted findings}

## Findings
### Unwarranted
{each: location — issue — fix (delete). "None" if empty.}
### Severe
{...}
### Medium
{...}
### Optimization
{...}

## Anchor Check
{missing / empty-criteria list per task. "All tasks have 1-5 non-empty anchors." }

## Builder Questions (pile 3 only)
{numbered ≤5; each: question + 2-4 mutually exclusive options + recommended default.
 "None" if empty.}

## Contract Deficiency (optional)
{things the body needs but the contract never authorized — for the user to rule on.
 Omit the section if empty.}
```

## Targeted Re-Review Mode

When the dispatcher marks the review as TARGETED, you are NOT re-running the full
protocol. You verify ONLY:

1. Each finding from the previous round (appended to your prompt): verdict it
   `ADDRESSED` or `NOT ADDRESSED`. "Attempted" is not "addressed" — the fix must
   actually resolve the issue as stated.
2. The sections the revision touched: check the fix did not introduce fresh damage
   (new under-decisions, new scope, broken anchors).

Same report skeleton and same signal line; the Findings section contains only the
verdicts plus any new findings from the touched sections.

## Output Format Requirements

The dispatcher extracts your review by searching for the literal delimiters
`<<<REVIEW_START>>>` and `<<<REVIEW_END>>>`, and reads the verdict and severity counts
from the line beginning `REVIEW COMPLETE`. You MUST:

1. Output the delimiters EXACTLY as written, each on its own line, content between them.
2. **Do NOT wrap the delimiters or the content in a code fence.**
3. **Do NOT translate, transliterate, or modify the delimiter strings.**
4. End with the literal completion signal on its own line:

`REVIEW COMPLETE | Verdict: PASS|FAIL | Unwarranted: X Severe: Y Medium: Z Optimization: W`

### Correct example

<<<REVIEW_START>>>
# Plan Review Report
...
<<<REVIEW_END>>>
REVIEW COMPLETE | Verdict: PASS | Unwarranted: 0 Severe: 0 Medium: 0 Optimization: 1

### Incorrect examples (DO NOT DO THESE)

- Code-fence wrapping; translated punctuation; missing/extra brackets; a signal line
  without `Verdict: PASS|FAIL` or without the `Unwarranted:` count — all force retry.

## Completion Signal

- Review complete: `REVIEW COMPLETE | Verdict: PASS|FAIL | Unwarranted: X Severe: Y Medium: Z Optimization: W`
- The `QUESTION:` channel is retired. Pile-3 items go in Builder Questions; everything
  else is your call, graded and reported.
````

- [ ] **Step 2: SKILL.md — Phase 4 携带文本整体替换（评审协议 + 内部循环）**

将 T2 携带的 `### Phase 4: Review`（含旧 reviewer 模板、旧 Handling、末尾 Context Snapshot Update 小节）整节替换为：

````markdown
### Phase 4: Review (full) + Targeted Revise/Re-Review Inner Loop

Hard cap on model calls in this phase: full review 1 + targeted revision 1 + targeted
re-review 1 + final revision 1 = 4. The happy path (first review PASSes) uses 1.

Read status.json BEFORE branching; branch only on the values just read.

**Full review dispatch** (status `designing` → set `reviewing` first):

```json
{
  "subagent_type": "general-purpose",
  "description": "Review technical plan (full)",
  "prompt": "<reviewer instructions>"
}
```

**Reviewer Instruction Template (FULL mode)**:

```
You are a senior architect reviewing a technical plan against its frozen scope contract.

## Review Target
- Plan file (contract header + body — read the contract header FIRST): <PROJECT_DIR>/.ghs/plans/<plan_file>
- Context snapshot: <PROJECT_DIR>/.ghs/plans/<context_file>
- Project directory: <PROJECT_DIR>
- Mode: FULL REVIEW

## Task
Run the four-step review protocol in the order defined in
${CLAUDE_PLUGIN_ROOT}/shared/references/plan-reviewer.md:
Step 4 builder questions (cold read) -> Step 1 contract mapping -> Step 2 bidirectional
failure scan -> Step 3 anchor completeness. Follow its severity definitions (Unwarranted /
Severe / Medium / Optimization), its report skeleton, and its verdict rule
(PASS = zero Unwarranted + zero Severe + zero Medium).

## Output Format Requirements (CRITICAL)
Output the FULL report between the literal delimiters <<<REVIEW_START>>> and
<<<REVIEW_END>>> (each on its own line, no code fences, ASCII only), then end with the
signal line on its own line:
REVIEW COMPLETE | Verdict: PASS|FAIL | Unwarranted: X Severe: Y Medium: Z Optimization: W

## Context Reset
- Disregard any context from previous conversations; read files fresh; isolated task.

## Completion Signal
When done, output the signal line above. The QUESTION channel is retired — pile-3 items
go in the report's Builder Questions section.
```

**Handling**:

1. Write the response verbatim to `<PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.review.raw`, parse with:

   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
     --kind review \
     --input-file <PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.review.raw \
     --completion-signal "REVIEW COMPLETE" \
     --min-length 150
   ```

2. Delete the temp file, then branch on the JSON (`retry_counts.review` for format retries, per Format Recovery; post-mortem raw rules unchanged):

   - **`ok`/`fallback_used`, verdict PASS or FAIL**: write `content` to `<review_file>` (prepend the fallback warning comment if `fallback_used`), overwrite. If `keep_raw_on_success: true`, also write the raw.
   - **`empty`/`malformed`/`verdict == null`**: per Format Recovery (retry once with the appendix; then User Decision Handling).

3. **Builder Questions (pile 3)**: read the report's Builder Questions section. If it is not "None", ask the user ONCE via AskUserQuestion — single batched question round, max 5 questions, each with the reviewer's 2-4 mutually exclusive options and recommended default. Questions beyond the cap (or unanswered) fall to Assumptions — do NOT follow up with more rounds. Record the user's answers.

4. **Branch on verdict** (read status.json first):

   - **PASS** (`reviewing`): if Builder Questions had answers → ONE touch-up dispatch to the designer (Phase 3 template + appendix: "Apply these user answers: <answers>. Change nothing else; output the FULL body.") → concatenate 契约头 + 正文, overwrite plan file. **No re-review after a touch-up.** If no answers → proceed directly. Set `pending_approval`, go to Phase 5.
   - **FAIL** (`reviewing` → set `revising`): ONE targeted revision dispatch — Phase 3 template + appendix:

     ```
     ## Targeted Revision
     Address the review findings ONLY, one by one:
     - Unwarranted -> delete the section/content.
     - Under-decision (Severe) -> supply the decision.
     - Over-decision (Medium) -> cut to decision level.
     - Anchor gaps (Medium) -> add compliant anchors.
     Apply the user's Builder-Question answers: <answers, if any>.
     Expanding beyond the findings is forbidden. Output the FULL body.
     ```

     Concatenate 契约头 + 正文, overwrite plan file, set `reviewing`, then ONE targeted re-review dispatch (same template, `Mode: TARGETED RE-REVIEW`, prompt appended with the previous findings list verbatim and the instruction: "verify each finding ADDRESSED/NOT ADDRESSED + check touched sections for fresh damage; do not re-run the full protocol"). Write the new report over `<review_file>`.
     - Re-review clean (`Unwarranted: 0 Severe: 0 Medium: 0`, and all prior findings ADDRESSED) → `pending_approval`, Phase 5.
     - Residue remains → set `final_fix_pending: true`, ONE final revision dispatch (same targeted appendix with only the surviving findings; **no re-review**), overwrite plan file, then `pending_approval`, Phase 5.

5. **`final_fix_pending` discipline**: while `true`, only one targeted revision is allowed and no further review runs. Clear the flag when entering `pending_approval` or `aborted`. This flag is the on-disk form of the 4-call hard cap — it survives restarts.

6. **Context Snapshot Update** (carried): if the designer/reviewer reported `ADDITIONAL FILES READ`, append a `## Supplementary Context` section to `<context_file>` so later dispatches see the expanded context.

**Contract replay** (explicit back-edge Phase 5 → Phase 2; see Phase 5): same `{plan_file}` — the dispatcher drafts and the user confirms a NEW contract header, the old body is deleted wholesale (it mapped the old contract), `<review_file>` will be overwritten by the next full review, status → `designing`, `reject_count` and `retry_counts` reset to zero, then a brand-new Phase 3.
````

- [ ] **Step 3: SKILL.md — Phase 5 审批替换**

将携带版 `### Phase 5: Approval`（含 Approval Summary Assembly 及其分支树）整节替换为：

````markdown
### Phase 5: Approval

The approval surface is assembled at ~zero cost because the dispatcher authored the
contract. Assemble (≤ ~40 lines total) and ask via AskUserQuestion:

| Block | Source |
|---|---|
| 契约头 | Read `<plan_file>` top — paste Intent / Goals / Non-Goals / Anti-Goals verbatim (Decisions/Open Space/Global Constraints 可折叠为一行计数) |
| 任务清单 | Grep `^### Task ` lines from `<plan_file>` (title line only) |
| 评审残留 | Latest `<review_file>`: signal counts + surviving finding titles (one line each; "无" if PASS with none) |
| Assumptions | `<plan_file>` 的 Assumptions 节逐条（"None" 则省略该块） |
| 文件 | Plan / Review 两个路径 |

Question: "是否批准该计划？" Options: `批准（归档并物化）` / `拒绝（说明修改方向）` / `中止`。

- **approve** → Phase 6。
- **reject**：Read status.json first。`reject_count += 1` 并写盘：
  - `reject_count < 3`：按用户反馈做一次定向修订（Phase 3 模板 + feedback appendix，无模型评审），拼接覆盖写盘，回本 Phase 重新组装审批面。
  - `reject_count >= 3`：**建议契约重放**（软建议，非硬闸）：AskUserQuestion — 契约重放 / 再修订一次 / 中止。用户亦可任意时刻主动发起重放。
- **契约重放**（回边 Phase 5 → Phase 2）：同一 `{plan_file}` 原地覆盖 — dispatcher 重新走 Phase 2（起草新契约头 + 用户确认 + Write 覆盖），旧正文整体作废删除（它映射的是旧契约），status → `designing`，`reject_count` 与 `retry_counts` 归零，随后全新 Phase 3。`<review_file>` 无需删除 — 下一次全量评审会覆盖写。
- **中止** → status `aborted`，停止。
````

- [ ] **Step 4: SKILL.md — 状态机与 Format Recovery 收窄**

- Format Recovery 节：删除 `MAX_BREACHES = 2` 常量条目及其全部正文引用；Constants 保留 `MAX_RETRY = 1` 并补一句 `Each counter persists in status.json retry_counts and resets to 0 on a successful parse.`；Raw file naming 段删除提及 max-rounds/breach 的句子。**Review retry appendix**（For Plan Reviewer retries）更新第 5 点信号行示例为 `REVIEW COMPLETE | Verdict: PASS|FAIL | Unwarranted: X Severe: Y Medium: Z Optimization: W`。
- Key Constraints：#2 已在 T2 删除 — 本步确认全文 `max_rounds` / `max_rounds_breaches` / `MAX_BREACHES` / `"rejected"` / `Round {N}` 字样归零（State Tracking 的 schema 已是新六态）。旧 `rejected` 枚举如在残留文本出现，删除。
- State Tracking 小节补一段（英文）：`Two cap counters live on disk: reject_count (Phase 5 rejections, >=3 triggers the contract-replay suggestion) and final_fix_pending (true while one final no-review revision is allowed). The dispatcher reads them before every branch — files are the single source of dispatcher state.`

- [ ] **Step 5: 验证**

```bash
grep -c "MAX_BREACHES\|max_rounds_breaches\|max_rounds" plugin/skills/ghs-plan/SKILL.md
grep -c '"rejected"' plugin/skills/ghs-plan/SKILL.md
grep -n "Key Constraints #2" plugin/skills/ghs-plan/SKILL.md | wc -l
grep -c "QUESTION" plugin/skills/ghs-plan/SKILL.md
grep -c "QUESTION:" plugin/skills/ghs-plan/SKILL.md
grep -c "Unwarranted" plugin/shared/references/plan-reviewer.md
grep -c "Builder Questions" plugin/skills/ghs-plan/SKILL.md
grep -c "final_fix_pending" plugin/skills/ghs-plan/SKILL.md
grep -c "契约重放" plugin/skills/ghs-plan/SKILL.md
grep -n "QUESTION" plugin/shared/references/plan-reviewer.md | wc -l
command python3 plugin/shared/scripts/test_parse_delimited_output.py 2>&1 | tail -1
```

Expected 依次：`0`、`0`、`0`（携带文本中对已删 Key Constraints #2 的悬挂引用随 T4 替换清零）、`2`（裁定：designer 与 reviewer 两模板各一条无冒号 retired 说明行——原期望"清至 1"漏计 reviewer 模板自身的 retired 行）、`0`（带冒号的 `QUESTION:` 信号字面量归零）、`≥6`、`≥2`、`≥2`、`≥2`、`1`（仅 "retired" 说明行）、`OK`。

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/ghs-plan/SKILL.md plugin/shared/references/plan-reviewer.md
git commit -m "feat(plan): P3+P4 评审环硬封顶（四步协议、Unwarranted、定向修订/复审、新审批面、契约重放、状态机 7→6）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: P5+P6 — 入口分诊 + 状态纪律收尾（commit ⑤）

**Files:**
- Modify: `plugin/skills/ghs-plan/SKILL.md`（Phase 0 加分诊三档 + 轻档支路 L + 自足出口 X；Phase 2 补规模边界切片语；Key Constraints #4 扩展）

**Interfaces:**
- Consumes: T2 的 Phase 2/6（轻档复用其 Write 与物化）、T4 的评审①契约映射（兜底说明）。
- Produces: `lane` 字段取值行为（`light`/`full`，Phase 0 写定）；轻档单轮合并审批交互。

**对应删减（随本任务生效）**：现状 Phase 0 对所有需求一律全流程的隐性成本（轻档不再付快照+设计+评审三轮）；"one question at a time" 对轻档合并轮的例外已由 T2 预埋。

- [ ] **Step 1: Phase 0 插入分诊小节**

在 `### Phase 0: Initialization` 的步骤 2（requirement 确认）之后、mkdir 之前插入：

````markdown
3. **Entry triage** — classify the requirement into one lane (heuristics, not hard
   thresholds), write `lane` into the status file, and route:

   | Lane | Signals | Route | Interaction |
   |---|---|---|---|
   | Self-sufficient | Names exact files and the exact change; no design space | Advise doing it directly and exit (plain text — no AskUserQuestion) | One sentence |
   | Light | Single subsystem; ≤ ~3 files; no new interface/schema; no architectural decision; short description | Light lane L below — skip Phase 1/3/4 entirely (zero subagents); dispatcher may read a few files directly to pin exact paths | 1 round |
   | Full | Everything else | Continue to Phase 1 | In-flow |

   **Downgrade-tell, upgrade-default**: moving DOWN to light/self-sufficient must be
   stated to the user (they can upgrade at any time); moving UP to full never asks —
   zero forced interaction rounds.
````

后续 mkdir/生成标识/初始化 status 的步骤编号顺延；初始化 status 步骤改为 `Write the status JSON per the schema, "status": "designing", "lane": "<light | full>"（自足出口不写文件，直接退出）.`

- [ ] **Step 2: 轻档支路 L（Phase 0 末尾追加小节）**

````markdown
### Light Lane L (zero subagents, merges at Phase 6)

1. **Dispatcher drafts the contract header** (Phase 2 template, six pieces + Global
   Constraints) and **ONE task card** (Phase 3 task-card serialization format) directly —
   reading a handful of project files to pin exact paths is allowed.
2. **Write** `{plan_file}` = 契约头 + 任务卡. Set `pending_approval`.
3. **Single merged round**: ONE AskUserQuestion showing 契约头 + 任务卡 —
   "确认物化 / 调整后物化 / 升完整档"：
   - 确认物化 → Phase 6（共用 `tasks_to_features.py`）。
   - 调整后物化 → dispatcher 原地修改后再问一次（仅一次），然后 Phase 6。
   - 升完整档 → `lane: "full"`，回 Phase 1（已写的 `{plan_file}` 作为契约头起点保留）。
4. Reviewers do not run on this lane; the merged round IS the gate. Full-lane runs keep
   review Step 1 contract mapping as the backstop for anything mis-triaged as light.
````

- [ ] **Step 3: Phase 2 补规模边界语**

在 Phase 2 起草步骤末尾追加一句（英文）：`For oversized same-domain needs, slice milestones via the contract's Non-Goals across multiple plan runs (each run gets its own frozen contract); for needs spanning independent subsystems the Phase 3 SPLIT_SUGGESTED gate applies. Safe zone: a single plan stays under ~800 lines.`

- [ ] **Step 4: P6 状态纪律（Key Constraints #4 扩展 + State Tracking 补 ~5 行）**

- Key Constraints #4 末尾追加（英文）：`Files are the single source of the dispatcher's own state: at every branch point, Read status.json first and branch only on the values just read; write a status change in the same turn as the file write it describes (write-through). No deriving dispatcher state from conversation memory.`
- State Tracking 小节末尾追加 5 行以内的纪律段（不立名目，英文）：

```
State discipline: (1) write-through — status and files change in the same turn;
(2) read-before-branch at the remaining branch points (Phase 4 verdict branch, Phase 5
reject branch, Phase 6 materialize-failure branch); (3) cap counters live on disk
(reject_count / final_fix_pending / retry_counts) and are never recomputed from memory;
(4) the plan document itself is the contract-freeze truth — no state-machine entry for it.
```

- [ ] **Step 5: 验证**

```bash
grep -c "Self-sufficient\|Light Lane L\|upgrade-default\|write-through" plugin/skills/ghs-plan/SKILL.md
grep -c "~800 lines" plugin/skills/ghs-plan/SKILL.md
grep -c '"lane"' plugin/skills/ghs-plan/SKILL.md
grep -ci "tdd\|red-green\|红绿" plugin/skills/ghs-plan/SKILL.md plugin/shared/references/plan-designer.md plugin/shared/references/plan-reviewer.md
```

Expected 依次：`≥4`、`1`、`≥2`、`0`（反目标：计划文档无 TDD 剧本）。

- [ ] **Step 6: Commit**

```bash
git add plugin/skills/ghs-plan/SKILL.md
git commit -m "feat(plan): P5+P6 入口分诊三档与轻档支路、状态纪律写穿与分支前读盘收尾

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: 终验（无 commit，除非修出缺陷）

**Files:** 无新增；只验证与修补。

**Interfaces:** Consumes T1-T5 全部产物。Produces: 终验结论（验收报告写进会话回复，不落盘新文档）。

- [ ] **Step 1: 全量静态闸门**

```bash
grep -ri sprint plugin/ README.md README-zh.md | grep -v "^plugin/shared/scripts/validate_structure.py" | wc -l
grep -c "sprint" plugin/shared/scripts/validate_structure.py
grep -ri sprint .claude-plugin/marketplace.json | wc -l
grep -c "haiku" plugin/skills/ghs-plan/SKILL.md
grep -rn "max_rounds\|MAX_BREACHES\|max_rounds_breaches" plugin/ | wc -l
grep -c "SCOPE CONTRACT" plugin/skills/ghs-plan/SKILL.md
command python3 -m py_compile plugin/shared/scripts/*.py
```

Expected 依次：`0`、`2`（登记例外：validate_structure.py 旧格式检测块字面量，见 Task 1 Step 3 裁定）、`0`（marketplace.json 已在 T1 修复轮收尾）、`0`、`0`、`≥1`、全部编译通过。任何非零/失败 → 定点修复后重跑本步。

- [ ] **Step 2: 全量测试回归**

```bash
command python3 plugin/shared/scripts/test_tasks_to_features.py 2>&1 | tail -1
command python3 plugin/shared/scripts/test_parse_delimited_output.py 2>&1 | tail -1
command python3 plugin/shared/scripts/test_parse_completion_signal.py 2>&1 | tail -1
```

Expected: 三个 `OK`。

- [ ] **Step 3: 跨文件一致性抽查**

```bash
grep -n "## Feature Planning" plugin/shared/assets/progress.md plugin/skills/ghs-to-features/SKILL.md plugin/shared/scripts/tasks_to_features.py
grep -n "plans\[\]" plugin/skills/ghs-to-features/SKILL.md plugin/shared/references/features-agent.md
grep -n "plan_ref" plugin/skills/ghs-code/SKILL.md plugin/shared/scripts/tasks_to_features.py
grep -n "REVIEW COMPLETE | Verdict: PASS|FAIL | Unwarranted" plugin/skills/ghs-plan/SKILL.md plugin/shared/references/plan-reviewer.md
```

Expected: 四处 grep 各自非空且措辞一致（progress 标题三处同串；`plans[]` 两处；`plan_ref` 读写两端在；signal 行两处同格式）。`plan_ref` 在 ghs-code 的读取协议（P7 非目标）应与重构前语义一致 — `git diff main...HEAD -- plugin/skills/ghs-code/SKILL.md` 仅含术语置换，逐段确认。

- [ ] **Step 4: 反目标清单核对（逐条人检，不落盘）**

1. 重构后流程步数/产物数 ≤ 现状（SKILL.md 行数 `wc -l` 对照重构前 790；控制文件清单无新增种类）；
2. plan-designer.md / plan-reviewer.md / SKILL.md 无 TDD 步骤剧本、无测试组织指令（Step 1 已 grep，人工再扫一遍任务卡锚点节措辞）；
3. 无新增多轮循环/协商/破例机制（重放是显式单回边；修订/复审是 Phase 4 内部循环且封顶 4 次）;
4. 无新增座位或子代理（builder check 已并入评审席第④步）。

- [ ] **Step 5: 完结报告**

向用户报告：五个 commit 的哈希与主题、三项测试结果、四道闸门的实测计数、反目标核对结论、以及遗留（P7 预案未实施属预期）。

---

