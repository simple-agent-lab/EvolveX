# Task 6 Implementation Report

## Summary

Split the recipe catalog into live Harbor recipes and explicit deterministic
smoke recipes. Real recipes now use MiniSWE source checkout plus
`agent_command`; smoke recipes preserve offline scaffold behavior under
`*-smoke` names. Offline init and recipe tests were retargeted to smoke names
where they depended on deterministic scaffolding.

## RED Evidence

### Test-first change

Patched the recipe policy test and offline init helpers before changing recipe
artifacts:

- `tests/test_phase_e_recipes.py`
- `tests/conftest.py`
- `tests/test_m0_init.py`
- `tests/test_m4_presets_bootstrap.py`
- `tests/test_phase_f_init_binding.py`
- `tests/test_harbor_evaluator_config.py`

### Failing command

```bash
uv run pytest tests/test_phase_e_recipes.py -q
```

Observed failure summary:

- `test_all_recipes_are_recipe_artifacts_only` failed because `RECIPE_NAMES`
  did not include the six expected `*-smoke` recipes.
- `test_real_recipes_use_harbor_and_real_agent_mutation` failed because real
  recipes still contained deterministic mutation or non-Harbor evaluator
  engines.
- `test_smoke_recipes_are_explicitly_named_and_deterministic` failed because
  the smoke recipe directories did not exist yet.

## GREEN Evidence

### Required command from brief

```bash
uv run pytest tests/test_phase_e_recipes.py tests/test_m0_init.py tests/test_m5_driver_operators.py -q
```

Result:

- `7 passed in 5.13s`

### Nearby coherence checks

```bash
uv run pytest tests/test_m4_presets_bootstrap.py tests/test_phase_f_init_binding.py tests/test_harbor_evaluator_config.py -q
```

Result:

- `5 passed in 5.40s`

## Changed Files

### Recipe artifacts

- `recipes/README.md`
- `recipes/hill_climb/evolve.yaml`
- `recipes/hill_climb/README.md`
- `recipes/dgm/evolve.yaml`
- `recipes/dgm/README.md`
- `recipes/ahe/evolve.yaml`
- `recipes/ahe/README.md`
- `recipes/autoresearch/evolve.yaml`
- `recipes/autoresearch/README.md`
- `recipes/hyperagents/evolve.yaml`
- `recipes/hyperagents/README.md`
- `recipes/metaagent/evolve.yaml`
- `recipes/metaagent/README.md`
- `recipes/hill_climb-smoke/evolve.yaml`
- `recipes/hill_climb-smoke/README.md`
- `recipes/dgm-smoke/evolve.yaml`
- `recipes/dgm-smoke/README.md`
- `recipes/ahe-smoke/evolve.yaml`
- `recipes/ahe-smoke/README.md`
- `recipes/autoresearch-smoke/evolve.yaml`
- `recipes/autoresearch-smoke/README.md`
- `recipes/hyperagents-smoke/evolve.yaml`
- `recipes/hyperagents-smoke/README.md`
- `recipes/metaagent-smoke/evolve.yaml`
- `recipes/metaagent-smoke/README.md`

### Tests

- `tests/conftest.py`
- `tests/test_phase_e_recipes.py`
- `tests/test_m0_init.py`
- `tests/test_m4_presets_bootstrap.py`
- `tests/test_phase_f_init_binding.py`
- `tests/test_harbor_evaluator_config.py`

## Self-Review Notes

- Kept recipe discovery unchanged; new smoke recipes are discovered naturally by
  adding `evolve.yaml` under new recipe directories.
- Left agent runner, Harbor wrapper, mutation patch builder, and workspace logic
  untouched.
- Updated only tests whose expectations were about offline scaffolding or
  library binding, not tests that intentionally validate Harbor-specific init
  wiring.
- Real recipes now all satisfy the policy enforced in
  `tests/test_phase_e_recipes.py`: Harbor engine, MiniSWE source agent, and
  `agent_command` mutation.

## Concerns

- Real recipe init now depends on cloning
  `https://github.com/SWE-agent/mini-swe-agent.git`, so any future tests or
  local workflows that still use plain recipe names for offline scaffolding will
  need to switch to `*-smoke` explicitly.

## Fix Section

### Changed files

- `tests/test_phase_e_recipes.py`

### Tests run

- `uv run pytest tests/test_phase_e_recipes.py -q`

### Exact results

- `3 passed in 0.03s`

### Self-review notes

- Added explicit assertions for the real-vs-smoke dataset and seed policy so
  the recipe catalog test now covers the invariant called out in review.
- Kept the change constrained to the existing recipe policy test file.
