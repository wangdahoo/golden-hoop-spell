# 诊断报告：ghs:plan 主对话 token 从 ~50K 涨到 ~141K

> 关联会话：`ab9609c9`（174 行），被用户在 Phase 0.5「项目上下文快照」阶段打断（L171）。完整的设计 + 评审循环尚未开始，仅 Phase 0.5 就吃掉 ~90K 增量。

## 一、Token 增长曲线（按 assistant turn）

| 阶段 | 行号 | total ≈ | 增量 | 原因 |
|------|------|---------|------|------|
| 加载 ghs:plan SKILL.md | L17–18 | 49K | +49K | system + 技能正文 |
| Phase 0 init | L23–43 | 53K | +4K | 小操作 |
| ToolSearch 加载 codegraph 三件套 | L47 | 55K | cache_read 53K→12K，cache_create +43K（本轮 total +2K） | 工具注册段刷新，prefix 部分失效 |
| TaskCreate × 4 + ToolSearch | L52–72 | 59K | +4K | — |
| `codegraph_files` + 1st `codegraph_explore` | L91 | 68K | +9K | — |
| `explore` × 2（completions / routes） | L106 | 90K | +22K | 结果 22K + 23K chars |
| `explore` × 2（store/AccessKey / crypto） | L121 | 106K | +17K | — |
| `explore`（KBList） + bash(ls migrations) | L133 | 119K | +12K | — |
| `explore`（ServiceContext） + bash(grep) | L146 | 131K | +13K | — |
| Bash × 4（grep migrations / sed kb.ts / App.tsx） | L151–169 | 141K | +10K | — |

**主犯**：Phase 0.5 阶段 dispatcher 直接在主对话里调用了 `1 × codegraph_files + 7 × codegraph_explore + 4 × Bash grep/sed`，原始结果（约 150KB chars / ~50–70K tokens）全部沉淀进主对话上下文。

## 二、三层根因

### 1. 技能设计缺陷：Path A 把原始代码灌进 dispatcher（结构性）

`SKILL.md:118–125` Path A 让 dispatcher **直接调用** codegraph：

> The dispatcher calls codegraph tools directly — no subagent needed

第 3 步是「Condense the output into the context snapshot format」。问题在于：一旦 `tool_result` 进入 dispatcher 对话，它就永远留在上下文里——写 `<context_file>` 文件不会把它从主对话清出。snapshot 文件是给下游 designer/reviewer 子代理重新读的，对 dispatcher 自己毫无减负。

对照 Path B（`SKILL.md:127–142`）：用 Explore 子代理扫描，子代理只回传压缩后的 snapshot 文本（带 `<<<CONTEXT_SNAPSHOT_START>>>` 定界符）——原始代码完全留在子代理上下文里。

→ Path A 在「可用」时被偏好，但它的上下文成本天然高于 Path B。技能正文对此零提示。

### 2. 模型放飞：把 1 次 explore 拆成 7 次（行为层）

`SKILL.md:122–123` 给的 Path A 模板是：

- `codegraph_files` × 1
- `codegraph_explore(query="… architecture")` × 1（单数）

dispatcher 实际把需求拆成 7 个语义切片（tenant / completions / routes / store / crypto / KB / ServiceContext）各跑一次 `explore`，每次 `maxFiles=8–12`。模板没规定上限，也没说「一次解决」，所以模型出于「严谨」做了过度分解。

### 3. ToolSearch 工具注册触发 prefix 失效（harness 层，无关技能）

L43 的 `ToolSearch select:codegraph_status,codegraph_files,codegraph_explore` 把三个 MCP 工具的 schema 加进 `tools` 段。下一轮 L47：

- `cache_read` 从 53K → 12K（旧 prefix 失效 ~41K）
- `cache_create` +43K（重写）

Anthropic API 缓存按 prefix 工作，`tools` 段变化会让其后所有内容失效。ToolSearch 的延迟加载机制存在隐性成本：每次 select 一组新工具，要为后面的 prefix 重新付一次 cache 写入费。session 里发生了两次（L43 加 codegraph，L52 加 Task*）。

## 三、修复建议（按收益排序）

### A. 高收益结构性修复 — 把 Path A 改成「子代理也跑 codegraph」

让 dispatcher 派一个轻量子代理（haiku 即可），子代理调 codegraph 并产出 snapshot，dispatcher 只接收最终文本。Path A 与 Path B 的差异只剩「子代理用 codegraph 还是 grep」，结构对称、上下文成本一致。

### B. 在 Path A 模板加硬约束 — 限定调用次数

`SKILL.md:122–123` 改为：

> Make at most ONE `codegraph_files` call and ONE `codegraph_explore` call. Combine all keyword facets into one query. If the result is insufficient, defer the rest to the designer subagent — do NOT make follow-up exploration calls in the dispatcher.

### C. Phase 0.5 加一个 sanity-check 前置门

参考最近 s4-feat-001/002 给 Verification Phase 加门的做法：在跨入 Phase 1 前，dispatcher 先自检——本阶段在主对话里产生了多少 `tool_result` 字节？超过阈值（例如 30KB）就警告并改走 Path B。

### D. 文档化 ToolSearch 成本

在 `references/` 里加一条：每次 ToolSearch 注册新工具会触发 prefix 重写，建议一次 `select` 把本次 phase 用到的所有工具一起加载，避免分多次 select。L43 + L52 本来可以合成一次。

## 四、与本仓库其他修复的对照

最近三次提交（`a3fe591` / `af3ab13` / `e12c805`）就是在 ghs-code 上做「删冗余段 + 加 sanity check 前置门 + Verification Phase 用 helper」。ghs:plan Phase 0.5 现在表现出几乎一样的病症——该走同样的路子。
