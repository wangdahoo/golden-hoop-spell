# Golden Hoop Spell

> 想让那孙猴子听你的？那得会念紧箍咒才行。

A skill suite that keeps Claude on a leash — iterative planning, structured sprints, and disciplined code delivery.

Skills form a pipeline: `init` → `plan` → `sprint` → `code` → `status`/`archive`.

## Skills

| Skill | Description |
|-------|-------------|
| `/ghs:init` | Initialize project tracking |
| `/ghs:plan` | Generate technical plans via iterative design & review |
| `/ghs:sprint` | Sprint planning & feature breakdown |
| `/ghs:code` | Feature implementation (single/parallel) |
| `/ghs:status` | Show project status |
| `/ghs:archive` | Archive completed sprints |
| `/ghs:force-archive` | Force archive all sprints |

## Quick Start

```bash
# 1. Initialize project tracking
/ghs:init

# 2. Design a technical plan
/ghs:plan Add user authentication with JWT  # → docs/ghs/plans/2026-06-10-jwt-auth.md

# 3. Break plan into sprint features
/ghs:sprint docs/ghs/plans/2026-06-10-jwt-auth.md

# 4. Implement features
/ghs:code            # one feature at a time
/ghs:code --parallel # independent features in parallel

# 5. Check progress
/ghs:status

# 6. Archive when sprint is done
/ghs:archive
```

## Usage

### `/ghs:init` — Initialize Project Tracking

Set up the `.ghs/` directory for tracking sprints and progress. Run this once per project before using any other skills.

```
/ghs:init
```

Creates `.ghs/features.json` (sprint/feature tracking), `.ghs/progress.md` (session logs), and updates `.gitignore`.

### `/ghs:plan` — Generate Technical Plans

Produce an executable technical plan through iterative design-and-review cycles. A designer agent drafts the plan, an architect reviewer critiques it, and they iterate (up to 5 rounds) until the plan is solid.

```
/ghs:plan Add pagination to the REST API
/ghs:plan Migrate authentication from session-based to JWT
```

The argument is your requirement description. After review passes, you approve the plan and it's saved to `docs/ghs/plans/` (e.g. `docs/ghs/plans/2026-06-10-jwt-auth.md`).

### `/ghs:sprint` — Sprint Planning & Feature Breakdown

Break requirements into atomic features with acceptance criteria, dependencies, and effort estimates. Each feature should be completable in 2–4 hours.

```
/ghs:sprint docs/ghs/plans/2026-06-10-jwt-auth.md
```

Provide a description of what to sprint on. The skill reads any existing technical plans and generates a structured feature list in `.ghs/features.json`.

### `/ghs:code` — Feature Implementation

Implement features from the current sprint one by one (default) or in parallel.

```
/ghs:code             # implement the next pending feature
/ghs:code --parallel  # implement independent features concurrently
```

Each feature is implemented, tested, and committed. Progress is tracked in `.ghs/features.json`.

### `/ghs:status` — Show Project Status

Display current sprint info, feature completion stats, and recent session activity.

```
/ghs:status
```

### `/ghs:archive` — Archive Completed Sprints

Move completed sprint data to `.ghs/archived/` and reset tracking files for a fresh sprint.

```
/ghs:archive
```

Only archives sprints that have reached `completed` status. For archiving regardless of status, use `/ghs:force-archive` (will ask for confirmation).

## Installation

### Install via Marketplace (Recommended)

Add the marketplace and install the plugin:

```bash
# Add marketplace
/plugin marketplace add wangdahoo/golden-hoop-spell

# Install plugin
/plugin install golden-hoop-spell
```

### Local Development

```bash
claude --plugin-dir /path/to/golden-hoop-spell
```

## License

MIT
