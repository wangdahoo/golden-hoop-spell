# progress.md 正名改造 —— 定位收敛为会话纪要

> SCOPE CONTRACT — frozen at kickoff. 由 dispatcher 维护并经用户确认；
> 正文不得扩大本契约范围，冲突时删正文不删契约。

## Intent
Dogfood 分析证实 progress.md 已不再承担「中断恢复小本本」职能（恢复实际由 features.json + git log + parallel raw 承担），且存在写入方膨胀、模板常驻文件本体、归档抽取丢数据（Init 条目实证丢失）三个问题。按已拍板的「正名路线」，将其定位收敛为「人类可读的会话纪要 + /ghs:status 展示素材」，恢复职能显式移交，并修复归档丢失。

## Goals
- G1: `.ghs/progress.md` 文件本体不再包含 `## Session Template` 模板块；条目结构规范外部化到 `plugin/shared/references/`（单一规范源）；7 个 SKILL.md 中「Session Template built into that file」措辞全部改指外部 reference
- G2: 写入方收敛——ghs-status、ghs-init 的 Closing Step 1（progress.md 条目）移除；`tasks_to_features.py` 空壳 planning 条目移除；ghs-to-features 双写改单条目
- G3: 归档不再丢条目——归档副本保存完整 Sessions 区（全量）；`_entry_matches_plan` 挑选式抽取退役；有剩余计划时的删除分支对 `Plan: N/A` 条目语义明确（保留于活动文件）且任何分支不丢信息
- G4: 恢复职能显式移交——ghs-code / coding-agent.md 的「Read progress.md (mandatory)」改为以 features.json + git log（+ 并行模式 raw 留档）为主的恢复源清单，progress.md 降为可选参考
- G5: 条目结构单一规范——coding-agent.md §383 与 examples.md 的漂移结构统一到外部化规范；Agent 枚举更新为真实值域
- G6: 测试同步——行为变更处测试更新/新增（归档抽取为重点），全量测试套件绿；全库 grep `progress.md` 无「恢复职能」残留表述
- G7: 语言中立——插件对目标项目产物的语言指示不得写死具体语言：本次新增/修改的全部插件文本（SKILL.md、新 reference、模板骨架）中，凡涉及「条目/文档用什么语言写」，一律表述为「遵循目标项目自身的语言设定（如其 CLAUDE.md/AGENTS.md）」

## Non-Goals
- 不改文件路径/文件名与「顶插、编号续接」追加约定
- 不引入新状态文件或恢复机制（不给 features.json 加断点字段）
- 不改 ghs-plan 流水线 Phase 1-5 及 `-status.json` 机制
- 不做 codex/pi 功能增减，仅同步文案，三宿主行为等价
- 不迁移/清洗既有 `.ghs/` 数据（现网文件与归档保持原样，无格式升级脚本）
- 不改 status.py 展示格式（模板块本就被日期过滤，仅需确认删除后无行为变化）

## Anti-Goals
- 出现双规范（SKILL.md 与外部 reference 条目结构不一致）——即使一处漏改也失败
- 归档/重置任何分支丢失未保存的条目（含 `Plan: N/A`）——即使功能全部上线也失败
- 模板删除后仍存在「built into that file」悬空引用
- 三宿主执行面行为分叉
- 本次改动后的插件文本对目标项目产物写死语言（中文或英文）——即使出于好意也失败

## Decisions
- 定位三分：会话纪要（progress.md）/ 流程管控与恢复（features.json + git log + raw）/ 状态机（-status.json）（用户 2026-10-30 拍板正名路线）
- 归档抽取改全量保存 Sessions 区 [DISCRETIONARY——备选为放宽匹配规则；全量更简单且彻底消除丢失面]
- ghs-plan、ghs-archive/force-archive 保留会话条目（契约/归档事件有叙事价值）[DISCRETIONARY]
- 模板外部化落点为新文件 `plugin/shared/references/session-entry-format.md` [DISCRETIONARY]
- 底部矛盾 marker `<!-- New sessions should be added above this line -->` 移除 [DISCRETIONARY]
- status.py `last_n=5`/展示 3 的不一致对齐（Optimization 级）[DISCRETIONARY]
- 语言中立化范围取最小面：仅本次触碰的文本 + 新 reference 的条目语言指示改为 defer [DISCRETIONARY——备选：顺带清扫 7 个 SKILL.md 中既有写死中文的交互文案（如 AskUserQuestion 提问串「该计划下全部特性已完成…」），该清扫与 progress.md 定位无关，建议另开计划]

## Open Space
- 外部 reference 的章节组织与措辞
- ghs-to-features 合并后单条目的字段结构
- 各 SKILL.md Closing Step 1 删除/改写后的行文
- 测试断言粒度；README/e2e 文档同步措辞

## Global Constraints
- 语言政策（双层，不得混淆）：① 本仓库自身源码遵循仓库 CLAUDE.md（文档/commit 中文；代码标识符、日志、错误信息、SKILL.md 指令正文英文）——仅约束 golden-hoop-spell 仓库；② 插件对目标项目产出的语言指示不写死具体语言，一律 defer 到目标项目自身设定（CLAUDE.md/AGENTS.md），对无设定的项目取中性默认并如实说明
- Python 一律 `command python3`；仅标准库；入口调 `force_utf8_stdio()`
- 测试用 stdlib unittest 直跑；现存 11 个测试文件全绿
- SKILL.md 改动三宿主行为等价，不新增宿主差异文件
- 初始骨架仍由 `init_project.py` 从 `assets/progress.md` 复制；reset 与初始同源
- 条目 H2 标题行内嵌日期不变（status.py 过滤依赖）
- `.ghs/` 不进 git；版本号不动（0.7.0 内交付）

## Current State

细节以 context snapshot（`.ghs/plans/2026-10-30-progress-reposition-context.md`）为准，此处只列影响决策的事实：

- 模板块物理上住在 `plugin/shared/assets/progress.md` 文件本体（`## Session Template` 段 + 尾部 marker 注释）；`init_project.py create_progress_md()` 整文件 copy，`archive_plans.py reset_progress_md()` 经 `get_progress_template()` 整文件覆写——两条路径都无需感知模板内容，外部化不动机制。
- 「Session Template built into that file」措辞分布在 7 个 SKILL.md（init §60、status §56、to-features §188、plan §931-932、code §117 与 §369、archive §86、force-archive §79）。
- 7 个 SKILL.md 的 Closing Steps 节首均为同一导语「Finish every run of this skill with BOTH closing steps」；G2 删步后需单步化的是 init/status/to-features 三处（各删 Closing Step 1），plan/code/archive/force-archive 四处仍为双步、导语保留。
- 归档丢失实证：`archive_plans.py _entry_matches_plan()` 只扫条目前 11 行找 plan id 子串，`**Plan**: N/A` 条目永不命中——抽取侧漏抽（p1 归档无 Init 条目）、删除侧遗留孤儿。归档副本现由 `extract_plan_sessions(progress_path, plan_id)` 挑选式生成。SKILL.md 侧的挑选式/重置表述分落在 ghs-archive：§53（Step 3 bullet「related sessions」）与 §62（What Gets Archived「Related progress sessions」）陈述挑选语义，§55/§64（「reset to the default template」）与 §86（After 排序理由「the script resets ... so the entry must be appended afterwards」）为无条件重置断言——有剩余计划分支下失真；force-archive 的 reset 断言（§63、§79）在 `--force` 清空全部计划下恒成立。
- 恢复职能来源两处：`ghs-code/SKILL.md` §41 与 `coding-agent.md` §27 的「Read .ghs/progress.md to understand previous sessions」（后者带 "This step is mandatory"）。
- 结构漂移三处规范：`coding-agent.md` §383（`### Implementation`、缺 Decisions Made）、`examples.md` Example 2/3（Technical Decisions、Implementation）、模板/SKILL.md 五小节。注意 `### Implementation Order`（examples.md §199、features-agent.md §216）是 Planning entry 规范五节之一，与漂移结构 `### Implementation` 是两回事，必须保留。
- `status.py read_progress_md(filepath, last_n=5)` 按首行日期过滤 H2 段，`main()` 只打印 `sessions[:3]`；无 test_status.py（p1 决议）。
- 测试文件实数 12 个（`ls plugin/shared/scripts/test_*.py`，含 `test_validate_manifests.py`）；契约 Global Constraint 所记「11 个」为失实旧计数，正文按 12 表述。
- 文档面：`docs/e2e-multi-host.md` §5（§226）init 判据含「progress.md 顶部新增会话条目」（init 停写后该判据永久失败）；`CLAUDE.md` §29「Each session logs to .ghs/progress.md」；README §122/§176 无需改。

## Design

### 总路线
条目结构规范外部化为唯一规范源 `plugin/shared/references/session-entry-format.md`，其余文件（assets 模板、SKILL.md 内联块、references 示例）一律降为指向它或与之逐字段一致的镜像。文件本体 `assets/progress.md` 只留骨架；归档改全量快照消除丢失面；写入方按 G2 收敛。

### 外部规范文件（G1/G5/G7，Open Space：章节组织）
`session-entry-format.md` 章节定为五节：
1. `## Role` — 本文件是 progress.md 条目结构的单一规范源；SKILL.md/references 中的内联块是镜像，必须与本文件逐字段一致。
2. `## Placement and Numbering` — 新条目插在 `## Sessions` 区顶部；`N` 续接既有 `## Session N` 编号；**H2 标题行必须内嵌 `YYYY-MM-DD`**（`status.py` 按首行日期过滤，缺日期 = 对 /ghs:status 不可见，写为硬性要求）。
3. `## Entry Types` — 三类条目模板：Session entry（`## Session N - YYYY-MM-DD`，Agent/Plan/Feature + 五小节 Work Completed / Tests Performed / Issues Encountered / Decisions Made / Next Steps；编码会话追加 `### Files Changed` + `### Acceptance Criteria Status`）；Planning entry（`## Feature Planning - YYYY-MM-DD`，Requirements Received / Features Planned / Plan Goal / Implementation Order / Notes）；Parallel Orchestration entry（`## Parallel Orchestration - YYYY-MM-DD`，Agent/Plan/Max Parallelism + Execution Summary 表 / Statistics / Next Steps，无 Feature 字段行）。
4. `## Agent Field Values` — 枚举真实值域：`To-Features Agent` / `Plan Dispatcher` / `Coding Agent` / `Coding Agent (Parallel Mode)` / `Archive Agent`（Init/Status Agent 随 G2 停写退役）；无适用计划时 `**Plan**: N/A`。
5. `## Entry Language` — 条目行文语言遵循目标项目自身的语言设定（如其 CLAUDE.md/AGENTS.md）；项目无设定时取中性默认并在条目内注明该选择（G7，不写死中文或英文）。

### assets/progress.md 瘦身（G1 + Decision）
保留 `# Project Progress Log` + 一句引言（说明这是人类可读会话纪要、条目结构见 **ghs 插件**的 `shared/references/session-entry-format.md`）+ `## Sessions`；删除 `## Session Template` 整段与 `<!-- New sessions ... -->` marker。引言必须写明「ghs 插件」归属：该文件会被整份复制进目标项目 `.ghs/`，裸路径 `shared/references/...` 对目标项目读者不可解析；规范指针的权威落点仍是各 SKILL.md 的 `${CLAUDE_PLUGIN_ROOT}` 引用。init copy 与 reset 覆写机制不动（Global Constraint：初始骨架仍由 init_project.py 复制、reset 与初始同源）；现网 `.ghs/` 文件不迁移。

### 归档全量快照（G3 + Decision）
- 新函数 `extract_sessions_section(progress_path: Path) -> str` 取代 `extract_plan_sessions`（后者删除）：返回 `## Sessions` 标题行之后的全部内容（strip）；标题缺失时回退为 `_split_entries` 全量 join（防手工编辑/旧文件，归档不因标题缺失丢数据）；返回空串时维持现有 `if sessions:` 守卫不写归档 progress.md。
- `archive_plan_files()` 改调新函数 → 每个归档目录的 progress.md 是归档时刻 Sessions 区的全量快照。同轮归档多计划时各目录持有相同快照（冗余但零丢失，契约已拍板全量优先）。
- `_entry_matches_plan()` 保留但退役抽取用途，仅服务删除分支，docstring 写明语义：头部 11 行子串匹配；不含任何 plan id 的条目（含 `**Plan**: N/A`）永不命中、**永远保留在活动文件**。
- 两条收尾分支的无损性论证（写入测试）：清空分支 reset 覆写前，全量快照已在本轮 `archive_plan_files` 落盘；剩余分支只删除命中条目，其内容已在对应计划的全量快照内，未命中条目（N/A、剩余计划）原地保留。

### 写入方收敛（G2）
- `ghs-init` / `ghs-status`：删除 Closing Step 1 整节（含条目模板块与 Agent: Init/Status Agent 模板），原 Step 2 升为 Step 1，节首「BOTH closing steps」导语改单步措辞。
- `ghs-to-features`：与 init/status 同构处理——删除 Closing Step 1（Session N 条目）后，§184「BOTH closing steps」导语同步改单步措辞、原 Closing Step 2（§214）升为 Step 1（只删条目而保留 BOTH 导语与 Step 2 编号，会形成与 init/status 同类的悬空措辞）；保留 Step 6 的 `## Feature Planning` 条目作为唯一 progress.md 写入——计划叙事（需求/目标/实现顺序）在该条目，会话条目与之重复。
- `ghs-plan` / `ghs-code`：条目保留（契约 Decision），「built into that file / built into `.ghs/progress.md`」改指 `${CLAUDE_PLUGIN_ROOT}/shared/references/session-entry-format.md`；ghs-plan 的「required on EVERY exit path」句保留，ghs-code 保留五小节 + 两附加小节的描述、仅规范出处改指外部文件。
- 归档措辞按行分置（ghs-archive）：§53 Step 3 bullet 与 §62 What Gets Archived bullet 改「完整 Sessions 区全量快照」——只有这两处陈述的是「归档副本里有什么」；§55 Step 3 bullet、§64 What Gets Archived bullet 的无条件 reset 断言与 §86 After 排序理由改两分支措辞（无剩余计划→重置为模板，有剩余→仅移除归档计划的条目）——这三处与正文要修的 §86 失真同源，必须同步修，否则「有剩余计划」分支下文档不实。force-archive 的 reset 断言（Step 3 bullet、After）维持无条件表述不变——`--force` 清空全部计划后 reset 恒成立，两分支化反而不实；仅改「built into that file」指向。

### 恢复职能移交（G4）
`ghs-code/SKILL.md` Start of Session 第 2 步与 `coding-agent.md` Start of Session 第 2 步重写为恢复源清单：`.ghs/features.json`（feature status / blocked_reason）+ `git log` 为主；并行中断场景加 `.ghs/parallel/<plan_id>/<feature_id>.raw.attempt<N>` 留档；progress.md 降级为 optional narrative reference。删除 "This step is mandatory" 句；`coding-agent.md` Pre-flight 第 3 步（§133）同步降为 optional 措辞。两文件并行子代理 prompt 模板中「Read progress.md for recent project context」不动（上下文获取而非恢复协议，且两模板必须逐字同步）。

### 结构漂移统一（G5）
- `coding-agent.md` §383「progress.md Structure」内联块替换为指向外部规范 + 一句 coding 附加小节说明；`### Implementation` 漂移小节（§393）随之删除/改名。
- `examples.md` Example 3：`### Implementation`（§227）→ `### Work Completed`、补 `### Decisions Made`；Example 2：`### Technical Decisions` 内容并入 `### Notes`；Example 4 注释改全量快照措辞；§291 To-Features workflow 改为只写 planning entry。`### Implementation Order`（§199，Planning entry 五节之一）保留不动。
- `features-agent.md` §195 与 `ghs-to-features` Step 6 的 planning entry 块保留为镜像，逐字段对齐规范并各加一行指向规范文件。

### status.py 对齐（Decision，Optimization 级）
`read_progress_md` 默认 `last_n=3`，`main()` 直接迭代返回值（删 `[:3]` 切片）；展示格式其余不动（Non-Goal）。不新建 test_status.py，以运行锚点把关（p1 决议）。

### 文档同步与清扫（G6 + Open Space）
`docs/e2e-multi-host.md` §5 init 判据「progress.md 顶部新增会话条目」改为「progress.md 存在且含 `## Sessions` 区」；§7 code 阶段判据保留。`CLAUDE.md` §29 改按剩余写入方（to-features planning entry、plan/code/archive 会话条目）表述。README/README-zh 无恢复职能表述，不改。清扫范围排除 `docs/superpowers/`、`docs/analysis/` 历史设计记录。

## Assumptions
- [ASSUMPTION] 并行子代理 prompt 模板（ghs-code §185、coding-agent.md §213）中的 progress.md 读取保留不改 — 属子代理上下文获取而非会话恢复协议，且两文件模板须逐字一致，改动会放大三宿主执行面。
- [ASSUMPTION] `extract_sessions_section` 在 `## Sessions` 标题缺失时回退为全量条目 join — 归档无损性不依赖文件形态良好的假设。
- [ASSUMPTION] G6 清扫排除 docs/superpowers/ 与 docs/analysis/ — 冻结的历史设计记录，改写即失真；活文档面（plugin/、README、CLAUDE.md、docs/e2e-multi-host.md）归零。
- [ASSUMPTION] e2e §5 init 判据改为「文件存在且含 Sessions 区」— init 停写后原判据「顶部新增会话条目」会永久误报失败。
- [ASSUMPTION] 不新建 test_status.py — p1 决议 stdio 类脚本以运行锚点把关，last_n 对齐为 Optimization 级。
- [ASSUMPTION] codex-host.md §193 与 pi-host.md §41-42 的「把降级/缺件事实记入 session log (.ghs/progress.md)」零改动 — progress.md 新定位仍是会话纪要，该指示语义成立；契约 Non-Goal（codex/pi 仅同步文案）未授权改写，Task 5 执行时核对两处与新定位无冲突即可，不视为遗漏。

## Risks
- 条目缺日期则 /ghs:status 静默不可见 — 规范将 H2 首行内嵌日期列为硬性要求，Task 1 锚点把关。
- 全量快照把剩余计划的条目也带进归档目录 — 接受（契约 Decision 拍板全量优先于挑选），归档目录是只增的快照不会回写。
- ghs-plan SKILL.md 970+ 行，Closing Steps 改写若伤及「EVERY exit path」语义会丢中止路径的会话痕迹 — 改写限定 Step 1 措辞层，保留该句与五小节结构。
- 镜像块（SKILL.md Step 6 / features-agent.md §195 / 规范文件）未来漂移重现双规范 — 规范文件 Role 节声明镜像规则 + Task 7 整行 grep 锚点当场校验一致（`^### Implementation$` 整行锚定，不误伤 Planning entry 的 `### Implementation Order`）。

### Task 1: 新建外部条目规范 session-entry-format.md
- Files: plugin/shared/references/session-entry-format.md
- Interfaces: 无代码接口; 文件五节结构 Role / Placement and Numbering / Entry Types / Agent Field Values / Entry Language
- Points: 按 Design「外部规范文件」一节落五节内容；三类条目模板字段与现存镜像（ghs-code Step 5.4 五小节+两附加小节、ghs-to-features Step 6 五小节、coding-agent.md §340 Parallel Orchestration 块）逐字段一致；Agent 枚举取真实值域五值; 条目语言 defer 到目标项目 CLAUDE.md/AGENTS.md（英文行文，不写死产物语言）。
- Anchors:
  - `grep -c "Session Template" plugin/shared/references/session-entry-format.md`: 输出 0 (不引入旧名)
  - `grep -n "YYYY-MM-DD" plugin/shared/references/session-entry-format.md`: 三类条目标题行均含日期占位且 Placement 节声明为硬性要求
  - `grep -n "Plan Dispatcher" plugin/shared/references/session-entry-format.md`: Agent 枚举含 Plan Dispatcher 等真实值域五值
  - `grep -n "CLAUDE.md" plugin/shared/references/session-entry-format.md`: Entry Language 节命中 defer 条款

### Task 2: assets/progress.md 瘦身
- Files: plugin/shared/assets/progress.md
- Points: 删 `## Session Template` 整段（含围栏块）与尾部 marker 注释行; 引言改为一句指向 **ghs 插件**的 `shared/references/session-entry-format.md`（写明插件归属——该文件被整份复制进目标项目 `.ghs/`，裸路径对其读者不可解析；权威指针仍由 SKILL.md 的 `${CLAUDE_PLUGIN_ROOT}` 引用承担）; 保留 `# Project Progress Log` 与 `## Sessions` 骨架及既有分隔线风格; 不动 init_project.py / archive_plans.py 的复制与覆写机制。
- Anchors:
  - `grep -c "Session Template" plugin/shared/assets/progress.md`: 输出 0
  - `grep -c "New sessions should be added above this line" plugin/shared/assets/progress.md`: 输出 0
  - `grep -c "## Sessions" plugin/shared/assets/progress.md`: 输出 1
  - `command python3 plugin/shared/scripts/test_init_project.py`: 全部用例通过 (新模板复制成功)

### Task 3: archive_plans.py 全量快照与删除分支语义
- Files: plugin/shared/scripts/archive_plans.py, plugin/shared/scripts/test_archive_plans.py
- Interfaces: `def extract_sessions_section(progress_path: Path) -> str`（取代并删除 `def extract_plan_sessions(progress_path: Path, plan_id: str) -> str`; `archive_plan_files` 改调新函数; `_entry_matches_plan` / `_split_entries` 签名不变）
- Points: extract_sessions_section 返回 `## Sessions` 标题行后全部内容 strip, 标题缺失回退 `_split_entries` 全量 join, 空返回 ""（沿用 `if sessions:` 守卫）; `_entry_matches_plan` docstring 改为 removal-only 语义并写明 N/A 条目永不命中且永远保留; 两收尾分支不改控制流（清空 reset / 剩余 remove）, 无损性由快照保证; 新增测试类覆盖全量快照、reset 分支 N/A 条目入档、remove 分支保留未命中条目三个场景。
- Anchors:
  - test_extract_sessions_section_full_snapshot: 返回值含 Plan 为 N/A 的 Session 条目, Feature Planning 条目与剩余计划条目, 顺序与原文件一致
  - test_archive_reset_branch_keeps_plan_na_entry: plans 清空分支后归档目录 progress.md 含 N/A 条目全文 (p1 Init 条目丢失场景回归)
  - test_remove_branch_keeps_unmatched_entries: 有剩余计划分支后活动文件仍含 N/A 条目与剩余计划条目且仅移除归档计划条目, 归档副本为全量快照
  - `command python3 plugin/shared/scripts/test_archive_plans.py`: 全部用例通过含既有 ensure_ascii 与清洗用例

### Task 4: tasks_to_features.py 移除空壳 planning 条目
- Files: plugin/shared/scripts/tasks_to_features.py, plugin/shared/scripts/test_tasks_to_features.py
- Interfaces: 删除 `def append_progress_entry(progress_path: Path, plan_id: str, count: int, plan_ref: str)` 及 main() 中其调用与随之失用的 `progress_path` 局部变量
- Points: 模块 docstring 去掉「appends a minimal planning entry to .ghs/progress.md」表述; test_10_progress_entry 重写为物化前后 progress.md 逐字节一致; 其余解析/物化行为零改动（三态路由与 exit code 不变）。
- Anchors:
  - test_10_progress_entry: 重写后断言物化前后 .ghs/progress.md 内容完全一致
  - `command python3 plugin/shared/scripts/test_tasks_to_features.py`: 全部用例通过
  - `grep -n "append_progress_entry" plugin/shared/scripts/tasks_to_features.py`: 输出 0 行

### Task 5: 写入方收敛——七个 SKILL.md 的 Closing Steps 与措辞
- Files: plugin/skills/ghs-init/SKILL.md, plugin/skills/ghs-status/SKILL.md, plugin/skills/ghs-to-features/SKILL.md, plugin/skills/ghs-plan/SKILL.md, plugin/skills/ghs-code/SKILL.md, plugin/skills/ghs-archive/SKILL.md, plugin/skills/ghs-force-archive/SKILL.md
- Interfaces: 无代码接口; ghs-init/ghs-status/ghs-to-features 三者的 Closing Steps 收敛为单步（原 Closing Step 2 升 Step 1）
- Points: init/status 删 Closing Step 1 整节含条目模板块（含 Agent: Init/Status Agent 行）, 节首「BOTH closing steps」导语改单步措辞, 原 Step 2 升 Step 1; to-features 同构处理——删 Closing Step 1（§186）, §184「BOTH closing steps」导语同改单步措辞, 原 Closing Step 2（§214）升为 Step 1, Step 6 planning entry 保留并加一行指向 session-entry-format.md; plan/code/archive/force-archive 四处「built into that file / built into .ghs/progress.md」改指 `${CLAUDE_PLUGIN_ROOT}/shared/references/session-entry-format.md`, ghs-plan 保留「required on EVERY exit path」句与五小节模板, ghs-code §117 与 §369 保留五小节+两附加小节的描述但规范出处改指外部文件; ghs-archive 措辞按行分置——§53 Step 3 bullet 与 §62 What Gets Archived bullet 改「完整 Sessions 区全量快照」, §55 bullet 改「Update `.ghs/progress.md`: reset to the default template when no plans remain; otherwise remove only the archived plan's entries」, §64 bullet 改「`.ghs/progress.md`: reset to the default template when no plans remain; otherwise only the archived plan's entries are removed」, §86 After 排序理由同改两分支措辞（无剩余计划→重置为模板, 有剩余→仅移除归档计划的条目）; force-archive 的 Step 3 reset bullet（§63）与 After（§79）维持无条件重置表述不变——`--force` 清空全部计划后 reset 恒成立, 仅按既有点位改「built into that file」指向; codex-host.md §193 与 pi-host.md §41-42 的降级记录指示核对与新定位无冲突且零改动（见 Assumptions）。
- Anchors:
  - `grep -rn "built into" plugin/skills`: 输出 0 行
  - `grep -rnE "Init Agent|Status Agent" plugin/skills`: 输出 0 行（init/status 的 Closing Step 1 条目模板块随节删除）
  - `grep -rln "BOTH closing steps" plugin/skills`: 命中且仅命中 ghs-plan, ghs-code, ghs-archive, ghs-force-archive 四个 SKILL.md（init/status/to-features 三处导语已单步化）
  - `grep -rln "session-entry-format.md" plugin/skills`: 命中 to-features, plan, code, archive, force-archive 五个 SKILL.md
  - `grep -nE "is reset to the default template|^(- )?Reset .\.ghs/progress\.md. to the default template" plugin/skills/ghs-archive/SKILL.md`: 输出 0 行（分支一守 §64 旧句 is reset to the default template; 分支二行首 bullet 容错 + 点通配反引号, 守 §55 旧句行首 Reset .ghs/progress.md 句——修订前模式对 §55 实文两分支均失配、漏改会假通过; §55/§64/§86 两分支新措辞不得再现上述任一旧句字面）

### Task 6: 恢复职能移交——恢复源清单替换 mandatory 读
- Files: plugin/skills/ghs-code/SKILL.md, plugin/shared/references/coding-agent.md
- Interfaces: 无代码接口; 两文件 Start of Session 第 2 步改为恢复源清单（features.json + git log 为主, `.ghs/parallel/<plan_id>/<feature_id>.raw.attempt<N>` 覆盖并行中断, progress.md 降为 optional narrative reference）
- Points: ghs-code §41 与 coding-agent.md §27 的「Read .ghs/progress.md to understand previous sessions」句替换, coding-agent.md「This step is mandatory」句删除; coding-agent.md §133 Pre-flight 第 3 步降为 optional 措辞; 两文件 git log 与 features.json 步骤的既有编号与顺序不动; 子代理 prompt 模板（ghs-code §185、coding-agent.md §213）保持逐字不变。
- Anchors:
  - `grep -rn "understand previous sessions" plugin`: 输出 0 行
  - `grep -rn "This step is mandatory" plugin`: 输出 0 行
  - `grep -in "optional" plugin/skills/ghs-code/SKILL.md plugin/shared/references/coding-agent.md`: 两文件 Session Protocol 恢复清单处各命中 optional 措辞

### Task 7: 结构漂移统一与示例对齐
- Files: plugin/shared/references/coding-agent.md, plugin/shared/references/examples.md, plugin/shared/references/features-agent.md
- Interfaces: 无代码接口; coding-agent.md §383 内联块替换为指向 session-entry-format.md 的指针节
- Points: §383 删 `### Implementation` 漂移结构改指针 + coding 附加小节说明; examples.md Example 3 改 Work Completed 并补 Decisions Made, Example 2 的 Technical Decisions 内容并入 Notes, Example 4 归档注释改全量快照措辞, §291 To-Features workflow 第 5 步改只写 planning entry; examples.md 另于 Example 2 与 Example 3 的条目围栏块紧邻上方（H2 标题行之后、围栏之前）各加一行镜像声明 `Entry structure spec: session-entry-format.md`——不进入条目正文以免污染示例结构, 与 §383 指针节 / features-agent.md §195 指针行同构, 锚点 4 的三文件命中由此齐备; features-agent.md §195 planning entry 块与规范逐字段一致并加指针行; `### Implementation Order`（examples.md §199、features-agent.md §216, Planning entry 规范五节之一）保留不动。
- Anchors:
  - `grep -n "^### Implementation$" plugin/shared/references/coding-agent.md plugin/shared/references/examples.md`: 输出 0 行（整行锚定; `### Implementation Order` 含尾缀不命中, Planning entry 五节不受影响）
  - `grep -n "Technical Decisions" plugin/shared/references/examples.md`: 输出 0 行
  - `grep -c "Decisions Made" plugin/shared/references/examples.md`: 输出大于等于 1 (Example 3 补齐小节)
  - `grep -rln "session-entry-format" plugin/shared/references`: coding-agent.md, examples.md, features-agent.md 三文件均在命中列表

### Task 8: status.py last_n 对齐
- Files: plugin/shared/scripts/status.py
- Interfaces: `def read_progress_md(filepath: Path, last_n=3)` （默认值 5 改 3; main() 中 `sessions[:3]` 改为直接迭代 `sessions`）
- Points: 仅动默认参数与切片, 日期过滤逻辑与打印格式逐行不动（Non-Goal: 展示格式零变化, 模板块本就被日期过滤）。
- Anchors:
  - `command python3 plugin/shared/scripts/status.py --project-dir .`: exit 0 且 Recent Sessions 至多 3 条
  - `grep -n "last_n" plugin/shared/scripts/status.py`: 默认值为 3 且 main 无二次切片

### Task 9: 文档同步与全库措辞清扫收口
- Files: docs/e2e-multi-host.md, CLAUDE.md
- Points: e2e §5（§226）init 判据「progress.md 顶部新增会话条目」改为「progress.md 存在且含 `## Sessions` 区」, §7 code 判据保留; CLAUDE.md §29「Each session logs to .ghs/progress.md」改为按剩余写入方表述（to-features 写 planning entry, plan/code/archive 写会话条目）; 终扫 plugin/ 与四个活文档的 recovery 残留与「Session Template」残留, docs/superpowers 与 docs/analysis 不扫。
- Anchors:
  - `grep -rn "Session Template" plugin README.md README-zh.md CLAUDE.md docs/e2e-multi-host.md`: 输出 0 行
  - `grep -rn "understand previous sessions" plugin docs/e2e-multi-host.md CLAUDE.md README.md README-zh.md`: 输出 0 行
  - `grep -nE "progress\.md.? 顶部新增会话条目" docs/e2e-multi-host.md`: 输出 0 行（模式以 .? 容错 progress.md 的成对反引号——修订前 §226 实文即命中非零, 漏改时锚点有守卫力; 改写后判据措辞不含该短语, 归零）
  - `grep -n "Each session logs" CLAUDE.md`: 输出 0 行
  - `for f in plugin/shared/scripts/test_*.py; do command python3 "$f" >/dev/null || echo "FAIL $f"; done`: 无 FAIL 输出 (实际 12 个测试文件全绿, 含 test_validate_manifests.py; 循环按 glob 运行, 不依赖计数)
