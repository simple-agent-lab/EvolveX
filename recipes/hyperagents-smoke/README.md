# HyperAgents Smoke

This is the deterministic offline scaffold for the `hyperagents` method. It
uses the same fixed selector, rollout, meta-agent, validator, gate, record, and
atomic mutable surface as the real recipe:

- `target/**`
- `operators/meta_agent.py`
- `operators/meta_agent.md`

The differences are only benchmark cost controls: builtin dummy target,
stub-friendly budget, one child per generation, one concurrent task, and small
staged/static task counts. It is intended for `EVAL_STUB=1` proof that accepted
meta-agent workflow edits affect the next generation and that forbidden edits
outside the atomic surface reject the child. Passing `hyperagents-smoke` is a
method-faithfulness smoke, not benchmark validation.
