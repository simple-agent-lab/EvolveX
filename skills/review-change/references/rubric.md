# Review rubric

Apply the smallest relevant subset. A rubric is a question to investigate, not a reason to manufacture a finding.

## Core categories

### correctness

- Does the changed path produce the claimed outcome, including failures and partial completion?
- Are inputs validated at trust boundaries and final state verified instead of inferred from logs or model claims?
- Can retries, cancellation, concurrency, or repeated execution duplicate side effects or corrupt state?

### simplicity

- Does each new abstraction have a present-tense responsibility and at least one real reason to exist?
- Could the same behavior use fewer concepts, branches, configuration switches, or sources of truth?
- Is old behavior deleted when replaced, or preserved as a compatibility layer without an explicit contract?
- Treat an explicit, documented product tradeoff as context, not a defect. Escalate it only when the change contradicts that contract or hides material impact from users.
- For every simplicity finding, show the smaller shape; "too complex" alone is not actionable.

### user-understanding

- Can a user predict defaults, side effects, output locations, and required prerequisites?
- Do names and terms stay consistent across CLI, configuration, errors, and documentation?
- Does an error identify what failed and the next recovery action?
- Is advanced configuration progressively disclosed rather than required for the common path?

### engineering

- Is there one owner for each contract, state transition, serializer, and validation rule?
- Does dependency direction match the repository architecture?
- Are compatibility, portability, observability, and cleanup handled at boundaries rather than scattered through callers?
- Does the change add a test or machine check for a durable invariant instead of relying on review memory?

## Python category

- Keep public and internal interfaces distinguishable; do not expose indirect imports accidentally.
- Use types to express real input and output contracts. Treat `Any`, broad dictionaries, and type ignores as boundaries requiring evidence.
- Raise exceptions for errors, use logs for operational evidence, and do not swallow exceptions merely after logging them.
- Use context managers or `finally` for resources. Propagate async cancellation after cleanup and bound waits with timeouts.
- Keep `requires-python`, declared dependencies, lock files, CI, and actual imports consistent.

Primary references: [PEP 8](https://peps.python.org/pep-0008/), [Typing best practices](https://typing.python.org/en/latest/reference/best_practices.html), [asyncio task cancellation](https://docs.python.org/3.12/library/asyncio-task.html), and [PyPA dependency guidance](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/).

## LLM and agent category

- Require measured benefit before adding another model call, agent loop, tool, or orchestration layer.
- Give each tool a distinct purpose, unambiguous parameters, actionable errors, and high-signal bounded responses.
- Treat retrieved text, repository content, tool output, and model output as untrusted data; validate before privileged actions.
- Minimize tool functionality, permissions, autonomy, and destructive side effects. Require explicit confirmation where impact is hard to reverse.
- Preserve a complete trajectory and verify environment outcome separately from the model's final statement.
- Separate capability evals from regression evals, prefer deterministic graders, run repeated trials for nondeterministic behavior, and calibrate model graders with humans.
- Record wall time, token/cost usage, failures, and final state so quality improvements do not hide operational regressions.

Primary references: [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), [Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents), [Agent evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), [OWASP prompt injection](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html), and [OWASP excessive agency](https://owasp.org/www-project-top-10-for-large-language-model-applications/2_0_vulns/LLM06_ExcessiveAgency.html).

## Non-findings

Do not report personal naming taste, formatting handled by tools, line-count folklore, abstract future flexibility, demanded design patterns, blanket DRY, or coverage percentage without a concrete missed behavior.
