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

Authentication is runtime state, not part of the genome. Run `codex login` on
the host so `~/.codex/auth.json` exists; set `CODEX_AUTH_JSON_PATH` only when
using another auth file location. Never commit credentials under `target/`.
