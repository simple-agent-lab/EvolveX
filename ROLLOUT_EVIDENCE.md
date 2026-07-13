# Harbor rollout evidence profiles

Harbor remains the rollout engine. The `evidence_profile` option controls only
which parts of Harbor's result are retained and emphasized for the mutate agent.

```yaml
operators:
  rollout: {variant: harbor, evidence_profile: self_harness}
```

Supported profiles are `self_harness`, `dgm`, `hyperagents`, `meta_harness`,
`sia`, `ace`, `mce`, `adas`, `aflow`, `gepa`, and `stop`.

## What Harbor provides

For each trial Harbor writes a `result.json`, an `agent/trajectory.json`, agent
output files, and verifier files. The adapter normalizes these into:

- task/trial identity, reward, outcome, exception, and all scalar verifier rewards;
- ordered message/tool-call/tool-result events from the trajectory;
- task instruction, final agent messages, and fallback raw agent output;
- redacted verifier output and an inventory of agent/verifier artifacts;
- token/cost usage and setup/execution/verifier timing.

Secrets are redacted before evidence is persisted. Infrastructure failures are
kept for diagnosis but separated from agent-attributable failures.

## Method mapping

| Profile | Evidence shown to the modify agent | Research correspondence |
|---|---|---|
| `self_harness` | Failed records are attributed as `(terminal verifier cause, causal status, reusable agent mechanism)`, deterministically clustered, and ordered by support. Representative traces and passing behaviors are retained. | [Self-Harness](https://arxiv.org/html/2606.09498) uses verifier-grounded failure signatures, representative tasks, shared symptoms, passing behavior, and prior edit summaries. |
| `dgm` | Concrete failed task instructions, full action/result trace, verifier evidence, and score. Population lineage and prior diffs come from the feedback history. | The [DGM paper](https://arxiv.org/html/2505.22954) and [official implementation](https://github.com/jennyzzt/dgm/blob/main/self_improve_step.py) diagnose a selected failed benchmark entry into a problem statement before self-editing; evaluation metadata and patches are archived. |
| `hyperagents` | Raw evaluation directory, metrics, source tree, and prior-generation history. The modifier is told to inspect these with tools instead of receiving a fixed summary. | [Hyperagents](https://arxiv.org/abs/2603.19461) passes an evaluation folder to an editable meta-agent; the official implementation exposes generated agents/evaluations and allows the meta-agent to edit its own improvement process. |
| `meta_harness` | Full redacted traces, scores, source, and prior candidate run directories through a filesystem interface. | [Meta-Harness](https://arxiv.org/html/2603.28052) stores source, scores, and raw execution traces for every candidate. Its ablation finds raw traces substantially better than scores or LLM summaries. |
| `sia` | Complete structured logs: prompts/messages, model responses, tool calls/results, extracted/final output, verifier feedback, metrics, cost, and timing. | [SIA](https://arxiv.org/html/2605.27276) gives the Feedback-Agent the previous scaffold, full per-instance trajectory, performance metrics/error logs, and optional sample task descriptions. |
| `ace` | Per-example success/failure trajectories and environment feedback in reflector-friendly records, plus successful behavior examples. | [ACE](https://arxiv.org/html/2510.04618) has a Generator mark helpful/misleading behavior, a Reflector extract concrete lessons, and a Curator apply itemized delta bullets with IDs and helpful/harmful counters. This repo preserves the reflector inputs; the modify agent performs reflection/editing. |
| `mce` | A batch/global view of rollout records and metrics, along with prior generation metrics and edit history. | [MCE](https://arxiv.org/html/2601.21557) gives the base agent training rollouts, the prior-best context, and a skill; its meta-agent reads all prior skills plus train/validation metrics to detect over/under-fitting. |
| `adas` | Candidate-level fitness, source tree, archive/lineage, and concise execution experience. | [ADAS](https://arxiv.org/abs/2408.08435) primarily gives the meta-agent an archive of prior agent code, descriptions, and fitness rather than raw task trajectories. |
| `aflow` | Candidate metrics, execution feedback, cost, and lineage/search experience. | [AFlow](https://arxiv.org/abs/2410.10762) uses code workflows, execution feedback, and tree-structured MCTS experience. |
| `gepa` | Input, output, reasoning/tool trace, textual verifier feedback, and score per example. | [GEPA](https://arxiv.org/abs/2507.19457) reflects over reasoning, tool calls/outputs, textual feedback, and scores before proposing prompt updates. |
| `stop` | Per-task utilities and the current improver source; trajectories are not emphasized. | [STOP](https://arxiv.org/abs/2310.02304) evaluates improver code by average downstream utility and asks the improver to improve itself. |

## Persisted artifacts

Every profile writes the same method-neutral files so a later modifier can
change its evidence strategy without rerunning Harbor:

- `rollout/cases.json`: normalized Harbor cases;
- `rollout/evidence/raw_traces.jsonl`: ordered, redacted full trace view;
- `rollout/evidence/failure_records.json`: per-failure causal attribution;
- `rollout/evidence/failure_patterns.json`: Self-Harness-style clusters;
- `rollout/evidence/passing_behaviors.json`: successful behavior to preserve;
- `rollout/evidence/reflective_records.jsonl`: ACE/GEPA/MCE/SIA-style records;
- `rollout/evidence/metrics.json`: aggregate and per-task reward/cost/timing;
- `rollout/evidence/manifest.json`: profile-to-artifact mapping;
- `rollout/evidence/selected.md`: bounded view injected into the mutate prompt.

The feedback assembly also writes `feedback/evidence/history.json`, containing
prior scores, parent/child lineage, changed surfaces, predicted/verified fixes,
selected evidence profiles, rollout metrics, source tags, and paths to prior raw
evidence. Thus filesystem-oriented profiles can compare multiple candidates
without flattening all history into one prompt.

## Fidelity boundary

The profiles reproduce the methods' **rollout-retention interfaces**, not their
entire search algorithms. For example, `aflow` does not add MCTS to the driver,
`mce` does not add a second skill-evolution agent, and `sia` does not train model
weights. They determine which Harbor evidence is persisted and made available
to the existing modify agent, as required here.
