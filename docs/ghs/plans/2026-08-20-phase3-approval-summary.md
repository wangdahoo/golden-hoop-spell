# Phase 3 用户批注信息增强 — 技术方案（Round 3 修订版）

## 修订日志（Round 2 → Round 3）

| 来源 | 问题 | 本版处理 |
|---|---|---|
| 用户反馈（Phase 3 拒批） | "方案摘要不能一句话，要讲目标和具体实现的功能，只不过要概括得说" — Plan Summary 仅取 review 报告一句话太短 | Plan Summary 字段规格改为**概括性多句摘要（2-4 句、约 50-150 字）**，必须覆盖：①方案目标；②具体实现的功能/做什么。信息源升级为：以 review 报告 `## Plan Summary` 节的第一段非空文本为起点，由 dispatcher 结合 plan 文件「背景与目标」「方案设计」章节的核心思路综合扩写。模板与行数预算同步调整（摘要节允许 2-4 行，总块上限放宽到 ≤ 34 行） |
| Round 2 评审 Optimization 1 | 「取该节下一行」可能取到空行 | 提取措辞改为「取该节下的第一段非空文本」（已并入上述新提取规则） |
| Round 2 评审 Optimization 2 | FAIL 场景逐行列问题可能突破行数上限 | FAIL 场景单独设限：最多列 6 条 Severe/Medium 问题标题（一行一条），超出截断并提示查看 Files 节中的 review 路径 |

## 背景与目标

`ghs:plan` 技能在方案通过评审后进入 Phase 3（用户批注），当前只向用户提问一句 "The plan has completed N rounds of review... Do you approve this plan?"（SKILL.md 第 577-579 行），不包含任何方案核心信息。用户必须自行打开方案文件才能做出批准/拒绝决策。

**目标**：修改 Phase 3（及 Phase 2 FAIL@max_rounds 菜单）的 AskUserQuestion 提问内容，附上结构化 "Approval Summary" 摘要块，包含：
- **方案摘要**（2-4 句概括：目标 + 具体实现的功能，让用户看懂"这个方案要做什么"）
- ≤5 条关键技术决策
- 评审统计（Verdict / Severe / Medium / Optimization）
- 轮次预算状态
- plan / review 文件路径

**非目标**：
- 不改变 Phase 3 状态机逻辑（批准/拒绝/中断、round budget、MAX_BREACHES 均不变）
- 不新增脚本、解析器 token 或子代理
- 不修改 plan-designer.md / plan-reviewer.md / status JSON schema

## 现状分析

### 当前实现（SKILL.md）

- **Phase 3（第 575-593 行）**：仅一句引用块提问，之后分支到 approve / reject 路径。
- **Phase 2 FAIL@max_rounds（第 552-558 行）**：三选项/硬顶两选项菜单，选项 1 仅一句 "Show the user the review report so they understand what triggered the FAIL"，无结构化信息。
- **早停路径（第 545 行）**：round==1 且 PASS 直接进 Phase 3，走同一提问。
- 信息源已在磁盘：status JSON（round/max_rounds/max_rounds_breaches/文件路径）、review 文件（`## Plan Summary` 节、`## Issue Summary` 统计节）、plan 文件（`## 背景与目标`/`## Background and Goals`、`## Plan Design` 等章节）。

### 关键架构约束

- **Dispatcher 上下文保护**：SKILL.md 明确原则 "dispatcher NEVER calls codegraph directly... raw results pollute the dispatcher's context permanently"。方案全文可能数百行，不能整篇灌入主对话——扩写摘要所需的 plan 文件内容必须通过 grep 定位 + 分段小读获取。
- **AskUserQuestion question 字段长度有限**，摘要必须紧凑。原 ≤30 行预算因摘要扩为多句，放宽为 **≤34 行**（摘要节 +4 行的净增），其余节维持原预算不变。
- **解析器输出事实**：`parse_delimited_output.py` 的 JSON `verdict` 字段仅为 `"PASS" | "FAIL" | null`；计数只在 `completion_signal` 字段或 review 文件中，**计数以读 review 文件为准**。

## 方案设计

### 核心思路

在 Phase 3 提问前增加 **"Approval Summary 组装步骤"**：dispatcher 用 Read/Grep 读取磁盘上三个已有文件的**小片段**，组装成纯文本摘要块，作为 AskUserQuestion 的 question 主体。

### 摘要块模板（纯文本，无 Markdown 语法依赖）

```
Plan ready for approval (Round {round}/{max_rounds}, breaches {max_rounds_breaches}/{MAX_BREACHES})

=== Plan Summary ===
{概括性摘要：2-4 句、约 50-150 字，必须先讲方案目标，再讲具体实现的功能/做什么；
表述概括，不展开实现细节。来源见下方提取规则；提取失败写 N/A}

=== Key Technical Decisions ===
- {决策 1}
- {决策 2}
- ...（最多 5 条，取自 plan 的 Plan Design / Current State Analysis 章节）

=== Review Result ===
Verdict: PASS | Severe: {X} Medium: {Y} Optimization: {Z}
{若 Z > 0，一行列出 Optimization 项标题，逗号分隔；超长则截断并加 "..."}

=== Files ===
- Plan: <PROJECT_DIR>/.ghs/plans/{plan_file}
- Review: <PROJECT_DIR>/.ghs/plans/{review_file}

Do you approve this plan?
```

### 信息提取规则（dispatcher 执行，明确写入 SKILL.md）

| 摘要字段 | 来源 | 提取方式 |
|---|---|---|
| **Plan Summary（概括性多句摘要）** | review 文件 `## Plan Summary` 节（起点）+ plan 文件「背景与目标 / Background and Goals」与「方案设计 / Plan Design」章节（扩写素材） | ① Read review 文件（通常 < 100 行，可整读），取 `## Plan Summary` 节下的**第一段非空文本**作为起点；② 再按读取预算分段读 plan 文件的目标/核心思路章节；③ 综合 ①② **改写为 2-4 句、约 50-150 字的概括性摘要**：第一句讲方案目标（解决什么问题），后续 1-3 句讲具体实现的功能/做什么（如改哪些文件、引入什么机制/模块、覆盖哪些场景），不展开实现细节；④ 任一来源缺失时基于可用来源生成，全部缺失写 `N/A` |
| Key Technical Decisions | plan 文件 `## Plan Design`（及 `## Current State Analysis`）节 | 先 grep `^## ` 定位章节标题，再分段 Read 这些章节；从内容中挑出带决策性质的要点（技术选型、架构取舍、接口约定），改写为每条一行的短句，最多 5 条 |
| Review 统计（Verdict/Severe/Medium/Optimization） | **review 文件**（首选）：`## Issue Summary` 节或报告末尾的 `REVIEW COMPLETE \| Verdict: ... \| Severe: X Medium: Y Optimization: Z` 信号行；**备选**：解析器 JSON 的 `completion_signal` 字段（仅解析成功且内存中仍保留时可用） | Read review 文件提取；**不得依赖 dispatcher 内存或 `verdict` 字段推断计数**（`verdict` 只有 PASS/FAIL/null） |
| 轮次/预算状态 | status JSON | dispatcher 已持有，直接填模板 |

**读取预算约束**（写明，防止上下文膨胀）：
- review 文件通常 < 100 行，可整读（Plan Summary 起点与 Review 统计一次读出）。
- plan 文件允许读取：文件头部 + 通过 grep `^## ` 定位后的「背景与目标」「方案设计 / Plan Design」「现状分析」目标章节（分段读，每段建议 ≤ 60 行）；摘要与决策提取共用这批读取，**不重复读**；禁止无差别全文读入主对话。
- 任何字段提取失败写 `N/A`，不阻塞提问——摘要是 best-effort，不引入新失败路径。

**行数预算**（总块 ≤ 34 行）：摘要节 ≤ 4 行；决策 ≤ 5 条（5 行）；Review Result ≤ 2 行；Files 2 行；FAIL 场景追加的问题标题 ≤ 6 行（见场景 5）。

### 涉及的提问场景（完整清单，共 5 项）

1. **常规批准提问**（round < max_rounds，含 PASS 路径）— 完整摘要块 + Approve/Reject 选项。
2. **早停路径**（Phase 2 中 round==1 且 PASS，第 545 行直接进 Phase 3）— 与常规批准提问完全相同，走同一摘要块，无需特殊处理（列出以明确覆盖）。
3. **Reject 后的修订反馈提问** — 无需摘要（用户刚看过）。
4. **Phase 3 reject@max_rounds 菜单** — 三选项**及硬顶两选项**（`max_rounds_breaches >= MAX_BREACHES`）菜单均附摘要块；Files 节后额外一行：`Continuing would exceed max_rounds budget; {MAX_BREACHES - max_rounds_breaches} breach(es) remaining`（硬顶场景该行改为 `Hard cap reached: no further revision rounds available`）。
5. **Phase 2 FAIL@max_rounds 菜单** — 三选项及硬顶两选项菜单均附摘要块，但 "Review Result" 节改为：FAIL 统计行 + 逐行列出触发 FAIL 的 Severe/Medium 问题标题，**最多列 6 条**，超出时截断并加一行 `... {N} more issue(s) — see Review file below`（替代现有 "Show the user the review report" 措辞）；Files 节保留 review 路径供深入查看。此场景总块上限相应放宽到 ≤ 40 行。

## 实施步骤

唯一修改文件：`plugin/skills/ghs-plan/SKILL.md`。

### Step 1：重写 Phase 3 提问模板（第 577-579 行区域）
- 在 "After the plan passes review..." 之后新增 "Approval Summary 组装" 小节：信息源表（按上节版本，重点是 Plan Summary 的新多句提取规则）、提取规则、读取预算约束、行数预算、N/A 容错。
- 将单句提问替换为纯文本摘要块模板 + "Do you approve this plan?"，模板中不使用 `##`/`**` 等 Markdown 语法。

### Step 2：更新 Phase 3 reject@max_rounds 分支（第 584-590 行）
三选项与硬顶两选项菜单的描述中均加入 "attach the Approval Summary block"，并写明两种场景各自的预算提示行文案。

### Step 3：更新 Phase 2 FAIL@max_rounds 分支（第 552-558 行）
将 "Show the user the review report so they understand what triggered the FAIL" 改为 "attach the Approval Summary block (per Phase 3), with the Review Result section showing the FAIL stats and up to 6 titles of the Severe/Medium issues that triggered the FAIL (truncate with a pointer to the Review file if more)"。

### Step 4：一致性走查
- 确认 Key Constraints "one question at a time" 不受影响（摘要只是 question 内容变长，仍是单问题）。
- 确认 User Decision Handling（格式错误路径）提问不受影响。
- 确认文档内部交叉引用（Phase 2 指向 Phase 3 摘要块的说法、行数预算表述）一致。

### Step 5：手工验证（无自动化测试框架）
1. 对一个真实小需求运行 `/ghs:plan`，走完 Round 1 → PASS → 早停进 Phase 3，检查摘要块各字段填充；**重点核验 Plan Summary 为 2-4 句、覆盖目标与具体功能、约 50-150 字**，且纯文本标签在终端 UI 中可读（无溢出、`===` 标签不与 Markdown 渲染冲突）。
2. 临时调低 status JSON 的 `max_rounds` 构造 reject@max_rounds 场景，验证三选项菜单摘要块与预算提示行。
3. 构造 `max_rounds_breaches` 达到 2 的场景，验证硬顶两选项菜单的提示行文案。
4. 构造 review 文件缺 `## Plan Summary` 节的情况，验证摘要仅从 plan 文件章节生成的降级路径，及全缺失时 N/A 容错不阻塞流程。
5. 构造一个含 8 条 Severe/Medium 问题的 FAIL@max_rounds 场景，验证问题标题最多列 6 条并出现截断提示行。

## 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 摘要扩为多句后 LLM 写成展开式长段落，违背"概括"要求 | 用户阅读负担、UI 超限 | 提取规则硬性写明 2-4 句 / 约 50-150 字 / "先目标后功能、不展开实现细节"；行数预算摘要节 ≤ 4 行；Step 5.1 实测 |
| 摘要块整体变长导致 AskUserQuestion UI 显示不佳或被截断 | 用户体验下降 | 总块 ≤ 34 行硬限（FAIL 场景 ≤ 40 行）；决策最多 5 条、Optimization 标题一行、FAIL 问题标题最多 6 条，均超长截断 |
| dispatcher 为提取摘要/决策读取大文件污染主对话 | 违背上下文保护原则 | 读取预算约束：review 整读；plan 仅 grep 定位 + 分段读目标章节（每段 ≤ 60 行），摘要与决策共用读取 |
| Review 统计被 LLM 从内存编造（`verdict` 字段不含计数） | 用户基于错误数字决策 | 提取规则明确"以 review 文件为准"，禁止依赖 `verdict` 字段推断计数；缺失写 N/A |
| LLM 提取摘要/决策时选择主观、不稳定 | 摘要质量不一 | 给出明确内容标准（摘要：目标+功能；决策：选型/架构取舍/接口约定）；best-effort，不影响流程正确性 |
| 纯文本标签在部分终端渲染异常 | 可读性问题 | 使用 ASCII `=== ... ===` 分隔标签，兼容性最高；Step 5.1 实测，异常则退化为全大写短标签 |
| FAIL 菜单复用摘要块时 PASS/FAIL 语境混淆 | 用户误判 | FAIL 场景模板的 Review Result 节显式展示 FAIL 统计 + 最多 6 条 Severe/Medium 问题标题，超出指向 review 路径 |
| 只改 SKILL.md，行为依赖 LLM 遵循度 | 增强效果时好时坏 | 与现有技能实现方式一致；提供逐字可复制的模板与量化字数/行数约束，降低偏离概率 |
