# Prepare and deploy an experiment

Use this playbook only after source approval. Source approval authorizes the
reviewed catalog or recipe change; it does not authorize access to an account,
environment repair, workspace creation, model calls, or evaluation spend.
Deployment approval is a separate decision because initialization freezes a
lineage and may require side effects outside the source checkout.

## Confirm the approved source packet

Start with the authoritative immutable or append-only hash-chained
source-approval event. Validate its approver identity, timestamp/event id,
predecessor hash, clean source commit or complete source-tree manifest/digest,
packet digest, and target digest bound to any target/surface evidence. A source
manifest must name its base and cover staged, unstaged, untracked, ignored, and
excluded paths. Validate the chain to its external immutable anchor. An ordinary
Git note is only a convenience mirror or pointer unless externally anchored; it
is not approval authority by itself.

The approved packet also contains the frozen recipe rationale, selected recipe
and operator, normalized configuration, narrowly scoped recipe-check output,
separate source checks, focused-test evidence, and limitations. If source bytes,
configuration, packet content, or target bytes/layout bound to source evidence
changed, return to source approval before deployment. Reopen architecture too
when target semantics changed. Do not append deployment evidence to the recipe
`README.md`; that would change the approved source identity.

Keep the Task 2 evaluation decision intact. Deployment uses the selected
existing evaluation assets and their approved target, partitions, evaluator,
and execution boundary; it is not an opportunity to weaken, replace, or
redesign the measurement contract to make an environment check pass.

## Gather current preflight evidence

For an uninitialized destination, the `evolve preflight` CLI contract is a
prospective init checklist and writes no destination receipt. Executing its
process and selected operator imports is not inherently non-mutating; only the
trusted boundary below may constrain side effects. The checklist covers the
recipe, seed, dataset, declared runtime digest, required tools, task limit, and
destination conditions represented by the command. Its stdout is not a receipt
and does not validate runtime availability or which authentication identity
owns or can access an external service.

Audit the command inputs before execution. Reject a seed, dataset, endpoint, or
other URL containing userinfo credentials or secret-bearing query parameters;
obtain a credential-free URL rather than passing or persisting the secret. Keep
credentials out of command arguments. Prospective preflight echoes Git seed
URLs verbatim, so use separately authorized out-of-band Git authentication
rather than embedding it in the URL.

This repository supplies no trusted containment launcher or preflight-output
sanitizer. Guided preflight therefore stops by default. It may proceed only
after a separate remediation decision supplies a verified, pre-provisioned
trusted containment launcher and allowlist sanitizer with recorded executable
identity, version or digest, and exact accepted-output schema. The Agent must
not improvise either tool or treat prose describing one as executable proof.

When those named tools exist, capture raw stdout and stderr only inside their
disposable boundary; never stream them to the host terminal, Agent context,
user, or durable record. The named sanitizer must reject fields outside its
approved schema, redact only recognized secret forms, and emit sanitized
content. Destroy the raw capture with the boundary. Manual redaction after
display is not a fallback. The sanitized output remains manual evidence, never
a generated receipt.

## Bind the exact target seed

Identify the exact vendoring closure initialization will consume, not merely a
path, Git status, or branch name:

- **Remote Git:** The source-approved recipe itself must contain the
  credential-free canonical `target.seed` URL and full 40-character immutable
  `target.revision`. Never pass a remote Git URL through `--seed`: that override
  removes the recipe revision. Record the revision's tree digest and expected
  vendored manifest.
- **Local directory:** Walk the actual filesystem with the framework's copy
  exclusions and symlink semantics. The deterministic manifest records every
  included and excluded path; its Git classification when applicable (tracked
  `HEAD`, staged, unstaged, untracked, or Git-ignored); file type; mode; content
  digest; and symlink text target plus resolved containment result. Reject an
  absolute, escaping, cyclic, broken, or otherwise unsafe symlink. Git status
  alone is not a vendoring inventory.
- **Built-in resource:** Recursively enumerate the exact packaged resource tree
  the recipe names and compute a deterministic digest over sorted relative
  path, file type, mode when represented, and content digest. Record the package
  artifact identity and exclusion semantics with that resource-tree digest.

Run secret detection over every included regular-file byte in that exact
closure, including included ignored content. Stop on a finding without copying
the secret into evidence. Record only the manifest/digest, inclusion and
exclusion decisions, framework copy-semantics identity, scanner identity, and
sanitized result.

For a local seed, eliminate the review-to-copy race. After separate authority
for preparation, use a trusted snapshot facility to materialize the approved
vendoring closure as a content-addressed, read-only immutable local snapshot.
Verify its manifest/digest, bind deployment approval to it, and use only that
snapshot path as the local `--seed`. If the available filesystem or framework
cannot consume and enforce that safe snapshot, stop; recomputing a mutable path
immediately before `init` is not atomic and is not an acceptable substitute.

Prospective preflight resolves selected named operators. Recheck static import
safety, materialize the exact reviewed source in the named trusted containment
launcher as read-only, and invoke the verified direct `evolve` executable from
an already-existing pre-provisioned environment. Verify its recipe and catalog
roots resolve to that read-only source identity. Redirect all permitted writes
and caches to disposable storage; remain offline, load no environment file,
and do not execute from the writable source checkout. If any prerequisite is
absent, stop for separate remediation rather than create `.venv`, synchronize,
download, or provision anything.

Supply only the inputs represented by the command: destination, exactly one of
`--recipe` or `--recipe-path`, optional **local immutable** `--seed`, dataset,
task limit, and declared `EVOLVE_RUNTIME_DIGEST`. For remote Git or built-in
targets, omit `--seed` so the source-approved recipe identity remains intact.
Do not load deployment credentials.

Append a hash-chained preflight event to the authoritative external record. It
retains the exact secret-free command, sanitized output, containment and
sanitizer identities/schema, independently computed source, packet, recipe,
operator, target snapshot, evaluator, dataset, and runtime identities, and
every unchecked assumption. Record intended authentication identity, runtime
availability, image readiness, remote-service reachability, disk capacity,
evaluator smoke, and external-service access as unchecked unless independently
verified. Call this a prospective preflight record, not a mechanism-generated
receipt.

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
when a recipe, selected source or packet, target snapshot, evaluator, dataset,
runtime, credential mode, destination, or relevant digest changes. A target
change also invalidates target-digest-bound source evidence and source approval;
rerun architecture approval when the target change is semantic.

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
packet digest, recipe and operator configuration, exact remote recipe revision,
local immutable snapshot identity, or built-in resource-tree digest as
applicable; expected post-copy target manifest; inclusion and exclusion
decisions; sanitized exact-content secret scan; evaluator and dataset
identities; runtime and authentication identities; recorded digests; current
preflight result; workspace destination; expected disk and runtime demand;
initialization side effects; and remaining unknowns.

Deployment approval authorizes one initialization with that exact packet. A
changed target snapshot, identity, digest, preflight input or result,
destination, runtime, credential mode, or source/configuration invalidates the
approval and requires a new packet and preflight. Append the approval to the
authoritative external hash chain with approver identity, timestamp/event id,
predecessor, source and packet identities, and every deployment binding. Do not
edit the recipe rationale or treat a general chat acknowledgement or ordinary
unanchored Git note as an open-ended deployment grant.

## Initialize and verify the frozen workspace

After deployment approval, initialize a remote target only from the
source-approved recipe-pinned URL/revision, a local target only from the
approved content-addressed read-only snapshot, or a built-in target only after
revalidating its approved resource-tree digest. Run the verified direct
`evolve init` with the exact preflighted inputs. Do not use a mutable local path
or a remote `--seed` override.

Before accepting generation zero, independently manifest the copied
`target/` using the same file, mode, symlink, exclusion, and deterministic
framework-metadata rules and require exact equality with the approved expected
post-copy manifest. For remote Git, also verify frozen provenance records the
exact recipe revision and that the copied tree matches it. For built-in
resources, verify the copied tree derives from the revalidated resource digest.
Confirm rendered configuration, component provenance and frozen digests,
generation-zero Git snapshot, readable status, and passing integrity
verification. A mismatch is a failed handoff: stop, preserve evidence, and
return to the relevant approval or preflight boundary rather than repair a
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
