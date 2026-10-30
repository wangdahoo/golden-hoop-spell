# Codex Host Operating Manual (golden-hoop-spell)

This is the OpenAI Codex CLI operating manual for the golden-hoop-spell plugin
(plugin `golden-hoop-spell`, version `0.8.0`, manifest at
`<plugin_root>/.codex-plugin/plugin.json`). The Claude side never reads this file.

Read it when the Platform Adaptation block in a SKILL.md directs you here, i.e.
after `host_compat.py` reports `"host": "codex"`. Precedence rule: follow this file
wherever it supersedes a host-specific instruction in the SKILL.md body (subagent
dispatch, interactive questions, plugin-root resolution). Everything this file does
not mention applies exactly as written in the body - the skill scripts, references,
delimiters, state machines, and file formats are shared verbatim with the Claude
side; only host primitives are swapped here.

Convention: every Python invocation in this plugin uses `command python3`, never a
bare `python3`.

## 1. Prerequisites

1. **multi_agent feature flag (hard prerequisite for the main dispatch path).**
   `~/.codex/config.toml` must contain:

   ```toml
   [features]
   multi_agent = true
   ```

   If it is missing, the `spawn_agent` tool family is unavailable and the main path
   in block 2 cannot be used. Tell the user how to enable it (add the lines above,
   restart the CLI session) and re-check. If it is still unavailable, use the
   block 6 fallback and record that fact in the session log.

2. **Machine-level subagent defaults (recommended safety net).** ghs never requests
   a per-spawn model or reasoning effort. Recommend that the user set machine-level
   defaults in `~/.codex/config.toml` so subagent runs inherit them:

   ```toml
   [agents]
   default_subagent_model = "<model name>"
   default_subagent_reasoning_effort = "<effort>"
   ```

   These keys are a fallback only; ghs works without them.

3. **python3 on PATH.** All helper scripts are standard-library-only Python and are
   always invoked as `command python3 <plugin_root>/shared/scripts/<script>.py`.

4. **Skill invocation forms.** The user triggers ghs skills on Codex either by
   describing the task in natural language (the model selects the matching skill)
   or by explicitly @-mentioning the plugin or skill. Both forms reach the same
   SKILL.md body; this manual then overlays the host-specific instructions.

## 2. Subagent Dispatch - Main Path (multi_agent)

The main path uses the native multi_agent tools: `spawn_agent`, `wait_agent`,
`followup_task`, `list_agents`. Before the first dispatch, confirm all four tool
names are present in the current turn's tool table. The actual tool table is always
the authority: if a named tool is absent, treat multi_agent as unavailable and go
to block 6.

Dispatch rules:

- **Clean-context fork.** Spawn with `{ fork_turns: "none" }` so every subagent
  starts from a clean context, matching the CONTEXT RESET isolation the ghs prompt
  templates assume. The prompt you pass is the body's template with all
  `<PROJECT_DIR>` and `${CLAUDE_PLUGIN_ROOT}` placeholders already literally
  replaced (see block 5) - subagents never see an unresolved variable.
- **Bounded wait, no polling.** Wait with `wait_agent` event subscription using a
  bounded `timeout_ms` between 300000 and 600000. Do not short-poll. Mind the async
  receipt semantics: the wait returning is not the answer - the subagent's
  completion answer arrives through the mailbox on the next turn.
- **Reconciliation.** Use `list_agents` to account for spawned agents before and
  after each wave (who is running, who finished, who failed).
- **Retries continue the SAME agent.** For a format retry (Format Recovery) or any
  follow-up instruction, use `followup_task` to send the same agent the recovery
  appendix plus the exact file path for THIS attempt. Do not spawn a fresh agent
  for a retry.
- **No close tool.** The V2 lifecycle has no `close_agent`; completed agents are
  reclaimed automatically. Do not look for one.

**Long-output handoff (plan / review lanes).** Subagents whose output is a long
delimited document (plan body, review report) must NOT pour the full document into
their reply. They write it verbatim to a file and return only the path. Append
this handoff appendix to the dispatch prompt (substitute the exact raw path and
the lane's normal completion signal):

```
## Output Handoff (Codex)
Write your FULL response verbatim - including every required delimiter pair and
your completion-signal line - to this exact file before you finish:
  <RAW_PATH>
Your final reply must contain ONLY:
1. The line: HANDOFF FILE: <RAW_PATH>
2. Your normal completion-signal line (e.g. <COMPLETION_SIGNAL>)
Do not summarize, truncate, or reformat the document in the reply.
```

Concrete raw paths per lane are defined in block 3. The dispatcher then runs the
existing parser helper with `--input-file` exactly as the body specifies, and reads
the parser's JSON result file with the host's file-reading tool (any file-read tool
available to this session - the body's "Read tool" means this on Codex). Never
consume the parser's stdout; under `--output-file` it only prints a one-line ASCII
pointer. Completion and branching decisions look only at the raw file's parse
result - never at a mailbox summary of what the subagent "said".

## 3. Role Mapping and Raw-File Writers

Claude `subagent_type` to Codex agent type:

| Claude body says | Spawn on Codex | Notes |
|---|---|---|
| `general-purpose` | `default` | reviewer, parallel implementation workers |
| `Plan` | `default` | prompt text unchanged - it still carries the full plan-designer.md instructions; only the agent type name differs |
| `Explore` | `explorer` | read-only context extraction |

Per-lane raw-file writer assignment. This is the one responsibility that differs
from the Claude side (where the dispatcher holds the response and writes the
scratch file); on Codex the writable `default` agent takes it over, and the body's
"Plan subagents do not have file write permissions" note is superseded for the
plan lane:

- **Plan lane (designer).** The subagent writes its full delimited output to
  `<PROJECT_DIR>/.ghs/plans/.tmp/<run-id>.plan.raw` (handoff appendix) and returns
  the path. The dispatcher parses that file with
  `parse_delimited_output.py --kind plan` (`--input-file` the subagent-written
  scratch, `--output-file` the result JSON) as the body specifies, reads the result
  JSON with the file-read tool, deletes both scratch files, and branches on
  `status` unchanged.
- **Review lane.** Same pattern with `.tmp/<run-id>.review.raw` and
  `parse_delimited_output.py --kind review --completion-signal "REVIEW COMPLETE"`.
- **Context lane (default).** The `explorer` agent is read-only, so it cannot write
  the scratch file. It outputs the full delimited snapshot
  (`<<<CONTEXT_SNAPSHOT_START>>>` ... `<<<CONTEXT_SNAPSHOT_END>>>`) in its
  response; the dispatcher captures that response via the existing body mechanism
  and writes it verbatim to `.tmp/<run-id>.context.raw` for the parser. This lane
  trusts response fidelity - if the delimiters or the body arrive damaged, treat it
  as a parse failure (retry / escalation below), never silently continue.

`<run-id>` follows the body's naming rule: any identifier stable within THIS run
(recommended: the `{date}-{slug}` file identifier plus a scratch counter when one
round writes several scratch sets); never derive it from the host session
identifier.

**Probe-gated escalation for the context lane (program unchanged).** Only when
running the plan pipeline's context leg, run the two observations and apply the
gate before relying on it:

1. Write-probe: add one probe instruction to the explorer dispatch - write a single
   line to `<PROJECT_DIR>/.ghs/explorer-write-probe.tmp` and report success or
   failure. Record "can write" / "cannot write"; delete the probe file afterwards.
2. Fidelity observation: run the context lane normally and check whether the
   captured response keeps both delimiters and the full snapshot body. Record
   "faithful" / "summarized".
3. Verdict: if summarized (dispatcher capture unreliable) OR can write (read-only
   assumption false, file handoff feasible), propose the escalation to the user and
   switch only after on-the-spot user approval: from then on spawn `default` with
   the same read-only constraint sentence appended, and use the file-handoff
   appendix with `.tmp/<run-id>.context.raw`. If "cannot write AND faithful", or
   the user does not approve, keep the explorer default. If summarized but not
   approved, record the leg as failed and let the existing parse-failure ->
   retry -> user-decision path absorb it.

**No MCP on Codex.** Codex sessions have no codegraph MCP. Skip the codegraph
detection probe entirely, set `CODEGRAPH_AVAILABLE = false` unconditionally, use
the `PROMPT_TEMPLATE_GREP` lane, and spawn `explorer` for it. The
`PROMPT_TEMPLATE_CODEGRAPH` / `general-purpose` combination never occurs on Codex.

## 4. Interactive Questions (AskUserQuestion Downgrade)

The body's AskUserQuestion calls downgrade on Codex in two tiers.

**Tier 1 - main path: the native `request_user_input` tool.** When it is
available, use it for every question the body routes through AskUserQuestion:

- Semantics preserved: one call can carry multiple questions; multiple-choice is
  preferred; every question requires a non-empty options list; free-form text
  answers are supported as well.
- Availability requires ALL THREE conditions:
  1. the tool is listed in the current turn's available tools table;
  2. an interactive stdin terminal is attached - `codex exec` and other
     non-interactive modes cannot use it;
  3. root thread only - subagents must never ask (the tool errors with
     "request_user_input requires the root thread"). ghs only asks from the
     dispatcher (main conversation), which satisfies this condition naturally.
- Async receipt discipline: the call returns immediately instead of blocking; the
  user's answers arrive with a later turn. Keep the body's "wait for the user's
  reply before branching" discipline unchanged - end your turn after asking and
  branch only when the answers arrive. Never assume the call blocks until the user
  has answered.
- Hard approval gates (for example the plan approval surface, or the
  plan-completion confirm in ghs-code): if no answer has arrived, re-ask ONCE
  explicitly; if the re-ask also goes unanswered, fall back to the tier 2 text
  question and record the downgrade in the session log (the `.ghs/progress.md`
  entry).

**Tier 2 - fallback: plain-text questions (kept for `codex exec` and every other
non-interactive scenario).** Follow this clause exactly:

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

## 5. ${CLAUDE_PLUGIN_ROOT} Resolution

Body commands reference `${CLAUDE_PLUGIN_ROOT}`. Codex does not guarantee that
this variable is expanded inside a skill session (verify once per install; the E2E
manual records the outcome). Three outcomes, all functional:

1. **Expanded by the host** - body commands work as written.
2. **Not expanded** - bootstrap per the SKILL.md Platform Adaptation block: derive
   the plugin root from the directory of the SKILL.md you are executing (its
   grandparent directory), run
   `command python3 <plugin_root>/shared/scripts/host_compat.py`, and take the
   script's single-line JSON output as the authority:
   `{"host": ..., "plugin_root": ..., "resolution": ...}` - the `plugin_root`
   value is the absolute root used everywhere below.
3. **Script reports unknown** - `host_compat.py` exits 1 with
   `{"host": "unknown", "plugin_root": null, "resolution": "asked"}`. The script
   itself never asks; ask the user for the plugin root path, use it, and continue.

**Single-point resolution.** Whatever the outcome, resolve the plugin root exactly
once in the main conversation, then literally substitute the resolved absolute
path for every `${CLAUDE_PLUGIN_ROOT}` occurrence in every prompt template before
dispatching a subagent - subagents never face an unresolved variable.

## 6. Fallback - Natural-Language Spawn (multi_agent unavailable)

When the block 1 flag is off, the CLI predates the multi_agent tools, or the tool
table lacks any of the four names: degrade to natural-language parallel spawn.

- Dispatch each subagent through the host's default agent-spawn mechanism with the
  same prompt (placeholders already substituted) plus the block 2 handoff appendix
  and the exact raw path for this attempt.
- **Summary-recovery risk (explicit).** In this mode the reply may be a summary
  rather than the verbatim output. Completion judgment therefore reads ONLY the
  raw file parse result (`parse_delimited_output.py` / `parse_completion_signal.py`
  on the raw file) and never trusts the summary content. A missing or unparseable
  raw file is a format failure: retry per Format Recovery, and the existing
  `MAX_RETRY` state machine and User Decision Handling apply unchanged.
- **ghs-code `--parallel`.** Every dispatched agent writes
  `<PROJECT_DIR>/.ghs/parallel/<plan_id>/<feature_id>.raw.attempt<N>` (attempt
  numbering stated in the dispatch prompt; a retry writes `attempt<N+1>`). The
  `dispatch_start_iso` precondition gate (commit/files sanity check) and the whole
  retry state machine are unchanged - recovery continues verbatim from the body's
  Verification Phase parser step.
- Record in the session log that the fallback path was used, so the
  summary-recovery risk stays visible in post-mortems.
