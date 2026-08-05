# Evolve skill behavioral evaluation

This suite measures whether the skill changes an Agent's process, not whether
the Agent repeats skill prose.

## Evaluation protocol

Run every behavior case as a paired comparison:

1. Start two fresh Agents with the same model, tools, reasoning effort, and
   token budget.
2. Give the control Agent only the case prompt.
3. Give the treatment Agent the rendered instruction to use the named skill.
4. Keep `rubric.json` hidden from both Agents.
5. Shuffle the two responses and grade them against the case rubric.
6. Record criterion scores, hard failures, and the treatment-minus-control
   score. Do not treat stylistic similarity as improvement.

Each criterion scores `0` (missing or wrong), `1` (partial), or `2` (complete).
A response passes at `8/10` with no hard failure. Report aggregate pass rate,
mean paired delta, and per-dimension failures. A small forward test is evidence
about process adherence, not proof of downstream agent-quality improvement.

## Files

- `behavior_cases.jsonl`: raw prompts for paired response evaluation.
- `invocation_cases.jsonl`: prompts for testing autonomous skill routing.
- `rubric.json`: hidden behavioral expectations and hard failures.
- `render_prompt.py`: emits one control or treatment prompt without the rubric.
- `current_results.json`: latest full behavioral run for the current skill package.

Render a prompt with:

```bash
uv run python evals/evolve-agent/render_prompt.py outer-ahe-agent --arm treatment
uv run python evals/evolve-agent/render_prompt.py outer-ahe-agent --arm control
```

Invocation cases require a runner that exposes the real installed skill catalog
and records whether the model loads a skill before answering. Do not prepend an
explicit `$skill` instruction to those cases.
