# 金箍咒（Golden Hoop Spell）

[English](README.md) | **中文**

> 想让那孙猴子听你的？那得会念紧箍咒才行。

一套让 Claude 乖乖听话的技能套件 —— 通过迭代式规划、特性拆解和严谨的代码交付来约束 Claude。

各技能组成一条流水线：`init` → `plan` → `code` → `status`/`archive`。

需要先把 plan 文档或裸需求拆解为特性？可使用替代入口 `/ghs:to-features`。

## 技能列表

| 技能 | 说明 |
|------|------|
| `/ghs:init` | 初始化项目跟踪 |
| `/ghs:plan` | 通过迭代式设计与评审生成技术方案 |
| `/ghs:to-features` | 将 plan 文档或裸需求拆解为原子 feature |
| `/ghs:code` | 特性实现（单特性/并行） |
| `/ghs:status` | 查看项目状态 |
| `/ghs:archive` | 归档已完成 plan 的 feature 组 |
| `/ghs:force-archive` | 强制归档所有 plan 的 feature 组 |

## 安装

### 通过插件市场安装（推荐）

添加插件市场并安装插件：

```bash
# 添加插件市场
/plugin marketplace add wangdahoo/golden-hoop-spell

# 安装插件
/plugin install golden-hoop-spell
```

### 本地开发

```bash
claude --plugin-dir /path/to/golden-hoop-spell/plugin
```

## 快速开始

```bash
# 1. 初始化项目跟踪
/ghs:init

# 2. 设计技术方案
/ghs:plan 使用 JWT 添加用户认证  # → docs/ghs/plans/2026-06-10-jwt-auth.md

# 3. 实现特性
/ghs:code            # 一次实现一个特性
/ghs:code --parallel # 并行实现相互独立的特性

# 4. 查看进度
/ghs:status

# 5. plan 完成后归档
/ghs:archive
```

## 使用说明

### `/ghs:init` —— 初始化项目跟踪

创建 `.ghs/` 目录，用于跟踪 plan 和进度。在使用其他任何技能之前，请先在每个项目中运行一次。

```
/ghs:init
```

会创建 `.ghs/features.json`（plan/特性跟踪）、`.ghs/progress.md`（会话日志），并更新 `.gitignore`。

### `/ghs:plan` —— 生成技术方案

通过迭代式"设计—评审"循环生成可执行的技术方案。设计智能体起草方案，架构师评审智能体提出批评，二者反复迭代（最多 5 轮），直到方案足够扎实。

```
/ghs:plan 给 REST API 添加分页
/ghs:plan 将认证方式从 session 迁移到 JWT
```

参数即你的需求描述。评审通过后，你确认方案，它会被保存到 `docs/ghs/plans/`（例如 `docs/ghs/plans/2026-06-10-jwt-auth.md`）。

### `/ghs:to-features` —— 将方案拆解为原子特性

将 plan 文档或裸需求拆解为原子化的特性，包含验收标准、依赖关系和工作量估算。每个特性应能在 2–4 小时内完成。

```
/ghs:to-features docs/ghs/plans/2026-06-10-jwt-auth.md
```

传入 plan 文档路径或要构建的内容描述。该技能会在 `.ghs/features.json` 中生成结构化的特性列表。

### `/ghs:code` —— 特性实现

逐个（默认）或并行地实现当前 plan 中的特性。

```
/ghs:code             # 实现下一个待处理的特性
/ghs:code --parallel  # 并行实现相互独立的特性
```

每个特性都会经过实现、测试、提交。进度跟踪记录在 `.ghs/features.json` 中。

### `/ghs:status` —— 查看项目状态

显示当前 plan 信息、特性完成度统计以及最近的会话活动。

```
/ghs:status
```

### `/ghs:archive` —— 归档已完成 plan 的 feature 组

将已完成 plan 的特性数据移至 `.ghs/archived/`，并重置跟踪文件，以便开始新的 plan。

```
/ghs:archive
```

仅归档状态为 `completed` 的 plan。若不论状态都要归档，请使用 `/ghs:force-archive`（会要求确认）。

## 许可证

MIT
