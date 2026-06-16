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

**Verify python3 works** before any other step:
```bash
python3 --version
```
If this errors with "_lazy_pyenv command not found" (or similar), your shell
has a half-loaded pyenv lazy loader. Workaround: use the full path
`/usr/bin/python3` for all subsequent python invocations in this session.

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
  "status": "designing | reviewing | revising | pending_approval | approved | rejected",
  "max_rounds": 5,
  "created_at": "YYYY-MM-DDTHH:mm:ss",
  "updated_at": "YYYY-MM-DDTHH:mm:ss"
}
```

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
   python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
   ```
   Store output as `PROJECT_DIR`.

2. **Confirm requirement**: If the user has not provided a requirement description, use AskUserQuestion to ask: "Please describe the requirement you need a technical plan for." Ask only one question at a time.

3. **Create working directory**:
   ```bash
   mkdir -p ${PROJECT_DIR}/.ghs/plans
   ```

4. **Generate file identifier**: Create `{date}-{slug}` based on current date and the requirement topic.

5. **Initialize status file**: Write `status: "designing"`.

### Phase 0.5: Context Snapshot Extraction

Extract a condensed context snapshot of the project. This snapshot is shared by all subsequent subagents (designer and reviewer) across all rounds, eliminating redundant codebase exploration.

**Detection**: Check if codegraph is available for the target project:
1. Check if `${PROJECT_DIR}/.codegraph/` directory exists
2. If yes, try calling `codegraph_status(projectPath="<PROJECT_DIR>")` to confirm the index is usable
3. If both checks pass → use Path A; otherwise → use Path B

#### Path A: Codegraph-accelerated (preferred when available)

The dispatcher calls codegraph tools directly — no subagent needed:

1. `codegraph_files(maxDepth=3, projectPath="<PROJECT_DIR>")` — get project structure
2. `codegraph_explore(query="<requirement-related keywords> architecture", projectPath="<PROJECT_DIR>")` — get relevant code context
3. Condense the output into the context snapshot format defined in `${CLAUDE_PLUGIN_ROOT}/shared/references/context-snapshot-guide.md`
4. Write to `<PROJECT_DIR>/.ghs/plans/<context_file>`

#### Path B: Explore subagent (fallback)

Spawn an Explore subagent (with haiku model) to scan the project and create a condensed context snapshot.

> **Note**: Explore subagents do not have file write permissions. The subagent outputs the snapshot content in its response; the dispatcher writes it to disk.

```json
{
  "subagent_type": "Explore",
  "model": "haiku",
  "description": "Extract project context snapshot",
  "prompt": "Extract a project context snapshot for the following requirement:\n\n## Requirement\n<user's requirement description>\n\n## Project Directory\n<PROJECT_DIR>\n\n## Task\nScan the project and produce a condensed context snapshot.\n\nFollow the format in ${CLAUDE_PLUGIN_ROOT}/shared/references/context-snapshot-guide.md:\n1. Read the dependency manifest (package.json, requirements.txt, Cargo.toml, etc.)\n2. Get the directory structure (exclude node_modules, .git, build dirs)\n3. Read the main entry point\n4. Read config files and database schemas\n5. Read files in directories related to the requirement topic\n6. Condense findings into the snapshot format\n\nTarget 50-70% compression vs raw source. Include function signatures, schemas, and routing — not full file contents.\n\n## Output Format\nOutput the FULL snapshot content in your response, delimited by:\n<<<CONTEXT_SNAPSHOT_START>>>\n...snapshot content here...\n<<<CONTEXT_SNAPSHOT_END>>>\n\nDo NOT attempt to write any files. Just output the content between the delimiters."
}
```

**Handling (Path B)**: First save the subagent's raw response to disk (file naming per [## Format Recovery](#format-recovery)): the first attempt goes to `<PROJECT_DIR>/.ghs/plans/<context_file>.raw`, retries go to `<context_file>.raw_retry<T>`. Then invoke the parser helper.

> **You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT parse the subagent output yourself — the helper is the single source of truth for delimiter extraction.**

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
  --kind context_snapshot \
  --input-file <PROJECT_DIR>/.ghs/plans/<context_file>.raw[_retry<T>] \
  --min-length 100
```

Read the JSON object printed to stdout and branch on `status`:

- **`ok`**: Write `content` to `<PROJECT_DIR>/.ghs/plans/<context_file>`. Add `context_file` to the status JSON. Proceed to Phase 1.
- **`fallback_used`**: Write `content` to `<context_file>` with a leading warning comment:
  ```
  <!-- WARNING: extracted via fallback strategy: <strategy>; warnings: <warnings joined by "; "> -->
  ```
  Add `context_file` to the status JSON. Notify the user that fallback extraction was used, then proceed to Phase 1.
- **`empty` or `malformed`** with `retry_count < MAX_RETRY (=1)`: Increment `retry_count`, re-dispatch the Explore subagent with the original prompt plus the [Format Recovery](#format-recovery) appendix for context_snapshot. Then return to the raw-save step (writing to `<context_file>.raw_retry<T>`).
- **`empty` or `malformed`** with `retry_count >= MAX_RETRY`: Use AskUserQuestion per [## User Decision Handling](#user-decision-handling).

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

1. Save the subagent's raw response to disk (file naming per [## Format Recovery](#format-recovery)): the first attempt in round R goes to `<PROJECT_DIR>/.ghs/plans/<plan_file>.raw.round<R>`, retries within round R go to `<plan_file>.raw.round<R>_retry<T>`.
2. **Designer question pre-check**: If the raw response contains a line matching `^QUESTION:\s*(.+)$`, treat it as a designer question — use AskUserQuestion to relay the question to the user, then re-dispatch the Plan subagent with the original prompt plus the user's answer appended. Skip the remaining steps.
3. Invoke the parser helper.

   > **You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT parse the subagent output yourself — the helper is the single source of truth for delimiter extraction.**

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
     --kind plan \
     --input-file <PROJECT_DIR>/.ghs/plans/<plan_file>.raw.round<R>[_retry<T>] \
     --completion-signal "PLAN DESIGN COMPLETE" \
     --min-length 300
   ```

4. Read the JSON object printed to stdout and branch on `status`:

   - **`ok`**: Write `content` to `<PROJECT_DIR>/.ghs/plans/<plan_file>`. Update status to `reviewing`. Proceed to Phase 2.
   - **`fallback_used`**: Write `content` to `<plan_file>` with a leading warning comment:
     ```
     <!-- WARNING: extracted via fallback strategy: <strategy>; warnings: <warnings joined by "; "> -->
     ```
     Update status to `reviewing`. Notify the user that fallback extraction was used, then proceed to Phase 2.
   - **`empty` or `malformed`** with `retry_count < MAX_RETRY (=1)`: Increment `retry_count`, re-dispatch the Plan subagent with the original prompt plus the [Format Recovery](#format-recovery) appendix for plan. Then return to step 1 (writing the next raw to `<plan_file>.raw.round<R>_retry<T>`).
   - **`empty` or `malformed`** with `retry_count >= MAX_RETRY`: Use AskUserQuestion per [## User Decision Handling](#user-decision-handling).

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

1. Save the subagent's raw response to disk (file naming per [## Format Recovery](#format-recovery)): the first attempt in round R goes to `<PROJECT_DIR>/.ghs/plans/<review_file>.raw.round<R>`, retries within round R go to `<review_file>.raw.round<R>_retry<T>`.
2. **Reviewer question pre-check**: If the raw response contains a line matching `^QUESTION:\s*(.+)$`, treat it as a reviewer question — use AskUserQuestion to relay the question to the user, then re-dispatch the reviewer with the original prompt plus the user's answer appended. Skip the remaining steps.
3. Invoke the parser helper.

   > **You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT parse the subagent output yourself — the helper is the single source of truth for delimiter extraction AND for the verdict.**

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
     --kind review \
     --input-file <PROJECT_DIR>/.ghs/plans/<review_file>.raw.round<R>[_retry<T>] \
     --completion-signal "REVIEW COMPLETE" \
     --min-length 150
   ```

4. Read the JSON object printed to stdout. **The verdict comes from the JSON `verdict` field — do NOT re-parse the completion signal text yourself.** Branch on `status` and `verdict`:

   - **`ok` or `fallback_used`** with `verdict == "PASS"`:
     - If `status == "fallback_used"`, write `content` to `<review_file>` with a leading warning comment: `<!-- WARNING: extracted via fallback strategy: <strategy>; warnings: <warnings joined by "; "> -->`. Otherwise write `content` directly.
     - **Early stop**: If `round == 1`, proceed directly to Phase 3 — no need for additional rounds.
     - Update status to `pending_approval`. Proceed to Phase 3.
   - **`ok` or `fallback_used`** with `verdict == "FAIL"`:
     - Write `content` to `<review_file>` (with the warning comment if `fallback_used`).
     - Check round count:
       - `round < max_rounds` -> Update status to `revising`, increment round, go back to Phase 1.
       - `round >= max_rounds` -> Notify the user that the max round limit is reached, use AskUserQuestion to show the current review result and ask whether to accept.
   - **`ok` or `fallback_used`** with `verdict == null`: Treat as format deviation — the reviewer's signal line did not contain `Verdict: PASS|FAIL`. Fall through to the retry path below.
   - **`empty` or `malformed`** (or `verdict == null`) with `retry_count < MAX_RETRY (=1)`: Increment `retry_count`, re-dispatch the reviewer with the original prompt plus the [Format Recovery](#format-recovery) appendix for review. Then return to step 1 (writing the next raw to `<review_file>.raw.round<R>_retry<T>`).
   - **`empty` or `malformed`** (or `verdict == null`) with `retry_count >= MAX_RETRY`: Use AskUserQuestion per [## User Decision Handling](#user-decision-handling).

### Phase 2.5: Context Snapshot Update (Optional)

After each design-review round, if the designer or reviewer read additional files beyond the context snapshot, update the snapshot to include the newly discovered context. This ensures subsequent rounds benefit from expanded knowledge.

1. Check if the designer output contains `ADDITIONAL FILES READ: ...`
2. If so, append a `## Supplementary Context` section to the context snapshot file with summaries of the additional files
3. Future rounds will automatically include this expanded context

### Phase 3: User Approval

After the plan passes review, use AskUserQuestion to request user confirmation:

> The plan has completed N rounds of review with no severe or medium issues remaining. Do you approve this plan?

- **User approves** -> Proceed to Phase 4
- **User rejects** -> Ask for specific revision requests, update status to `revising`, go back to Phase 1 with the user's feedback attached to the revision instructions

### Phase 4: Finalization

1. Copy the plan from `.ghs/plans/` to `docs/ghs/plans/`:
   ```bash
   mkdir -p ${PROJECT_DIR}/docs/ghs/plans
   cp ${PROJECT_DIR}/.ghs/plans/${plan_file} ${PROJECT_DIR}/docs/ghs/plans/${plan_file}
   ```

2. Commit the finalized plan document:
   ```bash
   cd ${PROJECT_DIR} && git add docs/ghs/plans/${plan_file} && git commit -m "docs(plan): add technical plan - ${plan_file}"
   ```

3. Update status to `approved`.

4. Report the final plan location and a summary of review rounds to the user. Suggest the next step: use `/ghs:sprint` to break the plan into features for implementation.

---

## Key Constraints

1. **One question at a time**: When using AskUserQuestion to follow up with the user, ask exactly one question. Do not move to the next question until the current one is answered.

2. **Maximum review-revise rounds**: The default limit is 5 rounds. For straightforward requirements (e.g., adding a single feature, small refactor, < 200 word description with no architectural changes), set `max_rounds` to 2 in the status file to save time. Once the limit is reached, the user must decide.

3. **Role isolation**:
   - The plan designer cannot communicate directly with the user; all questions are relayed through the dispatcher
   - The plan reviewer cannot communicate directly with the user; all questions are relayed through the dispatcher
   - The plan designer and reviewer do not interact directly; information is exchanged indirectly through files

4. **Files as the sole communication medium**: All information between the three roles is transmitted through files. The dispatcher coordinates via the status file and completion signals from agent outputs.

5. **Reviews must be severity-graded**: Every issue from the reviewer must have a severity label (Severe/Medium/Optimization). Reviews without severity labels are invalid.

6. **Plan designer must understand the project first**: The plan designer must understand the existing project architecture before designing. The context snapshot provides pre-extracted architectural knowledge; the designer reads this first and only falls back to raw files when the snapshot is insufficient. No designing in a vacuum.

## Error Handling

- **Subagent failure**: Log the error, notify the user, ask whether to retry
- **Subagent output format deviation**: If the subagent returns successfully but the output cannot be parsed via the delimiter protocol (detected via `parse_delimited_output.py` returning `status` "empty" or "malformed", or `verdict == null` for review), retry once with the [Format Recovery](#format-recovery) appendix appended to the prompt. If retry still fails, the raw output is already saved at `<file>.raw.round<R>[_retry<T>]`; use AskUserQuestion to let the user decide (retry / accept fallback / abort — see [## User Decision Handling](#user-decision-handling)). **Never silently hang on unparseable output.**
- **File read/write failure**: Check paths and permissions, notify the user
- **User not responding**: Wait, do not proceed automatically

## Format Recovery

When a subagent returns output the parser cannot extract (`status` `empty` / `malformed`, or `verdict == null` for reviews), the dispatcher retries the subagent once with a stronger format reminder appended to the prompt.

**Constants**:
- `MAX_RETRY = 1` — each subagent call may be re-dispatched at most once. This counter is independent from the review-revise `max_rounds` counter.

**Raw file naming** (preserves every attempt for post-mortem debugging):
- Phase 0.5 (context snapshot): `<context_file>.raw`, then `<context_file>.raw_retry1`, `<context_file>.raw_retry2`, ...
- Phase 1 (plan designer) and Phase 2 (reviewer): `<file>.raw.round<R>` for the first attempt in round R, then `<file>.raw.round<R>_retry1`, `<file>.raw.round<R>_retry2`, ...

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

For Explore subagent retries (`--kind context_snapshot`, Phase 0.5 Path B):
```
## IMPORTANT: Previous Output Format Issue
Your previous response could not be parsed correctly. The delimiters
<<<CONTEXT_SNAPSHOT_START>>> ... <<<CONTEXT_SNAPSHOT_END>>> were missing or malformed.

This time you MUST:
1. Output the delimiters EXACTLY as written: <<<CONTEXT_SNAPSHOT_START>>> on its own line, <<<CONTEXT_SNAPSHOT_END>>> on its own line.
2. Put ALL snapshot content between them.
3. Do NOT wrap the delimiters in a code fence.
4. Do NOT translate or modify the delimiter strings.
```

## User Decision Handling

When retry is exhausted (`retry_count >= MAX_RETRY`) and the parser still cannot extract usable content, the dispatcher uses AskUserQuestion to let the user decide. The three options and their semantics:

| Option | Dispatcher behavior | File side-effects | When available |
|--------|---------------------|-------------------|----------------|
| **Retry once more** | Increment `retry_count` (one-shot override past `MAX_RETRY`), re-dispatch the subagent with the [Format Recovery](#format-recovery) appendix | New `<file>.raw.round<R>_retry<T+1>` (or `<context_file>.raw_retry<T+1>` for Phase 0.5) | Always available |
| **Accept the fallback-extracted content** | Take the most recent `fallback_used` content (or the current raw if the user has manually inspected and confirmed it is usable) and write it to the target file with a leading warning comment: `<!-- WARNING: manually accepted after format deviation retry; strategy=<strategy>; warnings=<warnings joined by "; "> -->` | `<file>` written; status advances to the next phase | Only available if at least one prior parse produced `fallback_used`, OR the user explicitly confirms the current raw is acceptable |
| **Abort this planning session** | Set status to `aborted`, stop all subsequent actions | All `.raw*` files preserved for post-mortem | Always available |

The AskUserQuestion prompt must:
1. Show the parser's `status`, `strategy`, and `warnings` from the most recent attempt.
2. List only the currently-available options (e.g. if no `fallback_used` ever occurred, omit the "Accept fallback" option).
3. Include the path to the most recent `.raw*` file so the user can inspect it before deciding.

## Reference

- `${CLAUDE_PLUGIN_ROOT}/shared/references/plan-designer.md` — Detailed instructions and plan structure guide for the plan designer
- `${CLAUDE_PLUGIN_ROOT}/shared/references/plan-reviewer.md` — Detailed review standards and review report format for the plan reviewer
