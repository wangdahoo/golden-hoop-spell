# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A skill suite that keeps Claude on a leash — iterative planning, structured sprints, and disciplined code delivery. Skills form a pipeline: `init` sets up tracking, `plan` generates technical designs through iterative review, `sprint` breaks work into features, `code` implements them, and `status`/`archive` track and close out progress.

## Architecture

Each skill is a self-contained directory under `skills/` with a `SKILL.md` that defines behavior. Skills delegate deterministic operations to Python scripts in `shared/scripts/` and reference detailed workflows in `shared/references/`. All tracking state lives in the target project's `.ghs/` directory (gitignored), using `features.json` for sprint/feature tracking and `progress.md` for session logs.

The typical skill workflow: resolve project directory via `resolve_project_dir.py` → read `.ghs/` state → perform task → update `.ghs/` state.

`ghs:plan` uses a three-role architecture: a dispatcher (main conversation) orchestrates a plan designer (Plan subagent) and a plan reviewer (general-purpose subagent) through up to 5 review-revise rounds, communicating via files under `.ghs/plans/`.

## Conventions

- Skill names use `ghs:` prefix; directories use kebab-case (e.g., `ghs-init/`)
- Skills reference shared resources via `${CLAUDE_PLUGIN_ROOT}/shared/`
- Feature IDs follow `s{N}-feat-{NNN}` format
- Commit messages use conventional format: `<type>(<scope>): <description>`
- Each session logs to `.ghs/progress.md` at the top of the sessions section

## Critical Rules

1. When running eval loops with `/skill-creator`, use the `ghs-workspace` directory as the working directory.
2. Use Chinese for all user-facing conversation in the main session. Write all SKILL.md files, reference docs, and other LLM-facing content in English.
