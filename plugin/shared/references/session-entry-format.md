# Progress Log Entry Format

Structure spec for entries in a project's `.ghs/progress.md`. The ghs skills reference
this file via `${CLAUDE_PLUGIN_ROOT}/shared/references/session-entry-format.md`.

## Role

This file is the single source of truth for the structure of `.ghs/progress.md` entries.
Inline entry blocks found in `SKILL.md` files and in `shared/references/` documents
(coding-agent.md, examples.md, features-agent.md) are mirrors: they must stay
field-by-field identical to the templates defined here. On any divergence this file is
authoritative — fix the mirror, not the spec.

## Placement and Numbering

- New entries are inserted at the **top** of the `## Sessions` section — newest entry
  first. The surrounding skeleton of the file is left untouched.
- `N` continues the numbering of existing `## Session N` entries (highest existing
  number + 1). After a reset to the default skeleton, numbering starts from 1 again.
- **Hard requirement: every entry's H2 title line MUST embed a `YYYY-MM-DD` date.**
  `status.py` filters entries by the date found in their first line — an entry whose H2
  title line lacks a date is silently invisible to `/ghs:status`.

## Entry Types

Three entry types exist. Field structure is fixed; bracketed text is a placeholder to
fill in. Section order within an entry must not be rearranged.

### Session Entry

Written by the agent that performed the session's work, once per session:

```markdown
## Session N - YYYY-MM-DD
**Agent**: [one of the values listed under Agent Field Values]
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

Coding sessions add two sections to the base structure above:

- `### Files Changed` — inserted directly after `### Work Completed`; body lines of the
  form `- path/to/file - [brief description]`
- `### Acceptance Criteria Status` — inserted directly after `### Decisions Made`; body
  lines of the form `- [x] [criterion]`

so a coding session entry reads, in order: Work Completed, Files Changed, Tests
Performed, Issues Encountered, Decisions Made, Acceptance Criteria Status, Next Steps.

### Planning Entry

Written once per plan by `To-Features Agent` when the plan is materialized:

```markdown
## Feature Planning - YYYY-MM-DD
**Agent**: To-Features Agent
**Plan**: [Plan ID and Name]

### Requirements Received
- [User's requirement summary]

### Features Planned
- Total: N features
- High priority: N
- Medium priority: N
- Low priority: N

### Plan Goal
[Clear goal statement]

### Implementation Order
1. [feature-id] - [title] - [complexity]
2. [feature-id] - [title] - [complexity]

### Notes
[Any context or decisions]
```

### Parallel Orchestration Entry

Written by `Coding Agent (Parallel Mode)` after a parallel batch finishes. It has no
`**Feature**` field line:

```markdown
## Parallel Orchestration - YYYY-MM-DD
**Agent**: Coding Agent (Parallel Mode)
**Plan**: [Plan ID]
**Max Parallelism**: [N]

### Execution Summary
| Feature | Status | Result |
|---------|--------|--------|
| p1-feat-002 | completed | success |
| p1-feat-003 | completed | success |
| p1-feat-004 | blocked | lint errors in src/api/client.ts |

### Statistics
- Total features: 8
- Completed: 6
- Blocked: 2
- Success rate: 75%

### Next Steps
- [Recommended next actions]
```

## Agent Field Values

The `**Agent**` field takes exactly one of these five values:

| Value | Written by |
|-------|------------|
| `To-Features Agent` | `/ghs:to-features` (Planning Entry) |
| `Plan Dispatcher` | `/ghs:plan` (Session Entry) |
| `Coding Agent` | `/ghs:code` single-feature mode (Session Entry, coding variant) |
| `Coding Agent (Parallel Mode)` | `/ghs:code --parallel` (Parallel Orchestration Entry) |
| `Archive Agent` | `/ghs:archive` and `/ghs:force-archive` (Session Entry) |

Writers retired from earlier versions (Init Agent, Status Agent) no longer write
entries; do not reintroduce their values.

When no plan applies to an entry, write `**Plan**: N/A`.

## Entry Language

The prose language of an entry is NOT fixed by this file. Write entries in the language
the target project itself prescribes for documentation — follow the project's own
configuration such as its `CLAUDE.md` or `AGENTS.md`. If the project defines no such
preference, use a neutral default (for example, the language the project's existing
documentation mostly uses) and state that choice inside the entry, e.g. under
`### Decisions Made` or `### Notes`.
