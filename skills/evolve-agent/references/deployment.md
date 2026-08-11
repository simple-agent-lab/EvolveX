# Prepare and deploy an experiment

Use this playbook only after source approval. Source approval authorizes the
reviewed catalog or recipe change; it does not authorize access to an account,
environment repair, workspace creation, model calls, or evaluation spend.
Deployment approval is a separate decision because initialization freezes a
lineage and may require side effects outside the source checkout.

## Confirm the approved source packet

Start with the Task 3 source-approval record: the approved Git diff or commit,
selected recipe and operator, normalized configuration, recipe-check output,
focused-test evidence, and limitations. If any of those source bytes or
configuration values changed, return to source approval before preparing a
workspace.

Keep the Task 2 evaluation decision intact. Deployment uses the selected
existing evaluation assets and their approved target, partitions, evaluator,
and execution boundary; it is not an opportunity to weaken, replace, or
redesign the measurement contract to make an environment check pass.

## Gather current preflight evidence

Run `evolve preflight` using exactly the recipe, seed, dataset, evaluator
runtime, authentication mode, and destination intended for initialization.
Preflight writes nothing. Retain its receipt together with the current source,
recipe, evaluator, dataset, and runtime identities and their recorded digests.

Classify any failure before proposing a remedy:

- authoring or source evidence belongs back in the source-approval flow;
- environment readiness needs a bounded remediation proposal;
- evaluation-design concerns return to the architecture decision; and
- integrity failures require investigation, never a relaxed identity check.

Preflight evidence is current only for the exact inputs it checked. Re-run it
when a recipe, selected source, evaluator, dataset, runtime, credential mode,
destination, or relevant digest changes.

## Request authority for side effects

Do not infer authority from source approval or from a request to deploy. Before
an install, download, image build, credential access, or model probe, present a
separate remediation packet containing the exact command, affected location,
network access, credential identity and permitted account/scope, expected cost,
security consequences, and reversibility. Confirm that the approving user has
authority for the affected account, credential scope, resource, and spend, then
obtain their explicit authority for that action before performing it. Retain the
resulting preflight evidence.

Credential authority is not deployment approval: it names which identity may
be used, for what service and scope, and whether a model probe is allowed. Do
not place credentials in the recipe, workspace files, prompts, artifacts, or
approval record.

## Bind the deployment decision

Present a deployment packet that names the approved source identity, selected
recipe and operator configuration, evaluator and dataset identities, runtime
and authentication identities, recorded digests, current preflight result,
workspace destination, expected disk and runtime demand, initialization side
effects, and remaining unknowns.

Deployment approval authorizes one initialization with that exact packet. A
changed identity, digest, preflight input or result, destination, runtime,
credential mode, or source/configuration invalidates the approval and requires
a new packet and preflight. Record the approval with its bound identities; do
not treat a general chat acknowledgement as an open-ended deployment grant.

## Initialize and verify the frozen workspace

After deployment approval, run `evolve init` with the exact preflighted
inputs. Confirm that the resulting workspace has the expected rendered
configuration, component provenance and frozen digests, generation-zero Git
snapshot, readable status, and passing integrity verification. A mismatch is a
failed handoff: stop, preserve the evidence, and return to the relevant
approval or preflight boundary rather than repairing a frozen workspace in
place.

Initialization approval does not authorize candidate smoke, a model call, or
baseline certification. Before either a live model probe or generation-zero
baseline certification, obtain a separate spend decision that states the
budget, resource limits, evaluation scope, expected cost, and stop condition.

## Hand off to workspace operation

When initialization verification is complete, continue with
[the workspace contract](workspace-contract.md). It owns orientation, the
separately authorized baseline certification and control paths, recovery, and
reporting. Do not rewrite a frozen experiment to absorb a later evaluator,
recipe, or source change; start a new authoring and deployment flow for the new
workspace.
