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

All main recipes use the shared, content-pinned Terminal-Bench 2.0 subset. The
setup script downloads and verifies it and builds only the selected recipe's
pinned MiniSWE or Codex meta-agent image:

```bash
./scripts/setup_terminal_bench.sh gepa
./scripts/run_recipe_demo.sh gepa
```

Set `EVOLVE_ASSET_DIR` to place the reusable dataset outside the default
`.evolve-assets/terminal-bench-2.0` directory. Benchmark task images remain
dataset-owned and are managed by Harbor.

Development-only recipe fixtures live under `tests/fixtures/recipes/`.
