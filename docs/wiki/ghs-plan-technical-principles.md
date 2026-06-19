# ghs:plan 技术原理

> 本文系统阐述 `ghs:plan` 技能的设计原理与架构思路。目标读者是想理解「如何用 LLM 稳定产出高质量技术方案」这一问题的工程师。
>
> 文档聚焦于**为什么这么设计**以及**每个组件解决什么问题**——读完应能理解整体架构、各环节的设计取舍，并具备复刻这套机制的基本地图。具体的 prompt 模板、解析脚本、文件命名规范等实现细节以源代码为权威。

## 目录

- [1. 问题定义：LLM 用于技术方案生成的固有困境](#1-问题定义llm-用于技术方案生成的固有困境)
  - [1.1 单次生成的质量不稳定](#11-单次生成的质量不稳定)
  - [1.2 自我审查有同质化倾向](#12-自我审查有同质化倾向)
  - [1.3 人工审查的有效性有限](#13-人工审查的有效性有限)
  - [1.4 多智能体自由对话不可控](#14-多智能体自由对话不可控)
  - [1.5 设计目标](#15-设计目标)
- [2. 整体架构](#2-整体架构)
  - [2.1 四个角色](#21-四个角色)
  - [2.2 通信拓扑](#22-通信拓扑)
  - [2.3 架构形塑的四个倒推](#23-架构形塑的四个倒推)
- [3. 核心设计原则](#3-核心设计原则)
  - [3.1 确定性优先于 LLM 自治](#31-确定性优先于-llm-自治)
  - [3.2 隔离优先于共享上下文](#32-隔离优先于共享上下文)
  - [3.3 文件优先于消息](#33-文件优先于消息)
  - [3.4 错误显式优于静默挂起](#34-错误显式优于静默挂起)
  - [3.5 软硬双上限保证终止](#35-软硬双上限保证终止)
- [4. 各组件设计详解](#4-各组件设计详解)
  - [4.1 Dispatcher：编排大脑](#41-dispatcher编排大脑)
  - [4.2 Context Subagent：项目认知的抽取者](#42-context-subagent项目认知的抽取者)
  - [4.3 Plan Designer：方案的生产者](#43-plan-designer方案的生产者)
  - [4.4 Plan Reviewer：方案的独立审查者](#44-plan-reviewer方案的独立审查者)
  - [4.5 状态机：status.json](#45-状态机statusjson)
  - [4.6 Parser：确定性解析的边界](#46-parser确定性解析的边界)
  - [4.7 Handling 流程：happy path 与 error path 的精确取舍](#47-handling-流程happy-path-与-error-path-的精确取舍)
- [5. 流程编排与终止保证](#5-流程编排与终止保证)
  - [5.1 完整流程](#51-完整流程)
  - [5.2 两个独立的失败计数器](#52-两个独立的失败计数器)
  - [5.3 终止论证](#53-终止论证)
- [6. 上下文与 Token 经济](#6-上下文与-token-经济)
  - [6.1 模型分层：任务派给能胜任的最便宜模型](#61-模型分层任务派给能胜任的最便宜模型)
  - [6.2 内容传递：用文件路径替代内容嵌入](#62-内容传递用文件路径替代内容嵌入)
  - [6.3 硬调用预算：阻止子代理无限探索](#63-硬调用预算阻止子代理无限探索)
  - [6.4 终止保证即成本保证](#64-终止保证即成本保证)
- [7. 参考实现文件清单](#7-参考实现文件清单)

## 1. 问题定义：LLM 用于技术方案生成的固有困境

技术方案生成是对正确性、完备性、项目契合度都有高要求的任务。把 LLM 直接用于这件事会遇到几个层层叠加的困难，理解这些困难是理解后续所有设计选择的前提。

### 1.1 单次生成的质量不稳定

LLM 单次输出受上下文窗口限制，容易遗漏：
- 边界条件与异常路径
- 项目既有的架构约束与编码约定
- 跨模块的副作用与依赖

而且 LLM 在长输出中常出现「前文严谨、后文松懈」的衰减现象——开头的背景分析做得认真，到风险与缓解段就开始空泛。

### 1.2 自我审查有同质化倾向

让同一个 LLM「先生成再自查」，由于模型对自身输出的盲点一致性，很难发现自己逻辑里的结构性问题。审查往往停留在表层（错别字、措辞调整），而不是深层（架构选型、并发安全、数据一致性）。

### 1.3 人工审查的有效性有限

用户审查虽然能发现一些问题，但对深层技术问题的识别能力受限于投入时间和专业度。简单的「生成 → 用户审 → 修改 → 用户再审」循环会让用户疲劳，且容易在某一轮「看起来差不多」后就放行，实际仍藏着严重缺陷。

### 1.4 多智能体自由对话不可控

如果把多个 LLM agent 放在一起自由对话评审，会出现几类问题：
- **上下文累积爆炸**：每轮对话历史都被纳入下一轮上下文，几轮后成本飙升且模型注意力分散。
- **格式漂移**：agent 之间约定的输出格式在多轮中容易走样，导致下游解析失败。
- **无终止保证**：没有明确的「何时停」规则，agent 可能无限来回修改。
- **orchestrator hang**：任何一个 agent 输出异常，编排器可能卡死等不到响应。

### 1.5 设计目标

`ghs:plan` 要构建一个机制，使 LLM 在多轮迭代中**稳定产出可执行的技术方案**，具体要求：

- **质量**：经过若干轮设计-评审迭代后，方案覆盖核心维度、与项目架构契合、无严重缺陷。
- **可控性**：流程必然终止，不会因 LLM 输出异常或用户选择而无限循环。
- **可恢复性**：中途任何故障后都能从持久化状态恢复，不丢工作。
- **成本可控**：每轮上下文独立，不会因轮次增加而线性膨胀。

后续所有设计都可以看作对这四个目标的具体回应。

## 2. 整体架构

`ghs:plan` 采用**严格编排的多角色流水线 + 共享文件系统**的架构。

### 2.1 四个角色

| 角色 | 实现载体 | 职责 | 生命周期 |
|------|---------|------|---------|
| **Dispatcher** | 编排器主进程 | 编排流程、维护状态机、与用户交互 | 全程常驻 |
| **Context Subagent** | 通用或探索型子代理 | 抽取项目上下文快照 | 一次性 |
| **Plan Designer** | 专用子代理 | 设计或修订技术方案 | 每轮派生 |
| **Plan Reviewer** | 通用子代理 | 以架构师视角评审方案 | 每轮派生 |

Dispatcher 是常驻的编排者；其余三者都是按需派生的子代理，各自独立运行，完成后上下文即弃。

### 2.2 通信拓扑

```
                    ┌─────────────┐
                    │   User      │
                    └──────┬──────┘
                           │ AskUserQuestion
                           │ (唯一的用户交互通道)
                    ┌──────▼──────┐
                    │ Dispatcher  │
                    └──┬───┬───┬──┘
              派生/读取 │   │   │ 派生/读取
              ┌────────┘   │   └────────┐
              │            │            │
        ┌─────▼────┐ ┌─────▼────┐ ┌─────▼────┐
        │ Context  │ │ Designer │ │ Reviewer │
        │ Subagent │ │          │ │          │
        └─────┬────┘ └─────┬────┘ └─────┬────┘
              │            │            │
              │   写/读    │   写/读    │
              ▼            ▼            ▼
         ┌────────────────────────────────┐
         │   .ghs/plans/  (共享文件系统)   │
         │                                │
         │   {slug}-context.md            │
         │   {slug}.md  (plan)            │
         │   {slug}-review.md             │
         │   {slug}-status.json           │
         └────────────────────────────────┘
```

关键性质：

- **Designer 和 Reviewer 之间没有直接通信**。它们各自只读写共享文件系统中的特定文件。
- **Dispatcher 不直接面对 codegraph 等大输出源**。所有大查询封装在 Context Subagent 中。
- **唯一的用户交互通道是 Dispatcher 的 AskUserQuestion**。Designer / Reviewer 不能直接问用户问题。

### 2.3 架构形塑的四个倒推

这个架构的形式不是凭空想象的，而是由四个核心问题倒推出来的：

1. **如何避免多轮上下文累积？** → 每个子代理上下文独立、用完即弃，dispatcher 主进程不接收子代理的原始大输出。
2. **如何避免 LLM 自我审查的同质化？** → 用独立的 Reviewer 子代理，它看的是 plan 文件而非 Designer 的对话历史，视角天然不同。
3. **如何避免 dispatcher 在异常输出上卡死？** → 子代理输出全部经过确定性 parser 解析为结构化 JSON，dispatcher 只看 JSON 字段决策，不直接处理原始文本。
4. **如何让流程可中断可恢复？** → 所有状态写入 status.json，所有产物落入文件系统，任何 crash 后都能从 status 字段恢复。

## 3. 核心设计原则

整个设计的每一处细节都可以追溯到以下五条原则之一。它们彼此呼应，共同构成 `ghs:plan` 的设计骨架。

### 3.1 确定性优先于 LLM 自治

**问题**：LLM 在结构化任务（解析、分类、状态推进）上不可靠。让它自己解析另一个 LLM 的输出，或自己判断「评审是否通过」，出错率不可接受——一旦出错，编排器要么 hang，要么基于错误判断推进。

**原则**：凡是能用确定性代码完成的事，绝不交给 LLM。LLM 只承担它真正不可替代的部分（创意性的方案设计、需要判断力的架构评审）。

**体现**：
- 子代理输出的解析由独立的 `parse_delimited_output.py` 完成，dispatcher 只读 parser 返回的结构化 JSON。
- 评审「是否通过」的判断不靠 dispatcher 重读评审报告，而是 parser 提取 verdict 字段（PASS/FAIL）直接给出。
- 状态机推进由 dispatcher 根据 status 字段确定性完成，没有「感觉差不多了就推进」的模糊判断。

**收益**：LLM 输出格式的偶然漂移（漏写分隔符、verdict 写进正文）被隔离在 parser 边界内，不会污染编排器逻辑。parser 内部可以做多级 fallback、容错、retry，这些都是确定性代码擅长的事。

### 3.2 隔离优先于共享上下文

**问题**：如果编排器把所有历史对话、所有子代理输出、所有 codegraph 查询结果都堆在自己的上下文里，几轮之后：（a） 上下文成本爆炸；（b） 模型注意力被早期信息稀释，后期决策质量下降；（c） 任何子代理的格式漂移都永久污染主上下文。

**原则**：每个执行单元（dispatcher、各子代理）只持有完成任务所需的最小上下文，且生命周期结束后上下文即弃。

**体现**：
- Context Subagent 一次性抽取项目快照写入文件，dispatcher 永远不直接看 codegraph 输出。
- Designer 子代理每轮重新派生，只看 context snapshot 文件 + plan/review 文件，不知道前几轮的对话。
- Reviewer 同理，每轮独立派生。
- 用户与 dispatcher 的交互通过 AskUserQuestion，结论被序列化回 status.json，而不是留在对话历史里。

**代价与收益**：代价是子代理每轮要重新读文件、重新建立认知，有一定重复成本；收益是上下文规模与轮次无关，流程可以无限轮次而不退化。

### 3.3 文件优先于消息

**问题**：多 agent 直接对话（互相发消息）有几个隐患：（a） 消息历史只能增长不能收缩；（b） 消息内容只在内存里，crash 即丢失；（c） 第三方很难审计「当时到底说了什么」。

**原则**：agent 之间的所有信息交换通过文件系统完成。文件是唯一的信息载体。

**体现**：
- 三种产物文件（context、plan、review）是 Designer/Reviewer 之间唯一的通信介质。
- status.json 是流程状态的唯一快照，任何时刻读它都能知道「现在在哪一步」。
- 即便是 dispatcher ↔ 用户的 AskUserQuestion 决策，也被序列化回 status 字段持久化。

**收益**：流程**可中断**（任何一步停下都能从文件恢复）、**可审计**（事后能完整回放每一步）、**可调试**（出问题时直接看文件内容定位）。

### 3.4 错误显式优于静默挂起

**问题**：编排器处理 LLM 输出时，最危险的失败模式不是「报错退出」，而是「静默挂起」——某个分支没考虑到，流程卡在那一步永远不前进，用户也看不到明确提示。

**原则**：任何可能让流程停滞的情况都必须有显式的处理分支，而不是默认「应该不会发生」。

**体现**：
- 解析失败 → 自动 retry，而不是当作「无输出」继续。
- retry 用尽 → 显式询问用户决策，而不是默默接受 fallback。
- verdict 字段缺失 → 视作格式漂移走 retry，而不是默认 PASS 推进（否则一个未通过评审的方案可能被当成通过）。
- 用户在 max_rounds 边界 → 显式询问「继续/接受/终止」，而不是 silent continue。

**收益**：每一个边界情况都有确定路径，编排器不会因为输入异常而无限等待。

### 3.5 软硬双上限保证终止

**问题**：迭代型流程最大的风险是「停不下来」。如果用户每次都在 max_rounds 边界选「再来一轮」，理论上可以无限循环。

**原则**：设置软上限（可有限突破）和硬上限（不可突破），保证无论用户怎么选，流程必在有限步内进入终态。

**体现**：
- 软上限 `max_rounds`（默认 5）：正常的「设计-评审」循环轮次上限。
- 硬上限 `MAX_BREACHES`（默认 2）：用户在软上限边界「硬继续」的次数上限。
- 总轮次硬性封顶为 `max_rounds + MAX_BREACHES`。达到硬上限后，菜单中「继续」选项消失，用户只能「接受当前方案」或「终止」。
- Phase 3 的用户驳回路径与 Phase 2 的 FAIL 路径共用同一套双上限，**不存在任何 silent continue 通道**。

**收益**：流程必然终止，有数学保证。无论 LLM 输出多么异常、用户多么想继续，都会在已知上界内进入 `approved` 或 `aborted`。

## 4. 各组件设计详解

### 4.1 Dispatcher：编排大脑

Dispatcher 是编排器的主进程，承担四个职责：

1. **流程编排**：根据 status.json 的当前状态决定下一步派谁、传什么 prompt。
2. **状态机维护**：每次状态变更都同步写入 status.json。
3. **用户交互**：通过 AskUserQuestion 询问需求、获取批准、收集决策。
4. **结果落盘**：把子代理输出经过 parser 处理后写入对应的产物文件。

Dispatcher **明确不做**的事：

- **不自己解析子代理原始输出**（交给 parser）
- **不自己跑 codegraph 大查询**（交给 Context Subagent）
- **不自己设计方案或评审**（交给 Designer / Reviewer）

这种「编排与执行严格分离」的设计，目的是让 dispatcher 的逻辑保持简单可预测——它本质上就是一个状态机驱动器，所有复杂度都被推到子代理和 parser 边界外。dispatcher 代码越简单，bug 越少，越容易推理。

### 4.2 Context Subagent：项目认知的抽取者

#### 为什么需要独立抽取

如果没有 Context Subagent，Designer 和 Reviewer 各自去探索项目代码，会有三个问题：

- **重复探索**：每个子代理、每一轮都要重新理解项目。
- **上下文污染**：如果 dispatcher 直接调 codegraph，大输出（KB 级）会永久占用主上下文。
- **能力不确定**：codegraph 是可选 MCP，不同项目可用性不同，需要探测。

把项目认知的抽取独立成一个一次性子代理，这三个问题同时解决。

#### 关键设计

- **一次性派生**：Phase 0.5 派生一次，产物写入 `{slug}-context.md` 后即弃，dispatcher 主上下文从不接触 codegraph 原始输出。
- **能力探测**：dispatcher 先用最小开销的 status 调用确认 codegraph 是否可用（只返回文件数/节点数/边数，输出约 1KB），把可用性作为参数传入子代理 prompt。
- **双模板派生**：可用时用 `general-purpose` + codegraph MCP；不可用时用 `Explore` + grep/glob/read。两个模板的输出协议完全一致（同样的分隔符、同样的字段结构），让下游 parser 无感知——下游永远不需要关心 codegraph 是否可用。
- **预算约束**：模板内强制调用预算（如最多 1 次 `codegraph_files` + 1 次 `codegraph_explore`），避免子代理陷入无限探索。预算不够覆盖某个细节时，子代理不允许 follow-up 查询，而是把缺口写入快照可选的第五段「Known Gaps」——明示 Designer 后续自行补。这是硬调用预算机制的出气口：用文档化缺口替代额外调用，把「是否再查」的决策权交给下游（详见 [§6.3](#63-硬调用预算阻止子代理无限探索)）。
- **输出协议**：固定用 `<<<CONTEXT_SNAPSHOT_START>>>` / `<<<CONTEXT_SNAPSHOT_END>>>` 包围，内部按「技术栈 / 目录结构 / 架构摘要 / 相关代码节选」四段组织，目标 50-70% 压缩比——既保留必要细节，又控制下游读取成本。

#### 注入防护

用户输入的需求描述在替换进 prompt 模板前，要过滤掉分隔符字面量（防止用户输入恰好包含 `<<<CONTEXT_SNAPSHOT_START>>>` 字符串破坏 parser）。这是一个小但必要的细节——**任何把外部输入嵌入结构化模板的地方都需要考虑注入**。

### 4.3 Plan Designer：方案的生产者

#### 角色定位

Designer 是负责产出方案正文的子代理。每一轮的设计阶段都派生一个全新的 Designer 实例：

- **Round 1**：基于 context snapshot 全新设计。
- **Round 2+**：基于上一轮的 plan 文件 + review 文件修订，要求显式回应每一条 Severe/Medium 问题。

#### 关键约束

- **必须先读 context snapshot**：不能凭空设计。snapshot 不够时允许回退到原始文件，但必须把额外读过的文件列出来（`ADDITIONAL FILES READ:` 信号行），供 Phase 2.5 把摘要追加到 snapshot，让下一轮受益——这是**知识只增不减**的关键机制。
- **不直接写文件**：Designer 子代理没有文件写权限，输出在响应正文里，由 dispatcher 落盘。这是为了所有写入都经过 parser 校验，避免格式错误的内容直接落盘。
- **结构化输出协议**：用 `<<<PLAN_START>>>` / `<<<PLAN_END>>>` 包围方案正文，末尾跟 completion signal 行（`PLAN DESIGN COMPLETE`）。这样 parser 能可靠抽出方案主体，不受响应中其他文字干扰。
- **可问问题**：如果有需要用户澄清的关键问题，可以输出 `QUESTION:` 行，dispatcher 会用 AskUserQuestion 中转给用户，拿到答案后用「原 prompt + 答案」重派。这条路径不落任何临时文件（响应短不需要持久化）。

#### 方案结构

Designer 产出的方案包含六段：**背景与目标 / 现状分析 / 方案设计 / 实施步骤 / 风险与缓解 / 测试策略**。这六段对应了「为什么要做 / 现状如何 / 怎么做 / 具体步骤 / 可能出什么问题 / 怎么验证」的完整推理链。任何一段缺失都会被 Reviewer 的 12 维 checklist 捕捉到。

### 4.4 Plan Reviewer：方案的独立审查者

#### 为什么需要独立 Reviewer

让 Designer 自己复查，会受模型对自身输出盲点一致性的影响；让用户审查，深度受用户专业度限制。独立的 Reviewer 子代理带有一个关键性质：**它从未见过 Designer 的对话历史**，只看 plan 文件本身。这种「无记忆的审查者」能避免确认偏误，被迫从方案本身的逻辑出发重新评估。

#### 评审维度

Reviewer 按 12 维 checklist 评审：需求覆盖、架构一致性、技术选型、数据模型、接口设计、错误处理、边界条件、实施步骤、性能、安全、可测性、风险缓解。这覆盖了「方案是否完整且正确」的主要面。

#### 严重度三级（核心机制）

每一条评审反馈必须打上严重度标签：

| 级别 | 定义 | 典型场景 |
|------|------|----------|
| **Severe** | 不修会导致 bug、数据丢失、安全漏洞；或方案逻辑本身错误 | 未处理的并发/竞态、错误的安全假设、数据一致性问题 |
| **Medium** | 方向对但实施路径有问题、设计欠优；增加技术债 | 抽象层级不合理、缺失错误处理、N+1 查询 |
| **Optimization** | 不影响正确实施，采纳更好 | 命名建议、可选缓存策略、文档补充 |

**通过准则：零 Severe 和零 Medium**（只允许 Optimization）。

三级分类是 Reviewer 机制有效性的核心，设计上经过深思熟虑：

- 如果只有「通过/不通过」，Reviewer 倾向于报喜不报忧，流于形式。
- 如果只数问题数量，Designer 容易通过修若干小问题凑数过关。
- 三级分类强制 Reviewer 对每条反馈表态「这个有多严重」，而「零 Severe + 零 Medium」的硬性门槛让凑数变得困难——只要有任何一条结构性问题就不能通过。

#### 输出协议

```
<<<REVIEW_START>>>
...评审报告正文...
<<<REVIEW_END>>>
REVIEW COMPLETE | Verdict: PASS|FAIL | Severe: X Medium: Y Optimization: Z
```

最后一行是 verdict 信号行，parser 从中提取 verdict 字段（PASS/FAIL）。dispatcher 根据 verdict 决定下一步——**不自己重读评审报告判断「是否通过」**，这是 [§3.1](#31-确定性优先于-llm-自治) 确定性原则的具体落地。

### 4.5 状态机：status.json

status.json 是流程状态的唯一快照。它的设计有一个核心原则：**审计维度与状态枚举分离**。

#### 完整字段一览

| 字段 | 类型 | 含义 |
|------|------|------|
| `plan_file` | string | 当前 plan 文件名（`{date}-{slug}.md`）|
| `context_file` | string | 当前 context 文件名（`{date}-{slug}-context.md`）|
| `round` | int | 当前轮次，从 1 开始 |
| `status` | enum | 流程状态，见下文枚举 |
| `max_rounds` | int | 软上限，默认 5 |
| `max_rounds_breaches` | int | 硬继续计数器，默认 0，封顶 `MAX_BREACHES` |
| `accepted_with_fail` | bool | Phase 4 是否带病通过 |
| `keep_raw_on_success` | bool | 调试开关，强制 happy path 也写 raw |
| `created_at` | ISO 8601 | 创建时间戳 |
| `updated_at` | ISO 8601 | 最后更新时间戳 |

#### 状态枚举（流程语义）

`status` 字段只有流程语义，枚举为：

`designing | reviewing | revising | pending_approval | approved | rejected | aborted`

每个值唯一对应流程中的一个阶段，驱动 dispatcher 的下一步动作。这个枚举集是 closed set——不为了审计目的新增值。

#### 审计维度（独立标记）

与流程状态正交的审计维度独立为单独的字段：

- `max_rounds_breaches`：用户在 max_rounds 边界「硬继续」的次数计数。
- `accepted_with_fail`：Phase 4 终结时方案是否带病通过（仍有未修的 Severe/Medium）。
- `keep_raw_on_success`：调试开关，强制在 happy path 也写 post-mortem raw。

这些维度**不污染 status 枚举**。比如一个「带病通过」的方案，其 status 仍是 `approved`（终态语义不变），但 `accepted_with_fail: true` 让事后可以 `grep` 找出所有带病通过的方案。状态机的纯净度与审计的灵活度两全。

#### 可恢复性

由于状态全部序列化在 status.json，任何 crash 后重启都能从 status 字段恢复到准确位置。设计师产出的 plan 文件、评审者产出的 review 文件、上下文快照文件都是普通磁盘文件，不会因 crash 丢失。这是 [§3.3](#33-文件优先于消息) 文件优先原则的具体收益。

### 4.6 Parser：确定性解析的边界

`parse_delimited_output.py` 是 dispatcher 读取子代理输出的**唯一可信源**。它存在的意义是把「LLM 输出的不确定文本」转化为「结构化的 JSON 字段」，让 dispatcher 不必关心文本处理的复杂性。

#### 为什么 dispatcher 不自己解析

如果 dispatcher 自己用 regex 解析子代理输出，会有几个问题：

- LLM 输出格式偶然漂移时，dispatcher 要在多个 fallback 路径中切换，逻辑复杂。
- dispatcher 的上下文里堆满原始 LLM 输出（可能 KB 级），违反隔离原则。
- 解析逻辑演进时，要修改 dispatcher 的核心流程，而不是修改一个独立脚本。

把解析独立成脚本后：

- dispatcher 只看 JSON 字段，代码简单。
- 解析逻辑可以独立测试、独立演进。
- 子代理原始输出可以走临时文件传入 parser（`--input-file`），dispatcher 主上下文从不见到原始文本。

#### 关键设计

- **输入方式**：支持 `--stdin` / `--input-file` / `--input-string` 三种互斥方式。生产中只用 `--input-file`，shell 永远看不到响应内容，注入面为零。
- **多级 fallback 策略**：按优先级依次尝试四种抽取策略——`exact_delimiter`（字面分隔符）/ `normalized_delimiter`（容忍全角/半角标点变体）/ `code_fence`（最大围栏块）/ `whole_body`（剥离 thinking 和信号行后整体）。只有 `exact_delimiter` 命中才返回 `ok`，其余返回 `fallback_used` 让 dispatcher 决定是否警告。命中的策略名直接回显在 JSON 的 `strategy` 字段，事后 grep 调试可见。
- **thinking 兼容层**：所有策略之前先用 `_strip_thinking` 剥离 `<thinking>...</thinking>` 和 `<antml:thinking>...</antml:thinking>` 块——前者是现代 extended-thinking API 的产物，后者是 legacy/第三方网关的兼容。无论 LLM 走哪条 thinking 路径，parser 都看到干净的响应正文。
- **kind 区分**：不同产物（context / plan / review）有不同的最小长度阈值和分隔符 token 名，避免互相污染。
- **verdict 提取**：对 review 类型，从信号行提取 `Verdict: PASS|FAIL`。这是 dispatcher 决策的唯一依据。
- **状态码分类**：返回 `ok` / `fallback_used` / `empty` / `malformed`，让 dispatcher 按不同失败模式走不同恢复路径——`empty` 是找到过短内容（可能是分隔符写对但内容缺失），`malformed` 是完全找不到分隔符（可能是格式彻底走样），两者的恢复策略不同。

### 4.7 Handling 流程：happy path 与 error path 的精确取舍

dispatcher 接到子代理响应后，走一套统一的 Handling 流程（Phase 0.5 / Phase 1 / Phase 2 共用）。这条流程体现了一个核心取舍：**调试可见性 vs 目录整洁度**。

#### Happy path（解析成功）

1. **响应暂存内存**：不在主目录落盘，保持目录整洁。
2. **写临时文件**：到 `.ghs/plans/.tmp/<session_id>.<kind>.raw`（parser 的输入介质，只在 parser 运行期间存在）。`<session_id>` 维度让多个 ghs:plan 会话可以并行运行而不互相覆盖临时文件——这是并发安全的关键。
3. **parser 读取临时文件**：dispatcher 拿到结构化 JSON。
4. **按 JSON 字段推进**：status 置为下一阶段，把产物内容写入正式文件。
5. **删除临时文件**：任务完成，清理痕迹。

#### Error path（解析失败）

1. **写 post-mortem raw**：在主目录写 `<file>.raw`（或 `.raw.retry<T>`），保留原始响应供事后诊断。
2. **retry_count < MAX_RETRY**：重派子代理，在原 prompt 后附加 Format Recovery appendix（强调分隔符字面输出、不包代码块、verdict 行格式等），**保持同一 subagent_type 和模板**——避免切换模板引入新的失败变量。
3. **retry_count ≥ MAX_RETRY**：用 AskUserQuestion 询问用户三选一：再试一次（一次性突破 MAX_RETRY，但仍受总轮次硬上限约束）/ 接受 fallback 抽取的内容（在文件头部 prepend warning 注释）/ 终止。

#### 为什么这样设计

- **临时文件用完即删**：它的唯一使命是给 parser 提供输入，任务完成后没有保留价值。
- **post-mortem raw 只在失败时落盘**：解析成功时根本不需要事后看原始输出，所以不写。这一处不对称体现了「调试可见性」只为失败场景买单。
- **retry 走 fallback 路径而不是 happy path**：重派时不能直接覆盖已有产物，所以走 `.raw.retry<T>` 命名，与首次失败的 `.raw` 区分。
- **用户决策兜底**：retry 用尽后，把决策权交还用户，而不是默默接受 fallback（可能写入低质量内容）或默默终止（浪费已有工作）。

## 5. 流程编排与终止保证

### 5.1 完整流程

```
Phase 0    初始化:解析项目目录、确认需求、写初始 status
   │
   ▼
Phase 0.5  上下文快照抽取:派 Context Subagent,写 context 文件
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│  Round N 循环(1 ≤ N ≤ max_rounds + MAX_BREACHES)       │
│                                                         │
│  Phase 1  Plan Design:派 Designer → 写 plan 文件        │
│     │                                                   │
│     ▼                                                   │
│  Phase 2  Plan Review:派 Reviewer → 评审                │
│     │                                                   │
│     ├─ PASS @ round 1 → Phase 3 (early stop)            │
│     ├─ PASS @ round 2+ → Phase 2.5(可选,补快照)→ Phase 3 │
│     ├─ FAIL 且 round < max_rounds  → Round N+1          │
│     └─ FAIL 且 round ≥ max_rounds  → 用户决策           │
└─────────────────────────────────────────────────────────┘
   │
   ▼
Phase 3    User Approval:AskUserQuestion 请求用户确认
   │       ├─ approve → Phase 4
   │       └─ reject  → 回 Phase 1(同样受双上限约束)
   │
   ▼
Phase 4    Finalization:复制到 docs/ghs/plans/、git commit、置 approved
```

每个 Phase 的产物和决策都已序列化在 status.json 或对应文件中，任何中断都能从文件状态精确恢复。

### 5.2 两个独立的失败计数器

整个流程有两个独立的计数器，分别处理两类性质完全不同的失败：

| 计数器 | 默认值 | 针对的失败 | 触发条件 |
|--------|--------|-----------|----------|
| `MAX_RETRY` | 1 | 单次子代理调用的**格式漂移** | parser 返回 empty/malformed |
| `MAX_BREACHES` | 2 | 设计-评审循环**质量不达标但流程未完** | 用户在 max_rounds 边界 opt-in 继续 |

这两个计数器正交——retry 失败不会消耗 breach 配额，breach 也不会消耗 retry 配额。它们的共同作用是确保任何失败路径最终都汇聚到用户决策或终态，而不是无限循环。

之所以区分两套计数器，是因为两类失败的「治愈方式」不同：格式漂移重试一次通常能解决（LLM 偶然走样），所以 MAX_RETRY 设得很小；质量不达标是方案本身的问题，需要新一轮设计-评审，所以走 breach 通道，但又要避免用户无限制地「再来一轮」。

### 5.3 终止论证

无论用户怎么选择、无论 LLM 输出多么异常，流程必然在 `max_rounds + MAX_BREACHES` 轮内进入 `approved` 或 `aborted`：

- 每一轮 Round 都会推进 round 计数（round++）。
- round 达到 max_rounds 后，继续需要消耗 breach 配额（breaches++）。
- breach 配额用尽后，「继续」选项从用户菜单中消失。
- 用户只有「接受当前方案」或「终止」两个选项，前者进入 Phase 4（`approved`），后者进入 `aborted`。
- 即使在 retry 路径中，每次 retry 也只突破 MAX_RETRY 一次，用户决策菜单始终包含「终止」选项。

因此流程的轮次上界是 `max_rounds + MAX_BREACHES`，有严格数学保证。

## 6. 上下文与 Token 经济

LLM 工作流受两个硬约束：**context window 有限**、**token 按量计费**。多轮迭代工作流如果不主动设计，这两个约束都会快速恶化——上下文随轮次线性膨胀，成本随轮次线性甚至超线性增长。

[§3.2](#32-隔离优先于共享上下文)、[§3.3](#33-文件优先于消息)、[§3.5](#35-软硬双上限保证终止) 已经从**原则**上回答了「为什么不爆炸」。本章从**机制**层面补充：具体是哪些设计，把那几条原则落成了可量的成本控制。

### 6.1 模型分层：任务派给能胜任的最便宜模型

**问题**：不同子任务对推理深度的要求差异极大。代码库快照抽取需要广度但不需要深度推理；方案设计需要深度推理；评审需要判断力。所有子代理用同一个模型，要么成本不可控（全用高能力模型），要么质量不可控（全用低能力模型）。

**设计**：按任务的认知负担选择模型层级。

**体现**：

- **Context Subagent 用 `haiku`**：快照抽取本质是「读取 + 摘要」，不需要深度推理，但要处理较大输入。`haiku` 在大上下文里游刃有余，单价远低于更高能力的模型（如 Sonnet/Opus）。
- **Plan Designer / Reviewer 用各自子代理类型的默认模型**：架构设计与评审需要推理和判断力，留给默认（更高能力）的模型。
- **Dispatcher 用主对话模型**：状态机推进、用户交互需要遵循复杂指令的能力，继承主对话。

**收益**：成本大头（快照抽取的输入 token）落在最便宜的模型上，真正需要推理的部分（设计、评审）用足能力。单轮成本接近「最低必需」。

### 6.2 内容传递：用文件路径替代内容嵌入

**问题**：如果 dispatcher 在派生子代理时把 snapshot / plan / review 的内容**嵌入** prompt，会发生两件事：（a）dispatcher 自己的上下文要先持有这些内容（动辄 KB 级）；（b）每轮派生都把这些内容复制到子代理 prompt 里，token 重复消耗。

**设计**：dispatcher 的 prompt 里**只放文件路径**，不放内容。子代理按需自己读取。dispatcher 自己解析子代理输出时也走 `--input-file`——主上下文从不直接看到子代理响应内容。

**体现**：

- Designer 模板把 context snapshot 作为**文件路径**传入，附「READ THIS FILE FIRST」指令——子代理自己 open 文件读取。
- Reviewer 模板同样把 plan_file 作为路径传入。
- Dispatcher 调用 parser 时用 `--input-file`，parser 从临时文件读取响应——只有 parser 返回的几十字节 JSON 字段进入 dispatcher 决策。

**收益**：dispatcher 主上下文规模与产物文件大小解耦，不随快照/方案变长而膨胀。

### 6.3 硬调用预算：阻止子代理无限探索

**问题**：Context Subagent 拿到 codegraph 后，如果没有约束，很容易陷入「再查一个、再查一个」的探索螺旋——单次任务可能消耗十几次 `codegraph_explore` 调用，每次都返回大量内容。

**设计**：在 prompt 模板里写死**硬调用预算**，子代理不允许超出；并要求快照达到 50-70% 压缩比（包含函数签名、schema、路由，而非整文件）。

**体现**：

- 至多 1 次 `codegraph_files(maxDepth=3)` 调用。
- 至多 1 次 `codegraph_explore(query="...")` 调用，**所有关键词 facet 合并到单个查询**，不拆分。
- 单次 explore 不够覆盖某个细节时，**不允许 follow-up**，而是把缺口写入 `Known Gaps` 段——明示 Designer 后续自行补。

另外，模板要求快照达到 50-70% 压缩比：摘要是签名/schema/路由，不是整段代码——这把「读多少」和「写多少」都钉死在可控范围。

**收益**：Context Subagent 的总调用数被压到常数级（2 次），成本可预测。`Known Gaps` 把「是否再查」的决策权交给 Designer——后续真需要某细节时，它会通过 `ADDITIONAL FILES READ` 单独读那个文件，而不是让 Context Subagent 笼统地多查一遍。

### 6.4 终止保证即成本保证

[§3.5](#35-软硬双上限保证终止) 的双上限机制不只保证流程终止，也直接界定了**总成本上界**：

- 子代理调用次数硬性上界：`(max_rounds + MAX_BREACHES) × 2 + 1`（每轮一次 Designer + 一次 Reviewer，加上一次性的 Context Subagent）。默认配置下为 15 次。
- 加上 `MAX_RETRY` 上界，即使在最坏情况下（每次调用都触发一次格式 retry），总调用数也只翻倍到约 30 次。
- Dispatcher 主对话的轮次与子代理调用数成正比，因此也是常数级。

任何输入和任何用户选择下，总 token 成本和总执行时间都有已知上界，可以事先估算。这让 `ghs:plan` 适用于 CI/批处理场景——不会出现「跑了一晚上还在转」的情况。

## 7. 参考实现文件清单

| 路径 | 角色 |
|------|------|
| `plugin/skills/ghs-plan/SKILL.md` | 技能定义（prompt 模板、流程描述）|
| `plugin/shared/scripts/parse_delimited_output.py` | 确定性解析器（权威实现）|
| `plugin/shared/scripts/resolve_project_dir.py` | 项目目录解析 |
| `plugin/shared/references/plan-designer.md` | Designer 详细指令 |
| `plugin/shared/references/plan-reviewer.md` | Reviewer 详细指令（含严重度标准）|
| `plugin/shared/references/context-snapshot-guide.md` | 快照格式与抽取指南 |
| `${PROJECT_DIR}/.ghs/plans/` | 过程产物（gitignore）|
| `${PROJECT_DIR}/.ghs/plans/.tmp/` | parser 输入临时文件（即时清理）|
| `${PROJECT_DIR}/docs/ghs/plans/` | 最终方案归档（git 跟踪）|
