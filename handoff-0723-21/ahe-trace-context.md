# AHE trace-context handoff — 2026-07-23 21:17

- AHE now writes all bounded rollouts for each task to
  `/app/task/inputs/trace-evidence.json`; the debugger prompt contains only a
  short description and that path.
- Analysis scope matches AHE: one analyzer stage over all selected tasks, with
  one debugger call per task containing all pass/fail rollouts for that task.
- Debugger failures are fail-soft and counted as `debugger_errors` in
  `analysis/summary.json`. The real-run gate should require 10 detail reports
  and `debugger_errors == 0`.
- Both candidate and meta-agent paths use the Responses endpoint. OpenAI
  requests use a stable per-agent `prompt_cache_key` plus
  `extra: {"session_id": ...}` routing; reasoning effort remains enabled.
- Focused remote tests passed in both source trees (48 each); local suite passed
  before the later 64k-output changes. See `README.md` in this folder for the
  final v23/v24 real workspaces and latest full verification.

Current v15/v16 validation runs are **not the intended real experiments**:

- Inline v15: genesis certified; trace analyzer running.
- File-backed v16: genesis certified; trace analyzer running.
- Both use resilient `nohup` controllers because the DevBoxS tmux server
  previously disappeared and killed both parent controllers.

For the real runs, use the stopped v23/v24 workspaces documented in
`handoff-0723-21/README.md`, preserve 5 evaluator workers each, and record the
exact meta-agent image ID noted in `meta-agent-docker.md`.
