# ghs-plan：修 max_rounds 漏洞 + 重构 raw 文件生命周期（Round 3 修订版）

> **状态**: 待 review（Round 3，最终轮）
> **诊断来源**: 会话 `ad1ca924-a989-403f-bdbb-a5fa103b95af`（ghs-plan Phase 0.5 token 优化的元任务）
> **诊断日期**: 2026-06-18
> **改动范围**: 单文件 `plugin/skills/ghs-plan/SKILL.md`
> **行号锚定策略**: 本修订版删除了所有硬编码行号（Round 1 review Severe #1 指出原方案行号普遍漂移 ~118 行）。所有改动位置改用「段落标题 + 现有文本 before / 改后文本 after」三段对照定位。如确需提供行号作为辅助，标注「as of 2026-06-18」并放在括号里，标注为辅助信息，段落标题仍是主锚点。

## Context

会话 `ad1ca924` 在 `.ghs/plans/` 下生成了 **14 个文件**，而不是用户记忆中的 4 个（`xxx.md` / `xxx-context.md` / `xxx-review.md` / `xxx-status.json`）。

诊断显示两个独立问题：

### 问题 1：max_rounds 设计漏洞

status.json 里 `max_rounds=3`，但实际跑到了 **Round 5**。

- Phase 2 reviewer FAIL 路径（`### Phase 2: Plan Review` 段，`**Handling Reviewer Feedback**` 子段，"round >= max_rounds" 分支）**有** max_rounds 检查：达到上限时通知用户并问是否 accept。
- Phase 3 User Approval 的 reject 路径（`### Phase 3: User Approval` 段，"User rejects" bullet）**没有** max_rounds 检查：直接 "go back to Phase 1"。

事件链：
1. Round 3 reviewer **PASS**（用户原本期望结束）
2. 用户 reject："方案太乱了，重新写"
3. dispatcher **自创**「额外轮」概念静默继续 → Round 4
4. 用户再 reject："先确定那条路可以做再出方案"
5. dispatcher **自创** probe 步骤（派实测子代理、写 `-probe.md`）→ Round 5
6. 用户第三次 reject

Phase 2 的 max_rounds 约束被 Phase 3 的 reject 路径完全绕过。

### 问题 2：raw 文件累积浪费

commit `4272f82`（"feat(skills): ghs-plan 三处 Handling 改用 helper 解析 + 加 Format Recovery"）引入了 raw 文件保存机制，要求每次 subagent 调用都落盘 `<file>.raw.round<R>`，理由是 *"preserves every attempt for post-mortem debugging"*。

实测数据：

| 文件对比 | 总行数 | 变化行数 | 重复率 |
|---|---|---|---|
| `round1 → round2`（plan） | 958 | 115 | **88%** |
| `round2 → round3`（plan） | 1166 | 63 | **95%** |

5 轮 × 2 subagent = **10 个 raw 文件**，每个 7-46K 字符（plan.raw.round3 单文件 46K），总计 ~150KB 几乎全是冗余文本。

更糟糕的是 raw 文件里还包含 subagent 的「思考前缀」（"信息已经齐全。我现在产出完整方案..."）——这部分根本不是 plan 内容，但也被落盘。

### 期望结果

- Phase 3 reject 时正确尊重 max_rounds（用户明确知道在突破上限）。
- Happy path 主目录只产生 4 个最终文件（无 raw 污染），且 dispatcher 持有响应于内存中、通过临时文件 + `--input-file` 直传 parser（**零 shell 注入面**）。
- Error path 仍保留 raw 用于 post-mortem debug（commit `4272f82` 解决的 hang 问题不回归）。
- max_rounds 突破有**硬上限**，堵住 indefinite spawning。

## 改动范围

**单文件改动**：`plugin/skills/ghs-plan/SKILL.md`

raw 文件机制只在 SKILL.md 里（references/ 下的 plan-designer.md / plan-reviewer.md / context-snapshot-guide.md 都不引用），scripts/`parse_delimited_output.py` 已支持 `--stdin` / `--input-string` / `--input-file` 三种输入模式，**无需修改脚本**。

## 改动 1：max_rounds 在 Phase 3 reject 时生效 + 引入硬上限

### 1.1 改 `### Phase 3: User Approval` 段的 reject bullet

**位置锚**: `### Phase 3: User Approval` 段，"User rejects ->" 这一行（as of 2026-06-18，约 line 531，但以段落标题 + 文本为准）。

**当前**：

```markdown
- **User rejects** -> Ask for specific revision requests, update status to `revising`, go back to Phase 1 with the user's feedback attached to the revision instructions
```

**改为**：

```markdown
- **User rejects**:
  - If `round < max_rounds`: Ask for specific revision requests, update status to `revising`, increment `round`, go back to Phase 1.
  - If `round >= max_rounds` AND `max_rounds_breaches < MAX_BREACHES` (default `MAX_BREACHES = 2`, defined in [## Format Recovery](#format-recovery) → `**Constants**`): Max round limit reached. Use AskUserQuestion to present three options, since continuing would exceed the configured max_rounds:
    1. **Continue revising anyway** (one-shot breach): Increment `max_rounds_breaches`, ask for feedback, increment `round`, go to Phase 1. Notify the user this exceeds the original max_rounds budget and how many breaches remain.
    2. **Accept the current plan**: Proceed to Phase 4 finalization with the current plan file.
    3. **Abort**: Set status to `aborted`, stop.
  - If `round >= max_rounds` AND `max_rounds_breaches >= MAX_BREACHES`: Hard cap reached. Use AskUserQuestion to present only two options (the "Continue revising anyway" breach option is NO LONGER available):
    1. **Accept the current plan**: Proceed to Phase 4 finalization.
    2. **Abort**: Set status to `aborted`, stop.

  > The reject path does NOT silently continue past max_rounds. Each extra round requires explicit user opt-in, AND the total number of breaches is capped at `MAX_BREACHES` (defined in [## Format Recovery](#format-recovery) → `**Constants**`). Once the cap is reached, the dispatcher can no longer spawn a new round — the user must accept or abort. This closes BOTH the "silent continue" gap AND the "user keeps picking continue forever" gap (the latter being the actual root cause of the Round 5 runaway in the diagnostic session).
```

### 1.2 对称化 Phase 2 FAIL @ max_rounds 路径

**位置锚**: `### Phase 2: Plan Review` 段，`**Handling Reviewer Feedback**` 子段，`verdict == "FAIL"` 分支下 "round >= max_rounds" bullet（as of 2026-06-18，约 line 511，以段落 + 文本为准）。

**当前**：

```markdown
       - `round >= max_rounds` -> Notify the user that the max round limit is reached, use AskUserQuestion to show the current review result and ask whether to accept.
```

**改为**：

```markdown
       - `round >= max_rounds` AND `max_rounds_breaches < MAX_BREACHES` -> Max round limit reached. Use AskUserQuestion to present three options (symmetric with Phase 3 reject @ max_rounds):
         1. **Continue revising anyway** (one-shot breach): Increment `max_rounds_breaches`, increment `round`, go back to Phase 1. Show the user the review report so they understand what triggered the FAIL.
         2. **Accept the current plan despite the FAIL**: Proceed to Phase 4 with the current plan file (the user takes responsibility for the unfixed issues). Add a marker line at the top of the plan file: `<!-- WARNING: accepted with unfixed issues (round <R>, breaches=<B>): Severe=<X> Medium=<Y> -->` (see 改动 1.4 for Phase 4 handling).
         3. **Abort**: Set status to `aborted`, stop.
       - `round >= max_rounds` AND `max_rounds_breaches >= MAX_BREACHES` -> Hard cap reached. Use AskUserQuestion to present only two options (continue breach not available):
         1. **Accept the current plan despite the FAIL**: Same marker as above (改动 1.4).
         2. **Abort**.
```

> **对称性说明（Round 1 Medium #5 修复）**：Phase 2 FAIL @ max_rounds 和 Phase 3 reject @ max_rounds 现在用同一组三选项菜单（continue breach / accept / abort），用户在两个入口看到的决策能力一致。当 breach 数耗尽时，两处都降级到两选项。

### 1.3 改 `## Key Constraints` 第 2 条

**位置锚**: `## Key Constraints` 段，"Maximum review-revise rounds" 这一条（as of 2026-06-18，约 line 556）。

**当前**：

```markdown
2. **Maximum review-revise rounds**: The default limit is 5 rounds. For straightforward requirements (e.g., adding a single feature, small refactor, < 200 word description with no architectural changes), set `max_rounds` to 2 in the status file to save time. Once the limit is reached, the user must decide.
```

**改为**：

```markdown
2. **Maximum review-revise rounds (soft + hard cap)**: The default soft limit is 5 rounds (`max_rounds`). For straightforward requirements (e.g., adding a single feature, small refactor, < 200 word description with no architectural changes), set `max_rounds` to 2 in the status file to save time.

   Once `round >= max_rounds` is reached (either via Phase 2 FAIL or Phase 3 reject), the dispatcher MUST NOT silently start a new round. The user must explicitly choose one of three options: continue (breach), accept, or abort.

   **Hard cap on breaches**: The number of "Continue revising anyway" breaches is bounded by `MAX_BREACHES` (default `2`, defined in [## Format Recovery](#format-recovery) → `**Constants**`). When `max_rounds_breaches >= MAX_BREACHES`, the continue option is removed from the menu — the user can only accept or abort. This guarantees the dispatcher will terminate in at most `max_rounds + MAX_BREACHES` rounds regardless of user choices.
```

### 1.4 [Round 2 Medium #5 修复] 改 `### Phase 4: Finalization` 段，加 accepted-with-fail 标记分支

**位置锚**: `### Phase 4: Finalization` 段，步骤 2 "Commit the finalized plan document" 这一步（as of 2026-06-18，约 line 541-544）。

**当前**：

```markdown
2. Commit the finalized plan document:
   ```bash
   cd ${PROJECT_DIR} && git add docs/ghs/plans/${plan_file} && git commit -m "docs(plan): add technical plan - ${plan_file}"
   ```

3. Update status to `approved`.

4. Report the final plan location and a summary of review rounds to the user. Suggest the next step: use `/ghs:sprint` to break the plan into features for implementation.
```

**改为**：

```markdown
2. **Check for accepted-with-fail marker**: Read the top of the plan file. If it contains a line matching `<!-- WARNING: accepted with unfixed issues`, set `ACCEPTED_WITH_FAIL = true` and extract the `<R>`, `<B>`, `<X>`, `<Y>` values from the marker. Otherwise set `ACCEPTED_WITH_FAIL = false`.

3. Commit the finalized plan document. If `ACCEPTED_WITH_FAIL == true`, append the suffix `[accepted-with-fail; S=<X> M=<Y>]` to the commit message so that future `git log` readers can identify plans that passed with unfixed Severe/Medium issues:
   ```bash
   cd ${PROJECT_DIR} && git add docs/ghs/plans/${plan_file} && git commit -m "docs(plan): add technical plan - ${plan_file}[accepted-with-fail; S=<X> M=<Y>]"
   ```
   If `ACCEPTED_WITH_FAIL == false`, use the original commit message:
   ```bash
   cd ${PROJECT_DIR} && git add docs/ghs/plans/${plan_file} && git commit -m "docs(plan): add technical plan - ${plan_file}"
   ```

4. Update status to `approved`. If `ACCEPTED_WITH_FAIL == true`, also write `"accepted_with_fail": true` to the status file (so `status.json` can be grepped after-the-fact for "带病通过" plans). The `status` field itself stays `"approved"` (this avoids a new state-machine value); `accepted_with_fail` is a separate boolean flag.

5. Report the final plan location and a summary of review rounds to the user. If `ACCEPTED_WITH_FAIL == true`, explicitly warn the user: "This plan was accepted with unfixed issues (Severe=<X>, Medium=<Y>). These issues are listed in the review report and must be tracked separately." Suggest the next step: use `/ghs:sprint` to break the plan into features for implementation.
```

> **Round 2 Medium #5 修复对照**：原方案 Phase 2 的 "Accept the current plan despite the FAIL" 路径会跳到 Phase 4，但 Phase 4 不区分两种入口，事后 git log 看不出这个 plan 是带未解决 severe issue 通过的。本修订版在 Phase 4 加一个 `ACCEPTED_WITH_FAIL` 分支：plan header 含 `WARNING: accepted with unfixed issues` 标记时，commit message 加 `[accepted-with-fail; S=<X> M=<Y>]` 后缀，status.json 加 `accepted_with_fail: true` 字段，可审计性恢复。

## 改动 2：重构 raw 文件生命周期（核心，Round 1 Severe #2 修复）

### 2.1 改为「内存持有 + 临时文件 + `--input-file`」直传模式

替换当前"先 Write raw → `--input-file <raw>` → branch"模式为：dispatcher 在**内存中**持有 subagent 响应，仅在 error path 才落盘 raw；happy path 通过临时文件传给 parser（避免 shell 注入）。

**为什么不用 `printf '%s' "..." | --stdin`**（Round 1 Severe #2 根因）：subagent 响应里常见 `${var}` / 反斜杠 / 反引号 / `!`，这些在 shell 双引号内会被展开、转义、命令替换或历史展开。Round 1 原方案只考虑了 `"`，覆盖不全。`--input-file` 模式下 shell 完全不参与内容传递，**零注入面**。

**新流程模板**（替换三处 Handling 的 raw-save + parse 步骤，三处共用此模板，差异仅在 `<kind>` / `<target_file>` / `<min_length>` / `<completion_signal>`）：

```markdown
1. **Hold the subagent response in memory for the duration of parse.** Do NOT persist it to a post-mortem `.raw` file in the main `.ghs/plans/` directory on the happy path — only the `.tmp/` scratch file in step 2 exists transiently and is deleted in step 4. This is the key distinction from the old behavior: the main `.ghs/plans/` directory stays clean of raw files on success, but the response is briefly on disk under `.tmp/` for the duration of the parser call (which `--input-file` requires).

2. Write the response verbatim to a **temporary file** for parser input (this is a scratch file under `.tmp/`, not a post-mortem raw in the main directory):

   > **Copy this command verbatim, only replacing the `<placeholders>`.**

   Path: `<PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.<kind>.raw` (the `.tmp/` subdirectory is created once in Phase 0 init step 3; see 改动 2.6).

3. Invoke the parser helper via `--input-file` (shell never sees the response content — zero injection surface):

   > **You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT parse the subagent output yourself — the helper is the single source of truth for delimiter extraction AND (for review) the verdict.**

   Per-kind invocation (replace the flags based on `<kind>`):

   - **`<kind> = plan`** (Phase 1):
     ```bash
     command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
       --kind plan \
       --input-file <PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.plan.raw \
       --completion-signal "PLAN DESIGN COMPLETE" \
       --min-length 300
     ```
   - **`<kind> = review`** (Phase 2):
     ```bash
     command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
       --kind review \
       --input-file <PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.review.raw \
       --completion-signal "REVIEW COMPLETE" \
       --min-length 150
     ```
   - **`<kind> = context_snapshot`** (Phase 0.5):
     ```bash
     command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
       --kind context_snapshot \
       --input-file <PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.context.raw \
       --min-length 100
     ```
     Note: for context_snapshot, **do NOT pass `--completion-signal`** — there is no signal line for context snapshots, so the flag is omitted entirely (parser uses `default=None`).

4. Read the JSON object from stdout. **Delete the temporary file from step 2** (whether parse succeeded or failed — the temp file's job is done; persistence decisions are separate). Then branch on `status`:

   - **`ok`** or **`fallback_used`**:
     - Write `content` to the target file (`<plan_file>` / `<review_file>` / `<context_file>`). For `fallback_used`, prepend the warning comment `<!-- WARNING: extracted via fallback strategy: <strategy>; warnings: <warnings joined by "; "> -->`.
     - **No post-mortem raw file is created on the happy path** (unless `keep_raw_on_success: true` in status.json — see 改动 3.2). Proceed to the next phase.
   - **`empty`** / **`malformed`** (or `verdict == null` for review) with `retry_count < MAX_RETRY (=1)`:
     1. **Now persist the response to a post-mortem raw file in the main directory** — this is the only time a `.raw` file lands in the main `.ghs/plans/` directory:
        - Path: `<PROJECT_DIR>/.ghs/plans/<file>.raw` for the first attempt, `<PROJECT_DIR>/.ghs/plans/<file>.raw.retry<T>` for retry T.
     2. Increment `retry_count`, re-dispatch the subagent with the original prompt plus the [Format Recovery](#format-recovery) appendix.
     3. Return to step 1 with the new response (use `<file>.raw.retry<T>` if it fails again).
   - **`empty`** / **`malformed`** (or `verdict == null`) with `retry_count >= MAX_RETRY`: Post-mortem raw is already saved at `<file>.raw[.retry<T>]`. Use AskUserQuestion per [## User Decision Handling](#user-decision-handling).
```

> **Round 1 Severe #2 修复对照**：原方案用 `printf '%s' "..."`，覆盖不全 `` ` `` / `${...}` / `\` / `!` 四类字符。本修订版改用「临时文件 + `--input-file`」——dispatcher 把响应 Write 到 `.tmp/<session_id>.<kind>.raw`，parser 直接从文件读，shell 不参与内容传递，注入面为零。`parse_delimited_output.py` 已支持 `--input-file`（见 `main()` 的 argparse 定义及 `_read_input()` 的 `args.input_file` 分支），无需改脚本。
>
> **Round 1 Medium #2 修复对照**：原方案用 `--completion-signal "<PLAN DESIGN COMPLETE|REVIEW COMPLETE|>"` 这种 `|>` ambiguous 占位符表示 context_snapshot 是空字符串。本修订版明确分三列写明每个 kind 的 flag 组合，并显式说明 context_snapshot **不要传** `--completion-signal`（走 default=None）。
>
> **Round 2 Severe #2 修复对照**：Round 2 plan 的 step 1（持内存）与 step 2（写 `.tmp/<x>.raw`）自相矛盾——`.tmp/<x>.raw` 本身就是 `.raw*` glob 匹配的文件，"do NOT Write it to any `.raw*` file" 与 "Write to `.tmp/<x>.raw`" 死锁。本修订版把 step 1 改写为精确语义：「Hold the subagent response in memory for the duration of parse. Do NOT persist it to a post-mortem `.raw` file in the main `.ghs/plans/` directory on the happy path — only the `.tmp/` scratch file in step 2 exists transiently and is deleted in step 4」。区分「主目录 `.raw`（post-mortem，error path 才有）」与「`.tmp/` scratch（瞬时，parser 必需，step 4 删除）」两个概念。验证方式 step 1 也相应改为只 grep 主目录 `.ghs/plans/*.raw*`（不含 `.tmp/`）。

### 2.2 三处 Handling 段替换清单 + step 1.5 编号冲突修复（Round 2 Medium #4）

把改动 2.1 的新流程模板替换到三处 Handling。**为了消除 step 1.5 编号冲突**，本修订版**不**沿用 Round 2 plan 的"4 步 + 插 step 1.5"做法，而是按 kind **显式列出每个 kind 的最终步骤序列**：

- **`<kind> = context_snapshot`（Phase 0.5 Handling）**：4 步（持内存 / 写临时文件 / parse / branch），无 question pre-check。
- **`<kind> = plan`（Phase 1 Handling Designer Feedback）**：5 步 —— 把 Designer question pre-check 作为 **step 2**（在持内存 step 1 之后、写临时文件之前）。最终序列为：
  1. Hold response in memory (same as template step 1).
  2. **Designer question pre-check**: If the response contains a line matching `^QUESTION:\s*(.+)$`, treat it as a designer question — use AskUserQuestion to relay the question to the user, then re-dispatch the Plan subagent with the original prompt plus the user's answer appended. **No temporary file written** (the question response is short and not persisted). Skip the remaining steps.
  3. Write the response verbatim to `.tmp/<session_id>.plan.raw` (same as template step 2).
  4. Invoke parser via `--input-file` (same as template step 3 for plan).
  5. Read JSON, delete temp, branch on `status` (same as template step 4).
- **`<kind> = review`（Phase 2 Handling Reviewer Feedback）**：5 步 —— 把 Reviewer question pre-check 作为 **step 2**，与 Phase 1 对称。最终序列为：
  1. Hold response in memory.
  2. **Reviewer question pre-check**: If the response contains `^QUESTION:`, relay via AskUserQuestion and re-dispatch. No temp file written. Skip remaining.
  3. Write to `.tmp/<session_id>.review.raw`.
  4. Invoke parser via `--input-file` (for review).
  5. Read JSON, delete temp, branch on `status` AND `verdict` (verdict 仍从 JSON `verdict` 字段读取，不要重新 parse signal).

**位置锚 1（Phase 0.5）**: `### Phase 0.5: Context Snapshot Extraction` 段，`**Handling**: First save the subagent's raw response to disk` 这一段（as of 2026-06-18，约 line 256-280）。替换为 context_snapshot 的 4 步序列。

**位置锚 2（Phase 1 Designer）**: `### Phase 1: Plan Design (Round N)` 段，`**Handling Designer Feedback**` 子段，"1. Save the subagent's raw response to disk" 到 "4. ... branch on `status`" 这一段（as of 2026-06-18，约 line 373-398）。替换为 plan 的 5 步序列（Designer question pre-check 作为 step 2）。

**位置锚 3（Phase 2 Reviewer）**: `### Phase 2: Plan Review` 段，`**Handling Reviewer Feedback**` 子段，"1. Save the subagent's raw response to disk" 到 "4. ... branch on `status` and `verdict`" 这一段（as of 2026-06-18，约 line 485-514）。替换为 review 的 5 步序列（Reviewer question pre-check 作为 step 2）。

> **Round 2 Medium #4 修复对照**：Round 2 plan 要求 "把 Designer question pre-check 作为 step 1.5 插在 step 1 和 step 2 之间"，但新模板用 step 1-4 编号没有 step 1.5，导致编号 1/1.5/2/3/4 怪异。本修订版改为「按 kind 显式列出每个 kind 的最终步骤序列」：context_snapshot 4 步、plan 5 步（question pre-check 是 step 2）、review 5 步（question pre-check 是 step 2）。编号无歧义。

### 2.3 改 `## Format Recovery` 段：加 `MAX_BREACHES` 常量定义 + 改 Raw file naming

**位置锚**: `## Format Recovery` 段，`**Constants**` 子段 + `**Raw file naming**` 子段（as of 2026-06-18，约 line 580-585）。

#### 2.3a 加 `MAX_BREACHES` 常量（Round 2 Severe #3 修复）

**当前**（`**Constants**` 子段）：

```markdown
**Constants**:
- `MAX_RETRY = 1` — each subagent call may be re-dispatched at most once. This counter is independent from the review-revise `max_rounds` counter.
```

**改为**：

```markdown
**Constants**:
- `MAX_RETRY = 1` — each subagent call may be re-dispatched at most once. This counter is independent from the review-revise `max_rounds` counter.
- `MAX_BREACHES = 2` — the maximum number of "Continue revising anyway" breaches the user can opt into after `round >= max_rounds` is reached. Once `max_rounds_breaches >= MAX_BREACHES`, the "Continue revising anyway" option is removed from both Phase 2 FAIL @ max_rounds and Phase 3 reject @ max_rounds menus; the user can only accept or abort. This guarantees the dispatcher terminates in at most `max_rounds + MAX_BREACHES` rounds regardless of user choices. This constant is the **single source of truth** for the hard cap; Phase 2 / Phase 3 / Key Constraints all reference it by name. (Round 2 Severe #3: previously `MAX_BREACHES` was referenced 6 times without a definition point.)
```

> **Round 2 Severe #3 修复对照**：Round 2 plan 在 6 处引用 `MAX_BREACHES`，全部说"default `MAX_BREACHES = 2`"，但既不在 status.json、也不在脚本、也不在 SKILL.md Constants 段定义，硬上限是悬空承诺。本修订版选定**方案 A（推荐方案）**：在 `## Format Recovery` → `**Constants**` 段加 `MAX_BREACHES = 2`，与 `MAX_RETRY = 1` 并列，作为 single source of truth。改动 1.1 / 1.2 / 1.3 里的引用都改成交叉引用 `[## Format Recovery](#format-recovery) → **Constants**`，而不是重复声明 "default 2"。

#### 2.3b 改 Raw file naming（保持 Round 2 plan 的内容）

**当前**（`**Raw file naming**` 子段）：

```markdown
**Raw file naming** (preserves every attempt for post-mortem debugging):
- Phase 0.5 (context snapshot): `<context_file>.raw`, then `<context_file>.raw_retry1`, `<context_file>.raw_retry2`, ...
- Phase 1 (plan designer) and Phase 2 (reviewer): `<file>.raw.round<R>` for the first attempt in round R, then `<file>.raw.round<R>_retry1`, `<file>.raw.round<R>_retry2`, ...
```

**改为**：

```markdown
**Raw file naming** — post-mortem raw files ONLY exist on the error path (parse failure) or when `keep_raw_on_success: true` is set in status.json. They are NOT written on the happy path by default. Scratch files used for parser input live in `.ghs/plans/.tmp/` and are cleaned up immediately after parse (see 改动 2.1 step 4).
- First-attempt failure: `<file>.raw` (i.e. `<plan_file>.raw`, `<review_file>.raw`, `<context_file>.raw`)
- Retry-T failure: `<file>.raw.retry<T>` (e.g. `<plan_file>.raw.retry1`)
- Note: Round number is NO LONGER in the filename. Since happy path produces no post-mortem raw, and the normal error path is bounded by `MAX_RETRY=1`, there are at most 2 post-mortem raw files per subagent kind under normal retry (`.raw` + `.raw.retry1`).

  **User-opted retry exception**: If the user picks "Retry once more" in [## User Decision Handling](#user-decision-handling) after `MAX_RETRY` is exhausted, an additional `<file>.raw.retry<T+1>` is written. This path is NOT bounded by `MAX_RETRY` — but it IS bounded by the dispatcher's overall termination guarantee: the user can only retry-format as many times as they keep picking "Retry once more", and the session's max-rounds + breach hard cap (see Key Constraints #2) still bounds total subagent spawns. In practice, post-mortem raw count stays small.

  **`keep_raw_on_success: true` exception**: When this flag is set in status.json (see 改动 3.2), every successful parse ALSO writes a post-mortem raw at `<file>.raw` (overwriting any prior). Use this only for hard-to-debug sessions.
```

> **Round 1 Medium #1 修复对照**：原方案说"at most 2 raw files per subagent kind at any time"与 User Decision Handling 的 "Retry once more" 选项冲突（那个选项说会生成 `.raw.retry<T+1>`）。本修订版把"at most 2"限定为"under normal retry (MAX_RETRY=1)"，并显式承认 user-opted retry 路径会多写文件，但被 max-rounds + breach hard cap 间接约束。

### 2.4 改 `## Error Handling` 段的 format deviation 条目

**位置锚**: `## Error Handling` 段，"- **Subagent output format deviation**:" 这一条（as of 2026-06-18，约 line 572）。

**当前**：

```markdown
- **Subagent output format deviation**: If the subagent returns successfully but the output cannot be parsed via the delimiter protocol (detected via `parse_delimited_output.py` returning `status` "empty" or "malformed", or `verdict == null` for review), retry once with the [Format Recovery](#format-recovery) appendix appended to the prompt. If retry still fails, the raw output is already saved at `<file>.raw.round<R>[_retry<T>]`; use AskUserQuestion to let the user decide (retry / accept fallback / abort — see [## User Decision Handling](#user-decision-handling)). **Never silently hang on unparseable output.**
```

**改为**：

```markdown
- **Subagent output format deviation**: Detected via `parse_delimited_output.py` returning `status` "empty" or "malformed", or `verdict == null` for review. On detection, the response is persisted to a post-mortem raw at `<file>.raw` (first attempt) or `<file>.raw.retry<T>` (retry) in the main `.ghs/plans/` directory — see 改动 2.1 step 4. Retry once with the [Format Recovery](#format-recovery) appendix. If retry still fails, use AskUserQuestion to let the user decide (retry / accept fallback / abort — see [## User Decision Handling](#user-decision-handling)). **Never silently hang on unparseable output.**
```

### 2.5 改 `## User Decision Handling` 段的表格（Round 2 Medium #2 修复）

**位置锚**: `## User Decision Handling` 段的表格（as of 2026-06-18，约 line 651-662）。三行的 File side-effects 都要与新命名 + 新语义对齐：

**当前**（表格三行）：

```markdown
| **Retry once more** | Increment `retry_count` (one-shot override past `MAX_RETRY`), re-dispatch the subagent with the [Format Recovery](#format-recovery) appendix | New `<file>.raw.round<R>_retry<T+1>` (or `<context_file>.raw_retry<T+1>` for Phase 0.5) | Always available |
| **Accept the fallback-extracted content** | Take the most recent `fallback_used` content ... | `<file>` written; status advances to the next phase | Only available if at least one prior parse produced `fallback_used`, OR ... |
| **Abort this planning session** | Set status to `aborted`, stop all subsequent actions | All `.raw*` files preserved for post-mortem | Always available |
```

**改为**：

```markdown
| **Retry once more** | Increment `retry_count` (one-shot override past `MAX_RETRY`), re-dispatch the subagent with the [Format Recovery](#format-recovery) appendix | New `<file>.raw.retry<T+1>` (or `<context_file>.raw.retry<T+1>` for Phase 0.5) — round number no longer in filename | Always available |
| **Accept the fallback-extracted content** | Take the most recent `fallback_used` content ... | `<file>` written; status advances to the next phase | Only available if at least one prior parse produced `fallback_used`, OR ... |
| **Abort this planning session** | Set status to `aborted`, stop all subsequent actions | Any `.raw*` files written so far (post-mortem raw from error path, if any retry happened) are preserved in the main `.ghs/plans/` directory; `.tmp/` scratch is cleaned up by step 4 of the Handling flow (which deletes temp files even on the parse-success path) | Always available |
```

> **Round 2 Medium #2 修复对照**：Round 2 plan 只改了 "Retry once more" 行，「Abort」行还写 "All `.raw*` files preserved for post-mortem"，但在新模型下如果 abort 发生在 happy path 之后可能根本没有 `.raw*` 文件（happy path 默认不写 raw）。本修订版把「Abort」行改为"Any `.raw*` files written so far (post-mortem raw from error path, if any retry happened) are preserved; `.tmp/` scratch is cleaned"，语义准确。

### 2.6 [Round 2 Medium #1 修复] 改 `### Phase 0: Initialization` step 3，创建 `.tmp/` 子目录

**位置锚**: `### Phase 0: Initialization` 段，step 3 "Create working directory"（as of 2026-06-18，约 line 100-103）。

**当前**：

```markdown
3. **Create working directory**:
   ```bash
   mkdir -p ${PROJECT_DIR}/.ghs/plans
   ```
```

**改为**：

```markdown
3. **Create working directory** (creates both the main directory and the `.tmp/` scratch subdirectory in one shot, so Handling step 2's Write to `.tmp/<x>.raw` never hits "No such file or directory"):
   ```bash
   mkdir -p ${PROJECT_DIR}/.ghs/plans ${PROJECT_DIR}/.ghs/plans/.tmp
   ```
```

> **Round 2 Medium #1 修复对照**：Round 2 plan 改动 2.1 step 2 说 ".tmp/ subdirectory ... create it with `mkdir -p` on first use"，依赖每次 Write 临时文件前 dispatcher 自觉 mkdir。但 Phase 0 init step 3 现在只 `mkdir -p ${PROJECT_DIR}/.ghs/plans`，方案没改它去包含 `.tmp/`。本修订版显式改 Phase 0 init step 3，一次性创建整个目录结构。

## 改动 3：status.json 加 `max_rounds_breaches` + 可选 `keep_raw_on_success` + 可选 `accepted_with_fail`

### 3.1 加 `max_rounds_breaches` 字段

**位置锚**: `### State Tracking` 段的 status.json 示例（as of 2026-06-18，约 line 64-74）。

**当前**：

```json
{
  "plan_file": "{date}-{slug}.md",
  "context_file": "{date}-{slug}-context.md",
  "round": 1,
  "status": "designing | reviewing | revising | pending_approval | approved | rejected",
  "max_rounds": 5,
  "created_at": "YYYY-MM-DDTHH:mm:ss",
  "updated_at": "YYYY-MM-DDTHH:mm:ss"
}
```

**改为**：

```json
{
  "plan_file": "{date}-{slug}.md",
  "context_file": "{date}-{slug}-context.md",
  "round": 1,
  "status": "designing | reviewing | revising | pending_approval | approved | rejected | aborted",
  "max_rounds": 5,
  "max_rounds_breaches": 0,
  "accepted_with_fail": false,
  "created_at": "YYYY-MM-DDTHH:mm:ss",
  "updated_at": "YYYY-MM-DDTHH:mm:ss"
}
```

字段说明：
- `max_rounds_breaches`（int，默认 0）：每次用户在 Phase 2 FAIL @ max_rounds 或 Phase 3 reject @ max_rounds 选 "Continue revising anyway" 时 +1。达到 `MAX_BREACHES`（默认 2，定义见 `## Format Recovery` → `**Constants**`）后，continue 选项从菜单消失，dispatcher 强制 accept 或 abort。
- `accepted_with_fail`（bool，默认 `false`）：Phase 4 finalization 时若 plan header 含 `WARNING: accepted with unfixed issues` 标记（来自 Phase 2 "Accept despite FAIL"），写为 `true`。事后 `grep -l '"accepted_with_fail": true' .ghs/plans/*-status.json` 可找出所有"带病通过"的 plan。`status` 字段本身仍是 `"approved"`（不引入新状态值），这是独立 flag。

### 3.2 加可选 `keep_raw_on_success` 字段

**Round 1 Medium #4 修复**：原方案把 happy path 不落盘 raw 作为硬规则，但 commit `4272f82` 引入 raw 是为了 post-mortem debug，删了等于关掉一个 debug 通道。折中：默认不落盘（避免污染），但用户可临时打开。

在同一 status.json 示例里加一个可选字段（带注释说明默认值，作为文档说明而非 status.json 模板的必填字段）：

```json
{
  ...
  "max_rounds_breaches": 0,
  "keep_raw_on_success": false,
  ...
}
```

字段说明：
- `keep_raw_on_success`（bool，默认 `false`）：当为 `true` 时，即使 happy path parse 成功，dispatcher 也额外把 subagent 响应写到 `<file>.raw`（覆盖式，每次 round 重写）。用于 hard-to-debug sessions —— 用户怀疑 plan 内容看着 OK 但实际有逻辑错误、想事后看 subagent 原始输出时，把这个字段改 `true` 重跑即可。正常 session 保持 `false`，主目录干净。

> **与改动 2.1 step 4 的联动**：step 4 的 `ok` / `fallback_used` 分支末尾加一句 "unless `keep_raw_on_success: true` in status.json — in that case, additionally write the response to `<file>.raw` (overwrite) for post-mortem"。

## 验证方式

> **Round 2 Severe #1 修复对照**：Round 2 plan 的验证方式 step 2 里嵌入了字面 delimiter token（作为 dry-run 测试示例的内容），`parse_delimited_output.py` 用 first-match 策略提取 content 时看到字面 token 就提前结束，导致 raw 文件 530 行但 parse 后只剩 ~345 行，Verification 整个章节及后续内容全部丢失。本修订版的 dry-run 测试示例**绝对不出现字面 delimiter token**，需要展示 delimiter 用法时改为占位符 + 引用 parser 脚本 docstring，详见 step 2。

### 1. 静态检查（grep）

#### 1a. 旧模式不应残留

```bash
grep -n "\.raw\.round\|raw_retry" plugin/skills/ghs-plan/SKILL.md
```

**预期**: 无输出（旧命名 `.raw.round<R>` 与下划线版本 `raw_retry<T>` 都不应再出现）。

> **Round 2 Medium #3 修复对照**：Round 2 plan 的 grep 模式包含 `printf '%s' "<subagent` 和 `--input-string "<subagent` 两条无效断言——当前 SKILL.md 既没有 `printf '%s' "<subagent...>` 也没有 `--input-string "<subagent...>`，这两条 grep 永远 pass 但实际是空检查，给执行者虚假的"通过"信号。本修订版删掉这两条无效断言，只保留 `.raw.round` 与 `raw_retry` 两条针对旧命名的检查。

#### 1b. 新关键字应出现

```bash
grep -n "\.tmp/\|keep_raw_on_success\|max_rounds_breaches\|MAX_BREACHES\|accepted_with_fail" plugin/skills/ghs-plan/SKILL.md
```

**预期**: 每个关键字至少出现一次。

#### 1c. 主目录无 happy-path raw 残留的语义检查

由于 happy path 现在不再在主 `.ghs/plans/` 写 raw（只在 error path 或 `keep_raw_on_success: true` 时写），在真实跑完一个 happy-path `/ghs:plan` session 后做：

```bash
ls ${PROJECT_DIR}/.ghs/plans/*.raw* 2>/dev/null | grep -v "\.tmp/"
```

**预期**: 在一个无 format deviation 的 happy-path session 里，主目录无 `.raw*` 文件残留（`.tmp/` 已在 Handling step 4 删除）。注意：如果有 retry 发生过（error path），主目录会有 `.raw` / `.raw.retry<T>` —— 这是预期的，不是污染。

### 2. dry-run parse_delimited_output.py（无需真跑 subagent）

> **关键约束**：本步骤的测试输入文件内容**绝对不包含字面 delimiter token**。如果需要测试 parser 对 delimiter 的处理，请直接参考 `${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py` 的 module docstring 里已有的示例，或参考 `plugin/skills/ghs-plan/SKILL.md` 里 `## Format Recovery` → `**Retry appendix templates**` 段已有的字面示例（那是 SKILL.md 的固有内容，由 Format Recovery 模板承载，不在本 plan 的验证代码块里复述）。本 plan 的验证代码块只用占位符 `YOUR_KIND` + `_START` / `_END` 拼出 delimiter，避免字面 token 出现在 plan 内容里。

#### 2a. 用 `--input-file` 测 happy path（占位符替代字面 delimiter）

```bash
# 先把测试内容写到临时文件（模拟 dispatcher 的行为）。
# 注意：以下 START / END token 是占位符，需要替换为对应 kind 的真实字面 delimiter
# 才能真跑——参考 parser 脚本的 module docstring 里的字面 token 列表，或参考
# SKILL.md Format Recovery 段里 Retry appendix templates 里给出的真实示例。
TMPFILE=$(mktemp)
cat > "$TMPFILE" <<'EOF'
YOUR_KIND_START
# Test plan
hello world content here that exceeds min length requirement for the parser.
This is a synthetic test body to verify --input-file happy path extraction.
YOUR_KIND_END

EOF

# 用 plan kind 测，期待 status=ok
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
  --kind plan \
  --input-file "$TMPFILE" \
  --completion-signal "PLAN DESIGN COMPLETE" \
  --min-length 50

rm -f "$TMPFILE"
```

**预期**: 输出 JSON 含 `"status": "ok"`、`"verdict"` 字段为 null（因为 review completion signal 不匹配）、`content` 字段含 "hello world" 字符串。

> **说明**：上面用 `YOUR_KIND_START` / `YOUR_KIND_END` 是**占位符**，dispatcher 真跑测试时需要替换为 plan kind 对应的真实字面 delimiter（参考 parser 脚本 docstring）。本 plan 不复述字面 token 以避免 parser first-match 截断问题（Round 2 Severe #1 根因）。

#### 2b. 用 `--input-file` 测 error path

构造一个无任何 delimiter 的内容，期待 parser 返回 `status: "empty"` 或 `"malformed"`：

```bash
TMPFILE=$(mktemp)
cat > "$TMPFILE" <<'EOF'
This is plain text with no delimiters at all. The parser should fail to extract content.
EOF

command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
  --kind plan \
  --input-file "$TMPFILE" \
  --completion-signal "PLAN DESIGN COMPLETE" \
  --min-length 50

rm -f "$TMPFILE"
```

**预期**: 输出 JSON 含 `"status": "empty"` 或 `"status": "malformed"`，`content` 字段为空字符串。

### 3. 集成 dry-run（端到端 happy path）

跑一遍 `/ghs:plan "<small requirement>"`，session 走完 Phase 0.5 / 1 / 2 / 3 / 4 都不发生 format deviation。然后：

```bash
# 1. status.json 应有新字段
grep -E '"max_rounds_breaches":\s*0|"accepted_with_fail":\s*false' \
  ${PROJECT_DIR}/.ghs/plans/*-status.json

# 2. 主目录应有 4 个最终文件，无 .raw 残留（除非用户手动设了 keep_raw_on_success: true）
ls ${PROJECT_DIR}/.ghs/plans/*.md ${PROJECT_DIR}/.ghs/plans/*-context.md \
   ${PROJECT_DIR}/.ghs/plans/*-review.md ${PROJECT_DIR}/.ghs/plans/*-status.json
ls ${PROJECT_DIR}/.ghs/plans/*.raw* 2>/dev/null  # 期待空（happy path）

# 3. .tmp/ 目录应为空（Handling step 4 删除了所有 scratch）
ls ${PROJECT_DIR}/.ghs/plans/.tmp/ 2>/dev/null  # 期待空

# 4. docs/ghs/plans/ 应有最终 plan
ls ${PROJECT_DIR}/docs/ghs/plans/*.md
```

### 4. 集成 dry-run（端到端 accepted-with-fail path）

构造一个会触发 reviewer FAIL @ max_rounds 的场景（例如设 `max_rounds: 1` 跑一个需要多轮的复杂需求），用户在 AskUserQuestion 里选 "Accept the current plan despite the FAIL"。然后：

```bash
# 1. plan header 应含 WARNING 标记
head -5 ${PROJECT_DIR}/docs/ghs/plans/*.md | grep "WARNING: accepted with unfixed issues"

# 2. commit message 应含后缀
cd ${PROJECT_DIR} && git log -1 --pretty=%s | grep "\[accepted-with-fail; S=[0-9]\+ M=[0-9]\+\]"

# 3. status.json 应有 accepted_with_fail: true
grep '"accepted_with_fail": true' ${PROJECT_DIR}/.ghs/plans/*-status.json
```

## 风险与新边界情况

1. **`.tmp/` 目录可能与 .gitignore 冲突**：`.ghs/` 整体在 `.gitignore` 里，`.tmp/` 子目录自动被忽略，无新风险。但建议在 Phase 0 init step 3 之后明确 dispatcher 不需要 `git add` 任何 `.tmp/` 文件。

2. **临时文件 cleanup 失败**：如果 dispatcher 在 step 4 删除临时文件前崩溃，`.tmp/` 会留下孤儿文件。下次 Phase 0 init step 3 的 `mkdir -p` 不会清理它们。建议 dispatcher 在每个 Handling 流程开头可选地 `rm -f ${PROJECT_DIR}/.ghs/plans/.tmp/<session_id>.*.raw`（best-effort，不强制）。

3. **`MAX_BREACHES` 与 `max_rounds` 的耦合**：用户可在 status.json 里把 `max_rounds` 设到 1（如 simple requirement），同时 dispatcher 自动给 `MAX_BREACHES = 2` 上限。最坏情况是 1 + 2 = 3 轮。比原方案的 indefinite spawning 强很多。

4. **`accepted_with_fail` plan 的下游影响**：用户在 Phase 2 accept-with-fail 后，这个 plan 进入 `/ghs:sprint` 时 sprint planner 不一定能识别"带病"标记。建议在 `/ghs:sprint` SKILL.md 里加一条检查：若 status.json `accepted_with_fail: true`，sprint planner 在创建 feature 时给每个 feature 加一个 "originated-from-accepted-with-fail-plan" 标记。这超出本 plan 范围，作为 follow-up issue 记录。

5. **User Decision Handling 表格的 Retry once more 与新命名的一致性**：改动 2.5 已经把 `.raw.round<R>_retry<T+1>` 改成 `.raw.retry<T+1>`。但若用户在 status.json 里把 `keep_raw_on_success: true`，主目录会同时有 happy-path `.raw` 和 error-path `.raw.retry<T>`，命名一致。

6. **delimiter token 字面量在 SKILL.md 的 Format Recovery 模板里是固有内容**：SKILL.md 现有的 Format Recovery → Retry appendix templates 段**本来就**包含字面 delimiter token（作为给 subagent 的示例）。这是 SKILL.md 的固有内容，不是本 plan 引入的；本 plan **不**删除或修改 Format Recovery 模板里的字面 token。本 plan 自身的验证代码块避免出现字面 token 是为了避免 dispatcher 解析本 plan 时被 parser first-match 截断——这与 SKILL.md 运行时是否含字面 token 无关（运行时 parser 输入是 subagent 响应，不是 SKILL.md 本身）。

## 不在范围

- 不改 `parse_delimited_output.py`（已支持 `--input-file`）。
- 不改 `parse_completion_signal.py` / `resolve_project_dir.py`。
- 不改 references/ 下的 plan-designer.md / plan-reviewer.md / context-snapshot-guide.md（它们不引用 raw 文件机制）。
- 不删 SKILL.md Format Recovery → Retry appendix templates 段里的字面 delimiter（那是 SKILL.md 固有内容）。
- 不引入新的 status 字段值 `accepted_with_fail` 作为 status enum（用独立 boolean flag，避免状态机复杂化）。
- 不改 `/ghs:sprint` SKILL.md（accepted_with_fail 标记的下游处理作为 follow-up issue）。
- 不实现 Optimization #2 提到的独立 self-test 脚本（CI 集成是 follow-up）。

## 附录

### 附录 A：本次改动涉及的段落锚清单（核对用）

执行者按此清单逐个核对段落标题在 SKILL.md 里存在：

1. `### State Tracking`（status.json 示例）— 改动 3.1
2. `### Phase 0: Initialization`（step 3 mkdir）— 改动 2.6
3. `### Phase 0.5: Context Snapshot Extraction`（`**Handling**` 段）— 改动 2.2 位置锚 1
4. `### Phase 1: Plan Design (Round N)`（`**Handling Designer Feedback**` 段）— 改动 2.2 位置锚 2
5. `### Phase 2: Plan Review`（`**Handling Reviewer Feedback**` 段）— 改动 2.2 位置锚 3 + 改动 1.2
6. `### Phase 3: User Approval`（"User rejects" bullet）— 改动 1.1
7. `### Phase 4: Finalization`（step 2 commit）— 改动 1.4
8. `## Key Constraints`（第 2 条 max rounds）— 改动 1.3
9. `## Error Handling`（format deviation 条目）— 改动 2.4
10. `## Format Recovery` → `**Constants**` 子段 — 改动 2.3a
11. `## Format Recovery` → `**Raw file naming**` 子段 — 改动 2.3b
12. `## User Decision Handling`（表格）— 改动 2.5

### 附录 B：与 commit `4272f82` 的兼容性

commit `4272f82` 引入 raw 文件机制是为了解决 dispatcher hang 问题（解析失败时无 fallback）。本 plan 的 error path 仍保留 raw 写入（`<file>.raw` / `<file>.raw.retry<T>`），且 User Decision Handling 的 "Retry once more" 选项仍可让用户无限重试（被 max_rounds + breach hard cap 间接约束）。因此 commit `4272f82` 解决的 hang 问题不回归。

唯一行为变化：happy path 主目录不再有 raw 文件。如果用户怀疑 happy path 的 plan 有问题，可临时设 `keep_raw_on_success: true` 重新跑，恢复 raw 文件输出用于 debug。

## Round 2 Review 修复对照表

| Round 2 Issue | 严重度 | Round 2 描述摘要 | 本修订版如何修复 |
|---|---|---|---|
| Severe #1 | Severe | plan 内容嵌入字面 delimiter token（dry-run 测试示例 `cat > "$TMPFILE" <<'EOF' ... <PLAN_END_TOKEN>` 处），导致 parser first-match 提前截断，Verification 章节及之后内容全部丢失 | 验证方式 step 2 的 dry-run 测试示例**绝对不出现字面 delimiter token**。需要展示 delimiter 用法时改用占位符 `YOUR_KIND_START` / `YOUR_KIND_END`，并显式注明「参考 parser 脚本 docstring 里的字面 token 列表」。同时在验证方式开头加显式约束说明。本 plan 全文已 grep 检查不含字面 PLAN/REVIEW/CONTEXT_SNAPSHOT 的 START/END token。 |
| Severe #2 | Severe | step 1「持内存，do NOT Write to any `.raw*` file」与 step 2「Write to `.tmp/<x>.raw`」自相矛盾（`.tmp/<x>.raw` 就是 `.raw*` glob 匹配），Round 1 Medium #3 实际没修 | step 1 改写为精确语义：「Hold the subagent response in memory for the duration of parse. Do NOT persist it to a post-mortem `.raw` file in the main `.ghs/plans/` directory on the happy path — only the `.tmp/` scratch file in step 2 exists transiently and is deleted in step 4」。区分「主目录 `.raw`（post-mortem）」与「`.tmp/` scratch（瞬时）」。验证方式 step 1c 改为只 grep 主目录 `.ghs/plans/*.raw*`（用 `grep -v "\.tmp/"` 排除 scratch），删除"内容不落盘"这一物理上做不到的承诺。 |
| Severe #3 | Severe | `MAX_BREACHES` 在 6 处引用但无定义点（不在 status.json、不在脚本、不在 SKILL.md Constants） | 选定**方案 A**：改动 2.3a 在 `## Format Recovery` → `**Constants**` 段加 `MAX_BREACHES = 2`，与 `MAX_RETRY = 1` 并列，作为 single source of truth。改动 1.1 / 1.2 / 1.3 里的所有引用改成交叉引用 `[## Format Recovery](#format-recovery) → **Constants**`，不再重复声明 "default 2"。 |
| Medium #1 | Medium | `.ghs/plans/.tmp/` 子目录没在 Phase 0 init step 3 创建，Handling step 2 Write 可能触发 "No such file or directory" | 改动 2.6 显式改 `### Phase 0: Initialization` step 3，把 `mkdir -p ${PROJECT_DIR}/.ghs/plans` 改为 `mkdir -p ${PROJECT_DIR}/.ghs/plans ${PROJECT_DIR}/.ghs/plans/.tmp`，一次性创建好整个目录结构。 |
| Medium #2 | Medium | User Decision Handling 表格只改了「Retry once more」行，「Abort」行仍写 "All `.raw*` files preserved"，在新模型下语义不对（happy path 后 abort 可能无 `.raw*`） | 改动 2.5 把「Abort」行改为「Any `.raw*` files written so far (post-mortem raw from error path, if any retry happened) are preserved in the main `.ghs/plans/` directory; `.tmp/` scratch is cleaned up by step 4 of the Handling flow」。 |
| Medium #3 | Medium | 验证 step 1 grep 模式过宽，含 `printf '%s' "<subagent` 和 `--input-string "<subagent` 两条无效断言（当前 SKILL.md 无这些字符串），给执行者虚假通过信号 | 验证 step 1a 重写为只 grep `\.raw\.round\|raw_retry`（旧命名残留检查），删掉两条无效断言。step 1b 单独 grep 新关键字（`.tmp/` / `keep_raw_on_success` / `max_rounds_breaches` / `MAX_BREACHES` / `accepted_with_fail`）。 |
| Medium #4 | Medium | Phase 1 Designer Handling 的 step 1.5 插入位置与新模板的 step 1-4 编号冲突（无 step 1.5），LLM 执行时编号混乱 | 改动 2.2 改为「按 kind 显式列出每个 kind 的最终步骤序列」：context_snapshot 4 步、plan 5 步（question pre-check 是 step 2）、review 5 步（question pre-check 是 step 2）。编号无歧义。 |
| Medium #5 | Medium | Phase 2 "Accept despite FAIL" 与 Phase 3 "Accept" 操作语义未对齐，"带病通过" plan 在 git log 看不出区别 | 改动 1.4 显式改 Phase 4 Finalization：plan header 含 `WARNING: accepted with unfixed issues` 标记时，commit message 加 `[accepted-with-fail; S=<X> M=<Y>]` 后缀，status.json 加 `accepted_with_fail: true` 字段（改动 3.1），dispatcher 报告阶段显式 warning。Optimization #1（status 字段加 accepted_with_fail 作为可选最终值）已通过独立 boolean flag 实现，不污染状态机。 |