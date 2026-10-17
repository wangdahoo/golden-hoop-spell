# Golden Hoop Spell

**English** | [中文](README-zh.md)

> 想让那孙猴子听你的？那得会念紧箍咒才行。

A skill suite that keeps Claude on a leash — iterative planning, feature breakdown, and disciplined code delivery.

Skills form a pipeline: `init` → `plan` → `code` → `status`/`archive`.

Need to break a plan document or raw requirements into features first? Use `/ghs:to-features` as an alternative entry point.

## Skills

| Skill | Description |
|-------|-------------|
| `/ghs:init` | Initialize project tracking |
| `/ghs:plan` | Generate technical plans via iterative design & review |
| `/ghs:to-features` | Turn a plan document or raw requirements into atomic features |
| `/ghs:code` | Feature implementation (single/parallel) |
| `/ghs:status` | Show project status |
| `/ghs:archive` | Archive completed plans' feature groups |
| `/ghs:force-archive` | Force archive all plans' feature groups |

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
claude --plugin-dir /path/to/golden-hoop-spell/plugin
```

## Quick Start

```bash
# 1. Initialize project tracking
/ghs:init

# 2. Design a technical plan
/ghs:plan Add user authentication with JWT  # → docs/ghs/plans/2026-06-10-jwt-auth.md

# 3. Implement features
/ghs:code            # one feature at a time
/ghs:code --parallel # independent features in parallel

# 4. Check progress
/ghs:status

# 5. Archive when the plan is done
/ghs:archive
```

## Usage

### `/ghs:init` — Initialize Project Tracking

Set up the `.ghs/` directory for tracking plans and progress. Run this once per project before using any other skills.

```
/ghs:init
```

Creates `.ghs/features.json` (plan/feature tracking), `.ghs/progress.md` (session logs), and updates `.gitignore`.

### `/ghs:plan` — Generate Technical Plans

Produce an executable technical plan through iterative design-and-review cycles. A designer agent drafts the plan, an architect reviewer critiques it, and they iterate (up to 5 rounds) until the plan is solid.

```
/ghs:plan Add pagination to the REST API
/ghs:plan Migrate authentication from session-based to JWT
```

The argument is your requirement description. After review passes, you approve the plan and it's saved to `docs/ghs/plans/` (e.g. `docs/ghs/plans/2026-06-10-jwt-auth.md`).

### `/ghs:to-features` — Turn a Plan into Atomic Features

Break a plan document or raw requirements into atomic features with acceptance criteria, dependencies, and effort estimates. Each feature should be completable in 2–4 hours.

```
/ghs:to-features docs/ghs/plans/2026-06-10-jwt-auth.md
```

Provide a plan document path or a description of what to build. The skill generates a structured feature list in `.ghs/features.json`.

### `/ghs:code` — Feature Implementation

Implement features from the current plan one by one (default) or in parallel.

```
/ghs:code             # implement the next pending feature
/ghs:code --parallel  # implement independent features concurrently
```

Each feature is implemented, tested, and committed. Progress is tracked in `.ghs/features.json`.

### `/ghs:status` — Show Project Status

Display current plan info, feature completion stats, and recent session activity.

```
/ghs:status
```

### `/ghs:archive` — Archive Completed Plans' Feature Groups

Move completed plans' feature data to `.ghs/archived/` and reset tracking files for a fresh plan.

```
/ghs:archive
```

Only archives plans that have reached `completed` status. For archiving regardless of status, use `/ghs:force-archive` (will ask for confirmation).

## License

MIT
