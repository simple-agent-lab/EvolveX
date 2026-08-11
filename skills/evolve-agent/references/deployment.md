# Prepare and deploy an experiment

Use this playbook only after source approval. Source approval authorizes the
reviewed catalog or recipe change; it does not authorize access to an account,
environment repair, workspace creation, model calls, or evaluation spend.
Deployment approval is a separate decision because initialization freezes a
lineage and may require side effects outside the source checkout.

## Confirm the approved source packet

Start with the source-approval event in the append-only external task record or
Git note keyed to the approved Git identity: the approved diff or commit,
frozen recipe rationale, selected recipe and operator, normalized
configuration, recipe-check output, focused-test evidence, and limitations. If
any source bytes or configuration values changed, return to source approval
before preparing a workspace. Do not append deployment evidence to the recipe
`README.md`; changing that approved file would invalidate the source identity.

Keep the Task 2 evaluation decision intact. Deployment uses the selected
existing evaluation assets and their approved target, partitions, evaluator,
and execution boundary; it is not an opportunity to weaken, replace, or
redesign the measurement contract to make an environment check pass.

## Gather current preflight evidence

For an uninitialized destination, `evolve preflight` is a read-only prospective
init checklist. It writes no receipt. It checks the recipe, seed, dataset,
declared runtime digest, required tools, task limit, and destination conditions
represented by the command; its stdout is not a generated receipt and does not
validate runtime availability or which authentication identity owns or can
access an external service.

Audit the command inputs before execution. Reject a seed, dataset, endpoint, or
other URL containing userinfo credentials or secret-bearing query parameters;
obtain a credential-free URL rather than passing or persisting the secret. Keep
credentials out of command arguments. Prospective preflight echoes Git seed
URLs verbatim, so use separately authorized out-of-band Git authentication
rather than embedding it in the URL.

Capture raw stdout and stderr only inside the disposable inspection boundary;
do not stream them to the host terminal, Agent context, user, or durable record.
Inside that boundary, pass the captured bytes through an allowlist scanner for
the expected checklist fields and redact recognized secret forms. Reject the
record rather than emit an unrecognized or unsafely redacted field. Emit only
the sanitized result, then destroy the isolated boundary and its raw capture.
If that scanner and containment are unavailable, stop; manual redaction after
display is not an acceptable fallback. The sanitized output is still manual
evidence, never a generated receipt.

## Bind the exact target seed

Identify the exact bytes initialization would vendor, not merely the path or
branch name:

- For a remote Git seed, record the credential-free canonical URL and a full
  immutable commit revision. A moving branch, tag, or default branch is not a
  deployment identity.
- For a local seed, review a deterministic manifest and digest of the exact
  vendored set. For a Git working tree, the manifest must account separately
  for tracked `HEAD` content, staged changes, unstaged changes, and untracked
  paths, with an explicit include or exclude decision for every path represented
  in each class. For a non-Git directory, record the corresponding sorted path,
  file-type, mode, and content-digest manifest plus exclusions.

Run secret detection over the exact included bytes, including included staged,
unstaged, and untracked content. Stop on a finding without copying the secret
value into evidence. Record only the approved manifest/digest, inclusion and
exclusion decisions, scanner identity, and sanitized result. Recompute this
identity immediately before initialization; any target snapshot change
invalidates prospective evidence and deployment approval.

Prospective preflight resolves selected named operators. Recheck their static
import safety, then run the checklist in the credential-free, allowlisted
[operator-inspection sandbox](operator-authoring.md). Supply only the inputs the
command represents: destination, exactly one of `--recipe` or `--recipe-path`,
optional `--seed`, `--dataset`, and `--tasks`, plus the declared
`EVOLVE_RUNTIME_DIGEST`. Use a verified pre-provisioned `evolve` executable or
`uv run --frozen --no-sync`; do not let inspection install or synchronize an
environment. If neither path is available, stop for a separately approved
remediation packet. Do not load deployment credentials.

In the append-only external task record or Git note keyed to the approved
source identity, retain the exact secret-free command, sanitized output,
independently computed source, recipe, operator, target-seed, evaluator,
dataset, and runtime identities or digests, and every assumption the checklist
did not verify. Record intended authentication identity, runtime availability,
image readiness, remote-service reachability, disk capacity, evaluator smoke,
and external-service access as unchecked deployment assumptions unless
independently verified. Call this a prospective preflight record, not a
mechanism-generated receipt.

Classify any failure before proposing a remedy:

- authoring or source evidence belongs back in the source-approval flow;
- environment readiness needs a bounded remediation proposal;
- evaluation-design concerns return to the architecture decision; and
- integrity failures require investigation, never a relaxed identity check.

If remediation changes a material decision recorded in the recipe rationale,
update `README.md`, rerun the applicable source checks, and obtain renewed
source approval before returning to deployment. Do not hide a source change in
the external deployment record.

Preflight evidence is current only for the exact inputs it checked. Re-run it
when a recipe, selected source, target-seed snapshot, evaluator, dataset,
runtime, credential mode, destination, or relevant digest changes.

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
recipe and operator configuration, exact target-seed revision or reviewed local
manifest/digest, target inclusion and exclusion decisions, sanitized
exact-content secret scan, evaluator and dataset identities, runtime and
authentication identities, recorded digests, current preflight result,
workspace destination, expected disk and runtime demand, initialization side
effects, and remaining unknowns.

Deployment approval authorizes one initialization with that exact packet. A
changed target snapshot, identity, digest, preflight input or result,
destination, runtime, credential mode, or source/configuration invalidates the
approval and requires a new packet and preflight. Append the approval to the
external task record or Git note keyed to the approved source identity; do not
edit the recipe rationale. Do not treat a general chat acknowledgement as an
open-ended deployment grant.

## Initialize and verify the frozen workspace

After deployment approval, recompute the exact target-seed identity and secret
scan, then run `evolve init` with the exact preflighted inputs only if they still
match the approved packet. Confirm that the resulting workspace has the
expected rendered configuration, component provenance and frozen digests,
generation-zero Git snapshot, readable status, and passing integrity
verification. A mismatch is a failed handoff: stop, preserve the evidence, and
return to the relevant approval or preflight boundary rather than repairing a
frozen workspace in place.

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
