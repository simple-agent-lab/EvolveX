# HyperAgent handoff — 2026-07-23 21:00

## Current state

- The two real experiments are **stopped**. No matching processes or task containers remain.
- Their initialized workspaces and all modifications are preserved:
  - Inline: `/data00/home/zimuwang/simple-evolve-agent-10x3-20260722/experiments/tb2-ahe-10x3-10gen-20260723-v23-inline-filedebugger-responses-64k/ahe-10x3-10gen-20260723-v23-inline-filedebugger-responses-64k`
  - File-backed: `/data00/home/zimuwang/simple-evolve-agent-file-backed-20260722/experiments/tb2-ahe-10x3-10gen-20260723-v24-file-backed-filedebugger-responses-64k/ahe-10x3-10gen-20260723-v24-file-backed-filedebugger-responses-64k`
- Intended tmux session names:
  - `sea-ahe-inline-v23-real`
  - `sea-ahe-file-v24-real`

## Fix and verification

- OpenAI Responses calls now default to `max_output_tokens=64000` while preserving explicit overrides.
- Candidate reasoning remains `high`; AHE meta-agent reasoning is `xhigh`.
- Frozen real configs: 10 generations, 10 tasks/round, `k=2`, concurrency 5.
- Concurrent smokes produced clean tool-calling Responses requests with 64k, no truncation, and no `RepeatedFormatError`.
- Live real trajectories also showed 64k + high reasoning and completed requests without errors before the runs were stopped.
- Local tests: `395 passed`; `git diff --check` passed.
- Main edited wrappers:
  - `templates/workspace/evolve_harbor_adapter/__init__.py`
  - `templates/target/harbor/miniswe_source_agent.py`
  - tests in `tests/test_miniswe_harbor_wrapper.py`

## Important operational note

`--max-generations` limits evolution rounds, not evaluator attempts, benchmark tasks, or agent steps. A nominal per-task timeout did not bound the entire Harbor lifecycle, which is why earlier one-generation runs lasted much longer than expected.

When starting the real runs, source `/data00/home/zimuwang/simple-evolve-agent-project/.env`, set `EVOLVE_RUNTIME_DIGEST=tb2-10x3-runtime-20260722-v3`, `EVOLVE_UV_BINARY=/home/zimuwang/.local/bin/uv`, and reuse the runtime caches from the old v15/v16 workspaces. Run each preserved workspace with its source root's `.venv/bin/python -m evolve run <workspace> --max-generations 10 --verbose` inside the tmux sessions named above.
