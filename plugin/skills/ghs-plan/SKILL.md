---
name: ghs:plan
description: "Produce an executable technical plan through a contract-driven pipeline: the dispatcher freezes a scope contract with the user, a designer subagent writes the plan body against it, a reviewer enforces contract mapping, and approval materializes tasks into features automatically. Use whenever the user asks to create a technical plan, design a solution, or think through how to implement something before coding."
argument-hint: "[requirement description]"
---

# Technical Plan Generation

Produce an executable technical plan through multi-agent collaboration. The dispatcher (main conversation) coordinates a plan designer (Plan subagent) and a plan reviewer (architect subagent), iterating via review-revise cycles until the plan is ready.

## Flow Overview

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

## Prerequisites

- Project directory must be initialized (`.ghs/` directory exists). If not, tell the user to run `/ghs:init` first.
- User must provide a requirement description. If not provided, ask via AskUserQuestion.

## Core Concepts

### Three Roles

| Role | Implementation | Responsibility |
|------|---------------|----------------|
| **Dispatcher** | Main conversation (you) | Orchestrate flow, manage state, communicate with user |
| **Contract** | Dispatcher authors, user confirms | Scope truth: six-piece contract header frozen at kickoff; body maps to it |
| **Plan Designer** | Plan subagent | Design the plan body against the frozen contract (Current State / Design / Assumptions / Risks + task cards) |
| **Plan Reviewer** | general-purpose subagent | Enforce contract mapping, decision discipline, anchor completeness |

### File Conventions

All intermediate files are stored under `.ghs/plans/`:

| File | Description |
|------|-------------|
| `.ghs/plans/{date}-{slug}.md` | Technical plan (produced by designer) |
| `.ghs/plans/{date}-{slug}-context.md` | Project context snapshot (pre-extracted architectural summary) |
| `.ghs/plans/{date}-{slug}-review.md` | Review report (produced by reviewer) |
| `.ghs/plans/{date}-{slug}-status.json` | Status file (maintained by dispatcher) |

Where `{date}` is `YYYY-MM-DD` and `{slug}` is a short English descriptor of the requirement topic.

The plan file is created by the dispatcher in Phase 2 as the contract header; the designer only ever produces the body, which the dispatcher concatenates after the header — the contract never passes through the designer's hands.

After final approval, the plan is copied to `docs/ghs/plans/{date}-{slug}.md`.

### State Tracking

State is tracked via `.ghs/plans/{date}-{slug}-status.json`:

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

**Field descriptions**:
- `status` — six-state enum: `designing | reviewing | revising | pending_approval | approved | aborted`. The old `rejected` value is removed.
- `lane` (`"light" | "full"`) — written by the Phase 0 entry triage. Until the triage behavior lands, every session is initialized with `"lane": "full"`.
- `retry_counts` (object with keys `plan`, `review`, `context_snapshot`) — each subagent kind has its own independent retry counter, persisted in this file, reset to `0` on a successful parse of that kind. Per-kind cap: `MAX_RETRY = 1`.
- `reject_count` (int, default `0`) — cumulative count of Phase 5 approval rejections in this session. When `reject_count >= 3`, stop cycling and suggest a contract replay (back to Phase 2) instead of another revision.
- `final_fix_pending` (bool, default `false`) — set to `true` when a targeted re-review still leaves residual issues. While it is `true`, exactly one targeted revision is allowed and no further re-review runs; the flag is cleared when the session enters `pending_approval` or `aborted`.
- `accepted_with_fail` (bool, default `false`) — semantics narrowed to: residual issues remained after the (final) re-review AND the user explicitly accepted the plan anyway. After-the-fact audit via `grep '"accepted_with_fail": true' .ghs/plans/*-status.json` still reveals all plans that passed with unfixed issues. The `status` field itself remains `"approved"` (this is an independent flag, not a new status enum value).
- `keep_raw_on_success` (bool, default `false`): When set to `true`, the dispatcher additionally writes the subagent response to `<file>.raw` (overwriting) even on successful parse, for post-mortem debugging. Use only for hard-to-debug sessions where the user suspects logic errors in the plan despite it passing format validation. Normal sessions keep this `false` to keep the main directory clean.

Contract freeze is not a state-machine state — the plan document itself is the truth.

### Issue Severity Levels (Reviewer Must Use)

| Level | Definition | Examples |
|-------|-----------|----------|
| **Severe** | Would cause bugs, or the plan itself is incorrect | Unhandled race conditions, wrong security assumptions, logic errors |
| **Medium** | Implementation path issues, poor design | Unreasonable abstraction levels, missing error handling, performance pitfalls |
| **Unwarranted** | Plan content that maps to no contract entry | A section with no Goal/Decision/Open-Space/Constraint sponsor |
| **Optimization** | Does not block plan execution, nice-to-have | Naming improvements, optional caching strategies, better observability |

Pass criteria: zero Unwarranted, zero Severe, zero Medium issues.

---

## Detailed Flow

### Phase 0: Initialization

1. **Resolve project directory**:
   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
   ```
   Store output as `PROJECT_DIR`.

2. **Confirm requirement**: If the user has not provided a requirement description, use AskUserQuestion to ask: "Please describe the requirement you need a technical plan for." Ask only one question at a time.

3. **Create working directory** (creates both the main directory and the `.tmp/` scratch subdirectory in one shot, so Handling step 2's Write to `.tmp/<x>.raw` never hits "No such file or directory"):
   ```bash
   mkdir -p ${PROJECT_DIR}/.ghs/plans ${PROJECT_DIR}/.ghs/plans/.tmp
   ```

4. **Generate file identifier**: Create `{date}-{slug}` based on current date and the requirement topic.

5. **Initialize status file**: Write the status JSON exactly per the schema in State Tracking, with "status": "designing" and "lane": "full".

### Phase 1: Context Snapshot Extraction

Extract a condensed context snapshot of the project. This snapshot is shared by all subsequent subagents (designer and reviewer) across all rounds, eliminating redundant codebase exploration.

**Core principle**: The dispatcher NEVER calls `codegraph_files` or `codegraph_explore` directly in the main conversation — raw codegraph results are large and pollute the dispatcher's context permanently. All codegraph calls happen inside a Context Subagent whose context is discarded after it returns. The only codegraph call allowed in the main conversation is a single `codegraph_status` probe during Detection.

**Detection** (dispatcher, before spawning subagent):
1. Check if `${PROJECT_DIR}/.codegraph/` directory exists.
2. If yes, call `codegraph_status(projectPath="<PROJECT_DIR>")` ONCE to confirm the index is usable. This is the only codegraph call allowed in the main conversation (~1KB result).
3. Record `CODEGRAPH_AVAILABLE = <true | false>` and pass it into the Context Subagent prompt.

**Spawn a Context Subagent to extract the snapshot** — both the `subagent_type` AND the prompt template depend on `CODEGRAPH_AVAILABLE`:

- If `CODEGRAPH_AVAILABLE = true`: spawn `general-purpose` with `PROMPT_TEMPLATE_CODEGRAPH`. Verified to inherit project-scoped codegraph MCP.
- If `CODEGRAPH_AVAILABLE = false`: spawn `Explore` with `PROMPT_TEMPLATE_GREP`. read-only search agent — grep/glob/read fallback, no Write/Edit permission needed. The prompt explicitly forbids any `codegraph_*` call.

```json
{
  "subagent_type": "<general-purpose | Explore>",
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

**Handling**:

1. **Hold the subagent response in memory for the duration of parse.** Do NOT persist it to a post-mortem `.raw` file in the main `.ghs/plans/` directory on the happy path — only the `.tmp/` scratch file in step 2 exists transiently and is deleted in step 4. This is the key distinction from the old behavior: the main `.ghs/plans/` directory stays clean of raw files on success, but the response is briefly on disk under `.tmp/` for the duration of the parser call (which `--input-file` requires).

2. Write the response verbatim to a **temporary file** for parser input (this is a scratch file under `.tmp/`, not a post-mortem raw in the main directory):

   > **Copy this command verbatim, only replacing the `<placeholders>`.**

   Path: `<PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.context.raw` (the `.tmp/` subdirectory is created once in Phase 0 init step 3).

3. Invoke the parser helper via `--input-file` (shell never sees the response content — zero injection surface):

   > **You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT parse the subagent output yourself — the helper is the single source of truth for delimiter extraction.**

   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
     --kind context_snapshot \
     --input-file <PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.context.raw \
     --min-length 100
   ```
   Note: for context_snapshot, **do NOT pass `--completion-signal`** — there is no signal line for context snapshots, so the flag is omitted entirely (parser uses `default=None`).

4. Read the JSON object from stdout. **Delete the temporary file from step 2** (whether parse succeeded or failed — the temp file's job is done; persistence decisions are separate). Then branch on `status`:

   - **`ok`** or **`fallback_used`**:
     - Write `content` to the target file (`<context_file>`). For `fallback_used`, prepend the warning comment `<!-- WARNING: extracted via fallback strategy: <strategy>; warnings: <warnings joined by "; "> -->`.
     - **No post-mortem raw file is created on the happy path** (unless `keep_raw_on_success: true` in status.json — see [## State Tracking](#state-tracking)). Add `context_file` to the status JSON. Notify the user (as plain text in your response — this is informational, not a decision point, so do NOT use AskUserQuestion) if fallback was used. Proceed to Phase 2.
   - **`empty`** / **`malformed`** with `retry_counts.context_snapshot < MAX_RETRY (=1)`:
     1. **Now persist the response to a post-mortem raw file in the main directory** — this is the only time a `.raw` file lands in the main `.ghs/plans/` directory:
        - Path: `<PROJECT_DIR>/.ghs/plans/<context_file>.raw` for the first attempt, `<PROJECT_DIR>/.ghs/plans/<context_file>.raw.retry<T>` for retry T.
     2. Increment `retry_counts.context_snapshot`, re-dispatch the Context Subagent with the original prompt plus the [Format Recovery](#format-recovery) appendix.

       Note: keep the SAME `subagent_type` and the SAME prompt template
       (`PROMPT_TEMPLATE_CODEGRAPH` or `PROMPT_TEMPLATE_GREP`) as the first attempt —
       do NOT switch the subagent type or prompt template during retry. Keep
       `general-purpose`+`PROMPT_TEMPLATE_CODEGRAPH` or `Explore`+`PROMPT_TEMPLATE_GREP`
       consistent with the first attempt.
     3. Return to step 1 with the new response (use `<context_file>.raw.retry<T>` if it fails again).
   - **`empty`** / **`malformed`** with `retry_counts.context_snapshot >= MAX_RETRY`: Post-mortem raw is already saved at `<context_file>.raw[.retry<T>]`. Use AskUserQuestion per [## User Decision Handling](#user-decision-handling).

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

### Phase 3: Design

> Phase 3 runs on initial design; targeted revision after a FAIL is an inner loop of Phase 4 and re-dispatches this phase with findings.

Spawn a Plan subagent to design or revise the plan:

> **Note**: Plan subagents do not have file write permissions. The subagent outputs the plan content in its response; the dispatcher writes it to disk.

```json
{
  "subagent_type": "Plan",
  "description": "Design technical plan body",
  "prompt": "<designer instructions>"
}
```

**Designer Instruction Template**:

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

**Handling Designer Feedback**:

1. **Hold the subagent response in memory for the duration of parse.** Do NOT persist it to a post-mortem `.raw` file in the main `.ghs/plans/` directory on the happy path — only the `.tmp/` scratch file in step 3 exists transiently and is deleted in step 5. This is the key distinction from the old behavior: the main `.ghs/plans/` directory stays clean of raw files on success, but the response is briefly on disk under `.tmp/` for the duration of the parser call (which `--input-file` requires).

2. **SPLIT_SUGGESTED pre-check**: If the response contains a line matching ^SPLIT_SUGGESTED:\s*(.+)$, use AskUserQuestion to let the user decide: 拆分（当前 plan 置 status: "aborted"，把建议的子 plan 划分告知用户，各自后续走完整流程）/ 合并（附用户理由，重派 designer，回到本 Phase 步骤 1）。

3. Write the response verbatim to a **temporary file** for parser input (this is a scratch file under `.tmp/`, not a post-mortem raw in the main directory):

   > **Copy this command verbatim, only replacing the `<placeholders>`.**

   Path: `<PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.plan.raw` (the `.tmp/` subdirectory is created once in Phase 0 init step 3).

4. Invoke the parser helper via `--input-file` (shell never sees the response content — zero injection surface):

   > **You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT parse the subagent output yourself — the helper is the single source of truth for delimiter extraction.**

   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
     --kind plan \
     --input-file <PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.plan.raw \
     --completion-signal "PLAN DESIGN COMPLETE" \
     --min-length 300
   ```

5. Read the JSON object from stdout. **Delete the temporary file from step 3** (whether parse succeeded or failed — the temp file's job is done; persistence decisions are separate). Then branch on `status`:

   - **`ok`** or **`fallback_used`**:
     - `ok`/`fallback_used` 时 **dispatcher 以"契约头 + 正文"拼接覆盖写** `{plan_file}`：Read 现有文件得契约头（Phase 2 冻结内容，物理不经 designer），正文取解析 `content`；若正文以 `# {Plan Title}` 或重复契约头开头，剥离至 `## Current State` 起。`fallback_used` 时警告注释 prepend 到正文前、契约头之后。
     - **No post-mortem raw file is created on the happy path** (unless `keep_raw_on_success: true` in status.json — see [## State Tracking](#state-tracking)). Update status to `reviewing`. Notify the user (as plain text in your response — this is informational, not a decision point, so do NOT use AskUserQuestion) if fallback was used. Proceed to Phase 4.
   - **`empty`** / **`malformed`** with `retry_counts.plan < MAX_RETRY (=1)`:
     1. **Now persist the response to a post-mortem raw file in the main directory** — this is the only time a `.raw` file lands in the main `.ghs/plans/` directory:
        - Path: `<PROJECT_DIR>/.ghs/plans/<plan_file>.raw` for the first attempt, `<PROJECT_DIR>/.ghs/plans/<plan_file>.raw.retry<T>` for retry T.
     2. Increment `retry_counts.plan`, re-dispatch the Plan subagent with the original prompt plus the [Format Recovery](#format-recovery) appendix for plan.
     3. Return to step 1 with the new response (use `<plan_file>.raw.retry<T>` if it fails again).
   - **`empty`** / **`malformed`** with `retry_counts.plan >= MAX_RETRY`: Post-mortem raw is already saved at `<plan_file>.raw[.retry<T>]`. Use AskUserQuestion per [## User Decision Handling](#user-decision-handling).

### Phase 4: Review

Update status to `reviewing` and spawn the reviewer subagent:

```json
{
  "subagent_type": "general-purpose",
  "description": "Review technical plan round N",
  "prompt": "<reviewer instructions>"
}
```

**Reviewer Instruction Template**:

```
You are a senior architect responsible for reviewing technical plans. Critically examine the following plan.

## Review Target
- Plan file: <PROJECT_DIR>/.ghs/plans/<plan_file>
- Context snapshot: <PROJECT_DIR>/.ghs/plans/<context_file>
- Project directory: <PROJECT_DIR>

## Review Requirements
1. Read the context snapshot to understand the existing architecture
2. Read the plan file
3. If you need to verify specific implementation details against actual code, read those files from the project
4. Check each section of the plan systematically
5. Identify all issues and label them with severity:
   - **Severe**: Would cause bugs, or the plan itself is incorrect
   - **Medium**: Implementation path issues, poor design
   - **Optimization**: Does not block execution, nice-to-have

## Output Format Requirements (CRITICAL)
The dispatcher extracts your review by searching for the literal delimiters `<<<REVIEW_START>>>` and `<<<REVIEW_END>>>`, and reads the verdict from the line beginning with `REVIEW COMPLETE`. If you deviate, the dispatcher must invoke a fallback parser, retry, or ask the user — wasting a round and slowing the planning loop. You MUST:
1. Output the delimiters EXACTLY as written: `<<<REVIEW_START>>>` on its own line, `<<<REVIEW_END>>>` on its own line.
2. Put ALL review report content between them.
3. **Do NOT wrap the delimiters or the content in a code fence** (no ` ``` ` markers around them).
4. **Do NOT translate, transliterate, or modify the delimiter strings** — no `《《REVIEW_START》》`, no `<<REVIEW_START>>`, no `<<< REVIEW_START >>>`.
5. End with the literal completion signal `REVIEW COMPLETE | Verdict: PASS|FAIL | Severe: X Medium: Y Optimization: Z` on its own line — the dispatcher reads the verdict from this line via a parser; if it's missing or malformed, the review will be retried.
6. Use the literal ASCII characters `<`, `>`, `_`, `|`.

### Correct example
<<<REVIEW_START>>>
... review report ...
<<<REVIEW_END>>>
REVIEW COMPLETE | Verdict: PASS | Severe: 0 Medium: 0 Optimization: 1

### Incorrect examples (DO NOT DO THESE)
- Wrapping in a code fence, translated punctuation, missing/extra brackets — same problems as the designer case.
- Completion signal without `Verdict: PASS|FAIL` — the dispatcher cannot determine the verdict and will retry.

## Review Report Format
Output the FULL review report in your response, delimited by:
<<<REVIEW_START>>>
...review report content here...
<<<REVIEW_END>>>

Do NOT attempt to write any files.

The review report must include:
- Plan summary (one sentence)
- Issue list (each item: severity, location/section, description, suggested fix direction)
- Conclusion: PASS (only optimization items) / FAIL (has severe or medium issues)

## Review Criteria
- Does the plan fully cover the requirement?
- Are technology choices reasonable?
- Are implementation steps executable without ambiguity?
- Are edge cases and error handling considered?
- Is the plan compatible with the existing architecture?
- Are there security risks or performance issues?

## Reference
Read ${CLAUDE_PLUGIN_ROOT}/shared/references/plan-reviewer.md for detailed review standards, severity definitions, and review report format.

## Context Reset
- Disregard any context from previous conversations
- Read all necessary files fresh from the filesystem
- This is an isolated task

## Completion Signal
When done, output: "REVIEW COMPLETE | Verdict: PASS/FAIL | Severe: X Medium: Y Optimization: Z"
```

**Handling Reviewer Feedback**:

1. **Hold the subagent response in memory for the duration of parse.** Do NOT persist it to a post-mortem `.raw` file in the main `.ghs/plans/` directory on the happy path — only the `.tmp/` scratch file in step 3 exists transiently and is deleted in step 5. This is the key distinction from the old behavior: the main `.ghs/plans/` directory stays clean of raw files on success, but the response is briefly on disk under `.tmp/` for the duration of the parser call (which `--input-file` requires).

2. **Reviewer question pre-check**: If the response contains a line matching `^QUESTION:\s*(.+)$`, treat it as a reviewer question — use AskUserQuestion to relay the question to the user, then re-dispatch the reviewer with the original prompt plus the user's answer appended. **No temporary file written** (the question response is short and not persisted). Skip the remaining steps.

3. Write the response verbatim to a **temporary file** for parser input (this is a scratch file under `.tmp/`, not a post-mortem raw in the main directory):

   > **Copy this command verbatim, only replacing the `<placeholders>`.**

   Path: `<PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.review.raw` (the `.tmp/` subdirectory is created once in Phase 0 init step 3).

4. Invoke the parser helper via `--input-file` (shell never sees the response content — zero injection surface):

   > **You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT parse the subagent output yourself — the helper is the single source of truth for delimiter extraction AND for the verdict.**

   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
     --kind review \
     --input-file <PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.review.raw \
     --completion-signal "REVIEW COMPLETE" \
     --min-length 150
   ```

5. Read the JSON object from stdout. **The verdict comes from the JSON `verdict` field — do NOT re-parse the completion signal text yourself.** **Delete the temporary file from step 3** (whether parse succeeded or failed — the temp file's job is done; persistence decisions are separate). Then branch on `status` AND `verdict`:

   - **`ok` or `fallback_used`** with `verdict == "PASS"`:
     - If `status == "fallback_used"`, write `content` to `<review_file>` with a leading warning comment: `<!-- WARNING: extracted via fallback strategy: <strategy>; warnings: <warnings joined by "; "> -->`. Otherwise write `content` directly.
     - **No post-mortem raw file is created on the happy path** (unless `keep_raw_on_success: true` in status.json — see [## State Tracking](#state-tracking)).
     - **Early stop**: If `round == 1`, proceed directly to Phase 5 — no need for additional rounds.
     - Update status to `pending_approval`. Proceed to Phase 5.
   - **`ok` or `fallback_used`** with `verdict == "FAIL"`:
     - Write `content` to `<review_file>` (with the warning comment if `fallback_used`).
     - **No post-mortem raw file is created on the happy path** (unless `keep_raw_on_success: true` in status.json — see [## State Tracking](#state-tracking)).
     - Check round count:
       - `round < max_rounds` -> Update status to `revising`, increment round, go back to Phase 3.
       - `round >= max_rounds` AND `max_rounds_breaches < MAX_BREACHES` -> Max round limit reached. Use AskUserQuestion to present three options (symmetric with Phase 5 reject @ max_rounds), with the Approval Summary block as the question body. This is the FAIL scenario of the block defined in [Approval Summary Assembly](#approval-summary-assembly), with these deviations from the standard template:
         - **Header line**: instead of `Plan ready for approval (...)`, show `Plan review FAILED (Round {round}/{max_rounds}, breaches {max_rounds_breaches}/{MAX_BREACHES})` — the block must not claim readiness while listing blocking issues.
         - **Review Result section**: instead of the PASS stats line, show the FAIL stats line `Verdict: FAIL | Severe: {X} Medium: {Y}` followed by the titles of the Severe/Medium issues that triggered the FAIL, one per line, up to 6 titles (keep each title to one line); if there are more, truncate and append the line `... {N} more issue(s) — see Review file below`.
         - **Files section**: unchanged — both the Plan and Review file paths stay; the Review path lets the user dig into the full report.
         - **Closing line**: replace the closing guarantee/question with `The latest review found Severe/Medium issues. Continue revising, accept the plan as-is, or abort?`
         - **Line budget**: the total block budget is relaxed to ≤ 40 lines for this scenario (instead of the standard 34), accommodating the issue-title lines.
         1. **Continue revising anyway** (one-shot breach): Increment `max_rounds_breaches`, increment `round`, go back to Phase 3. Attach the Approval Summary block (per the deviations above) so the user understands what triggered the FAIL. (In other words: attach the Approval Summary block instead of dumping the full review report.)
         2. **Accept the current plan despite the FAIL**: Proceed to Phase 6 with the current plan file (the user takes responsibility for the unfixed issues). Add a marker line at the top of the plan file: `<!-- WARNING: accepted with unfixed issues (round <R>, breaches=<B>): Severe=<X> Medium=<Y> -->` (see Phase 6 Finalization for handling).
         3. **Abort**: Set status to `aborted`, stop.
       - `round >= max_rounds` AND `max_rounds_breaches >= MAX_BREACHES` -> Hard cap reached. Use AskUserQuestion to present only two options (continue breach not available), attaching the same FAIL-scenario Approval Summary block as above (failed header + FAIL stats + up to 6 issue titles, total ≤ 40 lines) plus this notice line appended after the Files section: `Hard cap reached: no further revision rounds available` (same wording as the Phase 5 hard-cap menu):
         1. **Accept the current plan despite the FAIL**: Same marker as above (see Phase 6 Finalization).
         2. **Abort**.
   - **`ok` or `fallback_used`** with `verdict == null`: Treat as format deviation — the reviewer's signal line did not contain `Verdict: PASS|FAIL`. Fall through to the retry path below.
   - **`empty` or `malformed`** (or `verdict == null`) with `retry_counts.review < MAX_RETRY (=1)`:
     1. **Now persist the response to a post-mortem raw file in the main directory** — this is the only time a `.raw` file lands in the main `.ghs/plans/` directory:
        - Path: `<PROJECT_DIR>/.ghs/plans/<review_file>.raw` for the first attempt, `<PROJECT_DIR>/.ghs/plans/<review_file>.raw.retry<T>` for retry T.
     2. Increment `retry_counts.review`, re-dispatch the reviewer with the original prompt plus the [Format Recovery](#format-recovery) appendix for review.
     3. Return to step 1 with the new response (use `<review_file>.raw.retry<T>` if it fails again).
   - **`empty` or `malformed`** (or `verdict == null`) with `retry_counts.review >= MAX_RETRY`: Post-mortem raw is already saved at `<review_file>.raw[.retry<T>]`. Use AskUserQuestion per [## User Decision Handling](#user-decision-handling).

#### Context Snapshot Update

After each design-review round, if the designer or reviewer read additional files beyond the context snapshot, update the snapshot to include the newly discovered context. This ensures subsequent rounds benefit from expanded knowledge.

1. Check if the designer output contains `ADDITIONAL FILES READ: ...`
2. If so, append a `## Supplementary Context` section to the context snapshot file with summaries of the additional files
3. Future rounds will automatically include this expanded context

### Phase 5: Approval

After the plan passes review, assemble an Approval Summary block (see below) and use AskUserQuestion to request user confirmation, with the summary block as the question body. This also applies to the early-stop path (round == 1 with PASS, entered directly from Phase 4).

#### Approval Summary Assembly

Before asking, read small fragments of the plan/review/status files from disk and assemble a plain-text summary block. Extraction rules:

| Block section | Source | How to extract |
|---|---|---|
| Plan Summary | Review file's plan-summary section (starting point) + plan file goal/core-approach sections (expansion material) | Read the review file (usually < 100 lines, read it whole) and locate its plan-summary section: the reviewer writes free-form prose, so the heading may be `## Plan Summary`, `## 方案摘要`, or another equivalent summary-like heading (a short section near the top summarizing the plan). Do NOT depend on one literal heading. Take the first non-empty paragraph under it as the starting point. Then read the plan file's goal/core-approach sections per the read budget below. Synthesize both into a 2-4 sentence summary (~50-150 words): the first sentence states the goal (what problem the plan solves), the next 1-3 sentences state what it concretely does (which files change, what mechanism/module is introduced, which scenarios are covered) — do NOT expand implementation details. If either source is missing, generate from what is available; if all are missing, write `N/A`. |
| Key Technical Decisions | Plan file `## Plan Design` section (including its `###` subsections — that is where the plan's own decisions live; `## Current State Analysis` describes the pre-existing codebase and may be skimmed only as optional context) | Grep `^## ` to locate section headings, then read those sections in segments (include `###` subsections of Plan Design). Pick decision-like points about what the PLAN chooses (technology choices, architecture trade-offs, interface contracts) — not descriptions of existing architecture — and rewrite each as a one-line short sentence, at most 5. |
| Review stats | 1. The parser JSON `completion_signal` field from the most recent review parse (Phase 4 -> Phase 5 happens in the same conversation turn, so this is normally in memory). 2. If unavailable: an issue-count section in the review file (`## Issue Summary` / `## 问题清单` or equivalent). | Do NOT infer counts from the JSON `verdict` field — `verdict` only holds PASS/FAIL/null, no counts. The `completion_signal` field holds the full signal line `REVIEW COMPLETE \| Verdict: ... \| Severe: X Medium: Y Optimization: Z`; parse the counts from it. Note: the written review file does NOT contain the signal line (the parser strips it before the dispatcher writes `content`), so do not look for it there. |
| Round/budget status | status JSON for `{round}`/`{max_rounds}`/`{max_rounds_breaches}`; the `{MAX_BREACHES}` template placeholder is NOT a status field — it is the SKILL.md constant (default `2`, defined in [## Format Recovery](#format-recovery) → `**Constants**`) | Fill the template directly from the values above. |

**Read budget constraints** (to prevent context bloat):

- The review file is usually < 100 lines — read it whole; every review-sourced field comes from this single read.
- For the plan file, read only the sections named in the table above (goal/core-approach and design sections), located via grep `^## ` and read in segments of ≤ 60 lines each. The summary and the decisions share these reads; do NOT re-read. Do NOT bulk-read the whole plan file into the main conversation.
- If any field cannot be extracted, write `N/A` and still ask the question — the summary is best-effort and must not introduce a new failure path.

**Line budget** (total block ≤ 34 lines): summary section ≤ 4 lines; decisions ≤ 5 lines; Review Result ≤ 2 lines; Files 2 lines.

**Summary block template** (plain text — no `##`/`**` Markdown syntax in the output):

```
Plan ready for approval (Round {round}/{max_rounds}, breaches {max_rounds_breaches}/{MAX_BREACHES})

=== Plan Summary ===
{plan summary — per extraction rules above}

=== Key Technical Decisions ===
- {decision 1}
- {decision 2}

=== Review Result ===
Verdict: PASS | Severe: {X} Medium: {Y} Optimization: {Z}
{optimization titles line — only if Z > 0}

=== Files ===
- Plan: <PROJECT_DIR>/.ghs/plans/{plan_file}
- Review: <PROJECT_DIR>/.ghs/plans/{review_file}

The plan has completed {round} rounds of review with no severe or medium issues remaining (verdict from the latest review: PASS).
Do you approve this plan?
```

- **User approves** -> Proceed to Phase 6
- **User rejects**:
  - If `round < max_rounds`: Ask for specific revision requests (no Approval Summary block needed — the user just reviewed it), update status to `revising`, increment `round`, go back to Phase 3.
  - If `round >= max_rounds` AND `max_rounds_breaches < MAX_BREACHES` (default `MAX_BREACHES = 2`, defined in [## Format Recovery](#format-recovery) → `**Constants**`): Max round limit reached. Use AskUserQuestion to present three options, since continuing would exceed the configured max_rounds. Do NOT re-assemble the full Approval Summary block (the user just reviewed and rejected it) — instead use a one-line state recap as the question body: `Round {round}/{max_rounds}, breaches {max_rounds_breaches}/{MAX_BREACHES}, latest review: PASS` followed by the notice line `Continuing would exceed max_rounds budget; {MAX_BREACHES - max_rounds_breaches} breach(es) remaining` and the question `How do you want to proceed?`:
    1. **Continue revising anyway** (one-shot breach): Increment `max_rounds_breaches`, ask for feedback (no Approval Summary block needed — the user just reviewed it), increment `round`, go to Phase 3.
    2. **Accept the current plan**: Proceed to Phase 6 finalization with the current plan file.
    3. **Abort**: Set status to `aborted`, stop.
  - If `round >= max_rounds` AND `max_rounds_breaches >= MAX_BREACHES`: Hard cap reached. Use AskUserQuestion to present only two options (the "Continue revising anyway" breach option is NO LONGER available). Same one-line state recap as above as the question body, with the notice line `Hard cap reached: no further revision rounds available` and the question `How do you want to proceed?`:
    1. **Accept the current plan**: Proceed to Phase 6 finalization.
    2. **Abort**: Set status to `aborted`, stop.

  > The reject path does NOT silently continue past max_rounds. Each extra round requires explicit user opt-in, AND the total number of breaches is capped at `MAX_BREACHES` (defined in [## Format Recovery](#format-recovery) → `**Constants**`). Once the cap is reached, the dispatcher can no longer spawn a new round — the user must accept or abort. This closes BOTH the "silent continue" gap AND the "user keeps picking continue forever" gap (the latter being the actual root cause of the Round 5 runaway in the diagnostic session).

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

---

## Key Constraints

1. **One question at a time**: When using AskUserQuestion to follow up with the user, ask exactly one question. Do not move to the next question until the current one is answered. Exception: the Phase 4 builder-question round is a single batched AskUserQuestion (see Phase 4).

3. **Role isolation**:
   - The plan designer cannot communicate directly with the user; all questions are relayed through the dispatcher
   - The plan reviewer cannot communicate directly with the user; all questions are relayed through the dispatcher
   - The plan designer and reviewer do not interact directly; information is exchanged indirectly through files

4. **Files as the sole communication medium**: All information between the three roles is transmitted through files. The dispatcher coordinates via the status file and completion signals from agent outputs.

5. **Reviews must be severity-graded**: Every issue from the reviewer must have a severity label (Severe/Medium/Optimization). Reviews without severity labels are invalid.

6. **Plan designer must understand the project first**: The plan designer must understand the existing project architecture before designing. The context snapshot provides pre-extracted architectural knowledge; the designer reads this first and only falls back to raw files when the snapshot is insufficient. No designing in a vacuum.

## Error Handling

- **Subagent failure**: Log the error, notify the user, ask whether to retry
- **Subagent output format deviation**: Detected via `parse_delimited_output.py` returning `status` "empty" or "malformed", or `verdict == null` for review. On detection, the response is persisted to a post-mortem raw at `<file>.raw` (first attempt) or `<file>.raw.retry<T>` (retry) in the main `.ghs/plans/` directory — see Phase 1 / Phase 3 / Phase 4 Handling step 4. Retry once with the [Format Recovery](#format-recovery) appendix. If retry still fails, use AskUserQuestion to let the user decide (retry / accept fallback / abort — see [## User Decision Handling](#user-decision-handling)). **Never silently hang on unparseable output.**
- **File read/write failure**: Check paths and permissions, notify the user
- **User not responding**: Wait, do not proceed automatically

## Format Recovery

When a subagent returns output the parser cannot extract (`status` `empty` / `malformed`, or `verdict == null` for reviews), the dispatcher retries the subagent once with a stronger format reminder appended to the prompt.

**Constants**:
- `MAX_RETRY = 1` — each subagent call may be re-dispatched at most once. This counter is independent from the review-revise `max_rounds` counter.
- `MAX_BREACHES = 2` — the maximum number of "Continue revising anyway" breaches the user can opt into after `round >= max_rounds` is reached. Once `max_rounds_breaches >= MAX_BREACHES`, the "Continue revising anyway" option is removed from both Phase 4 FAIL @ max_rounds and Phase 5 reject @ max_rounds menus; the user can only accept or abort. This guarantees the dispatcher terminates in at most `max_rounds + MAX_BREACHES` rounds regardless of user choices. This constant is the **single source of truth** for the hard cap; Phase 4 / Phase 5 / Key Constraints all reference it by name.

**Raw file naming** — post-mortem raw files ONLY exist on the error path (parse failure) or when `keep_raw_on_success: true` is set in status.json. They are NOT written on the happy path by default. Scratch files used for parser input live in `.ghs/plans/.tmp/` and are cleaned up immediately after parse (see Phase 1 / Phase 3 / Phase 4 Handling step 4).
- First-attempt failure: `<file>.raw` (i.e. `<plan_file>.raw`, `<review_file>.raw`, `<context_file>.raw`)
- Retry-T failure: `<file>.raw.retry<T>` (e.g. `<plan_file>.raw.retry1`)
- Note: Round number is NO LONGER in the filename. Since happy path produces no post-mortem raw, and the normal error path is bounded by `MAX_RETRY=1`, there are at most 2 post-mortem raw files per subagent kind under normal retry (`.raw` + `.raw.retry1`).

  **User-opted retry exception**: If the user picks "Retry once more" in [## User Decision Handling](#user-decision-handling) after `MAX_RETRY` is exhausted, an additional `<file>.raw.retry<T+1>` is written. This path is NOT bounded by `MAX_RETRY` — but it IS bounded by the dispatcher's overall termination guarantee: the user can only retry-format as many times as they keep picking "Retry once more", and the session's max-rounds + breach hard cap (see Key Constraints #2) still bounds total subagent spawns. In practice, post-mortem raw count stays small.

  **`keep_raw_on_success: true` exception**: When this flag is set in status.json, every successful parse ALSO writes a post-mortem raw at `<file>.raw` (overwriting any prior). Use this only for hard-to-debug sessions.

**Retry appendix templates** (append verbatim to the original subagent prompt; pick the one matching the kind):

For Plan Designer retries (`--kind plan`):
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

For Plan Reviewer retries (`--kind review`):
```
## IMPORTANT: Previous Output Format Issue
Your previous response could not be parsed correctly. The delimiters
<<<REVIEW_START>>> ... <<<REVIEW_END>>> were missing or malformed, or the
verdict signal was unreadable.

This time you MUST:
1. Output the delimiters EXACTLY as written: <<<REVIEW_START>>> on its own line, <<<REVIEW_END>>> on its own line.
2. Put ALL review report content between them.
3. Do NOT wrap the delimiters in a code fence.
4. Do NOT translate or modify the delimiter strings.
5. End with the literal completion signal starting with "REVIEW COMPLETE | Verdict: PASS|FAIL | Severe: X Medium: Y Optimization: Z".

Example (correct):
<<<REVIEW_START>>>
... review report ...
<<<REVIEW_END>>>
REVIEW COMPLETE | Verdict: PASS | Severe: 0 Medium: 0 Optimization: 1
```

For Context Subagent retries (`--kind context_snapshot`, Phase 1):
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

## User Decision Handling

When retry is exhausted (`retry_counts.<kind> >= MAX_RETRY`) and the parser still cannot extract usable content, the dispatcher uses AskUserQuestion to let the user decide. The three options and their semantics:

| Option | Dispatcher behavior | File side-effects | When available |
|--------|---------------------|-------------------|----------------|
| **Retry once more** | Increment `retry_counts.<kind>` (one-shot override past `MAX_RETRY`), re-dispatch the subagent with the [Format Recovery](#format-recovery) appendix | New `<file>.raw.retry<T+1>` (or `<context_file>.raw.retry<T+1>` for Phase 1) — round number no longer in filename | Always available |
| **Accept the fallback-extracted content** | Take the most recent `fallback_used` content (or the current raw if the user has manually inspected and confirmed it is usable) and write it to the target file with a leading warning comment: `<!-- WARNING: manually accepted after format deviation retry; strategy=<strategy>; warnings=<warnings joined by "; "> -->` | `<file>` written; status advances to the next phase | Only available if at least one prior parse produced `fallback_used`, OR the user explicitly confirms the current raw is acceptable |
| **Abort this planning session** | Set status to `aborted`, stop all subsequent actions | Any `.raw*` files written so far (post-mortem raw from error path, if any retry happened) are preserved in the main `.ghs/plans/` directory; `.tmp/` scratch is cleaned up by step 4 of the Handling flow (which deletes temp files even on the parse-success path) | Always available |

The AskUserQuestion prompt must:
1. Show the parser's `status`, `strategy`, and `warnings` from the most recent attempt.
2. List only the currently-available options (e.g. if no `fallback_used` ever occurred, omit the "Accept fallback" option).
3. Include the path to the most recent `.raw*` file so the user can inspect it before deciding.

## Reference

- `${CLAUDE_PLUGIN_ROOT}/shared/references/plan-designer.md` — Detailed instructions and plan structure guide for the plan designer
- `${CLAUDE_PLUGIN_ROOT}/shared/references/plan-reviewer.md` — Detailed review standards and review report format for the plan reviewer
