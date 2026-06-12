# ghs:code 技能及相关 Python 脚本优化计划

## 修订日志
| 轮次 | 日期 | 变更 |
|-------|------|--------|
| 1 | 2026-06-12 | 初始计划 |
| 2 | 2026-06-12 | Round 2 修订：降级 P0-2 为已知限制（贪心算法非 bug）；修正 P0-3 行号引用与修复逻辑；降级 P0-4 为 P1 并新增误匹配修复；拆分步骤 1.2 为 1.2a/1.2b 并重排顺序；将 sprint-agent.md 纳入路径修复范围；P1-8 覆盖保护扩展至 progress.md |

## 1. 背景与目标

### 1.1 背景
`ghs:code` 技能是 golden-hoop-spell (GHS) 项目管理系统的核心实现技能。它负责从当前 sprint 实现功能，支持单功能模式和并行模式。该技能与多个 Python 脚本（`resolve_project_dir.py`、`archive_sprint.py`、`status.py`、`validate_structure.py`、`init_project.py`）和参考文档（`coding-agent.md`、`examples.md`、`sprint-agent.md`）协作，形成一条完整的开发工作流流水线。

随着功能的迭代，这些文件之间出现了不一致、脆弱的模式和工作流摩擦，这些问题需要系统性解决。

### 1.2 目标
1. 修复 `ghs:code` 工作流中的所有逻辑错误、不一致和缺失的验证
2. 对齐 `SKILL.md`、Python 脚本和参考文档，使其相互一致
3. 消除脆弱模式（硬编码值、未处理的边缘情况、仅存在于文档中的代码）
4. 减少工作流摩擦并提高开发者体验（DX）
5. 将 `validate_structure.py` 融入活跃工作流或正式废弃它

### 1.3 范围
**范围内：**
- `skills/ghs-code/SKILL.md`
- `shared/scripts/` 中的所有 Python 脚本
- `shared/references/coding-agent.md`、`examples.md`、`sprint-agent.md`
- 相关技能文件（`ghs-sprint/SKILL.md`、`ghs-archive/SKILL.md`、`ghs-status/SKILL.md`），仅限于交叉引用一致性
- `shared/assets/` 模板文件

**范围外：**
- `ghs-plan/SKILL.md` 及其子代理架构（独立系统）
- `ghs-init/SKILL.md`（仅因交叉引用一致性而涉及的轻触）
- `ghs-force-archive/SKILL.md`（已正确委托给 `archive_sprint.py`）

## 2. 现状分析

### 2.1 发现的具体问题

根据严重程度和文件组织如下。

---

#### P0：严重 Bug / 逻辑错误

**P0-1. `examples.md` 中 Sprint ID 格式与规范冲突**
- **文件：** `shared/references/examples.md`（第 17 行，180 行）
- **问题：** 示例使用 `"sprint-001"` 作为 sprint ID，但 `sprint-agent.md`（第 118 行）和 `ghs-sprint/SKILL.md`（第 78 行）都规定 sprint ID 格式为 `s{N}`（例如 `s1`，`s2`）。特性 ID 使用 `s1-feat-001`，引用 sprint 号码 `1`，但父 sprint 的 ID 是 `sprint-001`。这意味着任何依赖匹配 sprint 号码的自动化都会失败。
- **影响：** 遵循示例的用户/LLM 将创建不符合 schema 的 sprint ID，从而破坏 `validate_structure.py`（如果曾调用）以及任何假设 `s{N}` 格式的代码。
- **修复：** 将示例中的 `"sprint-001"` 更改为 `"s1"`，`"sprint-002"` 更改为 `"s2"`，等等。

**P0-2.（已降级为已知限制）`build_parallel_batches()` 贪心算法的批次数非最优**
- **文件：** `shared/references/coding-agent.md`（第 170-199 行）
- **问题：** 批处理算法按顺序迭代 `remaining`，并将每个功能添加到第一个不冲突的批次中。这是贪心装箱策略的固有属性——它不保证产生最少批次。原计划中的分析示例有误：功能 C 同时触及文件 1 和文件 2，因此 C 与 A 和 B 都存在冲突，将 C 放入单独的批次实际上是**正确的**行为。贪心策略在此场景下不存在错误。
- **影响：** 在具有大量并行功能的极端情况下，可能产生比理论最优解更多的批次，但实际 sprint 中很少出现足够多的并行功能使此问题可观测。
- **处理方式：** 不作为 P0 修复项。本计划的 P1-2 将创建 `parallel_utils.py`，该脚本的实现可以采用更好的排序策略（如按文件重叠度降序排列），自然地改善此问题。如果未来确实需要最优批次数，那是 NP-hard 装箱问题，需要引入更复杂的算法（如回溯搜索），当前不纳入范围。

**P0-3. `archive_sprint.py` 在仍有剩余 sprint 时重置 `progress.md`**
- **文件：** `shared/scripts/archive_sprint.py`（第 237-238 行）
- **问题：** 在 `archive_completed_sprints()` 中，第 237 行 `if sprints_to_archive:` 总是为真（因为此时 `archived_info` 非空且 `sprints_to_archive` 是原始输入列表，从未被修改）。随后第 238 行 `reset_progress_md(progress_path)` 无条件重置整个 `progress.md`，即使 `features_data["sprints"]` 中仍有其他未归档的 sprint。这会丢失所有未归档 sprint 的会话历史。
- **影响：** 归档任何一个 sprint 时都会丢失其他活跃 sprint 的所有会话记录，造成数据丢失。
- **修复：** 将第 237-238 行的条件从 `if sprints_to_archive:` 改为检查 `features_data["sprints"]` 是否为空（即 `if not features_data.get("sprints"):`）。只有当所有 sprint 都已归档、不再有活跃 sprint 时，才重置 `progress.md`。当仍有剩余 sprint 时，应仅删除已归档 sprint 的会话而保留其余内容。

---

#### P1：可靠性改进

**P1-1.（原 P0-4，已降级）`extract_sprint_sessions()` 存在脆弱的基于分隔符的解析且存在误匹配风险**
- **文件：** `shared/scripts/archive_sprint.py`（第 87-99 行）
- **问题：** 函数通过 `"## Session"` 拆分 `progress.md`（第 92 行），这意味着：
  - 并行编排条目使用 `"## Parallel Orchestration"`，不匹配 `"## Session"` 拆分，因此永远不会被提取
  - Sprint 规划条目使用 `"## Sprint Planning"`，同样不会被提取
  - 第 96 行 `sprint_id.lower() in session.lower()` 是子字符串包含检查，会匹配会话正文中任何位置提及 sprint ID 的条目（不仅是标题/元数据行），可能产生误匹配
- **影响：** 如果 P0-3 已修复（仅在无剩余 sprint 时重置），则本问题的影响为"归档数据不完整"而非"数据丢失"——未提取的会话保留在活跃 `progress.md` 中，只是未被复制到归档目录。这是一个 P1 级别的不完整归档问题。
- **修复：**
  - (a) 将拆分方式从 `"## Session"` 改为按 `"## "` (H2 标题) 拆分，以捕获所有会话类型
  - (b) 将匹配逻辑从 `sprint_id.lower() in session.lower()` 改为先提取标题行/元数据行，然后仅在标题/元数据中检查 sprint ID，避免正文误匹配
  - (c) 确保提取结果包含 `"## Parallel Orchestration"` 和 `"## Sprint Planning"` 类型的条目

**P1-2. `get_ready_features()` 和 `build_parallel_batches()` 是仅存在于文档中的伪代码**
- **文件：** `shared/references/coding-agent.md`（第 150-199 行）
- **问题：** 这些关键函数仅作为参考文档中的示例 Python 代码片段存在。没有可执行的版本。当 `ghs:code` 在并行模式下运行时，LLM 必须从头重新实现此逻辑，这导致了 LLM 如何解释"构建依赖图"和"创建批次"步骤的不一致。
- **影响：** 不同会话中的并行模式行为不可预测。依赖解析或冲突检测错误可能导致子代理冲突。
- **修复：** 将这些函数移动到一个共享的 Python 模块中（例如 `shared/scripts/parallel_utils.py`），LLM 可以执行它，或者更好的是，让 `ghs:code` 技能调用脚本进行批次规划。

**P1-3. `blocked_reason` 字段被引用但从未被验证或模板化**
- **文件：** `skills/ghs-code/SKILL.md`（第 81 行），`shared/references/coding-agent.md`（第 299 行）
- **问题：** `SKILL.md` 指示将阻塞原因记录在 `blocked_reason` 中，并且 `coding-agent.md` 引用了 `blocked_reason`，但该字段不在 `features.json` schema、`shared/assets/features.json` 模板或 `validate_structure.py` 中的验证逻辑中。
- **影响：** LLM 可能会以不一致的字段名称写入阻塞原因，或者完全省略它。
- **修复：** 将 `blocked_reason` 作为可选字段添加到功能 schema 定义和验证逻辑中。

**P1-4. `validate_structure.py` 是死代码——从未被任何技能调用**
- **文件：** `shared/scripts/validate_structure.py`
- **问题：** 在任何 `SKILL.md` 文件中都没有调用 `validate_structure.py` 的工作流步骤。`ghs:code` 技能直接读取 `features.json` 而不进行验证。`ghs:sprint` 创建功能但从不验证结果。如果 `features.json` 被手动或 LLM 损坏，损坏将静默传播。
- **影响：** 损坏的 `features.json` 仅在脚本因意外数据失败时才被检测到，而不是在损坏发生时立即检测到。
- **修复：** 将验证调用添加到 `ghs:code` 会话协议（会话开始时）和 `ghs:sprint` 步骤 6（写入 `features.json` 后）。

**P1-5. `coding-agent.md` 路径引用使用相对 `scripts/` 而非 `${CLAUDE_PLUGIN_ROOT}/shared/scripts/`**
- **文件：** `shared/references/coding-agent.md`（第 19、21、122 行）
- **问题：** 参考文档使用 `python3 scripts/resolve_project_dir.py`（相对路径），但实际的 `SKILL.md` 文件使用 `python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py`（插值路径）。如果 LLM 从参考文档而不是 `SKILL.md` 复制命令，它将因"文件未找到"而失败。
- **影响：** 如果代理遵循参考文档而非 `SKILL.md`，命令将失败。
- **修复：** 将 `coding-agent.md` 中的所有路径引用更新为使用 `${CLAUDE_PLUGIN_ROOT}/shared/scripts/` 格式。

**P1-6. `sprint-agent.md` 存在相同的相对路径问题**
- **文件：** `shared/references/sprint-agent.md`（第 22-24 行）
- **问题：** 与 P1-5 相同的问题。`sprint-agent.md` 在归档命令示例中使用 `python3 scripts/archive_sprint.py`（相对路径），如果 LLM 直接从此文档复制命令，同样会失败。
- **影响：** 代理遵循参考文档时命令失败。
- **修复：** 将 `sprint-agent.md` 中的所有路径引用更新为使用 `${CLAUDE_PLUGIN_ROOT}/shared/scripts/` 格式。纳入步骤 2.6 的路径修复范围。

**P1-7. `status.py` 会话解析存在与 `archive_sprint.py` 相同的脆弱模式**
- **文件：** `shared/scripts/status.py`（第 23-27 行）
- **问题：** `read_progress_md()` 也通过 `"## Session"` 拆分，这意味着它只捕获编码会话条目。Sprint 规划条目 (`"## Sprint Planning"`) 和并行编排条目 (`"## Parallel Orchestration"`) 被静默忽略，并且从不显示在状态输出中。
- **影响：** 状态显示不完整的会话历史。
- **修复：** 按任何 H2 标题（`## `）拆分，而不仅仅是 `"## Session"`，以捕获所有会话类型。

**P1-8. `archive_sprint.py` 未验证 `features.json` schema 的一致性**
- **文件：** `shared/scripts/archive_sprint.py`
- **问题：** `remove_archived_sprint()` 函数直接修改 `features_data` 字典而不验证结果是否仍然是有效的 JSON。如果 `features.json` 中有重复的 sprint ID（这将通过验证捕获，但未调用），它可能无法正确删除。
- **影响：** 归档后的状态可能不一致。
- **修复：** 在修改后，在写回之前添加对 `features_data` 的验证步骤。

**P1-9. `coding-agent.md` 引用了项目中不存在的 `AGENTS.md`**
- **文件：** `shared/references/coding-agent.md`（第 38、412、415、416、469 行）
- **问题：** 参考文献反复指示"参见项目的 `AGENTS.md`"以获取 lint/build 命令和代码样式，但 `AGENTS.md` 是特定于目标项目的约定，而非 GHS 工具本身。对于没有 `AGENTS.md` 的项目，这些指令是死胡同。
- **影响：** LLM 尝试读取不存在的文件，浪费 token 并可能跳过重要步骤。
- **修复：** 添加备用语言："参见项目的 `AGENTS.md`（如果存在）或 `CLAUDE.md` 以获取 lint/build 命令。"

**P1-10. `init_project.py` 在重新初始化时覆盖现有 `features.json` 和 `progress.md`**
- **文件：** `shared/scripts/init_project.py`（第 12-32 行，第 57-68 行）
- **问题：** 如果在 `.ghs/features.json` 已存在的情况下调用 `init_project.py`，`create_features_json()` 会以 `"w"` 模式打开文件（第 27 行）静默覆盖它，丢失所有 sprint 数据。同样，`create_progress_md()` 使用 `shutil.copy()`（第 65 行）也会静默覆盖现有的 `progress.md`。两个文件都没有存在性检查。
- **影响：** 意外数据丢失——两种跟踪文件都会被覆盖。
- **修复：** 添加预检查，如果 `features.json` 或 `progress.md` 已存在则中止，除非传递 `--force` 标志。对两个文件都实施保护。

---

#### P2：DX（开发者体验）改进

**P2-1. `ghs:code` 中缺少 `--max-parallel` 参数处理**
- **文件：** `skills/ghs-code/SKILL.md`（第 4 行）
- **问题：** `argument-hint` 提到 `[--parallel] [--max-parallel=N]`，但 `SKILL.md` 从未描述 LLM 应如何解析或使用 `--max-parallel=N`。没有提到读取此参数。
- **影响：** 用户可能传递 `--max-parallel=3`，但它将被静默忽略。
- **修复：** 添加一个部分来解析 `--max-parallel` 参数并将其传递给批次规划逻辑。

**P2-2. 并行模式状态更新部分编号错误**
- **文件：** `skills/ghs-code/SKILL.md`（第 192 行）
- **问题：** "状态更新阶段"下的编号从 1 跳到 3（1 然后是 3），跳过了 2。
- **影响：** 小的文档质量问题，但表明复制粘贴错误。
- **修复：** 将编号修正为 1、2。

**P2-3. `progress.md` 模板在 `archive_sprint.py` 中硬编码**
- **文件：** `shared/scripts/archive_sprint.py`（第 110-147 行）
- **问题：** `get_progress_template()` 函数返回一个硬编码的字符串，而不是读取 `shared/assets/progress.md` 中的模板。如果资产中的模板更新，硬编码版本将不同步。
- **影响：** 重置 `progress.md` 创建的文件与 `init_project.py` 创建的文件不同。
- **修复：** 从 `shared/assets/progress.md` 读取模板，与 `init_project.py` 的做法保持一致。

**P2-4. 功能选择优先级规则未考虑部分完成的功能**
- **文件：** `skills/ghs-code/SKILL.md`（第 39-44 行）
- **问题：** 功能选择指南仅提及选择 `pending` 功能。它没有提到如果一个 `in_progress` 功能被放弃（例如，之前的会话中断），该怎么办。`coding-agent.md`（第 282 行）中的"会话开始"检查到"之前会话中的未提交更改"，但没有处理 `features.json` 中已标记为 `in_progress` 但没有活动的未提交更改的功能（即，会话已完成但状态从未更新回来）。
- **影响：** 当先前会话在状态更新之前崩溃时，功能可能会永久卡在 `in_progress` 状态。
- **修复：** 添加一个恢复协议：如果一个功能是 `in_progress` 且工作树干净，则检查该功能的工作是否已提交。如果是，更新状态。如果不是，继续该功能。

**P2-5. `status.py` 未显示跨 sprint 的功能依赖状态**
- **文件：** `shared/scripts/status.py`
- **问题：** 状态显示功能数量和"下一个"功能，但不检查所选的"下一个"功能是否实际满足依赖。它只选择第一个待处理的功能。
- **影响：** 状态可能建议用户/LLM 开始一个依赖尚未完成的功能。
- **修复：** 添加依赖检查："下一个"功能应仅从所有依赖都已完成的功能中选择。

**P2-6. `coding-agent.md` 和 `SKILL.md` 之间的不一致**
- **文件：** `skills/ghs-code/SKILL.md` 对比 `shared/references/coding-agent.md`
- **问题：** 这两个文件包含重叠的内容，但存在差异：
  - `SKILL.md` 包含提交消息格式说明，但未包含 `Feature: <feature-id>` 页脚，而 `coding-agent.md` 包含（第 98-99 行）。
  - `SKILL.md` 在并行模式下说"验证干净的工作树"，而 `coding-agent.md` 是预飞检查中的第四步（在"检查未完成的 sprint"和"审查近期上下文"之后）。
  - `coding-agent.md` 有一个"实施计划"步骤（第 75-82 行），`SKILL.md` 中没有。
  - `SKILL.md` 子代理提示说"列出每个修改过的文件明确使用 `git add`"，但没有包含提交消息中的 `Feature: <feature-id>` 页脚，而 `coding-agent.md` 和并行模式提示都包含了。
- **影响：** 根据哪个文件是主要参考，LLM 会产生不同的行为。
- **修复：** 调整 `SKILL.md`，使其作为简洁的工作流权威来源，并让 `coding-agent.md` 作为详细参考，两者不冲突。

**P2-7. `status.py` 使用表情符号，在某些终端中渲染效果不佳**
- **文件：** `shared/scripts/status.py`（第 56、65-68、82-87、97-101 行）
- **问题：** 脚本输出使用 Unicode 表情符号。这些在某些终端、CI 环境或管道输出中无法正确渲染。注意：项目中所有 Python 脚本都使用表情符号（包括 `validate_structure.py` 第 120-128 行的 checkmark/cross 表情符号），因此任何 `--no-emoji` 修复应在所有脚本中一致应用，而不仅仅是 `status.py`。
- **影响：** 某些环境中的显示损坏。
- **修复：** 考虑添加一个 `--no-emoji` 标志或使用 ASCII 备用方案。如实施，应覆盖所有使用表情符号的 Python 脚本。这优先级较低。

### 2.2 架构约束

- **无外部依赖**：所有 Python 脚本都必须仅使用标准库
- **仅限 LLM 执行**：SKILL.md 文件是供 Claude 遵循的指令，而不是可执行代码
- **基于文件的通信**：代理通过 `features.json` 和 `progress.md` 进行状态通信
- **无自动化测试**：项目没有测试框架；验证是手动的

## 3. 计划设计

### 3.1 总体架构

方法是对每个文件进行重点、有针对性的修复，而不是进行结构性重构。当前的架构（SKILL.md 作为指令，Python 脚本作为工具，参考文档作为详细说明）是健全的。问题在于不同层之间的一致性和健壮性。

一种新的补充：一个新的 `shared/scripts/parallel_utils.py` 脚本，它将文档中的伪代码具体化为一个可执行工具，供 LLM 在并行模式下运行。

```
Before:
  SKILL.md (instructions) --> LLM reads features.json, implements logic from scratch
  coding-agent.md (reference) --> contains pseudocode for parallel logic

After:
  SKILL.md (instructions) --> LLM runs parallel_utils.py for batch planning
  parallel_utils.py (new) --> executable version of get_ready_features + build_parallel_batches
  coding-agent.md (reference) --> references parallel_utils.py instead of inline pseudocode
```

### 3.2 数据模型变更

向功能 schema 添加 `blocked_reason`：

```json
{
  "id": "s1-feat-001",
  "status": "blocked",
  "blocked_reason": "Dependency s1-feat-002 not yet completed"
}
```

这将更新到：
- `shared/assets/features.json`（作为带注释的 schema 示例，可选字段）
- `shared/references/sprint-agent.md` 功能定义
- `shared/references/coding-agent.md` 功能 schema 部分
- `shared/scripts/validate_structure.py`（添加可选字段验证）

### 3.3 接口设计

**新脚本：`shared/scripts/parallel_utils.py`**

```
Usage:
  python3 parallel_utils.py --project-dir <DIR> [--max-parallel N]

Output:
  JSON to stdout with:
  {
    "ready_features": [...],
    "batches": [[feat_id, ...], ...],
    "skipped": [{"id": ..., "reason": "dependency_not_met" | "file_conflict"}, ...]
  }
```

注意：`build_parallel_batches()` 的实现可采用按文件重叠度降序排列的策略作为启发式优化，以改善贪心装箱的批次数（对应原 P0-2 的已知限制）。这是在多项式时间内的实用改进，无需引入 NP-hard 的最优装箱算法。

**更新后的 `validate_structure.py`**：添加对 `blocked_reason` 字段和 sprint ID 格式验证（正则表达式 `^s\d{1,4}$`）的支持。

**更新后的 `archive_sprint.py`**：
- 修复 `extract_sprint_sessions()` 以处理所有会话类型（会话、冲刺规划、并行编排）
- 匹配逻辑改为检查标题/元数据行中的 sprint ID，而非全文子字符串搜索
- 修复 `reset_progress_md` 调用条件为仅在 `features_data["sprints"]` 为空时触发

### 3.4 关键流程

**更新后的 `ghs:code` 会话开始协议：**

1. 运行 `resolve_project_dir.py`（未更改）
2. 运行 `validate_structure.py --project-dir <DIR>`（新增——在开始前捕获损坏）
3. 审查近期工作：`git log` + `progress.md`（未更改）
4. 审查功能状态 + 恢复检查：如果一个功能是 `in_progress` 且工作树干净，则确定是否完成或应继续（改进）
5. 验证项目状态：lint/build（未更改）

**更新后的并行模式流程：**

1. 预飞检查（未更改）
2. 运行 `parallel_utils.py --project-dir <DIR> --max-parallel N`（新增——替换临时 LLM 逻辑）
3. 审查输出并显示给用户
4. 按照当前 `SKILL.md` 分派子代理（未更改）
5. 照常验证和更新（未更改）

**更新后的归档流程：**

1. 列出已完成的冲刺（未更改）
2. 归档：提取相关会话（所有类型），创建归档文件夹，从 `features.json` 中移除冲刺（改进）
3. 仅当 `features.json` 中没有剩余冲刺时才重置 `progress.md`（修复）

### 3.5 错误处理

- `parallel_utils.py`：处理空功能列表、循环依赖（检测并报告）、缺失的依赖引用
- `archive_sprint.py`：在删除会话后验证生成的 `progress.md` 是否仍然格式良好
- `validate_structure.py`：添加 sprint ID 格式验证以捕获 `examples.md` 样式的 ID

## 4. 实施步骤

### 阶段 1：修复关键 Bug（P0）

- [ ] **步骤 1.1**：修复 `shared/references/examples.md` 中的 Sprint ID 格式。将所有 `"sprint-001"` 更改为 `"s1"`，将 `"sprint-002"` 更改为 `"s2"`。更新所有引用 `sprint-001` 的文本，包括档案目录示例路径（`sprint-001_authentication_sprint_20240120_143000` 应变为 `s1_authentication_sprint_20240120_143000`）。
- [ ] **步骤 1.2a**：修复 `shared/scripts/archive_sprint.py` —— 重置逻辑。将第 237 行 `if sprints_to_archive:` 及第 238 行的 `reset_progress_md()` 调用替换为：检查 `features_data` 中移除已归档 sprint 后是否还有剩余 sprint（即 `if not features_data.get("sprints"):`）。只有当没有剩余 sprint 时才执行 `reset_progress_md(progress_path)`。当仍有剩余 sprint 时，应仅通过删除已归档 sprint 的会话来更新 `progress.md`（而不是重置整个文件）。
  - **验收标准**：使用包含多个 sprint 的 `features.json` 进行测试——归档其中一个 sprint 后，验证 `progress.md` 仍保留其他 sprint 的会话记录，且仅在归档最后一个 sprint 时才重置为模板。
- [ ] **步骤 1.2b**：修复 `shared/scripts/status.py` —— 会话解析。更新 `read_progress_md()`（第 26 行）以按 `## `（H2 标题）拆分而不是 `"## Session"`，以捕获所有会话类型（Sprint 规划、并行编排、编码会话）。
  - **验收标准**：使用包含混合会话类型（`## Session`、`## Sprint Planning`、`## Parallel Orchestration`）的 `progress.md` 进行测试，验证所有类型都在状态输出中显示。

### 阶段 2：可靠性改进（P1）

- [ ] **步骤 2.1**：创建 `shared/scripts/parallel_utils.py`。实现 `get_ready_features()` 和 `build_parallel_batches()` 作为可执行脚本，接受 `--project-dir` 和 `--max-parallel` 参数。输出 JSON。包含循环依赖检测。在 `build_parallel_batches()` 中采用按文件重叠度降序排列的启发式策略以改善批次数（缓解原 P0-2 的已知限制）。
- [ ] **步骤 2.2**：修复 `shared/scripts/archive_sprint.py` —— 会话提取逻辑。更新 `extract_sprint_sessions()`（第 87-99 行）：
  - (a) 将拆分方式从 `content.split("## Session")` 改为 `re.split(r'^## ', content, flags=re.MULTILINE)` 以捕获所有 H2 标题开头的条目
  - (b) 将匹配逻辑从 `sprint_id.lower() in session.lower()`（全文搜索，会误匹配正文）改为：先提取每个条目的前几行（标题行及元数据行），然后仅在这些行中检查 sprint ID，避免正文误匹配
  - (c) 确保返回的会话文本保留原始 `## ` 前缀
  - **验收标准**：使用包含在正文中提及另一 sprint ID 的会话条目的 `progress.md` 进行测试——验证只提取标题/元数据中匹配 sprint ID 的条目，不产生误匹配。
- [ ] **步骤 2.3**：更新 `shared/scripts/validate_structure.py`。添加：(a) sprint ID 格式验证（正则表达式 `^s\d{1,4}$`），(b) 功能 ID 格式验证（正则表达式 `^s\d{1,4}-feat-\d{3}$`），(c) 可选的 `blocked_reason` 字段支持，(d) sprint 上下文中的功能 ID 一致性检查（功能前缀与父 sprint 匹配）。
- [ ] **步骤 2.4**：使用 `/skill-creator` 更新 `skills/ghs-code/SKILL.md`。添加验证步骤（步骤 1.2 后运行 `validate_structure.py`）。为被中断的功能添加恢复协议。修复提交消息格式以包含 `Feature: <feature-id>` 页脚。修复并行模式中的编号。添加对 `--max-parallel` 参数处理的说明。在并行模式下引用 `parallel_utils.py`。
- [ ] **步骤 2.5**：使用 `/skill-creator` 更新 `skills/ghs-sprint/SKILL.md`。在步骤 6 中添加验证步骤：写入 `features.json` 后，运行 `validate_structure.py` 以确认结构有效性。
- [ ] **步骤 2.6**：更新 `shared/references/coding-agent.md`。将路径引用从 `scripts/resolve_project_dir.py` 修复为 `${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py`。添加 `AGENTS.md` 的备用语言（`CLAUDE.md`）。将内联伪代码块替换为对 `parallel_utils.py` 的引用。在功能 schema 部分添加 `blocked_reason`。
- [ ] **步骤 2.7**：更新 `shared/references/sprint-agent.md`。将路径引用从 `scripts/archive_sprint.py` 修复为 `${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_sprint.py`（第 22-24 行）。将 `blocked_reason` 作为可选字段添加到功能定义中。确保与更新后的 `validate_structure.py` 规则保持一致。
- [ ] **步骤 2.8**：更新 `shared/scripts/archive_sprint.py` 中的 `get_progress_template()`。读取 `shared/assets/progress.md` 而非返回硬编码字符串。
- [ ] **步骤 2.9**：更新 `shared/scripts/init_project.py`。在覆盖现有文件之前添加预检查。如果 `.ghs/features.json` 或 `.ghs/progress.md` 已存在，则打印错误并列出已存在的文件，然后退出（除非传递 `--force` 标志）。对两个跟踪文件都实施保护，而不仅仅是 `features.json`。
  - **验收标准**：在已有 `.ghs/` 目录的项目上运行 `init_project.py`，验证拒绝覆盖。使用 `--force` 标志再次运行，验证允许覆盖。
- [ ] **阶段 2 的验收标准**：运行 `parallel_utils.py` 并根据示例 `features.json` 验证其输出。运行 `validate_structure.py` 对有效和无效的数据文件。测试 `init_project.py` 的覆盖保护（对 `features.json` 和 `progress.md` 都测试）。

### 阶段 3：DX 改进（P2）

- [ ] **步骤 3.1**：使用 `/skill-creator` 更新 `skills/ghs-code/SKILL.md`。完善功能选择优先级，以考虑 `in_progress` 功能的恢复。在提交消息格式中添加 `Feature: <feature-id>` 页脚。
- [ ] **步骤 3.2**：更新 `shared/scripts/status.py`。将"下一个"功能选择更改为过滤依赖就绪的功能。考虑添加一个 `--no-emoji` 标志（如果实施，应同时应用于 `validate_structure.py` 等其他使用表情符号的脚本）。
- [ ] **步骤 3.3**：对齐 `shared/references/coding-agent.md` 和 `skills/ghs-code/SKILL.md`。确保 `SKILL.md` 是简洁的权威工作流，`coding-agent.md` 是详细的参考，两者不冲突。删除重复部分。
- [ ] **步骤 3.3 的验收标准**：对每个修改过的文件进行手动审查。验证 `SKILL.md`、`coding-agent.md` 和 `sprint-agent.md` 之间的交叉引用一致性。

## 5. 风险与缓解措施

| 风险 | 可能性 | 影响 | 缓解策略 |
|------|-----------|--------|---------------------|
| 创建 `parallel_utils.py` 引入了新的故障点 | 中 | 中 | 保持其具有确定性、无状态，仅从 `features.json` 读取并输出 JSON。它不修改任何内容，因此最坏情况是输出不佳，LLM 可以覆盖。 |
| 修复 `examples.md` 中的 sprint ID 格式会破坏现有用户数据 | 低 | 高 | 这是一个文档修复，而不是迁移。具有旧格式的现有 `features.json` 文件仍将有效，直到他们运行 `validate_structure.py`，这将标记它们。为受影响的用户添加迁移说明。 |
| 更改 `progress.md` 解析逻辑会破坏现有归档 | 低 | 中 | 新逻辑是旧逻辑的扩展。基于 `"## Session"` 的旧拆分是 `## ` 的子集，因此向后兼容。 |
| SKILL.md 更改使现有会话或上下文失效 | 中 | 低 | 这是预期结果。技能说明是向前兼容的。使用 `/skill-creator` 进行 SKILL 更改可确保格式和质量合规。 |
| `parallel_utils.py` 检测到未记录的循环依赖 | 中 | 低 | 脚本应该优雅地报告循环，而不是崩溃。LLM 收到报告并可以通知用户。 |
| 会话提取改为按 H2 标题拆分后误匹配减少，但可能遗漏不规范的标题格式 | 低 | 低 | H2 标题（`## `）是 `progress.md` 模板定义的会话分隔格式。如果模板被严格遵守（由 `ghs:code` 技能保证），此风险可忽略。 |

## 6. 测试策略

由于本项目没有自动化测试框架，因此所有验证都是手动的：

1. **单元验证**：创建一个带有测试 `features.json` 的临时项目目录，并使用各种边缘情况（空冲刺、循环依赖、缺失字段、无效状态）运行每个修改过的 Python 脚本。
2. **工作流验证**：执行完整的 GHS 流水线：`init` -> `sprint` -> `code`（单功能）-> `status` -> `code`（并行）-> `archive`。验证每个步骤的文件输出是否正确。
3. **边缘情况测试**：
   - 在 `features.json` 损坏的情况下运行 `ghs:code`（验证是否捕获）
   - 在具有不同会话类型的 `progress.md` 的情况下运行 `ghs:archive`（验证所有类型都被提取）
   - 在包含正文中提及其他 sprint ID 的会话的 `progress.md` 上测试 `extract_sprint_sessions()`（验证无误匹配）
   - 在具有多个 sprint 的项目上运行 `ghs:archive`，归档其中一个后验证其余 sprint 的会话保留
   - 在现有 `.ghs/` 目录下运行 `ghs:init`（验证 `features.json` 和 `progress.md` 都有覆盖保护）
   - 使用循环依赖运行 `parallel_utils.py`（验证检测）
4. **交叉引用审查**：读取每个修改过的文件并检查其引用的所有路径、字段名、状态值和 ID 格式是否与所有其他文件一致。

---

### 本轮修订与 Round 1 审查报告的逐项对应

| 审查问题 | 修订动作 |
|----------|----------|
| Severe #1：P0-2 贪心算法非 bug | 降级为"已知限制"，从 P0 修复列表中移除。P1-2 的 `parallel_utils.py` 可自然改善此问题。 |
| Medium #1：P0-3 行号引用不准确 | 修正行号为 237（`if sprints_to_archive:`）和 238（`reset_progress_md()`）。澄清第 237 行的条件检查是冗余的（在 `archived_info` 非空时总为真），修复方案改为检查 `features_data["sprints"]` 是否为空。 |
| Medium #2：P0-4 严重性夸大 | 降级为 P1-1。在 P0-3 修复后，影响从"数据丢失"变为"不完整归档数据"。新增误匹配修复（匹配逻辑从全文子字符串改为仅标题/元数据行）。 |
| Medium #3：步骤 1.2 和 1.3 纠缠 | 拆分为步骤 1.2a（修复重置逻辑，含验收标准）和 1.2b（修复 status.py 会话解析，含验收标准）。步骤 2.2 专门处理 archive_sprint.py 的会话提取修复（原步骤 1.2 的第二部分）。 |
| Opt #2：sprint-agent.md 路径问题 | 新增 P1-6，在步骤 2.7 中修复。 |
| Opt #3：P1-8 覆盖保护不完整 | 扩展 P1-10（原 P1-8）覆盖 `features.json` 和 `progress.md` 两个文件。步骤 2.9 对应实施。 |