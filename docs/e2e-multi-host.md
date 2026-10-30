# ghs 双宿主端到端验证手册（OpenAI Codex CLI / Pi coding agent）

同一套 ghs 技能源在 Claude Code 之外的两大宿主上以原生形态安装并功能对等运转的端到端验证手册。
单文件多宿主形态：公共腿不重复，宿主差异只在安装（§2）、发现（§3）、派发与交互原语（§6）三处；
与 Claude 基线的回归腿单列 §10。

- 插件：`golden-hoop-spell`，版本 `0.6.0`（Claude 清单 `plugin/.claude-plugin/plugin.json`、Codex 清单
  `plugin/.codex-plugin/plugin.json`、Pi 清单仓库根 `package.json`，三者一致性由
  `command python3 plugin/shared/scripts/validate_manifests.py` 把关）。
- 宿主差异知识：`plugin/shared/references/codex-host.md` 与 `plugin/shared/references/pi-host.md`；
  SKILL.md 正文零宿主差异，唯一入口是各 SKILL.md 的 `## Platform Adaptation` 指针块。

## 0. 记录约定与本轮执行环境

每条记录行格式为 `VERDICT — 说明（输出摘录）`，`VERDICT ∈ {PASS, FAIL, NOT_EXECUTED}`：

- `PASS` — 检查已在本机执行且通过，附真实输出摘录；
- `FAIL` — 检查已在本机执行且未通过，附缺失项与修复动作（FAIL 不阻断手册本身，是给下一轮执行者的待办）；
- `NOT_EXECUTED` — 检查未在本机执行，附原因。无 CLI 或未安装的宿主，其步骤全部标 `NOT_EXECUTED`，手册照常交付。

本轮为手册编写轮（2026-10-30），执行范围受两条约束：**不安装任何插件/扩展包**（不改动用户机器的
`~/.codex`、`~/.pi` 状态），**不启动交互式宿主会话**。因此凡需要安装、`/plugins` 浏览器、宿主会话
（技能调用、子代理派发、交互提问）的步骤一律 `NOT_EXECUTED`，留待人工执行轮补录；本轮只诚实执行
廉价、只读、非安装类的检查（版本探测、配置与缓存布局观测、脚本与测试套件）。

本轮执行环境（真实探测输出）：

- PASS — `codex --version` → `codex-cli 0.162.0`
- PASS — `pi --version` → `0.85.1`
- PASS — `claude --version` → `2.1.292 (Claude Code)`
- PASS — `command python3 --version` → `Python 3.12.5`（Windows 11 + Git Bash）

### 0.1 Codex 宿主前置

1. CLI 在位（见上，`codex-cli 0.162.0`）。
2. 开启 `multi_agent` 特性开关（子代理派发硬前置）。编辑 `~/.codex/config.toml` 追加后重启 CLI 会话：

   ```toml
   [features]
   multi_agent = true
   ```

3. 建议的机器级兜底（可选，ghs 不请求 per-spawn 模型参数，子代理继承机器默认值）：

   ```toml
   [agents]
   default_subagent_model = "<model name>"
   default_subagent_reasoning_effort = "<effort>"
   ```

4. `python3` 在 PATH 上（一律 `command python3` 调用）。

本机实测记录：

- PASS — CLI 版本探测通过（`codex-cli 0.162.0`，见 §0 环境块）。
- FAIL — `multi_agent` 开关未开启：`~/.codex/config.toml` 全文无 `[features]` 段（grep `^\[` 实测节段仅为
  `model_providers/projects/windows/tui/marketplaces/plugins/hooks.state`）。按上方步骤 2 追加后重测。
- FAIL — `[agents]` 兜底段同样缺失（可选建议项，不阻断主路径；按上方步骤 3 酌情补）。
- PASS — `command python3 --version` → `Python 3.12.5`。

### 0.2 Pi 宿主前置

1. CLI 在位（见上，`pi 0.85.1`）。
2. 安装 pi-subagents（三角色流水线与 `--parallel` 的硬前置）：

   ```bash
   pi install npm:pi-subagents
   ```

3. `python3` 在 PATH 上。

本机实测记录：

- PASS — CLI 版本探测通过（`pi 0.85.1`，见 §0 环境块）。
- FAIL — pi-subagents 未安装：`~/.pi/agent/settings.json` 的 `packages` 数组实测仅含
  `"git:git@github.com:wangdahoo/pi-harness"`，无 `pi-subagents`。按上方命令安装后重测；会话内再按
  `pi-host.md` 块 1 用 `{action: "list"}` 复核。
- PASS — `command python3 --version` → `Python 3.12.5`。

## 1. scratch 项目准备

准备一个最小 Git 项目作为 ghs 技能的操作对象（init / plan / code 的靶子）。任意空目录执行：

```bash
SCRATCH=$(mktemp -d)/scratch-e2e && mkdir -p "$SCRATCH" && cd "$SCRATCH"
git init
printf 'def greet():\n    return "hello"\n' > app.py
printf 'scratch-e2e\n' > README.md
git add -A && git commit -m "chore: scratch project bootstrap"
```

- PASS — 本轮已按上述步骤在临时目录实测执行：`git init` 成功、`app.py`/`README.md` 落盘、
  首次提交 `21960a7 chore: scratch project bootstrap` 成功（临时目录随系统清理，无需善后；
  Git 的 LF→CRLF 提示为 Windows 常态，不影响后续步骤）。

## 2. 安装（每宿主本地 + 远程两路）

两条路线覆盖 pi 的 git 源分发与 Codex 的 marketplace 分发；本地路径路线供开发态联调。
安装命令与 `README.md` / `README-zh.md` 安装章节逐字一致。

### 2.1 Codex — 远程 marketplace 路线

```bash
codex plugin marketplace add wangdahoo/golden-hoop-spell
```

随后在 Codex CLI 会话内经 `/plugins` 浏览器完成插件安装（官方用户页无 `codex plugin install`
子命令记载；若实测发现安装子命令，以实测回改 README 与本节）。

- NOT_EXECUTED — 安装类操作不在本轮授权范围（不改动 `~/.codex` 状态），留待人工执行轮。
- 预期落点（待实测校验的假设）：`~/.codex/plugins/cache/<marketplace>/golden-hoop-spell/<version|local>/`。

### 2.2 Codex — 本地路径路线

```bash
codex plugin marketplace add <repo-root>
```

`<repo-root>` 为本仓库检出路径（legacy 读取 `.claude-plugin/marketplace.json`，其单条目 source 为
`./plugin`，指向同时含 `.codex-plugin/plugin.json`、`skills/`、`shared/` 的插件根）。

- NOT_EXECUTED — 同 2.1，安装类操作不在本轮范围。

### 2.3 Codex — 真实缓存布局与 marker env 观测（只读，已执行）

- PASS — `~/.codex/plugins/cache/` 在位，真实层级布局为 `<marketplace>/<plugin>/<version|hash>`，实测样例：
  `openai-api-curated/superpowers/5fd93af4`、`openai-api-curated/github/5fd93af4`、`ponytail/ponytail/5.2.0`。
  与 `test_host_compat.py` 构造的 `golden-hoop-spell@golden-hoop-spell` 扁平 join 形态不同——
  `host_compat.py` 采用递归 glob `**/shared/scripts/ghs_compat.py` 加路径含 `golden-hoop-spell` 过滤，
  对层级/扁平两种形态均不敏感，无需收紧；后续若 Codex 缓存布局再变，以本节记录为收紧依据。
- PASS — marker env 约定确认：`host_compat.py` 以任意 `CODEX_` 前缀 env 为 Codex marker
  （优先于 `CLAUDE_PLUGIN_ROOT` 判 host，防宿主兼容展开该变量导致误判）；本轮编写 shell 实测无
  `CODEX_*` 变量在环境（该 shell 属 Claude Code 会话，符合预期）。宿主会话内的真实注入集
  （NOT_EXECUTED，待 §2.1 安装后实测）。

### 2.4 Pi — 远程 git 源路线

```bash
pi install git:github.com/wangdahoo/golden-hoop-spell
```

git 源克隆到 `~/.pi/agent/git/`（全局；项目级加 `-l` 落 `.pi/`），无 manifest 时按约定目录自动发现
`skills/`（递归找 SKILL.md），有 `package.json` 时按 `pi` 键声明解析（本仓库为
`"skills": ["plugin/skills"]`、`"extensions": ["plugin/pi-extensions"]`）。克隆后 pi 会执行 `npm install`，
本仓库 `package.json` 零 `dependencies`，该步骤无害。

- NOT_EXECUTED — 安装类操作不在本轮授权范围（不改动 `~/.pi` 状态），留待人工执行轮。

### 2.5 Pi — 本地路径路线

```bash
pi install /path/to/golden-hoop-spell/plugin
```

本地路径为原位引用（不克隆）；项目级安装在任一命令后追加 `-l`（写入 `.pi/settings.json`）。

- NOT_EXECUTED — 同 2.4，安装类操作不在本轮范围。

### 2.6 Pi — 真实落点布局与 marker env 观测（只读，已执行）

- PASS — git 源落点布局实测（以已装的 pi-harness 为样本）：`~/.pi/agent/git/github.com/wangdahoo/pi-harness/`
  为仓库整体检出（`package.json`、`skills/`、`extensions/` 等在仓库根），与 `host_compat.py` 递归 glob
  覆盖 `~/.pi/agent` 下 `skills/` 与 `git/` 两种落点的设计一致；ghs 落点预期为
  `~/.pi/agent/git/github.com/wangdahoo/golden-hoop-spell/`（待 §2.4 实测确认）。
- PASS — `~/.pi/agent/skills/` 平铺技能目录在位（实测含 `frontend-design`、`python-patterns`、
  `python-testing` 三个独立技能目录），pi 技能发现机制运转正常的旁证。
- PASS — marker env 约定确认：`host_compat.py` 以 `{PI_SESSION_ID, PI_SESSION_FILE, PI_CODING_AGENT_DIR}`
  任一为 pi marker（pi 的 bash 工具向命令注入会话 env，官方文档核实）；本轮编写 shell 实测无 `PI_*`
  变量（同 §2.3，符合当前会话归属）。agent dir 缺省 `~/.pi/agent`（实测在位，含 `settings.json`，
  其 `lastChangelogVersion: 0.85.1` 与 CLI 版本一致）。
- NOT_EXECUTED — `pi.extensions` 指向的 `plugin/pi-extensions/` 目录落盘前（ask-user.ts 由后续任务落盘），
  pi 对缺失扩展目录的加载行为按计划留待本节实测记录；本轮未安装、未启动 pi 会话，无观测。

### 2.7 插件根探测脚本（公共腿，已执行）

- PASS — `command python3 plugin/shared/scripts/host_compat.py` → exit 0，单行 JSON 三键齐全：
  `{"host": "claude-code", "plugin_root": "...\\.claude\\plugins\\cache\\golden-hoop-spell\\golden-hoop-spell\\0.6.0", "resolution": "cache-glob"}`。
  本机 Claude 缓存真实布局 `<marketplace>/<plugin>/<version>/`（顶层恰含 `skills/` 与 `shared/`）命中递归 glob。
- PASS — `command python3 plugin/shared/scripts/validate_manifests.py` → exit 0，六项检查全 OK
  （codex 清单必填键与 kebab-case / 与 Claude 清单 name+version 严格相等 / skills 目录 7 个 SKILL.md /
  marketplace 单条目 source 解析 / package.json pi.skills 与 version / 可选 .agents 交叉核对）。

## 3. 七技能发现性检查

目标：两宿主安装后 7 个技能全部可发现、可调用（`ghs-init`、`ghs-plan`、`ghs-to-features`、`ghs-code`、
`ghs-status`、`ghs-archive`、`ghs-force-archive`）。技能名含冒号（`ghs:init` 等）不在 Agent Skills 名称
字符集内，pi 可能仅警告加载也可能拒载——本腿最先核实，拒载即记 FAIL 并上报契约修订。

- NOT_EXECUTED — Codex：需安装后在会话内经 `/plugins` 查看插件已装载、再以自然语言或 `@` 显式调用
  一个技能（如 @-mention `ghs-status`）验证可达。依赖 §2.1。
- NOT_EXECUTED — pi：需安装后在会话内执行 `/skill:ghs:status` 验证显式命令形态可达（技能 frontmatter
  均含 `disable-model-invocation: true`，不参与自动选择，显式命令仍可用）。依赖 §2.4。

## 4. ${CLAUDE_PLUGIN_ROOT} 探针（每宿主三结局）

技能正文命令引用 `${CLAUDE_PLUGIN_ROOT}`。判据三结局，全部功能可达：

1. **已展开** — 宿主兼容展开该变量，正文命令原样可用；
2. **未展开但自举** — 按 SKILL.md `## Platform Adaptation` 指针块自举：取所执行 SKILL.md 的祖父目录为
   插件根，`command python3 <plugin_root>/shared/scripts/host_compat.py`，以其单行 JSON 的
   `plugin_root` 为准；
3. **unknown → 询问用户** — `host_compat.py` exit 1 且
   `{"host": "unknown", "plugin_root": null, "resolution": "asked"}`（脚本自身不交互），此时询问用户
   插件根路径后继续。

无论何结局，主会话只解析一次插件根，派发前把 prompt 模板中 `${CLAUDE_PLUGIN_ROOT}` 字面替换，
子代理不见未解析变量（单点解析原则）。

- PASS — 结局 2 的自举权威已实测：`host_compat.py` CLI 运行输出见 §2.7（本机宿主为 claude-code /
  cache-glob；同一机制在 codex / pi 会话内复用，仅 marker 不同）。
- PASS — 结局 3 分支由单测覆盖：`test_host_compat_double_failure_unknown` 验证相关 env 清空且缓存无命中
  时输出 `unknown/null/asked` 且 CLI exit 1（本轮 166 项测试全绿，含此例）。
- NOT_EXECUTED — Codex 会话内结局判定（已展开 / 未展开）：需在 §2.1 安装后调用任一技能，观察正文
  `${CLAUDE_PLUGIN_ROOT}` 是否被展开；未展开则验证指针块自举链路（宿主任意文件读取工具读取
  `codex-host.md`）。依赖 §3 的 Codex 腿。
- NOT_EXECUTED — pi 会话内结局判定：pi 按官方文档不展开该变量，预期恒为结局 2；需在 §2.4 安装后经
  `/skill:ghs:<name>` 调用实测并记录。依赖 §3 的 pi 腿。

## 5. init（scratch 项目初始化跟踪）

在 §1 的 scratch 项目内初始化 ghs 跟踪（`.ghs/features.json` + `.ghs/progress.md`，`.gitignore` 含 `.ghs`）：

- NOT_EXECUTED — Codex：会话内以自然语言描述或 @-mention 调用 `ghs:init`。依赖 §2.1 + §3。
- NOT_EXECUTED — pi：会话内 `/skill:ghs:init`。依赖 §2.4 + §3。
- 参考判据（供执行轮复用）：`.ghs/features.json` 与 `.ghs/progress.md` 生成、
  `git check-ignore .ghs/features.json` 生效、`progress.md` 顶部新增会话条目。

## 6. plan 三角色流水线（每宿主）

在 scratch 项目内跑 `/ghs:plan` 全流程（Phase 1 上下文 → Phase 3 设计 → Phase 4 评审 → 定向修订 →
批准），验证三泳道派发、长输出文件交接、交互原语降级三件事。宿主差异按
`codex-host.md` / `pi-host.md` 覆盖正文；以下为各宿主必验清单。

### 6.1 Codex 腿

1. **先验 spawn_agent 主路径链路**（`multi_agent` 在位为前提，见 §0.1）：
   确认当轮工具表含 `spawn_agent` / `wait_agent` / `followup_task` / `list_agents` 四名 →
   plan 泳道 `{fork_turns: "none"}` 干净上下文派发（prompt 已字面替换根路径）→ `wait_agent`
   有界等待（`timeout_ms` 300000–600000，不短轮询）→ 完成答案经 mailbox 随下回合到达 →
   `list_agents` 对账 → 格式失败时 `followup_task` 续发同一代理承接 Format Recovery（不新开代理）→
   子代理写 `.tmp/<run-id>.plan.raw` 回传路径，`parse_delimited_output.py --kind plan --output-file`
   结果用宿主任意文件读取工具读取，完成判定只看 raw 解析结果。
2. **再走 explorer 探针决策程序**（context 泳道，程序不变）：写探针（explorer 写一行到
   `.ghs/explorer-write-probe.tmp`，记录 can write / cannot write）+ 保真观察（捕获响应定界符与正文
   完整，记录 faithful / summarized）→ 门槛判定：summarized 或 can write → 提请用户批准后升级为
   `default` + 文件交接附录；cannot write 且 faithful → 维持 explorer 默认。
3. **request_user_input 在位验证**（当轮工具表在列 + 交互式 stdin 终端前提；`codex exec` 等非交互模式
   不可用，仅 root 线程可问——ghs 只从 dispatcher 询问天然满足）。
4. **异步回执记录**：提问回合即返（调用不阻塞、当回合先返回）记一行；答复随下回合到达记一行；
   硬批准门未获答先重问一次，仍未获答落回文本提问并记录降级。

- NOT_EXECUTED — 步骤 1（主路径链路验证）：依赖 §0.1 的 `multi_agent` FAIL 修复 + §2.1 安装 + §3 发现。
- NOT_EXECUTED — 步骤 2（explorer 探针决策程序）：依赖步骤 1。
- NOT_EXECUTED — 步骤 3（request_user_input 三条件在位）：依赖步骤 1 的交互会话。
- NOT_EXECUTED — 步骤 4（异步回执两行记录）：依赖步骤 3。

### 6.2 Pi 腿

1. **`{action: "list"}` 在位验证**（pi-subagents 前置复核，见 §0.2）：roster 返回即工具在位；缺失时
   停止多子代理工作、显式报告缺失并给出安装命令，禁止内联伪装（单特性 code 不受影响）。
2. **单发 output 文件 verbatim 校验**：单泳道派发 `{agent: <映射名>, task: <prompt>,
   output: "<raw 绝对路径>", outputMode: "file-only"}`，核对落盘 raw 文件该泳道定界符对与完成信号行
   完整在场（以 `parse_delimited_output.py` 判 `status=ok` 为准），回执仅文件引用、不参与判定。
   角色映射 `general-purpose→delegate`、`Explore→scout`、`Plan→planner`，以 `{action: "list"}` 实际
   roster 为准，缺名退 `delegate` 并记录。
3. **双任务 `{tasks}` 并行验证**：一次调用携两个 task 条目（各带自己的 raw 路径）+ `concurrency: 2`，
   核对两份 raw 各自落盘、互不串写。
4. **ask_user 工具在位验证**：扩展加载后工具表含 `ask_user` 即在位；缺失（扩展未装/加载失败）时
   实测 pi-host.md 块 4 文本提问 fallback 生效并记录降级。ask_user 随插件 `pi.extensions` 自动注册，
   非安装前置。

- NOT_EXECUTED — 步骤 1（list 在位）：依赖 §0.2 的 pi-subagents FAIL 修复 + §2.4 安装 + §3 发现。
- NOT_EXECUTED — 步骤 2（output 文件 verbatim）：依赖步骤 1。
- NOT_EXECUTED — 步骤 3（双任务并行落 raw）：依赖步骤 2。
- NOT_EXECUTED — 步骤 4（ask_user 在位 / 文本 fallback 记录）：依赖步骤 1 的会话；且 ask-user.ts 尚未
  落盘（后续任务交付），当前预期即走文本 fallback 分支。

## 7. code 单特性（每宿主）

在 §6 产出的计划内选一个特性跑 `/ghs:code` 单特性模式（无子代理派发的泳道也覆盖：脚本链
`resolve_project_dir.py` → 实现提交 → Verification Phase parser → status 更新）。

- NOT_EXECUTED — Codex：会话内 @-mention 或自然语言调用 `ghs-code`。依赖 §6.1。
- NOT_EXECUTED — pi：会话内 `/skill:ghs:code`。依赖 §6.2。
- 参考判据：scratch 项目出现特性对应实现与 conventional 格式提交；`features.json` 中该特性 status
  翻转 `completed`；`progress.md` 新增会话日志。

## 8. code `--parallel` 双特性并行（每宿主）

### 8.1 最小 features.json 准备（两无依赖特性，已执行）

在 scratch 项目的 `.ghs/features.json` 写入最小双特性计划（两个 `pending` 特性、`dependencies` 均空、
`files_affected` 不重叠——重叠特性会被 `parallel_utils.py` 自动分入不同批次）：

```json
{
  "project": {"name": "scratch-e2e", "description": "E2E scratch project for multi-host verification",
               "tech_stack": [], "created_at": "2026-10-30"},
  "plans": [
    {
      "id": "p1",
      "name": "parallel smoke",
      "status": "in_progress",
      "created_at": "2026-10-30",
      "features": [
        {"id": "p1-feat-001", "title": "Add util_a.py",
         "description": "- create util_a.py with one function",
         "status": "pending", "dependencies": [], "files_affected": ["util_a.py"]},
        {"id": "p1-feat-002", "title": "Add util_b.py",
         "description": "- create util_b.py with one function",
         "status": "pending", "dependencies": [], "files_affected": ["util_b.py"]}
      ]
    }
  ],
  "metadata": {"version": "1.0.0", "last_updated": "2026-10-30"}
}
```

批次预检命令（与 SKILL.md 正文一致）：

```bash
command python3 <plugin_root>/shared/scripts/parallel_utils.py --project-dir "$SCRATCH" --plan-id p1 --max-parallel 2
```

- PASS — 本轮已实测：对上述最小 fixture 运行 `parallel_utils.py` → exit 0，`ready_features` 恰为两特性，
  `batches` 恰一个批次含两条目（可同批并行），`skipped`/`cycles`/`cycle_feature_ids` 均空。
- PASS — 测试套件回归：`command python3 -m unittest discover -s plugin/shared/scripts -p "test_*.py"`
  → 166 tests OK（本轮实测），含 `parallel_utils` 既有用例，批次语义未漂移。

### 8.2 并行执行腿（每宿主，未执行）

派发形态：每代理写 `<PROJECT_DIR>/.ghs/parallel/p1/<feature_id>.raw.attempt<N>`；`dispatch_start_iso`
前置门（spawn 时刻记录 ISO 时间戳，用于时间窗 git log 对账）与 `MAX_RETRY` 重试状态机不变；
完成判定只看 raw 文件解析结果。Codex 腿子代理类型 `default`；pi 腿 `{tasks, concurrency}` 一批派发、
子代理 `delegate`（以 roster 为准）。

- NOT_EXECUTED — Codex：`/ghs:code --parallel` 双特性并行执行。依赖 §6.1。
- NOT_EXECUTED — pi：同上。依赖 §6.2。
- 参考判据：两特性各自独立提交；两份 raw 各自落盘且均解析 `status=ok`；`features.json` 两特性均翻转
  `completed`；无文件交叉污染（`util_a.py` 只出现在 feat-001 的提交）。

## 9. status + archive（每宿主）

收尾腿：`/ghs:status` 展示进度，`/ghs:archive`（或 `/ghs:force-archive`）归档计划。

- NOT_EXECUTED — Codex：会话内调用 `ghs-status` / `ghs-archive`。依赖 §8。
- NOT_EXECUTED — pi：会话内 `/skill:ghs:status` / `/skill:ghs:archive`。依赖 §8。
- 参考判据：status 输出含项目行与特性计数；归档后计划状态翻转、归档产物入
  `docs/ghs/plans/`（或用户指定位置）。已知注记：`status.py` 在 GBK 控制台打印 emoji 会
  `UnicodeEncodeError`（2026-10-30 实证），修复已立项为 p1-feat-010——执行轮若在 GBK 终端遇到该崩溃，
  以 `PYTHONIOENCODING=utf-8` 临时绕过并确认 p1-feat-010 已合入。

## 10. Claude 回归腿（基线不受双宿主改动影响）

双宿主兼容层对 Claude 侧应零影响：Claude 清单与 `.claude-plugin/marketplace.json` 零改动、SKILL.md
既有行零删改（指针块 add-only）、既有 references 零改动。

```bash
claude --plugin-dir plugin
```

- NOT_EXECUTED — `claude --plugin-dir plugin` 冒烟一个技能（建议 `ghs:status`）：交互式宿主会话不在
  本轮范围。启动后任选一个技能完整跑一遍，确认指针块在 Claude 侧行为不变（"nothing to do"）。
- PASS — 仓库级回归已执行：`validate_manifests.py` 六项全 OK（§2.7）、测试套件 166 tests OK（§8.1）、
  `git diff --stat -- plugin/.claude-plugin/plugin.json .claude-plugin/marketplace.json` 输出为空
  （Claude 侧清单零改动，本轮实测）。

---

## 附：执行轮快速清单

按序补录 `NOT_EXECUTED` 项：§0.1 开 `multi_agent` → §0.2 装 pi-subagents（`pi install npm:pi-subagents`）
→ §2 四条安装路线 → §3 发现性 → §4 探针 → §5 init → §6 三角色（Codex 先主路径后探针；pi 先 list、
verbatim、并行、ask_user）→ §7 单特性 → §8 并行 → §9 收尾 → §10 Claude 冒烟。每步把对应记录行改写为
`PASS/FAIL` 并附输出摘录；安装命令若实测修正，回改 `README.md` / `README-zh.md` 对应章节保持逐字一致。
