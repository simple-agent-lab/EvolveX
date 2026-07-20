# Harbor Mounted Payload Transport

## Goal

Keep large agent inputs and outputs inside the disposable Docker-visible
workspace. Harbor process arguments and environment variables carry only short
paths and control values. This prevents operating-system argument limits from
depending on the method, benchmark size, or amount of retained evidence.

The immediate AHE failure is part of this scope. Its 242--245 KB meta-agent
instruction exceeds Linux's per-argument limit because Harbor's installed
MiniSWE adapter embeds the complete instruction in `--task`. HyperAgents uses
the same transport but has not failed because its current instructions are only
6--17 KB.

## Design

### Mounted-file payload contract

The disposable experiment workspace remains the medium for agent data. Before
starting an agent, the framework writes its instruction and referenced evidence
to stable paths beneath the current run. The Docker runner receives a short
container-visible instruction path, reads the file inside the container, and
passes its contents to the agent through the Python API. It never expands the
instruction into a shell command, CLI argument, or environment variable.

The same rule applies to future large payloads such as trace bundles, generated
configuration, trajectories, and structured agent results:

- payload content travels through files in the mounted workspace;
- process arguments contain paths and small control flags only;
- agent outputs are written to run-scoped files before Harbor collects the
  disposable workspace artifact;
- the existing surface gate remains the only path by which model edits become
  persistent candidate changes.

The launcher is shared by AHE, HyperAgents, and read-only debugger calls. Method
operators continue to build their own prompts and do not implement transport.

### AHE evidence deduplication

File transport removes the crash but does not justify sending redundant model
context. AHE's selected evidence currently repeats each normalized bounded case
inside the task detail Markdown even though the same cases are already stored
in `trace_analyzer/evidence/cases.jsonl` and run-scoped detail artifacts.

The AHE meta-agent instruction will inline:

- the debugger overview;
- each task's LLM diagnosis;
- concise failing-verifier evidence;
- change attribution, recent archive outcomes, surface rules, and the required
  change-manifest contract.

It will link to container-visible detail and case files for drill-down instead
of inlining bounded cases. No evidence is deleted, clipped, or made inaccessible
to the agent. HyperAgents keeps its existing evidence-selection behavior.

### Secrets and control values

Credentials are not experiment payloads. API keys, authentication material,
and private proxy credentials remain injected through Harbor's controlled
secret or environment mechanism and must not be written into the returned
workspace.

Small values such as the model identifier, timeout, retry count, role, and file
paths may remain arguments or environment variables. Payload-sized text may
not.

### Size diagnostics

The shared Harbor runner measures the serialized instruction before launch and
records its byte size. A conservative diagnostic threshold detects accidental
regressions before entering Harbor. Crossing that threshold is not a reason to
clip or reject a valid file-backed instruction; it verifies that the selected
launcher is file-backed and otherwise fails with a specific
`harbor_instruction_transport_unsafe` error.

This replaces the opaque downstream `OSError: [Errno 7] Argument list too long`
with a framework-owned invariant.

## Data Flow

1. The trace analyzer writes summaries and detailed evidence beneath the
   current generation directory.
2. The meta-agent operator builds `meta_agent/prompt.md`, using
   container-visible paths for detailed evidence.
3. The Harbor runner assembles the disposable full workspace and starts a
   shared file-backed launcher with the prompt path.
4. The launcher reads the prompt inside Docker, runs MiniSWE through its Python
   API, and writes the trajectory and textual log to run-scoped paths.
5. Harbor returns the complete disposable workspace.
6. The host compares the returned tree with its trusted pre-run state and
   imports only surface-approved editable roots.

## Failure Handling

- A missing or unreadable instruction file fails before the model call with the
  phase and expected path.
- A launcher that would embed an oversized instruction fails the transport
  invariant before Docker execution.
- Agent, model, timeout, and output parsing failures retain their existing
  ownership and retry behavior.
- Operator failure records remain valid without a `gate.json`; record handling
  must not replace the primary failure with a missing-gate exception.
- Returned runtime files, prompt files, evidence edits, and credentials never
  bypass the surface gate.

## Implementation Sequence

1. Remove bounded-case duplication from AHE's selected meta-agent context while
   preserving container-visible detail paths.
2. Add the shared file-backed instruction launcher and route all Harbor agent
   roles through it.
3. Add the transport-size invariant and explicit diagnostics.
4. Make operator-failure recording tolerate the absence of `gate.json`.
5. Run one AHE generation, then concurrent AHE and HyperAgents smoke runs before
   resuming the full experiment.

The first step can unblock the immediate smoke independently. The second and
third steps establish the long-term framework contract.

## Tests

Tests cover:

1. AHE selected context omits bounded-case bodies but exposes their mounted
   paths and retains all evidence files;
2. a prompt larger than Linux's per-argument limit reaches a fake MiniSWE Python
   API unchanged through the file-backed launcher;
3. no launcher command or environment value contains the large prompt body;
4. AHE, HyperAgents, and debugger roles use the same transport;
5. prompt byte size and unsafe-transport failures are recorded clearly;
6. credentials are absent from workspace payload files and returned artifacts;
7. operator failure can be recorded without `gate.json` while preserving the
   original failure;
8. existing surface checks, artifact collection, retries, and candidate import
   remain unchanged;
9. a DevBoxS AHE smoke produces a real meta-agent trajectory and candidate, and
   a concurrent HyperAgents smoke remains successful.

## Non-Goals

- Rewriting Harbor's Docker environment or the experiment driver.
- Changing AHE or HyperAgents search policy, budgets, models, or benchmark
  tasks.
- Silently clipping prompts or evidence.
- Moving credentials into the experiment workspace.
- Relaxing the surface gate or persisting runtime-evidence edits.
