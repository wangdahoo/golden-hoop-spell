# ghs:plan Phase 0.5 §A 聚焦方案：Context Subagent 隔离 codegraph 调用

## 修订日志

- **Round 1**（全新设计）：从 `2026-06-18-ghs-plan-token-opt.md` 抽取 §A（含内嵌的 §B 硬约束），作为独立技术方案。关键调整：codegraph 可用路径用 `general-purpose + haiku`（实测可继承 codegraph MCP），不可用路径用 `Explore + haiku`（原方案两条路径都用 general-purpose）。

- **Round 2**（按 Round 1 评审报告修订，覆盖 Severe #1 #2 / Medium #1 #2 #3 #4 / Optimization #1 #2 #3 #4）：
  - **Severe #1**：§3.5 Note 段中文括号注释翻成英文。
  - **Severe #2**：§5.2 验收清单放宽——允许否定性「重启」表述。
  - **Medium #1**：门 1 改为「**结构性约束为主 + 运行时自检降级**」。
  - **Medium #2**：snapshot 格式无 "Known Gaps" 段——在 Context Subagent prompt 内联定义。
  - **Medium #3**：dispatcher 按 `CODEGRAPH_AVAILABLE` 选**两份独立 prompt 模板**。
  - **Medium #4**：门 1 违规「告知用户」明确为**普通文字告知**。
  - **Optimization #1-4**：数字一致性 / retry appendix 加句 / 占位符转义 / python3 调用核查。

- **Round 3**（按 Round 2 评审报告修订）：
  - **Severe #1**：§3.5 代码块整段翻成 100% 英文。
  - **Severe #2**：§3.4 改为「展示与解释」，§3.5 保留完整两份模板作为「真源」。
  - **Medium #1**：门 1「确定性主防线」措辞降级为「降低违规概率但不消除」。
  - **Medium #2**：§5.2 加两份模板共享段一致性校验。
  - **Medium #3**：§3.4 inline 给可粘贴的 sed 命令。
  - **Optimization #1-2**：retry 措辞统一 / §3.5 代码块中文防御性检查。

- **Round 4**（按 Round 3 评审报告修订，覆盖 Severe #1 / Medium #1 / Optimization #1）：
  - **Severe #1**：§5.2 第 7 条的 awk 命令两条都改用 state-flag 版本。designer 实测通过。
  - **Medium #1**：§3.5 retry 分支末尾追加 `Note:` 段，与 §3.7 retry appendix 末尾段**逐字符一致**。
  - **Optimization #1**：§3.5 spawn JSON 块的 `prompt` 字段占位符语义明确化。

- **Round 5**（按用户反馈修订——**scope 失控修复**）：
  - **核心修订**：**彻底移除 §C**（Phase 0.5 Sanity Check 前置门）。用户在 Round 4 PASS 后审查方案时明确反馈：「都说了不要 §C 这个鸡肋功能，怎么又加进来了？」
  - **scope 失控回顾**：用户的原话是「把 A 单独拿出来做独立方案」，§C 是源方案里**另一个独立建议**（Phase 0.5 加 sanity check 前置门），与 §A 的 codegraph 隔离目标是正交的。Round 1 designer 自行决定引入 §C 精简版（理由「§A 没有 self-verification 就不可观测」），但用户从未要求 §C；Round 1-4 多轮 reviewer 也没质疑这个 scope 决定。本轮彻底移除，方案只保留 §A + §B（A+B 在源方案中已合并、不可拆分）。
  - **§3.5 代码块修订**：删除整个 `### Phase 0.5 Sanity Check` 段（含「primary defense」「auxiliary」「Honest scope note」「structural constraint LOWERS the probability」「Do NOT restart Phase 0.5」「snapshot file existence」等所有内容）。代码块结束于 Handling 段最后一条。Handling 段的 `ok` / `fallback_used` 分支不再「Run the Phase 0.5 Sanity Check」——改为直接「Proceed to Phase 1.」
  - **§3.6（原「是否引入 §C 精简版」）整段删除**，后续段重新编号（原 §3.7→§3.6、原 §3.8→§3.7）。
  - **§5.1 风险表修订**：「结构性主防线被越过」一行修订为「dispatcher 自由发挥调 codegraph 是结构性风险，但本方案不再声称有 §C 主防线兜底」。
  - **§5.2 验收清单修订**：删除 Sanity Check 段相关验收项；追加一条「SKILL.md Phase 0.5 段**不含 `### Phase 0.5 Sanity Check` 子段」+「Handling 的 ok/fallback_used 分支末尾是『Proceed to Phase 1.』」。
  - **§1.3 Scope 修订**：In scope 删除「§C 精简版」一项；Out of scope 追加「§C」。
  - **关键设计决策摘要修订**：删除第 5、6、7 条（§C 相关），其余决策重新编号。

---

## 1. 背景与目标

### 1.1 背景

诊断报告 `docs/analysis/2026-06-18-ghs-plan-phase-0.5-context-bloat.md` 显示会话 `ab9609c9` 在 Phase 0.5 让 dispatcher 主对话 token 从 ~50K 涨到 ~141K，单 phase 吃掉 ~90K 增量。根因是**结构性缺陷**：`SKILL.md:118-125` 的 Path A 让 dispatcher 在主对话直接调 codegraph，原始 `tool_result`（~150KB chars / ~50-70K tokens）沉淀进 prefix，**永不清出**——Anthropic API 不提供清除单条 message 的能力。诊断会话实际调了 `1 × codegraph_files + 7 × codegraph_explore + 4 × Bash`。

### 1.2 目标（可度量）

- 把 Phase 0.5 主对话 `tool_result` 字节从 ~150KB 降到 < 5KB。
- dispatcher 主对话 `codegraph_files + codegraph_explore` 调用次数从 **8** 降到 **0**（仅保留 1 次 `codegraph_status` 探测）。
- codegraph 调用全部在子代理上下文内发生，子代理返回即销毁，主对话零污染。

### 1.3 Scope

**In scope**：
- §A：把 codegraph 调用从 dispatcher 主对话隔离到 Context Subagent。
- §B：call budget（硬约束）内嵌在子代理 prompt 里（A+B 在源方案中已合并，不可拆分）。

**Out of scope**：
- **§C（Phase 0.5 Sanity Check 前置门）**：源方案里另一个独立建议，与 §A 的 codegraph 隔离目标正交。本聚焦方案不引入（详见修订日志 Round 5）。
- §D（ToolSearch 软建议）：与 §A 的 codegraph 隔离目标正交。
- 不优化 designer / reviewer 子代理内部 token。
- 不改 `parse_delimited_output.py` 解析器；**不改 snapshot 文件格式与定界符**。
- 不动 Phase 0 init。
- **不引入 audit log 方案**（破坏「主对话零额外写文件」洁癖，边际收益不足以抵消复杂度成本）。

### 1.4 关键事实依据

经实测（详见 `.ghs/plans/2026-06-18-ghs-plan-token-opt-probe.md`）：
- `general-purpose + haiku` 子代理可成功调用 project-scoped codegraph MCP。
- Explore subagent 在 codegraph 不可用时退化为 grep/glob/read 探索。
- Explore subagent 是否能继承 codegraph MCP **未在官方文档明确**——本方案在 prompt 层用绝对禁止条款兜底。

---

## 2. 现状分析

### 2.1 现有 Phase 0.5 双路径结构（`plugin/skills/ghs-plan/SKILL.md:109-162`）

**Detection**（L113-116）：检查 `.codegraph/` 目录 + `codegraph_status` 一次探测。

**Path A 现状（L118-125）—— dispatcher 在主对话直接调 codegraph**：
1. `codegraph_files(maxDepth=3, ...)`
2. `codegraph_explore(query="<keywords> architecture", ...)`
3. 压缩为 snapshot
4. 写 `<context_file>`

**核心问题**：原始 codegraph `tool_result` 沉淀进 dispatcher 主对话 prefix，**永不清出**。

**Path B 现状（L127-140）—— Explore subagent + haiku**：已经是子代理隔离形态。

**Handling（L142-162）**：raw 落盘 → `parse_delimited_output.py --kind context_snapshot --min-length 100` → 按 `status` 分支。

### 2.2 子代理能力对比

| 维度 | Explore Agent | general-purpose Agent |
|------|---------------|----------------------|
| Tools | All except Agent / ExitPlanMode / Edit / Write / NotebookEdit | `*`（全部） |
| 定位 | Fast read-only search agent | General-purpose agent |
| Write/Edit | 无（天然安全护栏） | 有（但本流程只输出文本） |
| codegraph MCP 继承 | 未在官方文档明确（用 prompt 禁止条款兜底） | 实测 PASS（haiku） |
| 适配本路径 | codegraph 不可用路径 | codegraph 可用路径 |

**为什么不对称**：codegraph 可用路径必须能调 codegraph MCP，实测只有 general-purpose 确认可继承；codegraph 不可用路径只需 grep/read，Explore 的 read-only 限制反而是安全护栏，且与现有 Path B 兼容。

### 2.3 约束

- python3 调用必须用 `command python3`（不是裸 `python3`）—— shell snapshot 会丢 `_` 前缀的 zsh 函数导致 pyenv 懒加载失效。
- 输出语言策略：中文用于人类可读内容；英文用于 LLM-facing prompts（含 SKILL.md 内的子代理 prompt 模板，以及 §3.5 代码块）。
- **一致性校验命令跨 awk 实现兼容性约束**（Round 4 Severe #1 学到）：本项目开发环境是 macOS，默认 awk 是 BSD awk（`awk version 20200816`）。BSD awk 的 range pattern `/start/,/end/` 是可重入的，不能用来「只抓第一段」或「只抓第二段」。所有「按出现次序抓特定段」的需求都必须用基于 count 状态标志的 awk 实现。

---

## 3. 方案设计

### 3.1 整体流程图

```
[Dispatcher main conversation]
   |
   +-- 1. ${PROJECT_DIR}/.codegraph/ 存在?
   |       YES -> codegraph_status ONCE (~1KB)
   |              index usable  -> CODEGRAPH_AVAILABLE=true
   |              index not OK  -> CODEGRAPH_AVAILABLE=false
   |       NO  -> CODEGRAPH_AVAILABLE=false
   |
   +-- 2. spawn Context Subagent (按 CODEGRAPH_AVAILABLE 选类型 AND 选 prompt 模板)
   |       CODEGRAPH_AVAILABLE=true:
   |         subagent_type = general-purpose, model = haiku
   |         prompt = PROMPT_TEMPLATE_CODEGRAPH
   |       CODEGRAPH_AVAILABLE=false:
   |         subagent_type = Explore, model = haiku
   |         prompt = PROMPT_TEMPLATE_GREP
   |       -> 输出 <<<CONTEXT_SNAPSHOT_*>>>
   |
   +-- 3. raw 落盘 -> parse_delimited_output.py --kind context_snapshot
   +-- 4. 按 status 分支 -> Phase 1
```

### 3.2 codegraph 可用路径：general-purpose + haiku + call budget

dispatcher 探测到 `CODEGRAPH_AVAILABLE=true` 后，spawn 一个 `general-purpose` 子代理（`model: haiku`），prompt 用 `PROMPT_TEMPLATE_CODEGRAPH`。子代理内部受 prompt 的 hard call budget 约束：
- 至多 1 次 `codegraph_files(maxDepth=3, projectPath="<PROJECT_DIR>")`。
- 至多 1 次 `codegraph_explore(query="...", projectPath="<PROJECT_DIR>")`，**所有关键词合并为单一 query**。
- 单次 explore 不足时，把缺口写进 snapshot 的 `## Known Gaps (optional)` 段，**不做 follow-up explore**。

### 3.3 codegraph 不可用路径：Explore + haiku

dispatcher 探测到 `CODEGRAPH_AVAILABLE=false` 后，spawn 一个 `Explore` 子代理（`model: haiku`），prompt 用 `PROMPT_TEMPLATE_GREP`。prompt 顶部有绝对禁止 codegraph 调用条款。

### 3.4 Context Subagent prompt 模板：展示与解释（完整模板见 §3.5）

> **Round 3 Severe #2 修订**：§3.4 不再含完整模板正文。完整模板作为唯一真源在 §3.5 内联。

dispatcher 在 spawn 前替换所有 `<PROJECT_DIR>` 与 `<requirement description>` 占位符。

#### 占位符替换的最小转义实操（Round 3 Medium #3）

```bash
# Strip snapshot-delimiter substrings from the user's requirement text to
# prevent delimiter injection, then substitute the sanitized text into the
# prompt template's <requirement description> placeholder.
SANITIZED_REQ=$(printf '%s' "$USER_REQ" \
  | sed 's/<<<CONTEXT_SNAPSHOT_START>>>//g; s/<<<CONTEXT_SNAPSHOT_END>>>//g')
```

然后用 `$SANITIZED_REQ` 替换 prompt 模板里的 `<requirement description>` 占位符。

#### 两份独立模板的理由（Round 2 Medium #3 备选方案沿用）

采用两份独立模板彻底消除死分支——true 模板只含 codegraph 指令、false 模板只含 grep 指令且顶部绝对禁止 codegraph。

#### 两份模板的关键措辞理由

**PROMPT_TEMPLATE_CODEGRAPH**：`hard call budget (do NOT exceed)` + `Combine ALL keyword facets` + `NOTE the gap ... do NOT make follow-up explore calls`。

**PROMPT_TEMPLATE_GREP**：顶部第一句 `**You MUST NOT call any \`codegraph_*\` tool in this run**`。

**两份模板共享段**：`### Snapshot format` 段、`## 5. Known Gaps (optional)` 段、`## Output Format` 段文字**逐字符一致**——这是 §5.2 一致性校验的对象。

### 3.5 完整目标 SKILL.md Phase 0.5 段（可直接粘贴替换 L109-162）

> **Round 3 修订要点**：本代码块**整段已 100% 英文**；内联**完整**两份 prompt 模板。
>
> **Round 4 修订要点**：retry 分支末尾追加 `Note:` 段，与 §3.6 retry appendix 末尾段**逐字符一致**；spawn JSON 块的 `prompt` 字段占位符语义明确化。
>
> **Round 5 修订要点**：删除整个 `### Phase 0.5 Sanity Check` 段；Handling 段 `ok` / `fallback_used` 分支末尾从「Run the Phase 0.5 Sanity Check」改为直接「Proceed to Phase 1.」。本代码块仍 100% 英文、可直接粘贴替换 SKILL.md L109-162。
>
> 替换现有 `SKILL.md:109-162`（保留 L109-111 的段标题与开篇说明文字不变）：

```
### Phase 0.5: Context Snapshot Extraction

Extract a condensed context snapshot of the project. This snapshot is shared by all subsequent subagents (designer and reviewer) across all rounds, eliminating redundant codebase exploration.

**Core principle**: The dispatcher NEVER calls `codegraph_files` or `codegraph_explore` directly in the main conversation — raw codegraph results are large and pollute the dispatcher's context permanently. All codegraph calls happen inside a Context Subagent whose context is discarded after it returns. The only codegraph call allowed in the main conversation is a single `codegraph_status` probe during Detection.

**Detection** (dispatcher, before spawning subagent):
1. Check if `${PROJECT_DIR}/.codegraph/` directory exists.
2. If yes, call `codegraph_status(projectPath="<PROJECT_DIR>")` ONCE to confirm the index is usable. This is the only codegraph call allowed in the main conversation (~1KB result).
3. Record `CODEGRAPH_AVAILABLE = <true | false>` and pass it into the Context Subagent prompt.

**Spawn a Context Subagent to extract the snapshot** — both the `subagent_type` AND the prompt template depend on `CODEGRAPH_AVAILABLE`:

- If `CODEGRAPH_AVAILABLE = true`: spawn `general-purpose` (model `haiku`) with `PROMPT_TEMPLATE_CODEGRAPH`. Verified to inherit project-scoped codegraph MCP.
- If `CODEGRAPH_AVAILABLE = false`: spawn `Explore` (model `haiku`) with `PROMPT_TEMPLATE_GREP`. read-only search agent — grep/glob/read fallback, no Write/Edit permission needed. The prompt explicitly forbids any `codegraph_*` call.

```json
{
  "subagent_type": "<general-purpose | Explore>",
  "model": "haiku",
  "description": "Extract project context snapshot",
  "prompt": "<dispatcher fills with the full text of PROMPT_TEMPLATE_CODEGRAPH or PROMPT_TEMPLATE_GREP from below>"
}
```

Before spawning, the dispatcher replaces all `<PROJECT_DIR>` and `<requirement description>` placeholders. When replacing `<requirement description>`, strip any substring matching the snapshot delimiters (`<<<CONTEXT_SNAPSHOT_START>>>` / `<<<CONTEXT_SNAPSHOT_END>>>`) from the user input to prevent delimiter injection. A minimal-sed recipe the dispatcher can run verbatim:

```bash
SANITIZED_REQ=$(printf '%s' "$USER_REQ" \
  | sed 's/<<<CONTEXT_SNAPSHOT_START>>>//g; s/<<<CONTEXT_SNAPSHOT_END>>>//g')
```

Then substitute `$SANITIZED_REQ` into the `<requirement description>` placeholder of the chosen prompt template.

**PROMPT_TEMPLATE_CODEGRAPH** (used when `CODEGRAPH_AVAILABLE = true`, `subagent_type = general-purpose`):

```
You are extracting a condensed project context snapshot. Your output feeds
downstream plan designers/reviewers — keep it tight.

## Requirement
<requirement description>

## Project Directory
<PROJECT_DIR>

## Task
codegraph MCP is available for this project. Use it as the primary exploration
tool. Produce a context snapshot following the format in
${CLAUDE_PLUGIN_ROOT}/shared/references/context-snapshot-guide.md.

### Hard call budget (do NOT exceed):
- At most ONE `codegraph_files(maxDepth=3, projectPath="<PROJECT_DIR>")` call.
- At most ONE `codegraph_explore(query="...", projectPath="<PROJECT_DIR>")` call.
  Combine ALL keyword facets from the requirement into a single query
  (e.g. "<keyword1> <keyword2> <keyword3> architecture" — example is generic;
  the actual query terms are derived from the requirement being planned).
  Do NOT split into per-facet explore calls.
- If the single explore result is insufficient for a specific detail, NOTE the
  gap in the snapshot's "Known Gaps" section (see format below) — do NOT make
  follow-up explore calls. The plan designer will fill gaps later.

### Snapshot format
Follow the four sections defined in context-snapshot-guide.md:
1. Technology Stack
2. Directory Structure
3. Architecture Summary
4. Relevant Code Excerpts

You MAY append one optional section at the end if needed:

## 5. Known Gaps (optional)
List any specific details you could not fully capture within the call budget.
One bullet per gap, each naming the file/symbol/area and what is missing.
Example:
- `src/auth/session.ts` — could not verify the session refresh token rotation
  logic (omitted from the single explore query to stay within budget).

Target 50-70% compression vs raw source. Include function signatures, schemas,
routing — NOT full file contents.

## Output Format
Output the FULL snapshot content in your response, delimited by:
<<<CONTEXT_SNAPSHOT_START>>>
...snapshot content here...
<<<CONTEXT_SNAPSHOT_END>>>

Do NOT attempt to write any files. Just output the content between the delimiters.
```

**PROMPT_TEMPLATE_GREP** (used when `CODEGRAPH_AVAILABLE = false`, `subagent_type = Explore`):

```
You are extracting a condensed project context snapshot. Your output feeds
downstream plan designers/reviewers — keep it tight.

## Requirement
<requirement description>

## Project Directory
<PROJECT_DIR>

## Task
**You MUST NOT call any `codegraph_*` tool in this run — codegraph is not
available. Use grep/glob/read only.**

Produce a context snapshot following the format in
${CLAUDE_PLUGIN_ROOT}/shared/references/context-snapshot-guide.md.

### Exploration steps:
1. Read the dependency manifest (package.json / requirements.txt / Cargo.toml / ...)
2. Get directory structure (exclude node_modules, .git, build dirs)
3. Read main entry point
4. Read config files and DB schemas
5. Read files in directories related to the requirement topic
6. Condense into snapshot format

### Snapshot format
Follow the four sections defined in context-snapshot-guide.md:
1. Technology Stack
2. Directory Structure
3. Architecture Summary
4. Relevant Code Excerpts

You MAY append one optional section at the end if needed:

## 5. Known Gaps (optional)
List any specific details you could not fully capture within the call budget.
One bullet per gap, each naming the file/symbol/area and what is missing.
Example:
- `src/auth/session.ts` — could not verify the session refresh token rotation
  logic (omitted from the single explore query to stay within budget).

Target 50-70% compression vs raw source. Include function signatures, schemas,
routing — NOT full file contents.

## Output Format
Output the FULL snapshot content in your response, delimited by:
<<<CONTEXT_SNAPSHOT_START>>>
...snapshot content here...
<<<CONTEXT_SNAPSHOT_END>>>

Do NOT attempt to write any files. Just output the content between the delimiters.
```

> **Note**: Context Subagents **should not** write files — output the snapshot in your response and let the dispatcher write it. (general-purpose subagents have Write permission by default, but this flow requires text-only output; Explore subagents have no Write permission by design.)

**Handling**: First save the subagent's raw response to disk (file naming per the Format Recovery section): the first attempt goes to `<PROJECT_DIR>/.ghs/plans/<context_file>.raw`, retries go to `<context_file>.raw_retry<T>`. Then invoke the parser helper.

> **You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT parse the subagent output yourself — the helper is the single source of truth for delimiter extraction.**

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
  --kind context_snapshot \
  --input-file <PROJECT_DIR>/.ghs/plans/<context_file>.raw[_retry<T>] \
  --min-length 100
```

Read the JSON object printed to stdout and branch on `status`:

- **`ok`**: Write `content` to `<PROJECT_DIR>/.ghs/plans/<context_file>`. Add `context_file` to the status JSON. Proceed to Phase 1.
- **`fallback_used`**: Write `content` to `<context_file>` with a leading warning comment (`<!-- WARNING: extracted via fallback strategy: <strategy>; warnings: <warnings joined by "; "> -->`). Add `context_file` to the status JSON. Notify the user (as plain text in your response — this is informational, not a decision point, so do NOT use AskUserQuestion) that fallback extraction was used. Proceed to Phase 1.
- **`empty` or `malformed`** with `retry_count < MAX_RETRY (=1)`: Increment `retry_count`, re-dispatch the Context Subagent with the Format Recovery appendix appended.

  Note: keep the SAME `subagent_type` and the SAME prompt template
  (`PROMPT_TEMPLATE_CODEGRAPH` or `PROMPT_TEMPLATE_GREP`) as the first attempt —
  do NOT switch the subagent type or prompt template during retry. Keep
  `general-purpose`+`PROMPT_TEMPLATE_CODEGRAPH` or `Explore`+`PROMPT_TEMPLATE_GREP`
  consistent with the first attempt.

  Then return to the raw-save step (writing to `<context_file>.raw_retry<T>`).
- **`empty` or `malformed`** with `retry_count >= MAX_RETRY`: Use AskUserQuestion per the User Decision Handling section.
```

### 3.6 Format Recovery 段更新（`SKILL.md:512`）

将 `SKILL.md:512` 的标题从「For Explore subagent retries (`--kind context_snapshot`, Phase 0.5 Path B):」改为「For Context Subagent retries (`--kind context_snapshot`, Phase 0.5):」。

retry appendix 全文（标题改 + 末尾加一段 `Note:`，与 §3.5 retry 分支**逐字符统一**——两处都是独立的 `Note:` 段）：

```
## IMPORTANT: Previous Output Format Issue
Your previous response could not be parsed correctly. The delimiters
<<<CONTEXT_SNAPSHOT_START>>> ... <<<CONTEXT_SNAPSHOT_END>>> were missing or malformed.

This time you MUST:
1. Output the delimiters EXACTLY as written: <<<CONTEXT_SNAPSHOT_START>>> on its own line, <<<CONTEXT_SNAPSHOT_END>>> on its own line.
2. Put ALL snapshot content between them.
3. Do NOT wrap the delimiters in a code fence.
4. Do NOT translate or modify the delimiter strings.

Note: keep the SAME `subagent_type` and the SAME prompt template
(`PROMPT_TEMPLATE_CODEGRAPH` or `PROMPT_TEMPLATE_GREP`) as the first attempt —
do NOT switch the subagent type or prompt template during retry. Keep
`general-purpose`+`PROMPT_TEMPLATE_CODEGRAPH` or `Explore`+`PROMPT_TEMPLATE_GREP`
consistent with the first attempt.
```

> **Round 4 Medium #1 修订**：§3.5 retry 分支末尾的 `Note:` 段与 §3.6 retry appendix 末尾的 `Note:` 段现**逐字符一致**。

### 3.7 错误处理

| 场景 | 处理 |
|------|------|
| `codegraph_status` 探测失败 | `CODEGRAPH_AVAILABLE=false`，走 Explore + PROMPT_TEMPLATE_GREP 路径 |
| Context Subagent 调 codegraph 失败（仅 true 路径） | 子代理在 `## Known Gaps (optional)` 段记录 |
| 子代理输出定界符缺失/malformed | Format Recovery 重试一次（**同 `subagent_type` + 同 prompt 模板**） |
| snapshot 文件 < 100 字节 | 触发 Format Recovery / User Decision Handling |

---

## 4. 实施步骤（一张表）

| 步骤 | 文件 / 位置 | 操作 |
|------|------------|------|
| **1** | `plugin/skills/ghs-plan/SKILL.md` L109-162 | 用 §3.5 的完整段替换 |
| **2** | `plugin/skills/ghs-plan/SKILL.md` L512 | Format Recovery 段 retry appendix 标题改 + 模板末尾追加 `Note:` 段（与 §3.5 retry 分支末尾 `Note:` 段**逐字符一致**——Round 4 Medium #1） |
| **3** | — | 验证 `parse_delimited_output.py --kind context_snapshot` 行为不变 |
| **4** | — | 静态检查（见 §5.2） |
| **5** | 带 `.codegraph/` 的项目 | 动态验证：主对话 0 次 codegraph_files/explore |
| **6** | 不带 `.codegraph/` 的项目 | 回归验证：Explore + PROMPT_TEMPLATE_GREP 路径 |

---

## 5. 风险与验收

### 5.1 风险表

| 风险 | 可能性 | 影响 | 缓解策略 |
|------|--------|------|----------|
| Context Subagent 延迟变长 | 中 | 低 | 可接受；大项目可换 sonnet 子代理 |
| dispatcher 自由发挥调 codegraph（结构性风险，无 §C 主防线兜底） | 低 | 中 | SKILL.md 指令层不引导违规（§5.2 静态检查可验证文本契约）；但静态检查不证明运行时行为——LLM 仍可能越过指令；prefix 已不可逆污染。本方案不引入运行时自检（详见修订日志 Round 5 scope 决定） |
| B 硬约束被模型忽视 | 低 | 中 | 措辞用「hard call budget (do NOT exceed)」+ 给合规出口（Known Gaps 段） |
| Explore 子代理误调 codegraph | 低 | 低 | PROMPT_TEMPLATE_GREP 顶部绝对禁止条款 |
| 两份 prompt 模板漂移 | 低 | 低 | §5.2 加一致性校验（Round 4 Severe #1：命令已修为 BSD awk 兼容的双 state-flag awk 版本） |
| §3.5 代码块残留中文 | 低 | 高 | §5.2 加防御性 grep 检查；§3.5 代码块现已是 100% 英文 |
| 一致性校验命令本身在 BSD awk 下不工作 | 低 | 高 | §5.2 第 7 条 awk 命令全部改用 state-flag 版本；designer 已实测通过 |

### 5.2 验收清单

**静态检查**：

- [ ] grep `codegraph_(files|explore)\(` 在 SKILL.md，应**仅出现在 PROMPT_TEMPLATE_CODEGRAPH 模板内**。
- [ ] SKILL.md Phase 0.5 段含 `**Core principle**: The dispatcher NEVER calls` 字样。
- [ ] SKILL.md Phase 0.5 段含两个 `subagent_type` + prompt 模板分支说明。
- [ ] SKILL.md Phase 0.5 段含两份**完整**独立 prompt 模板，**模板正文存在**（不是占位符引用）。
- [ ] SKILL.md Phase 0.5 段的 spawn JSON 块的 `prompt` 字段占位符语义为 `<dispatcher fills with the full text of PROMPT_TEMPLATE_CODEGRAPH or PROMPT_TEMPLATE_GREP from below>`——Round 4 Optimization #1。
- [ ] `PROMPT_TEMPLATE_GREP` 模板顶部含绝对禁止条款。
- [ ] 两份 prompt 模板都含 `## 5. Known Gaps (optional)` 段格式内联定义。
- [ ] **两份模板的共享段文字逐字符一致**——可执行校验命令（BSD awk `version 20200816` 实测通过）：
      ```bash
      awk '
      /^### Snapshot format/ { count++; if (count == 1) in_range = 1 }
      /^## Output Format/ && in_range { print; in_range = 0; next }
      in_range { print }
      ' SKILL.md > /tmp/region_codegraph.txt
      awk '
      /^### Snapshot format/ { count++; if (count == 2) in_range = 1 }
      /^## Output Format/ && in_range { print; in_range = 0; next }
      in_range { print }
      ' SKILL.md > /tmp/region_grep.txt
      diff /tmp/region_codegraph.txt /tmp/region_grep.txt && echo "TEMPLATES_CONSISTENT" || echo "TEMPLATES_DRIFT_DETECTED"
      ```

- [ ] SKILL.md Phase 0.5 Note 段措辞为「should not write files」+ 全英文括号注释。
- [ ] SKILL.md Phase 0.5 段含占位符替换的最小转义说明 + 可执行 sed 命令。
- [ ] SKILL.md Phase 0.5 段不含 `[xxx](#xxx)` 锚点链接。
- [ ] SKILL.md Phase 0.5 段**不含 `### Phase 0.5 Sanity Check` 子段**——Round 5 移除 §C。
- [ ] SKILL.md Phase 0.5 段 Handling 的 `ok` / `fallback_used` 分支末尾是「Proceed to Phase 1.」（不是「Run the Phase 0.5 Sanity Check」）——Round 5 移除 §C。
- [ ] SKILL.md L512 retry appendix 标题为「For Context Subagent retries」。
- [ ] SKILL.md L512 retry appendix 末尾含独立 `Note:` 段，**与 §3.5 retry 分支末尾的 `Note:` 段逐字符一致**——Round 4 Medium #1。
- [ ] SKILL.md 内 `command python3`（非裸 `python3`）。
- [ ] `references/` 与 `shared/scripts/` 下凡涉及 python3 的调用同样用 `command python3`。
- [ ] **§3.5 代码块整体不含中文字符**。

**动态验证（带 `.codegraph/` 项目重跑一次 `/ghs:plan`）**：

- [ ] dispatcher 主对话 `codegraph_files` / `codegraph_explore` 调用次数 = 0。
- [ ] Context Subagent 是 `general-purpose`，prompt 是 `PROMPT_TEMPLATE_CODEGRAPH`。
- [ ] Context Subagent 内部 `codegraph_files` ≤ 1 次、`codegraph_explore` ≤ 1 次。
- [ ] `wc -c <context_file>` 输出典型 3-8KB。
- [ ] 会话未触发「Context compressed」自动压缩提示。
- [ ] `<context_file>.raw` 存在，parser 返回 `status: ok`。

**回归（不带 `.codegraph/` 项目）**：

- [ ] Context Subagent 是 `Explore`，prompt 是 `PROMPT_TEMPLATE_GREP`。
- [ ] Explore 子代理用 grep/glob/read 产出非空 snapshot。
- [ ] Explore 子代理**未调任何 `codegraph_*` 工具**。
- [ ] 人为破坏定界符触发解析失败，Format Recovery 路径不变。

### 5.3 测试策略说明

本方案无新增 helper（复用 `parse_delimited_output.py`），无单元测试新增。验证以**静态检查 + 动态验证**为主。

---

## 关键设计决策摘要

1. **两条路径子代理类型 + prompt 模板双重不对称但对外结构对称**。
2. **两份独立 prompt 模板而非共用模板**（Round 2 Medium #3）：彻底消除死分支。
3. **§3.4 改为「展示与解释」段、§3.5 保留完整模板作为真源**（Round 3 Severe #2）：消除漂移风险。
4. **A+B 合并**：B 的 hard call budget 内嵌在 PROMPT_TEMPLATE_CODEGRAPH 里。
5. **Known Gaps 段在 prompt 内联定义**：保持不改 `context-snapshot-guide.md`。
6. **占位符替换的最小转义实操命令 inline**（Round 3 Medium #3）：sed 命令删除定界符子串。
7. **不引入 §C**（Round 5 scope 修复）：§C 是源方案里另一个独立建议（Phase 0.5 加 sanity check 前置门），与 §A 的 codegraph 隔离目标正交。本聚焦方案只保留 §A + §B（A+B 不可拆分）。
8. **不引入 §D**：ToolSearch 软建议与 §A 目标正交。
9. **不新增 helper**：复用 `parse_delimited_output.py`。
10. **Format Recovery 标题改为「Context Subagent retries」+ 加 `Note:` 段，与 §3.5 retry 分支逐字符统一**（Round 4 Medium #1）。
11. **§3.5 代码块 100% 英文 + §5.2 加防御性中文检查**（Round 3 Severe #1 + Optimization #2）。
12. **§5.2 一致性校验命令用双 state-flag awk**（Round 4 Severe #1）：BSD awk 的 range pattern 可重入，必须用 state-flag 模式按 count 选择段。
13. **spawn JSON 块 prompt 字段占位符语义明确化**（Round 4 Optimization #1）。
14. **§5.1 风险表如实反映「无 §C 兜底」**（Round 5）：dispatcher 自由发挥调 codegraph 是结构性风险，但本方案不引入运行时自检（scope 限定）。