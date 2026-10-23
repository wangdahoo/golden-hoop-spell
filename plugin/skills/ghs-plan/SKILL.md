---
name: ghs:plan
description: "Produce an executable technical plan through a contract-driven pipeline: the dispatcher freezes a scope contract with the user, a designer subagent writes the plan body against it, a reviewer enforces contract mapping, and approval materializes tasks into features automatically. Use whenever the user asks to create a technical plan, design a solution, or think through how to implement something before coding."
argument-hint: "[requirement description]"
disable-model-invocation: true
---

# Technical Plan Generation

Produce an executable technical plan through multi-agent collaboration. The dispatcher (main conversation) coordinates a plan designer (Plan subagent) and a plan reviewer (architect subagent), operating under a hard review cap: one full review, then at most one targeted revision, one targeted re-review, and one final revision.

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
| `.ghs/plans/{date}-{slug}.md` | Technical plan (contract header written by the dispatcher; body designed by the Plan subagent and concatenated by the dispatcher) |
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
- `retry_counts` (object with keys `plan`, `review`, `context_snapshot`) — each subagent kind has its own independent retry counter, persisted in this file, reset to `0` on a successful parse of that kind. Per-kind cap: `MAX_RETRY = 1`.
- `reject_count` (int, default `0`) — cumulative count of Phase 5 approval rejections in this session. When `reject_count >= 3`, stop cycling and suggest a contract replay (back to Phase 2) instead of another revision.
- `final_fix_pending` (bool, default `false`) — set to `true` when a targeted re-review still leaves residual issues. While it is `true`, exactly one targeted revision is allowed and no further re-review runs; the flag is cleared when the session enters `pending_approval` or `aborted`.
- `accepted_with_fail` (bool, default `false`) — semantics narrowed to: residual issues remained after the (final) re-review AND the user explicitly accepted the plan anyway. After-the-fact audit via `grep '"accepted_with_fail": true' .ghs/plans/*-status.json` still reveals all plans that passed with unfixed issues. The `status` field itself remains `"approved"` (this is an independent flag, not a new status enum value).
- `keep_raw_on_success` (bool, default `false`): When set to `true`, the dispatcher additionally writes the subagent response to `<file>.raw` (overwriting) even on successful parse, for post-mortem debugging. Use only for hard-to-debug sessions where the user suspects logic errors in the plan despite it passing format validation. Normal sessions keep this `false` to keep the main directory clean.

**Updating the status file (script-only, Windows-safe)**: after the Phase 0 creation Write, every mutation goes through `update_plan_status.py` — NEVER inline `python -c` (multi-line `-c` bodies get wrapped into a temporary batch script by the Windows shell and fail, and stdout JSON is GBK-fragile on legacy consoles). Below, `<status_file>` abbreviates `<PROJECT_DIR>/.ghs/plans/{date}-{slug}-status.json`. Canonical form:

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py \
  --file <status_file> \
  --set status=revising
```

- `--set KEY=VALUE` (repeatable; combine several in ONE call when a transition touches multiple fields): `status` (the six-state enum above), `lane` (`light | full`), `plan_file`, `context_file`, `reject_count` (non-negative int), `final_fix_pending` / `accepted_with_fail` / `keep_raw_on_success` (`true | false`), `retry_counts.<plan|review|context_snapshot>` (non-negative int).
- `--bump-retry <plan|review|context_snapshot>` adds 1 to that retry counter (a missing key counts as 0).
- The script performs a strict read-modify-write (unknown fields preserved verbatim), saves UTF-8, refreshes `updated_at` automatically on every call, validates enums/types (unknown keys and bad values exit 2 leaving the file untouched), and prints a single ASCII confirmation line. Read the file (Read tool) BEFORE branching, derive new counter values from what you just read, and persist them in the same turn (write-through).

Two cap counters live on disk: reject_count (Phase 5 rejections, >=3 triggers the contract-replay suggestion) and final_fix_pending (true while one final no-review revision is allowed). The dispatcher reads them before every branch — files are the single source of dispatcher state.

Contract freeze is not a state-machine state — the plan document itself is the truth.

State discipline: (1) write-through — status and files change in the same turn;
(2) read-before-branch at the remaining branch points (Phase 4 verdict branch, Phase 5
reject branch, Phase 6 materialize-failure branch); (3) cap counters live on disk
(reject_count / final_fix_pending / retry_counts) and are never recomputed from memory;
(4) the plan document itself is the contract-freeze truth — no state-machine entry for it.

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

3. **Entry triage** — classify the requirement into one lane (heuristics, not hard
   thresholds), write `lane` into the status file, and route:

   | Lane | Signals | Route | Interaction |
   |---|---|---|---|
   | Self-sufficient | Names exact files and the exact change; no design space | Advise doing it directly and exit (plain text — no AskUserQuestion) | One sentence |
   | Light | Single subsystem; ≤ ~3 files; no new interface/schema; no architectural decision; short description | Light lane L below — skip Phase 1/3/4 entirely (zero subagents); dispatcher may read a few files directly to pin exact paths | 1 round |
   | Full | Everything else | Continue to Phase 1 | In-flow |

   **Downgrade-tell, upgrade-default**: moving DOWN to light/self-sufficient must be
   stated to the user (they can upgrade at any time); moving UP to full never asks —
   zero forced interaction rounds.

4. **Create working directory** (creates both the main directory and the `.tmp/` scratch subdirectory in one shot, so Handling step 2's Write to `.tmp/<x>.raw` never hits "No such file or directory"):
   ```bash
   mkdir -p ${PROJECT_DIR}/.ghs/plans ${PROJECT_DIR}/.ghs/plans/.tmp
   ```

5. **Generate file identifier**: Create `{date}-{slug}` based on current date and the requirement topic.

6. **Initialize status file**: Write the status JSON per the schema, "status": "designing", "lane": "<light | full>" (the self-sufficient exit writes no file — it exits directly at step 3). This creation Write is the only time the status file is written by hand — all later mutations go through `update_plan_status.py` (see [State Tracking](#state-tracking)).

### Light Lane L (zero subagents, merges at Phase 6)

1. **Dispatcher drafts the contract header** (Phase 2 template, six pieces + Global
   Constraints) and **ONE task card** (Phase 3 task-card serialization format) directly —
   reading a handful of project files to pin exact paths is allowed.
2. **Write** `{plan_file}` = contract header + task card. Persist `pending_approval` (`command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py --file <status_file> --set status=pending_approval`).
3. **Single merged round**: ONE AskUserQuestion showing the contract header + task card —
   options `确认物化` / `调整后物化` / `升完整档`:
   - `确认物化` → Phase 6 (shared `tasks_to_features.py`).
   - `调整后物化` → the dispatcher edits the file in place, asks once more (once only), then Phase 6.
   - `升完整档` → persist `lane: "full"` (`update_plan_status.py --set lane=full`), return to Phase 1. The written `{plan_file}` is kept as the
     contract-header starting point: preserve the contract header (everything before the first
     `### Task ` heading) verbatim and strip the old task card — the full-lane designer re-derives
     the task breakdown in Phase 3. State the strip to the user (plain text, no question round).
4. Reviewers do not run on this lane; the merged round IS the gate. Full-lane runs keep
   review Step 1 contract mapping as the backstop for anything mis-triaged as light.

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

1. **Hold the subagent response in memory for the duration of parse.** Do NOT persist it to a post-mortem `.raw` file in the main `.ghs/plans/` directory on the happy path — only the `.tmp/` scratch files in steps 2-3 (raw input + parser result JSON) exist transiently and are deleted in step 4. This is the key distinction from the old behavior: the main `.ghs/plans/` directory stays clean of raw files on success, but the response is briefly on disk under `.tmp/` for the duration of the parser call (which `--input-file` requires).

2. Write the response verbatim to a **temporary file** for parser input (this is a scratch file under `.tmp/`, not a post-mortem raw in the main directory):

   > **Copy this command verbatim, only replacing the `<placeholders>`.**

   Path: `<PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.context.raw` (the `.tmp/` subdirectory is created once in Phase 0 init step 4).

   **`<run-id>` naming rule (all phases)**: `<run-id>` is ANY identifier that stays stable
   within THIS planning run — recommended: the `{date}-{slug}` file identifier, suffixed
   with a scratch counter when one round writes several scratch sets (e.g.
   `2026-10-19-auth-rework-s1`). Never derive it from the host session: the dispatcher
   cannot reliably know the host session identifier, so any naming rule that requires it
   is unexecutable.

3. Invoke the parser helper via `--input-file` (shell never sees the response content — zero injection surface):

   > **You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT parse the subagent output yourself — the helper is the single source of truth for delimiter extraction.**

   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
     --kind context_snapshot \
     --input-file <PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.context.raw \
     --output-file <PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.context.result.json \
     --min-length 100
   ```
   Note: for context_snapshot, **do NOT pass `--completion-signal`** — there is no signal line for context snapshots, so the flag is omitted entirely (parser uses `default=None`).

4. Read the JSON result file from step 3 with the Read tool (`<run-id>.context.result.json`) — do NOT consume the parser's stdout, which only prints a one-line ASCII pointer under `--output-file`; the file is the payload channel and stays exact UTF-8 even on GBK consoles. **Delete both temporary files from steps 2-3** (the raw scratch and the result JSON — whether parse succeeded or failed; persistence decisions are separate). Then branch on `status`:

   - **`ok`** or **`fallback_used`**:
     - Write `content` to the target file (`<context_file>`). For `fallback_used`, prepend the warning comment `<!-- WARNING: extracted via fallback strategy: <strategy>; warnings: <warnings joined by "; "> -->`.
     - **No post-mortem raw file is created on the happy path** (unless `keep_raw_on_success: true` in status.json — see [## State Tracking](#state-tracking)). Persist `context_file` and reset the (possibly bumped) format counter in one call. Notify the user (as plain text in your response — this is informational, not a decision point, so do NOT use AskUserQuestion) if fallback was used. Proceed to Phase 2.

       ```bash
       command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py \
         --file <status_file> \
         --set context_file=<context_file> --set retry_counts.context_snapshot=0
       ```
   - **`empty`** / **`malformed`** with `retry_counts.context_snapshot < MAX_RETRY (=1)`:
     1. **Now persist the response to a post-mortem raw file in the main directory** — this is the only time a `.raw` file lands in the main `.ghs/plans/` directory:
        - Path: `<PROJECT_DIR>/.ghs/plans/<context_file>.raw` for the first attempt, `<PROJECT_DIR>/.ghs/plans/<context_file>.raw.retry<T>` for retry T.
     2. Increment and persist `retry_counts.context_snapshot`, then re-dispatch the Context Subagent with the original prompt plus the [Format Recovery](#format-recovery) appendix.

        ```bash
        command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py \
          --file <status_file> \
          --bump-retry context_snapshot
        ```

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
   rules, ports; no prose). For oversized same-domain needs, slice milestones via the contract's Non-Goals across multiple plan runs (each run gets its own frozen contract); for needs spanning independent subsystems the Phase 3 SPLIT_SUGGESTED gate applies. Safe zone: a single plan stays under ~800 lines.
2. **Confirm with the user** via AskUserQuestion — ONE question showing the full draft:
   "以上是本次计划的范围契约，有无需要修正的地方？" Options: "确认冻结" / "需要修正"。
   If the user requests corrections, revise in place and re-confirm (still the same
   single question). If Phase 0/1 already included a clarification AskUserQuestion round,
   ride this confirmation on that round's final exchange instead of adding a new one —
   UNLESS investigation (reading project files, verifying paths, measuring scope for the
   goals) intervenes between that clarification round and the finished draft. Splitting
   into a separate confirmation round is allowed in that case: the merged exchange is an
   optimization for the no-investigation path, not a hard cap — never force-merge into a
   round that confirms a draft the user has not actually seen.
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

4. Timestamp the contract freeze in the status file (the script refreshes `updated_at` on every call; the set keeps the current state value):

   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py \
     --file <status_file> \
     --set status=designing
   ```

   Proceed to Phase 3.

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

1. **Hold the subagent response in memory for the duration of parse.** Do NOT persist it to a post-mortem `.raw` file in the main `.ghs/plans/` directory on the happy path — only the `.tmp/` scratch files in steps 3-4 (raw input + parser result JSON) exist transiently and are deleted in step 5. This is the key distinction from the old behavior: the main `.ghs/plans/` directory stays clean of raw files on success, but the response is briefly on disk under `.tmp/` for the duration of the parser call (which `--input-file` requires).

2. **SPLIT_SUGGESTED pre-check**: If the response contains a line matching ^SPLIT_SUGGESTED:\s*(.+)$, use AskUserQuestion to let the user decide: 拆分 (persist `aborted` via `update_plan_status.py --set status=aborted`, tell the user the suggested sub-plan split; each sub-plan later runs the full flow) / 合并 (append the user's reason and re-dispatch the designer, returning to this Phase's step 1).

3. Write the response verbatim to a **temporary file** for parser input (this is a scratch file under `.tmp/`, not a post-mortem raw in the main directory):

   > **Copy this command verbatim, only replacing the `<placeholders>`.**

   Path: `<PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.plan.raw` (the `.tmp/` subdirectory is created once in Phase 0 init step 4; `<run-id>` per the naming rule in Phase 1 Handling step 2).

4. Invoke the parser helper via `--input-file` (shell never sees the response content — zero injection surface):

   > **You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT parse the subagent output yourself — the helper is the single source of truth for delimiter extraction.**

   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
     --kind plan \
     --input-file <PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.plan.raw \
     --output-file <PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.plan.result.json \
     --completion-signal "PLAN DESIGN COMPLETE" \
     --min-length 300
   ```

5. Read the JSON result file from step 4 with the Read tool (`<run-id>.plan.result.json`) — do NOT consume the parser's stdout, which only prints a one-line ASCII pointer under `--output-file`; the file is the payload channel and stays exact UTF-8 even on GBK consoles. **Delete both temporary files from steps 3-4** (the raw scratch and the result JSON — whether parse succeeded or failed; persistence decisions are separate). Then branch on `status`:

   - **`ok`** or **`fallback_used`**:
     - On `ok`/`fallback_used`, **the dispatcher overwrites `{plan_file}` with contract header + body**: Read the existing file for the contract header — everything before the first `### Task ` heading (the Phase 2 frozen content; physically never routed through the designer); the body is the parsed `content`; if the body starts with `# {Plan Title}` or a duplicated contract header, strip it down to `## Current State`. On `fallback_used`, prepend the warning comment after the contract header, before the body.
     - **No post-mortem raw file is created on the happy path** (unless `keep_raw_on_success: true` in status.json — see [## State Tracking](#state-tracking)). Persist the transition and reset the (possibly bumped) format counter in one call. Notify the user (as plain text in your response — this is informational, not a decision point, so do NOT use AskUserQuestion) if fallback was used. Proceed to Phase 4.

       ```bash
       command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py \
         --file <status_file> \
         --set status=reviewing --set retry_counts.plan=0
       ```
   - **`empty`** / **`malformed`** with `retry_counts.plan < MAX_RETRY (=1)`:
     1. **Now persist the response to a post-mortem raw file in the main directory** — this is the only time a `.raw` file lands in the main `.ghs/plans/` directory:
        - Path: `<PROJECT_DIR>/.ghs/plans/<plan_file>.raw` for the first attempt, `<PROJECT_DIR>/.ghs/plans/<plan_file>.raw.retry<T>` for retry T.
     2. Increment and persist `retry_counts.plan`, then re-dispatch the Plan subagent with the original prompt plus the [Format Recovery](#format-recovery) appendix for plan.

        ```bash
        command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py \
          --file <status_file> \
          --bump-retry plan
        ```
     3. Return to step 1 with the new response (use `<plan_file>.raw.retry<T>` if it fails again).
   - **`empty`** / **`malformed`** with `retry_counts.plan >= MAX_RETRY`: Post-mortem raw is already saved at `<plan_file>.raw[.retry<T>]`. Use AskUserQuestion per [## User Decision Handling](#user-decision-handling).

### Phase 4: Review (full) + Targeted Revise/Re-Review Inner Loop

Hard cap on model calls in this phase: full review 1 + targeted revision 1 + targeted
re-review 1 + final revision 1 = 4. The happy path (first review PASSes) uses 1.

Read status.json BEFORE branching; branch only on the values just read.

**Full review dispatch** (persist `status: reviewing` first, then dispatch):

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py \
  --file <status_file> \
  --set status=reviewing
```

```json
{
  "subagent_type": "general-purpose",
  "description": "Review technical plan (full)",
  "prompt": "<reviewer instructions>"
}
```

**Reviewer Instruction Template (FULL mode)**:

```
You are a senior architect reviewing a technical plan against its frozen scope contract.

## Review Target
- Plan file (contract header + body — read the contract header FIRST): <PROJECT_DIR>/.ghs/plans/<plan_file>
- Context snapshot: <PROJECT_DIR>/.ghs/plans/<context_file>
- Project directory: <PROJECT_DIR>
- Mode: FULL REVIEW

## Task
Run the four-step review protocol in the order defined in
${CLAUDE_PLUGIN_ROOT}/shared/references/plan-reviewer.md:
Step 4 builder questions (cold read) -> Step 1 contract mapping -> Step 2 bidirectional
failure scan -> Step 3 anchor completeness. Follow its severity definitions (Unwarranted /
Severe / Medium / Optimization), its report skeleton, and its verdict rule
(PASS = zero Unwarranted + zero Severe + zero Medium).

## Output Format Requirements (CRITICAL)
Output the FULL report between the literal delimiters <<<REVIEW_START>>> and
<<<REVIEW_END>>> (each on its own line, no code fences, ASCII only), then end with the
signal line on its own line:
REVIEW COMPLETE | Verdict: PASS|FAIL | Unwarranted: X Severe: Y Medium: Z Optimization: W

## Context Reset
- Disregard any context from previous conversations; read files fresh; isolated task.

## Completion Signal
When done, output the signal line above. The QUESTION channel is retired — pile-3 items
go in the report's Builder Questions section.
```

**Handling**:

1. Write the response verbatim to `<PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.review.raw` (`<run-id>` per the naming rule in Phase 1 Handling step 2), parse with:

   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_delimited_output.py \
     --kind review \
     --input-file <PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.review.raw \
     --output-file <PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.review.result.json \
     --completion-signal "REVIEW COMPLETE" \
     --min-length 150
   ```

2. Read the JSON result file from step 1 with the Read tool (`<run-id>.review.result.json`) — do NOT consume the parser's stdout, which only prints a one-line ASCII pointer under `--output-file`; the file is the payload channel and stays exact UTF-8 even on GBK consoles. Then delete both temp files (the raw scratch and the result JSON), and branch on the JSON (`retry_counts.review` for format retries, per Format Recovery; post-mortem raw rules unchanged):

   - **`ok`/`fallback_used`, verdict PASS or FAIL**: write `content` to `<review_file>` (prepend the fallback warning comment if `fallback_used`), overwrite. If `keep_raw_on_success: true`, also write the raw. Then reset the (possibly bumped) format counter: `command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py --file <status_file> --set retry_counts.review=0`.
   - **`empty`/`malformed`/`verdict == null`**: per Format Recovery (retry once with the appendix; then User Decision Handling).

3. **Builder Questions (pile 3)**: read the report's Builder Questions section. If it is not "None", ask the user ONCE via AskUserQuestion — single batched question round, max 5 questions, each with the reviewer's 2-4 mutually exclusive options and recommended default. Questions beyond the cap (or unanswered) fall to Assumptions — do NOT follow up with more rounds. Record the user's answers.

4. **Branch on verdict** (read status.json first):

   - **PASS** (`reviewing`): if Builder Questions had answers → ONE touch-up dispatch to the designer (Phase 3 template + appendix: "Apply these user answers: <answers>. Change nothing else; output the FULL body.") → concatenate the contract header + body, overwrite plan file. **No re-review after a touch-up.** If no answers → proceed directly. Persist `pending_approval` (clears `final_fix_pending` in the same call): `command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py --file <status_file> --set status=pending_approval --set final_fix_pending=false`. Go to Phase 5.
   - **FAIL** (`reviewing` → persist `revising` via `command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py --file <status_file> --set status=revising`): ONE targeted revision dispatch — Phase 3 template + appendix:

     ```
     ## Targeted Revision
     Address the review findings ONLY, one by one:
     - Unwarranted -> delete the section/content.
     - Under-decision (Severe) -> supply the decision.
     - Over-decision (Medium) -> cut to decision level.
     - Anchor gaps (Medium) -> add compliant anchors.
     Apply the user's Builder-Question answers: <answers, if any>.
     Expanding beyond the findings is forbidden. Output the FULL body.
     ```

     Concatenate the contract header + body, overwrite plan file, persist `status: reviewing` (`update_plan_status.py --set status=reviewing`), then ONE targeted re-review dispatch (same template, `Mode: TARGETED RE-REVIEW`, prompt appended with the previous findings list verbatim and the instruction: "verify each finding ADDRESSED/NOT ADDRESSED + check touched sections for fresh damage; do not re-run the full protocol"). Write the new report over `<review_file>`.
     - Re-review clean (`Unwarranted: 0 Severe: 0 Medium: 0`, and all prior findings ADDRESSED) → persist `pending_approval` (`--set status=pending_approval --set final_fix_pending=false`), Phase 5.
     - Residue remains → AskUserQuestion, user's call (spec cap flow — never automatic):
       - `再修一次（最后一次，无复审）` → persist `final_fix_pending: true` (`--set final_fix_pending=true`), ONE final revision dispatch (same targeted appendix with only the surviving findings; **no re-review**), overwrite plan file, then persist `pending_approval` (`--set status=pending_approval --set final_fix_pending=false`), Phase 5.
       - `带瑕疵接受` → write the accepted-with-fail marker as the FIRST line of `{plan_file}`: `<!-- WARNING: accepted with unfixed issues; S=<X> M=<Y> -->` (`<X>`/`<Y>` = surviving Severe/Medium counts from the latest `<review_file>`), then persist `pending_approval` (`--set status=pending_approval --set final_fix_pending=false`), Phase 5 — the approval surface already lists the residue, and Phase 6 turns the marker into the `accepted_with_fail` audit flag and commit suffix.
       - `中止` → persist `aborted` (`--set status=aborted --set final_fix_pending=false`), stop.

5. **`final_fix_pending` discipline**: while `true`, only one targeted revision is allowed and no further review runs. Clear the flag when entering `pending_approval` or `aborted` — the persist commands above therefore always pair the transition with `--set final_fix_pending=false`. This flag is the on-disk form of the 4-call hard cap — it survives restarts.

6. **Context Snapshot Update** (carried): if the designer/reviewer reported `ADDITIONAL FILES READ`, append a `## Supplementary Context` section to `<context_file>` so later dispatches see the expanded context.

**Contract replay** (explicit back-edge Phase 5 → Phase 2; see Phase 5): same `{plan_file}` — the dispatcher drafts and the user confirms a NEW contract header, the old body is deleted wholesale (it mapped the old contract), `<review_file>` will be overwritten by the next full review, status → `designing`, `reject_count` and `retry_counts` reset to zero (persisted via the one-call `update_plan_status.py` reset defined in Phase 5), then a brand-new Phase 3.

### Phase 5: Approval

The approval surface is assembled at ~zero cost because the dispatcher authored the
contract. Assemble (≤ ~40 lines total) and ask via AskUserQuestion:

| Block | Source |
|---|---|
| 契约头 | Read `<plan_file>` top — paste Intent / Goals / Non-Goals / Anti-Goals verbatim (Decisions/Open Space/Global Constraints may collapse to a one-line count) |
| 任务清单 | Grep `^### Task ` lines from `<plan_file>` (title line only) |
| 评审残留 | Latest `<review_file>`: signal counts + surviving finding titles (one line each; "无" if PASS with none) |
| Assumptions | The `<plan_file>` Assumptions section, item by item (omit this block if "None") |
| 文件 | Plan / Review 两个路径 |
| 修订状态 | "无" if the reviewed text is exactly what is being approved; otherwise "本轮修订未经评审" plus a one-line summary of each post-review revision (rule below) |

**修订状态 rule (unreviewed-revision disclosure)**: if ANY revision was applied after the
most recent review pass without a review covering it — a reject-driven revision from the
`reject_count < 3` path below (designer-dispatched or dispatcher direct edit), the final
no-review fix (`final_fix_pending`), or the builder-question touch-up — the approval
surface MUST say "本轮修订未经评审" and summarize what each such revision changed, one
line per revision. The user is approving the plan AS REVISED, so they must see that the
revised text never went back through the reviewer; presenting an unreviewed revision as
if the PASS verdict covered it is forbidden.

Question: "是否批准该计划？" Options: `批准（归档并物化）` / `拒绝（说明修改方向）` / `中止`。
AskUserQuestion text hygiene: question and option text are PLAIN TEXT — no control
characters, no ANSI escapes, no emoji or decorative special symbols. Strip them from the
surface content before asking; polluted option text has rendered the choice unreadable
in practice.

- **approve** → Phase 6。
- **reject**: Read status.json first. Persist the incremented count (the value you just read + 1) and the transition in ONE call:

  ```bash
  command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py \
    --file <status_file> \
    --set reject_count=<N+1> --set status=revising
  ```

  - `reject_count < 3`: (status already persisted as `revising` above) ONE targeted revision from the user's feedback — still exactly one revision per reject — then persist `pending_approval` (`update_plan_status.py --set status=pending_approval`) and reassemble the approval surface. Two execution forms, chosen by the feedback's nature:
    - **Dispatcher direct edit (mechanical feedback only)**: when the feedback is pure deletion (remove the sections/lines the user names) or mechanical text correction (reword/replace text without adding content or changing any decision, task, or anchor semantics), apply it directly with Edit — no designer dispatch needed. This edit IS the revision for this reject round, and it stays unreviewed, so the reassembled approval surface must disclose it via the 修订状态 rule above. Boundary: feedback that adds content, introduces or changes a decision, adds/removes/retimes tasks, or alters anchor semantics is NOT mechanical and falls to the designer form — this hatch must never become a channel for the dispatcher to redesign the plan.
    - **Designer dispatch (everything else)**: Phase 3 template + feedback appendix (no model review), concatenate and overwrite the plan file.
  - `reject_count >= 3`: **suggest contract replay** (a soft suggestion, not a hard gate): AskUserQuestion — `契约重放` / `再修订一次` / `中止`. `再修订一次` follows the same status discipline as the <3 path (revising → pending_approval, write-through). The user may also initiate a replay at any time.
- **contract replay** (back-edge Phase 5 → Phase 2): overwrite the same `{plan_file}` in place — the dispatcher re-runs Phase 2 (draft a new contract header + user confirmation + Write overwrite); the old body is voided and deleted wholesale (it mapped the old contract); then persist the full reset in one call; then a brand-new Phase 3. `<review_file>` needs no deletion — the next full review overwrites it.

  ```bash
  command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py \
    --file <status_file> \
    --set status=designing --set reject_count=0 \
    --set retry_counts.plan=0 --set retry_counts.review=0 \
    --set retry_counts.context_snapshot=0
  ```

- **`中止`** → persist `aborted` (`command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py --file <status_file> --set status=aborted`), stop.

### Phase 6: Archive + Materialize

1. Copy the approved plan to the permanent archive:
   ```bash
   mkdir -p ${PROJECT_DIR}/docs/ghs/plans
   cp ${PROJECT_DIR}/.ghs/plans/${plan_file} ${PROJECT_DIR}/docs/ghs/plans/${plan_file}
   ```

2. **Check for accepted-with-fail marker**: Read the top of the plan file. If it contains a line matching `<!-- WARNING: accepted with unfixed issues`, set `ACCEPTED_WITH_FAIL = true` and extract the `<X>`/`<Y>` values; otherwise `false`.

3. Commit the archived plan. With the `accepted-with-fail` suffix when applicable:
   ```bash
   cd ${PROJECT_DIR} && git add docs/ghs/plans/${plan_file} && git commit -m "docs(plan): 新增技术方案 - ${plan_file}"
   ```
   (If `ACCEPTED_WITH_FAIL == true`, append the suffix `[accepted-with-fail; S=<X> M=<Y>]` to the message.)

4. **Materialize the task tail** (plan loop closed — the main chain converges to plan → code):
   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/tasks_to_features.py \
     --project-dir <PROJECT_DIR> \
     --plan-file <PROJECT_DIR>/docs/ghs/plans/<plan_file>
   ```
   Read the JSON from stdout and branch on `status`:

   - **`parsed`**: features written. Report plan id and feature ids to the user.
   - **`no_task_zone`**: the plan has no task tail. Tell the user materialization was skipped and suggest `/ghs:to-features` to break the plan down by LLM instead.
   - **`malformed`**: materialization failed AFTER approval and archive; regenerating the whole plan is forbidden (it would silently void the passed review). Two escalating responses, picked by the failure's nature:

     - **Dispatcher direct fix — character-level mechanical deviations ONLY.** When the parser `reason`/`warnings` point at character-level deviations — full-width vs half-width punctuation (e.g. `：` where the materializer requires `:`), full-width spaces, stray whitespace — the dispatcher fixes EXACTLY those characters directly with Edit, on BOTH copies. Hard boundary: single-character substitution/deletion that grep can verify (e.g. `grep -n '：'` against the plan file lists the offending lines); adding, moving, deleting, or rewriting any content, heading, or anchor is forbidden, and so is any semantic change — this hatch exists so a stray full-width colon does not burn a designer round, never as a reformatting channel. Report the exact characters fixed to the user (plain text). Then re-run the materializer command above; if STILL `malformed` (or grep still finds offending characters), fall through to the targeted rewrite.
     - **Targeted task-tail rewrite — everything else.** Re-dispatch the designer (same Phase 3 dispatch, subagent_type Plan) with the FULL current plan file inlined as FROZEN plus this appendix appended:

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

       On success, concatenate the contract header + new body and overwrite `${PROJECT_DIR}/.ghs/plans/${plan_file}` AND `docs/ghs/plans/${plan_file}` (both copies), then re-run the materializer command above. Still `malformed` after one targeted rewrite → AskUserQuestion with two options: `跳过物化` (the user later runs `/ghs:to-features`) / `再修一次任务节` (repeat this branch, once only).
     - **Archive-commit sync (explicit step, once the materializer returns `parsed`)**: the archived copy committed in step 3 is now stale. Both copies already carry the fixed text (the direct fix edits both in place; the rewrite overwrites both) — amend the archive commit so the committed history matches the materialized text, instead of improvising a fix-up commit:
       ```bash
       cd ${PROJECT_DIR} && git add docs/ghs/plans/${plan_file} && git commit --amend --no-edit
       ```

5. Persist the final status (append `--set accepted_with_fail=true` to the same call when `ACCEPTED_WITH_FAIL == true`):

   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py \
     --file <status_file> \
     --set status=approved
   ```

   Report the archived plan path, feature count, and close with: suggest `/ghs:code` to start implementing the first feature.

---

## Key Constraints

1. **One question at a time**: When using AskUserQuestion to follow up with the user, ask exactly one question. Do not move to the next question until the current one is answered. Exception: the Phase 4 builder-question round is a single batched AskUserQuestion (see Phase 4). Every AskUserQuestion — approval surface included — uses PLAIN TEXT for the question and every option: no control characters, no ANSI escapes, no emoji or decorative special symbols (they have polluted option text in practice); strip them before asking.

2. **Role isolation**:
   - The plan designer cannot communicate directly with the user; all questions are relayed through the dispatcher
   - The plan reviewer cannot communicate directly with the user; all questions are relayed through the dispatcher
   - The plan designer and reviewer do not interact directly; information is exchanged indirectly through files

3. **Files as the sole communication medium**: All information between the three roles is transmitted through files. The dispatcher coordinates via the status file and completion signals from agent outputs. Files are the single source of the dispatcher's own state: at every branch point, Read status.json first and branch only on the values just read; write a status change in the same turn as the file write it describes (write-through). No deriving dispatcher state from conversation memory.

4. **Reviews must be severity-graded**: Every issue from the reviewer must have a severity label (Unwarranted/Severe/Medium/Optimization). Reviews without severity labels are invalid.

5. **Plan designer must understand the project first**: The plan designer must understand the existing project architecture before designing. The context snapshot provides pre-extracted architectural knowledge; the designer reads this first and only falls back to raw files when the snapshot is insufficient. No designing in a vacuum.

## Error Handling

- **Subagent failure**: Log the error, notify the user, ask whether to retry
- **Subagent output format deviation**: Detected via `parse_delimited_output.py` returning `status` "empty" or "malformed", or `verdict == null` for review. On detection, the response is persisted to a post-mortem raw at `<file>.raw` (first attempt) or `<file>.raw.retry<T>` (retry) in the main `.ghs/plans/` directory — see Phase 1 / Phase 3 / Phase 4 Handling step 4. Retry once with the [Format Recovery](#format-recovery) appendix. If retry still fails, use AskUserQuestion to let the user decide (retry / accept fallback / abort — see [## User Decision Handling](#user-decision-handling)). **Never silently hang on unparseable output.**
- **File read/write failure**: Check paths and permissions, notify the user
- **User not responding**: Wait, do not proceed automatically

## Format Recovery

When a subagent returns output the parser cannot extract (`status` `empty` / `malformed`, or `verdict == null` for reviews), the dispatcher retries the subagent once with a stronger format reminder appended to the prompt.

**Constants**:
- `MAX_RETRY = 1` — each subagent call may be re-dispatched at most once. Each counter persists in status.json retry_counts and resets to 0 on a successful parse.
- Retry counters are persisted ONLY via `command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_plan_status.py --file <status_file> --bump-retry <plan|review|context_snapshot>` (never hand-edit the JSON and never use inline `python -c` — see [State Tracking](#state-tracking)).

**Raw file naming** — post-mortem raw files ONLY exist on the error path (parse failure) or when `keep_raw_on_success: true` is set in status.json. They are NOT written on the happy path by default. Scratch files (parser input raw + parser result JSON) live in `.ghs/plans/.tmp/` and are cleaned up immediately after parse (Phase 1 Handling step 4, Phase 3 Handling step 5, Phase 4 Handling step 2); their names follow the `<run-id>` naming rule defined in Phase 1 Handling step 2 — stable within this run, never derived from the host session.
- First-attempt failure: `<file>.raw` (i.e. `<plan_file>.raw`, `<review_file>.raw`, `<context_file>.raw`)
- Retry-T failure: `<file>.raw.retry<T>` (e.g. `<plan_file>.raw.retry1`)
- Note: Round number is NO LONGER in the filename. Since happy path produces no post-mortem raw, and the normal error path is bounded by `MAX_RETRY=1`, there are at most 2 post-mortem raw files per subagent kind under normal retry (`.raw` + `.raw.retry1`).

  **User-opted retry exception**: If the user picks "Retry once more" in [## User Decision Handling](#user-decision-handling) after `MAX_RETRY` is exhausted, an additional `<file>.raw.retry<T+1>` is written. In practice, post-mortem raw count stays small.

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
## Current State
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
5. End with the literal completion signal starting with "REVIEW COMPLETE | Verdict: PASS|FAIL | Unwarranted: X Severe: Y Medium: Z Optimization: W".

Example (correct):
<<<REVIEW_START>>>
... review report ...
<<<REVIEW_END>>>
REVIEW COMPLETE | Verdict: PASS | Unwarranted: 0 Severe: 0 Medium: 0 Optimization: 1
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
| **Retry once more** | Bump `retry_counts.<kind>` via `update_plan_status.py --bump-retry <kind>` (one-shot override past `MAX_RETRY`), re-dispatch the subagent with the [Format Recovery](#format-recovery) appendix | New `<file>.raw.retry<T+1>` (or `<context_file>.raw.retry<T+1>` for Phase 1) — round number no longer in filename | Always available |
| **Accept the fallback-extracted content** | Take the most recent `fallback_used` content (or the current raw if the user has manually inspected and confirmed it is usable) and write it to the target file with a leading warning comment: `<!-- WARNING: manually accepted after format deviation retry; strategy=<strategy>; warnings=<warnings joined by "; "> -->` | `<file>` written; status advances to the next phase | Only available if at least one prior parse produced `fallback_used`, OR the user explicitly confirms the current raw is acceptable |
| **Abort this planning session** | Persist `aborted` via `update_plan_status.py --set status=aborted`, stop all subsequent actions | Any `.raw*` files written so far (post-mortem raw from error path, if any retry happened) are preserved in the main `.ghs/plans/` directory; `.tmp/` scratch (raw + result JSON) is cleaned up by the Handling flow's read/delete step (which deletes temp files even on the parse-success path) | Always available |

The AskUserQuestion prompt must:
1. Show the parser's `status`, `strategy`, and `warnings` from the most recent attempt.
2. List only the currently-available options (e.g. if no `fallback_used` ever occurred, omit the "Accept fallback" option).
3. Include the path to the most recent `.raw*` file so the user can inspect it before deciding.

## Reference

- `${CLAUDE_PLUGIN_ROOT}/shared/references/plan-designer.md` — Detailed instructions and plan structure guide for the plan designer
- `${CLAUDE_PLUGIN_ROOT}/shared/references/plan-reviewer.md` — Detailed review standards and review report format for the plan reviewer

## Closing Steps

Finish every run of this skill with BOTH closing steps (including aborted and replay
runs). They are mandatory: every ghs skill sets `disable-model-invocation: true` in its
frontmatter, so the model never auto-loads the next skill — after this skill finishes,
these pointers are the only channel that routes the user to the next stage of the
workflow.

### Step 1: Append the progress.md session entry

Add ONE entry at the **top** of the `## Sessions` section in
`<PROJECT_DIR>/.ghs/progress.md`, following the field structure of the Session Template
built into that file:

```markdown
## Session N - YYYY-MM-DD
**Agent**: Plan Dispatcher
**Plan**: [Plan ID if applicable]
**Feature**: [Feature ID if applicable]

### Work Completed
- [What was done in this session]

### Tests Performed
- [How the results were verified]

### Issues Encountered
- [Any blockers, bugs, or challenges]

### Decisions Made
- [Architectural or design choices]

### Next Steps
- [Recommended next actions]
```

`N` continues the numbering of existing `## Session N` entries. This entry is required on
EVERY exit path — approved, aborted, contract-replay exit, and rejection-driven stop —
otherwise a full plan run leaves zero trace in the session log.

### Step 2: Give the user the next-step guidance

End the session by telling the user exactly what to run next. Never invoke the next ghs
skill yourself — with model invocation disabled, every ghs skill is triggered only by an
explicit user command:

- Next step: `/ghs:code` — implement the first feature materialized from the approved plan
- If materialization was skipped (`no_task_zone`): `/ghs:to-features` — break the plan
  into features with LLM planning instead
- If the session was aborted or stopped at the reject cap: no command — the user decides
  whether to fix the requirement and run `/ghs:plan` again
