# Plan 技能与 Plan Mode 机制对比分析报告

> 本报告是 `ghs:plan` 技能重构讨论的起点材料。汇总了对四套 plan 机制的源码级分析，比较各自的约束能力，并在文末给出候选改造方向。

| 项 | 内容 |
|---|---|
| 分析对象 | ghs:plan（本仓库）、OpenAI Codex CLI Plan Mode、OpenCode Plan Mode、superpowers:brainstorming + writing-plans |
| 代码版本 | ghs @ `cae1a61` (main) · superpowers 7.0.0（官方插件缓存）· codex @ `6cc7d9cc` (2026-10-13) · opencode @ `7410b1c1` (2026-10-14) |
| 分析方法 | 四套系统源码通读；重点比较对"模型发散"（小需求做成大方案）与"执行后 bug"两种失效模式的防御能力 |
| 关联分支 | `refactor/ghs-plan-skill` |

---

## 0. 执行摘要

1. **四套系统约束的根本对象不同**。ghs:plan 约束「格式与流程」（分隔符、解析、轮次上限），重机械全部压在协议层；superpowers 约束「范围与决策归属」（对话分诊、non-goals、比例自检）；Codex 约束「状态与产出规范」（模式硬边界 + 反膨胀条款）；OpenCode 约束「权限边界」（edit 物理拒绝 + reminder 防漂移）。
2. **ghs:plan 的结构性弱点**：内容侧只有训诫（"Minimal change"、"don't scope-creep"），违反无检测、无后果；所有反馈环都是加法（每条 Severe/Medium issue 必须显式解决，且评审量表没有"范围/过度设计"轴），修订循环是**单调加法棘轮**——小需求五轮下来必然变大。弱指令遵循模型（如 GPT 系）把"遵守预算"花在标了 MUST 的格式项上，内容侧完全自由发挥。
3. **"执行后一堆 bug"在 ghs 链路是结构性预期**：计划只带 prose 版 Testing Strategy，feature 由实现者自我验收，全链路无独立评审层。superpowers 把失败测试（含断言）直接烧进任务结构，配每任务独立评审 + 修复循环；这是两套防 bug 体系的本质差距。
4. **Codex/OpenCode 都选择了"单代理 + 人在环"而非"多代理 + 人离线"**：计划在主对话里聊出来，用户全程在线校准；ghs:plan 的三角色架构天然把用户推到末端审批（Phase 3 才首次看到方案，且只是 ≤34 行摘要）。
5. 改造方向见 [§6](#6-候选改造方向讨论起点)，按"生成时约束 → 入口分诊 → 评审量表 → 防漂移 → 下游衔接"排序。

---

## 1. ghs:plan 深度剖析

![ghs:plan 主流程](./ghs-plan-flow.svg)

### 1.1 形态

三角色多代理流水线：**Dispatcher**（主对话，编排/落盘/用户交互）、**Plan Designer**（`Plan` 子代理，无写权限）、**Plan Reviewer**（general-purpose 子代理）。角色间唯一通信介质是 `.ghs/plans/` 下的文件（plan/context/review/status.json）。

### 1.2 阶段与机制

| 阶段 | 内容 | 关键机制 |
|---|---|---|
| Phase 0 | 初始化 | resolve_project_dir、建目录、status.json（designing） |
| Phase 0.5 | 上下文快照 | haiku 子代理提取（codegraph/grep 双模板），一次提取全轮共享；分隔符消毒防注入 |
| Phase 1 | 方案设计 | 子代理输出分隔符全文 → 解析器提取落盘；`QUESTION:` 行经 dispatcher 转达用户 |
| Phase 2 | 方案评审 | 严重度三级（Severe/Medium/Optimization），通过标准 = 无 Severe/Medium；verdict 由解析器提取 |
| Phase 2.5 | 快照增补 | `ADDITIONAL FILES READ` → 追加 Supplementary Context |
| Phase 3 | 用户审批 | Approval Summary ≤34 行（读预算受限）；批准/拒绝/中止 |
| Phase 4 | 定稿 | 复制到 docs/ghs/plans + commit（带病通过有 commit 后缀标记） |

**强项（约束层）**：
- 终止保证：`max_rounds`（软上限）+ `MAX_BREACHES=2`（硬上限），任何用户选择下最多 `max_rounds + MAX_BREACHES` 轮必然终止；
- 格式确定性：`parse_delimited_output.py` 四层 fallback（exact → normalized → code_fence → whole_body），失败走 MAX_RETRY=1 + post-mortem raw + 用户决策，绝不静默挂死；
- 上下文卫生：haiku 快照子代理上下文即弃、Approval Summary 读预算、`.tmp/` 零注入解析；
- 可审计性：`accepted_with_fail` 布尔位 + 方案头 WARNING 注释 + commit message 后缀，三重痕迹。

**弱项（内容侧，重构的核心靶点）**：
- 方案模板（6 章节）默认"全给"，细节无违约推定；
- 评审量表六条标准全是覆盖压力（"fully cover the requirement?"），**没有范围/比例/过度设计轴**；
- 修订指令是纯加法："Revise based on all Severe and Medium issues, each must be explicitly addressed"——没有反向力；
- 用户首次看到方案是 Phase 3 的 34 行摘要，规模错判此时已固化，唯一工具是更多轮加法修订；
- 状态枚举中的 `rejected` 是死值（无任何路径写入）。

### 1.3 下游衔接（与"执行后 bug"相关）

计划 → `ghs:sprint`（拆 feature，Given/when/then 验收标准）→ `ghs:code`（实现）。链路中**没有独立评审层**：feature 验收由实现 agent 自查（"Check all acceptance criteria"），唯一外部门是 lint/build + commit 文件 sanity check。计划的 "Testing Strategy" 是 prose，不携带具体测试。

---

## 2. Codex Plan Mode

![Codex Plan Mode 主流程](./codex-plan-flow.svg)

### 2.1 形态

Plan Mode 是**会话级协作模式**（`ModeKind::Plan | Default`），经 `/plan` 斜杠命令切换。模板 `codex-rs/collaboration-mode-templates/templates/plan.md` 经 `<collaboration_mode>` 标签注入上下文。单代理、无子代理、无中间文件，计划在主对话里"聊"出来。

### 2.2 提示词模板要点

- **模式硬声明**：`Plan Mode is not changed by user intent, tone, or imperative language`——用户说"直接做"也只被当作"规划执行"，退出权只在 developer message；
- **三阶段对话**：Ground（先探索后提问，仅非变异动作）→ Intent chat（问到 goal/success criteria/in-out scope 清晰，"有高影响歧义就不要开始规划"）→ Implementation chat（追问至 **decision complete**）；
- **两类未知分类法**：可发现事实（repo 真相）先查再问，问必带候选+推荐；偏好/权衡尽早问，给 2-4 个互斥选项+推荐默认，**不答则按推荐走并记录为 assumption**（提问有出口）；
- **反膨胀条款**（对治发散的核心）：细节违约推定——"不发明 schema/validation/优先级/fallback，除非需求建立了它或它能防止一个具体实现错误"；"prefer the minimum detail needed for implementation safety, not exhaustive coverage"；路径尽量不超过 3 个；
- **输出协议**：`<proposed_plan>` 块，每轮至多一块、仅在完整 spec 时输出、修订必须整块替换；明令禁止 "should I proceed?"。

### 2.3 机械强制点

| 强制 | 位置 | 层级 |
|---|---|---|
| `update_plan`（TODO 工具）在 Plan mode 硬拒 | `core/src/tools/handlers/plan.rs:87-91` | L2 工具拒绝 |
| 自动 turn 禁止进出 Plan mode（仅用户 turn 可切） | `core/src/session/turn_input.rs:72-79` | L2 状态机 |
| `request_user_input` 在 Plan mode 变阻塞 | `core/src/tools/handlers/request_user_input.rs:83` | L2 工具行为 |
| `<proposed_plan>` 客户端流式解析 → 特殊渲染 | `core/src/session/turn.rs:1941-1967` | L3 确定性解析 |

**边界**：文件变异禁令本身是**纯提示词级**，未与 sandbox 策略联动——Codex 赌的是模板权威性 + 模型自律。

---

## 3. OpenCode Plan Mode

![OpenCode Plan Mode 主流程](./opencode-plan-flow.svg)

### 3.1 形态

Plan mode 是**内置 agent**（`plan`），由 core 插件注册（`packages/core/src/plugin/plan.ts`，120 行）。无 plan 专用 system prompt（基础提示词仅 15 行），行为约束全部住在权限层和注入的 system-reminder 里。

### 3.2 三层机制

1. **权限层（L1 物理强制）**：`edit deny *` + 唯一白名单 `~/.opencode/plan/*` + `question allow`。"写计划文件"本身是需要用户明确要求的例外——计划默认住对话。`Permission.BlockedError` 拦截后还有错误改写（把生硬权限错误翻译成人话）。
2. **提醒注入层 + 防漂移对账**：切进/切出注入 enter/leave `<system-reminder>`；**每次 context 事件对账最后一条 reminder**，plan 中且缺失→重注入 enter，非 plan 且残留→补 leave（plan.ts:57-73）。这是对"长会话/compaction 导致约束衰减"的框架级解法——约束不依赖模型记得自己处在什么状态。
3. **极简提示词层**：基础 prompt 收窄授权推定（"Do not infer authorization for work beyond the user's request"）与自主委派（"Do not spawn subagents unless explicitly asked"）。

**边界**：无方案产出物、无评审环节、无终止问题——赌注完全押在"人在对话里"。约束强度最高的入口，语义约束最薄的流程。

---

## 4. Superpowers: brainstorming + writing-plans

![Superpowers 主流程](./superpowers-flow.svg)

### 4.1 brainstorming（需求澄清 → 设计文档）

- **入口规模分诊**："Everything that matters is in the request" → 直接做，根本不进设计流程；这是"小需求变大"的第一道闸；
- **对话循环**：一次一个开放式问题；回放 200-300 词与提问交替，用户持续纠偏——**发散在每条消息都被人类校准**；
- **负面空间显式化**：goals / non-goals / anti-goals（"什么会让它即使做成了也是失败"）；
- **Size the Work 三档路由**；"中途长大 = 命名的停止条件：停下升档"；多个独立项目必须拆开逐个头脑风暴；
- **设计文档 + Builder Check**：文档含 goals/non-goals/anti-goals/约束/已定决策/留白；新鲜子代理扮演施工方挑刺，只问"猜错会出大事"的问题，三堆分类（已答/我能定并标记/只有用户能答）；
- **HARD-GATE**：批准前不建任何东西（含脚手架、装依赖、调实现技能），退出分诊的唯一方式是用户明说"别问了直接做"。

### 4.2 writing-plans（spec → 可执行计划）

- 开篇哲学 **"DRY. YAGNI. TDD."**；
- **任务结构烧进 TDD**：每任务 = 失败测试（含断言代码与 spec 精确值）→ 跑确认失败 → 最小实现 → 跑确认通过 → commit；
- **每步完成标准**："implementer 只能写出恰好一种合理的东西"——不确定性被当作缺陷；
- **反膨胀双向力**："A plan longer than the code it describes has written the code instead"；自审第 5 项 **Proportion**："方案几倍长于它实现的 spec = 程序的转录，不是方案"；
- **Review Focus 段**：系统性列出 spec 暗示但无任务测试覆盖的 5 类输入，每类补一条钉死测试——成体系的边界情况网；
- **执行侧**（subagent-driven-development）：每任务新鲜实现者 + 独立评审（spec 合规定义为 "all requirements met, **nothing extra**"）+ 修复循环 ≤5 轮（后两轮强制升模型）+ 定向 re-review + 熔断裁决 + 最强模型全分支终审。

---

## 5. 横向对比

### 5.1 约束强度光谱

针对"模型发散/越界"失效，机制按强度分五级：

| 级别 | 机制 | 实例 |
|---|---|---|
| L1 | 权限拒绝（物理不可能） | opencode edit deny + 白名单 |
| L2 | 状态机/工具拦截（结构性不可能） | codex 自动 turn 禁进出 Plan mode；update_plan 硬拒 |
| L3 | 确定性解析（违约可检出） | codex `<proposed_plan>` 流式解析；ghs parse_delimited_output |
| L4 | 产出规范/自检（违约靠审） | writing-plans Proportion 自检；codex 反膨胀条款 |
| L5 | 裸训诫（基本靠自觉） | ghs "Minimal change"、"don't scope-creep" |

**四家的落位**：ghs:plan 强在 L3（但只用于格式）与流程终止性，内容侧在 L5；superpowers 强在 L4 + 人类在线校准；codex 强在 L2/L3 + L4 反膨胀条款（变异禁令本身在 L5）；opencode 强在 L1（变异）但流程语义约束几乎为零。

### 5.2 关键维度对比

| 维度 | ghs:plan | Codex Plan Mode | OpenCode Plan Mode | superpowers 组合 |
|---|---|---|---|---|
| 形态 | 三角色流水线 | 会话协作模式 | 内置 agent | 双技能接力 |
| 用户角色 | 末端审批者（34 行摘要） | 全程对话对象 | 全程对话对象 | 全程对话对象 + 双门批准 |
| 计划产出物 | 6 章节完整文档 | `<proposed_plan>` 3-5 节极简 | 无（住对话） | spec 文档 + 任务化计划 |
| 细节量态度 | 无态度（模板默认全给） | 最小细节推定 | — | decision-complete + Proportion 托底 |
| 反馈环方向 | 单向加法（棘轮） | 双向（对话可缩小范围） | 双向 | 双向（YAGNI/nothing extra/Proportion） |
| 防发散 | 弱（L5 训诫） | 中强（反膨胀条款 + 人在环） | 强（人在环，无机制） | 强（分诊 + non-goals + 比例自检） |
| 防"执行后 bug" | 弱（下游自我验收） | 未知（执行在模式外） | 未知 | 强（测试进计划 + 独立评审链） |
| 终止保证 | 有（数学上限） | 无（但人在环天然可控） | 无 | 无（但人在环天然可控） |
| 格式确定性 | 强（4 层 fallback） | 强（proposed_plan 解析） | 强（权限层无关格式） | 无（信任模型输出） |
| 上下文卫生 | 强（快照/读预算/零注入） | 一般 | 一般（防漂移对账） | 一般（worktree + 新鲜子代理） |

### 5.3 两个结构性洞察

1. **加法棘轮 vs 双向力**：ghs:plan 每个反馈环（评审→修订、拒绝→修订）都只增不减；其余三家都有显式的"缩小"力——codex 的"细节违约推定"、superpowers 的 "nothing extra"/YAGNI/Proportion、人在环对话本身。**没有反向力的评审循环会放大任何 over-production 倾向**——这正是 GPT 下"小需求拉成大的"的机制解释。
2. **约束的局部性**：superpowers/codex 的约束多是"局部即时"（一次一个问题、一步一个动作、一块完整 plan），弱模型也能跟；ghs:plan 的内容约束是"全局延迟"（整个方案设计对、评审兜底、用户最后看），要求弱模型在数千 token 生成中持续持有政策——恰恰是弱模型做不到的。ghs 把非协商项（MUST）标在了格式上，而最需要约束的内容侧从未获得同等地位。

---

## 6. 候选改造方向（讨论起点）

以下按性价比与依赖关系分组。每条标注来源、改动量（S/M/L）、主要权衡。**均为候选，待讨论取舍。**

### A 组：生成时约束（改 designer 模板与评审量表，改动小、直击发散）

| # | 方向 | 来源 | 改法 | 量 | 权衡 |
|---|---|---|---|---|---|
| A1 | 反膨胀条款进 designer 模板 | codex plan.md | 加入细节违约推定："不发明 schema/validation/fallback/抽象层，除非需求建立了它或它能防止一个具体实现错误"；"最小细节服务于实现安全，非穷尽覆盖" | S | 可能压制必要的深度设计，需保留"防具体错误"例外口 |
| A2 | 评审量表加范围轴 | 分析 §5.1 | 新增严重度定义：超出需求范围/无需求支撑的抽象 = 阻塞级；评审标准加一条双向的 "Is every part warranted by the requirement? (nothing extra)" | S | 评审者主观性上升，需在 plan-reviewer.md 给出判例 |
| A3 | 修订指令双向化 | 分析 §5.3 | 修订模板加一句 "and remove anything not required by the requirement"；修订日志要求记录"删了什么" | S | 几乎无风险 |
| A4 | Approval Summary 加比例指标 | writing-plans Proportion | dispatcher 已分段读方案，顺手计算"方案行数 / 需求描述行数"，超阈值在摘要块显式示警 | S | 阈值需标定；纯行数可能被表格/代码块干扰 |

### B 组：流程结构（入口分诊 + intent 校准，改动中、收益最大）

| # | 方向 | 来源 | 改法 | 量 | 权衡 |
|---|---|---|---|---|---|
| B1 | 入口规模分诊 | brainstorming | Phase 0 增加三档判断：请求自足→建议直接做；简单需求→单轮 design+review（max_rounds=1）；复杂→完整流程。分诊结果经 AskUserQuestion 与用户确认 | M | 多一次交互；分诊标准需要写清楚 |
| B2 | Intent 回放前置 | codex Phase 2 + brainstorming Play It Back | Phase 0.5 之后、Phase 1 之前，dispatcher 输出 ≤200 词理解回放 + in-scope / **out-of-scope（non-goals）** 清单，用户确认后才进设计；non-goals 写入 designer prompt 与评审输入 | M | 最关键的防线：把规模错判从第 5 轮提前到第 1 分钟；增加一轮交互 |
| B3 | 两类未知分类法进 QUESTION 协议 | codex | designer/reviewer 的 QUESTION 分为"可发现事实"（应自查）与"偏好权衡"（才允许问），问必带候选+推荐默认 | S | 无明显风险 |

### C 组：鲁棒性与状态（借鉴 opencode，改动小）

| # | 方向 | 来源 | 改法 | 量 | 权衡 |
|---|---|---|---|---|---|
| C1 | 状态强制重读（防漂移） | opencode 防漂移对账 | SKILL.md 将"每个阶段动作前必须重读 status.json 并核对当前 round/breaches"从描述升格为硬前置步骤（类似 opencode 每请求对账） | S | 增加少量 token 开销 |
| C2 | 清理死枚举 `rejected` | 本报告 §1.2 | 要么实现它（Phase 3 拒绝且用户选"接受现状前先明确拒绝"），要么从枚举移除 | S | 无 |

### D 组：下游衔接（跨技能，超出 plan 单技能范围，单列讨论）

| # | 方向 | 来源 | 改法 | 量 | 权衡 |
|---|---|---|---|---|---|
| D1 | 测试锚点进计划 | writing-plans TDD 结构 | Implementation Steps 每阶段强制带"验证方式：具体测试名 + 断言要点"，sprint 拆 feature 时验收标准从计划继承客观锚点 | M | plan 与 sprint 两个技能需协同改 |
| D2 | 独立评审层进 ghs:code | SDD 每任务评审 | feature 完成后由独立子代理对照验收标准评审（可先做并行模式，单模式后跟） | L | 成本显著上升；涉及 code 技能重构 |

### 待决策问题清单

1. **形态**：保持三角色流水线（修内容侧），还是收敛为"人在环受限会话"（B2 是最低成本的中间态）？
2. **用户介入深度**：B1/B2 各加一轮交互，可接受度如何？是否做成可跳过（superpowers 的"别问了直接做"出口）？
3. **A 组先行**：A1-A4 均为模板/量表级小改，是否作为第一期独立落地，与 B 组解耦？
4. **D 组范围**：本次重构是否包含 ghs:code 侧（D2），还是严格限定在 plan 技能？
5. **评审者与设计者的模型档位**：是否在 SKILL.md 中显式建议 designer/reviewer 使用更强模型（当前仅快照子代理指定 haiku）？

---

## 附：源码位置索引

| 系统 | 关键文件 |
|---|---|
| ghs:plan | `plugin/skills/ghs-plan/SKILL.md` · `plugin/shared/references/plan-designer.md` · `plugin/shared/references/plan-reviewer.md` · `plugin/shared/scripts/parse_delimited_output.py` · `plugin/skills/ghs-sprint/SKILL.md` · `plugin/skills/ghs-code/SKILL.md` |
| Codex | `codex-rs/collaboration-mode-templates/templates/plan.md` · `codex-rs/core/src/tools/handlers/plan.rs` · `codex-rs/core/src/session/turn_input.rs` · `codex-rs/core/src/session/turn.rs`（PlanModeStreamState） · `codex-rs/protocol/src/config_types.rs`（ModeKind） |
| OpenCode | `packages/core/src/plugin/plan.ts` · `packages/schema/src/agent.ts` · `packages/core/src/session/runner/prompt/system.txt` · `packages/core/src/plugin/system-prompt/gpt.txt` |
| superpowers | `skills/brainstorming/SKILL.md` · `skills/brainstorming/builder-check-prompt.md` · `skills/writing-plans/SKILL.md` · `skills/subagent-driven-development/SKILL.md`（执行侧） |

（codex/opencode 源码为临时克隆，位于 `/tmp/planmode-src/`，未纳入本仓库。）
