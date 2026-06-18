# 健壮化 Plan 输出解析方案

## Revision Log
- **Round 2（本版本）**：基于 Round 1 review 报告逐条修订全部 8 个 Medium 问题；采纳 Optimization #4 和 #6
  - Medium #1：`--completion-signal` 语义改为"行首前缀匹配 + 正则锚定"，覆盖 review 的 `REVIEW COMPLETE | Verdict: PASS/FAIL | ...` 模板
  - Medium #2：helper JSON 输出新增 `completion_signal` 和 `verdict` 字段，dispatcher 不再退回 LLM 解析 verdict
  - Medium #3：STRATEGY 4 thinking 兼容性拆为两场景，明确 extended thinking API 已剥离的兜底语义
  - Medium #4：SKILL.md 改造加强为"1:1 copy 指令 + 失败后果说明"，Phase 4 增加"故意触发偏离场景验证 LLM 真调 helper"
  - Medium #5：按 kind 区分 `--min-length`：context_snapshot=100 / plan=300 / review=150，helper 默认值仍保留 200
  - Medium #6：`.raw` 文件改为带 round/retry 后缀的文件名，保留 retry 历史
  - Medium #7：补 3 类关键测试用例（多 START/END 对、嵌套 code fence、`ADDITIONAL FILES READ:` 后续内容）
  - Medium #8：测试入口规范——`if __name__ == '__main__': unittest.main()`，可 `python3 path/to/test.py` 直接运行，不引入 pytest
  - Optimization #4：fallback_used 写文件时顶部 warning 注释含 strategy 和 warnings
  - Optimization #6：SKILL.md 新增 "User Decision Handling" 子段，明确三选项各自写什么文件
- Round 1：基于 context snapshot 初稿设计

## 1. Background and Goals

### 1.1 Background

`ghs-plan` skill 在三个地方使用 delimiter-based output protocol（`<<<X_START>>>...<<<X_END>>>`）让子代理把内容回传给 dispatcher：
1. Plan Designer → Dispatcher（`<<<PLAN_START>>>...<<<PLAN_END>>>`）
2. Plan Reviewer → Dispatcher（`<<<REVIEW_START>>>...<<<REVIEW_END>>>`）
3. Explore subagent → Dispatcher（`<<<CONTEXT_SNAPSHOT_START>>>...<<<CONTEXT_SNAPSHOT_END>>>`）

由于 LLM 输出本质上不可控，子代理偶尔会偏离协议（用 code fence 代替分隔符、把分隔符放进 thinking 段、用中文变体 `《《PLAN_START》》`、直接输出 markdown 等）。当这种情况发生时：
- dispatcher 的 "Extract the content between `<<<PLAN_START>>>` and `<<<PLAN_END>>>`" 步骤提取出空内容
- 既没有显式错误触发 retry，也没有 `QUESTION` 触发 user 介入
- 状态停在 `designing` / `reviewing`，整个 iteration 流程 long-hang

### 1.2 Goals

1. **G1（核心）**：当子代理输出偏离分隔符协议时，dispatcher 能确定性、可测试地提取出 plan 内容，避免 hung 住
2. **G2**：建立明确的"格式不符合"判定标准与 retry 策略，避免无限循环
3. **G3**：所有解析逻辑必须可单测——把确定性解析逻辑放进一个 Python helper，单测覆盖各种偏离场景
4. **G4**：方案同时覆盖 designer、reviewer、explore 三个协议（snapshot §Risks Q5）
5. **G5**：保留现有约束：designer 不能写文件；dispatcher 仍负责协调；severity-graded review 不变
6. **G6（Round 2 新增）**：dispatcher 在判定 review 结论（PASS/FAIL）时，不得退回"LLM 读取文本"路径——所有 verdict、completion signal 信息必须由 helper 显式输出

### 1.3 Scope

**In scope**：
- 新增 `parse_delimited_output.py` Python helper（确定性、可单测，支持前缀/正则完成信号、verdict 解析）
- 修改 `plugin/skills/ghs-plan/SKILL.md`（Phase 0.5 / Phase 1 / Phase 2 / Error Handling / 新增 User Decision Handling 子段）
- 同步 `plugin/shared/references/plan-designer.md` 和 `plan-reviewer.md` 的 Output Format 段，加强 prompt 约束
- 新增 helper 的单测脚本（含 Round 2 新增的 5 类边界用例）

**Out of scope**：
- ghs-code 的 `FEATURE COMPLETE: <id>` 协议（单行信号，无 START/END 分隔符，不会触发本类 hang；不在本次修改）
- ghs-sprint（dispatcher 直接处理，无子代理协议，无此问题）
- 子代理模型本身的可靠性调优（不在工程范围内）

---

## 2. Current State Analysis

### 2.1 Existing Architecture

**协议三处定义**（snapshot §现状 已详述）：
- `plugin/skills/ghs-plan/SKILL.md:138` — Explore subagent 的 `CONTEXT_SNAPSHOT` 分隔符
- `plugin/skills/ghs-plan/SKILL.md:203-212` — Plan Designer 的 `PLAN` 分隔符 + Completion Signal（`PLAN DESIGN COMPLETE`，字面字符串）
- `plugin/skills/ghs-plan/SKILL.md:251-264, 281` — Plan Reviewer 的 `REVIEW` 分隔符 + Completion Signal（`REVIEW COMPLETE | Verdict: PASS/FAIL | Severe: X Medium: Y Optimization: Z`，**带变量模板**）

**Handling 三处**（这是 hang 的直接发生点）：
- `SKILL.md:142` — "Extract the content between `<<<CONTEXT_SNAPSHOT_START>>>` and `<<<CONTEXT_SNAPSHOT_END>>>`..."
- `SKILL.md:216` — "Extract the content between `<<<PLAN_START>>>` and `<<<PLAN_END>>>`..."
- `SKILL.md:286` — "Extract the content between `<<<REVIEW_START>>>` and `<<<REVIEW_END>>>`..."，**且要求 "Evaluate the verdict from the completion signal"**

三处 handling 都是 prose 描述，dispatcher（即 LLM 自己）按描述去识别分隔符、截取中间内容、对于 review 还要再从 completion signal 里读 verdict。没有任何 fallback、没有任何错误分支。

**现有 Error Handling**（`SKILL.md:347-351`）只覆盖：
- Subagent failure（子代理报错）
- File read/write failure
- User not responding

**缺口**：没有 cover "subagent 成功返回但格式不符合协议"。

### 2.2 Constraints and Limitations

1. **dispatcher 是 LLM**：dispatcher 本身是主对话中的 Claude，解析由 LLM 执行。LLM 解析有不确定性，必须把确定性逻辑外置到 Python 脚本
2. **不能让 designer 写文件**：`SKILL.md:150` 明确 "Plan subagents do not have file write permissions"。Plan agent 通常没有 Write tool。绕过分隔符协议让 designer 直接写文件违反设计原则
3. **任何固定分隔符都可能被 LLM 改写**：包括 `<<<PLAN_START>>>` 被写成 `《《PLAN_START》》`、`<<< PLAN_START >>>`（带空格）、`<<PLAN_START>>`（少一个尖括号）
4. **Completion signal 也可能带变量**：review 的 `REVIEW COMPLETE | Verdict: PASS/FAIL | ...`，字面匹配会漏；解析策略必须支持前缀/正则
5. **dispatcher 必须能拿到 verdict**：现有 `SKILL.md:286` 流程依赖 verdict 判定 PASS/FAIL；helper 不能只返回 content，必须显式输出 verdict
6. **项目用 Python 3 + stdlib**：`plugin/shared/scripts/` 已有 6 个 Python 脚本（`status.py` / `validate_structure.py` / `init_project.py` / `archive_sprint.py` / `parallel_utils.py` / `resolve_project_dir.py`），全部用 stdlib（pathlib、argparse、json、re），无第三方依赖，无 pytest。helper 必须遵循同一约定
7. **`run_in_background` 子代理场景**：ghs-code 用了 background agents，但 ghs-plan 的三个子代理是同步派发

---

## 3. Plan Design

### 3.1 Overall Architecture

**核心思路：方案 D（多格式兼容）+ 方案 A（fallback 解析）+ 方案 B（条件 retry），通过 Python helper 实现确定性 + 可测试性。**

不采用方案 C（让 designer 写文件）：违反 §2.2 约束 2。

```
Before:
  Subagent output (raw text)
      |
      v
  Dispatcher (LLM) reads "Extract between <<<PLAN_START>>> and <<<PLAN_END>>>"
  (reviewer 还要再 LLM-read "Verdict: PASS/FAIL")
      |
      +-- normal case: success
      +-- deviation case: empty extraction, hang

After:
  Subagent output (raw text)
      |
      v
  Dispatcher invokes (1:1 copy from SKILL.md template):
    python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
      --kind <plan|review|context_snapshot> \
      --stdin \
      --completion-signal "<prefix>" \
      --min-length <N>
      |
      v
  Script returns structured JSON:
    {
      "status": "ok" | "fallback_used" | "empty" | "malformed",
      "content": "<extracted>",
      "strategy": "exact_delimiter" | "normalized_delimiter" | "code_fence" | "whole_body" | "none",
      "completion_signal": "<stripped signal line, or null>",
      "verdict": "PASS" | "FAIL" | null,        # only for --kind review
      "warnings": ["...", "..."],
      "meta": { "kind": "...", "input_length": N, "content_length": N }
    }
      |
      v
  Dispatcher branches (pure JSON-driven, no LLM re-parsing):
    ok / fallback_used (content length >= MIN_LEN) -> write to file, proceed
    empty / malformed                                -> retry up to MAX_RETRY
                                                       -> still failing -> ask user
```

### 3.2 Design Decisions（Q1-Q6 明确回答）

#### Q1：方案选择 = D + A + B 组合

- **D（多格式兼容）**：helper 内部依次尝试 4 种解析策略，按优先级返回第一个成功的
- **A（fallback）**：当所有"严格/半严格"策略都失败时，把整个输出（剥离 thinking 痕迹、剥离尾部 completion signal 之后）作为最后兜底
- **B（retry）**：当 helper 返回 `empty`/`malformed` 时，dispatcher 重派子代理，prompt 附加"上次输出格式警告 + few-shot 示例"
- **C（让 designer 写文件）**：明确不采用

**为什么这个组合最务实**：
- 多数实际失败是"分隔符被改写"或"用了 code fence"——helper 的策略 2、3 直接 cover
- "完全没分隔符也没 fence 的纯 markdown" 比例较少——靠 fallback 兜底，结合 retry 给 LLM 第二次机会
- 把不可控的 LLM 解析换成确定性的 Python 解析，从根本上消除"dispatcher 自己也读不懂"的递归问题

#### Q2：失败判定标准（在 helper 内部判定）

helper 返回的 `status` 字段就是失败判定：

| status | 触发条件 | dispatcher 行为 |
|--------|---------|----------------|
| `ok` | 策略 1（精确分隔符）成功，且 `len(content.strip()) >= MIN_LEN` | 写文件，proceed |
| `fallback_used` | 策略 2/3/4（normalize/code_fence/whole_body）成功，且内容 ≥ MIN_LEN | 写文件 + 在文件顶部加 warning 注释（含 strategy + warnings，见 Optimization #4），proceed（但记录 warning） |
| `empty` | 所有策略都提取出内容，但全部 `< MIN_LEN` | retry |
| `malformed` | 没有任何策略找到内容（输出只有 thinking / completion signal / 完全无意义） | retry |

**参数（按 kind 区分，Round 2 修订 Medium #5）**：

| kind | 推荐 `--min-length` | 依据 |
|------|---------------------|------|
| `context_snapshot` | **100** | 小项目经 codegraph 加速后可能只有 50-150 字符的精简摘要，仍合法 |
| `plan` | **300** | 一份合格 plan 含 Background/Goals/Architecture 等多段，至少几百字符 |
| `review` | **150** | PASS 场景下"无严重/中等问题，仅 Optimization N 项"通常 100-300 字符 |
| helper 默认值 | **200** | 通用兜底，未指定 kind 时使用 |

完成信号字符串（`PLAN DESIGN COMPLETE` 等）不计入 content；helper 显式输出 `completion_signal` 和 `verdict` 字段（见 §3.3）。

#### Q3：Retry 策略

- **`MAX_RETRY = 1`**：每个子代理调用最多重派 1 次。理由：偶发问题通常一次重派就解决；多次重派意味着系统性问题，应交给用户判断。这与 `max_rounds = 5` 的 review-revise 循环独立计数。**数据基础**：当前无日志统计，先 ship MAX_RETRY=1，根据用户反馈再调整（采纳 Optimization #3 的措辞）
- **Retry prompt 追加内容**（附加到原 prompt 末尾）：
  ```
  ## IMPORTANT: Previous Output Format Issue
  Your previous response could not be parsed correctly. The delimiters
  <<<PLAN_START>>> ... <<<PLAN_END>>> were missing or malformed.

  This time you MUST:
  1. Output the delimiters EXACTLY as written: <<<PLAN_START>>> on its own line, <<<PLAN_END>>> on its own line.
  2. Put ALL plan content between them.
  3. Do NOT wrap the delimiters in a code fence.
  4. Do NOT translate or modify the delimiter strings.

  Example (correct):
  <<<PLAN_START>>>
  # My Plan
  ... content ...
  <<<PLAN_END>>>
  PLAN DESIGN COMPLETE
  ```
- **Retry 仍失败**：进入 Q4 兜底分支

#### Q4：超时/兜底

retry 仍失败时，dispatcher 的兜底行为（按优先级）：

1. **首选**：使用 `AskUserQuestion` 通知用户：
   ```
   The plan designer's output could not be parsed after 1 retry.
   The raw output has been saved to:
     <PROJECT_DIR>/.ghs/plans/<plan_file>.raw.round<R>[_retry<T>]
   
   Options:
   - Retry once more (re-dispatch with stronger format reminder)
   - Accept the fallback-extracted content (if any) and proceed to review
   - Abort this planning session
   ```
2. **保留原始输出（Round 2 修订 Medium #6）**：每次子代理返回，dispatcher 在写 `<plan_file>` 之前，先把原始 raw 文本写到带后缀的文件名：
   - 第 1 次返回（round R 内）：`<plan_file>.raw.round<R>`（如 `xxx.md.raw.round1`）
   - retry 后第 2 次返回：`<plan_file>.raw.round<R>_retry1`
   - 同一 round 内多次 retry 用 `_retry1` / `_retry2` 区分；不同 review-revise round 用 `.round<R>` 区分
   - 这样所有历史 raw 都保留，debug 时可对比
3. **不**自动采用"把整个原始输出当 plan 写入文件"作为静默 fallback——必须经用户同意，因为这种 fallback 内容质量不可控，可能让 reviewer 基于错误内容给出错误 review

> 注：方案 3.1 流程图里的"fallback_used"分支（helper 返回 fallback_used 时直接 proceed）针对的是 **helper 内部策略成功**的情况（如 LLM 用了 code fence 但内容完整）——这种内容质量是可控的。Q4 兜底针对的是 **retry 仍失败**的更严重情况

#### Q5：影响范围

- **本次修改**：ghs-plan 的 3 个协议全部覆盖（Plan Designer、Plan Reviewer、Explore subagent）。helper 用 `--kind {plan|review|context_snapshot|generic}` 参数支持三种分隔符，三处统一调用
- **ghs-code**：不用修改（`FEATURE COMPLETE: <id>` 是单行信号，无 hang 风险）。但本方案的 helper 可被未来扩展支持单行信号解析
- **ghs-sprint**：不用修改（dispatcher 直接处理，无子代理协议）

#### Q6：测试性

**核心机制**：所有解析逻辑放到 `plugin/shared/scripts/parse_delimited_output.py`，dispatcher 用 bash 调用它。LLM 只负责"调用脚本 + 读取 JSON + 按字段分支"，不再负责"理解分隔符语义"或"读 verdict"

**单测覆盖**（`plugin/shared/scripts/test_parse_delimited_output.py`）：

| 测试用例 | 输入 | 期望 status | 期望 strategy |
|---------|------|------------|--------------|
| exact_match | 完美 `<<<PLAN_START>>>...<<<PLAN_END>>>` | ok | exact_delimiter |
| extra_whitespace | `<<< PLAN_START >>>...<<< PLAN END >>>` | fallback_used | normalized_delimiter |
| chinese_quotes | `《《PLAN_START》》...《《PLAN_END》》` | fallback_used | normalized_delimiter |
| fewer_brackets | `<<PLAN_START>>...<<PLAN_END>>` | fallback_used | normalized_delimiter |
| code_fence_wrapped | ` ```\n<<<PLAN_START>>>...\n<<<PLAN_END>>>\n``` ` | ok | exact_delimiter |
| markdown_only_with_fence | 只有 ` ```\n# Plan\n... ` 无分隔符 | fallback_used | code_fence |
| pure_markdown | 纯 `# Plan\n...`，无任何包裹 | fallback_used | whole_body |
| thinking_only | 只有 `<thinking>...</thinking>` | malformed | none |
| empty_between | `<<<PLAN_START>>><<<PLAN_END>>>` | empty | exact_delimiter |
| too_short_between | `<<<PLAN_START>>>hi<<<PLAN_END>>>` | empty | exact_delimiter |
| truncated_no_end | `<<<PLAN_START>>>... `（无 END） | fallback_used | whole_body |
| completion_signal_only | 只有 `PLAN DESIGN COMPLETE` | malformed | none |
| **multi_kind_pairs**（Round 2 新增，Medium #7-a）| 同一输出含 `<<<PLAN_START>>>...<<<PLAN_END>>>` 和 `<<<REVIEW_START>>>...<<<REVIEW_END>>>`，跑 `--kind review` | ok | exact_delimiter（仅取 REVIEW 对） |
| **nested_code_fence**（Round 2 新增，Medium #7-b）| ` ```python\n# code containing <<<PLAN_START>>> as string\n``` ` 然后 `<<<PLAN_START>>>...` | ok | exact_delimiter（exact 优先，不被嵌套 fence 干扰） |
| **additional_files_read**（Round 2 新增，Medium #7-e）| `<<<PLAN_START>>>...<<<PLAN_END>>>\nPLAN DESIGN COMPLETE\nADDITIONAL FILES READ: a.py, b.py` | ok | exact_delimiter |
| **review_with_verdict_pass**（Round 2 新增，配合 Medium #2）| `<<<REVIEW_START>>>...<<<REVIEW_END>>>\nREVIEW COMPLETE \| Verdict: PASS \| Severe: 0 Medium: 0 Optimization: 1`，跑 `--kind review --completion-signal "REVIEW COMPLETE"` | ok + `completion_signal` 含整行 + `verdict: "PASS"` | exact_delimiter |
| **review_with_verdict_fail**（同上）| 类似但 `Verdict: FAIL` | ok + `verdict: "FAIL"` | exact_delimiter |

**测试运行方式（Round 2 修订 Medium #8）**：
- 每个测试文件以 `if __name__ == '__main__': unittest.main()` 自带入口
- 直接运行：`python3 /Users/tom/github/golden-hoop-spell/plugin/shared/scripts/test_parse_delimited_output.py`
- 不引入 pytest / pytest.ini / conftest.py，与现有 `plugin/shared/scripts/` 的纯 stdlib 约束一致

### 3.3 Helper Interface Design

```python
# plugin/shared/scripts/parse_delimited_output.py
#!/usr/bin/env python3
"""Parse delimiter-based subagent output.

Usage:
    python3 parse_delimited_output.py --kind plan --stdin < raw_output.txt
    python3 parse_delimited_output.py --kind review --input-file path/to/raw.txt
    python3 parse_delimited_output.py --kind plan --input-string "..."

Output: JSON to stdout
{
  "status": "ok" | "fallback_used" | "empty" | "malformed",
  "content": "<extracted text>",
  "strategy": "exact_delimiter" | "normalized_delimiter" | "code_fence" | "whole_body" | "none",
  "completion_signal": "<stripped signal line, including variables like Verdict: PASS/FAIL, or null>",
  "verdict": "PASS" | "FAIL" | null,
  "warnings": ["..."],
  "meta": {
    "kind": "plan",
    "input_length": 1234,
    "content_length": 567
  }
}

Exit codes:
    0 - parsing succeeded (status == ok or fallback_used)
    1 - parsing failed (status == empty or malformed)
    2 - invalid arguments / IO error
"""
```

**参数**：
- `--kind {plan,review,context_snapshot,generic}` — 决定分隔符 token 名称（`PLAN` / `REVIEW` / `CONTEXT_SNAPSHOT` / 用户自定义）
- `--start-token` / `--end-token` — 显式覆盖（`generic` 模式必填）
- `--stdin` — 从 stdin 读
- `--input-file PATH` — 从文件读
- `--input-string STR` — 直接传字符串
- `--min-length N` — 最小内容长度（**默认 200**；SKILL.md 三处调用按 kind 传不同值：context_snapshot=100、plan=300、review=150）
- `--completion-signal STR` — 完成信号锚点（**Round 2 修订 Medium #1**：按"行首前缀"匹配，详见下方"Completion signal 匹配语义"）

**Completion signal 匹配语义（Round 2 修订 Medium #1）**：

helper 把 `--completion-signal` 当作**行首前缀锚点**，匹配规则如下：

| kind | `--completion-signal` 参数 | 匹配方式 | 示例匹配的行 |
|------|---------------------------|---------|------------|
| `plan` | `"PLAN DESIGN COMPLETE"` | 行首字面前缀（整行也接受） | `PLAN DESIGN COMPLETE`、`PLAN DESIGN COMPLETE\n...` |
| `review` | `"REVIEW COMPLETE"` | 行首字面前缀（后接 `\| Verdict: ...`） | `REVIEW COMPLETE \| Verdict: PASS \| Severe: 0 Medium: 0 Optimization: 1` |
| `context_snapshot` | （一般不传，无完成信号模板） | — | — |

实现细节：
- helper 内部把 `--completion-signal` 转成正则 `r'^\s*' + re.escape(signal) + r'\b.*$'`，按 `re.MULTILINE` 匹配整行
- 匹配到的整行（含变量）写入 JSON 的 `completion_signal` 字段，方便 dispatcher debug
- 从 `content` 中剥离该行（在 STRATEGY 4 whole_body 兜底里强制执行；STRATEGY 1-3 一般不会遇到，因为分隔符在前、completion signal 在后）

**Verdict 解析（Round 2 修订 Medium #2）**：

- 仅当 `--kind review` 时，helper 从 `completion_signal` 行（或整个 raw input 末尾，作为兜底）用正则 `r'Verdict:\s*(PASS|FAIL)'` 提取 verdict
- 提取成功：JSON `verdict` 字段为 `"PASS"` 或 `"FAIL"`
- 提取失败：`verdict` 字段为 `null`（dispatcher 可选择走 retry 或显式告警，不退回 LLM 解析）
- 非 review kind：`verdict` 永远为 `null`

**解析策略（按优先级）**：

```
STRATEGY 1: exact_delimiter
  - 精确匹配 <<<{TOKEN}_START>>> 和 <<<{TOKEN}_END>>>
  - 取两者之间内容
  
STRATEGY 2: normalized_delimiter
  - 正则匹配，容忍以下变形：
    - 中英文括号互换: 《《 / 》》/ 「「/ 」」
    - 尖括号数量变化: << / <<< / <<<<
    - 空白: <<< PLAN_START >>> （含空格）
    - 大小写: plan_start / Plan_Start
  - 正则: r'[<《「〖]+\s*_*\s*{TOKEN}_?START\s*_*\s*[>》」〗]+'
  - 当同一 raw input 含多个 kind 的分隔符对（如 PLAN 和 REVIEW 同时出现），仅取 {TOKEN} 指定的那一对
  
STRATEGY 3: code_fence
  - 当 STRATEGY 1/2 失败时，寻找 markdown code fence (``` 或 ~~~)
  - 取最大的 fenced block 作为 content
  - 如果 fence 内还含分隔符，先用 STRATEGY 1 处理
  - 注意嵌套 fence：STRATEGY 1 优先级最高，若 raw 同时有"含分隔符字符串的嵌套 fence"和"裸分隔符对"，exact_delimiter 取裸分隔符对，不会误进 fence
  
STRATEGY 4: whole_body（Round 2 修订 Medium #3）
  - thinking 兼容性分两场景：
    (a) extended thinking（主流场景）：Claude API 已剥离 thinking 内容，主响应文本里
        不含 <thinking> 标签或 antml:thinking 块。_strip_thinking 此时是 no-op，
        但保留作为兜底不影响正确性。
    (b) legacy / 第三方集成痕迹：raw 文本里出现 <thinking>...</thinking> 或
        <antml:thinking>...</antml:thinking>（部分 SDK / 网关会把它塞回主响应）。
        _strip_thinking 用正则 r'<\/?(?:antml:)?thinking>.*?<\/(?:antml:)?thinking>'
        + re.DOTALL 剥离。
  - 剥离完成信号行（按 §"Completion signal 匹配语义"的前缀匹配，剥离整行）
  - 剥离 "ADDITIONAL FILES READ:" 之后的内容（plan-designer 协议明确有）
  - 剩余部分作为 content
  - 仅当剩余部分长度 >= MIN_LEN 时返回
```

每个策略返回前都检查 `len(content.strip()) >= MIN_LEN`。不满足则进入下一策略。全失败则 status = `malformed`（完全无内容）或 `empty`（策略找到内容但太短）。

### 3.4 Key Flows

**修改后的 Phase 1 Plan Design 流程**（Phase 2 / Phase 0.5 类似，仅 `--kind`、`--completion-signal`、`--min-length` 不同）：

```
1. Dispatcher 派发 Plan subagent（prompt 内嵌强化的 Output Format 要求）
2. Subagent 返回 raw_response
3. Dispatcher 把 raw_response 写到带后缀的 raw 文件（Round 2 修订 Medium #6）：
   - 第 1 次：<plan_file>.raw.round<R>
   - retry 后：<plan_file>.raw.round<R>_retry<T>
4. Dispatcher 1:1 copy 以下命令模板（仅替换 <占位符>），调用 helper：
   echo "<raw_response>" | python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
     --kind plan \
     --stdin \
     --completion-signal "PLAN DESIGN COMPLETE" \
     --min-length 300
5. Dispatcher 读取 JSON 输出
6. 分支（纯 JSON 驱动，不再 LLM 解析）:
   - status == ok:
       写 content 到 <plan_file>
       proceed to Phase 2
   - status == fallback_used:
       content 头部加 warning 注释（Round 2 Optimization #4）：
         <!-- WARNING: extracted via fallback strategy: <strategy>
              warnings: <warnings list joined by "; "> -->
       写到 <plan_file>
       通知用户 "plan extracted via fallback strategy: <strategy>"
       proceed to Phase 2
   - status in {empty, malformed} 且 retry_count < MAX_RETRY:
       retry_count += 1
       重新派发 subagent，prompt 末尾追加 "Previous Output Format Issue" 段
       回到 step 2
   - status in {empty, malformed} 且 retry_count >= MAX_RETRY:
       AskUserQuestion: retry / accept fallback / abort（详见 §3.4.1 User Decision Handling）
```

review 协议（Phase 2）的差异：
- `--kind review`、`--completion-signal "REVIEW COMPLETE"`、`--min-length 150`
- 拿到 JSON 后，dispatcher 读 `verdict` 字段（不是 LLM 解析）：
  - `verdict == "PASS"` -> proceed to Phase 3 / early stop
  - `verdict == "FAIL"` -> check round count, 循环或 ask user
  - `verdict == null` -> 当作 format deviation，走 retry 分支

#### 3.4.1 User Decision Handling（Round 2 Optimization #6）

当 retry 用尽、dispatcher 走 AskUserQuestion 时，三个用户选项的语义明确如下：

| 用户选项 | dispatcher 行为 | 文件副作用 |
|---------|----------------|-----------|
| **Retry once more** | retry_count += 1（突破 MAX_RETRY 上限一次），重新派发 subagent | 新增 `<plan_file>.raw.round<R>_retry<T+1>` |
| **Accept the fallback-extracted content**（仅当至少有一次 helper 返回过 `fallback_used` 或当前 raw 经手动检查可用） | 把当前 raw 或最近一次 fallback content 写到 `<plan_file>`，顶部加 `<!-- WARNING: manually accepted after format deviation retry; strategy=...; warnings=... -->` 注释 | `<plan_file>` 写入，状态推进到下一 phase |
| **Abort this planning session** | 状态置为 `aborted`，停止后续动作 | 保留所有 `.raw.round*` 文件供事后 debug |

dispatcher 在 AskUserQuestion 的描述里必须显式列出当前可用选项（如从未 fallback_used 过，则 "Accept the fallback-extracted content" 选项不可选，只提供 retry / abort）。

### 3.5 Error Handling 升级

`SKILL.md` 的 `## Error Handling` 段补一条：

```
- **Subagent output format deviation**: If the subagent returns successfully but
  the output cannot be parsed via the delimiter protocol (detected via
  parse_delimited_output.py returning status "empty" or "malformed"), retry once
  with an enhanced prompt. If retry still fails, save the raw output to
  <plan_file>.raw.round<R>[_retry<T>] and use AskUserQuestion to let the user
  decide (retry / accept raw / abort — see User Decision Handling subsection).
  Never silently hang on unparseable output.
```

---

## 4. Implementation Steps

### Phase 1: 新增 Python helper 与单测
- [ ] **Step 1.1**：创建 `plugin/shared/scripts/parse_delimited_output.py`，按 §3.3 接口实现：
  - argparse（参数同 §3.3）
  - 4 个策略函数：`_strategy_exact`、`_strategy_normalized`、`_strategy_code_fence`、`_strategy_whole_body`
  - 清洗函数：`_strip_thinking`（兼容 legacy `<thinking>` 和 `<antml:thinking>`）、`_strip_completion_signal`（行首前缀匹配）、`_strip_additional_files_read`、`_extract_verdict`（仅 review kind）
  - JSON 输出含 `status` / `content` / `strategy` / `completion_signal` / `verdict` / `warnings` / `meta`
  - exit code 0/1/2，全程 stdlib
  - main 函数用 try/except 包住
- [ ] **Step 1.2**：创建 `plugin/shared/scripts/test_parse_delimited_output.py`，覆盖 §3.2 Q6 全部用例（**17 个**，含 Round 2 新增的 5 个）。测试文件必须自带入口 `if __name__ == '__main__': unittest.main()`，可 `python3 path/to/test.py` 直接运行；不引入 pytest（Round 2 Medium #8）
- [ ] **Step 1.3**：本地运行测试确保全部通过

**Acceptance criteria**：
- helper 可独立调用，17 个测试用例通过
- `--kind plan/review/context_snapshot` 三种 token 切换正确
- `--kind review` 时 verdict 字段正确从 `Verdict: PASS/FAIL` 提取
- `--completion-signal` 行首前缀匹配覆盖 review 的 `REVIEW COMPLETE | Verdict: FAIL | ...`
- 退出码 0/1/2 符合规范
- 测试可 `python3 path/to/test.py` 直接运行，不依赖 pytest

### Phase 2: 修改 ghs-plan SKILL.md
- [ ] **Step 2.1**：Phase 0.5 Path B（line 142 附近）Handling 改成调用 helper（`--kind context_snapshot --min-length 100`）+ retry/fallback 分支。**明确指令**："You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT parse the subagent output yourself."
- [ ] **Step 2.2**：Phase 1（line 215-217）Handling Designer Feedback 改成调用 helper（`--kind plan --completion-signal "PLAN DESIGN COMPLETE" --min-length 300`）的完整分支流程。同样附 1:1 copy 指令
- [ ] **Step 2.3**：Phase 2（line 286）Handling Reviewer Feedback 改成调用 helper（`--kind review --completion-signal "REVIEW COMPLETE" --min-length 150`）；**verdict 来自 JSON 的 `verdict` 字段，不再 LLM 解析 completion signal**
- [ ] **Step 2.4**：`## Error Handling` 段（line 347-351）追加 §3.5 的 "Subagent output format deviation" 条目
- [ ] **Step 2.5**：Designer / Reviewer Instruction Template 里强化 Output Format 要求，加上 "do NOT wrap in code fence / do NOT translate delimiters" 的反例说明
- [ ] **Step 2.6**（Round 2 Optimization #6）：在 `## Error Handling` 段后新增 `## User Decision Handling` 子段，写清三选项（retry / accept fallback / abort）各自写什么文件、proceed 到哪个 phase、副作用

### Phase 3: 同步 plan-designer.md 与 plan-reviewer.md
- [ ] **Step 3.1**：在 `plugin/shared/references/plan-designer.md` 末尾 `## Completion Signal` 段前补 `## Output Format Requirements`
- [ ] **Step 3.2**：在 `plugin/shared/references/plan-reviewer.md` 的 `## Review Report Format` 段追加同样的 format requirements 子段

### Phase 4: 手动验证
- [ ] **Step 4.1**：手动构造一个偏离格式的 raw 输出文件（如用 code fence 包裹），跑 helper 验证 status = fallback_used、warnings 字段非空
- [ ] **Step 4.2**：模拟 dispatcher 行为——在 Claude 主对话中调一次 `/ghs:plan`，观察所有 Handling 是否按新流程走
- [ ] **Step 4.3**：确认 retry 分支：把 helper 临时改成永远返回 `malformed`，确认 dispatcher 走 retry → ask user 流程而非 hang
- [ ] **Step 4.4**（Round 2 Medium #4 新增）：**故意触发偏离场景验证 LLM 真调 helper**——在测试用 prompt 里把分隔符协议弱化（如只说 "output a plan"），观察 dispatcher 是否仍 1:1 调用 helper 而非自己解析

---

## 5. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation Strategy |
|------|-----------|--------|---------------------|
| helper 的 normalized_delimiter 正则不够宽容，漏掉某种新变形 | 中 | 中 | 用单测覆盖已知变形；helper 返回 `warnings` 字段记录用了哪个 strategy |
| whole_body fallback 误把 thinking 段或 completion signal 当 plan 内容 | 中 | 高 | `_strip_thinking`（兼容 legacy + antml）和 `_strip_completion_signal`（行首前缀匹配）在 whole_body 策略里强制执行；单测覆盖 thinking_only / completion_signal_only / review_with_verdict_pass |
| **dispatcher（LLM）忘记调用 helper，仍按旧 prose 方式解析**（Round 2 Medium #4 加强） | 中 | 高 | SKILL.md 里把 Handling 写成明确的 bash 命令模板，加粗 "MUST 1:1 copy"，声明失败后果；Phase 4 Step 4.4 专项验证 |
| **helper 自身 bug 把错误内容当 plan 写入**（Round 2 Optimization #4） | 低 | 高 | fallback_used 写文件时顶部加 `<!-- WARNING: ... -->`；reviewer 读 plan 时第一眼看到 warning |
| retry 也失败时用户不在场，AskUserQuestion 永久阻塞 | 低 | 中 | 与现有 "User not responding" 同类问题，已在 Error Handling 覆盖 |
| helper 调用本身失败（Python 异常、stdin 管道问题） | 低 | 中 | try/except 包住 main，异常返回 exit 2 + stderr 错误；dispatcher 看到 exit 2 当作 format deviation |
| **verdict 提取失败导致 dispatcher 误判 PASS/FAIL**（Round 2 Medium #2） | 低 | 高 | helper 显式输出 `verdict` 字段；提取失败时返回 `null`；dispatcher 看到 null 走 retry，绝不退回 LLM 解析 |
| 引入 helper 增加 dispatcher 工作复杂度 | 低 | 中 | helper 调用是单条 bash 命令 + 读 JSON，比 prose 解析更确定 |
| `.raw.round*` 文件污染 `.ghs/plans/` 目录 | 低 | 低 | 临时性调试文件；可在 Phase 4 finalize 后清理；按 round/retry 后缀命名避免覆盖历史 |

---

## 6. Testing Strategy

### 6.1 单元测试（确定性部分）
`test_parse_delimited_output.py` 覆盖 §3.2 Q6 的 17 个用例，验证 4 个策略 + 清洗函数 + verdict 提取 + completion signal 前缀匹配。测试自带 `if __name__ == '__main__': unittest.main()` 入口，纯 stdlib，可 `python3 path/to/test.py` 直接运行，不引入 pytest。

### 6.2 集成验证（LLM 行为部分）
由于 LLM 偏离格式是偶发的，无法在 CI 复现。验证手段：
- 单测保证解析逻辑正确
- SKILL.md 的命令模板（含 1:1 copy 强制指令）保证 dispatcher 一定会调用 helper
- 实际使用中遇到 hang 时，检查 `<plan_file>.raw.round*` 是否存在
- Phase 4 Step 4.4 的弱化 prompt 测试，验证 LLM 在指令边界条件下仍调 helper

### 6.3 回归保护
修改 SKILL.md 后，跑一次完整 `/ghs:plan` 流程（用任意简单需求），确认：
- 正常场景（subagent 按格式输出）走 status == ok 分支
- review 场景 verdict 字段正确返回 PASS/FAIL
- helper 调用命令在 SKILL.md 中可被 LLM 正确执行
- 写出的 `<plan_file>` 内容与原协议解析结果一致（无 regression）
- `.raw.round*` 文件在 retry 时正确累积，不互相覆盖
