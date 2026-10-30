# 设计 spec：计划状态闭环 + 两项实测 bug 修复

- **日期**：2026-10-24
- **来源**：session `d4771384`（dogfood 修复批 p2）复盘结论，经版本复核（0.5.1 缓存 vs 分支工作树）确认全部为分支现行问题
- **状态**：已经用户逐节评审定稿

## 背景与问题

dogfood 轮实证：`ghs-code --parallel` 完成 6/6 特性后，features.json 中计划状态仍为 `in_progress`，`/ghs:archive` 以「无 completed 计划」拒绝工作，编排者被迫即兴手写临时脚本翻转状态后才完成归档。根因是**计划级状态转移无归属**：

| 环节 | 现状 | 证据 |
|---|---|---|
| 计划状态写入 | 全插件只有 `ghs-to-features/SKILL.md:95` 在创建时写 `in_progress`，无人负责翻转 `completed` | grep 两版 `ghs-code/SKILL.md` 中计划级状态条款零命中 |
| `ghs-code` | 只更新特性级状态，收尾无计划完成检测 | `ghs-code/SKILL.md` Step 5、并行模式收尾（约 227 行） |
| `ghs-archive` | 只认 `completed`，缺失时让用户手改 features.json（死胡同） | `ghs-archive/SKILL.md:57-59` |
| 脚本层 | `update_plan_status.py` 只管 `.ghs/plans/*-status.json`；无任何脚本可写 features.json 状态 | 脚本清单核对 |

同轮实测的另两个 bug 并入本批：`parallel_utils.py` 多计划并存时静默取 `plans[0]` 选错计划；`archive_plans.py` 不消毒计划名中的非法字符导致 Windows `NotADirectoryError`（`archive_plans.py:56/60`）。

## 目标

1. 计划状态 `in_progress → completed` 获得明确归属：`ghs-code` 收尾主动检测并（经用户确认）翻转，`ghs-archive` 兜底补翻。
2. features.json 的状态变更全部脚本化，消灭 `.claude-tmp/mark_completed.py`、`complete_p2.py` 类即兴脚本及其引发的多行 `python -c` 崩溃。
3. 消灭「多计划静默选错」与「归档目录名非法字符崩溃」两个实测 bug。

## 非目标（出范围）

- `plugin.json` 版本 bump 与 dogfood 重装纪律（P1，下一批）
- `plan_ref` 缺失 WARN 的行为定义（P2）
- 缺陷线索入账 features.json 的机制（P1，下一批）
- `ghs-status` 收尾指引在「can_complete 但未翻转」时的提示优化——`ghs-archive` 兜底生效后该路径可自愈，影响可忽略（用户已裁量不改）
- references 用词漂移（N7）中与状态更新无关的部分

## 第 1 节 · 新脚本 `plugin/shared/scripts/update_features.py`

features.json 状态变更的唯一脚本入口，读改写、非重建（未知字段完整保留）。

### CLI 契约

```
# 写：特性状态（跨 plans[].features[] 按 id 定位）
--set-feature <feature_id> --status pending|in_progress|completed|blocked [--blocked-reason "..."]
  - status 为 blocked 时必须提供 --blocked-reason，否则 exit 2
  - feature_id 在多个计划下重复出现 → exit 2（歧义拒绝），文件不动
  - feature_id 不存在 → exit 1

# 写：计划状态
--set-plan <plan_id> --status planning|in_progress|completed|on_hold
  - 枚举与 validate_structure.py:139 一致；非法值 exit 2
  - plan_id 不存在 → exit 1

# 读：计划完成状态判定（stdout 输出单行 JSON，供 code/archive 收尾检测调用）
--plan-state <plan_id>
  输出：{"plan_id": "...", "counts": {"completed": N, "in_progress": N, "pending": N, "blocked": N},
         "can_complete": <bool>, "blocked_ids": [...]}
  can_complete 定义：completed >= 1 且 pending == 0 且 in_progress == 0 且 blocked == 0
  plan_id 不存在 → exit 1

# 通用
--file <path>   覆盖默认路径（默认 <PROJECT_DIR>/.ghs/features.json，经 resolve_project_dir 解析）；
                供测试注入临时文件
```

### 通用约束

- 状态枚举与 `validate_structure.py:96`（特性：pending/in_progress/completed/blocked）、`:139`（计划：planning/in_progress/completed/on_hold）严格一致，非法输入 exit 2 且文件不动。
- 原子写：UTF-8 临时文件 + `os.replace`；保持既有 2 空格缩进；stdout 仅单行 ASCII 确认或 JSON。
- 错误信息英文（语言政策：日志/错误串英文），stderr 输出。
- 接入 `ghs_compat.force_utf8_stdio()`（与 p2-feat-001 后的脚本模式一致）。

### 测试（新增 `test_update_features.py`，unittest 模式）

- set-feature 正常/枚举非法/blocked 缺 reason/歧义 id/不存在 id
- set-plan 正常/枚举非法/不存在
- plan-state：全完成（can_complete=true）、含 blocked、含 pending、计划不存在
- 未知字段保留、原子写（异常时文件不动）

## 第 2 节 · `ghs-code/SKILL.md`：收尾闭环（单特性与 `--parallel` 共用）

1. **特性状态写入脚本化**：替换 Step 5 第 2 步及并行模式约 227 行的手改指令——所有 `status: "completed"`/`"blocked"` 写入改经 `update_features.py --set-feature`。新增条款（英文，LLM-facing）：

   > All status mutations in `.ghs/features.json` (feature-level and plan-level) MUST go through `update_features.py`. NEVER hand-edit the JSON and NEVER use inline `python -c` (same Windows-safety rationale as `update_plan_status.py` in ghs-plan).

2. **计划完成检测**（单特性 Step 5 末尾、并行编排最后一特性验证通过并标记后各一处）：运行 `--plan-state <plan_id>`：
   - `can_complete=true` → AskUserQuestion：「该计划下全部特性已完成，是否将计划标记为 completed？」→ 确认则 `--set-plan <plan_id> --status completed`，拒绝则保持 `in_progress` 并记录；
   - 存在 blocked → 不翻转，向用户报告各状态计数，并在收尾 Next Steps 注明阻塞项；
   - 仍有 pending（如用户中止某特性）→ 同样不翻转并报告。

3. 该检测步置于既有 Closing Steps（progress.md 条目 + 下一步指引）**之前**，检测结果写入当次 session 条目的 Next Steps。

## 第 3 节 · `ghs-archive/SKILL.md`：兜底翻转

替换「If No Completed Plans」死胡同段（57-59 行）为：

1. Step 1 `--list` 为空时，遍历活动计划逐一运行 `update_features.py --plan-state <plan_id>`；
2. 若存在「`can_complete=true` 但计划状态非 completed」→ AskUserQuestion：「计划 pX 全部特性已完成但状态为 <status>，翻转后归档？」→ 确认则 `--set-plan --status completed` → 重跑 `--list` → 继续正常流程；
3. 计划确有 pending/in_progress/blocked 特性 → 维持现有文案（提示 force-archive 或先完成特性），不提供翻转选项。

## 第 4 节 · `parallel_utils.py`：消灭静默选错计划

- 现状：`--plan-id` 缺省时取首个 `in_progress` 计划，否则 `plans[0]`（`parallel_utils.py:96-102`），多计划并存时静默选错（本轮实证：用户要 p2，脚本输出 p1）。
- 修改：无 `--plan-id` 且 `plans[]` 条目数 > 1 → exit 2，stderr 列出全部计划 id 要求显式传参；stdout 保持纯净（JSON 契约不变）。仅 1 个计划时保留默认行为（无歧义）。
- 同步：`ghs-code/SKILL.md` 并行模式 pre-flight 模板改为**必传** `--plan-id`。
- 测试：`test_parallel_utils.py` 新增多计划无参报错、单计划默认、显式传参三用例。

## 第 5 节 · `archive_plans.py`：归档目录名消毒

- 现状：`archive_plans.py:56` 仅 `replace(" ", "_").lower()`，计划名中的 `:` 等字符原样拼进目录名，Windows `mkdir` 抛 `NotADirectoryError: [WinError 267]`（本轮实证崩溃点 `:60`）。
- 修改：目录名派生处加白名单消毒——`[\\/:*?"<>|]` 及 ASCII 控制字符**剔除**，空格转下划线、小写逻辑不变；连续剔除后若目录名为空则回退 `<plan_id>`。
- 边界：**只消毒目录名派生点**；features.json 数据、progress.md 会话匹配等处的计划原名不动。
- 测试：`test_archive_plans.py` 新增「计划名含 `:` `/` `"`」用例，断言归档成功且目录名不含非法字符（复现本轮崩溃场景）。

## 第 6 节 · references 联动（第 2 节的完整性要求）

第 2 节条款生效后，references 中的手改指引与之直接冲突，必须同步：

- `shared/references/coding-agent.md`：275、278、328、329、338 行共 5 处「Update `.ghs/features.json` with status...」类指令，改为指向 `update_features.py --set-feature`（子代理保持只读——221 行「Do NOT modify .ghs/ files」不变，写入口全在 orchestrator 侧脚本调用）；
- `shared/references/examples.md`：291、299 行两处「Update `.ghs/features.json` and `.ghs/progress.md`」样例同步改为脚本调用表述。

## 测试与验证计划

1. 新增 `test_update_features.py`（第 1 节用例清单）；
2. `test_parallel_utils.py`、`test_archive_plans.py` 各增第 4/5 节用例；
3. 全量回归：`command python3 -m unittest discover -s plugin/shared/scripts`（现 126 个，全绿为门槛）；
4. `claude plugin validate` 通过；
5. 冒烟：对本仓库真实 `.ghs/` 跑 `validate_structure.py` 与 `update_features.py --plan-state p1`（只读），确认输出可解析。

## 验收标准

1. `ghs-code` 单特性模式与 `--parallel` 模式收尾均含计划完成检测，检测经 `--plan-state` 驱动，翻转必经 AskUserQuestion 确认；
2. `ghs-archive` 在「无 completed 计划」时主动探测 can_complete 并提供翻转路径，不再让用户手改 JSON；
3. features.json 状态变更三处 SKILL.md/references 指令全部指向脚本，仓库内「手改状态」表述清零；
4. 多计划 + 无 `--plan-id` 调用 `parallel_utils.py` 以非零码退出并列出计划；
5. 计划名含 `:`/`/` 的归档操作不再崩溃，目录名已消毒；
6. 全量测试通过，`claude plugin validate` 通过。
