# Supported recipes

Recipes are the public configuration inventory. Each YAML file selects its
target, evaluator, and operator variants; the recipe README explains the
workflow it represents.

- [A-Evolve](aevolve/README.md)
- [Agentic Harness Engineering](ahe/README.md)
- [Agentic Harness Engineering for Codex](ahe_codex/README.md)
- [GEPA](gepa/README.md)
- [Hill Climb](hill_climb/README.md)
- [Hill Climb for Codex](hill_climb_codex/README.md)
- [HyperAgents](hyperagents/README.md)
- [HyperAgents for Codex](hyperagents_codex/README.md)

Codex-backed meta-agent and trajectory-judge jobs use
`evolve-meta-agent-codex:20260805-codex0145`. Build it before an experiment:

```bash
docker build -t evolve-meta-agent-codex:20260805-codex0145 containers/meta-agent-codex
```

This image removes repeated Codex installation from framework-owned Harbor
jobs. Benchmark task images remain dataset-owned; their agent setup is still
managed by Harbor.

Development-only recipe fixtures live under `tests/fixtures/recipes/`.
