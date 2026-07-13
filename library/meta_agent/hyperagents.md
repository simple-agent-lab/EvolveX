# HyperAgents Self-Improvement

Modify any part of the allowed codebase to improve downstream task performance.
The allowed surface is exactly `target/**`, `operators/meta_agent.py`, and
`operators/meta_agent.md`.
You may improve the task agent, this meta-agent workflow and prompt, or their
interaction. Inspect prior generations and evaluation artifacts before editing.
Make one coherent repository change; descendants inherit the complete patch.
Do not modify fixed evaluator, selection, validation, gate, record, configuration,
or mechanism files.
