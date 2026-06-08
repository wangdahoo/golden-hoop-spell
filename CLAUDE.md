# golden-hoop-spell

A Claude Code plugin with multiple skills.

## Project Structure

```
golden-hoop-spell/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest (required)
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

## Conventions

- Skill names use `ghs:` prefix (e.g., `ghs:init`, `ghs:sprint`)
- Skill directories use kebab-case (e.g., `ghs-init/`, `ghs-sprint/`)
- Each skill has its own directory under `skills/`
- Shared scripts, references, and assets live in `shared/`
- Skills reference shared resources via `${CLAUDE_PLUGIN_ROOT}/shared/`

## Critical Rules

1. When running eval loops with `/skill-creator`, use the `ghs-workspace` directory as the working directory.
2. Always respond in Chinese.
