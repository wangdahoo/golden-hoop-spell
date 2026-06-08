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

Spawn an Explore subagent to scan the project and create a condensed context snapshot. This snapshot is shared by all subsequent subagents (designer and reviewer) across all rounds, eliminating redundant codebase exploration.

```json
{
  "subagent_type": "Explore",
  "description": "Extract project context snapshot",
  "prompt": "Extract a project context snapshot for the following requirement:\n\n## Requirement\n<user's requirement description>\n\n## Project Directory\n<PROJECT_DIR>\n\n## Task\nScan the project and create a condensed context snapshot file at: <PROJECT_DIR>/.ghs/plans/<context_file>\n\nFollow the format in ${CLAUDE_PLUGIN_ROOT}/shared/references/context-snapshot-guide.md:\n1. Read the dependency manifest (package.json, requirements.txt, Cargo.toml, etc.)\n2. Get the directory structure (exclude node_modules, .git, build dirs)\n3. Read the main entry point\n4. Read config files and database schemas\n5. Read files in directories related to the requirement topic\n6. Condense findings into the snapshot format\n\nTarget 50-70% compression vs raw source. Include function signatures, schemas, and routing — not full file contents.\n\nWhen done, output: 'CONTEXT SNAPSHOT CREATED: <context_file>'"
}
```

**Handling**: If the agent reports `CONTEXT SNAPSHOT CREATED`, proceed to Phase 1. Add `context_file` to the status JSON.

### Phase 1: Plan Design (Round N)

> Every round of plan design follows this flow. Round 1 is a fresh design; Round 2+ incorporates review feedback.

Spawn a Plan subagent to design or revise the plan:

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
4. Save the plan to: <PROJECT_DIR>/.ghs/plans/<plan_file>
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

## Completion Signal
When done, output: "PLAN DESIGN COMPLETE: <plan_file>"
If you encounter a technical decision you cannot resolve, output: "QUESTION: <specific question>"
If you read files beyond the context snapshot, list them as: "ADDITIONAL FILES READ: <file1>, <file2>, ..."
```

**Handling Designer Feedback**:
- Received `PLAN DESIGN COMPLETE` -> Update status to `reviewing`, proceed to Phase 2
- Received `QUESTION` -> Use AskUserQuestion to ask the user, then re-dispatch the design task with the user's answer appended to the prompt

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

## Review Report Format
Save the review report to: <PROJECT_DIR>/.ghs/plans/<review_file>

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
When done, output: "REVIEW COMPLETE: <review_file> | Verdict: PASS/FAIL | Severe: X Medium: Y Optimization: Z"
If you encounter a judgment you cannot resolve, output: "QUESTION: <specific question>"
```

**Handling Reviewer Feedback**:
- Received `REVIEW COMPLETE` -> Read the review report and evaluate the conclusion
  - **PASS** (no severe or medium issues) -> Update status to `pending_approval`, proceed to Phase 3
  - **FAIL** -> Check round count:
    - `round < max_rounds` -> Update status to `revising`, increment round, go back to Phase 1
    - `round >= max_rounds` -> Notify the user that the max round limit is reached, use AskUserQuestion to show the current review result and ask whether to accept
- Received `QUESTION` -> Use AskUserQuestion to ask the user, then re-dispatch the review task with the user's answer appended

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

2. **Maximum 5 review-revise rounds**: Starting from the initial draft, allow up to 5 design-review cycles. Once the limit is reached, the user must decide.

3. **Role isolation**:
   - The plan designer cannot communicate directly with the user; all questions are relayed through the dispatcher
   - The plan reviewer cannot communicate directly with the user; all questions are relayed through the dispatcher
   - The plan designer and reviewer do not interact directly; information is exchanged indirectly through files

4. **Files as the sole communication medium**: All information between the three roles is transmitted through files. The dispatcher coordinates via the status file and completion signals from agent outputs.

5. **Reviews must be severity-graded**: Every issue from the reviewer must have a severity label (Severe/Medium/Optimization). Reviews without severity labels are invalid.

6. **Plan designer must understand the project first**: The plan designer must understand the existing project architecture before designing. The context snapshot provides pre-extracted architectural knowledge; the designer reads this first and only falls back to raw files when the snapshot is insufficient. No designing in a vacuum.

## Error Handling

- **Subagent failure**: Log the error, notify the user, ask whether to retry
- **File read/write failure**: Check paths and permissions, notify the user
- **User not responding**: Wait, do not proceed automatically

## Reference

- `${CLAUDE_PLUGIN_ROOT}/shared/references/plan-designer.md` — Detailed instructions and plan structure guide for the plan designer
- `${CLAUDE_PLUGIN_ROOT}/shared/references/plan-reviewer.md` — Detailed review standards and review report format for the plan reviewer
