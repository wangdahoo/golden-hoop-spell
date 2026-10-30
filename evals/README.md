# ghs 评测语料与方法

本目录存放 `eval_pipeline.py bench` 的基准语料和使用说明。评测只做两类判断：过程合规由 `audit` 的只读检查报告，结果质量只由每个案例的隐藏验证脚本判定。

## 命令

```bash
command python3 plugin/shared/scripts/eval_pipeline.py audit --project-dir <DIR>
command python3 plugin/shared/scripts/eval_pipeline.py bench --cases evals/cases [--baseline] [--clean-env]
```

`audit` 输出 JSON：退出码 `0` 表示全部检查通过，`1` 表示有错误，`2` 表示参数/IO 失败或检测到写入。`bench` 输出逐案例和聚合 JSON：`0` 表示所有执行的 ghs 臂通过，`1` 表示存在案例或结果失败，`2` 表示参数、IO 或没有可用案例。

## 案例目录契约

每个案例必须是一个独立目录，目录名同时是案例名：

```text
evals/cases/<name>/
  case.json
  brief.md
  fixture/
  verify.py
  expected_artifacts.json
```

### case.json

```json
{
  "schema_version": 1,
  "name": "safe-case-name",
  "title": "Short human-readable title",
  "verify_timeout_seconds": 120
}
```

- `schema_version` 必须是 `1`。
- `name` 必须匹配目录名，且首字符为字母或数字，后续可为字母、数字、`-`、`_`。
- `title` 必须是非空字符串。
- `verify_timeout_seconds` 可选，必须是正整数；省略时为 `120`。

### brief.md、fixture/ 和隐藏验证

- `brief.md` 是给代理的完整任务简报，不得暴露 `verify.py` 内容。
- `fixture/` 是初始项目。fixture 的初始状态必须让对应 verifier 失败，否则不能证明代理完成了工作。
- `verify.py` 是唯一结果 oracle。评测器用 Python 执行 `verify.py <workdir>`，工作目录为 `workdir`；exit `0` 才算通过，非零或超时算失败。脚本只能用 Python 标准库，输出尾部会进入报告用于定位失败。
- `expected_artifacts.json` 只记录声明式产物门。隐藏验证前先检查每个产物是否存在；`sha256` 为 `null` 时只查存在，为 64 位小写十六进制时还要求哈希一致。

### expected_artifacts.json

```json
{
  "schema_version": 1,
  "artifacts": [
    {"path": "calc.py", "sha256": null}
  ]
}
```

`path` 必须是相对 POSIX 路径。绝对路径、空路径、`..`、反斜杠和盘符都会导致案例无效。如非刻意锁产物内容，优先用 `sha256: null`。

## 无效案例

出现任一情况时 `load_cases` 判定案例无效，bench 不会启动 host：

- 缺少 `case.json`、`brief.md`、`fixture/`、`verify.py` 或 `expected_artifacts.json`。
- JSON 不可读、不符合上面的字段契约，或 `case.json.name` 不等于目录名。
- 产物路径不安全、重复或哈希字段非法。
- `brief.md` 为空，或 fixture 不是目录。
- fixture 初始状态能通过隐藏验证。

## 过程指标

ghs 臂的 `metrics.layer` 固定为 `"process"`，全部读取 ghs 既有状态，不新增被测侧埋点：

| 指标 | 定义 |
|---|---|
| `review_rounds` | 所有 plan status JSON 中 `retry_counts.review` 的总和。 |
| `rejects` | 所有 plan status JSON 中 `reject_count` 的总和。 |
| `blocked_count` | active 与 archived features 中状态为 `blocked` 的数量。 |
| `materialization_rewrites` | 按 plan 归组，先统计 progress 中 `**Agent**: Plan Materializer` block，再取 `max(0, blocks - 1)`，最后跨 plan 求和；首次初始物化计 0，后续每次物化修订各计 1。 |

baseline 臂不产生 process metrics，报告中该字段为 `null`。

## A/B 对照与解读

默认只跑 ghs 臂。加 `--baseline` 后，每个案例在同一调用中获得两个独立的一次性工作副本：ghs 臂收到先执行 `/ghs:init`、再 `/ghs:plan`、然后 `/ghs:code` 和 `/ghs:archive` 的授权；baseline 臂收到同一 `brief.md`，但禁止使用 ghs、读取或创建 `.ghs/`。两臂使用同一 fixture 和同一隐藏验证；baseline prompt 不会声称 fixture 自带可通过的自动化验证。host 退出后由评测器执行隐藏验证。

baseline 有两种模式，报告必须按 `baseline_env` 分组解读，不得混合比较：

- `ambient`（默认）：两臂共享同一当前宿主环境；用户本地其他 skills/plugins/hooks 和环境变量保持恒定，同时注入相同 plugin root。它回答“在我当前机器配置上 ghs 的边际增益”，不能解读为裸 CLI。
- `clean`（`--clean-env`）：ghs 臂仍用正常宿主环境以加载 ghs；baseline 臂得到全新临时 `CODEX_HOME`，其中只有最小默认 `config.toml`，不加载用户级 skills/plugins/hooks，也不接收 plugin-root 注入。这是有意的不对称，更接近裸 CLI 隔离基线。

顶层 `summary` 分别给出 ghs 与可选 baseline 的 `total`、`passed` 和 `pass_rate`；有 baseline 时还输出 `comparison` 和 `pass_rate_delta`。结果判分只看产物门和 `verify.py` exit code，不使用 LLM 或人工代码质量评审。单案例差异不能推广为总体优势。

## 当前种子语料

按确定性顺序：

1. `case-insensitive-user-lookup`：新增 `find_user(users, email)`，按 email 的大小写不敏感精确匹配返回第一个匹配 dict，找不到返回 `None` 且不得修改输入。
2. `divide-by-zero-guard`：修复 `calc.divide`，非零除数返回向零截断的整数商，零除数抛 `ValueError`。
3. `word-count-cli`：实现 `python word_count.py PATH`，读取 UTF-8 文本并只输出 whitespace token 数，空文件输出 `0`。

## 添加案例

1. 创建合法的 `<safe-name>/` 目录，按上面的契约写入五个固定入口。
2. 在 `brief.md` 写清输入、输出、边界和错误行为；不暴露 verifier 或实现代码。
3. 构造一个必然失败的 fixture，再在本地临时副本中写入参考实现并运行 `verify.py` 确认 exit `0`。
4. 把 `expected_artifacts.json` 限制为最小必要产物。
5. 运行 corpus 级测试：

   ```bash
   command python3 -m unittest plugin.shared.scripts.test_eval_pipeline -v
   ```

6. 如需执行真实 host，再运行 bench；不要把案例源目录交给代理写入。
