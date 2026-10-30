# Pi Host Operating Manual (golden-hoop-spell)

This is the Pi coding agent operating manual for the golden-hoop-spell plugin
(plugin `golden-hoop-spell`, version `0.8.0`; the plugin's resource declarations
live in the repository root `package.json` under the `pi` key). The Claude side
never reads this file.

Read it when the Platform Adaptation block in a SKILL.md directs you here, i.e.
after `host_compat.py` reports `"host": "pi"`. Precedence rule: follow this file
wherever it supersedes a host-specific instruction in the SKILL.md body (subagent
dispatch, interactive questions, skill invocation, plugin-root resolution).
Everything this file does not mention applies exactly as written in the body - the
skill scripts, references, delimiters, state machines, and file formats are shared
verbatim with the Claude side; only host primitives are swapped here.

Convention: every Python invocation in this plugin uses `command python3`, never a
bare `python3`.

## 1. Prerequisites

1. **pi-subagents (hard prerequisite for the three-role pipeline and `--parallel`).**
   The `subagent` tool used throughout this manual is provided by the extension
   package `pi-subagents`. Install it before the session starts:

   ```
   pi install npm:pi-subagents
   ```

2. **Verify availability before the first dispatch.** Before the first subagent
   dispatch of a run, confirm the tool is in place: call the management action
   `{action: "list"}` once (it must answer with the agent roster), or confirm a
   `subagent` entry in the current turn's tool table. The actual tool table is
   always the authority - if `subagent` is absent, treat pi-subagents as
   unavailable no matter what any document says.

3. **If pi-subagents is not installed: stop and report - never fake it.** When the
   check above fails (the `subagent` tool is not installed, `{action: "list"}`
   errors, or the tool table has no `subagent` entry), STOP the multi-subagent
   work (the ghs:plan three-role pipeline and `ghs-code --parallel`), explicitly
   report the missing prerequisite to the user, hand them the exact install
   command from item 1, and record the fact in the session log
   (`.ghs/progress.md`). Do NOT inline the subagent's role yourself, merge lanes,
   or otherwise pretend the capability exists - silent degradation is forbidden.
   Single-feature `ghs-code` runs that dispatch no subagents are unaffected and
   may proceed normally.

4. **`ask_user` is NOT an install prerequisite.** The ghs-bundled `ask_user`
   interactive extension (block 4) is declared in the repository root
   `package.json` under the `pi.extensions` key and registers itself
   automatically when the installed plugin is loaded (`pi.registerTool` takes
   effect in the same session) - there is no extra step to run and nothing to
   install here.

5. **python3 on PATH.** All helper scripts are standard-library-only Python and
   are always invoked as `command python3 <plugin_root>/shared/scripts/<script>.py`.

## 2. Subagent Dispatch - Main Path (pi-subagents)

The main path is the `subagent` tool. Dispatch rules:

- **Single dispatch.** `{agent: "<mapped name>", task: "<full prompt>"}`. The
  prompt you pass is the body's template with all `<PROJECT_DIR>` and
  `${CLAUDE_PLUGIN_ROOT}` placeholders already literally replaced (see block 5) -
  subagents never see an unresolved variable.
- **Native file handoff on every lane.** Every dispatch passes
  `output: "<raw absolute path>", outputMode: "file-only"` (per-lane raw paths in
  block 3). The extension writes the subagent's FULL final response verbatim to
  that file - every delimiter pair and the completion-signal line included - and
  the receipt you get back is only a file reference. The receipt is not the
  payload; never judge anything from it. Because the extension performs the
  handoff itself, no Codex-style "write your output to a file" appendix is
  appended to the prompt: dispatch the body's template unchanged.
- **Parallel dispatch.** For `ghs-code --parallel`, send each parallel_utils batch
  as ONE call: `{tasks: [{agent, task, output, outputMode}, ...], concurrency: N}`,
  with every task entry carrying its own raw path for THIS attempt (block 3). The
  body's batch semantics are otherwise unchanged.
- **Parser consumption.** Run the parser helpers exactly as the body specifies.
  Where the body has the parser write a `--output-file` result JSON
  (`parse_delimited_output.py`), read that result file with pi's `read` tool (the
  body's "Read tool" means this on pi) and never consume the parser's stdout,
  which only prints a one-line ASCII pointer under `--output-file`.
  `parse_completion_signal.py` prints its JSON to stdout per the body's
  Verification Phase. Delete raw scratch and result files afterwards exactly as
  the body instructs.
- **Completion judgment reads the raw file only.** Branch on the raw file's parse
  result (`parse_delimited_output.py` / `parse_completion_signal.py` run on the
  raw file), never on the receipt text or any summary of what the subagent
  "said".
- **Async is an optional optimization.** `async: true` plus the management
  actions `{action: "status"}` and `{action: "resume"}` may background
  dispatches. They are optional: completion judgment still reads ONLY the raw
  file parse result whenever the attempt is accounted for.
- **Retries re-dispatch.** A format failure (Format Recovery) re-dispatches the
  SAME prompt plus the recovery appendix, with `output` pointing at the raw path
  for the new attempt: `attempt<N+1>` in parallel mode, the body's retry scratch
  name (for example `<context_file>.raw.retry<T>`) in the plan lanes. Keep the
  same mapped agent name and prompt template as the first attempt. The
  `MAX_RETRY` state machine and User Decision Handling apply unchanged.

## 3. Role Mapping and Raw-File Writers

Claude `subagent_type` to pi-subagents builtin agent:

| Claude body says | Spawn on pi | Notes |
|---|---|---|
| `general-purpose` | `delegate` | reviewer, review lane, parallel implementation workers |
| `Plan` | `planner` | its "read and plan, not edit code" semantics match the Claude Plan subagent; prompt text unchanged |
| `Explore` | `scout` | read-only context extraction |

- **Trust the actual roster, not this table.** Before relying on a mapped name,
  run `{action: "list"}` and take ITS output as the authority (the same
  "trust the actual tool table" discipline the body applies everywhere). If a
  mapped name is absent from the roster, fall back to `delegate` with the
  original prompt unchanged and record the substitution in the session log.
- **Review lane.** The Phase 4 reviewer's `subagent_type` is `general-purpose`,
  so it maps to `delegate` and its prompt is unchanged.
- **Raw-file writers (all three lanes).** On pi every lane's subagent writes its
  own raw file through the block 2 file handoff - there is no dispatcher-capture
  lane and no probe-gated escalation program (that is a Codex-side workaround for
  a read-only agent; pi's file-only output mode makes it unnecessary):
  - Plan lane (designer): `<PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.plan.raw`
  - Review lane: `<PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.review.raw`
  - Context lane: `<PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.context.raw`

  These are parsed with the body's `parse_delimited_output.py --kind plan|review`
  invocations unchanged. The context lane's response-fidelity concern is absorbed
  by the extension's verbatim file write: if the raw file is missing or
  unparseable, treat it as a parse failure and let the existing retry path absorb
  it - never silently continue.
- **`--parallel` raw files.** Each dispatched task writes
  `<PROJECT_DIR>/.ghs/parallel/<plan_id>/<feature_id>.raw.attempt<N>` via its
  `output` parameter (a retry writes `attempt<N+1>`); the `dispatch_start_iso`
  precondition gate and the whole retry state machine are unchanged.
- **`<run-id>` follows the body's naming rule**: any identifier stable within
  THIS run (recommended: the `{date}-{slug}` file identifier plus a scratch
  counter when one round writes several scratch sets); never derive it from the
  host session identifier.

## 4. Interactive Questions (AskUserQuestion Downgrade)

The body's AskUserQuestion calls downgrade on pi in two tiers.

**Tier 1 - main path: the ghs-bundled `ask_user` extension.** It is registered by
the plugin itself (`pi.registerTool`) and renders its questions through the
native `ctx.ui.select` / `ctx.ui.input` controls. When it is available, use it
for every question the body routes through AskUserQuestion:

- Availability: the tool table of the current turn contains `ask_user`. The
  actual tool table is always the authority.
- Semantics preserved, aligned with the Claude AskUserQuestion surface: one call
  carries a batch of questions (single-turn batch semantics); every question
  enumerates its options; a `recommended` option is offered per question;
  free-form answers are supported through the trailing `Other` entry.
- Ask only from the dispatcher (main conversation), as the body already
  prescribes; do not route questions through subagents.
- If a call fails to render (for example a non-interactive session without the
  TUI attached), treat the tool as unavailable for this run and fall back to
  tier 2, recording the downgrade in the session log.

**Tier 2 - fallback: plain-text questions (used whenever the tool table has no
`ask_user` entry - extension missing, load failure, or a failed call).** Follow
this clause exactly:

> On hosts without AskUserQuestion, ask the user in plain text instead, keeping the
> original option-table semantics exactly. Per question, enumerate the options
> verbatim (original numbering and wording), mark the recommended option with a
> one-line reason, and wait for the user's reply before proceeding on the chosen
> branch. Keep the original batching form: questions the body groups into one
> single batched AskUserQuestion (e.g. builder questions, one batch of up to 5) are
> enumerated together in a single message and answered in order; questions asked
> individually stay one per message.

The body's text-hygiene rule still applies to every question and option: plain
text only - no control characters, no ANSI escapes, no emoji or decorative
special symbols.

## 5. Skill Invocation and ${CLAUDE_PLUGIN_ROOT} Resolution

- **Invocation form.** Every ghs skill sets `disable-model-invocation: true` in
  its frontmatter, so the user invokes them on pi with the explicit command form
  `/skill:ghs:<name>` (for example `/skill:ghs:plan`). Wherever the body's
  Closing Steps or text say "run `/ghs:xxx`", read that on pi as
  `/skill:ghs:xxx` - same skill, pi's command namespace.

- **${CLAUDE_PLUGIN_ROOT} is never expanded by pi.** Bootstrap per the SKILL.md
  Platform Adaptation block: derive the plugin root from the directory of the
  SKILL.md you are executing (its grandparent directory), run
  `command python3 <plugin_root>/shared/scripts/host_compat.py`, and take the
  script's single-line JSON output as the authority:
  `{"host": ..., "plugin_root": ..., "resolution": ...}` - the `plugin_root`
  value is the absolute root used everywhere below. If the script exits 1 with
  `{"host": "unknown", "plugin_root": null, "resolution": "asked"}`, it never
  asks by itself: ask the user for the plugin root path, use it, and continue.

- **Single-point resolution.** Whatever the outcome, resolve the plugin root
  exactly once in the main conversation, then literally substitute the resolved
  absolute path for every `${CLAUDE_PLUGIN_ROOT}` occurrence in every prompt
  template before dispatching a subagent - subagents never face an unresolved
  variable.

- **Tool-name mapping.** Wherever a body instruction names the Claude Read tool
  (reading parser result files, reading reference files), that means pi's `read`
  tool; apply the same substitution to other Claude tool names when pi's
  builtins differ.

## 6. Fallback and Limits

- **No `subagent` tool.** Per block 1: stop the multi-subagent work, report the
  missing pi-subagents prerequisite with its install command, and record it.
  There is NO natural-language-spawn degrade on pi - pretending the capability
  exists is forbidden. Single-feature `ghs-code` runs without subagents are
  unaffected.
- **No codegraph MCP on pi.** pi sessions have no codegraph MCP. Skip the
  codegraph detection probe entirely, set `CODEGRAPH_AVAILABLE = false`
  unconditionally, use the `PROMPT_TEMPLATE_GREP` lane, and spawn `scout` for
  it. The `PROMPT_TEMPLATE_CODEGRAPH` / `general-purpose` combination never
  occurs on pi.
