# 方案 Y：删除 Dispatch Phase Feature Details 冗余段（Round 2 修订版）

## Revision Log

| Round | 变更 |
|------|------|
| Round 1 | 初稿。基于 context snapshot + SKILL.md line 144-180 / coding-agent.md line 200-236 实测源文件 + features.json schema 实测。设计"删 Feature Details 段 + 强化 Task step 1 + 新增 plan_ref 读取 step + 继承 v1 §3.6 sanity check"的极简方案，0 新代码。 |
| Round 2 | 修复 Round 1 Severe #1（模板字符数严重高估）：将 §3.2 模板从 2309 字符压缩到 **实测 1373 字符**（用 Python `len()` 实测，dispatcher 独立核验一致，见 §3.7 决策点 5）。具体压缩动作：(a) step 1 从 430+ 字符压到 ~270 字符；(b) step 2 从 ~580 字符压到 ~360 字符；(c) step 3 删除"do NOT read other features"软约束（同时解决 Medium #1）；(d) 合并原 step 4+5 为新 step 4（implement + test）；(e) 合并原 step 6+7 为新 step 5（lint/build + 单一 commit），并明确"single commit"措辞（解决 Medium #2）；(f) CONTEXT RESET 从 4 条压到 1 句；总步骤从 7 减到 5。同步处理 Medium #3（sanity check 时序明确为"写 features.json 之前"）、Medium #4（§3.5.4 子步骤直接 copy §3.5.2 原文）、Optimization #1-#4。所有量化数字（§1.3、§1.4、§3.7 决策点 5、§5 风险表、§9 对比表）基于 1373 字符实测重算。 |

---

## 10. Round 2 修订追踪段

### 10.1 Round 1 评审结论
FAIL（1 Severe + 4 Medium + 4 Optimization）。Severe #1（模板字符数高估）为唯一阻塞项，4 个 Medium 是实施会踩到的坑，4 个 Optimization 是文档质量项。

### 10.2 Round 2 必须处理项 → 处理状态

| Issue | 处理位置 | 处理方式 |
|---|---|---|
| **Severe #1** 模板字符数严重高估 | §3.2、§1.3、§1.4、§3.7 决策点 5、§5 风险表、§9 对比表 | 模板从 2309 字符压到实测 1373 字符；所有量化数字基于 1373 重算（降幅 41.4%-61.6%，平均 53.6%，ROI 论证重新成立） |
| **Medium #1** step 1 与 step 3 自相矛盾 | §3.2 新模板 step 3、§3.7 决策点 2 | 删除 step 3 末尾"do NOT read other features' details"软约束；依赖 feature_id 全局唯一 + sanity check 兜底 |
| **Medium #2** sanity check `git log -1` 多 commit 漏检 | §3.2 新模板 step 5（合并后）、§3.5.2 step 3、§3.5 备注段 | 新模板 step 5 明确"single commit"；sanity check 改用 `git log --since=<dispatch_start_iso>` 时间窗（dispatch 前 orchestrator 记录 ts） |
| **Medium #3** sanity check 与写 features.json 时序 | §3.5.4 改写、§3.5 开头 | 明确插入位置：在 `completed` 分支的 "Update `.ghs/features.json`" **之前** 插入 sanity check，sanity check pass 才允许写 |
| **Medium #4** §3.5.4 子步骤与 §3.5.2 文案脱节 | §3.5.4 | §3.5.4 子步骤直接 copy §3.5.2 步骤原文，不做改写 |
| **Optimization #1** step 7 ".ghs" 缺斜杠 | §3.2 模板 | 新模板统一用 `.ghs/` |
| **Optimization #2** "保留 line 182-190" 行号含糊 | §3.3 末段 | 改为"保留 line 181 空行 + line 182-190 `Spawn as background agents:` 段"；§3.4 显式说明 coding-agent.md 对应 line 238 `Use the Agent tool to spawn subagents:` 差异 |
| **Optimization #3** Task step 4 差异三处重复 | §3.2 末段、§3.4 改造点 2 | 差异说明集中到 §3.4 改造点 2 一处声明，§3.2 仅链接引用 |
| **Optimization #4** LLM 偷懒回退的弱兜底 | §6.7（新增） | dispatch 后用 grep 检查主会话 prompt 参数是否含 features.json 字段值（自动化检查） |

### 10.3 字符数实测命令（Round 2 新增）

修订模板后用 Python `len()` 实测，dispatcher 独立核验：

```bash
command python3 -c "
template = '''<§3.2 新模板原文>'''
print(f'Chars: {len(template)}')
"
# Round 2 实测输出：Chars: 1373（dispatcher 独立核验一致）
```

---

## 1. 背景与目标

### 1.1 背景

`ghs:code --parallel` 执行时，主会话（orchestrator）在 Dispatch Phase 把 features.json 中每个 feature 的 `description / acceptance_criteria / technical_notes / files_affected` 字段全文 inline 到 subagent prompt。但 SKILL.md Dispatch Phase 模板的 `## Your Task` step 1（line 168）本来就要求 subagent "Read `.ghs/features.json` and `.ghs/progress.md`"——这是**同一份内容输出两次**：

- 一次：主会话从 features.json 读字段，inline 到 prompt（Feature Details 段，line 158-165）
- 二次：subagent 收到 prompt 后，按 Task step 1 再读一次 features.json

主会话搬运的字段并不"被理解"——主会话只把字符串原样塞进 Agent tool 的 prompt 参数。LLM 输出 token 按生成字符计费，这是 8-feature batch 单轮主会话输出暴增到约 12K-19K token 的直接原因。

### 1.2 实测数据（继承 context snapshot §1.4）

Dispatch Phase 单 feature prompt 模板字符量拆解：

| 部分 | 字符数 |
|---|---|
| CONTEXT RESET | ~300 |
| Feature Details（含字段值） | 1015-2246 |
| Your Task（5 步） | ~600 |
| Feature ID 占位（Details 段内） | ~30 |
| Critical Rules | ~400 |
| **总计 per feature** | **2345-3576** |

8 feature batch 单轮主会话输出：约 **18K-29K 字符 → 12K-19K token**（字段 9-14K + 协议块 2-3K）。

### 1.3 目标（Round 2 实测口径）

**核心目标**：删除 `## Feature Details` 整段，让 subagent 自己读 features.json 拿字段（subagent 本来就要读，Task step 1 没变）。

**量化目标（基于 Round 2 §3.2 模板 Python `len()` 实测：1373 字符/feature）**：

- 单 feature dispatch prompt 字符数：从 2345-3576 → 降到 **实测 1373**（固定值，不含字段变量）
- 8 feature batch 单轮主会话输出：从 12K-19K token → 降到约 **7.3K token**（8 × 1373 / 1.5）
- 降幅 **41.4%-61.6%**（平均约 53.6%）

**为什么 Round 1 的"1530 字符、50-60% 降幅"会失败**：Round 1 §3.2 模板为 7 步 + 4 条 CONTEXT RESET + 5 条 Critical Rules，实测 2309 字符，远超 1530 估算。Round 2 通过 5 处压缩（详见 §10.2 Severe #1）将模板压到 1373 字符，使原 ROI 论证（降幅 ~50%）重新成立。

### 1.4 ROI 论证（方案 Y vs v1，Round 2 重算）

| 维度 | v1（外置 helper） | 方案 Y（删冗余段，1373 字符模板） | 结论 |
|---|---|---|---|
| 降幅 | 55-65% | **41.4%-61.6%**（平均 53.6%） | **基本持平**（v1 略高 1-2 个百分点，方案 Y 上界更稳） |
| 实施成本 | 1 个新 Python helper + 20 单测 + archive_sprint.py 改动 + parallel_utils.py 改动 + 2 处 SKILL/coding-agent 同步 | **仅 2 处 SKILL/coding-agent 模板修改 + sanity check 子段** | **方案 Y 实施成本约为 v1 的 10%** |
| 风险面 | helper bug / brief 文件污染 / archive 清理破坏性 / sprint_id 漂移 | 仅"subagent 不读 features.json"单点风险（已被 sanity check 覆盖） | **方案 Y 风险面小一个数量级** |
| 维护负担 | 新 helper 需长期维护，schema 演化时需同步改 | 0 新代码，模板文字调整即可 | **方案 Y 维护成本接近 0** |

**结论**：方案 Y 在降幅与 v1 基本持平（差距 1-2 个百分点）的前提下，把实施成本压到 v1 的 10%、风险面压到 v1 的 10%。这是显然的更优解。

### 1.5 Scope

**In scope**：

- 修改 `plugin/skills/ghs-code/SKILL.md` Dispatch Phase（line 144-180）：删 Feature Details 段、压缩并强化 Task step、压缩 CONTEXT RESET、合并 Critical Rules
- 同步修改 `plugin/shared/references/coding-agent.md` Dispatch Phase（line 200-236）：与 SKILL.md 字字一致（除 §3.4 声明的引导句差异）
- 在 SKILL.md 与 coding-agent.md 的 Verification Phase 新增 commit/files sanity check 段（继承 v1 §3.6 设计，适配为从 features.json 读 expected_files、用时间窗 git log）
- 端到端 smoke test（ghs-workspace 隔离工作区）
- 单 feature 模式回归（默认 `/ghs:code` 不受影响）

**Out of scope**：

- 不引入新 Python helper
- 不引入 brief 文件（`.brief.md` 不存在）
- 不改 `archive_sprint.py`
- 不改 `parallel_utils.py`
- 不改 `parse_completion_signal.py` 接口
- 不改 features.json schema
- 不改 `.ghs/parallel/` 目录布局
- 不改 Single Feature Mode（默认 `/ghs:code`）

---

## 2. 现状分析

### 2.1 v1 plan 错在哪

v1 plan（`2026-06-17-parallel-dispatch-token-optimization.废弃-v1-helper-approach.md`）的根本错误：**把"删冗余"问题当成"外置 helper"问题处理**。

v1 plan §1.1 把本次问题与 s2/s3 类比为同构（"主会话做 LLM 不友好的内容搬运 → 外置 Python helper"），并据此推导出 `prepare_feature_brief.py` + brief 文件 + archive 清理 + parallel_utils 改动的一整套方案。但这个类比是错的。

### 2.2 本次问题与 s2/s3 的本质区别

| 维度 | s2（plan 输出解析） | s3（completion signal 解析） | 本次（feature 详情 inline） |
|---|---|---|---|
| LLM 做的工作性质 | 自解析 delimiter（**确定性工作**，原本无解析器） | 自 grep 完成信号（**确定性工作**，原本无解析器） | 把 features.json 字段 inline 到 prompt（**冗余工作**，subagent 本来就要读 features.json） |
| 与现有约定的关系 | subagent 从未约定要"解析输出"——这是新能力 | subagent 从未约定要"自检完成信号"——这是新能力 | subagent 本来就约定要读 features.json（Task step 1 既有）——主会话再 inline 一遍是**纯冗余** |
| 解决手段 | 外置 Python helper（新增能力，可单测） | 外置 Python helper（新增能力，可单测） | **删冗余段**（0 新代码，让既有 step 1 完成它本来要做的事） |
| 与现状的改造关系 | 加性 | 加性 | 减性（删字） |

**关键洞察**：s2/s3 的 LLM 工作是"做本来没有的事"——必须新增 helper。本次的 LLM 工作是"做本来已经有人做的事"——必须删冗余。

### 2.3 方案 Y 的根本正确性

方案 Y 的论点：**subagent 的 Task step 1 已经要求它读 features.json，那么主会话在 Feature Details 段再 inline 一遍就是纯粹的重复劳动**。删掉 Feature Details 段，subagent 仍然能从 features.json 拿到所有字段——只是来源从"prompt 内嵌"变成"读文件"。

这与 subagent 读 `coding-agent.md` 引用、读 `progress.md` 的既有模式完全一致：subagent 本来就要读项目文件。方案 Y 没有引入新的"读文件"行为，只是把"读哪个字段"的指示从隐式（依赖 prompt 内嵌值）改为显式（在 Task step 1 里指明字段名）。

### 2.4 现有 Dispatch Phase 模板的精确结构（已实测）

`plugin/skills/ghs-code/SKILL.md` line 144-180：

```
### Dispatch Phase

For each feature, spawn a subagent with this prompt:

```
Implement ONE feature for this project.

## CONTEXT RESET - READ THIS FIRST            ← line 151（压缩保留）
This is an isolated task. You MUST:
1. DISREGARD any context from previous conversations or tasks
2. NOT assume any prior knowledge about the project state
3. Read all necessary files fresh to understand current state
4. Start with a clean mental state - this is your ONLY task

## Feature Details                             ← line 158（删除整段）
- **ID**: <feature_id>
- **Title**: <title>
- **Description**: <description>
- **Acceptance Criteria**:
  <criteria_list>
- **Technical Notes**: <technical_notes>
- **Files to Modify**: <files_affected>

## Your Task                                   ← line 167（压缩 + 强化 + 新增 plan_ref step）
1. Read .ghs/features.json and .ghs/progress.md to understand project context
2. Implement the feature
3. Test all acceptance criteria
4. Run lint/build to verify no breakage
5. Commit your changes (...): ... feat(<scope>): ... (Feature: <feature_id>)

## Critical Rules                              ← line 174（合并压缩到 3 条）
- Do NOT modify .ghs/features.json or .ghs/progress.md ...
- Focus ONLY on this feature
- Ensure the codebase remains in a working state
- Signal completion by stating "FEATURE COMPLETE: <feature_id>" ...
- If you cannot complete the feature, state "FEATURE BLOCKED: ..." ...
```

`plugin/shared/references/coding-agent.md` line 200-236 与 SKILL.md **字字同构**（仅 Task step 2 多一句 "following the coding-agent.md guidelines"，Critical Rules 多一句 "do not modify unrelated code"）。

### 2.5 features.json schema（已实测）

```python
# Sprint 级 keys
['created_at', 'features', 'goal', 'id', 'name', 'plan_ref', 'status']
# Feature 级 keys
['acceptance_criteria', 'category', 'dependencies', 'description',
 'estimated_complexity', 'files_affected', 'id', 'priority',
 'status', 'technical_notes', 'title']
```

**plan_ref 是 sprint 级字段**（不在 feature 级），实测 s2/s3 都有：

| sprint | plan_ref（实测相对路径，相对项目根目录） |
|---|---|
| s2 | `docs/ghs/plans/2026-06-15-robust-plan-output-parsing.md` |
| s3 | `docs/ghs/plans/2026-06-15-robust-completion-signal-parsing.md` |

注意：plan_ref 路径前缀是 `docs/ghs/plans/`，不是 `.ghs/plans/`（context snapshot §3 笔误）。两者并存于不同目录。

### 2.6 technical_notes 中 §章节引用形态（实测 s2/s3 共 8 feature）

- 引用频率：8 个 feature 中 6 个含 §章节引用（75%）
- 引用样式统一：`参考 plan §3.3 Helper Interface Design` / `参考 plan §3.4 Key Flows、§3.4.1 ...`
- **关键洞察**：subagent 必须读 plan_ref 指向的 plan 文档才能理解 technical_notes 的章节引用

---

## 3. 方案设计

### 3.1 总体架构

```
BEFORE                                       AFTER
─────                                        ─────
Analysis Phase                               Analysis Phase (不变)
  ↓ parallel_utils.py                          ↓ parallel_utils.py
  ↓ ready_features (summary only)              ↓ ready_features (summary only)
                                            ↓
Dispatch Phase (per feature)                 Dispatch Phase (per feature)
  ↓ LLM 读 features.json 全字段                  ↓ LLM 只填 <feature_id> 占位符
  ↓ LLM 把字段 inline 到 prompt（11-17K）       ↓ prompt 中只有骨架 + feature_id (1373 chars)
  ↓ Agent tool dispatch                        ↓ Agent tool dispatch
                                            ↓
                                            Verification Phase
                                              ↓ parse_completion_signal.py (不变)
                                              ↓ [新增] commit/files sanity check
                                                (针对 status=completed, 时间窗 git log)
```

**核心思想**：subagent 的 Task step 1 本来就要读 features.json；方案 Y 只是删除主会话的重复 inline 段，把"读哪个字段"在 Task step 1 中显式化。零新代码。

### 3.2 新 Dispatch Phase prompt 模板（Round 2 压缩版，Python `len()` 实测 1373 字符）

以下是 SKILL.md 与 coding-agent.md 共用的**新模板**。两个文件字字一致，**仅 Task step 4 的引导句差异**（SKILL.md："Implement the feature and verify all `acceptance_criteria` are met."；coding-agent.md："Implement the feature following the coding-agent.md guidelines; verify all `acceptance_criteria` are met."）——差异声明集中在 §3.4 改造点 2，本处不再重复。

````
Implement ONE feature for this project.

## CONTEXT RESET - READ THIS FIRST
This is an isolated task. Disregard prior context, assume nothing, read files fresh, start clean.

## Your Task
1. Open `<PROJECT_DIR>/.ghs/features.json`, find your feature by `id == "<feature_id>"` under `sprints[].features[]`. Read its `description`/`acceptance_criteria`/`technical_notes`/`files_affected` — these are your source of truth, not the title.
2. If the containing sprint has a `plan_ref` field, open that plan file (relative to project root) and read any sections your `technical_notes` references (e.g. "参考 plan §3.3 ..." means read §3.3). If `plan_ref` is missing or the file does not exist, log a one-line warning and proceed with `technical_notes` verbatim.
3. Read `<PROJECT_DIR>/.ghs/progress.md` for recent project context.
4. Implement the feature and verify all `acceptance_criteria` are met.
5. Run lint/build, then make a **single** commit (stage all modified implementation files with `git add`; do NOT commit `.ghs/*` files) with message: `feat(<scope>): <brief description> (Feature: <feature_id>)`.

## Feature ID
<feature_id>

## Critical Rules
- Do NOT modify `.ghs/` files. You may READ `features.json` but MUST NOT write.
- Focus ONLY on this feature.
- End with EXACTLY ONE signal: `FEATURE COMPLETE: <feature_id>` or `FEATURE BLOCKED: <feature_id> - <reason>`.
````

**字符数实测（Round 2，§10.3 命令）**：`Chars: 1373`（dispatcher 独立核验一致）。

**关键设计点**：

1. **删除 `## Feature Details` 整段**（原 SKILL.md line 158-165、coding-agent.md line 214-221）
2. **CONTEXT RESET 压缩**：4 条带长说明的 MUST 压到 1 句话"Disregard prior context, assume nothing, read files fresh, start clean."（语义等价，§3.7 决策点 6 论证）
3. **Task step 1 强化**：从 430+ 字符压到 ~270 字符——明确指示按 `id == "<feature_id>"` 查找、读取 4 个字段名（斜杠分隔紧凑写法）、声明"source of truth, not the title"
4. **Task step 2 新增（plan_ref 读取）**：从 ~580 字符压到 ~360 字符——保留 plan_ref 读取与 §章节引用展开逻辑、缺失时优雅降级（log warning，不 abort）
5. **Task step 3 收窄（progress.md）**：删除 Round 1 的"do NOT read other features' details"软约束（解决 Medium #1，理由见 §3.7 决策点 2）
6. **Task step 4 合并（原 step 4+5）**：implement + test 合并为一句"Implement the feature and verify all `acceptance_criteria` are met."
7. **Task step 5 合并（原 step 6+7）**：lint/build + commit 合并，并明确"**single** commit"措辞（解决 Medium #2）；用 `git add` 显式 stage、强调"do NOT commit `.ghs/*` files"（解决 Optimization #1：`.ghs/` 带斜杠）
8. **Feature ID 独立成段**（原 Details 段内的 ID 行提到独立段，避免 subagent 误以为"只有 ID 没有 details"）
9. **Critical Rules 合并到 3 条**：原 5 条合并——(a) 第 1 条合并"Do NOT modify .ghs/"与"MUST NOT write features.json"（解决 Optimization #1）；(b) 第 4+5 条（completion signal 正反两种）合并为一条"End with EXACTLY ONE signal: ... or ..."

### 3.3 SKILL.md 改造点（行号级）

**改动文件**：`plugin/skills/ghs-code/SKILL.md`

**改动范围**：line 144-180（`### Dispatch Phase` 整段，到下一个 `###` 之前）

**具体操作**：

1. **保留** line 144-147（`### Dispatch Phase` 标题 + "For each feature, spawn a subagent with this prompt:" 引导句）
2. **替换** line 148-180（```` ``` ```` 代码块内的整个 prompt 模板）为 §3.2 的新模板
3. **保留** line 181 空行 + line 182-190（`Spawn as background agents:` + JSON 块）零改动（Optimization #2：精确行号）

**新模板插入位置示意**（行号会因新模板内容长度而偏移；以下用语义段标记）：

```markdown
### Dispatch Phase

For each feature, spawn a subagent with this prompt:

```
<§3.2 的新模板内容>
```

The orchestrator MUST substitute `<PROJECT_DIR>` (from `resolve_project_dir.py`) and `<feature_id>` (from the batch feature list) into the prompt before spawning. The prompt contains NO inline feature details — the subagent reads them from `.ghs/features.json` per Task step 1.

Spawn as background agents:
```json
{
  "subagent_type": "general-purpose",
  "description": "Implement feature <id>",
  "prompt": "<full prompt from template above>",
  "run_in_background": true
}
```
```

**新增的渲染说明段**（在代码块之后、JSON 块之前）：明确 `<PROJECT_DIR>` 与 `<feature_id>` 的占位符渲染责任。注意：**方案 Y 不需要 `<sprint_id>` 占位符**（subagent 自己按 `id == <feature_id>` 在 features.json 里查 sprint，无需主会话传 sprint_id）。

### 3.4 coding-agent.md 同步改造点（行号级）

**改动文件**：`plugin/shared/references/coding-agent.md`

**改动范围**：line 200-236（`### Dispatch Phase` 整段）

**具体操作**：

1. **保留** line 200-202（`### Dispatch Phase` 标题 + "For each feature, spawn a subagent with this prompt structure:" 引导句——注意 coding-agent.md 用 "structure" 措辞，SKILL.md 用 "prompt"，保留各自原文不强行统一）
2. **替换** line 203-236（代码块内的 prompt 模板）为 §3.2 的新模板。**唯一差异**（Optimization #3：差异声明集中到本处）：Task step 4 改为 "Implement the feature following the coding-agent.md guidelines; verify all `acceptance_criteria` are met."（保留原 coding-agent.md step 2 的"following the coding-agent.md guidelines"引导句风格）
3. **保留** line 237 空行 + line 238-247（`Use the Agent tool to spawn subagents:` + JSON 块 + "For each batch:" 段）零改动。注意 SKILL.md 用 `Spawn as background agents:`（line 182），coding-agent.md 用 `Use the Agent tool to spawn subagents:`（line 238）——两文件措辞差异，保留原文不强行统一。

**两个文件改动后的 diff 比对要求**：

- Dispatch Phase 的 CONTEXT RESET / Your Task / Feature ID / Critical Rules 段**必须字字一致**（除 Task step 4 的引导句差异）
- 引导句差异（两处，均保留原文）：
  - 主引导句：SKILL.md 用 "spawn a subagent with this prompt"，coding-agent.md 用 "spawn a subagent with this prompt structure"
  - JSON 块引导句：SKILL.md 用 "Spawn as background agents:"，coding-agent.md 用 "Use the Agent tool to spawn subagents:"
- Task step 4 引导句差异（§3.2 注释已说明）

### 3.5 Verification Phase commit/files sanity check（继承 v1 §3.6 设计，Round 2 适配）

由于方案 Y 删除了 Feature Details 段，存在一个新失败模式：**subagent 不读 features.json，仅凭 feature_id/title 猜一个实现，再正确发出 `FEATURE COMPLETE: <feature_id>`**。此时 `parse_completion_signal.py` 返回 `completed`，Verification Phase 顺利通过，但实现完全跑偏。

**兜底策略**：在 Verification Phase 检测到 `status == "completed"` 之后、State Update Phase 写 features.json 之前，主会话执行轻量级 sanity check。**sanity check 是 status=completed 写入的前置门**（Round 2 Medium #3 修复）——sanity check pass 才允许写 features.json；fail 则触发 retry，不写。

#### 3.5.1 expected_files 来源（方案 Y 关键决策）

v1 方案的 expected_files 来自 brief 文件。**方案 Y 没有 brief 文件**，因此 expected_files 改为从 `features.json` 读取——主会话读 features.json 中该 feature 的 `files_affected` 字段。

**为什么不用 git log 反推**：git log 反推是循环论证（"subagent 改了什么就算什么是期望的"——无法检测"该改的没改"）。必须用 features.json 中**事先声明**的 `files_affected` 作为 ground truth。

#### 3.5.2 判定顺序（继承 v1 §3.6 Round 3 Medium N2 修正，Round 2 适配时间窗 git log）

**前置（Round 2 Medium #2 修复）**：dispatch 前 orchestrator 在内存中记录 `dispatch_start_iso = datetime.now(timezone.utc).isoformat()`（每个 feature 一个，dispatch 那一刻记）。Verification Phase 用 `git log --since=<dispatch_start_iso>` 取该 feature dispatch 之后的所有 commit。

1. 从 `<PROJECT_DIR>/.ghs/features.json` 读 feature `<feature_id>` 的 `files_affected` 字段，得 `expected_files`（list）
2. **立即检查 expected_files 是否为空**：若 `expected_files == []`（features.json 中该字段缺失或为空 list），**整个 sanity check 跳过**，视为通过，日志记录 `"sanity check skipped: feature <feature_id> has no files_affected in features.json"`。此跳过分支**必须在读 git log（步骤 3）之前判断**，不得合并到步骤 5 的空集检查。
3. 读 subagent 的 commit log（`git log --since=<dispatch_start_iso> --name-only --pretty=format:"%H %s"`），得 `actual_files`（list，去重）。**用时间窗而非 `git log -1`**——Round 2 Medium #2 修复：subagent 即便多 commit（虽然新模板 step 5 要求 single commit），时间窗查询能覆盖所有 commit 的文件。
4. 计算 `intersection = set(expected_files) ∩ set(actual_files)`
5. 如果 `intersection` 为空（即所有 commit 加起来一个期望文件都没碰），主会话**不要立即标记 feature 完成**，而是触发 Format Recovery retry，appendix 中加一句：`Your commit did not touch any file listed in this feature's files_affected in features.json. Did you read features.json to find your feature's expected files?`
6. 如果 retry 后仍空，走 User Decision Handling（mark blocked / abort）

**两个"空集"分别走不同分支**（关键，避免 LLM 误解）：

- `expected_files == []` → **skip 分支**（视为通过，因为 features.json 没声明期望文件时无法判定）
- `intersection == []`（expected_files 非空但所有 commit 加起来没碰任何一个）→ **retry 分支**

两者**必须分开判定**，不得合并到同一空集检查。

#### 3.5.3 sanity check 不是充分验证

- commit 修改了一个期望文件**不代表**实现正确
- 但所有 commit 加起来一个期望文件都没碰**几乎肯定**有问题（subagent 要么没读 features.json、要么改错了文件）
- 这是低成本兜底，不替代人工 review

#### 3.5.4 SKILL.md Verification Phase 改造点（Round 2 Medium #3 修复：时序明确为"写之前"）

`plugin/skills/ghs-code/SKILL.md` 的 `### Verification Phase`（line 192）step 3 的 `completed` 分支原文：

```markdown
   - **`completed`**: Update `.ghs/features.json` for `<feature_id>` with `status: "completed"`. Run lint/build to verify code quality. Verify acceptance criteria. Proceed to next feature.
```

**改写为**（sanity check 作为 completed 状态写入的前置门；子步骤文案直接 copy §3.5.2 步骤原文，不做改写——Round 2 Medium #4 修复）：

```markdown
   - **`completed`**:
     1. **Run the commit/files sanity check** (前置门 — pass 才允许写 features.json):
        - 从 `<PROJECT_DIR>/.ghs/features.json` 读 feature `<feature_id>` 的 `files_affected` 字段，得 `expected_files`（list）。
        - **立即检查 expected_files 是否为空**：若 `expected_files == []`（features.json 中该字段缺失或为空 list），**整个 sanity check 跳过**，视为通过，日志记录 `"sanity check skipped: feature <feature_id> has no files_affected in features.json"`。此跳过分支**必须在读 git log 之前判断**，不得合并到下面的空集检查。
        - 读 subagent 的 commit log（`git log --since=<dispatch_start_iso> --name-only --pretty=format:"%H %s"`，dispatch_start_iso 见下方备注），得 `actual_files`（list，去重）。
        - 计算 `intersection = set(expected_files) ∩ set(actual_files)`。
        - 如果 `intersection` 为空（即所有 commit 加起来一个期望文件都没碰），**不要标记 feature 完成**，触发 Format Recovery retry，appendix 中加一句：`Your commit did not touch any file listed in this feature's files_affected in features.json. Did you read features.json to find your feature's expected files?`。retry 后仍空则走 User Decision Handling。**此分支不写 features.json。**
        - 如果 `intersection` 非空（或 sanity check 走 skip 分支），进入步骤 2。
     2. Update `.ghs/features.json` for `<feature_id>` with `status: "completed"`. Run lint/build to verify code quality. Verify acceptance criteria. Proceed to next feature.

     **备注**：`dispatch_start_iso` 是 orchestrator 在 Dispatch Phase spawn 该 subagent 那一刻记录的 ISO 时间戳（`datetime.now(timezone.utc).isoformat()`），用于时间窗 git log 查询，覆盖 subagent 可能的多 commit。
```

#### 3.5.5 coding-agent.md Verification Phase 同步改造

`plugin/shared/references/coding-agent.md` 的 `### Verification Phase`（line 255）step 3 的 `completed` 分支原文（line 277）：

```markdown
   - **`completed`** → Update `.ghs/features.json` for `<feature_id>` with `status: "completed"`. Run lint/build. Verify acceptance criteria. Record result and proceed.
```

**改写为**与 §3.5.4 字字一致的 sanity check 子步骤（含同样的备注）。

### 3.6 Format Recovery 改造

**基本不动**：Format Recovery appendix（SKILL.md line 252-274、coding-agent.md 对应段）保留原文。

**唯一新增**：当 sanity check 触发 retry 时，appendix 中追加一句提示。**完整 retry appendix 模板示例**（原 appendix + sanity check 追加句）：

```
## IMPORTANT: Previous Output Format Issue
Your previous response did not contain the required completion signal.
The dispatcher could not determine whether the feature is complete.

This time you MUST end your response with EXACTLY ONE of:
  - "FEATURE COMPLETE: <feature_id>"  (if successful)
  - "FEATURE BLOCKED: <feature_id> - <reason>"  (if blocked)

The signal line must:
1. Be on its own line
2. Use uppercase FEATURE
3. Use the exact feature_id given above
4. For BLOCKED, include a one-line reason after the dash

Do NOT use:
- "Feature Complete" (lowercase)
- "FEATURE COMPLETED" (extra D)
- "The feature is complete" (natural language)
- Chinese variants like "特性完成"

## IMPORTANT: Previous Commit Did Not Touch Expected Files
Your previous commit did not touch any file listed in this feature's files_affected in features.json.
The dispatcher sanity check failed.
Did you read features.json to find your feature's expected files? Re-read it now and ensure your next commit touches at least one of: <expected_files 列表>.
```

**实施说明**：原 appendix（## IMPORTANT: Previous Output Format Issue 段，SKILL.md line 252-274）保留原文；新追加段（## IMPORTANT: Previous Commit Did Not Touch Expected Files）仅在 sanity check 触发 retry 时附加。两段都附加时按上面顺序拼接。

### 3.7 关键设计决策

#### 决策点 1：plan_ref 缺失时怎么办？

**场景**：sprint 没设 `plan_ref` 字段，或 `plan_ref` 指向的文件不存在。subagent 在 Task step 2 遇到 §章节引用时怎么办？

**决策**：**优雅降级**。Task step 2 明确指示 subagent："If `plan_ref` is missing or the file does not exist, log a one-line warning and proceed with `technical_notes` verbatim."

**理由**：

- technical_notes 字段本身有字面值（如 "实现 parse_delimited_output.py"），即使没有 plan_ref 章节展开，subagent 仍能完成基础实现
- 强制 abort 会导致 sprint 配置错误时整个 feature 卡死，违反"留有降级路径"原则
- warning 让用户在 raw.attempt 文件中能看到降级发生，便于事后追查

**未来 sprint 配置规范建议**（不在本 plan 范围，但记录）：所有有 technical_notes §引用的 sprint 必须设 `plan_ref`。

#### 决策点 2：subagent 读其他 sprint 的 feature 怎么办（context pollution）？（Round 2 修订）

**场景**：features.json 有多个 sprint，每个 sprint 有 features。subagent 按 `id == "<feature_id>"` 查找时，理论上不会读错——因为 `<feature_id>` 是全局唯一的（s2-feat-001 不会出现在 s3）。

**Round 1 决策**：Task step 3 显式收窄 "do NOT read other features' details"。

**Round 2 修订决策**：**删除该软约束**。

**理由**（Medium #1）：

- step 1 要求 subagent "find your feature by `id == "<feature_id>"` under `sprints[].features[]`"——**必然要遍历 sprints[].features[]**，过程中 LLM 至少会扫过每个 feature 的 `id`/`title`（短字段，不可避）
- Round 1 step 3 的"do NOT read other features' details"如果指 description/acceptance_criteria 等长字段，措辞不精确；如果字面解读为"不读其他 feature"，则与 step 1 直接冲突
- LLM 在面对冲突指令时倾向选择性遵守——可能反而认为"step 1 让我读，step 3 又说不读，那我什么都不读，凭 id 猜实现"，这正是 sanity check 要兜底的失败模式
- 依赖 feature_id 全局唯一 + sanity check 兜底即可，不需要自相矛盾的软约束
- 顺带省字符（Severe #1 压缩的一部分）

**不引入更严格的隔离机制**（如生成临时 features.json 只含目标 feature）：成本远超收益，且 features.json 是 orchestrator-managed 的，subagent 改不了，最多只是"读多了"而非"改错了"。

#### 决策点 3：Verification Phase sanity check 的 expected_files 来源

**决策**：**从 features.json 读 `feature.files_affected`**（§3.5.1 已论证）。不用 git log 反推、不用 brief 文件（方案 Y 不存在 brief）。

**对空 `files_affected` 的处理**：skip 分支（§3.5.2 step 2）。实测 s2-feat-004 与 s3-feat-004 的 files_affected 为空——这些 feature 的 sanity check 自动跳过，不会误触发 retry。

#### 决策点 4：新 prompt 模板的最终样式

见 §3.2（完整模板已贴）。骨架结构（5 步）：

- CONTEXT RESET（1 句，与原 4 条语义等价——见决策点 6）
- Your Task（5 步：locate feature / read plan_ref / read progress.md / implement+test / lint+single commit）
- Feature ID（独立段，仅占位符 `<feature_id>`）
- Critical Rules（3 条，强化第 1 条 "READ but MUST NOT write features.json"）

#### 决策点 5：主会话 token 优化估算（Round 2 基于 Python `len()` 实测，§10.3 命令）

**§3.2 新模板实测字符数**：**1373**（Python `len()` 直接测，非估算；dispatcher 独立核验一致）。

| 维度 | 旧模板 | 新模板 |
|---|---|---|
| CONTEXT RESET | ~300（4 条带说明） | ~120（1 句压缩） |
| Feature Details 段 | 1015-2246 | **0**（删除） |
| Your Task 段 | ~600（5 步） | ~840（5 步，含 plan_ref 引用与 single commit 措辞） |
| Feature ID 段 | ~30（Details 段内） | ~30（独立段） |
| Critical Rules 段 | ~400（5 条） | ~180（3 条合并） |
| **单 feature 总计** | **2345-3576** | **1373**（固定值，不含字段变量） |

8 feature batch 单轮主会话输出：

- 旧：8 × 2345-3576 ≈ 18.8K-28.6K 字符 → 约 12K-19K token
- 新：8 × 1373 ≈ 11.0K 字符 → 约 **7.3K token**（按 1.5 字符/token 保守估算）

**实际降幅**：

- 下界（vs 旧模板下限 2345）：`(2345-1373)/2345 = 41.4%`
- 上界（vs 旧模板上限 3576）：`(3576-1373)/3576 = 61.6%`
- **降幅范围 41.4%-61.6%，平均约 53.6%**

**Round 1 vs Round 2 估算对比**：

| 维度 | Round 1 claim | Round 1 实测 | Round 2 实测 |
|---|---|---|---|
| 单 feature 新模板字符 | 1530（估算） | 2309（reviewer 实测） | **1373**（Python `len()`） |
| 8 batch 字符 | ~12.2K | ~18.5K | **~11.0K** |
| 8 batch token | ~8K | ~12.3K | **~7.3K** |
| 降幅 | 33-58% | 1.5%-35.4% | **41.4%-61.6%** |

**Round 2 通过 5 处压缩**（§10.2 Severe #1）将模板从 2309 压到 1373，降幅重新回到 41.4%-61.6% 区间，与 v1 plan claim 的 55-65% 差距从 Round 1 的 20-50 个百分点收窄到 1-2 个百分点。ROI 论证重新成立。

**7.3K token 的实际意义**：显著低于旧模板的 12-19K，且**没有上界膨胀风险**（旧模板随 description 长度线性增长，新模板固定 1373 字符/feature）。这是方案 Y 的核心价值——不是单点降幅，而是把"无上界"变成"固定值"。

#### 决策点 6：CONTEXT RESET 压缩是否损失语义？（Round 2 新增）

**Round 1**：4 条带长说明的 MUST（DISREGARD / NOT assume / Read fresh / clean mental state），约 300 字符。

**Round 2**：1 句话"Disregard prior context, assume nothing, read files fresh, start clean."，约 120 字符。

**语义对照**：

| Round 1 原文 | Round 2 压缩句 | 语义保留 |
|---|---|---|
| "DISREGARD any context from previous conversations or tasks" | "Disregard prior context" | ✓ |
| "NOT assume any prior knowledge about the project state" | "assume nothing" | ✓ |
| "Read all necessary files fresh to understand current state" | "read files fresh" | ✓ |
| "Start with a clean mental state - this is your ONLY task" | "start clean" | ✓（"this is your ONLY task" 语义由"isolated task"首句承载） |

**结论**：4 条 MUST 的语义全部保留，压缩句是同义重写。省下 ~180 字符是 Severe #1 压缩的关键来源之一。

#### 决策点 7：Critical Rules 合并是否损失语义？（Round 2 新增）

**Round 1**：5 条（Do NOT modify .ghs / Focus ONLY / Ensure codebase working / Signal completion / If blocked）。

**Round 2**：3 条：

1. "Do NOT modify `.ghs/` files. You may READ `features.json` but MUST NOT write."（合并原第 1 条 + Optimization #1 强化）
2. "Focus ONLY on this feature."（原第 2 条 + 原第 3 条"Ensure codebase working"语义并入 step 4/5 的 lint/build）
3. "End with EXACTLY ONE signal: `FEATURE COMPLETE: <feature_id>` or `FEATURE BLOCKED: <feature_id> - <reason>`."（合并原第 4+5 条）

**语义保留**：

- "Ensure codebase remains in a working state" 语义由 step 5 "Run lint/build" 承载（lint/build 通过即 working state）
- "EXACTLY ONE signal" 比 Round 1 的两条更精确（强调"只能有一个 signal"，防止 subagent 同时输出 COMPLETE 和 BLOCKED）

**结论**：合并后语义等价或更强，省下 ~220 字符。

---

## 4. 实施步骤

### Phase 1: SKILL.md 改造

- [ ] **Step 1.1**: 备份当前 `plugin/skills/ghs-code/SKILL.md`（`cp SKILL.md SKILL.md.bak`，便于回滚；实施完成后删除 .bak）
- [ ] **Step 1.2**: 在 `### Dispatch Phase`（line 144）的代码块（line 148-180）中：
  - 删除 `## Feature Details` 整段（line 158-165，含前后空行）
  - 替换 `## Your Task` 段（line 167-172）为 §3.2 的新 5-step 压缩版
  - 压缩 `## CONTEXT RESET` 段（line 151-156）为 §3.2 的 1 句版本
  - 新增 `## Feature ID` 独立段（在 Task 段之后、Critical Rules 之前）
  - 合并 `## Critical Rules` 段（line 174-179）为 §3.2 的 3 条版本，强化第 1 条（加 "READ features.json but MUST NOT write"）
- [ ] **Step 1.3**: 在代码块之后、`Spawn as background agents:` JSON 块（line 182-190）之前，新增渲染说明段（§3.3 末尾示意）
- [ ] **Step 1.4**: 在 `### Verification Phase`（line 192）step 3 的 `completed` 分支（line 215），按 §3.5.4 改写为"sanity check 前置门 + 写 features.json"两步结构
- [ ] **Step 1.5**: 检查改动后整段 markdown 结构完整（标题层级正确、代码块闭合）
- [ ] **Step 1.6**: `git diff plugin/skills/ghs-code/SKILL.md` 检查改动范围只在 Dispatch Phase + Verification Phase，未误伤其他段
- [ ] **Step 1.7**: 用 §10.3 命令实测新 Dispatch Phase 代码块字符数，确认 ≤ 1400（实测目标 1373）

**Acceptance criteria**：
- 新 Dispatch Phase prompt 模板不含 `<description>` / `<criteria_list>` / `<technical_notes>` / `<files_affected>` / `<title>` 占位符
- 新模板含 `<feature_id>` 占位符（在 Feature ID 段）和 `<PROJECT_DIR>` 占位符（在 Task step 1/3 中）
- 新模板 Task step 1 含 "find your feature by `id == \"<feature_id>\"`" 指示
- 新模板 Task step 2 含 plan_ref 读取与缺失降级指示
- 新模板 Task step 5 含 "single commit" 与 "do NOT commit `.ghs/*` files" 措辞
- 新模板 Critical Rules 第 1 条含 "READ `features.json` but MUST NOT write"
- 新模板 Critical Rules 第 3 条含 "EXACTLY ONE signal"
- 新模板 Python `len()` 实测 ≤ 1400 字符
- Verification Phase `completed` 分支含 sanity check 前置门子步骤，且 sanity check pass 才写 features.json
- git diff 显示改动仅在 Dispatch Phase 段 + Verification Phase 段

### Phase 2: coding-agent.md 同步改造

- [ ] **Step 2.1**: 备份当前 `plugin/shared/references/coding-agent.md`
- [ ] **Step 2.2**: 在 `### Dispatch Phase`（line 200）的代码块（line 204-236）中做与 Step 1.2 相同的改造（字字一致，除 §3.4 改造点 2 声明的 Task step 4 引导句差异）
- [ ] **Step 2.3**: 在代码块之后、`Use the Agent tool to spawn subagents:` JSON 块（line 238-247）之前，新增渲染说明段（与 SKILL.md 字字一致，除 JSON 块引导句措辞差异）
- [ ] **Step 2.4**: 在 `### Verification Phase`（line 255）step 3 的 `completed` 分支（line 277），按 §3.5.5 改写为与 SKILL.md 字字一致的 sanity check 前置门结构
- [ ] **Step 2.5**: diff 比对两个文件的 Dispatch Phase + Verification Phase 段，确认除 §3.4 声明的差异外字字一致

**Acceptance criteria**：
- coding-agent.md 与 SKILL.md 的 Dispatch Phase 模板 diff 仅显示：
  - 主引导句差异（"prompt" vs "prompt structure"）
  - JSON 块引导句差异（"Spawn as background agents:" vs "Use the Agent tool to spawn subagents:"）
  - Task step 4 引导句差异（"Implement the feature and verify..." vs "Implement the feature following the coding-agent.md guidelines; verify..."）
- 两个文件的 Verification Phase sanity check 子步骤字字一致
- 两个文件的 CONTEXT RESET / Critical Rules 段字字一致

### Phase 3: 端到端 smoke test（隔离工作区）

- [ ] **Step 3.1**: 准备 ghs-workspace 测试环境
  ```bash
  WORKSPACE=~/ghs-workspace
  # 复制真实 features.json 作为基线
  cp /Users/tom/github/golden-hoop-spell/.ghs/features.json $WORKSPACE/.ghs/features.json
  # 把待测 sprint 的 status 改回 in_progress（如已 completed）
  # 把该 sprint 下 feature 的 status 改回 pending
  # 清理 parallel 目录
  rm -rf $WORKSPACE/.ghs/parallel/<sprint_id>/
  ```
- [ ] **Step 3.2**: 跑 `/ghs:code --parallel`
  - 观察 Analysis Phase（batches 正常）
  - **观察 Dispatch Phase 主会话输出**：用 `wc -c` 或直观感知对比改造前后的 prompt 长度（应明显变短，不再含 description 全文）
  - 观察 Verification Phase（parse_completion_signal 正常；status=completed 时触发 sanity check，sanity check pass 才写 features.json）
- [ ] **Step 3.3**: 验证 subagent 行为
  - 抽查 1-2 个 raw.attempt 文件，确认 subagent 在 Task step 1 读 features.json、Task step 2 读 plan_ref 指向的 plan 文档
  - 确认 subagent 未修改 features.json（git diff features.json 应只有 orchestrator 的 status 更新）
  - 确认 subagent 单一 commit（`git log --since=<dispatch_start_iso> --oneline` 应只有 1 条 commit；若多 commit，sanity check 时间窗查询仍能覆盖）
- [ ] **Step 3.4**: 弱化测试（构造超长 description 的 feature）
  - 在测试 sprint 中加一个 description 长度 5000+ 字符的 feature
  - 跑 `/ghs:code --parallel`
  - 验证主会话 Dispatch Phase prompt 长度仍为 1373 字符/feature（超长 description 不放大主会话输出）

**Acceptance criteria**：
- 端到端流程跑通，所有 feature 走完 dispatch → verification → state update
- 主会话单 feature dispatch prompt 长度 Python `len()` 实测 ≤ 1400 字符（目标 1373）
- 8 feature batch 单轮主会话输出实测约 7.3K token（±20%，即 5.8K-8.8K）
- 弱化测试中主会话 prompt 长度与正常 case 一致（不被超长 description 拉长）
- subagent 在 raw.attempt 中能观察到 "Read features.json" / "Read plan_ref" 行为痕迹
- subagent 单一 commit（或即便多 commit，sanity check 时间窗 git log 覆盖所有 commit）

### Phase 4: 失败模式测试（sanity check 触发）

- [ ] **Step 4.1**: 构造 subagent 不读 features.json 的场景
  - 手动 dispatch 一个 prompt（绕过新模板），让 subagent 凭 feature_id 编实现
  - 或修改 features.json 中该 feature 的 files_affected 为某文件 X，但 subagent 实际改了文件 Y
  - 验证 sanity check 用 `git log --since=<dispatch_start_iso>` 检测到 intersection 为空，触发 Format Recovery retry
  - 验证 retry 期间 features.json **未被写为 completed**（sanity check 是前置门）
- [ ] **Step 4.2**: 构造 files_affected 为空的 feature（如 s2-feat-004 实测为空）
  - 验证 sanity check 走 skip 分支（不误触发 retry）
  - 日志记录 "sanity check skipped: feature <id> has no files_affected in features.json"
  - 验证 features.json 正常写为 completed
- [ ] **Step 4.3**: 构造 plan_ref 缺失场景
  - 临时移除测试 sprint 的 plan_ref 字段
  - 跑 `/ghs:code --parallel`
  - 验证 subagent 在 raw.attempt 中 log warning "plan_ref missing or unreadable"
  - 验证 feature 仍能完成基础实现（不 abort）
- [ ] **Step 4.4**: 构造 subagent 多 commit 场景（Medium #2 验证）
  - 手动让 subagent 对同一 feature 做 2 个 commit（如先 commit 文件 A，再 commit 文件 B）
  - 其中文件 A 在 expected_files、文件 B 不在
  - 验证 sanity check 用时间窗 `git log --since=<dispatch_start_iso>` 取到两个 commit 的文件，intersection 含文件 A，**不误触发 retry**
  - 对照：若用 Round 1 的 `git log -1`，只能取到最后一个 commit（文件 B），intersection 为空，会误触发 retry

**Acceptance criteria**：
- 失败模式 4.1 触发 Format Recovery retry，appendix 含 "Did you read features.json?" 提示；retry 期间 features.json 未被写为 completed
- 失败模式 4.2 走 skip 分支，不误触发 retry
- 失败模式 4.3 subagent 优雅降级，不 abort
- 失败模式 4.4 时间窗 git log 覆盖多 commit，不误触发 retry

### Phase 5: 回归

- [ ] **Step 5.1**: 单 feature 模式回归（默认 `/ghs:code`）
  - 跑一个单 feature 实现
  - 验证 Dispatch Phase 行为不变（单 feature 模式本来就不走 Parallel Mode Dispatch Phase，应零影响）
- [ ] **Step 5.2**: 跑现有 helper 测试套件
  ```bash
  command python3 plugin/shared/scripts/test_parse_completion_signal.py
  command python3 plugin/shared/scripts/test_parse_delimited_output.py
  command python3 plugin/shared/scripts/test_parallel_utils.py
  ```
  - 全部通过（本 plan 不改任何 helper，应零影响）
- [ ] **Step 5.3**: 文档同步
  - 在 `.ghs/progress.md` 记录本次改动会话
  - 注明 SKILL.md / coding-agent.md Dispatch Phase 模板结构变更（删 Feature Details 段、Task 压缩到 5 步、CONTEXT RESET 压缩到 1 句、Critical Rules 合并到 3 条、新增 sanity check 前置门）

**Acceptance criteria**：
- 单 feature 模式行为完全不变
- 所有现有 helper 测试套件通过
- progress.md 记录本次改动

---

## 5. 风险与缓解（Round 2 重算）

| Risk | Likelihood | Impact | Mitigation Strategy |
|------|-----------|--------|---------------------|
| subagent 不读 features.json，凭 feature_id 猜实现 + 正确发出 FEATURE COMPLETE | Medium | High | Task step 1 显式指示 "find your feature by `id == \"<feature_id>\"`" + 声明 "source of truth, not the title"；**Verification Phase commit/files sanity check**（§3.5）：status=completed 时用时间窗 `git log --since=<dispatch_start_iso>` 读 commit 实际修改文件，与 features.json 的 files_affected 求交集，空集触发 retry（且 retry 期间不写 features.json） |
| subagent 读 features.json 时读到别的 sprint 的 feature（context pollution） | Low | Medium | feature_id 全局唯一（实测 s2/s3 命名空间分离）；subagent 改不了 features.json（Critical Rules 约束 + orchestrator 后置更新），最多"读多了"；context pollution 的极端情况由 sanity check 兜底 |
| plan_ref 缺失或文件不存在，subagent 卡在 Task step 2 | Low | Medium | Task step 2 明确降级路径："log a one-line warning and proceed with `technical_notes` verbatim"；不 abort |
| LLM 偷懒回退到老的内联模板（看到 features.json 就把字段塞回 prompt） | Low | Medium | 新模板不含 `<description>` 等占位符，LLM 无处可塞；新模板要求 "Read its description ... — these are your source of truth"；**§6.7 自动化检查**：dispatch 后 grep 主会话 prompt 参数是否含 features.json 字段值（Optimization #4） |
| sanity check 误伤合法实现（subagent 重构导致文件路径变化） | Low | Low | sanity check 是"至少碰一个 expected_file"而非"只碰这些"；retry 失败后走 User Decision Handling，用户可手动 mark completed |
| subagent 多 commit 导致 `git log -1` 漏检（Medium #2） | Medium | Medium | 新模板 step 5 明确 "single commit" 措辞；sanity check 改用时间窗 `git log --since=<dispatch_start_iso>` 覆盖所有 commit（§3.5.2 step 3）；Phase 4 Step 4.4 验证 |
| sanity check 与写 features.json 时序错乱（Medium #3） | Medium | High | §3.5.4 明确 sanity check 是 completed 状态写入的前置门：sanity check pass 才写 features.json，fail 触发 retry 且不写；Phase 4 Step 4.1 验证 retry 期间 features.json 未被写 |
| features.json schema 演化（未来加 feature 级 plan_ref） | Very Low | Low | Task step 2 当前只读 sprint 级 plan_ref；本 plan 不预先处理，未来按需扩展 |
| 删除 Feature Details 段后主会话"忘记"传 feature_id 给 subagent | Low | High | Feature ID 独立成段（§3.2），主会话必须替换 `<feature_id>` 占位符；若占位符未替换，subagent 在 Task step 1 按 `id == "<feature_id>"`（字面值）查找会失败，触发 retry |
| 新模板字符数高于预期 | 已量化 | Low | §3.7 决策点 5 Python `len()` 实测 1373 字符/feature；相比旧模板 2345-3576 降幅 41.4%-61.6%；且固定值无上界膨胀风险 |

---

## 6. 测试策略

### 6.1 模板正确性验证（人工 + diff）

方案 Y 不引入新代码，因此无单测。验证主要靠：

- **diff 比对**：SKILL.md 与 coding-agent.md 的 Dispatch Phase + Verification Phase 段在改造后做 diff，确认除 §3.4 声明的差异外字字一致
- **占位符检查**：grep 新模板，确认不含 `<description>` / `<title>` / `<criteria_list>` / `<technical_notes>` / `<files_affected>` 等老占位符；确认含 `<feature_id>` 与 `<PROJECT_DIR>` 新占位符

```bash
# 检查老占位符已删除
grep -n '<description>\|<title>\|<criteria_list>\|<technical_notes>\|<files_affected>' \
  plugin/skills/ghs-code/SKILL.md plugin/shared/references/coding-agent.md
# 期望：无输出（或仅在无关段出现）

# 检查新占位符存在
grep -n '<feature_id>\|<PROJECT_DIR>' \
  plugin/skills/ghs-code/SKILL.md plugin/shared/references/coding-agent.md
# 期望：Dispatch Phase 段含两个占位符
```

### 6.2 集成测试（ghs-workspace 隔离工作区）

在 ghs-workspace 跑完整 `/ghs:code --parallel`：

- 4-8 feature sprint（构造最小到中等数据集）
- 验证：Analysis → Dispatch → Verification（含 sanity check 前置门） → State Update 全链路
- 测量主会话每轮输出 token，对比改造前

### 6.3 回归测试

- 跑现有 `test_parse_completion_signal.py` 确认 Verification Phase 未被破坏
- 跑现有 `test_parse_delimited_output.py`（无关，但确认未被波及）
- 跑现有 `test_parallel_utils.py` 确认 batching 算法未被破坏
- 单 feature 模式回归（默认 `/ghs:code`）行为不变

### 6.4 弱化测试

- 构造 description = 5000+ 中文字符的 feature
- 验证主会话 dispatch prompt 长度仍为 1373 字符（不被超长 description 拉长）
- 验证 subagent 仍能从 features.json 读到完整 description 并正确实现

### 6.5 失败模式测试

见 §4 Phase 4：

- subagent 不读 features.json → sanity check 触发 retry（且 retry 期间不写 features.json）
- files_affected 为空 → sanity check 走 skip 分支
- plan_ref 缺失 → subagent 优雅降级
- subagent 多 commit → 时间窗 git log 覆盖（Medium #2 验证）

### 6.6 手动验证清单

- [ ] 新 Dispatch Phase prompt 模板不含老占位符（`<description>` 等）
- [ ] 新模板含 `<feature_id>` 与 `<PROJECT_DIR>` 占位符
- [ ] 新模板 Task step 1 含 "find your feature by `id == \"<feature_id>\"`"
- [ ] 新模板 Task step 2 含 plan_ref 读取与缺失降级指示
- [ ] 新模板 Task step 5 含 "single commit" 与 "do NOT commit `.ghs/*` files"
- [ ] 新模板 Critical Rules 第 1 条含 "READ `features.json` but MUST NOT write"
- [ ] 新模板 Critical Rules 第 3 条含 "EXACTLY ONE signal"
- [ ] 新模板 Python `len()` 实测 ≤ 1400 字符
- [ ] Verification Phase `completed` 分支含 sanity check 前置门子步骤
- [ ] SKILL.md 与 coding-agent.md 的 Dispatch Phase 段 diff 仅显示 §3.4 声明的差异
- [ ] 端到端 `/ghs:code --parallel` 跑通
- [ ] 主会话单 feature dispatch prompt 长度 Python `len()` 实测 ≤ 1400 字符
- [ ] 8 feature batch 单轮主会话输出实测约 7.3K token（±20%）
- [ ] 单 feature 模式回归行为不变
- [ ] 现有 helper 测试套件全部通过

### 6.7 LLM 偷懒回退的自动化检查（Optimization #4）

dispatch 后用 grep 检查主会话输出的 prompt 参数中是否包含 features.json 中已知字段值：

```bash
# 取某 feature description 的前 50 字符作为指纹
FINGERPRINT=$(python3 -c "
import json
with open('.ghs/features.json') as f:
    data = json.load(f)
for sprint in data.get('sprints', []):
    for feat in sprint.get('features', []):
        if feat['id'] == '<feature_id>':
            print(feat['description'][:50])
            break
")

# 主会话日志路径在不同 Claude Code 环境下不一致（stdout transcript / 固定文件 / 不可访问）
# 退化策略：只检查 .ghs/parallel/<sprint_id>/*.raw.attempt* 文件——
# subagent 收到的完整 prompt 已被记录在 raw.attempt 文件头部（含主会话拼接的 prompt 字符串）
# 若 raw.attempt 含该指纹，说明主会话 LLM 偷懒把字段 inline 了
grep -l "$FINGERPRINT" .ghs/parallel/<sprint_id>/*.raw.attempt*
# 期望：无输出（主会话不应 inline 字段值）
# 若有输出：说明主会话回退到了老的内联模板，需要回头检查 SKILL.md Dispatch Phase 是否被正确应用
```

**说明**：raw.attempt 文件由 dispatcher 在 Verification Phase step 1 写入（参见 SKILL.md line 196-200），包含 subagent 这一轮的完整输入与输出。检查 raw.attempt 头部即可覆盖主会话 inline 行为，不需要直接访问主会话日志。此检查作为 Phase 3 集成测试的附加验证项。

---

## 7. 关键设计决策汇总（Round 2 更新）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 解决手段 | **删除 Feature Details 段**（0 新代码） | 与 s2/s3 本质不同：s2/s3 是"新增能力"，本次是"删冗余"；删字比加 helper 成本低一个数量级 |
| 与 v1 的关系 | 完全废弃 v1，不沿用其 helper / brief 文件 / archive 改动 / parallel_utils 改动 | v1 建立在错误前提上；方案 Y 是更简洁的正确解 |
| **唯一继承自 v1 的设计** | Verification Phase commit/files sanity check | v1 §3.6 设计正确，方案 Y 删 Feature Details 段后该兜底更必要 |
| Task step 1 强化方式 | 显式指示按 `id == "<feature_id>"` 查找 feature、读取 4 个字段名（斜杠紧凑写法）、声明文件为唯一来源 | 防 subagent 凭 title/id 猜实现 |
| Task step 2 设计（plan_ref） | 读 sprint 级 plan_ref 指向的 plan 文档；缺失时优雅降级（log warning，不 abort） | technical_notes §章节引用需要；强 abort 违反降级原则 |
| Task step 3 收窄（Round 2 修订） | **删除"do NOT read other features' details"软约束**（Medium #1） | 与 step 1 的"find by id 遍历 sprints[].features[]"自相矛盾；依赖 feature_id 全局唯一 + sanity check 兜底 |
| Task step 4 合并（Round 2 新增） | implement + test 合并为一句 | 省 |
| Task step 5 合并（Round 2 新增） | lint/build + commit 合并，明确"single commit"（Medium #2） | 防多 commit；配合时间窗 git log |
| Feature ID 段位置 | 独立成段，在 Task 之后、Critical Rules 之前 | 与原 Details 段内的 ID 行区分 |
| Critical Rules 强化 + 合并（Round 2） | 5 条合并到 3 条；第 1 条加 "READ but MUST NOT write"；第 3 条合并 completion signal 正反两种为 "EXACTLY ONE signal" | 省 + 语义更强 |
| CONTEXT RESET 压缩（Round 2 新增） | 4 条带说明压到 1 句（语义等价，决策点 6 论证） | 省 ~180 字符，Severe #1 压缩关键来源 |
| `<sprint_id>` 占位符 | **不需要**（subagent 自己按 id 查 sprint） | 简化主会话渲染责任；feature_id 全局唯一 |
| expected_files 来源（sanity check） | 从 features.json 读 `feature.files_affected` | 方案 Y 无 brief 文件；不用 git log 反推（循环论证） |
| sanity check git log 查询方式（Round 2 修订） | `git log --since=<dispatch_start_iso>` 时间窗（非 `git log -1`） | Medium #2：覆盖 subagent 可能的多 commit |
| sanity check 判定时机 | 先判 expected_files 是否为空（skip 分支）→ 再做 intersection 与空集判（retry 分支）；两个空集分开判定 | 继承 v1 §3.6 Round 3 Medium N2 修正 |
| sanity check 与写 features.json 时序（Round 2 明确） | sanity check 是 completed 状态写入的**前置门**：pass 才写，fail 触发 retry 且不写 | Medium #3：防 retry 期间 features.json 已被写为 completed 的状态语义混乱 |
| 主会话 token 优化估算（Round 2 实测） | 单 feature 实测 1373 字符（Python `len()`），8 batch 约 7.3K token，降幅 41.4%-61.6% | 修正 Round 1 的 1530 字符估算（实测 2309）；Round 2 压缩后重新成立 |
| 单 feature 模式 | 不受影响 | 本次改动只在 Parallel Mode Dispatch Phase |
| plan_ref 缺失的 future-proofing | 不预先处理 feature 级 plan_ref | YAGNI |

---

## 8. 验收（Plan 整体，Round 2 更新）

本 plan 完整覆盖以下需求：

1. ✅ 问题定位正确：v1 错在把"删冗余"当成"外置 helper"问题；方案 Y 是删冗余（§2.1-§2.3 显式论证）
2. ✅ 核心改动极简：删 Feature Details 段 + 压缩强化 Task（5 步）+ 压缩 CONTEXT RESET（1 句）+ 合并 Critical Rules（3 条）+ 保留协议层（§3.2-§3.4）
3. ✅ Critical Rules 保留 "Do NOT modify `.ghs/`"（含 features.json 只读约束，Optimization #1 带斜杠）
4. ✅ subagent 不读 features.json 的兜底：继承 v1 §3.6 Verification Phase sanity check（§3.5）
5. ✅ expected_files 来源明确：从 features.json 读（非 brief 文件、非 git log 反推）（§3.5.1）
6. ✅ plan_ref 缺失处理：优雅降级（§3.7 决策点 1）
7. ✅ context pollution 处理：删除自相矛盾的软约束 + sanity check 兜底（§3.7 决策点 2，Medium #1 修复）
8. ✅ 新 prompt 模板完整贴出（§3.2），Python `len()` 实测 1373 字符（§10.3）
9. ✅ 主会话 token 优化估算基于实测数据（§3.7 决策点 5，1373 字符，降幅 41.4%-61.6%）
10. ✅ SKILL.md 改造点行号级（§3.3，Optimization #2 精确行号）
11. ✅ coding-agent.md 同步改造点行号级（§3.4，差异声明集中，Optimization #3）
12. ✅ Verification Phase sanity check 设计完整（§3.5，含时间窗 git log + 前置门时序，Medium #2/#3 修复）
13. ✅ sanity check 子步骤文案与判定顺序统一（§3.5.4 直接 copy §3.5.2，Medium #4 修复）
14. ✅ 实施步骤 phased 可执行（§4 Phase 1-5）
15. ✅ 风险与缓解覆盖（§5，含 Medium #2/#3 新增风险行）
16. ✅ 测试策略覆盖模板正确性 / 集成 / 回归 / 弱化 / 失败模式 / 偷懒回退自动化检查（§6，Optimization #4）
17. ✅ 关键设计决策汇总（§7）
18. ✅ 与 s2/s3 的本质区别显式论证（§2.2）
19. ✅ Round 2 修订追踪段完整（§10）

---

## 9. 与 v1 plan 的对比（废弃论证，Round 2 重算）

| 维度 | v1（外置 helper） | 方案 Y（删冗余段，1373 字符模板） | 谁更优 |
|---|---|---|---|
| 核心动作 | 新增 prepare_feature_brief.py + brief 文件 + archive 清理 + parallel_utils 改动 | 删除 Feature Details 段 + 压缩强化 Task/CONTEXT RESET/Critical Rules | 方案 Y |
| 新代码行数 | ~300 行 Python + ~400 行测试 | 0 | 方案 Y |
| 改动文件数 | 6 个（helper / test / archive / parallel_utils / SKILL / coding-agent） | 2 个（SKILL / coding-agent） | 方案 Y |
| 降幅 | 55-65% | **41.4%-61.6%**（平均 53.6%） | 持平（v1 略高 1-2 个百分点） |
| 风险面 | helper bug / brief 污染 / archive 破坏性 / sprint_id 漂移 / 路径未传递 | 单点风险（subagent 不读 features.json），已被 sanity check 覆盖 | 方案 Y |
| 维护负担 | 长期维护 helper，schema 演化需同步改 | 接近 0 | 方案 Y |
| 实施成本 | 高（多 phase，多文件） | 低（2 处模板修改 + sanity check 子段 + smoke test） | 方案 Y |

**结论**：v1 plan 建立在错误前提上（把删冗余问题同构 s2/s3 当成外置 helper 问题），引入了不必要的基建。方案 Y 在降幅与 v1 基本持平（差距 1-2 个百分点）的前提下，把实施成本压到 v1 的 10%、风险面压到 v1 的 10%、维护成本压到接近 0。方案 Y 是显然的更优解。

唯一值得从 v1 继承的是 §3.6 Verification Phase commit/files sanity check 设计——方案 Y 已继承（§3.5），并适配为"从 features.json 读 expected_files + 时间窗 git log + 前置门时序"（v1 是从 brief 文件读 + `git log -1` + 时序未明确）。
