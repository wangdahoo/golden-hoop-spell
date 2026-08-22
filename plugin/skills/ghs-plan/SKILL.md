---
name: ghs:plan
description: "Generate comprehensive, executable technical plans through an iterative design-and-review process. Uses a three-role architecture: a dispatcher orchestrates a plan designer (Plan agent) and a plan reviewer (architect), running up to 5 rounds of review-revise cycles. Use this skill whenever the user asks to create a technical plan, design a solution, produce a tech spec, or wants to think through how to implement something before coding."
argument-hint: "[requirement description]"
---

# Technical Plan Generation

Produce an executable technical plan through multi-agent collaboration. The dispatcher (main conversation) coordinates a plan designer (Plan subagent) and a plan reviewer (architect subagent), iterating via review-revise cycles until the plan is ready.

## Flow Overview

```
User describes requirement
  |
  v
[Dispatcher] dispatch design task -> [Plan Designer] produces initial plan
  |                                      |
  v                                      v
[Dispatcher] dispatch review task -> [Plan Reviewer] reviews plan
  |                                      |
  v                                      v
[Dispatcher] evaluates result <-- Review report (with severity-graded issues)
  +-- Has severe/medium issues -> dispatch revise task -> [Plan Designer] revises -> back to review
  +-- No severe/medium issues -> AskUserQuestion for user approval
       +-- User approves -> finalize plan, save to docs/ghs/plans/
       +-- User rejects -> continue revise cycle
```

## Prerequisites

- Project directory must be initialized (`.ghs/` directory exists). If not, tell the user to run `/ghs:init` first.
- User must provide a requirement description. If not provided, ask via AskUserQuestion.

## Core Concepts

### Three Roles

| Role | Implementation | Responsibility |
|------|---------------|----------------|
| **Dispatcher** | Main conversation (you) | Orchestrate flow, manage state, communicate with user |
| **Plan Designer** | Plan subagent | Design technical plan, revise based on review feedback |
| **Plan Reviewer** | general-purpose subagent | Review plan from architect perspective, identify and grade issues |

### File Conventions

All intermediate files are stored under `.ghs/plans/`:

| File | Description |
|------|-------------|
| `.ghs/plans/{date}-{slug}.md` | Technical plan (produced by designer) |
| `.ghs/plans/{date}-{slug}-context.md` | Project context snapshot (pre-extracted architectural summary) |
| `.ghs/plans/{date}-{slug}-review.md` | Review report (produced by reviewer) |
| `.ghs/plans/{date}-{slug}-status.json` | Status file (maintained by dispatcher) |

Where `{date}` is `YYYY-MM-DD` and `{slug}` is a short English descriptor of the requirement topic.

After final approval, the plan is copied to `docs/ghs/plans/{date}-{slug}.md`.

### State Tracking

State is tracked via `.ghs/plans/{date}-{slug}-status.json`:

```json
{
  "plan_file": "{date}-{slug}.md",
  "context_file": "{date}-{slug}-context.md",
  "round": 1,
  "status": "designing | reviewing | revising | pending_approval | approved | rejected | aborted",
  "max_rounds": 5,
  "max_rounds_breaches": 0,
  "accepted_with_fail": false,
  "keep_raw_on_success": false,
  "created_at": "YYYY-MM-DDTHH:mm:ss",
  "updated_at": "YYYY-MM-DDTHH:mm:ss"
}
```

**Field descriptions**:
- `max_rounds_breaches` (int, default `0`): Incremented by 1 each time the user chooses "Continue revising anyway" at Phase 2 FAIL @ max_rounds or Phase 3 reject @ max_rounds. When `max_rounds_breaches >= MAX_BREACHES` (default `2`, defined in [## Format Recovery](#format-recovery) → **Constants**), the continue option is removed from the menu in both Phase 2 and Phase 3; the user can only accept or abort. This enforces the hard cap that guarantees dispatcher termination in at most `max_rounds + MAX_BREACHES` rounds.
- `accepted_with_fail` (bool, default `false`): Set to `true` during Phase 4 finalization if the plan header contains a `WARNING: accepted with unfixed issues` marker (from Phase 2 "Accept despite FAIL"). After-the-fact audit via `grep '"accepted_with_fail": true' .ghs/plans/*-status.json` reveals all plans that passed with unfixed issues. The `status` field itself remains `"approved"` (this is an independent flag, not a new status enum value).
- `keep_raw_on_success` (bool, default `false`): When set to `true`, the dispatcher additionally writes the subagent response to `<file>.raw` (overwriting) even on successful parse, for post-mortem debugging. Use only for hard-to-debug sessions where the user suspects logic errors in the plan despite it passing format validation. Normal sessions keep this `false` to keep the main directory clean.

### Issue Severity Levels (Reviewer Must Use)

| Level | Definition | Examples |
|-------|-----------|----------|
| **Severe** | Would cause bugs, or the plan itself is incorrect | Unhandled race conditions, wrong security assumptions, logic errors |
| **Medium** | Implementation path issues, poor design | Unreasonable abstraction levels, missing error handling, performance pitfalls |
| **Optimization** | Does not block plan execution, nice-to-have | Naming improvements, optional caching strategies, better observability |

Pass criteria: **zero severe or medium issues**. Only optimization items are acceptable.

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

5. **Initialize status file**: Write `status: "designing"`.

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
     - **No post-mortem raw file is created on the happy path** (unless `keep_raw_on_success: true` in status.json — see [## State Tracking](#state-tracking)). Add `context_file` to the status JSON. Notify the user (as plain text in your response — this is informational, not a decision point, so do NOT use AskUserQuestion) if fallback was used. Proceed to Phase 1.
   - **`empty`** / **`malformed`** with `retry_count < MAX_RETRY (=1)`:
     1. **Now persist the response to a post-mortem raw file in the main directory** — this is the only time a `.raw` file lands in the main `.ghs/plans/` directory:
        - Path: `<PROJECT_DIR>/.ghs/plans/<context_file>.raw` for the first attempt, `<PROJECT_DIR>/.ghs/plans/<context_file>.raw.retry<T>` for retry T.
     2. Increment `retry_count`, re-dispatch the Context Subagent with the original prompt plus the [Format Recovery](#format-recovery) appendix.

       Note: keep the SAME `subagent_type` and the SAME prompt template
       (`PROMPT_TEMPLATE_CODEGRAPH` or `PROMPT_TEMPLATE_GREP`) as the first attempt —
       do NOT switch the subagent type or prompt template during retry. Keep
       `general-purpose`+`PROMPT_TEMPLATE_CODEGRAPH` or `Explore`+`PROMPT_TEMPLATE_GREP`
       consistent with the first attempt.
     3. Return to step 1 with the new response (use `<context_file>.raw.retry<T>` if it fails again).
   - **`empty`** / **`malformed`** with `retry_count >= MAX_RETRY`: Post-mortem raw is already saved at `<context_file>.raw[.retry<T>]`. Use AskUserQuestion per [## User Decision Handling](#user-decision-handling).

### Phase 1: Plan Design (Round N)

> Every round of plan design follows this flow. Round 1 is a fresh design; Round 2+ incorporates review feedback.

Spawn a Plan subagent to design or revise the plan:

> **Note**: Plan subagents do not have file write permissions. The subagent outputs the plan content in its response; the dispatcher writes it to disk.

```json
{
  "subagent_type": "Plan",
  "description": "Design technical plan round N",
  "prompt": "<designer instructions>"
}
```

**Designer Instruction Template**:

```
You are a senior technical plan designer. Design an executable technical plan for the following requirement.

## Requirement Description
<user's requirement description>

## Project Context
- Project directory: <PROJECT_DIR>
- **Context snapshot**: <PROJECT_DIR>/.ghs/plans/<context_file>
  READ THIS FILE FIRST. It contains a condensed summary of the project's architecture,
  tech stack, directory structure, and relevant code excerpts. Only read raw project
  files if the snapshot is clearly insufficient for a specific detail.

## Task Requirements
1. Read the context snapshot to understand the project architecture
2. If the snapshot lacks specific detail you need, read the relevant source file(s) from the project
3. Design a technical plan based on the requirement
4. Output the FULL plan content in your response (do NOT attempt to write files)
5. If you read files beyond the snapshot, list them after your completion signal

## Plan Structure
The plan should include the following sections (adjust flexibly based on the requirement):
- Background and Goals
- Current State Analysis
- Plan Design (architecture, interfaces, data models, etc.)
- Implementation Steps (phased, executable)
- Risks and Mitigations

## Round Information
- Current round: Round <N>
<N == 1 ? "" : "- Previous review report: <PROJECT_DIR>/.ghs/plans/<review_file>
- Revise the plan based on all Severe and Medium issues in the review report. Each issue must be explicitly addressed in the revised plan.">

## Reference
Read ${CLAUDE_PLUGIN_ROOT}/shared/references/plan-designer.md for detailed design principles and plan structure guide.

## Context Reset
- Disregard any context from previous conversations
- Read all necessary files fresh from the filesystem
- This is an isolated task

## Output Format Requirements (CRITICAL)
The dispatcher extracts your plan by searching for the literal delimiters `<<<PLAN_START>>>` and `<<<PLAN_END>>>`. If you deviate, the dispatcher must invoke a fallback parser, retry, or ask the user — wasting a round and slowing the planning loop. You MUST:
1. Output the delimiters EXACTLY as written: `<<<PLAN_START>>>` on its own line, `<<<PLAN_END>>>` on its own line.
2. Put ALL plan content between them.
3. **Do NOT wrap the delimiters or the content in a code fence** (no ` ``` ` markers around them).
4. **Do NOT translate, transliterate, or modify the delimiter strings** — no `《《PLAN_START》》`, no `<<PLAN_START>>`, no `<<< PLAN_START >>>`.
5. Use the literal ASCII characters `<`, `>`, `_`.

### Correct example
<<<PLAN_START>>>
# My Plan
... content ...
<<<PLAN_END>>>
PLAN DESIGN COMPLETE

### Incorrect examples (DO NOT DO THESE)
- Wrapping in a code fence: ```` ```\n<<<PLAN_START>>>...\n<<<PLAN_END>>>\n``` ```` — the parser falls back to a less reliable strategy.
- Translated punctuation: `《《PLAN_START》》...《《PLAN_END》》` — the parser may fall back or fail.
- Missing or extra brackets: `<<PLAN_START>>` / `<<<<PLAN_START>>>>` — same problem.

## Output Format
Output the FULL plan content in your response, delimited by:
<<<PLAN_START>>>
...plan content here...
<<<PLAN_END>>>

## Completion Signal
When done, output: "PLAN DESIGN COMPLETE"
If you encounter a technical decision you cannot resolve, output: "QUESTION: <specific question>"
If you read files beyond the context snapshot, list them as: "ADDITIONAL FILES READ: <file1>, <file2>, ..."
```

**Handling Designer Feedback**:

1. **Hold the subagent response in memory for the duration of parse.** Do NOT persist it to a post-mortem `.raw` file in the main `.ghs/plans/` directory on the happy path — only the `.tmp/` scratch file in step 3 exists transiently and is deleted in step 5. This is the key distinction from the old behavior: the main `.ghs/plans/` directory stays clean of raw files on success, but the response is briefly on disk under `.tmp/` for the duration of the parser call (which `--input-file` requires).

2. **Designer question pre-check**: If the response contains a line matching `^QUESTION:\s*(.+)$`, treat it as a designer question — use AskUserQuestion to relay the question to the user, then re-dispatch the Plan subagent with the original prompt plus the user's answer appended. **No temporary file written** (the question response is short and not persisted). Skip the remaining steps.

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
     - Write `content` to the target file (`<plan_file>`). For `fallback_used`, prepend the warning comment `<!-- WARNING: extracted via fallback strategy: <strategy>; warnings: <warnings joined by "; "> -->`.
     - **No post-mortem raw file is created on the happy path** (unless `keep_raw_on_success: true` in status.json — see [## State Tracking](#state-tracking)). Update status to `reviewing`. Notify the user (as plain text in your response — this is informational, not a decision point, so do NOT use AskUserQuestion) if fallback was used. Proceed to Phase 2.
   - **`empty`** / **`malformed`** with `retry_count < MAX_RETRY (=1)`:
     1. **Now persist the response to a post-mortem raw file in the main directory** — this is the only time a `.raw` file lands in the main `.ghs/plans/` directory:
        - Path: `<PROJECT_DIR>/.ghs/plans/<plan_file>.raw` for the first attempt, `<PROJECT_DIR>/.ghs/plans/<plan_file>.raw.retry<T>` for retry T.
     2. Increment `retry_count`, re-dispatch the Plan subagent with the original prompt plus the [Format Recovery](#format-recovery) appendix for plan.
     3. Return to step 1 with the new response (use `<plan_file>.raw.retry<T>` if it fails again).
   - **`empty`** / **`malformed`** with `retry_count >= MAX_RETRY`: Post-mortem raw is already saved at `<plan_file>.raw[.retry<T>]`. Use AskUserQuestion per [## User Decision Handling](#user-decision-handling).

### Phase 2: Plan Review

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
If you encounter a judgment you cannot resolve, output: "QUESTION: <specific question>"
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
     - **Early stop**: If `round == 1`, proceed directly to Phase 3 — no need for additional rounds.
     - Update status to `pending_approval`. Proceed to Phase 3.
   - **`ok` or `fallback_used`** with `verdict == "FAIL"`:
     - Write `content` to `<review_file>` (with the warning comment if `fallback_used`).
     - **No post-mortem raw file is created on the happy path** (unless `keep_raw_on_success: true` in status.json — see [## State Tracking](#state-tracking)).
     - Check round count:
       - `round < max_rounds` -> Update status to `revising`, increment round, go back to Phase 1.
       - `round >= max_rounds` AND `max_rounds_breaches < MAX_BREACHES` -> Max round limit reached. Use AskUserQuestion to present three options (symmetric with Phase 3 reject @ max_rounds), with the Approval Summary block as the question body. This is the FAIL scenario of the block defined in [Approval Summary Assembly](#approval-summary-assembly), with these deviations from the standard template:
         - **Header line**: instead of `Plan ready for approval (...)`, show `Plan review FAILED (Round {round}/{max_rounds}, breaches {max_rounds_breaches}/{MAX_BREACHES})` — the block must not claim readiness while listing blocking issues.
         - **Review Result section**: instead of the PASS stats line, show the FAIL stats line `Verdict: FAIL | Severe: {X} Medium: {Y}` followed by the titles of the Severe/Medium issues that triggered the FAIL, one per line, up to 6 titles (keep each title to one line); if there are more, truncate and append the line `... {N} more issue(s) — see Review file below`.
         - **Files section**: unchanged — both the Plan and Review file paths stay; the Review path lets the user dig into the full report.
         - **Closing line**: replace the closing guarantee/question with `The latest review found Severe/Medium issues. Continue revising, accept the plan as-is, or abort?`
         - **Line budget**: the total block budget is relaxed to ≤ 40 lines for this scenario (instead of the standard 34), accommodating the issue-title lines.
         1. **Continue revising anyway** (one-shot breach): Increment `max_rounds_breaches`, increment `round`, go back to Phase 1. Attach the Approval Summary block (per the deviations above) so the user understands what triggered the FAIL. (In other words: attach the Approval Summary block instead of dumping the full review report.)
         2. **Accept the current plan despite the FAIL**: Proceed to Phase 4 with the current plan file (the user takes responsibility for the unfixed issues). Add a marker line at the top of the plan file: `<!-- WARNING: accepted with unfixed issues (round <R>, breaches=<B>): Severe=<X> Medium=<Y> -->` (see Phase 4 Finalization for handling).
         3. **Abort**: Set status to `aborted`, stop.
       - `round >= max_rounds` AND `max_rounds_breaches >= MAX_BREACHES` -> Hard cap reached. Use AskUserQuestion to present only two options (continue breach not available), attaching the same FAIL-scenario Approval Summary block as above (failed header + FAIL stats + up to 6 issue titles, total ≤ 40 lines) plus this notice line appended after the Files section: `Hard cap reached: no further revision rounds available` (same wording as the Phase 3 hard-cap menu):
         1. **Accept the current plan despite the FAIL**: Same marker as above (see Phase 4 Finalization).
         2. **Abort**.
   - **`ok` or `fallback_used`** with `verdict == null`: Treat as format deviation — the reviewer's signal line did not contain `Verdict: PASS|FAIL`. Fall through to the retry path below.
   - **`empty` or `malformed`** (or `verdict == null`) with `retry_count < MAX_RETRY (=1)`:
     1. **Now persist the response to a post-mortem raw file in the main directory** — this is the only time a `.raw` file lands in the main `.ghs/plans/` directory:
        - Path: `<PROJECT_DIR>/.ghs/plans/<review_file>.raw` for the first attempt, `<PROJECT_DIR>/.ghs/plans/<review_file>.raw.retry<T>` for retry T.
     2. Increment `retry_count`, re-dispatch the reviewer with the original prompt plus the [Format Recovery](#format-recovery) appendix for review.
     3. Return to step 1 with the new response (use `<review_file>.raw.retry<T>` if it fails again).
   - **`empty` or `malformed`** (or `verdict == null`) with `retry_count >= MAX_RETRY`: Post-mortem raw is already saved at `<review_file>.raw[.retry<T>]`. Use AskUserQuestion per [## User Decision Handling](#user-decision-handling).

### Phase 2.5: Context Snapshot Update (Optional)

After each design-review round, if the designer or reviewer read additional files beyond the context snapshot, update the snapshot to include the newly discovered context. This ensures subsequent rounds benefit from expanded knowledge.

1. Check if the designer output contains `ADDITIONAL FILES READ: ...`
2. If so, append a `## Supplementary Context` section to the context snapshot file with summaries of the additional files
3. Future rounds will automatically include this expanded context

### Phase 3: User Approval

After the plan passes review, assemble an Approval Summary block (see below) and use AskUserQuestion to request user confirmation, with the summary block as the question body. This also applies to the early-stop path (round == 1 with PASS, entered directly from Phase 2).

#### Approval Summary Assembly

Before asking, read small fragments of the plan/review/status files from disk and assemble a plain-text summary block. Extraction rules:

| Block section | Source | How to extract |
|---|---|---|
| Plan Summary | Review file's plan-summary section (starting point) + plan file goal/core-approach sections (expansion material) | Read the review file (usually < 100 lines, read it whole) and locate its plan-summary section: the reviewer writes free-form prose, so the heading may be `## Plan Summary`, `## 方案摘要`, or another equivalent summary-like heading (a short section near the top summarizing the plan). Do NOT depend on one literal heading. Take the first non-empty paragraph under it as the starting point. Then read the plan file's goal/core-approach sections per the read budget below. Synthesize both into a 2-4 sentence summary (~50-150 words): the first sentence states the goal (what problem the plan solves), the next 1-3 sentences state what it concretely does (which files change, what mechanism/module is introduced, which scenarios are covered) — do NOT expand implementation details. If either source is missing, generate from what is available; if all are missing, write `N/A`. |
| Key Technical Decisions | Plan file `## Plan Design` section (including its `###` subsections — that is where the plan's own decisions live; `## Current State Analysis` describes the pre-existing codebase and may be skimmed only as optional context) | Grep `^## ` to locate section headings, then read those sections in segments (include `###` subsections of Plan Design). Pick decision-like points about what the PLAN chooses (technology choices, architecture trade-offs, interface contracts) — not descriptions of existing architecture — and rewrite each as a one-line short sentence, at most 5. |
| Review stats | 1. The parser JSON `completion_signal` field from the most recent review parse (Phase 2 -> Phase 3 happens in the same conversation turn, so this is normally in memory). 2. If unavailable: an issue-count section in the review file (`## Issue Summary` / `## 问题清单` or equivalent). | Do NOT infer counts from the JSON `verdict` field — `verdict` only holds PASS/FAIL/null, no counts. The `completion_signal` field holds the full signal line `REVIEW COMPLETE \| Verdict: ... \| Severe: X Medium: Y Optimization: Z`; parse the counts from it. Note: the written review file does NOT contain the signal line (the parser strips it before the dispatcher writes `content`), so do not look for it there. |
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

- **User approves** -> Proceed to Phase 4
- **User rejects**:
  - If `round < max_rounds`: Ask for specific revision requests (no Approval Summary block needed — the user just reviewed it), update status to `revising`, increment `round`, go back to Phase 1.
  - If `round >= max_rounds` AND `max_rounds_breaches < MAX_BREACHES` (default `MAX_BREACHES = 2`, defined in [## Format Recovery](#format-recovery) → `**Constants**`): Max round limit reached. Use AskUserQuestion to present three options, since continuing would exceed the configured max_rounds. Do NOT re-assemble the full Approval Summary block (the user just reviewed and rejected it) — instead use a one-line state recap as the question body: `Round {round}/{max_rounds}, breaches {max_rounds_breaches}/{MAX_BREACHES}, latest review: PASS` followed by the notice line `Continuing would exceed max_rounds budget; {MAX_BREACHES - max_rounds_breaches} breach(es) remaining` and the question `How do you want to proceed?`:
    1. **Continue revising anyway** (one-shot breach): Increment `max_rounds_breaches`, ask for feedback (no Approval Summary block needed — the user just reviewed it), increment `round`, go to Phase 1.
    2. **Accept the current plan**: Proceed to Phase 4 finalization with the current plan file.
    3. **Abort**: Set status to `aborted`, stop.
  - If `round >= max_rounds` AND `max_rounds_breaches >= MAX_BREACHES`: Hard cap reached. Use AskUserQuestion to present only two options (the "Continue revising anyway" breach option is NO LONGER available). Same one-line state recap as above as the question body, with the notice line `Hard cap reached: no further revision rounds available` and the question `How do you want to proceed?`:
    1. **Accept the current plan**: Proceed to Phase 4 finalization.
    2. **Abort**: Set status to `aborted`, stop.

  > The reject path does NOT silently continue past max_rounds. Each extra round requires explicit user opt-in, AND the total number of breaches is capped at `MAX_BREACHES` (defined in [## Format Recovery](#format-recovery) → `**Constants**`). Once the cap is reached, the dispatcher can no longer spawn a new round — the user must accept or abort. This closes BOTH the "silent continue" gap AND the "user keeps picking continue forever" gap (the latter being the actual root cause of the Round 5 runaway in the diagnostic session).

### Phase 4: Finalization

1. Copy the plan from `.ghs/plans/` to `docs/ghs/plans/`:
   ```bash
   mkdir -p ${PROJECT_DIR}/docs/ghs/plans
   cp ${PROJECT_DIR}/.ghs/plans/${plan_file} ${PROJECT_DIR}/docs/ghs/plans/${plan_file}
   ```

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

---

## Key Constraints

1. **One question at a time**: When using AskUserQuestion to follow up with the user, ask exactly one question. Do not move to the next question until the current one is answered.

2. **Maximum review-revise rounds (soft + hard cap)**: The default soft limit is 5 rounds (`max_rounds`). For straightforward requirements (e.g., adding a single feature, small refactor, < 200 word description with no architectural changes), set `max_rounds` to 2 in the status file to save time.

   Once `round >= max_rounds` is reached (either via Phase 2 FAIL or Phase 3 reject), the dispatcher MUST NOT silently start a new round. The user must explicitly choose one of three options: continue (breach), accept, or abort.

   **Hard cap on breaches**: The number of "Continue revising anyway" breaches is bounded by `MAX_BREACHES` (default `2`, defined in [## Format Recovery](#format-recovery) → **Constants**). When `max_rounds_breaches >= MAX_BREACHES`, the continue option is removed from the menu — the user can only accept or abort. This guarantees the dispatcher will terminate in at most `max_rounds + MAX_BREACHES` rounds regardless of user choices.

3. **Role isolation**:
   - The plan designer cannot communicate directly with the user; all questions are relayed through the dispatcher
   - The plan reviewer cannot communicate directly with the user; all questions are relayed through the dispatcher
   - The plan designer and reviewer do not interact directly; information is exchanged indirectly through files

4. **Files as the sole communication medium**: All information between the three roles is transmitted through files. The dispatcher coordinates via the status file and completion signals from agent outputs.

5. **Reviews must be severity-graded**: Every issue from the reviewer must have a severity label (Severe/Medium/Optimization). Reviews without severity labels are invalid.

6. **Plan designer must understand the project first**: The plan designer must understand the existing project architecture before designing. The context snapshot provides pre-extracted architectural knowledge; the designer reads this first and only falls back to raw files when the snapshot is insufficient. No designing in a vacuum.

## Error Handling

- **Subagent failure**: Log the error, notify the user, ask whether to retry
- **Subagent output format deviation**: Detected via `parse_delimited_output.py` returning `status` "empty" or "malformed", or `verdict == null` for review. On detection, the response is persisted to a post-mortem raw at `<file>.raw` (first attempt) or `<file>.raw.retry<T>` (retry) in the main `.ghs/plans/` directory — see Phase 0.5 / Phase 1 / Phase 2 Handling step 4. Retry once with the [Format Recovery](#format-recovery) appendix. If retry still fails, use AskUserQuestion to let the user decide (retry / accept fallback / abort — see [## User Decision Handling](#user-decision-handling)). **Never silently hang on unparseable output.**
- **File read/write failure**: Check paths and permissions, notify the user
- **User not responding**: Wait, do not proceed automatically

## Format Recovery

When a subagent returns output the parser cannot extract (`status` `empty` / `malformed`, or `verdict == null` for reviews), the dispatcher retries the subagent once with a stronger format reminder appended to the prompt.

**Constants**:
- `MAX_RETRY = 1` — each subagent call may be re-dispatched at most once. This counter is independent from the review-revise `max_rounds` counter.
- `MAX_BREACHES = 2` — the maximum number of "Continue revising anyway" breaches the user can opt into after `round >= max_rounds` is reached. Once `max_rounds_breaches >= MAX_BREACHES`, the "Continue revising anyway" option is removed from both Phase 2 FAIL @ max_rounds and Phase 3 reject @ max_rounds menus; the user can only accept or abort. This guarantees the dispatcher terminates in at most `max_rounds + MAX_BREACHES` rounds regardless of user choices. This constant is the **single source of truth** for the hard cap; Phase 2 / Phase 3 / Key Constraints all reference it by name.

**Raw file naming** — post-mortem raw files ONLY exist on the error path (parse failure) or when `keep_raw_on_success: true` is set in status.json. They are NOT written on the happy path by default. Scratch files used for parser input live in `.ghs/plans/.tmp/` and are cleaned up immediately after parse (see Phase 0.5 / Phase 1 / Phase 2 Handling step 4).
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

For Context Subagent retries (`--kind context_snapshot`, Phase 0.5):
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

When retry is exhausted (`retry_count >= MAX_RETRY`) and the parser still cannot extract usable content, the dispatcher uses AskUserQuestion to let the user decide. The three options and their semantics:

| Option | Dispatcher behavior | File side-effects | When available |
|--------|---------------------|-------------------|----------------|
| **Retry once more** | Increment `retry_count` (one-shot override past `MAX_RETRY`), re-dispatch the subagent with the [Format Recovery](#format-recovery) appendix | New `<file>.raw.retry<T+1>` (or `<context_file>.raw.retry<T+1>` for Phase 0.5) — round number no longer in filename | Always available |
| **Accept the fallback-extracted content** | Take the most recent `fallback_used` content (or the current raw if the user has manually inspected and confirmed it is usable) and write it to the target file with a leading warning comment: `<!-- WARNING: manually accepted after format deviation retry; strategy=<strategy>; warnings=<warnings joined by "; "> -->` | `<file>` written; status advances to the next phase | Only available if at least one prior parse produced `fallback_used`, OR the user explicitly confirms the current raw is acceptable |
| **Abort this planning session** | Set status to `aborted`, stop all subsequent actions | Any `.raw*` files written so far (post-mortem raw from error path, if any retry happened) are preserved in the main `.ghs/plans/` directory; `.tmp/` scratch is cleaned up by step 4 of the Handling flow (which deletes temp files even on the parse-success path) | Always available |

The AskUserQuestion prompt must:
1. Show the parser's `status`, `strategy`, and `warnings` from the most recent attempt.
2. List only the currently-available options (e.g. if no `fallback_used` ever occurred, omit the "Accept fallback" option).
3. Include the path to the most recent `.raw*` file so the user can inspect it before deciding.

## Reference

- `${CLAUDE_PLUGIN_ROOT}/shared/references/plan-designer.md` — Detailed instructions and plan structure guide for the plan designer
- `${CLAUDE_PLUGIN_ROOT}/shared/references/plan-reviewer.md` — Detailed review standards and review report format for the plan reviewer
