# 修复 Pyenv 路径硬编码（Round 3 修订版 — Scope 缩减）

## 修订日志

| Round | 修订内容 |
|-------|----------|
| 1     | 初稿（sprint 自动推进 + pyenv 路径） |
| 2     | 修订：解决 Severe #1+#2、Medium #1-#8（针对 sprint 自动推进部分） |
| 3     | **Scope 缩减**：根据用户反馈，"Sprint status 不会自动推进" 不是真实问题（LLM 在实际使用中会自行推进 sprint status）。删除所有 sprint 自动推进相关内容（helper script、SKILL.md 接入、validate_structure warning、单元测试），仅保留 pyenv 路径硬编码修复。重命名 plan 标题。 |

---

## 1. Background and Goals

### 1.1 Background
回归测试发现 1 个真实问题：

**Pyenv 路径硬编码**：3 处 `SKILL.md` 用 `~/.pyenv/shims/python3` 调用 validator / parallel_utils。当用户 shell 没初始化 pyenv（`_lazy_pyenv` 未定义，或者压根没装 pyenv）时这条路径不存在，命令直接失败。所有脚本 shebang 已是 `#!/usr/bin/env python3`，只要 `PATH` 里有 `python3` 就能跑，硬编码 pyenv shim 多余且不兼容。

### 1.2 Goals
- **G1**：移除所有 `~/.pyenv/shims/python3` 硬编码引用（仅限 `plugin/` 下活动文档），统一改为 `python3`。

### 1.3 Scope
**In scope**：
- 修改 3 处 SKILL.md 的 pyenv 路径（ghs-code 两处、ghs-sprint 一处）

**Out of scope**：
- `docs/ghs/plans/*.md` 历史归档文档（按之前 plan §4 Step 4.3 决策，时间戳档案不改）
- Sprint 自动推进相关任何改动（**Round 3 决策**：经用户确认，LLM 在实际使用中会自行把 sprint status 从 `in_progress` 推进到 `completed`，原回归测试结论是基于隔离测试场景的误判，不是真实 bug）

---

## 2. Current State Analysis

### 2.1 pyenv 硬编码位置（grep 验证）
共 3 处，全部在 `plugin/skills/*/SKILL.md`：

| 文件 | 行号 | 当前内容 |
|------|------|----------|
| `plugin/skills/ghs-code/SKILL.md` | 33 | `~/.pyenv/shims/python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/validate_structure.py --project-dir "<PROJECT_DIR>"` |
| `plugin/skills/ghs-code/SKILL.md` | 136 | `~/.pyenv/shims/python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parallel_utils.py --project-dir "<PROJECT_DIR>" --max-parallel <N>` |
| `plugin/skills/ghs-sprint/SKILL.md` | 98 | `~/.pyenv/shims/python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/validate_structure.py --project-dir "<PROJECT_DIR>"` |

### 2.2 已使用通用 `python3` 的位置（无需修改）
- `plugin/skills/ghs-sprint/SKILL.md` line 11：`python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py`
- `plugin/shared/references/sprint-agent.md`：用 `python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_sprint.py`
- 所有 `plugin/shared/scripts/*.py` 的 shebang：`#!/usr/bin/env python3`

### 2.3 约束
- 所有 Python 脚本必须保持 `#!/usr/bin/env python3`，避免反向引入新硬编码

---

## 3. Plan Design

### 3.1 替换策略
统一把 `~/.pyenv/shims/python3` 替换为 `python3`。理由：
- 所有 Python 脚本 shebang 已是 `#!/usr/bin/env python3`，只要 `PATH` 里有 `python3` 就能跑
- `python3` 是 POSIX 习惯命名，覆盖 system python、homebrew python、pyenv、asdf、conda 等所有主流 Python 安装方式
- 不需要在 SKILL.md 里写复杂的环境检测逻辑

### 3.2 验证策略
1. **静态验证**：替换后跑 `grep -rn "pyenv" plugin/` 确认 `plugin/` 下 0 匹配
2. **运行验证**：用 `PATH=/usr/bin:/bin command -v python3` 模拟不依赖 pyenv shim 的最小环境，确认 validator 能跑通
3. **行为不变**：所有 SKILL.md 调用的脚本接口不变，feature 工作流不受影响

---

## 4. Implementation Steps

### Phase 1：替换 3 处 pyenv 路径

- [ ] **Step 1.1**：修改 `plugin/skills/ghs-code/SKILL.md` 第 33 行：
  - `~/.pyenv/shims/python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/validate_structure.py --project-dir "<PROJECT_DIR>"`
  - → `python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/validate_structure.py --project-dir "<PROJECT_DIR>"`

- [ ] **Step 1.2**：修改 `plugin/skills/ghs-code/SKILL.md` 第 136 行：
  - `~/.pyenv/shims/python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parallel_utils.py --project-dir "<PROJECT_DIR>" --max-parallel <N>`
  - → `python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parallel_utils.py --project-dir "<PROJECT_DIR>" --max-parallel <N>`

- [ ] **Step 1.3**：修改 `plugin/skills/ghs-sprint/SKILL.md` 第 98 行：
  - `~/.pyenv/shims/python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/validate_structure.py --project-dir "<PROJECT_DIR>"`
  - → `python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/validate_structure.py --project-dir "<PROJECT_DIR>"`

- **Acceptance criteria**：
  - 3 处 `~/.pyenv/shims/python3` 全部改为 `python3`
  - `git diff` 显示仅这 3 行修改
  - 工作树干净

### Phase 2：验证

- [ ] **Step 2.1**：静态验证 — 全仓库 grep：
  ```bash
  grep -rn "pyenv" plugin/
  ```
  期望：无输出（plugin/ 下 0 匹配）

- [ ] **Step 2.2**：文档验证 — 确认 `docs/ghs/plans/` 下的历史 plan 仍有 pyenv 引用（按 Out of scope 决策不改）：
  ```bash
  grep -rln "pyenv" docs/ghs/plans/ | head -5
  ```
  期望：列出若干历史 plan 文件（这些是时间戳档案，不改）

- [ ] **Step 2.3**：运行验证 — 模拟不依赖 pyenv 的最小 PATH 跑 validator：
  ```bash
  PATH=/usr/bin:/bin command -v python3 && \
    PATH=/usr/bin:/bin python3 plugin/shared/scripts/validate_structure.py \
      --project-dir /Users/tom/github/golden-hoop-spell
  ```
  期望：
  - `command -v python3` 输出 `/usr/bin/python3` 或 `/usr/local/bin/python3`（不依赖 pyenv shim）
  - validator 正常输出 `✅ Validation passed!`

- [ ] **Step 2.4**：SKILL.md 行为验证（可选手动验收）：
  - 触发一次 `/ghs:code` 或 `/ghs:sprint` 流程
  - 观察 validator 调用是否成功（不再报 `command not found: _lazy_pyenv`）

- **Acceptance criteria**：
  - Phase 2.1 grep 无输出
  - Phase 2.2 列出历史 plan（不改）
  - Phase 2.3 validator 输出 `✅ Validation passed!`

### Phase 3：提交

- [ ] **Step 3.1**：commit（HEREDOC 格式）：
  ```bash
  git add plugin/skills/ghs-code/SKILL.md plugin/skills/ghs-sprint/SKILL.md
  git commit -m "$(cat <<'EOF'
  fix(skills): 把 pyenv shim 硬编码替换为通用 python3 (Feature: TBD)

  3 处 SKILL.md 用 ~/.pyenv/shims/python3 调用 validator 和 parallel_utils，
  在用户 shell 没初始化 pyenv 时（_lazy_pyenv 未定义，或没装 pyenv）会失败。
  所有 Python 脚本 shebang 已是 #!/usr/bin/env python3，统一用 python3 让
  PATH 决定解释器，覆盖 system/homebrew/pyenv/asdf/conda 等所有安装方式。

  - plugin/skills/ghs-code/SKILL.md:33 validate_structure.py 调用
  - plugin/skills/ghs-code/SKILL.md:136 parallel_utils.py 调用
  - plugin/skills/ghs-sprint/SKILL.md:98 validate_structure.py 调用

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## 5. Risks and Mitigations

| Risk | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 用户系统 PATH 里没有 `python3`（极旧 macOS 或精简 Linux） | 极低 | 中 | 用户需自行保证 PATH 含 python3（Python 3 是 Claude Code 运行前提之一，用户必然已装） |
| 替换后破坏现有依赖 pyenv 的用户工作流 | 极低 | 低 | pyenv 用户 PATH 里也有 `python3`（pyenv 会 shim 它），所以从 `~/.pyenv/shims/python3` 改为 `python3` 对 pyenv 用户透明 |
| `git diff` 包含意外改动 | 低 | 低 | Phase 1 显式列 3 行；commit 前 `git diff --stat` 应只显示 2 个文件、3 行 |

---

## 6. Testing Strategy

### 6.1 静态检查
- `grep -rn "pyenv" plugin/` 无输出

### 6.2 运行检查
- `PATH=/usr/bin:/bin python3 plugin/shared/scripts/validate_structure.py` 成功执行

### 6.3 文档完整性
- 历史 plan `docs/ghs/plans/*.md` 保留 pyenv 引用（按 Out of scope 决策）

### 6.4 不需要的测试
- ~~单元测试~~（无新代码）
- ~~回归测试脚本~~（无功能变更，仅环境适配）
- ~~端到端 workflow 验证~~（行为完全不变）

---

## 7. 决策摘要

| 维度 | 决策 |
|------|------|
| **修改范围** | 仅 `plugin/skills/ghs-code/SKILL.md`（2 处）和 `plugin/skills/ghs-sprint/SKILL.md`（1 处），共 3 行 |
| **替换策略** | `~/.pyenv/shims/python3` → `python3`（让 PATH 决定） |
| **历史文档** | `docs/ghs/plans/*.md` 不改（时间戳档案） |
| **Python 脚本** | 不改（shebang 已正确） |
| **测试** | 静态 grep + 运行 validator 即可 |

---

## 8. Round 3 修订说明（用户反馈处理）

用户反馈（2026-06-15）：
> 1. ghs 套件在使用过程中，llm 会自行把 in_progress 推进到 completed，所以并不存在 "Sprint status 不会自动推进" 这个问题
> 2. 方案仅保留 Pyenv 路径硬编码问题的修复

处理：
- 删除 Round 2 方案中所有 sprint 自动推进相关内容：
  - Phase 1（新增 helper）→ 删除
  - Phase 3（ghs-code End of Session 接入 helper）→ 删除
  - Phase 4（ghs-sprint 自愈接入）→ 删除
  - Phase 5（ghs-archive 自愈接入）→ 删除
  - Phase 6（validate_structure.py warning）→ 删除
  - Phase 7（单元测试）→ 删除
  - Phase 8（coding-agent.md 更新）→ 删除
- 保留 Round 2 方案中 pyenv 相关：
  - 原 Phase 2（pyenv 路径替换）→ 升级为新 Phase 1
  - 原 §6.3 pyenv 验证 → 升级为新 Phase 2
- Plan 标题从 "修复 Sprint 自动完成 + Pyenv 路径兼容性" 改为 "修复 Pyenv 路径硬编码"
- 评审轮次从 `max_rounds=2` 突破为 Round 3（用户明确反馈优先于流程限制）
