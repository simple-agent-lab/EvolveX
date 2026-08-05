# Local smoke seed

A deterministic Harbor agent that needs no model and no Docker: it answers
each task by looking the question up in `knowledge.md` and writing the
result to `answer.txt` in the task workdir. Facts are `- <question> = <answer>` list
lines; everything else in the document is prose, so the knowledge base can
grow sections, explanations, and structure as it evolves. Unknown questions
produce `unknown`, which fails the verifier — evolving `knowledge.md` is the
whole optimization problem.

The agent reads candidate files through `EVOLVE_CANDIDATE_SOURCE`, the exact
candidate snapshot the evaluation engine mounts. Follow the same rule in any
custom seed: resolving files relative to `__file__` silently reads the parent
candidate during admission minibatch runs.

Pair this test-oriented seed with the `gepa_local` recipe and a local task
directory to smoke-test a fully local evolution loop.
