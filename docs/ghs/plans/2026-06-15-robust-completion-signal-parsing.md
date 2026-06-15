# 健壮化 ghs:code 验证信号解析与 pyenv shim 修复方案

> **手写文档**：本 plan 未走 `/ghs:plan` 的 dispatcher-review 流程（因为 /ghs:plan 自身在 Opus 4.7 下也会 hang，正是本系列诊断的对象）。文档按 `/ghs:plan` 输出格式编写，可作为后续 sprint 的输入。诊断依据见 `/diagnose` 会话记录（2026-06-15）。

## 1. Background and Goals

### 1.1 Background

`/diagnose` 诊断 ghs 套件工作流 hang 时定位到两类问题：

**A. ghs:code Parallel Mode Verification Phase 同构 hang（主因）**

`plugin/skills/ghs-code/SKILL.md:195` 与 `plugin/shared/references/coding-agent.md:259` 的 Verification Phase 完全依赖 dispatcher（LLM 自己）grep 子代理输出找：

```
Check for "FEATURE COMPLETE: <id>" or "FEATURE BLOCKED: <id>" in output
```

这与 `ghs:plan` 的 `<<<X_START>>>...<<<X_END>>>` delimiter 解析**结构同构**——都是 LLM 自己解析子代理输出，没有确定性外置。诊断证据：

- 用户实测：Opus 4.6 不 hang；Opus 4.7（effort high/xhigh）hang。表现：彻底无输出，看起来在等。
- 用户的初步判断："流程推进依赖提示词，表现不稳定"——精准命中根因。
- 已验证（诊断 Phase 1 反馈回路）：相同偏离格式喂给确定性 Python helper 全部能解析（22 个测试样本），silent hang 完全发生在 dispatcher LLM 自解析路径。

可能的子代理偏离模式：`Feature Complete:`（大小写）、`FEATURE COMPLETED:`（多 D）、`Feature 完成: <id>`（中文）、`The feature is complete`（自然语言）、把信号包在 markdown bold 里、子代理只 commit 没显式输出信号等。

**B. shell 环境 pyenv lazy loader 半加载（独立 contributing factor）**

诊断中发现：用户交互 shell `~/.zshrc:157-166` 把 `python3` 定义为 zsh 函数 `_lazy_pyenv`，但当前 shell 处于半加载状态（`_lazy_pyenv` 已被某机制 unset，wrapper 函数 `python3()` 仍指向它）。导致任何 `python3 ...` 调用立即报：

```
python3:1: command not found: _lazy_pyenv
```

影响范围：`resolve_project_dir.py` / `validate_structure.py` / `parallel_utils.py` / `status.py` / `archive_sprint.py` / `parse_delimited_output.py` 全部用 `python3` 调用。任何 ghs skill 的 session 起手第一步就可能立即失败。

**与 hang 现象的关联**：不能解释"模型差异"（shell 错误对所有模型一样），但可能是 contributing factor——dispatcher 看到 shell 错误时若没识别为失败，可能 silent。

### 1.2 Goals

1. **G1（核心）**：把 ghs:code Parallel Verification 的 completion-signal 解析从"LLM 自 grep"改为"确定性 Python helper 提取"，消除 Opus 4.7 下的 silent hang
2. **G2**：建立显式 retry / User Decision 分支，子代理输出偏离协议时不 silent 等待
3. **G3**：所有解析逻辑可单测——结构对仗 `parse_delimited_output.py`，复用其设计哲学
4. **G4**：让 `python3` 调用在用户半加载 pyenv 环境下也能工作（H3 修复）
5. **G5**：本方案不重复 s2 sprint 已经覆盖的 ghs:plan 修复（s2-feat-002/003/004）；二者并行推进

### 1.3 Scope

**In scope**：
- 新增 `plugin/shared/scripts/parse_completion_signal.py` Python helper（确定性、可单测，支持 status / blocked / unknown 三态、id 提取、reason 提取、各类偏离格式 fallback）
- 修改 `plugin/skills/ghs-code/SKILL.md` 的 Verification Phase + Error Handling + User Decision Handling
- 同步 `plugin/shared/references/coding-agent.md` 的 Verification Phase 段
- 新增 helper 的单测脚本（参考 `test_parse_delimited_output.py` 结构）
- 修复 H3：让 skill 调用 python 的方式不受 pyenv lazy loader 半加载影响

**Out of scope**：
- ghs:plan 的修复（s2 sprint 已覆盖，本 plan 不重复）
- ghs:sprint（dispatcher 直接处理，无子代理协议）
- 子代理模型本身的可靠性调优（不在工程范围内）
- 用户 shell 环境的 pyenv lazy loader 配置（用户侧问题，但 skill 侧需 robust）

---

## 2. Current State Analysis

### 2.1 Existing Architecture

**ghs:code Parallel Mode 流程**（`plugin/skills/ghs-code/SKILL.md:122-211`）：

1. Pre-flight：resolve project dir、检查 sprint、clean working tree
2. Analysis：调 `parallel_utils.py` 输出 ready_features / batches
3. Dispatch：每个 feature spawn 一个 background general-purpose subagent，prompt 末尾要求"Signal completion by stating 'FEATURE COMPLETE: <feature_id>'"
4. **Verification（hang 点）**：
   - LLM 自己 grep 子代理输出找 `"FEATURE COMPLETE: <id>"` 或 `"FEATURE BLOCKED: <id>"`
   - 没有显式 retry、没有 fallback、没有 User Decision 分支
   - 子代理偏离协议（大小写变化、中文、自然语言、忘记输出）时 LLM 解析失败 → 不知道状态 → silent
5. State Update：根据 LLM 解析结果更新 features.json

**对比 ghs:plan 的 hang 模式**（s2 plan §1.1）：完全同构。s2 plan 给出的修复方案（确定性 helper + retry + User Decision Handling）可直接移植。

### 2.2 Constraints and Limitations

1. **dispatcher 是 LLM**：同 s2 plan §2.2 约束 1。LLM 自解析不稳定，必须外置
2. **background subagent 的输出通过 TaskOutput 拿到**：dispatcher 把整段输出（含 thinking、commit log、注释）当 raw text 喂给 helper
3. **completion signal 是单行信号**（不是 START/END 包裹），与 plan 的 delimiter 协议不同——helper 设计要适配
4. **每个 feature 一个子代理**：解析时必须按 feature_id 区分，避免一个子代理的信号被误归到另一个 feature
5. **失败状态需要 reason**：`FEATURE BLOCKED: <id> - <reason>` 的 reason 部分对 progress.md 记录有用
6. **项目用 Python 3 + stdlib**：同 s2 plan §2.2 约束 6。helper 必须遵循同一约定
7. **半加载 pyenv 问题**：H3 修复需要让 skill scripts 调用不依赖 shell 函数解析

---

## 3. Plan Design

### 3.1 Overall Architecture

**核心思路**（直接对仗 s2 plan §3.1）：

```
Before:
  Background subagent returns (raw text)
      |
      v
  Dispatcher (LLM) greps "FEATURE COMPLETE: <id>" / "FEATURE BLOCKED: <id>"
      |
      +-- normal case: success
      +-- deviation case: parse fails, silent hang

After:
  Background subagent returns (raw text)
      |
      v
  Dispatcher invokes (1:1 copy from SKILL.md template):
    python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_completion_signal.py \
      --feature-id <id> \
      --stdin \
      --min-length 50
      |
      v
  Script returns structured JSON:
    {
      "status": "completed" | "blocked" | "unknown",
      "feature_id": "<id>",
      "reason": "<reason text, or null>",
      "strategy": "exact_signal" | "case_insensitive" | "natural_language" | "none",
      "raw_signal_line": "<stripped signal line, or null>",
      "warnings": ["..."],
      "meta": { "feature_id": "...", "input_length": N }
    }
      |
      v
  Dispatcher branches (pure JSON-driven, no LLM re-parsing):
    completed                              -> update features.json status=completed
    blocked                                -> update features.json status=blocked + reason
    unknown 且 retry_count < MAX_RETRY     -> retry subagent with stronger format reminder
    unknown 且 retry_count >= MAX_RETRY    -> AskUserQuestion (retry / accept manual / abort)
```

### 3.2 Design Decisions

#### Q1：失败判定标准（helper 内部判定）

helper 返回的 `status` 字段就是失败判定：

| status | 触发条件 | dispatcher 行为 |
|--------|---------|----------------|
| `completed` | 精确匹配 `FEATURE COMPLETE: <id>` 或大小写/分隔变形 | 写 features.json `status: "completed"`，proceed |
| `blocked` | 精确匹配 `FEATURE BLOCKED: <id>` 或变形，含可选 reason | 写 features.json `status: "blocked"` + `blocked_reason`，proceed |
| `unknown` | 上述都未匹配（子代理偏离协议、self-loop 没收尾、自然语言表述） | retry（详见 Q2） |

**min-length 语义**：completion-signal 解析不依赖内容长度（信号是单行），但 helper 仍接受 `--min-length` 用于过滤完全空输出（默认 50 字符，子代理输出至少含 commit log 或基本描述）。低于阈值的输出视为 `unknown`。

#### Q2：Retry 策略

- **`MAX_RETRY = 1`**：与 s2 plan §3.2 Q3 一致。每个子代理调用最多重派 1 次
- **Retry prompt 追加内容**（附加到原 prompt 末尾）：

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
- Chinese variants
```

- **Retry 仍失败**：进入 Q3 兜底

#### Q3：超时/兜底

retry 仍失败时，dispatcher 兜底（按优先级）：

1. **首选**：使用 `AskUserQuestion`：

```
Subagent for feature <id> did not emit a clear completion signal after 1 retry.
The raw output has been saved to:
  <PROJECT_DIR>/.ghs/parallel/<sprint_id>/<feature_id>.raw.attempt<N>

Options:
- Retry once more (re-dispatch with stronger format reminder)
- Manually mark as completed (if you've verified the work)
- Manually mark as blocked (provide reason)
- Abort this feature, continue with others
```

2. **保留原始输出**：每次子代理返回，dispatcher 在写 features.json 前先把 raw 写到：
   - `<PROJECT_DIR>/.ghs/parallel/<sprint_id>/<feature_id>.raw.attempt<N>`（attempt 从 1 开始；retry 后是 attempt 2）
   - 这样所有历史 raw 都保留，debug 时可对比

3. **不**自动把"子代理没输出信号"当作 completed——必须显式确认（用户介入或 retry 成功）

#### Q4：影响范围

- **本次修改**：ghs:code Parallel Mode 的 Verification Phase 完整覆盖
- **ghs:code Single Mode**：不需要修改（无子代理协议，dispatcher 自己实现，没有外部解析需求）
- **ghs:plan**：s2 sprint 已覆盖，不重复
- **未来扩展**：helper 设计通用，可支持其他单行信号协议（如 future skill 的 `TASK DONE: <id>`）

#### Q5：与 s2 plan 的关系

- s2 plan 解决 ghs:plan 的 delimiter 协议（START/END 包裹）
- 本 plan 解决 ghs:code 的单行信号协议（COMPLETED/BLOCKED）
- 两个 helper 共享设计哲学（确定性外置 + retry + User Decision），但接口不同（plan 是 `--kind {plan|review|context_snapshot}`，本 helper 是 `--feature-id <id>`）
- 两个 plan 独立推进，互不阻塞

### 3.3 Helper Interface Design

```python
# plugin/shared/scripts/parse_completion_signal.py
#!/usr/bin/env python3
"""Parse completion signal from background subagent output.

Usage:
    python3 parse_completion_signal.py --feature-id s1-feat-002 --stdin < raw.txt
    python3 parse_completion_signal.py --feature-id s1-feat-002 --input-file path/to/raw.txt
    python3 parse_completion_signal.py --feature-id s1-feat-002 --input-string "..."

Output: JSON to stdout
{
  "status": "completed" | "blocked" | "unknown",
  "feature_id": "<id>",
  "reason": "<reason text, or null>",    # only non-null for blocked
  "strategy": "exact_signal" | "case_insensitive" | "natural_language" | "none",
  "raw_signal_line": "<stripped signal line, or null>",
  "warnings": ["..."],
  "meta": {
    "feature_id": "s1-feat-002",
    "input_length": 1234
  }
}

Exit codes:
    0 - signal detected (status == completed or blocked)
    1 - signal not detected (status == unknown)
    2 - invalid arguments / IO error
"""
```

**参数**：
- `--feature-id STR`（必填）—— 要匹配的 feature ID
- `--stdin` / `--input-file PATH` / `--input-string STR` —— 输入源（三选一）
- `--min-length N`（默认 50）—— 最小输入长度（过滤空输出）

**解析策略（按优先级）**：

```
STRATEGY 1: exact_signal
  - 精确匹配 r'^FEATURE\s+(COMPLETE|BLOCKED):\s*<feature_id>'
  - 完成态：返回 status=completed
  - 阻塞态：返回 status=blocked，从信号行尾部提取 reason（`- <reason>` 部分）
  
STRATEGY 2: case_insensitive
  - r'(?i)^feature\s+(complete|blocked):\s*<feature_id>' 容忍大小写变化
  - 完成态/阻塞态判定同 STRATEGY 1
  - warnings 添加 "case insensitive match"
  
STRATEGY 3: natural_language
  - 容忍更宽松的表述：
    - "The feature <id> is complete"
    - "I have completed feature <id>"
    - "<id> is blocked because ..."
  - 用关键词 + feature_id 共现 + 句末语义判定
  - warnings 添加 "natural language fallback: <matched pattern>"
  - 准确率较低，仅在前两个策略失败时使用

STRATEGY 4: none（兜底）
  - 所有策略都未匹配
  - 返回 status=unknown
  - 触发 dispatcher retry / User Decision
```

**reason 提取**（仅 blocked）：
- 精确/大小写匹配：从信号行 `-` 后部分提取（如 `FEATURE BLOCKED: s1-feat-002 - lint errors in foo.ts` → reason="lint errors in foo.ts"）
- 自然语言：从匹配行后最多 200 字符内提取（容忍多行 reason）

### 3.4 Key Flows

**修改后的 Verification Phase 流程**：

```
For each feature in batch:
1. 收到 background subagent 返回（通过 TaskOutput）
2. 把 raw_response 写到 .ghs/parallel/<sprint>/<feature_id>.raw.attempt<N>
3. 1:1 copy 以下命令（仅替换 <占位符>），调用 helper：
   echo "<raw_response>" | python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_completion_signal.py \
     --feature-id <feature_id> \
     --stdin \
     --min-length 50
4. 读取 JSON 输出
5. 分支（纯 JSON 驱动）：
   - status == completed:
       features.json 更新 status=completed
       proceed to next feature
   - status == blocked:
       features.json 更新 status=blocked + blocked_reason
       proceed to next feature
   - status == unknown 且 retry_count < MAX_RETRY:
       retry_count += 1
       重新派发 subagent，prompt 末尾追加 "Previous Output Format Issue" 段
       回到 step 1
   - status == unknown 且 retry_count >= MAX_RETRY:
       AskUserQuestion（retry / mark completed / mark blocked / abort，详见 §3.4.1）
```

#### 3.4.1 User Decision Handling

当 retry 用尽、dispatcher 走 AskUserQuestion 时，四个用户选项的语义：

| 用户选项 | dispatcher 行为 | 文件副作用 |
|---------|----------------|-----------|
| **Retry once more** | retry_count += 1（突破 MAX_RETRY 一次），重新派发 subagent | 新增 `<feature_id>.raw.attempt<N+1>` |
| **Manually mark as completed** | features.json 更新 status=completed，progress.md 记录"manually marked after format deviation" | features.json 写入；progress.md 追加说明 |
| **Manually mark as blocked** | features.json 更新 status=blocked，要求用户提供 reason；progress.md 记录 | features.json 写入；progress.md 追加 |
| **Abort this feature, continue with others** | features.json 保持 status=pending；progress.md 记录 abort 决策；继续 batch 内其他 feature | features.json 不变；progress.md 追加 |

dispatcher 在 AskUserQuestion 描述里必须列出当前 raw 输出文件路径，方便用户检查后决策。

### 3.5 pyenv shim 修复（H3）

**问题**：用户 `~/.zshrc:157-166` 把 python3 定义为 zsh 函数指向 `_lazy_pyenv`，但 loader 半加载状态下 `_lazy_pyenv` 已被 unset，导致 `python3` 调用直接报 "command not found"。

**修复方向**：

1. **首选：让 skill scripts 用 shebang 直接执行**（不通过 shell 函数）。当前 scripts 都有 `#!/usr/bin/env python3` shebang，调用方式应改成 `chmod +x script.py && ./script.py` 而非 `python3 script.py`。但这对 dispatcher（LLM）的 prompt 要求更高（必须记住 chmod + 用 ./）。

2. **次选：在 scripts 内部 wrapper 探测**。新建 `plugin/shared/scripts/_python_runtime.sh`：

```bash
#!/bin/bash
# Find a working python3 binary, bypassing shell function shims.
for candidate in /usr/bin/python3 /usr/local/bin/python3 "${PYTHON3:-}"; do
    [ -n "$candidate" ] && [ -x "$candidate" ] && exec "$candidate" "$@"
done
# Last resort: try whatever python3 resolves to in a clean env.
exec env -i PATH="/usr/bin:/usr/local/bin" python3 "$@"
```

skill scripts 改成调用 `_python_runtime.sh script.py ...`。但这对每个调用点都要改。

3. **保守：只在 SKILL.md 的 prompt 里加诊断指令**。在每个 skill 的 Session Protocol 起手加一步：

```
0. **Verify python3 works**:
   ```bash
   python3 --version
   ```
   If this errors with "command not found: _lazy_pyenv" or similar, your shell
   has a half-loaded pyenv lazy loader. Workaround:
   ```bash
   /usr/bin/python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
   ```
   Use the full path `/usr/bin/python3` for all subsequent python invocations
   in this session.
```

**推荐方案 3**（保守）：影响最小，只在 SKILL.md 加诊断步骤，不动 scripts。本 plan 范围内做这个；方案 1/2 留作 future improvement。

---

## 4. Implementation Steps

### Phase 1: 新增 parse_completion_signal.py 与单测
- [ ] **Step 1.1**：创建 `plugin/shared/scripts/parse_completion_signal.py`，按 §3.3 接口实现
- [ ] **Step 1.2**：创建 `plugin/shared/scripts/test_parse_completion_signal.py`，覆盖至少 15 个用例
- [ ] **Step 1.3**：本地运行测试确保全部通过

**Acceptance criteria**：
- helper 可独立调用，所有测试通过
- 三种 status（completed/blocked/unknown）正确返回
- reason 提取准确（blocked 才有）
- exit code 0/1/2 符合规范

### Phase 2: 修改 ghs-code SKILL.md 与 coding-agent.md
- [ ] **Step 2.1**：`plugin/skills/ghs-code/SKILL.md:195` Verification Phase 改成调 helper
- [ ] **Step 2.2**：`plugin/shared/references/coding-agent.md:259` 同步改造
- [ ] **Step 2.3**：两处都加 "You MUST copy this command verbatim" 强制指令
- [ ] **Step 2.4**：ghs-code SKILL.md 加 `## Error Handling` 段的 "Subagent output format deviation" 条目
- [ ] **Step 2.5**：加 `## User Decision Handling` 子段（四选项表格）

### Phase 3: pyenv shim 诊断指令
- [ ] **Step 3.1**：ghs-code / ghs-plan / ghs-sprint / ghs-status / ghs-archive / ghs-init 每个 SKILL.md 的 Session Protocol 起手加一步 "Verify python3 works"
- [ ] **Step 3.2**：在 `plugin/shared/references/coding-agent.md` 加同样的诊断步骤
- [ ] **Step 3.3**：在本 plan 的 Risks 段记录"半加载 pyenv 是用户侧问题，skill 侧只做诊断 + workaround"

### Phase 4: 手动验证
- [ ] **Step 4.1**：构造 5 种典型偏离格式（大小写、中文、自然语言、忘记输出、信号在 thinking 段）跑 helper，验证 status 正确
- [ ] **Step 4.2**：在 ghs-workspace 隔离工作区跑 `/ghs:code --parallel`，验证 Verification Phase 调 helper
- [ ] **Step 4.3**：临时改 helper 永远返回 unknown，验证 dispatcher 走 retry → User Decision 而非 hang
- [ ] **Step 4.4**：弱化 prompt 测试（子代理 prompt 只说 "implement and report status"），验证 dispatcher 仍 1:1 调 helper
- [ ] **Step 4.5**：模拟 pyenv 半加载环境，验证 Session Protocol 起手诊断步骤正确触发

---

## 5. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation Strategy |
|------|-----------|--------|---------------------|
| helper 的 natural_language 策略误判（把"feature is not complete"识别为 completed） | 中 | 高 | STRATEGY 3 仅在前两个策略失败时使用；warnings 字段标记；dispatcher 看到 natural_language strategy 时可选择性 ask user |
| dispatcher（LLM）忘记调 helper，仍按旧 grep 方式解析 | 中 | 高 | SKILL.md 把 Handling 写成 bash 命令模板，加粗 "MUST 1:1 copy"；Phase 4 Step 4.4 专项验证 |
| retry 也失败时用户不在场，AskUserQuestion 永久阻塞 | 低 | 中 | 与现有 "User not responding" 同类问题，已在 Error Handling 覆盖 |
| 子代理 self-loop（反复修 lint），background task 长时间不返回 | 中 | 中 | 这是 H5 假设，本 plan 不直接解决；记录在 progress.md 供后续观察；可考虑 future 加 background task timeout |
| pyenv shim 修复方案 3（仅诊断指令）不够，用户仍踩坑 | 中 | 中 | Phase 4 Step 4.5 验证；若不够，后续 plan 推进方案 1/2 |
| helper 调用本身失败（Python 异常、stdin 管道问题） | 低 | 中 | try/except 包住 main，异常返回 exit 2 + stderr 错误；dispatcher 看到 exit 2 当作 format deviation |
| 引入 helper 增加 dispatcher 工作复杂度 | 低 | 中 | helper 调用是单条 bash 命令 + 读 JSON，比 prose grep 更确定 |

---

## 6. Testing Strategy

### 6.1 单元测试（确定性部分）
`test_parse_completion_signal.py` 覆盖至少 15 个用例：
- exact_signal: 完美 `FEATURE COMPLETE: <id>` / `FEATURE BLOCKED: <id> - reason`
- case_insensitive: `Feature Complete: <id>` / `feature complete: <id>`
- 多余字符: `FEATURE COMPLETED: <id>` / `FEATURE COMPLETES: <id>`
- 中文: `特性完成: <id>` / `功能完成: <id>`
- 自然语言: `I have completed feature <id>` / `Feature <id> is blocked because lint fails`
- 信号在 thinking 段: `<thinking>FEATURE COMPLETE: <id></thinking>` → 应识别（thinking 是子代理推理，不是协议信号）
- 信号在 markdown bold 里: `**FEATURE COMPLETE: <id>**`
- 忘记输出信号: 子代理只 commit 没显式 COMPLETE/BLOCKED → unknown
- 空输出: 输入长度 < min_length → unknown
- 错误 feature_id: `FEATURE COMPLETE: <other_id>` → unknown（不是当前 feature）
- 多 feature 共现: 同一输出含 `<id1>` COMPLETE 和 `<id2>` BLOCKED，调 `--feature-id <id1>` 只识别 id1
- retry 场景: 输入完全无信号 → unknown + warnings 非空

### 6.2 集成验证（LLM 行为部分）
- 单测保证解析逻辑正确
- SKILL.md 的命令模板保证 dispatcher 一定会调用 helper
- 实际使用中遇到 hang 时，检查 `.ghs/parallel/<sprint>/<feature_id>.raw.attempt*` 是否存在
- Phase 4 Step 4.4 弱化 prompt 测试

### 6.3 回归保护
修改 SKILL.md 后，跑一次完整 `/ghs:code --parallel`（在隔离工作区），确认：
- 正常场景（子代理按格式输出）走 status=completed 分支
- blocked 场景正确返回 reason
- helper 调用命令在 SKILL.md 中可被 LLM 正确执行
- features.json 更新结果与原协议解析一致（无 regression）
- `.raw.attempt*` 文件在 retry 时正确累积

---

## 7. 与 s2 sprint 的关系

| 项目 | s2 sprint（已立项） | 本 plan |
|------|---------------------|---------|
| 范围 | ghs:plan 三处 delimiter 协议 | ghs:code Parallel Verification 单行信号协议 |
| 核心机制 | `parse_delimited_output.py`（START/END 包裹） | `parse_completion_signal.py`（单行信号） |
| 设计哲学 | 确定性外置 + retry + User Decision | 同左（结构对仗） |
| 状态 | s2-feat-001 已合入；s2-feat-002/003/004 待做 | 本 plan 立项后开新 sprint |
| 优先级 | 高（ghs:plan 是入口流程） | 高（ghs:code --parallel 是核心开发流程） |

两个 sprint 互不阻塞，可并行推进。建议先完成 s2-feat-002/003/004（ghs:plan 闭环），再启动本 plan 对应的 sprint。
