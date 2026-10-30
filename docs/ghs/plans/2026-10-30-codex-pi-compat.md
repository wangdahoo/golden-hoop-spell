# Codex 与 Pi 双宿主兼容层（接续 2026-10-18 codex-compat 设计）

> SCOPE CONTRACT — frozen at kickoff. 由 dispatcher 维护并经用户确认；
> 正文不得扩大本契约范围，冲突时删正文不删契约。

## Intent
同一套 ghs 技能源在 Claude Code 之外的两大宿主（OpenAI Codex CLI、badlogic pi
coding agent）上以原生形态安装并以功能对等方式运转（含 ghs:plan 三角色流水线与
ghs:code --parallel 的多代理编排），宿主差异收敛到最小兼容层；本计划是对
2026-10-18 已归档但从未实施的 codex-compat 设计的接续与双宿主扩展。

## Goals
- 仓库可被 Codex（plugin marketplace）与 pi（其技能/扩展安装机制）原生安装；Claude 侧发布与加载零影响
- Codex 与 pi 安装后 7 个技能全部可发现、可调用
- 功能对等：三角色流水线与 --parallel 在 Codex 与 pi 上均以等价机制运转（pi 以 pi-subagents 扩展为前置）
- 兼容层形态遵循既有裁决：SKILL.md 正文零宿主差异（统一 Platform Adaptation 指针块 add-only），宿主差异知识外置 per-host 参考文件，通用探测/解析逻辑下沉 Python 脚本
- ${CLAUDE_PLUGIN_ROOT} 等路径引用在两宿主可解析（实测验证，失败时脚本兜底接管）
- README（中英）提供 Codex 与 pi 安装章节
- 端到端验证：本机可用的宿主实测跑通 install → init → plan（三角色）→ code（含 --parallel）→ status → archive；不可用的宿主交付可复现 E2E 手册

## Non-Goals
- 不改 plugin/skills 与 plugin/shared 现有布局及 Claude 安装路径（指针块 add-only 除外）
- 不维护任何技能内容的第二副本（单一技能源）
- 不做 ChatGPT 桌面/网页端等其它宿主形态的适配（仅 Codex CLI 与 pi CLI）
- 不使用 Codex hooks/MCP/.app.json 扩展点（ghs 现无 hooks/MCP，保持为零）
- 不引入新重依赖（工具仅 Python 标准库）

## Anti-Goals
- Claude marketplace 现有安装/使用回归
- 任一宿主上技能可安装但功能缺失或静默失败（相对 Claude 侧功能阉割即失败）
- 把宿主专属知识写进 SKILL.md 正文（正文零污染裁决）
- 双清单/多宿主文档版本漂移且无校验手段
- pi 上缺失 pi-subagents 时伪装功能可用（必须显式检测并显式报告缺失）

## Decisions
- 接续旧方案：2026-10-18 设计的兼容层形态（指针块 + per-host 参考 + host_compat.py + plugin.json + 清单校验脚本 + E2E 手册）作为基线沿用；但 v0.5.1→v0.6.0 技能面已演进，现状事实以本计划上下文快照为准重新核实，不复用旧方案的行号与计数 [DISCRETIONARY]
- 宿主集合固定为三个：claude-code（基线）、codex、pi；host_compat.py 探测输出扩展三值枚举
- pi 子代理依赖 pi-subagents 扩展包（subagent 工具），作为 pi 侧前置条件写入 pi-host.md 与安装文档；缺失时显式报缺失，不静默降级
- Codex 侧沿用旧方案映射（general-purpose/Plan→default、Explore→explorer）；pi 侧角色映射由 designer 依据 pi-subagents 工具语义与官方文档裁量 [DISCRETIONARY]
- 交互原语（AskUserQuestion）在无此原语的宿主降为文本提问，单题/选项枚举/默认推荐与单轮批量语义保持一致（沿用旧方案成文条款）
- 「长输出子代理文件交接 + 完成判定只看 raw 文件解析结果」与 retry/状态机零改动原则继续有效

## Open Space
- pi 侧技能/插件安装机制的落地形态（designer 调研 pi 官方文档后落定）
- host_compat.py 对 pi 的探测信号（env marker / 目录布局，designer 依据调研裁量）
- pi-host.md 的内容块划分（对齐 codex-host.md 的块结构）
- E2E 手册形态：单文件多宿主 vs per-host 分册
- README 两宿主章节的命令细节（以实测或官方文档为准）

## Global Constraints
- Python 调用一律 command python3
- 语言政策沿用 CLAUDE.md：中文文档/commit，英文标识符/日志/错误串/LLM 提示
- SKILL.md 既有行零删改（仅指针块 add-only，七文件块内容逐字一致）
- 版本与 0.6.0 体系对齐；新增/扩展的清单校验脚本覆盖多清单一致性
- pi 前置条件 pi-subagents 显式声明，缺失检测显式失败

## Current State

以下事实在快照基础上补充本次核实结论（快照 §1-§4 不再复述）：

- **references 宿主原语清点（闭合快照 Known Gaps 第 2 条）**：全 6 个 references 文件 grep 宿主原语词表（AskUserQuestion / Task tool / subagent / TaskOutput / CLAUDE_PLUGIN_ROOT / TodoWrite）结果——宿主原语只集中在 `coding-agent.md`（AskUserQuestion 3 处、"Use the Agent tool to spawn subagents" 派发块 1 处含 `subagent_type`/`run_in_background`、`${CLAUDE_PLUGIN_ROOT}` 脚本命令 5 处）与 `features-agent.md`（仅 `${CLAUDE_PLUGIN_ROOT}` 脚本命令 4 处，host 无关）；`plan-designer.md` / `plan-reviewer.md` / `examples.md` / `context-snapshot-guide.md` 零宿主原语（仅 "subagent" 作通用名词）。SKILL.md 侧不变：AskUserQuestion 28 处、派发 JSON 4 处、`run_in_background` 1 处、`TaskOutput` 提及 1 处（原文已带 "or equivalent" 措辞）。
- **Codex 宿主机制（developers.openai.com/codex/plugins 与 /codex/plugins/build 现行文档，2026-10-30 核实，其中两点修正旧方案）**：(1) 插件清单规范位置是 `plugin/.codex-plugin/plugin.json`（"Every plugin has a manifest at `.codex-plugin/plugin.json`"，仅该文件入 `.codex-plugin/`，`skills/` 等留插件根），现行最小与完整清单示例均**无 `$schema` 字段**——旧方案"可移植 plugin.json 置于插件根 + $schema 必填"两点作废；(2) `marketplace add` 支持 `owner/repo` / 本地路径，Codex 继续读取 legacy `$REPO_ROOT/.claude-plugin/marketplace.json`（字符串 source 为文档明示合法形态）；安装落点 `~/.codex/plugins/cache/<marketplace>/<plugin>/<version|local>/`，CLI 经 `/plugins` 浏览器安装（文档无 `codex plugin install` 子命令记载）；调用形态 = 自然语言描述任务或 `@` 显式调用插件/技能；hooks 命令注 `PLUGIN_ROOT`/`PLUGIN_DATA` 且兼容注入 `CLAUDE_PLUGIN_ROOT`/`CLAUDE_PLUGIN_DATA`（技能会话内是否展开该变量仍未文档化，保留 E2E 实测）。
- **pi 宿主机制（badlogic/pi-mono 官方文档 packages/coding-agent/docs，2026-10-30 核实）**：pi 实现 Agent Skills 规范——技能 = 含 SKILL.md 的目录，从 `~/.pi/agent/skills/`（agent directory 缺省 `~/.pi/agent/`，可 `PI_CODING_AGENT_DIR` 改写）、`.pi/skills/`、`~/.agents/skills/`、`.agents/skills/` 递归发现，多数非法字段仅警告不拒载；frontmatter `disable-model-invocation: true` 被 pi 支持（不参与自动选择，显式命令 `/skill:<name>` 仍可用，`enableSkillCommands` 缺省 true）；包机制 `pi install npm:<pkg>` / `git:github.com/user/repo` / `https://…` / 本地路径（写 `~/.pi/agent/settings.json` 或 `-l` 写 `.pi/settings.json`），无 manifest 时按约定目录自动发现 `skills/`（递归找 SKILL.md），有 `package.json` 时按 `pi` 键声明（路径支持 glob），git 源克隆到 `~/.pi/agent/git/`（全局）或 `.pi/git/`（项目）；内建工具 `read`/`bash`/`powershell`/`edit`/`write`/`grep`/`find`/`ls`（缺省启 read/bash/edit/write）；bash/powershell 工具向命令注入会话 env `PI_SESSION_ID`/`PI_SESSION_FILE`/`PI_PROVIDER`/`PI_MODEL`/`PI_REASONING_LEVEL`（缺省开启，`exposeSessionEnvironment: false` 关闭）。
- **pi-subagents（npm:pi-subagents，nicobailon，官方 README 核实）**：`pi install npm:pi-subagents` 安装后提供 LLM 工具 `subagent`——单发 `{agent, task}`、forked 上下文 `{context: "fork"}`、并行 `{tasks: [{agent, task}, ...], concurrency}`、链式 `{chain: [...]}` 与 `async: true` 后台；`output: "<路径>"` + `outputMode: "file-only"` 由扩展把代理最终输出落盘并只回文件引用（原生文件交接泳道）；管理动作 `{action: "list"|"status"|"resume"|"stop"|...}`；内建 agent：`scout`（只读侦察）/ `planner`（"read and plan, not edit code"）/ `worker`（实现）/ `reviewer`（评审）/ `delegate`（贴近父会话的通用代理）/ `oracle` / `researcher` / `context-builder`；`tools` 省略时子代理获得 pi 正常内建工具（可读文件）。生态存在多个同名 pi-subagents 包，本计划钉 `npm:pi-subagents` 为规范前置。
- **旧方案失效事实点回执（快照 §4）**：版本 0.5.1→0.6.0；`${CLAUDE_PLUGIN_ROOT}` 57 处；AskUserQuestion 28 处；测试 10 个；scratch 命名 `<run-id>`（禁宿主 session 派生）；状态写入已全脚本化；ghs-archive 兜底翻转新增 AskUserQuestion；parser 已有 `--output-file` 且结果改为 Read 文件消费；`plugin/plugin.json`（旧位置）/`codex-host.md`/`host_compat.py`/`validate_manifests.py`/E2E 手册/README Codex 节至今全部不存在于树。
- **superpowers 先例指针块原文已补读（闭合 Known Gaps 第 1 条）**：`using-superpowers/SKILL.md` 的形态是独立 `## Platform Adaptation` 小节 + 逐宿主 bullet 列表指向相对路径参考文件；ghs 的 references 在插件根 `shared/references/` 而非技能目录内，故指针块需改为解析后的绝对引用并内嵌自举说明。

## Design

### 兼容层总体形态（沿用五件套 + 双宿主扩展）

superpowers 实证同型继续有效：7 个 SKILL.md 各插入统一英文 Platform Adaptation 指针块（add-only，七文件逐字一致）；宿主差异知识全部外置 `plugin/shared/references/codex-host.md` 与 `plugin/shared/references/pi-host.md`（Claude 侧永不读取，既有 references 对二者零反向引用，唯一入口是指针块）；通用探测下沉 `plugin/shared/scripts/host_compat.py`（host 枚举三值）；新增 Codex 清单与 pi 清单；`validate_manifests.py` 扩展为多清单一致性校验。**references 裁定：既有 references 全部零改动**——`coding-agent.md` 的派发节由 per-host 文件按指针块 "wherever it supersedes" 读序覆盖（与旧方案 codex-host.md 机制同型），子代理必读的定界符/信号/文件交接协议本身宿主中立，无需指针豁免文件。单点解析原则保留：主会话解析一次插件根，派发前把 prompt 模板中 `${CLAUDE_PLUGIN_ROOT}` 字面替换，子代理不见未解析变量。

### Platform Adaptation 指针块（统一模板，实现时逐字转录）

```markdown
## Platform Adaptation
- Claude Code hosts: nothing to do — proceed as written below.
- Other hosts (OpenAI Codex CLI, Pi coding agent): if `${CLAUDE_PLUGIN_ROOT}` below is
  not expanded by your harness, derive the plugin root from the directory of the SKILL.md
  you are executing (its grandparent directory), run
  `command python3 <plugin_root>/shared/scripts/host_compat.py`, then read
  `<plugin_root>/shared/references/codex-host.md` when it reports `"host": "codex"` or
  `<plugin_root>/shared/references/pi-host.md` when it reports `"host": "pi"`, and follow
  that file wherever it supersedes a host-specific instruction below (subagent dispatch,
  interactive questions, plugin-root resolution).
```

插入位置：frontmatter 与 H1 引言段之后、第一个既有 `## ` 小节之前；除该块外正文零改动。

### host_compat.py 三宿主探测（Open Space：pi 探测信号——落定）

CLI 与输出语义沿用旧方案并扩展：`command python3 plugin/shared/scripts/host_compat.py [--project-dir DIR]`，stdout 单行 JSON `{"host": "claude-code"|"codex"|"pi"|"unknown", "plugin_root": "<abs path>"|null, "resolution": "env"|"cache-glob"|"asked"}`，exit 0 成功 / exit 1 unknown(asked)；脚本不交互。探测顺序（首中即停；root 有效性 = `<值>/shared/scripts/ghs_compat.py` 存在；glob 一律递归 `**/shared/scripts/ghs_compat.py` 且路径含 `golden-hoop-spell` 过滤，天然覆盖层级与 `@` 扁平两种缓存布局；多命中取最高版本，数字感知元组比较，`local` 优先）：

1. 任意 `CODEX_` 前缀 env → host=codex；root 依次试 `CLAUDE_PLUGIN_ROOT`、`PLUGIN_ROOT`（resolution=env），否则递归 glob `$CODEX_HOME/plugins/cache`（缺省 `~/.codex/plugins/cache`）→ cache-glob；
2. pi marker env `{PI_SESSION_ID, PI_SESSION_FILE, PI_CODING_AGENT_DIR}` 任一 → host=pi；root 依次试同上两个 env，否则递归 glob `$PI_CODING_AGENT_DIR`（缺省 `~/.pi/agent`，覆盖其 `skills/` 与 `git/` 两种落点）→ cache-glob；项目级 `.pi/` 安装是本地路径原位引用，由指针块自举覆盖，不入 glob；
3. `CLAUDE_PLUGIN_ROOT` 有效 → claude-code / env；
4. `PLUGIN_ROOT` 有效 → claude-code / env；
5. 递归 glob `~/.claude/plugins/cache` → claude-code / cache-glob；
6. 全部失败 → unknown / asked / exit 1。

宿主 marker 优先于 `CLAUDE_PLUGIN_ROOT` 判 host（防"宿主兼容展开该变量 → 误判 claude-code → 跳过 per-host 文件"），理由同旧方案。模块暴露纯函数 `detect(env: Mapping[str, str], paths: DetectPaths) -> dict`，`DetectPaths(claude_home: Path, codex_home: Path | None, pi_agent_dir: Path | None)` dataclass，CLI 为薄壳（home 缺省 `~/.claude` / `$CODEX_HOME` 或 `~/.codex` / `$PI_CODING_AGENT_DIR` 或 `~/.pi/agent`）；复用 `ghs_compat.force_utf8_stdio()`；仅标准库；`--project-dir` 接受但不参与探测。

### codex-host.md（六块，v0.6.0 修订）

全英文，Claude 侧永不读取。块结构沿用旧方案，内容吸收三点修订：raw/scratch 路径话术一律 `<run-id>`（旧方案 `<session_id>` 措辞废弃，当前 SKILL.md 明令禁宿主 session 派生）；parser `--output-file` 结果文件用宿主任意文件读取工具 Read 消费；清单/版本引用对齐 `.codex-plugin/plugin.json` 与 0.6.0。六块：(1) Prerequisites——`~/.codex/config.toml` `[features] multi_agent = true`（缺失则主路径不可用，见块 6）、建议 `[agents] default_subagent_model`/`default_subagent_reasoning_effort` 机器级兜底、python3；(2) Dispatch main path——`spawn_agent {fork_turns: "none"}` 干净上下文、`wait_agent` 事件订阅有界等待 `timeout_ms` 300000–600000（不短轮询）、完成答案经 mailbox 随下回合到达、`list_agents` 对账、`followup_task` 续发同一代理承接 retry/Format Recovery、V2 无 `close_agent`、以实际工具表为准；(3) Role mapping & raw writers——`general-purpose`/`Plan`→`default`（Plan 泳道 prompt 原文保留 plan-designer.md 指令）、`Explore`→`explorer`（只读）；plan/review 泳道 = 子代理写 `.tmp/<run-id>.plan.raw` / `.tmp/<run-id>.review.raw` 后回传路径，context 泳道 = explorer 响应 dispatcher 沿既有机制捕获落盘（探针门控升级程序不变）；无 MCP → `CODEGRAPH_AVAILABLE` 恒 false 走 `PROMPT_TEMPLATE_GREP`；(4) AskUserQuestion downgrade——旧方案成文条款原文照录（单题、选项 verbatim 枚举、默认推荐、单轮批量语义）；(5) `${CLAUDE_PLUGIN_ROOT}` resolution——指针块自举 + host_compat.py JSON 为准，unknown 时询问用户；(6) Fallback——multi_agent 不可用降级自然语言并行 spawn，显式注明摘要回收风险，完成判定只看 raw 文件解析结果；`--parallel` 每代理写 `.ghs/parallel/<plan_id>/<feature_id>.raw.attempt<N>`，`dispatch_start_iso` 前置门与 retry 状态机不变。另附技能调用形态说明：自然语言描述任务或 `@` 显式调用。

### pi-host.md（六块，结构对齐 codex-host.md）

全英文。(1) Prerequisites——`pi install npm:pi-subagents` 为三角色与 `--parallel` 的硬前置；会话首次派发前验证 subagent 工具在位（`{action: "list"}` 或可用工具表检查）；**缺失时停止流水线、显式报告缺失并给出安装命令，禁止内联伪装子代理**（契约 Anti-Goal；单特性 code 模式不受影响）；python3。(2) Dispatch main path——`subagent` 单发 `{agent: <映射名>, task: <已替换根路径的完整 prompt>}`；plan/review/context 三泳道统一用扩展原生文件交接：`output: "<raw 绝对路径>", outputMode: "file-only"`（扩展将最终响应 verbatim 落盘、回执仅文件引用，不依赖响应保真，pi 侧无需旧方案 Codex 的 explorer 探针程序）；`--parallel` 按 parallel_utils 批次 `{tasks: [...], concurrency: N}` 一次派发；后台/异步（`async` 与 `{action: "status"|"resume"}`）可选优化，完成判定只看 raw 文件解析结果；retry = 同 prompt + Format Recovery 附录重派，落盘 `attempt<N+1>`，`MAX_RETRY` 状态机不变。(3) Role mapping——`general-purpose`→`delegate`、`Explore`→`scout`、`Plan`→`planner`（其 "read and plan, not edit code" 语义对位 Claude 无写盘 Plan 子代理）；Phase 4 评审泳道按其 subagent_type（general-purpose）映射 `delegate`、prompt 原文不变；内置名以 `{action: "list"}` 实际输出为准（superpowers 同款"信实际工具表不信表格式"条款），缺名退 `delegate` + 原 prompt 并记录。(4) AskUserQuestion downgrade——与 codex-host.md 逐字相同条款。(5) Invocation & root resolution——pi 技能显式命令形态 `/skill:ghs:<name>`（`disable-model-invocation: true` 下 Closing Steps 文字路由的 `/ghs:xxx` 在 pi 侧读作对应 `/skill:ghs:xxx`）；`${CLAUDE_PLUGIN_ROOT}` 不被 pi 展开 → 指针块自举 + host_compat.py；正文指令中 Read 对应 pi `read` 工具。(6) Fallback/limits——无 subagent 工具按块 1 显式缺失规则；无 codegraph → `CODEGRAPH_AVAILABLE=false` 走 GREP 模板。

### 清单三件套与多清单校验（Open Space 不再留白）

- 新增 `plugin/.codex-plugin/plugin.json`：`name: "golden-hoop-spell"`（kebab-case）、`version: "0.6.0"`、`description`、`skills: "./skills/"`，可选 `author`/`repository`/`license` 从 Claude 清单原样映射、`keywords` 增补 `codex`/`openai`；**不带 `$schema`**（官方现行示例无此字段，修正旧方案）。
- 新增仓库根 `package.json`：`{"name": "golden-hoop-spell", "private": true, "version": "0.6.0", "pi": {"skills": ["plugin/skills"]}}`——pi 的 git/https 源安装从仓库根解析资源声明；`pi install <repo>/plugin` 本地路径形态走约定目录自动发现，两条路并写 README/E2E。
- `.claude-plugin/marketplace.json` 与 `plugin/.claude-plugin/plugin.json` 零改动（legacy 读取为官方现行文档确认；仅当 E2E 实测失败才按旧方案程序追加键/建 `.agents/plugins/marketplace.json`，并纳入校验脚本交叉分支）。
- 新增 `plugin/shared/scripts/validate_manifests.py`：`[--repo-root DIR]`（缺省 `parents[3]`）、逐项英文 OK/FAIL 行、exit 0 全过 / 1 任一失败；六项检查：(1) `.codex-plugin/plugin.json` 存在且含 name/version/description/skills 四键、name kebab-case；(2) name/version 与 Claude 清单严格相等、双 description 非空；(3) `skills: "./skills/"` 解析目录恰含 7 个 SKILL.md；(4) marketplace.json 恰一个 golden-hoop-spell 条目且 source 解析到同时含 `.codex-plugin/plugin.json`、`skills/`、`shared/` 的目录；(5) 根 `package.json` 的 `pi.skills` 解析目录含 7 个 SKILL.md 且 version=0.6.0；(6) 若存在 `.agents/plugins/marketplace.json` 则与 legacy 清单逐条目核对。配套 `test_validate_manifests.py`（unittest + tempfile fixture）。

### README 与 E2E（Open Space：E2E 形态——落定）

README.md / README-zh.md 的 Installation 下各增两小节：`### Install on OpenAI Codex CLI`（marketplace add + `/plugins` 安装 + multi_agent 前置 + 触发形态）与 `### Install on Pi`（`pi install git:github.com/wangdahoo/golden-hoop-spell` 或本地路径 + `pi install npm:pi-subagents` 前置 + `/skill:ghs:<name>` 触发形态）。E2E 采用**单文件多宿主** `docs/e2e-multi-host.md`（同一套技能源功能对等叙事，公共腿不重复；理由：per-host 差异只在安装/发现/派发腿，分册会造成公共步骤双份漂移）。章节 0-10：0 前置条件（分宿主小节）；1 scratch 项目准备；2 安装（每宿主本地 + 远程两路，记录真实缓存/落点布局与宿主 marker env 集）；3 七技能发现性检查（Codex `/plugins` + `@` 调用；pi `/skill:ghs:status` 可调用）；4 `${CLAUDE_PLUGIN_ROOT}` 探针（每宿主三结局：已展开 / 未展开但自举 + host_compat 接管 / unknown→询问用户）；5 init；6 plan 三角色（Codex：spawn_agent 主路径链路验证 + explorer 探针决策程序沿用旧方案；pi：subagent 工具在位验证 + output 文件 verbatim 校验 + 双任务并行验证）；7 code 单特性；8 code `--parallel` 双特性；9 status + archive；10 Claude 回归腿。每步每宿主记录行 PASS/FAIL/NOT_EXECUTED + 输出摘录；本机不可用的宿主全标 NOT_EXECUTED，手册照交。

## Assumptions

- [ASSUMPTION] Codex 清单落 `plugin/.codex-plugin/plugin.json` 且不含 `$schema`——官方 Build plugins 页现行规范与示例如此；修正旧方案"插件根 plugin.json + $schema 必填"两点（官方文档已演进）。
- [ASSUMPTION] Codex 安装命令书写为 `codex plugin marketplace add wangdahoo/golden-hoop-spell` + `/plugins` 浏览器安装——官方用户页无 CLI install 子命令记载；若实测发现 install 子命令，以实测修正 README/E2E。
- [ASSUMPTION] pi 角色映射 `general-purpose→delegate`、`Explore→scout`、`Plan→planner`，且 pi 三泳道统一走 subagent 工具 `output`/`outputMode: "file-only"` 原生文件交接（context 泳道不沿用 Codex 的 dispatcher 捕获 + 探针程序）——契约指派 designer 按 pi-subagents 工具语义裁量；扩展原生落盘消解响应保真问题。
- [ASSUMPTION] pi 探测信号集 `{PI_SESSION_ID, PI_SESSION_FILE, PI_CODING_AGENT_DIR}` 与 agent dir 缺省 `~/.pi/agent`、git 落点 `~/.pi/agent/git/`——官方文档推导，未经本机实测；E2E 第 2 腿记录实际 marker 与布局供收紧。
- [ASSUMPTION] 仓库根新增 `package.json`（private、零依赖）作为 pi 清单——pi git 源安装唯一资源声明载体；`pi install` 对 git 源克隆后跑 `npm install`，零依赖 package.json 使其无害。
- [ASSUMPTION] pi 前置包钉为 `npm:pi-subagents`（nicobailon）——pi 生态同名包多个，契约泛指"pi-subagents 扩展包"；pi-host.md 以"实际工具表为准"条款自护版本漂移。
- [ASSUMPTION] 既有 references 全部零改动——宿主原语清点显示仅 coding-agent.md 需要覆盖，per-host 读序覆盖机制已足够，不需要指针豁免或话术中立化改造。
- [ASSUMPTION] E2E 手册取单文件多宿主形态 `docs/e2e-multi-host.md`——Open Space 落定项；理由见 Design 末节。

## Risks

- 技能名含冒号（`ghs:init` 等）不合 Agent Skills 名称字符集（小写字母/数字/连字符）→ pi 可能仅警告加载（文档："多数非法字段仅警告"）也可能拒载，Codex 侧冒号名同样未验证 → E2E 第 3 腿最先核实；拒载即记 FAIL 并上报契约修订（frontmatter 受"既有行零删改"保护，正文无可走空间）。
- pi-subagents 迭代快，builtin agent 名与参数语义漂移 → pi-host.md 强制 `{action: "list"}` 现场对账 + `delegate` 兜底；E2E 第 6 腿显式校验 output 文件 verbatim 语义，偏差回写 pi-host.md。
- pi `output` 文件被截断或摘要而非 verbatim → 完成判定只看 raw 文件解析结果 + parse 失败 retry 链兜底；E2E 第 6 腿核对定界符完整在场。
- Codex `${CLAUDE_PLUGIN_ROOT}` 在技能会话不展开且用户自定义安装位置使 cache-glob 失灵 → 指针块自举 + glob 双失败走 unknown→询问用户兜底，功能可达仅体验降级；E2E 第 4 腿记录实测。
- 用户未开 `multi_agent` / 未装 pi-subagents → per-host 前置块显式检测显式报告缺失（契约 Anti-Goal），README/E2E 第 0 节给开启与安装步骤；不提供静默降级路径。
- 新增 `.codex-plugin/` 与根 `package.json` 对 Claude 加载理论惰性，但属未验证假设 → E2E 第 10 腿 Claude 回归把关；Claude 清单与 marketplace.json 零改动有锚点把关。
- 缓存布局与 marker 集假设（含 `@` 扁平名）在其它版本失准 → host_compat.py 递归 glob + 名称过滤对布局形态不敏感，仍失败走 asked 兜底；E2E 第 2 腿记录真实布局作为收紧依据。

### Task 1: 三宿主探测脚本 host_compat.py 与测试
- Files: plugin/shared/scripts/host_compat.py, plugin/shared/scripts/test_host_compat.py
- Interfaces: `host_compat.py [--project-dir DIR]`；stdout 单行 JSON `{"host": "claude-code"|"codex"|"pi"|"unknown", "plugin_root": "<abs>"|null, "resolution": "env"|"cache-glob"|"asked"}`；exit 0 成功 / exit 1 unknown(asked)；纯函数 `detect(env: Mapping[str, str], paths: DetectPaths) -> dict`，`DetectPaths(claude_home: Path, codex_home: Path | None, pi_agent_dir: Path | None)`
- Points:
  - 按 Design 六步顺序实现：CODEX_ 前缀 marker → pi marker 三变量 → CLAUDE_PLUGIN_ROOT → PLUGIN_ROOT → claude cache-glob → unknown；root 有效性 = `<root>/shared/scripts/ghs_compat.py` 存在；递归 glob 加路径含 golden-hoop-spell 过滤；多命中取最高版本（数字感知元组, local 优先）
  - 复用 `ghs_compat.force_utf8_stdio()`；`--project-dir` 接受不参与探测；仅标准库；脚本自身不交互
  - test 用 tempfile 造 home/agent-dir 树 + 经 `detect(env, paths)` 注入，不触碰真实 `~/.codex`/`~/.claude`/`~/.pi`
- Anchors:
  - test_host_compat_claude_env_hit: CLAUDE_PLUGIN_ROOT 指向含 shared/scripts/ghs_compat.py 的 tmp 树 → host=claude-code, resolution=env, plugin_root=该值
  - test_host_compat_codex_cache_glob_flat_join: 设 CODEX_ marker, 无 env root, tmp cache 下 golden-hoop-spell@golden-hoop-spell 扁平布局 → host=codex, resolution=cache-glob
  - test_host_compat_pi_detection: PI_SESSION_ID marker 下 env root 命中 → host=pi, resolution=env; PI_CODING_AGENT_DIR marker + tmp agent-dir 内 git 落点布局 → host=pi, resolution=cache-glob
  - test_host_compat_double_failure_unknown: 相关 env 清空且 tmp 树无命中 → host=unknown, plugin_root=null, resolution=asked 且 CLI exit 1
  - command: `command python3 plugin/shared/scripts/host_compat.py` → exit 0 且 stdout 为含 host/plugin_root/resolution 三键的单行 JSON（本机 Claude 缓存必命中其一）

### Task 2: 七个 SKILL.md 的 Platform Adaptation 指针块
- Files: plugin/skills/ghs-init/SKILL.md, plugin/skills/ghs-plan/SKILL.md, plugin/skills/ghs-to-features/SKILL.md, plugin/skills/ghs-code/SKILL.md, plugin/skills/ghs-status/SKILL.md, plugin/skills/ghs-archive/SKILL.md, plugin/skills/ghs-force-archive/SKILL.md
- Points:
  - 按 Design 统一模板逐字插入（英文），位置为 frontmatter 与 H1 引言之后、第一个既有 `## ` 小节之前；七文件块内容逐字一致
  - 除该块外正文零改动，禁止改动任何既有行
- Anchors:
  - command: `grep -l "## Platform Adaptation" plugin/skills/*/SKILL.md | wc -l` → 7
  - command: `command python3 -c "import pathlib,re;bs=[re.search(r'## Platform Adaptation.*?(?=\n## )',pathlib.Path(str(p)).read_text(encoding='utf-8'),re.S).group(0) for p in pathlib.Path('plugin/skills').glob('*/SKILL.md')];assert len(bs)==7 and len(set(bs))==1"` → exit 0（七块逐字一致）
  - command: `git diff -- plugin/skills/ | grep -cE '^-[^-]'` → 0（既有行零删改）
  - command: `grep -c "host_compat.py" plugin/skills/*/SKILL.md` → 每文件 ≥1

### Task 3: codex-host.md Codex 侧操作手册
- Files: plugin/shared/references/codex-host.md
- Points:
  - 按 Design 六块编写, 全英文; 覆盖 multi_agent 前置与 [agents] 兜底, spawn_agent/wait_agent/followup_task/list_agents 主路径, 角色映射与 raw 写手分配（plan/review 泳道子代理写 raw, context 泳道 dispatcher 捕获 + 探针升级程序）, AskUserQuestion 降级成文条款, ${CLAUDE_PLUGIN_ROOT} 解析与自举, 自然语言 spawn fallback 与摘要回收风险注记
  - 全部 raw/scratch 路径话术用 `<run-id>`（禁 session_id 措辞）; parser 结果文件消费写明用宿主任意文件读取工具 Read; 版本与清单引用对齐 0.6.0 与 .codex-plugin/plugin.json
  - 既有 references 与 SKILL.md 不新增对本文件的引用; 既有 references 零改动
- Anchors:
  - command: `grep -cE "spawn_agent|followup_task|wait_agent|list_agents" plugin/shared/references/codex-host.md` → ≥4
  - command: `LC_ALL=C.UTF-8 grep -cP "[\x{4e00}-\x{9fff}]" plugin/shared/references/codex-host.md` → 0（全英文）
  - command: `grep -c "session_id" plugin/shared/references/codex-host.md` → 0（scratch 话术已迁移 <run-id>）
  - command: `git status --porcelain plugin/shared/references/` → 新增行仅 codex-host.md（既有文件零改动）

### Task 4: pi-host.md Pi 侧操作手册
- Files: plugin/shared/references/pi-host.md
- Points:
  - 按 Design 六块编写, 全英文, 块结构对齐 codex-host.md; 前置块含 `pi install npm:pi-subagents` 与显式缺失检测条款（无 subagent 工具时停止并报告, 禁止内联伪装）
  - 派发话术按 subagent 工具语义逐泳道成文: 单发 {agent, task}, output/outputMode file-only 文件交接, {tasks, concurrency} 并行, retry 重派 + Format Recovery 附录 + attempt<N+1>, 管理动作 status/resume 为可选
  - 角色映射表 delegate/scout/planner + "以 {action: list} 实际输出为准" 条款; AskUserQuestion 降级条款与 codex-host.md 逐字相同; /skill:ghs:<name> 调用形态与 ${CLAUDE_PLUGIN_ROOT} 自举说明
- Anchors:
  - command: `grep -ci "pi-subagents" plugin/shared/references/pi-host.md` → ≥2（前置与缺失报告在场）
  - command: `grep -cE "delegate|scout|planner" plugin/shared/references/pi-host.md` → ≥3（三个映射名在场）
  - command: `grep -ci "not installed" plugin/shared/references/pi-host.md` → ≥1（显式缺失报告条款在场）
  - command: `LC_ALL=C.UTF-8 grep -cP "[\x{4e00}-\x{9fff}]" plugin/shared/references/pi-host.md` → 0（全英文）
  - command: `git status --porcelain plugin/shared/references/` → 新增行恰为 codex-host.md 与 pi-host.md 两行（既有文件零改动）

### Task 5: Codex 清单与 Pi 清单
- Files: plugin/.codex-plugin/plugin.json, package.json
- Interfaces: plugin/.codex-plugin/plugin.json 顶层键 name("golden-hoop-spell")/version("0.6.0")/description/skills("./skills/") + 可选 author/repository/license/keywords(含 codex, openai), 无 $schema; package.json 顶层 name/version/private(true)/pi{"skills":["plugin/skills"]}
- Points:
  - name/version 与 plugin/.claude-plugin/plugin.json 严格一致; author/repository/license 从 Claude 清单原样映射; description 沿用或按宿主措辞（非空）
  - .claude-plugin/marketplace.json 与 plugin/.claude-plugin/plugin.json 零改动（legacy 读取为官方文档确认; E2E 失败才按 Design 程序追加, 本任务不预建 .agents/plugins/marketplace.json）
- Anchors:
  - command: `command python3 -c "import json;d=json.load(open('plugin/.codex-plugin/plugin.json',encoding='utf-8'));assert d['name']=='golden-hoop-spell' and d['version']=='0.6.0' and d['skills']=='./skills/' and all(k in d for k in ('name','version','description','skills'))"` → exit 0
  - command: `command python3 -c "import json;d=json.load(open('package.json',encoding='utf-8'));assert d['name']=='golden-hoop-spell' and d['version']=='0.6.0' and d.get('private') is True and d['pi']['skills']==['plugin/skills']"` → exit 0
  - command: `git diff --stat -- plugin/.claude-plugin/plugin.json .claude-plugin/marketplace.json` → 空输出（Claude 侧清单零改动）
  - command: `ls plugin/skills | wc -l` → 7（skills 字段指向的目录含七个技能目录）

### Task 6: 多清单一致性校验脚本与测试
- Files: plugin/shared/scripts/validate_manifests.py, plugin/shared/scripts/test_validate_manifests.py
- Interfaces: `validate_manifests.py [--repo-root DIR]`，stdout 逐项英文 OK/FAIL 行，exit 0 全过 / 1 任一失败
- Points:
  - 实现 Design 六项检查（codex 清单必填键与 kebab-case; 与 Claude 清单 name/version 严格相等 + 双 description 非空; skills 目录 7 个 SKILL.md; marketplace 单条目 source 解析; package.json pi.skills 解析与 version; 可选 .agents 清单交叉核对）; repo-root 缺省 `Path(__file__).resolve().parents[3]`; 复用 `ghs_compat.force_utf8_stdio()`
  - test_validate_manifests.py 用 tempfile fixture 覆盖: 一致通过, version 漂移, 缺 codex 清单, pi.skills 指向不存在目录
- Anchors:
  - test_validate_manifests_ok_fixture: 一致 fixture 输出含每个检查项 OK 且进程 exit 0
  - test_validate_manifests_version_mismatch: 篡改 fixture 中 .codex-plugin/plugin.json 的 version → exit 1 且输出含 "version mismatch"
  - test_validate_manifests_missing_codex_manifest: fixture 删除 .codex-plugin/plugin.json → exit 1
  - test_validate_manifests_pi_skills_glob_broken: fixture 中 package.json pi.skills 指向不存在目录 → exit 1
  - command: `command python3 plugin/shared/scripts/validate_manifests.py` → 对当前仓库 exit 0

### Task 7: README 两宿主安装章节
- Files: README.md, README-zh.md
- Points:
  - Installation 下各增两小节: `### Install on OpenAI Codex CLI`（marketplace add, /plugins 安装, multi_agent 前置, 自然语言或 @ 触发）与 `### Install on Pi`（pi install git 源或本地路径两条路, pi-subagents 前置, /skill:ghs:<name> 触发）; 中文版镜像
  - 安装命令与 docs/e2e-multi-host.md 第 2 节实测记录逐字一致（若实测修正过命令, 回改此处）
- Anchors:
  - command: `grep -c "Codex" README.md README-zh.md` → 两文件各 ≥1
  - command: `grep -c "pi install" README.md README-zh.md` → 两文件各 ≥1
  - command: `grep -cE "multi_agent|pi-subagents" README.md README-zh.md` → 两文件各 ≥1（前置条件行在场）
  - command: `grep -oE "pi install [a-z:@./_-]+" README.md README-zh.md | sort -u` → 命令词集合一致（人工核对输出）

### Task 8: E2E 双宿主手册编写与执行记录
- Files: docs/e2e-multi-host.md
- Points:
  - 按 Design 编写 0-10 共 11 节单文件多宿主手册, 每节每宿主记录行（PASS/FAIL/NOT_EXECUTED + 输出摘录）; 无 CLI 的宿主全部标 NOT_EXECUTED 且手册照交
  - 第 0 节分宿主前置: Codex（multi_agent 开启步骤 + [agents] 兜底建议）; pi（pi-subagents 安装与 python3）; 第 2 节每宿主本地 + 远程两路安装并记录真实缓存/落点布局与宿主 marker env 集（CODEX_* 与 PI_*），供收紧 host_compat.py 假设
  - 第 4 节 ${CLAUDE_PLUGIN_ROOT} 探针判据三结局（已展开 / 未展开但自举 + host_compat 接管 / unknown→询问用户）逐宿主记录
  - 第 6 节: Codex 腿按旧方案程序先验 spawn_agent 主路径链路再走 explorer 探针决策程序; pi 腿先 `{action: "list"}` 在位验证, 再验单发 output 文件 verbatim（定界符完整在场）, 再验双任务 {tasks} 并行各自落 raw
  - 第 8 节双特性并行验证给出最小 features.json 准备步骤（两无依赖特性）; 第 10 节 Claude 回归腿 `claude --plugin-dir plugin` 冒烟一个技能
- Anchors:
  - command: `grep -c "^## " docs/e2e-multi-host.md` → ≥11
  - command: `grep -cE "PASS|FAIL|NOT_EXECUTED" docs/e2e-multi-host.md` → ≥22（0-10 每节两宿主各至少一行）
  - command: `grep -cE "spawn_agent|multi_agent|pi-subagents" docs/e2e-multi-host.md` → ≥5（Codex 前置/第 6 腿与 pi 前置/安装/第 6 腿在场）
  - command: `grep -oE "pi install [a-z:@./_-]+" README.md README-zh.md docs/e2e-multi-host.md | sort -u` → 命令词集合一致（人工核对输出；E2E 第 2 节实测落定后执行）
  - [UNDEFINED-INPUT] 本机任一宿主 CLI 不可用: 该宿主全部步骤标 NOT_EXECUTED 并继续交付手册, 不中止任务
