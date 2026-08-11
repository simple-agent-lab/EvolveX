# Design an evolution experiment

Use this playbook before writing a recipe, operator, evaluator asset, or workspace. Read `decision-protocol.md` first. Ask one focused question at a time; prefer choices only after enough evidence exists to explain them.

## Classify the starting context

- In an initialized workspace, stop source authoring and use `workspace-contract.md`.
- In an EvolveX source checkout, keep authoring on an isolated branch or worktree and preserve unrelated changes.
- In an external target project, treat it as the candidate and locate a writable EvolveX source checkout. Do not clone or modify an installed package without approval.
- If evidence is insufficient, ask for the target or checkout location rather than guessing.

State the evidence for the classification.

## Establish the experiment brief

Name the target, exact seed identity, mutable surface, protected paths, desired behavior, observed failures, frozen evaluator, optimization/gate/sealed partitions, candidate budget, concurrency, timeouts, cost boundary, execution boundary, credentials mode, baseline requirement, and evidence required for acceptance and claims.

During design, write confirmed choices, assumptions, and limitations into the
current task record. After architecture approval selects a custom recipe,
materialize that record into the recipe `README.md`; do not create source merely
to hold a pre-approval decision. Never encode credentials in either record.

## Design evaluation before optimization

Qualify existing evaluation assets before selecting a method or reading method
cards. Record:

- **Coverage:** which required behaviors, known failures, edge cases, and
  optimization, gate, and sealed partitions are measured or missing.
- **Scoring semantics:** score direction; domain, range, and units; aggregation
  and weighting; handling of missing, invalid, timed-out, or failed cases;
  thresholds; tie behavior; and the exact acceptance or non-regression rule.
- **Determinism:** whether repeated runs of the same candidate under the same
  runtime reproduce inputs and outcomes, plus every known nondeterministic
  component and tolerance.
- **Leakage:** what candidate or mutation code can observe, whether protected
  labels, verifier outputs, gate data, or sealed data can influence mutation,
  and how disjoint identities are enforced.
- **Runtime compatibility:** whether the evaluator, task assets, adapters, and
  dependencies can execute against the target in the approved isolation and
  resource boundary.
- **Calibration:** results for at least one known-positive and one
  known-negative candidate, including whether each passes, fails, and
  discriminates for the intended reasons.
- **Limitations:** unmeasured behavior, uncertainty, flaky or subjective
  components, environmental assumptions, and known incentive gaps.
- **Supported claims:** the narrow conclusions justified by the covered
  partitions and calibration evidence, and the claims the evaluator cannot
  support.

An evaluator is qualified only when these facts are sufficient for the
experiment's acceptance rule and intended claims. If qualification fails, stop
method selection. Gather missing evidence, repair the existing evaluation, or
route to Harbor-compatible evaluation authoring when isolated tasks can express
the requirement. Route to evaluator-engine authoring only when a named
execution or scoring requirement cannot fit Harbor. Do not optimize against an
unqualified ruler.

Prefer existing or model-free calibration evidence. If qualification requires
a live evaluator, external service, credential, or material budget, present a
separate bounded calibration packet with its exact candidate controls, command,
credential scope, budget, retained evidence, and stop condition. Run it only
with explicit authority. This calibration authority does not approve source or
deployment. Without safe existing evidence or that authority, qualification
remains incomplete and method selection stops.

After qualification, present a decision packet with these choices when
relevant:

1. Configure existing evaluation assets.
2. Author a Harbor-compatible evaluation when isolated tasks can express the desired behavior.
3. Develop a new evaluator engine only when a named execution or scoring requirement does not fit Harbor, or the user selects it after reviewing its larger trusted-framework cost.

This delivery implements option 1 only when the existing evaluation qualifies.
For option 2, stop after the approved evaluation design and route to the Harbor
evaluation-authoring project. For option 3, stop after the decision and require
a separate evaluator-engine design and threat review. Do not initialize an
experiment with an unvalidated measurement contract.

Use `scientific-foundations.md` when evaluator semantics, partitions, acceptance rules, or claims are being defined or changed.

## Compare composition options

Read only the method cards supported by the available evidence. Present the nearest supported recipe, a code-free custom composition when needed, and deferral when the evaluator or target contract is incomplete. Explain the evidence each method consumes, the paths it may change, and the claims it can support.

Inspect the live operator catalog before claiming that custom source is needed.
Filesystem-only listing may run during design through a verified
pre-provisioned executable or `uv run --frozen --no-sync`; if neither is
available, stop for separately approved environment remediation. Before
`operator describe`, use the static review and credential-free isolation
procedure in [operator authoring](operator-authoring.md); inspection is
evidence gathering, not authority to scaffold or edit source. Do not use file
presence in an initialized workspace as the source catalog.

## Record the architecture decision

Before source work, present architecture approval bound to the target,
evaluation identity and scoring semantics, partitions, recipe composition,
proposed custom operator gaps, mutable surface, runtime, budget, risks,
unknowns, and task-record rationale. If approved, preserve that rationale in
the custom recipe `README.md` created during source authoring.

Do not initialize, build external assets, or implement source before the user
approves this exact architecture. Do not call models except for a separately
authorized bounded calibration probe described above. A changed measurement
contract returns the workflow to evaluation design.
