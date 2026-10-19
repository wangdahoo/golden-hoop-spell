# Codex 双生态原生插件发布与功能对等兼容层

> SCOPE CONTRACT — frozen at kickoff. 由 dispatcher 维护并经用户确认；
> 正文不得扩大本契约范围，冲突时删正文不删契约。

## Intent
同一套 skills 源，以 Anthropic marketplace 与 Codex plugin/marketplace 双生态原生发布；Codex 侧功能与 Claude 侧完全一致（含多代理编排），机制差异收敛到最小兼容层；同时作为 ghs 流程的 dogfood 轮次。

## Goals
- 仓库可被 `codex plugin marketplace add` 添加，golden-hoop-spell 可被 Codex 原生安装；Claude 侧发布方式不变
- 新增 Agent Plugins 标准清单（plugin.json），Claude 侧加载零影响
- Codex 安装后 7 个技能全部可发现、可调用
- 功能对等：ghs:plan 三角色流水线（Context/设计/评审子代理）与 ghs:code `--parallel` 并行模式在 Codex 上以原生 Subagents 等价运转——派发、并行、结果回收、信号解析全链路可用
- 兼容层：host 差异只允许存在于新增的适配文件/小节；SKILL.md 正文、shared/scripts、references、assets 尽可能 100% 复用
- `${CLAUDE_PLUGIN_ROOT}` 等路径引用在 Codex 上下文可解析（验证 Codex 的兼容变量行为，必要时兼容层接管）
- README 提供 Codex 安装章节（安装命令与技能触发方式）
- 端到端验证：Codex CLI 上 install → init → plan（完整三角色）→ code（单特性）→ status → archive 全链路实测；`--parallel` 至少一次双特性并行验证；若本机无 Codex CLI 则交付可复现验证手册

## Non-Goals
- 不使用 Codex hooks/MCP/`.app.json` 扩展点（ghs 现无 hooks/MCP，保持为零）
- 不做 ChatGPT 桌面/网页端形态的专门适配与验证，仅 Codex CLI
- 不改动 `plugin/skills` 与 `plugin/shared` 现有布局及 Claude 安装路径
- 不维护第二份技能内容副本（单一技能源）
- 不用自定义子代理 TOML（插件机制不支持打包 agents；用内建类型 + 派发词已满足）

## Anti-Goals
- Claude marketplace 现有安装/使用回归
- Codex 侧任一技能可安装但功能缺失或静默失败（相对 Claude 侧的功能阉割即失败）
- 双 manifest 版本漂移且无同步/校验手段
- 以复制/分叉技能正文的方式实现 Codex 支持
- 依赖已废弃特性（custom prompts）

## Decisions
- Codex 子代理派发用内建类型映射：general-purpose→default、Explore→explorer、Plan→default+设计指令词
- 长输出子代理（计划正文/评审报告）改为文件交接：子代理写盘、回传路径 + 完成信号，parser 走 --input-file；两侧机制不同、功能等价
- 交互原语允许形态差异：Claude 的 AskUserQuestion 在 Codex 侧降为文本提问（单题、选项枚举、默认推荐语义保持一致）
- 采用可移植清单 plugin.json（官方推荐路径）
- marketplace 清单优先复用 .claude-plugin/marketplace.json 的 legacy 兼容读取，缺字段补字段；是否另建 .agents/plugins/marketplace.json 由 designer 裁量
- 插件标识保持 golden-hoop-spell；版本与 0.5.1 体系对齐

## Open Space
- 兼容层的物理形态：host-adapter 参考文件 vs SKILL.md 内条件小节 vs 探测脚本
- host 探测方式（环境变量探测脚本 vs 文档约定）
- plugin.json 字段映射与版本单源化手段
- `${CLAUDE_PLUGIN_ROOT}` 的验证方法与保底替换方案
- E2E 手册形态

## Global Constraints
- Codex marketplace 清单：原生 .agents/plugins/marketplace.json 或 legacy .claude-plugin/marketplace.json，内容单源
- Codex plugin.json 必填 $schema、name（kebab-case）、version、description
- 插件内技能路径 skills/<name>/SKILL.md 自动发现
- Python 调用一律 command python3
- 语言政策沿用 CLAUDE.md：中文文档/commit，英文标识符/日志/错误串
- 不引入新重依赖，工具用 Python 标准库

## Current State

- 纯内容插件仓库：7 个技能（`plugin/skills/<name>/SKILL.md` 单文件）+ `plugin/shared/{scripts,references,assets}`；版本号唯一位置 `plugin/.claude-plugin/plugin.json`（0.5.1）；marketplace 清单 `.claude-plugin/marketplace.json`（name=golden-hoop-spell，单条目 source `./plugin`）。
- 宿主耦合面（快照 §4）：43 处 `${CLAUDE_PLUGIN_ROOT}`（脚本调用 / Read 参考 / 资产路径三种形态）；4 处 JSON 子代理派发（ghs-plan×3、ghs-code×1）+ coding-agent.md 内嵌 prompt 模板；AskUserQuestion 20+ 处；无 hooks/agents/commands/AGENTS.md。
- 关键既有事实（决定兼容层体积极小）：两个解析器均已原生支持 `--input-file`；SKILL.md 已规定 dispatcher 把子代理完整响应 verbatim 落盘为 raw 文件再喂 parser——context 用 `<PROJECT_DIR>/.ghs/plans/.tmp/<session_id>.context.raw`，并行实现用 `<PROJECT_DIR>/.ghs/parallel/<plan_id>/<feature_id>.raw.attempt<N>`。因此 Codex 侧唯一要改的职责是「谁写 raw 文件」（计划正文/评审报告泳道：Claude=dispatcher 写，Codex=子代理写后回传路径；Context 泳道两侧均由 dispatcher 捕获落盘，机制见 Design），下游解析、retry、状态机零改动。
- 插件内技能布局 `skills/<name>/SKILL.md` 与 Codex 自动发现约定同构，无需移动任何技能；SKILL.md 正文以英文为主。
- 测试模式：7 个 `test_*.py`，标准库 unittest，`command python3` 直接运行，无 pytest。
- 七个 SKILL.md 结构同构（已核实）：frontmatter → H1 → 引言段 → 第一个既有 `## ` 小节，指针块插入位置在七文件上均成立。

## Design

### 兼容层总体形态（Open Space：物理形态 + host 探测——本修订落定）

采用 superpowers v6.3.0 实证同型（契约已核事实）：**技能正文零宿主差异**——7 个 SKILL.md 各插入统一 ~6 行英文 Platform Adaptation 指针块（add-only，Claude 侧读到即跳过）；宿主差异知识全部外置到 `plugin/shared/references/codex-host.md`（Codex 侧操作手册，Claude 侧永不读取）；通用逻辑（host 探测 + plugin root 三级解析）下沉为通用脚本 `plugin/shared/scripts/host_compat.py`。加上新增 Codex 清单与清单校验脚本（各有专节），兼容层共五个新增件；SKILL.md 正文（指针块之外）、shared 既有脚本、references、assets 零改动。不采纳正文内条件小节形态（用户裁决：「在一个 skill 文件内容中做兼容特别傻」）；三级解析不写成正文文字教程（同一裁决：「该做成通用脚本的做成通用脚本」）。

**单点解析原则**（保留）：插件根路径只在主会话解析一次；派发子代理前，主会话把 prompt 模板中的 `${CLAUDE_PLUGIN_ROOT}` 字面替换为实际路径——子代理永远不面对未解析变量（coding-agent.md 因此零改动）。

**指针块自举**：指针块命令本身引用 `${CLAUDE_PLUGIN_ROOT}`，宿主未展开该变量时会话无法按字面执行。此时会话以当前执行的 SKILL.md 所在路径推导插件根（`skills/<name>/` 上两级）定位并运行 host_compat.py，脚本以 cache-glob 交叉归一（两种缓存布局都试，含 `golden-hoop-spell@golden-hoop-spell` 扁平连接名）；仍失败则脚本输出 unknown + 非零 exit，主会话询问用户。Codex 对该变量的真实兼容行为由 E2E 第 4 步实测记录（Goal 6）。

### host_compat.py 通用脚本（Open Space：host 探测）

- CLI：`command python3 plugin/shared/scripts/host_compat.py [--project-dir DIR]`（`--project-dir` 仅为与其他 shared 脚本调用形态对称而接受，不参与探测逻辑）；复用 `ghs_compat.force_utf8_stdio()`；仅 Python 标准库。
- stdout 输出单行 JSON：`{"host": "claude-code" | "codex" | "unknown", "plugin_root": "<abs path>" | null, "resolution": "env" | "cache-glob" | "asked"}`。exit 0 = 解析成功；exit 1 = `{"host": "unknown", "plugin_root": null, "resolution": "asked"}`——脚本自身不交互，主会话据此询问用户插件根路径（resolution 记 asked）。
- 探测顺序（host 判定与根解析，首中即停；root 有效性判据 = `<值>/shared/scripts/ghs_compat.py` 存在）：
  1. 存在 Codex 特征 env（任意 `CODEX_` 前缀变量，含 `CODEX_HOME`）→ host=codex：依次试 `CLAUDE_PLUGIN_ROOT`（Codex 兼容展开该变量的场景，即 Goal 6 验证点）、`PLUGIN_ROOT`，有效即 resolution=env；否则递归 glob `$CODEX_HOME/plugins/cache`（缺省 `~/.codex/plugins/cache`）下 `**/shared/scripts/ghs_compat.py`、按路径含 `golden-hoop-spell` 过滤，命中即 resolution=cache-glob；
  2. 无 Codex 特征：`CLAUDE_PLUGIN_ROOT` 有效 → claude-code / env；
  3. `PLUGIN_ROOT` 有效 → claude-code / env；
  4. 递归 glob `~/.claude/plugins/cache/**/shared/scripts/ghs_compat.py`（同名过滤）→ claude-code / cache-glob；
  5. 全部失败 → unknown / asked / exit 1。
  Codex 特征 env 优先于 `CLAUDE_PLUGIN_ROOT` 判定 host，防「Codex 兼容展开该变量 → 误判为 Claude 宿主 → 跳过 codex-host.md」。
- 多命中取最高版本目录（数字感知元组比较，`local` 优先）。解析用「递归 glob + 路径含名过滤」而非固定层级模式，天然同时覆盖 `marketplace/插件/版本` 层级布局与 `golden-hoop-spell@golden-hoop-spell` 扁平连接布局（修正原双层级 glob 假设，两种布局都试）。
- 模块暴露纯函数 `detect(home: Path, env: Mapping[str, str]) -> dict`（CLI 为薄壳），供测试注入 tmp home 与 env，不触碰真实 `~/.codex`/`~/.claude`。
- 配套 `test_host_compat.py`（unittest + tempfile + env 打桩）：env 命中、`@` 扁平名 glob 命中、双失败返回 unknown、Codex marker 下的 env 路由。

### Platform Adaptation 指针块（7 个 SKILL.md，add-only）

统一模板（英文，七文件逐字一致，实现时按此转录；除该块外正文零改动）：

```markdown
## Platform Adaptation
- Claude Code hosts: nothing to do — proceed as written below.
- Other hosts (e.g. OpenAI Codex CLI): run
  `command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/host_compat.py`,
  then read `<plugin_root>/shared/references/codex-host.md` and follow it wherever it
  supersedes a host-specific instruction below (subagent dispatch, interactive questions).
```

插入位置：frontmatter 之后、H1 引言段之后、第一个既有 `## ` 小节之前。

### codex-host.md 参考文件（Open Space：物理形态）

`plugin/shared/references/codex-host.md`，全英文（含所有代码标识符与话术），Claude 侧永不读取。六个内容块（吸收原 Design 全部 Codex 专属知识）：

1. **Prerequisites**：`~/.codex/config.toml` 添加 `[features] multi_agent = true`（缺失则主路径不可用，见第 6 块 fallback）；建议 `[agents] default_subagent_model` / `default_subagent_reasoning_effort` 机器级兜底——ghs 派发不指定 per-spawn model，由兜底承接。
2. **Dispatch main path**：`spawn_agent {fork_turns: "none"}`（干净上下文分叉，对齐 ghs 子代理模型）为主机制，取代自然语言 spawn；子代理把完整定界符输出 verbatim 写入既有 raw 约定路径，最终回复只含该路径与既有完成声明；等待用 `wait_agent` 事件订阅（空闲时有界等待 `timeout_ms` 300000–600000，不短轮询；完成答案经 mailbox 随下一回合到达）；对账用 `list_agents`；V2 生命周期无 `close_agent`（完成子代理自动回收）；`followup_task` 承接 retry/Format Recovery——向同一代理续发消息与下一次 attempt 路径，不重派新代理。
3. **Role mapping & raw writers**：`general-purpose`/`Plan` → `default`（Plan 泳道 prompt 原文保留 plan-designer.md 指令与契约头；Reviewer 保留 plan-reviewer.md）；`Explore` → `explorer`（只读）。写手分配：计划正文/评审报告泳道 = 子代理写 `.tmp/<session_id>.plan.raw` / `.tmp/<session_id>.review.raw` 后回传路径；Context 泳道规范默认 = explorer 在最终响应输出完整定界快照、dispatcher 沿用既有正文机制捕获落盘 `.tmp/<session_id>.context.raw`（不依赖子代理写权限，两侧同构）；A 方案升级门控不变（见 E2E 第 6 步）。Codex 无 MCP：跳过 codegraph 探针，`CODEGRAPH_AVAILABLE` 恒为 false，走 `PROMPT_TEMPLATE_GREP` 泳道。
4. **AskUserQuestion downgrade**（原文照录，含单轮批量语义）：`On hosts without AskUserQuestion, ask the user in plain text instead, keeping the original option-table semantics exactly. Per question, enumerate the options verbatim (original numbering and wording), mark the recommended option with a one-line reason, and wait for the user's reply before proceeding on the chosen branch. Keep the original batching form: questions the body groups into one single batched AskUserQuestion (e.g. builder questions, one batch of up to 5) are enumerated together in a single message and answered in order; questions asked individually stay one per message.`
5. **`${CLAUDE_PLUGIN_ROOT}` resolution**：变量未展开时按指针块自举调 host_compat.py，以脚本 JSON 输出为准；unknown 时按其 exit 语义询问用户后继续。
6. **Fallback**：multi_agent 不可用时降级自然语言并行 spawn（逐代理 instructions + 交接附录），显式注明摘要回收风险——完成判定只看 raw 文件解析结果、不信任摘要内容；ghs-code `--parallel` 每代理写 `<PROJECT_DIR>/.ghs/parallel/<plan_id>/<feature_id>.raw.attempt<N>`，attempt 编号由主会话派发词给出，retry 写 attempt<N+1>；回收从既有 Verification Phase 步骤 2（`parse_completion_signal.py --input-file`）verbatim 继续，`dispatch_start_iso`、前置门 sanity check、unknown→retry→User Decision Handling 链路不变。

派发话术按 spawn_agent 工具语义重写为英文操作说明（取代原正文中英混排模板），逐泳道给出：spawn 参数、prompt 组成（已字面替换根路径的既有模板 + 交接附录）、raw 路径、最终回复形态。retry 语义两侧通用：同类型同模板重派（multi_agent 下用 followup_task 续发同一代理），Format Recovery 附录给出本次 attempt 确切落盘路径，既有 `.raw.retry<T>` 命名与 `MAX_RETRY` 状态机不变。

### 清单与版本单源化（Open Space：字段映射 + 版本单源手段）

- 新增 `plugin/plugin.json`（Codex 清单，置于插件根；marketplace source `./plugin` 即指向此目录）：必填 `$schema`（字面量以官方文档 developers.openai.com/plugins/build/plugins 示例为准，契约允许缺口查官方文档）、`name: "golden-hoop-spell"`、`version: "0.5.1"`、`description`；可选 `author`/`repository`/`license` 从 Claude 清单原样映射，`keywords` 增补 `codex`/`openai`。
- marketplace 清单：**不另建** `.agents/plugins/marketplace.json`，复用 `.claude-plugin/marketplace.json` 的 legacy 兼容读取（契约优先项），达成内容单源。仅当 E2E 实测 legacy 读取或 `./plugin` source 解析失败时才建原生清单，并同步纳入下述校验脚本的交叉核对分支。
- 版本漂移防护 = 校验脚本 + 发布纪律（双改），不做生成式同步——校验手段已满足 Anti-Goal，生成式方案是无契约依据的机器。
- 新增 `plugin/shared/scripts/validate_manifests.py`：`command python3 plugin/shared/scripts/validate_manifests.py [--repo-root DIR]`（默认 `Path(__file__).resolve().parents[3]`；`import ghs_compat.force_utf8_stdio`）。逐项输出英文 OK/FAIL 行，exit 0 全过 / 1 任一失败。检查项：(1) `plugin/plugin.json` 存在且含四个必填键；(2) name 为 `golden-hoop-spell` 且 kebab-case；(3) 与 `plugin/.claude-plugin/plugin.json` 的 name、version 严格相等，description 双方非空（措辞允许差异）；(4) `.claude-plugin/marketplace.json` 恰含一个 name=`golden-hoop-spell` 条目，其 source 路径解析到同时含 `plugin.json` 与 `skills/` 的目录；(5) 若存在 `.agents/plugins/marketplace.json` 则与 legacy 清单逐条目核对 name/source 一致。配套 `test_validate_manifests.py`（unittest + tempfile fixture）。

### `${CLAUDE_PLUGIN_ROOT}` 验证与保底（Goal 6）

验证放 E2E 手册第 4 步（探针）：在 Codex 安装后的目标项目触发 `/ghs:status`（自然语言触发），记录命令中变量是否被宿主展开。三种结局功能都可达：已展开 → 指针块命令直接可用；未展开 → 指针块自举（SKILL.md 路径推导插件根）+ host_compat.py 归一接管；双失败 → 脚本输出 unknown，主会话询问用户（resolution=asked）。手册记录实测结论与真实 cache 目录布局、Codex 特征 env marker 集，作为后续收紧 host_compat.py glob 假设的依据。

### ghs-plan 三角色 Codex 映射（Goal 4 + Decisions）

机制知识全部归 codex-host.md（上节第 2/3/4 块），Design 只保留架构不变量：

- 三角色流水线结构、串行单代理、契约头/六状态机/`MAX_RETRY`、parse_delimited_output.py 多级 fallback 两侧共用零改动；唯一职责差异是「谁写 raw 文件」——计划正文/评审报告泳道 Claude=dispatcher 写、Codex=子代理写后回传路径；Context 泳道两侧均 dispatcher 捕获落盘。
- 类型映射落契约 Decision：general-purpose→default、Explore→explorer、Plan→default+设计指令词（prompt 原文不变）。
- A 方案升级程序不变（非本版默认）：仅当 E2E 第 6 步探针判「可写盘或被摘要」且用户现场批准修订契约两行 Decision（文件交接枚举扩入 Context 快照；类型映射改为 `Explore→default`+只读探索约束词）后启用——Context 泳道切换为与 Plan/Reviewer 泳道同构的文件交接（`default` 类型、子代理写 `.tmp/<session_id>.context.raw` 并回传路径）。批准前契约保持冻结、正文以 explorer 方案为准。

### ghs-code `--parallel` Codex 映射（Goal 4）

- 单特性模式：无子代理，指针块 + host_compat.py 已覆盖（仅路径解析）。
- 并行模式：调度核心（parallel_utils.py 批次、CONTEXT RESET prompt、completion 信号协议）两侧共用零改动；Codex 侧差异仅派发/回收形态——`spawn_agent` 并行派发 N 代理（每代理 prompt = 已替换根路径的 CONTEXT RESET 模板 + 交接附录写 `.raw.attempt<N>`、只回路径与完成声明），`wait_agent` 等待、回收从 Verification Phase 步骤 2 verbatim 继续（细节归 codex-host.md 第 6 块）。

### README 的 Codex 安装章节（Goal 7 + Open Space）

- `README.md` Installation 下新增 `### Install on OpenAI Codex CLI`，`README-zh.md` 对应中文小节；命令与 `docs/codex-e2e.md` 实测通过的命令逐字一致。

### E2E 手册形态（Goal 8 + Open Space）

新增 `docs/codex-e2e.md` 单文件手册，章节：0 前置条件（Codex CLI、`config.toml` `[features] multi_agent = true` 检查、建议 `[agents] default_subagent_model`/`default_subagent_reasoning_effort` 兜底、python3）；1 scratch 目标项目准备；2 安装（本地路径与 GitHub 源两条路）；3 七技能发现性检查；4 `${CLAUDE_PLUGIN_ROOT}` 探针（并顺带记录 `~/.codex/plugins/cache` 真实目录布局——marketplace/插件/版本各级的实际嵌套或 `@` 扁平连接形态——与 Codex 特征 env marker 集，供收紧 host_compat.py 的 cache-glob 假设）；5 init；6 plan 完整三角色（spawn_agent 主路径可用性验证与 fallback 行为记录 + explorer 探针决策程序，见下）；7 code 单特性；8 code `--parallel` 双特性；9 status + archive；10 Claude 侧回归腿（`claude --plugin-dir plugin` 冒烟一个技能）。每步附记录行（PASS/FAIL/NOT_EXECUTED + 实际输出摘录）；本机无 Codex CLI 时全部标 NOT_EXECUTED，手册照交（Goal 的可复现手册分支）。

**第 6 步 spawn_agent 主路径验证**（新增，先于 explorer 探针）：确认 multi_agent 开启后，按 codex-host.md 主路径派发一次真实子代理（`fork_turns: "none"`），验证 spawn 派发 → `wait_agent` 有界等待 → mailbox 回收 → `followup_task` 续发 → `list_agents` 对账全链路，记录 PASS/FAIL。multi_agent 不可用 → 记录 fallback（自然语言 spawn）实际行为与摘要回收风险观察，后续三角色腿按 fallback 执行并在记录行注明。

**第 6 步内嵌 explorer 探针决策程序**（不变，Builder Question 1 = C 的编码；契约保持冻结，两观察 + 一批准门）：
1. 写盘观察：向 explorer Context 子代理的派发词追加一条探针指令——把一行文本写入 `<PROJECT_DIR>/.ghs/explorer-write-probe.tmp` 并回告成功与否；记录「可写盘 / 不可写盘」（探针文件随后删除）。
2. 保真观察：正常走完 explorer Context 泳道，核对主会话收到的响应是否保留 `<<<CONTEXT_SNAPSHOT_START/END>>>` 定界符与完整正文；记录「保真 / 被摘要」。
3. 判读：被摘要（dispatcher 捕获不可靠）或可写盘（只读前提不成立、文件交接可行）→ 触发升级：现场经用户确认修订契约两行 Decision（文件交接枚举扩入 Context 快照；类型映射改为 `Explore→default`+只读探索约束词），批准后本轮及后续切换 A 方案（`default` + 文件交接，与 Plan/Reviewer 泳道同构）；「不可写盘且保真」或用户不批准 → 维持规范默认 explorer 方案。若被摘要但用户不批准，第 6 步 Context 腿记 FAIL，由既有 parse 失败→retry→升级路径兜底，手册如实记录。
4. 记录行必含：写盘能力、保真度、最终分支；若升级，附「契约两行 Decision 已获用户确认修订」。

## Assumptions

- [ASSUMPTION] 不另建 `.agents/plugins/marketplace.json`，单一 legacy 清单——契约明示优先复用；E2E 证明 legacy 读取/`./plugin` source 解析失败时才建，届时纳入 validate 脚本交叉核对。
- [ASSUMPTION] Context 泳道为「双分支 + 探针门控 + 用户批准后修订契约」的程序假设：规范默认 = 契约忠实设计（`Explore→explorer`，dispatcher 沿用既有正文机制捕获落盘）；E2E 第 6 步内嵌 explorer 探针（写盘能力 + 输出保真度双观察），判「可写盘或被摘要」且用户现场批准修订契约两行 Decision 后，本轮切换 A 方案（`Explore→default`+只读探索约束词、Context 快照纳入文件交接）；「不可写盘且保真」或用户不批准则维持 explorer，批准前契约冻结不改。
- [ASSUMPTION] 版本单源化 = 校验脚本 + 发布双改纪律，description 允许两侧措辞差异（仅校验非空）——Claude 清单描述含 "with Claude Code" 字样，为 Claude 侧零改动不改它。
- [ASSUMPTION] `plugin/plugin.json` 的 `$schema` 字面量以官方文档示例为准（契约许可缺口查官方文档）；Codex 安装命令书写为 `codex plugin install golden-hoop-spell@golden-hoop-spell` 形态，最终以 E2E 实测输出修正 README。
- [ASSUMPTION] `.claude-plugin/marketplace.json` 仅在 Codex 实测报缺字段时追加纯新增键（如 `policy.installation`/`category`），既有键一律不动。
- [ASSUMPTION] host_compat.py 探测信号集具体化：Codex 特征 env = 任意 `CODEX_` 前缀变量（含 `CODEX_HOME`），Codex 缓存基准 = `$CODEX_HOME/plugins/cache`（缺省 `~/.codex/plugins/cache`）——基准路径与 marker 集未经验证；解析用递归 glob + 路径含 `golden-hoop-spell` 过滤，同时覆盖层级与 `@` 扁平连接两种布局（修正原双层级 glob 假设）；E2E 第 4 步记录真实布局与 marker 集据实测收紧；双失败 unknown→主会话询问用户兜底保证功能可达。
- [ASSUMPTION] 指针块自举依赖「宿主向会话暴露当前执行的 SKILL.md 文件路径」：`${CLAUDE_PLUGIN_ROOT}` 未展开时会话以 `skills/<name>/` 上两级推导插件根定位 host_compat.py；该宿主行为未经验证，E2E 第 4 步实测，失败时落 unknown→询问用户兜底。

## Risks

- Codex legacy 读取可能不接受 `"source": "./plugin"` 字符串形态 → E2E 第 2 步最先实测；失败即按 Assumption 1 切原生清单（改动仅一个文件，技能面零波及）。
- `${CLAUDE_PLUGIN_ROOT}` 未展开且用户自定义安装位置使 cache-glob 失灵 → host_compat.py 输出 unknown + 非零 exit，主会话询问用户，功能可达仅体验降级；实测结论记录进手册供后续收紧。
- spawn_agent 工具链实测偏差（Codex 版本/预设差异致工具缺失或语义不同）→ E2E 第 6 步主路径验证显式覆盖；不可用时按 codex-host.md fallback（自然语言 spawn）接管并记录摘要回收风险，`codex exec` 备选仅评估不预建代码路径。
- Codex 子代理「摘要回收」丢信号 → 文件交接泳道（计划正文/评审报告）完成判定只看 raw 文件解析结果、不信任 mailbox 摘要内容；Context 泳道依赖 explorer 响应保真，由 parse 失败→retry（followup_task 续发）→既有升级路径兜底，E2E 第 6 步探针门控（触发且获批准即升级文件交接）。
- 用户未开启 `multi_agent`（feature 默认关）→ 主路径不可用：codex-host.md 前置条件与 README/E2E 第 0 节给出开启步骤，fallback 语义成文，第 6 步记录实际行为。
- marketplace.json 新增键可能影响 Claude 端解析 → 只加不改；E2E 第 10 步 Claude 回归腿把关，触发即回退该键并记录。

### Task 1: 通用 host 探测与插件根解析脚本 host_compat.py
- Files: plugin/shared/scripts/host_compat.py, plugin/shared/scripts/test_host_compat.py
- Interfaces: `host_compat.py [--project-dir DIR]`，stdout 单行 JSON `{"host": "claude-code"|"codex"|"unknown", "plugin_root": "<abs path>"|null, "resolution": "env"|"cache-glob"|"asked"}`，exit 0 解析成功 / exit 1 unknown(asked)；模块级纯函数 `detect(home: Path, env: Mapping[str, str]) -> dict`
- Points:
  - 实现 Design 节 5 步探测顺序：Codex 特征 env（任意 `CODEX_` 前缀）优先判 host；root 有效性 = `<值>/shared/scripts/ghs_compat.py` 存在；递归 glob `**/shared/scripts/ghs_compat.py` 按路径含 `golden-hoop-spell` 过滤（层级与 `@` 扁平两种布局都覆盖）；多命中取最高版本（数字感知元组比较，`local` 优先）
  - 复用 `ghs_compat.force_utf8_stdio()`；`--project-dir` 接受但不参与探测；仅 Python 标准库；脚本自身不交互，unknown 时输出固定 JSON 并 exit 1
  - test 用 tempfile 造 home 树 + env 打桩（经 `detect(home, env)` 注入），不触碰真实 `~/.codex`/`~/.claude`
- Anchors:
  - test_host_compat_env_hit: `CLAUDE_PLUGIN_ROOT` 指向含 `shared/scripts/ghs_compat.py` 的 tmp 树 → host=claude-code、resolution=env、plugin_root=该值
  - test_host_compat_glob_flat_join: tmp home 的 `$CODEX_HOME/plugins/cache` 下 `golden-hoop-spell@golden-hoop-spell` 扁平布局、无 PLUGIN_ROOT → host=codex、resolution=cache-glob、plugin_root 位于扁平连接目录内
  - test_host_compat_codex_marker_env: 设 `CODEX_*` marker 且同时给 `CLAUDE_PLUGIN_ROOT` 与 `PLUGIN_ROOT` → host=codex、resolution=env、root 取自 `CLAUDE_PLUGIN_ROOT`（marker 优先 + 兼容变量次序）
  - test_host_compat_double_failure_unknown: 相关 env 清空、tmp home 无 cache 命中 → host=unknown、plugin_root=null、resolution=asked 且 CLI exit 1
  - command: `command python3 plugin/shared/scripts/host_compat.py` → exit 0 且 stdout 为含 host/plugin_root/resolution 三键的 JSON（本机 Claude 缓存已安装本插件，env 或 cache-glob 必命中其一）

### Task 2: 七个 SKILL.md 的 Platform Adaptation 指针块
- Files: plugin/skills/ghs-init/SKILL.md, plugin/skills/ghs-plan/SKILL.md, plugin/skills/ghs-to-features/SKILL.md, plugin/skills/ghs-code/SKILL.md, plugin/skills/ghs-status/SKILL.md, plugin/skills/ghs-archive/SKILL.md, plugin/skills/ghs-force-archive/SKILL.md
- Points:
  - 按 Design 节统一模板逐字插入（英文），位置为 frontmatter 与 H1 引言之后、第一个既有 `## ` 小节之前；七文件块内容完全一致
  - 除该块外正文零改动，禁止改动任何既有行（原 Task 3/4/5 的内嵌适配小节全部撤销，宿主差异归 codex-host.md）
- Anchors:
  - command: `grep -l "## Platform Adaptation" plugin/skills/*/SKILL.md | wc -l` → 7
  - command: `git diff --numstat -- plugin/skills/` → 七个 SKILL.md 删除列均为 0
  - command: `git diff -- plugin/skills/ | grep -cE '^-[^-]'` → 0（既有行零删改，新增行仅指针块）
  - command: `grep -c "host_compat.py" plugin/skills/*/SKILL.md` → 每文件 ≥1

### Task 3: codex-host.md Codex 侧操作手册
- Files: plugin/shared/references/codex-host.md
- Points:
  - 按 Design 节六个内容块编写，全英文；覆盖原 plan/code 两技能宿主差异全集（multi_agent 前置与 `[agents]` 兜底、spawn_agent 主路径与 wait_agent/followup_task/list_agents、角色映射与 raw 写手分配、AskUserQuestion 降级原文、`${CLAUDE_PLUGIN_ROOT}` 解析、自然语言 spawn fallback 及摘要回收风险注记）
  - 派发话术按 spawn_agent 工具语义写成英文操作说明，逐泳道：spawn 参数、prompt 组成（已替换根路径的既有模板 + 交接附录）、raw 路径、最终回复形态；retry = followup_task 续发同一代理 + Format Recovery 附录给本次 attempt 确切落盘路径
  - 既有 references 与 SKILL.md 不新增对本文件的引用（唯一入口是 Task 2 指针块）；既有 references 零改动
- Anchors:
  - command: `grep -cE "spawn_agent|followup_task|wait_agent|list_agents" plugin/shared/references/codex-host.md` → ≥4（四个工具名各至少 1 次）
  - command: `grep -cP "[\x{4e00}-\x{9fff}]" plugin/shared/references/codex-host.md` → 0（全英文）
  - command: `grep -c "host_compat.py" plugin/shared/references/codex-host.md` → ≥1（路径解析章节在场）
  - command: `git status --porcelain plugin/shared/references/` → 仅新增 codex-host.md 一行（既有文件零改动）

### Task 4: 新增 Codex 插件清单 plugin/plugin.json
- Files: plugin/plugin.json, .claude-plugin/marketplace.json
- Interfaces: plugin/plugin.json 顶层键含 $schema、name("golden-hoop-spell")、version("0.5.1")、description；可选 author/repository/license/keywords
- Points:
  - $schema 字面量复制自官方文档 developers.openai.com/plugins/build/plugins 的 plugin.json 示例，不得自造 URL
  - name/version 与 plugin/.claude-plugin/plugin.json 严格一致；description 沿用或 Codex 措辞（非空）；keywords 增补 "codex"、"openai"
  - 仅当本机有 Codex CLI：`codex plugin marketplace add <本仓库本地路径>` 试装；按报错向 .claude-plugin/marketplace.json 追加纯新增键（不改既有键）；若报 source 形态不兼容则按 Assumption 1 改建 .agents/plugins/marketplace.json 并在提交说明中记录触发原因
- Anchors:
  - command: `command python3 -c "import json;d=json.load(open('plugin/plugin.json',encoding='utf-8'));assert d['name']=='golden-hoop-spell' and d['version']=='0.5.1' and all(k in d for k in ('$schema','name','version','description'))"` → exit 0
  - command: `git diff --stat -- plugin/.claude-plugin/plugin.json` → 空输出（Claude 清单零改动）
  - [UNDEFINED-INPUT] 本机无 Codex CLI: 跳过 marketplace add 实测，任务输出记录 "deferred to E2E manual"，不阻塞完成

### Task 5: 清单一致性校验脚本与测试
- Files: plugin/shared/scripts/validate_manifests.py, plugin/shared/scripts/test_validate_manifests.py, CLAUDE.md
- Interfaces: `validate_manifests.py [--repo-root DIR]`，stdout 逐项英文 OK/FAIL 行，exit 0 全过 / 1 任一失败
- Points:
  - 实现 Design 节列出的 5 项检查；repo-root 默认 `Path(__file__).resolve().parents[3]`；复用 `ghs_compat.force_utf8_stdio()`
  - test_validate_manifests.py 用 tempfile fixture 覆盖：一致通过、version 漂移、缺必填字段、marketplace source 指向不存在目录
  - CLAUDE.md 追加一行：发布前运行 `command python3 plugin/shared/scripts/validate_manifests.py`
- Anchors:
  - test_validate_manifests_ok_fixture: 一致 fixture 输出含每个检查项 OK 且进程 exit 0
  - test_validate_manifests_version_mismatch: 篡改 fixture 中 plugin.json 的 version → exit 1 且输出含 "version mismatch"
  - test_validate_manifests_missing_required_field: 删除 $schema/name/version/description 之一 → exit 1
  - command: `command python3 plugin/shared/scripts/validate_manifests.py` → 对当前仓库 exit 0

### Task 6: README 的 Codex 安装章节
- Files: README.md, README-zh.md
- Points:
  - 两个 README 各新增 Codex 安装小节：marketplace add（GitHub 源）、plugin install、技能自然语言触发说明、与 Claude 安装章节并列不混淆
  - 安装命令与 docs/codex-e2e.md 第 2 步逐字一致（若 Task 7 实测修正过命令，回改此处保持一致）
- Anchors:
  - command: `grep -c "Codex" README.md README-zh.md` → 两文件各 ≥1
  - command: `grep -o "codex plugin [a-z]*" README.md README-zh.md docs/codex-e2e.md | sort -u` → 命令动词集合一致（人工核对输出）

### Task 7: E2E 手册编写与执行记录
- Files: docs/codex-e2e.md
- Points:
  - 按 Design 节编写 0-10 共 11 节手册，每步给出可复制命令、期望观察点与记录行（PASS/FAIL/NOT_EXECUTED + 输出摘录）
  - 第 0 节前置条件含 `~/.codex/config.toml` `[features] multi_agent = true` 检查与建议 `[agents] default_subagent_model`/`default_subagent_reasoning_effort` 兜底（缺失时给出添加步骤）
  - 第 4 步明确 `${CLAUDE_PLUGIN_ROOT}` 探针判据：变量被展开 / 未展开但指针块自举 + host_compat.py 接管 / 失败（unknown→询问用户），三种结局都要记录；并记录真实 cache 目录布局与 Codex 特征 env marker 集，供收紧 host_compat.py 的 cache-glob 假设
  - 第 6 步先编码 spawn_agent 主路径可用性验证（`fork_turns:"none"` 派发 → `wait_agent` 有界等待 → mailbox 回收 → `followup_task` 续发 → `list_agents` 对账）与 multi_agent 不可用时的 fallback 行为记录（自然语言 spawn + 摘要回收风险观察）；再按 Design 节编码 explorer 探针决策程序（写盘能力与输出保真度双观察、用户批准门、A/B 分支切换判据与必填记录项，含升级时的契约修订确认）
  - `codex --version` 探测本机：可用则顺序执行并回填记录行，同时按实测修正 Task 4/6 的清单与文档命令；不可用则全部标 NOT_EXECUTED 并在手册头部注明
  - 第 8 步双特性并行验证需 scratch 项目含两个无依赖特性（手册中给出最小 features.json 准备步骤）
- Anchors:
  - command: `grep -c "^## " docs/codex-e2e.md` → ≥11
  - command: `grep -cE "PASS|FAIL|NOT_EXECUTED" docs/codex-e2e.md` → ≥ 11（0-10 每节至少一行记录行；无 CLI 时为 11 行 NOT_EXECUTED）
  - command: `grep -cE "spawn_agent|multi_agent" docs/codex-e2e.md` → ≥2（第 0/6 步主路径与 fallback 记录行在场）
  - [UNDEFINED-INPUT] Codex CLI 版本差异或步骤实测失败: 把实际输出与偏差写入该步记录行并继续后续步骤，不中止手册交付
