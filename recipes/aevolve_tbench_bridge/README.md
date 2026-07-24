# A-Evolve Terminal-Bench Bridge

Runs A-Evolve for ten generations with a MiniSWE source target, Codex as the
Harbor-hosted meta-agent, and a local OpenAI-compatible Responses bridge for
target rollouts. Supply the local MiniSWE seed and Terminal-Bench dataset with
`evolve init --seed ... --dataset ...`.

The A-Evolve meta-agent may evolve the MiniSWE runtime prompt, reusable skills,
and JSONL memory; tools remain disabled. During each rollout the fixed Harbor
adapter discovers `target/skills/*/SKILL.md`, adds the skill names,
descriptions, and readable container paths to MiniSWE's system prompt, and
injects the last 100 entries from `target/memory/*.jsonl`. The complete skill
body stays lazy-loaded: MiniSWE reads the referenced `SKILL.md` with its bash
tool when the skill is relevant.
