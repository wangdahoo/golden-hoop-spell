# Golden Hoop Spell

A Claude Code plugin providing a suite of skills for sprint-driven project management and code generation.

## Skills

| Skill | Description |
|-------|-------------|
| `/ghs:init` | Initialize project tracking |
| `/ghs:sprint` | Sprint planning & feature breakdown |
| `/ghs:plan` | Generate technical plans via iterative design & review |
| `/ghs:code` | Feature implementation (single/parallel) |
| `/ghs:status` | Show project status |
| `/ghs:archive` | Archive completed sprints |
| `/ghs:force-archive` | Force archive all sprints |

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
