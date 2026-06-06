# golden-hoop-spell

A Claude Code plugin with multiple skills.

## Project Structure

```
golden-hoop-spell/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest (required)
├── package.json                 # npm package metadata
├── CLAUDE.md                    # Project documentation (this file)
├── shared/                      # Shared resources across skills
│   ├── scripts/                 # Python utility scripts
│   ├── references/              # Detailed workflow docs
│   └── assets/                  # Templates (features.json, progress.md)
├── skills/                      # All skills live here
│   ├── ghs-init/                # /ghs:init — Initialize project tracking
│   ├── ghs-sprint/              # /ghs:sprint — Sprint planning & feature breakdown
│   ├── ghs-code/                # /ghs:code — Feature implementation (single/parallel)
│   ├── ghs-status/              # /ghs:status — Show project status
│   ├── ghs-archive/             # /ghs:archive — Archive completed sprints
│   ├── ghs-force-archive/       # /ghs:force-archive — Force archive all sprints
│   └── <skill-name>/            # Each skill is a directory with SKILL.md
└── .gitignore
```

## Installation

```bash
claude plugin install https://github.com/wangdahoo/golden-hoop-spell
```

Or local development:
```bash
claude --plugin-dir /path/to/golden-hoop-spell
```

## Adding a New Skill

1. Create a directory under `skills/` with the skill name (kebab-case)
2. Add a `SKILL.md` file with YAML frontmatter:

```yaml
---
name: skill-name
description: "What this skill does"
---

# Skill Title

Instructions for the skill...
```

## Conventions

- Skill names use `ghs:` prefix (e.g., `ghs:init`, `ghs:sprint`)
- Skill directories use kebab-case (e.g., `ghs-init/`, `ghs-sprint/`)
- Each skill has its own directory under `skills/`
- Shared scripts, references, and assets live in `shared/`
- Skills reference shared resources via `${CLAUDE_PLUGIN_ROOT}/shared/`
