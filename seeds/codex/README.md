# Built-in Codex Target

This target wraps Harbor's installed Codex agent while keeping the behavior
surface under `target/**` so RSIHub can mutate it.

- `agent.py` injects the candidate-owned prompt, skills, and Codex flags.
- `prompt.md` is the task prompt template and must retain `{{ instruction }}`.
- `skills/**` contains reusable workflows copied into each Harbor task container.
- `codex.toml` pins the initial model/CLI version and exposes reasoning,
  web-search, compaction, and tool-output settings.
- `.agents/plugins/marketplace.json` and `plugins/evolve-target/**` define an
  evolvable local plugin. The initial `SessionStart` hook injects concise
  candidate-owned context into every evaluated Codex session.

Compaction overrides are off by default so Codex uses model defaults. Set
`compaction.override_defaults = true` to evaluate the candidate values.

Authentication is runtime state, not part of the genome. The default `auto`
mode uses `CODEX_AUTH_JSON_PATH` or `CODEX_FORCE_AUTH_JSON` when either is set,
switches to API mode when `OPENAI_BASE_URL` or `OPENAI_API_BASE` is set, and
otherwise requires `~/.codex/auth.json`. Set `EVOLVE_CODEX_AUTH_MODE` to
`auth_json` or `api` to choose explicitly. API mode requires
`OPENAI_API_KEY`, configures an OpenAI-compatible Responses provider, disables
WebSockets, and supplies the key through both the normal provider auth and the
`api-key` header. Never commit credentials under `target/`.

The Harbor wrapper installs the candidate plugin into its temporary
`CODEX_HOME` for each isolated task. It bypasses interactive hook review only
for that externally sandboxed evaluator invocation, so changed hook definitions
are exercised instead of silently skipped.
