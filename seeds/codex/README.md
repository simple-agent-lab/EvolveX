# Built-in Codex Target

This target wraps Harbor's installed Codex agent while keeping the behavior
surface under `target/**` so Evolve can mutate it.

- `agent.py` injects the candidate-owned prompt, skills, and Codex flags.
- `prompt.md` is the task prompt template and must retain `{{ instruction }}`.
- `skills/**` contains reusable workflows copied into each Harbor task container.
- `codex.toml` pins the initial model/CLI version and exposes reasoning,
  web-search, compaction, and tool-output settings.

Compaction overrides are off by default so Codex uses model defaults. Set
`compaction.override_defaults = true` to evaluate the candidate values.

Authentication is runtime state, not part of the genome. New workspaces require
`OPENAI_API_KEY`; `OPENAI_BASE_URL` is optional. The shared runtime
configuration passes them through Harbor's supported API-key mode. An explicit
`CODEX_AUTH_JSON_PATH` is also supported, with no implicit home-directory
fallback. Never commit credentials under `target/`.
