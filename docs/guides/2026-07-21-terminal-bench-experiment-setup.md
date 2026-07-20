# Terminal-Bench 2.0 experiment setup

This is the retained setup for the HyperAgents and AHE experiments. Each method
is compared with its own reference implementation and experimental claims, not
against the other method.

## Common setup

- Benchmark: the complete 89-task Terminal-Bench 2.0 dataset.
- Sampling: the same frozen task set is evaluated at generation 0 and after
  every candidate generation. There is no train/test dataset split or separate
  final anchor in this optimization experiment.
- Model: `openai/gpt-5.4-2026-03-05` for canonical rollouts, AHE debugger calls,
  and the meta-agent.
- Concurrency: four canonical-evaluation workers per experiment.
- Candidate runtime: UV, Python 3.12, with a host-prepared cache and interpreter
  mounted into Harbor. Candidate containers run UV offline.
- Harbor mounts the experiment workspace writable. Prompts define the intended
  editable surface, and the deterministic surface check rejects changes outside
  that surface.
- The frozen evaluator, task identities, model choice, credentials, and resource
  limits are not mutable candidate state.

The score at each generation is that generation's canonical full-benchmark
score. A lower later score does not invalidate an earlier score; the learning
curve and best-ever candidate are separate views.

## AHE

- Recipe: `ahe`.
- Canonical sampling: `k: 2`, giving 178 trials per full generation.
- Mutable surface: `target/**`.
- Each selected parent's retained canonical trajectories are analyzed by one
  MiniSWE debugger call per task. The debugger writes a Harbor artifact; there
  is no plain-LLM or trajectory-text fallback.
- The meta-agent is encouraged to make one coherent `target/**` change and to
  emit `<AHE_CHANGE_MANIFEST>`, but the manifest is best-effort metadata.
  Missing or malformed manifest JSON does not reject a valid patch.
- Authoritative change context is the raw meta-agent output, `changed.json`, and
  `patch.diff`, plus a parsed or synthesized manifest when available. The next
  meta-agent receives all of this context. Predicted-fix and risk attribution is
  optional; transition measurement and canonical gating do not depend on it.
- The gate accepts a surface-clean child when canonical evaluation completes and
  marks it parent-eligible, regardless of score regression or manifest format.

## HyperAgents

- Recipe: `hyperagents`.
- Canonical sampling: `k: 1`, matching the retained HyperAgents setup, giving 89
  trials per full generation.
- Mutable surface: `target/**` and `operators/**`. The prompt still requires a
  substantive target change.
- Retained canonical trajectories feed the trace browser, and the Harbor
  meta-agent may evolve both agent behavior and the allowed operator process.
- The parent-eligible gate admits canonically evaluated process variants even
  when their score is lower than the current best.

## Readiness smoke completed on DevBoxS

The readiness smoke used the same four frozen Terminal-Bench tasks for both
methods: `cancel-async-tasks`, `largest-eigenval`, `prove-plus-comm`, and
`regex-log`.

| Method | Evidence | Result |
| --- | --- | --- |
| AHE | Fresh generation after the best-effort-manifest change; four debugger artifacts, one surface-clean two-file target patch, `k: 2` canonical evaluation, gate, and record | 8/8 child trials benchmark-complete, zero exceptions and retries; gate accepted |
| HyperAgents | Generation 0 plus two successful candidate generations on the same four-task set | 12/12 trials benchmark-complete, zero exceptions; both candidate gates accepted |

The AHE smoke intentionally exercised the missing-manifest case: the model
omitted the formal block, the raw output and patch were preserved, a context
manifest was synthesized, and the full generation completed. These smoke scores
are readiness diagnostics, not benchmark results.

## Full-run shape

When authorized, initialize one workspace per method from the corresponding
recipe, point `evaluator.dataset` at the full frozen Terminal-Bench 2.0 task
directory, retain the settings above, and run generation 0 followed by ten
candidate generations. Run the two methods independently; neither consumes the
other method's state or results.
