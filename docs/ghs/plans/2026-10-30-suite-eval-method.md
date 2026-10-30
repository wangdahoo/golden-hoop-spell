# ghs 套件全流程执行质量评测方法

> SCOPE CONTRACT — frozen at kickoff. 由 dispatcher 维护并经用户确认；
> 正文不得扩大本契约范围，冲突时删正文不删契约。

## Intent
ghs 目前只有单脚本单元测试和人工 E2E 台账，无法回答两个问题：
流程是否被正确执行（合规），以及用 ghs 写代码是否真的更好（效果）。
建立两层评测方法：过程层只读审计固化验证底线；结果层用带隐藏验证的
基准案例真实驱动全流程并以通过率判分，A/B 对照不开 ghs 的基线，
用数据回答 ghs 的价值。

## Goals
- 产出 plugin/shared/scripts/eval_pipeline.py，两个子命令：
  - audit --project-dir <DIR>：对任意含 .ghs/ 的项目做只读四阶段审计
    （plan 终态/契约/review、features.json 结构与关联、feature 提交证据、
    归档完整性），输出 JSON 报告；退出码 0/1/2
  - bench --cases <DIR> [--baseline] [--case <NAME>]：逐案例在一次性目录中
    真实驱动 ghs 全流程（经宿主 CLI 非交互执行），跑完执行案例隐藏验证，
    输出逐案例 JSON：结果 pass/fail + 过程指标（复审轮数、reject 次数、
    blocked 数、物化重写次数）
- 基准案例语料格式（SWE-bench 风格）落地：每案例 = 任务简报 + fixture 项目
  + 隐藏验证脚本 + 期望产物清单，存于 evals/cases/<name>/
- A/B 对照：--baseline 时同案例不开 ghs 直接执行，报告输出 ghs 与基线
  的通过率对比
- 种子语料 >=3 个案例（至少含：带隐藏测试的缺陷修复、带验收判据的小功能）
- audit 模式零写入；新增单测 test_eval_pipeline.py（audit 逻辑全部覆盖，
  bench runner 覆盖案例解析与报告聚合），与既有测试全部通过
- 评测方法文档落地 evals/README.md（指标定义、案例编写规范、如何加案例）

## Non-Goals
- 不导入 SWE-bench/HumanEval 等现成数据集（风格借鉴，语料自带）
- 不做 LLM-as-judge 主观代码质量评审（隐藏测试是唯一结果判分）
- 不在本期实现全部三宿主的 bench 自动化（先支持 codex exec，
  宿主适配留 adapter 接缝）
- 不修改任何既有 ghs 脚本/skill 行为
- 不覆盖 light lane 全链路状态机审计（仅产物存在性核对）

## Anti-Goals
- 审计模式对被测项目产生任何写入 => 失败
- bench 案例无隐藏验证（结果不可判定）=> 案例本身无效
- 报告无法区分过程层与结果层、无法定位失败阶段与原因 => 失败
- 评测器需要第三方依赖 => 失败

## Decisions
- 评测分两层：audit 事后只读审计 + bench 真实驱动执行（用户方向性决策）
- bench 执行通道：宿主 CLI 非交互模式（当前环境 codex exec 优先）[DISCRETIONARY]
- 结果判分唯一标准是案例隐藏验证的通过/失败 [DISCRETIONARY]
- 过程指标直接读取 ghs 既有状态文件（不新增被测侧埋点）[DISCRETIONARY]

## Open Space
- 案例目录的具体文件命名与 fixture 工程模板
- 报告 JSON 的字段命名与聚合结构
- 基线（不开 ghs）的提示词措辞
- audit 与 bench 报告是否共用 schema

## Global Constraints
- Python 3 标准库 only，零第三方依赖
- Windows 兼容（路径、UTF-8 无 BOM、进程调用）
- 沿用仓库现有脚本风格（argparse、退出码约定）
- 新文件位置：脚本 plugin/shared/scripts/，语料与文档 evals/

## Current State

- 项目已有稳定的状态文件、任务物化、features 状态、parallel 证据、归档副产物与 166 个脚本测试；快照给出可机读字段、CLI 约定和已知缺口。
- 现有自动化只覆盖脚本单元，`archive_plans.py` 没有稳定 JSON，单模式代码也没有持久 completion 证据；流程合规和效果评测需要新的只读聚合器与真实执行器。
- 本计划只新增评测层，不修改既有 ghs 脚本和 skill；audit 可直接消费既有产物，bench 必须把真实代理运行限制在一次性目录内。

## Design

### Overall Approach

- 新增单一标准库脚本 `plugin/shared/scripts/eval_pipeline.py`，内部分成 audit engine、case loader、host adapter、bench runner 和 report aggregator；CLI 只做参数解析、UTF-8 输出和退出码映射。
- 新增 `plugin/shared/scripts/test_eval_pipeline.py` 用临时项目与 fake host 覆盖纯逻辑，不要求测试环境安装 Codex。
- 评测文档和种子语料放在 `evals/`；案例源目录在 bench 中只读，所有代理写入都发生在 `tempfile` 建出的一次性工作副本。

### Interface Design

```bash
python plugin/shared/scripts/eval_pipeline.py audit --project-dir <DIR>
python plugin/shared/scripts/eval_pipeline.py bench --cases <DIR> \
  [--baseline] [--case <NAME>] [--clean-env] [--codex-bin <CODEX>] \
  [--plugin-root <DIR>] [--timeout-seconds <N>]
```

- `audit` 输出一个 JSON 对象并使用退出码 0/1/2：0 是无 error，1 是任一 stage error，2 是参数或 IO 错误。
- `bench` 输出一个聚合 JSON 对象；未选择案例、案例根目录不可读等参数/IO 错误退出 2，选中案例任一 arm 判 fail 或案例无效退出 1，全部 pass 退出 0。
- Python 层接口固定为：

```python
def run_audit(project_dir: Path) -> dict: ...
def load_cases(cases_dir: Path, selected: set[str] | None) -> tuple[list[Case], list[CaseError]]: ...
def run_bench(cases_dir: Path, selected: set[str] | None, baseline: bool,
              adapter: HostAdapter, plugin_root: Path,
              timeout_seconds: int, clean_env: bool = False) -> dict: ...
def verify_workdir(case: Case, workdir: Path) -> VerifyOutcome: ...
```

- `HostAdapter` 是抽象接缝：`name: str` 加 `run(workdir: Path, prompt: str, timeout_seconds: int, *, arm: str) -> HostRun`；`arm` 只能是 `"ghs"` 或 `"baseline"`，供同一 adapter 区分两臂环境分支。
- `CodexExecAdapter(codex_bin: str, plugin_root: Path, clean_env: bool = False)` 是本期唯一内置 adapter；后续宿主只替换 adapter，不改 case 和 verifier 协议。`clean_env` 不改变默认 ambient 行为，只在 baseline arm 生效。

### Audit

- audit 报告顶层字段为 `schema_version: 1`、`kind: "ghs-eval-audit"`、`project_dir`、`passed`、`zero_write_verified`、`summary` 和 `stages`；四个 stage id 固定为 `plan`、`features`、`commits`、`archive`。
- 每个 check 记录 `id`、`severity: "error"|"warning"`、`passed`、`message`，以及可用的 `plan_id` 或 `feature_id`；报告必须能定位失败 stage、plan/feature 和原因。
- plan stage 从 `.ghs/plans/*-status.json` 与归档 tracker 的 `archived_plan` 汇总候选；full lane 的终态接受 `approved`、`aborted` 或 archived `completed`。非终态 status、缺失/错误 contract 标题、缺失 review、review 信号不是 PASS 且 `accepted_with_fail != true` 都报 error。
- review 检查解析完整 completion signal 中的 `Verdict`、`Unwarranted`、`Severe`、`Medium`；PASS 必须前三类计数为 0。`accepted_with_fail: true` 且 review 产物存在时降为 warning，用于暴露用户显式接受的残留。
- light lane 只做产物存在性核对：终态、contract 标题、一个 `### Task 1:` 卡和 `- Anchors:` 存在；不重建 light 状态机。
- features stage 按 `validate_structure.py` 已记录的结构规则做等价只读检查，另检查 feature ID 全局唯一、数字前缀与 plan 匹配、dependency 可解析、`plan_ref` 存在且指向实际文件。
- commits stage 先确认目标在 git work tree 内；active 与 archived tracker 中每个 completed feature 都必须有 commit message 含 `(Feature: <id>)` 的提交。`files_affected` 非空时，该提交还必须触碰至少一个声明文件；pending/in_progress/blocked 不检查 commit。所有 git 调用都在子进程环境中设 `GIT_OPTIONAL_LOCKS=0`，且只允许 `rev-parse --show-toplevel`、`log --format=...`、`diff-tree --no-commit-id --name-only -r <commit>` 这类历史/对象只读查询；禁止 `status`、`add`、`checkout`、`config` 和其他可能刷新或重建 index 的调用。
- archive stage 检查每个 archived tracker 的 `archived_plan.status == completed`、全部 feature completed、活动 tracker 不再含同 ID plan，并在 `.ghs/plans` 或 `docs/ghs/plans` 找到 plan 文档。active tracker 中已完成但尚未归档的计划报 warning，不算 archive error。
- audit 进入前后对项目内 `.ghs`、`docs/ghs/plans` 的 regular files 做 path、size、`st_mtime_ns` 快照并比较；差异时 `zero_write_verified: false` 并退出 2。`.git` 元数据不在快照边界内，但仍受零写入要求约束：audit 只使用上述非变更 git 查询，不刷新 index、不写对象、不改 refs 或 config。audit 自身也不创建目录、不写被测项目文件。
- 输出使用 `ensure_ascii=False` 的 UTF-8 JSON，并在 Windows 控制台先应用与既有脚本一致的 UTF-8 stdio guard。

### Bench Case Format

每个案例必须是下列固定文件集；缺任一必需文件、JSON 无效、`name != directory name` 或路径不安全都判 case 无效：

```text
evals/cases/<name>/
  case.json
  brief.md
  fixture/
  verify.py
  expected_artifacts.json
```

- `case.json` 必须是 `{"schema_version":1,"name":"<safe-name>","title":"<non-empty>","verify_timeout_seconds":120}`；最后一个键可选且必须为正整数。`name` 限定 `[A-Za-z0-9][A-Za-z0-9_-]*`。
- `brief.md` 是给代理的完整任务简报，不暴露 verify.py 内容。
- `fixture/` 是初始项目；`verify.py` 是唯一结果 oracle，必须能用 Python 标准库执行；`expected_artifacts.json` 只记录声明式产物门。
- 产物清单格式为 `{"schema_version":1,"artifacts":[{"path":"repo/relative/path","sha256":null}]}`；`sha256` 可选为 64 位小写十六进制。path 使用 POSIX 相对路径，禁止绝对路径、空路径、`..` 和盘符。
- runner 用 `python verify.py <workdir>` 调用 verifier，`cwd=workdir`，exit 0 才通过；捕获 stdout/stderr 尾部用于报告定位。

### Bench Flow

- 默认只跑 ghs arm；`--baseline` 在同一调用中对每个选中案例额外建立独立一次性目录并跑 baseline arm，以获得成对 A/B 对比。
- 每个案例先复制 fixture 到独立 temp directory，再执行 `git init -b main`、设置本地 `user.name/user.email` 并创建 baseline fixture commit；这是 ghs code 提交证据所需的最小初始化。
- ghs prompt 要求代理使用 prompt 中给出的绝对 plugin root、先非交互执行 `/ghs:init`，确认一次性目录已建立 `.ghs/features.json` 与 `.ghs/progress.md` 后再从 `/ghs:plan` 完成契约/评审/批准、执行 `/ghs:code` 直到 feature completed、最后执行 `/ghs:archive`；同时声明用户预授权一次通过、不得访问 eval corpus 或 verifier。runner 不在被测 case fixture 源中预置 `.ghs/`。baseline prompt 禁止使用 ghs、读取或创建 `.ghs`，只包含同一 `brief.md`，不声称 fixture 自带可通过的自动化验证；隐藏验证在 host 退出后由评测器执行。
- 默认不加 `--clean-env` 时采用 ambient-constant：两臂都继承同一当前宿主环境，用户本地的其他 skills/plugins/hooks 在两臂同样在场；`CODEX_*` 等环境变量按现设计透传，`PLUGIN_ROOT` 与 `CLAUDE_PLUGIN_ROOT` 也两臂同注入。baseline 只靠 prompt 禁止调用 ghs、读取或创建 `.ghs`；此模式测量 ghs 在真实环境中的边际增益。
- 加 `--clean-env` 时 ghs arm 仍使用正常宿主环境以加载 ghs 插件；baseline arm 在该 arm 的进程启动前获得全新临时 `CODEX_HOME`，其中只创建 UTF-8 无 BOM 的最小默认 `config.toml`，不复制或发现用户级 skills/plugins/hooks/prompts/history。该 baseline 进程不继承原 `CODEX_HOME` 的值，也不注入 `PLUGIN_ROOT` 或 `CLAUDE_PLUGIN_ROOT`；其他宿主运行所需环境按 adapter 需要保留。`--clean-env` 不带 `--baseline` 时没有可观测的 baseline 效果。两臂环境差异是设计意图，必须在报告与文档中显式声明。
- `CodexExecAdapter.run` 调用 `codex exec --cd <workdir> --sandbox workspace-write <prompt>`，默认 `--codex-bin codex`、`--timeout-seconds 3600`；ambient 模式环境保留宿主原有 `CODEX_*` 标记，并把 `PLUGIN_ROOT` 与 `CLAUDE_PLUGIN_ROOT` 指向选定的 plugin root，另设 `PYTHONIOENCODING=utf-8`。clean baseline 的隔离 `CODEX_HOME` 在该 arm 进程退出后删除。
- host 返回非零、超时或无法启动时记录 `failure_stage: "host"`、argv、exit code、timed out、时长和输出尾部；隐藏验证仍执行一次，便于区分“代理失败”和“初始 fixture 已失败”。
- host 停止后先核对 expected artifacts，再运行 hidden verifier。只有产物门和隐藏验证全通过，该 arm 的 `result` 才是 `pass`；不使用 LLM 评审或人工代码质量判断。
- process metrics 只读 ghs 既有状态：`review_rounds` 是所有 plan status JSON 的 `retry_counts.review` 总和，`rejects` 是 `reject_count` 总和，`blocked_count` 是 active 与 archived features 中 `blocked` 数量。`materialization_rewrites` 按 plan 归组计算：解析每个 active/archive progress 的 plan session，先计数 `**Agent**: Plan Materializer` block，再取 `max(0, materializer_blocks - 1)`，最后跨 plan 求和；因此一次初始物化计 0，后续每次物化修订各计 1。baseline 的 metrics 为 `null`。
- 聚合报告字段为 `schema_version`、`kind: "ghs-eval-bench"`、`cases_dir`、`mode: "ghs"|"ab"`、`baseline_env: "ambient"|"clean"`、`summary`、`cases`。顶层 summary 分别输出 ghs 与可选 baseline 的 `total`、`passed`、`pass_rate`，baseline 存在时输出 `comparison` 与 ghs-baseline `pass_rate_delta`。
- 每个 case JSON 包含 `name`、`case_valid`、`baseline_env: "ambient"|"clean"`、`result`、`failure_stages`、`metrics`（`layer: "process"`）、`verification`（`layer: "outcome"`）和每个已执行 arm 的 host/verify 详情；arm 详情也标注 `environment`。无效案例不启动 host，`result: "fail"`、`case_valid: false`、`failure_stages: ["case_validation"]`，但仍记录请求的 baseline 模式。
- 输出 JSON 用 UTF-8 无 BOM 写到 stdout；host 与 verifier 原始输出只保留尾部，默认最多 4000 characters each，避免报告被代理日志淹没。

### Seed Corpus

- `divide-by-zero-guard` 是带隐藏测试的缺陷修复：修复 `calc.divide` 的商行为，非零除数返回向零截断的整数商，零除数抛 `ValueError`；隐藏 verifier 用标准库动态导入并覆盖正负数与零除数。
- `case-insensitive-user-lookup` 是小功能：新增 `find_user(users, email)`，按 case-insensitive exact email 返回第一个匹配 dict，找不到返回 None 且不得修改输入；hidden verifier 覆盖大小写、顺序和无匹配。
- `word-count-cli` 是小功能：`python word_count.py PATH` 读取 UTF-8 文本并只输出 whitespace token 数，空文件输出 0；hidden verifier 生成临时文本并捕获 stdout。
- 三个案例的 fixture 初始状态都让 hidden verifier 失败，`expected_artifacts.json` 分别声明 `calc.py`、`users.py`、`word_count.py`。

### Documentation

- `evals/README.md` 固化案例目录契约、JSON 字段、verifier 退出协议、添加案例步骤、无效案例条件、四个过程指标定义、结果判分规则、audit/bench 命令和 A/B 报告读法。
- 文档明确 baseline 的准确含义：同一 brief、同一 fixture 和隐藏验证，仅移除 ghs 流程授权；baseline prompt 不声称 fixture 自带可通过的自动化验证，隐藏验证由评测器在 host 退出后执行；baseline 不产生 process metrics。
- 文档定义两种 baseline 模式：默认 ambient baseline 表示两臂共享同一宿主环境，本地其他 skills/plugins/hooks 和环境变量都保持恒定，适合回答“在我当前机器配置上 ghs 的边际增益”，但结论不得表述成裸 CLI；`--clean-env` 表示 clean baseline 的临时 `CODEX_HOME` 只含最小默认 config，baseline 不加载用户级 skills/plugins/hooks，也不接收 plugin-root 注入，更接近裸 CLI，适合隔离本地环境噪声。clean 模式下 ghs arm 仍使用正常环境，这是有意的不对称；解读时必须以 `baseline_env` 分组，不得把 ambient 与 clean 报告直接混合比较，也不得用单案例差异断言总体优势。

## Assumptions

- [ASSUMPTION] `--baseline` 表示同一调用额外执行 baseline arm，而不是替换 ghs arm — 只有同调用成对执行才能直接产出通过率对比。
- [ASSUMPTION] bench 的案例失败返回 1，参数/IO 失败返回 2，沿用既有脚本退出码习惯；契约只为 audit 显式列出三档。
- [ASSUMPTION] Codex CLI 已在 PATH 中且支持 `exec --cd` 与 `workspace-write`；本期只承诺该可替换 adapter，不承诺其他宿主。
- [ASSUMPTION] 一次性 fixture 项目由 bench runner 初始化为最小 git repo — ghs code 与 audit 的提交证据都以 git 为前提。

## Risks

- Codex exec 可能在非交互流程中等待确认：prompt 内置一次性预授权声明、3600 秒硬超时和完整 host tail 定位；超时不重试。
- progress 的 materialization 记录是 Markdown 而非数据库：metrics parser 只按 `## Session` block 和固定 `**Agent**` 行计数，结果只作过程证据，不参与 hidden-test 判分。
- 宿主可能解析到旧插件缓存：adapter 显式注入 `PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT`，prompt 也重复绝对 plugin root。
- Windows 编码或路径差异破坏命令：统一 UTF-8 stdio/env、POSIX case paths、`Path` 映射和 `subprocess` list argv。

### Task 1: Implement read-only audit engine

- Files: plugin/shared/scripts/eval_pipeline.py, plugin/shared/scripts/test_eval_pipeline.py
- Interfaces:
  - `python plugin/shared/scripts/eval_pipeline.py audit --project-dir <DIR>`
  - `def run_audit(project_dir: Path) -> dict`
- Points:
  - 实现 audit CLI、UTF-8 stdio guard、四 stage 报告 schema 和 0/1/2 退出码。
  - 实现 plan 终态、contract/review、light artifact、features 结构与关联检查。
  - 实现 git feature commit、archived tracker 完整性、warning 与 error 分层。
  - 实现 audit 前后只读快照和零写入标记，不创建被测项目文件。
- Anchors:
  - test_audit_valid_full_lifecycle_reports_no_errors: approved plan plus PASS review plus valid linked committed features yields zero errors and exit 0
  - test_audit_plan_contract_review_failures_are_located: missing review and bad contract or nonterminal status produce plan stage errors with plan IDs
  - test_audit_feature_commit_and_archive_evidence: bad dependency and uncommitted completed feature or incomplete archive produce the correct stage errors
  - test_audit_light_lane_and_zero_write: light plan checks artifact presence only and audit-visible state paths remain unchanged
  - python -m unittest plugin.shared.scripts.test_eval_pipeline -v: all audit tests pass

### Task 2: Implement benchmark case loading and hidden verification

- Files: plugin/shared/scripts/eval_pipeline.py, plugin/shared/scripts/test_eval_pipeline.py
- Interfaces:
  - `def load_cases(cases_dir: Path, selected: set[str] | None) -> tuple[list[Case], list[CaseError]]`
  - `def verify_workdir(case: Case, workdir: Path) -> VerifyOutcome`
- Points:
  - 实现 case 目录发现、固定 schema 校验、`--case` 去重过滤和确定性排序。
  - 实现 expected artifact path safety、存在性与可选 SHA-256 核对。
  - 实现标准库 verifier 子进程调用、timeout、exit code 与 output tail 捕获。
- Anchors:
  - test_load_cases_parses_valid_case_and_fixture: valid directory becomes Case with safe artifact list and deterministic order
  - test_case_without_hidden_verify_is_invalid: missing verify.py or expected_artifacts.json yields case_valid false without launching a host
  - test_expected_artifact_paths_are_rejected_when_unsafe: absolute path and parent traversal are case validation errors
  - test_verify_case_reports_pass_and_failure_tails: verifier exit 0 passes and nonzero failure preserves captured output tail
  - python -m unittest plugin.shared.scripts.test_eval_pipeline -v: all case loader tests pass

### Task 3: Implement benchmark runner and A/B aggregation

- Files: plugin/shared/scripts/eval_pipeline.py, plugin/shared/scripts/test_eval_pipeline.py
- Interfaces:
  - `def run_bench(cases_dir: Path, selected: set[str] | None, baseline: bool, adapter: HostAdapter, plugin_root: Path, timeout_seconds: int, clean_env: bool = False) -> dict`
  - `class HostAdapter` with `run(workdir: Path, prompt: str, timeout_seconds: int, *, arm: str) -> HostRun`
  - `class CodexExecAdapter(codex_bin: str, plugin_root: Path, clean_env: bool = False)`
- Points:
  - 实现一次性 fixture copy、最小 git init/commit、隔离执行和 finally 清理；不向 case 源目录复制或写入 `.ghs/`。
  - 实现 ghs 与 baseline prompt 模板，其中 ghs 模板显式要求先 `/ghs:init` 再 `/ghs:plan`；实现 Codex argv、plugin root 环境注入和 timeout 进程终止。
  - 实现 `--clean-env` 透传分支：默认把 ambient 环境与 plugin-root 注入用于两臂并在报告记录 `baseline_env: "ambient"`；开启后 ghs arm 仍用正常环境，baseline arm 由 adapter 建立全新临时 `CODEX_HOME` 与最小默认 config，改写原 `CODEX_HOME` 并取消 plugin-root 注入，arm 结束后清理隔离目录，报告记录 `baseline_env: "clean"`。
  - 实现四个 process metrics 的既有状态文件解析；materialization 按 plan 分组执行 `max(0, blocks - 1)`，baseline metrics 置 null。
  - 实现逐案例 pass/fail、failure stage、pass rate、A/B delta 和 UTF-8 JSON 输出。
  - 实现选中案例失败或无效时 bench exit 1，参数/IO 失败 exit 2。
- Anchors:
  - test_bench_runner_aggregates_ghs_and_baseline: fake adapter observes ghs prompt requiring init before plan, receives arm and clean-env pass-through, runs isolated copies, records baseline_env, and aggregate pass rates plus delta are exact
  - test_bench_process_metrics_extract_ghs_state: synthetic state with review rounds 2 rejects 1 blocked 1 and three materializer blocks reports 2 1 1 and exactly 2 rewrites
  - test_bench_reports_host_and_verify_failures: nonzero host and failing verifier produce distinct failure stages without crashing
  - test_codex_adapter_environment_modes: ambient mode monkeypatches subprocess with codex exec argv, workdir, timeout, and identical plugin-root environment for ghs and ambient baseline arms, while clean-env baseline receives a fresh CODEX_HOME containing minimal default config without the original CODEX_HOME value or plugin-root variables and the ghs run keeps its normal environment
  - python -m unittest plugin.shared.scripts.test_eval_pipeline -v: all bench runner tests pass

### Task 4: Add seed corpus and evaluator documentation

- Files: evals/README.md, evals/cases/divide-by-zero-guard/case.json, evals/cases/divide-by-zero-guard/brief.md, evals/cases/divide-by-zero-guard/expected_artifacts.json, evals/cases/divide-by-zero-guard/verify.py, evals/cases/divide-by-zero-guard/fixture/calc.py, evals/cases/case-insensitive-user-lookup/case.json, evals/cases/case-insensitive-user-lookup/brief.md, evals/cases/case-insensitive-user-lookup/expected_artifacts.json, evals/cases/case-insensitive-user-lookup/verify.py, evals/cases/case-insensitive-user-lookup/fixture/users.py, evals/cases/word-count-cli/case.json, evals/cases/word-count-cli/brief.md, evals/cases/word-count-cli/expected_artifacts.json, evals/cases/word-count-cli/verify.py, evals/cases/word-count-cli/fixture/word_count.py, plugin/shared/scripts/test_eval_pipeline.py
- Interfaces:
  - `python plugin/shared/scripts/eval_pipeline.py audit --project-dir <DIR>`
  - `python plugin/shared/scripts/eval_pipeline.py bench --cases evals/cases [--baseline]`
- Points:
  - 落地三个 UTF-8 无 BOM 案例，fixture 初始状态必须使 hidden verifier 失败。
  - 落地案例编写规范、指标定义、A/B 解释、添加案例步骤和无效案例清单。
  - 增加 corpus 级测试验证三个案例可解析且 fixture 与标准参考实现分别 fail/pass。
- Anchors:
  - test_seed_cases_are_valid: load_cases discovers three valid cases in deterministic order
  - test_seed_hidden_verifiers_separate_fixture_and_reference: each initial fixture fails its verifier and the documented reference behavior passes
  - test_readme_documents_metrics_and_case_rules: README contains case schema metric definitions hidden verification rule and add-case workflow
  - python -m unittest discover -s plugin/shared/scripts -p "test_*.py": all existing and new tests pass
  - python plugin/shared/scripts/validate_manifests.py: manifest validation exits 0
