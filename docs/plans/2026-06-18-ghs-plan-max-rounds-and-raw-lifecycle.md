# ghs-plan：修 max_rounds 漏洞 + 重构 raw 文件生命周期

> **状态**: 待 review
> **诊断来源**: 会话 `ad1ca924-a989-403f-bdbb-a5fa103b95af`（ghs-plan Phase 0.5 token 优化的元任务）
> **诊断日期**: 2026-06-18
> **改动范围**: 单文件 `plugin/skills/ghs-plan/SKILL.md`

## Context

会话 `ad1ca924` 在 `.ghs/plans/` 下生成了 **14 个文件**，而不是用户记忆中的 4 个（`xxx.md` / `xxx-context.md` / `xxx-review.md` / `xxx-status.json`）。

诊断显示两个独立问题：

### 问题 1：max_rounds 设计漏洞

status.json 里 `max_rounds=3`，但实际跑到了 **Round 5**。

- Phase 2 reviewer FAIL 路径（SKILL.md line 393）**有** max_rounds 检查：`round >= max_rounds -> Notify the user that the max round limit is reached`
- Phase 3 User Approval 的 reject 路径（SKILL.md line 413）**没有** max_rounds 检查：`User rejects -> ... go back to Phase 1`

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
- Happy path 主目录只产生 4 个最终文件（无 raw 污染）。
- Error path 仍保留 raw 用于 post-mortem debug（commit `4272f82` 解决的 hang 问题不回归）。

## 改动范围

**单文件改动**：`plugin/skills/ghs-plan/SKILL.md`

raw 文件机制只在 SKILL.md 里（references/ 下的 plan-designer.md / plan-reviewer.md / context-snapshot-guide.md 都不引用），scripts/`parse_delimited_output.py` 已支持 `--stdin` / `--input-string` / `--input-file` 三种输入模式，**无需修改脚本**。

## 改动 1：max_rounds 在 Phase 3 reject 时生效

**位置**: `### Phase 3: User Approval` 段（当前 SKILL.md line 406-413）

**当前**：

```markdown
- **User rejects** -> Ask for specific revision requests, update status to `revising`, go back to Phase 1 with the user's feedback attached to the revision instructions
```

**改为**：

```markdown
- **User rejects**:
  - If `round < max_rounds`: Ask for specific revision requests, update status to `revising`, increment round, go back to Phase 1.
  - If `round >= max_rounds`: Max round limit reached. Use AskUserQuestion to make the user explicitly choose between three options, since continuing would exceed the configured max_rounds:
    1. **Continue revising anyway** (one-shot override): Treat as `round < max_rounds` path — ask for feedback, increment round, go to Phase 1. Notify the user this exceeds the original max_rounds budget.
    2. **Accept the current plan**: Proceed to Phase 4 finalization with the current plan file.
    3. **Abort**: Set status to `aborted`, stop.

  > The reject path does NOT silently continue past max_rounds. Each extra round requires explicit user opt-in. This closes the gap where user rejection bypassed the Phase 2 max_rounds check and dispatcher kept spawning subagents indefinitely.
```

**位置**: `## Key Constraints` 第 2 条（line 438）补充一句明确：

```markdown
2. **Maximum review-revise rounds**: ... Once the limit is reached (either via Phase 2 FAIL or Phase 3 reject), the user must explicitly decide — dispatcher MUST NOT silently start a new round past max_rounds.
```

## 改动 2：重构 raw 文件生命周期（核心）

替换三处 Handling 段（Phase 0.5 Path B / Phase 1 Designer / Phase 2 Reviewer）的 raw 处理逻辑。

**新策略**：happy path 即时清理（零中间文件），error path 才保留。

### 新流程模板（三处 Handling 通用）

替换当前"先 Write raw → parse → branch"模式为：

```markdown
1. Parse the subagent response directly via stdin (no intermediate file):

   > **Copy this command verbatim, only replacing the <placeholders>.**

   ```bash
   printf '%s' "<subagent response verbatim>" | \
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
     --kind <plan|review|context_snapshot> \
     --stdin \
     --completion-signal "<PLAN DESIGN COMPLETE|REVIEW COMPLETE|>" \
     --min-length <300|150|100>
   ```

   > **Shell quoting**: The subagent response is enclosed in double quotes inside `printf '%s' "..."`. If the response contains literal `"` characters, escape them as `\"` in the printf argument. (Heredoc is intentionally avoided because dispatcher models occasionally mis-emit heredoc terminators.)

2. Read the JSON object from stdout. Branch on `status`:

   - **`ok`** or **`fallback_used`**: Write `content` to the target file (`<plan_file>` / `<review_file>` / `<context_file>`). **No raw file is created.** Proceed to the next phase.
     - If `fallback_used`, prepend the warning comment `<!-- WARNING: extracted via fallback strategy: <strategy>; warnings: <warnings joined by "; "> -->`.
   - **`empty`** / **`malformed`** (or `verdict == null` for review) with `retry_count < MAX_RETRY (=1)`:
     1. **Save the raw response to disk for post-mortem debug** — this is the only time a raw file is written:
        - Path: `<PROJECT_DIR>/.ghs/plans/<file>.raw` for the first attempt, `<file>.raw.retry<T>` for retry T.
     2. Increment `retry_count`, re-dispatch the subagent with the original prompt plus the [Format Recovery](#format-recovery) appendix.
     3. Return to step 1 with the new response (use `<file>.raw.retry<T>` if it fails again).
   - **`empty`** / **`malformed`** (or `verdict == null`) with `retry_count >= MAX_RETRY`: Raw is already saved at `<file>.raw[.retry<T>]`. Use AskUserQuestion per [## User Decision Handling](#user-decision-handling).
```

### Raw 文件命名简化

**位置**: `## Format Recovery` 段（line 465-467）

**当前**：

```markdown
- Phase 0.5 (context snapshot): `<context_file>.raw`, then `<context_file>.raw_retry1`, `<context_file>.raw_retry2`, ...
- Phase 1 (plan designer) and Phase 2 (reviewer): `<file>.raw.round<R>` for the first attempt in round R, then `<file>.raw.round<R>_retry1`, `<file>.raw.round<R>_retry2`, ...
```

**改为**：

```markdown
**Raw file naming** — raw files ONLY exist on the error path (parse failure). They are NOT written on happy path.
- First-attempt failure: `<file>.raw` (i.e. `<plan_file>.raw`, `<review_file>.raw`, `<context_file>.raw`)
- Retry-T failure: `<file>.raw.retry<T>` (e.g. `<plan_file>.raw.retry1`)
- Note: Round number is NO LONGER in the filename. Since happy path produces no raw, and error path is bounded by MAX_RETRY=1, there are at most 2 raw files per subagent kind at any time.
```

### Error Handling 段更新

**位置**: line 454

**当前**：

```markdown
- **Subagent output format deviation**: If the subagent returns successfully but the output cannot be parsed via the delimiter protocol (detected via `parse_delimited_output.py` returning `status` "empty" or "malformed", or `verdict == null` for review), retry once with the [Format Recovery](#format-recovery) appendix appended to the prompt. If retry still fails, the raw output is already saved at `<file>.raw.round<R>[_retry<T>]`; use AskUserQuestion to let the user decide (retry / accept fallback / abort — see [## User Decision Handling](#user-decision-handling)). **Never silently hang on unparseable output.**
```

**改为**：

```markdown
- **Subagent output format deviation**: Detected via `parse_delimited_output.py` returning `status` "empty" or "malformed", or `verdict == null` for review. On detection, the raw response is saved to `<file>.raw` (first attempt) or `<file>.raw.retry<T>` (retry) for post-mortem debug. Retry once with the [Format Recovery](#format-recovery) appendix. If retry still fails, use AskUserQuestion to let the user decide (retry / accept fallback / abort — see [## User Decision Handling](#user-decision-handling)). **Never silently hang on unparseable output.**
```

### User Decision Handling 段更新

**位置**: line 525-538

表格里 raw 文件路径同步改为新命名（去 `.round<R>`）：
- `<file>.raw.retry<T+1>` 替代 `<file>.raw.round<R>_retry<T+1>`
- Phase 0.5 用 `<context_file>.raw.retry<T+1>`

## 改动 3：状态文件结构补 max_rounds_breaches 字段（可选）

**位置**: `### State Tracking` 的 status.json 示例（line 64-74）

为了让用户 reject 后的「Continue revising anyway」选择有持久记录，加一个可选字段：

```json
{
  ...
  "max_rounds_breaches": 0,  // count of times user opted to continue past max_rounds via Phase 3
  ...
}
```

可选——主要价值是 finalize 后 post-mortem 能看到本次 planning 突破了几次上限。

## 验证方式

### 1. 静态检查

```bash
grep -n "raw\.round\|\.raw\.retry\|input-file" plugin/skills/ghs-plan/SKILL.md
```

**预期**: 无 `raw.round` 残留；`input-file` 应已替换为 `--stdin` + `printf` 模式。

### 2. dry-run parse_delimited_output.py（无需真跑 subagent）

```bash
printf '%s' "<<<PLAN_START>>>
# Test plan
hello world content here that exceeds min length requirement
<<<PLAN_END>>>
PLAN DESIGN COMPLETE" | command python3 plugin/shared/scripts/parse_delimited_output.py --kind plan --stdin --completion-signal "PLAN DESIGN COMPLETE" --min-length 50
```

**预期**: JSON `status: ok`。

### 3. 真跑一次 ghs:plan（在 ghs-workspace 目录）

参考 CLAUDE.md「When running eval loops with `/skill-creator`, use the `ghs-workspace` directory」。

- 用一个简单需求，预期 max_rounds=2
- **Happy path 验证**: `.ghs/plans/` 下只有 4 个文件（无 `.raw` 残留）
- **Error path 验证**: 临时把 parser 的 `--min-length` 调到 999999 让 happy parse 失败 → 验证 `<file>.raw` 被创建

### 4. 回归 max_rounds 漏洞

- max_rounds=2，跑到 Round 2 reviewer PASS → 用户 reject
- **预期**: dispatcher 显示 AskUserQuestion 三选项（continue/accept/abort），**而不是**直接派 Round 3 designer

## 不在范围

- 不改 `parse_delimited_output.py`（接口已足够）
- 不改 references/ 下的文档（它们不引用 raw 机制）
- 不引入 diff/patch 模式让 Round 2+ designer 只输出修订（这是更大的设计变更，不在本次诊断范围）
- 不改 commit `4272f82` 解决 hang 问题的核心机制（parse helper 仍是确定性外置工具，仅 raw 文件生命周期调整）

## 附录：诊断时的关键证据

### 实际生成的文件清单（`.ghs/plans/` 下 `2026-06-18-ghs-plan-token-opt*` 系列）

| 文件 | 大小 | 性质 |
|---|---|---|
| `-status.json` | 958B | ✓ 最终 |
| `-context.md` | 7.1K | ✓ 最终 |
| `-context.raw` | 5.6K | ✗ raw（应删） |
| `-review.md` | 7.4K | ✓ 最终 |
| `-review.raw.round1` | 17.5K | ✗ raw（应删） |
| `-review.raw.round2` | 13.9K | ✗ raw（应删） |
| `-review.raw.round3` | 7.5K | ✗ raw（应删） |
| `-probe.md` | 2.1K | ✗ dispatcher 自创 |
| `.md`（plan） | 19.9K | ✓ 最终 |
| `.raw.round1` | 24.8K | ✗ raw（应删） |
| `.raw.round2` | 40.9K | ✗ raw（应删） |
| `.raw.round3` | 46.9K | ✗ raw（应删） |
| `.raw.round4` | 21.2K | ✗ raw（应删） |
| `.raw.round5` | 19.9K | ✗ raw（应删） |

总计 14 个文件，**预期新机制下只产生 4 个**（status.json, context.md, review.md, plan.md）。

### 时间线（核心节点）

| 时间 | 事件 |
|---|---|
| 03:22 | Round 1 context 抽取 |
| 03:26 | Round 1 plan designer |
| 03:33 | Round 1 review FAIL (2 Severe + 5 Medium + 3 Opt) |
| 03:38 | Round 2 plan designer（parse 触发 retry，文件名覆盖而非 `_retry1`） |
| 03:41 | Round 2 review FAIL (1 Medium + 5 Opt) |
| 03:46 | Round 3 plan designer |
| 03:49 | Round 3 review **PASS** |
| 03:49 | Phase 3 → 用户 reject #1：「方案太乱了，重新写」|
| 10:47 | Round 4 designer（dispatcher 自创「额外轮」概念） |
| 10:50 | Phase 3 → 用户 reject #2：「先确定那条路可以做再出方案」|
| 11:21 | dispatcher 自创 probe 步骤（派实测子代理） |
| 11:25 | Round 5 designer |
| 11:25 | Phase 3 → 用户 reject #3（dispatcher 这次没继续） |

### Token 消耗估算

- 主会话日志：1.6MB JSONL
- 10 个 subagent 日志：约 1.3MB（平均 130K）
- 5 轮 plan.raw 累积：~150KB markdown
- **总计 3MB+ JSONL**，估计 token **50K-100K**
