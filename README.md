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

### 通过市场安装（推荐）

添加市场并安装插件：

```bash
# 添加市场
/plugin marketplace add wangdahoo/golden-hoop-spell

# 安装插件
/plugin install golden-hoop-spell
```

### 本地开发

```bash
claude --plugin-dir /path/to/golden-hoop-spell
```

## License

MIT
