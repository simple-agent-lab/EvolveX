# Evolve Your Agent README Design

## Goal

Make the repository README answer a new user's first practical question:
"How do I evolve an agent or harness I already have?"

The primary path starts with a built-in Codex or MiniSWE target. The advanced
path shows how the same model extends to a Harbor-compatible agent. A reader
should be able to identify the candidate files, runtime adapter, evaluator,
mutable surface, and launch command without reading framework source.

## Audience and success criteria

The primary reader is an agent researcher or engineer who has a Harbor task
dataset and either:

1. wants to begin with the built-in Codex target;
2. wants to evolve the bundled MiniSWE source target; or
3. has an installable Harbor `BaseAgent` adapter and candidate repository.

The README succeeds when this reader can:

- choose the appropriate starting path;
- explain the difference between target, Harbor agent, evaluator, and
  meta-agent;
- run one built-in example end to end;
- see exactly which files are allowed to evolve; and
- adapt a minimal custom recipe for their own Harbor-compatible agent.

## Information architecture

The README will use progressive disclosure:

1. **Project promise** — three concise sentences describing evaluator-driven
   evolution and the protected evidence boundary.
2. **Mental model** — a compact table defining four distinct roles:
   - target: candidate state under `target/`;
   - Harbor agent: runtime adapter that executes the candidate on a task;
   - evaluator: task dataset and verifier that produce trusted scores;
   - meta-agent: editing agent that proposes the next candidate.
3. **Choose a starting point** — a decision table for Codex, MiniSWE, and a
   custom Harbor agent.
4. **Prerequisites and installation** — Python, `uv`, Git, Harbor runtime,
   credentials, and immutable evaluator digest.
5. **Path A: built-in Codex target** — a copy-pasteable init/run/inspect flow
   using `aevolve --seed builtin-codex` and a local Harbor task dataset.
6. **Path B: MiniSWE source target** — a copy-pasteable flow using the recipe's
   pinned MiniSWE seed and a compatible task dataset.
7. **Path C: bring your own Harbor-compatible agent** — the integration
   contract, minimal target layout, adapter reference, custom recipe, locked
   dependency step, and run command.
8. **What happens during a generation** — select, execute, analyze, edit,
   evaluate, gate, and record, connected to retained artifacts.
9. **Reference** — recipes, trust boundaries, result inspection, limitations,
   and links to deeper design and contributor documentation.

Project-development details, exhaustive CLI listings, Mac-specific operational
notes, and milestone history will remain in dedicated documents rather than
interrupting the first-run path.

## Custom Harbor-agent contract

The README must state this contract explicitly:

- `evolve init --seed PATH_OR_GIT_URL` vendors the candidate repository into
  `target/`.
- The evaluator's `agent` is a Harbor `BaseAgent` implementation referenced as
  `package.module:ClassName`.
- The adapter must execute the candidate state from the current checkout's
  `target/`; otherwise evaluations would not measure the evolved candidate.
- The adapter package must be declared in the generated workspace's
  `pyproject.toml` and `uv.lock`. Import-path injection is unsupported.
- `surface.include` is the genome boundary. The introductory example keeps it
  at `target/**`; evolving operator logic is an explicitly advanced option.
- The evaluator and its verifier remain outside the mutable surface.
- `operators.meta_agent` names the editing strategy and runner; it is not the
  same component as the evaluated Harbor agent.

The example will use a small custom recipe directory passed with
`--recipe-path`, because changing a generated workspace after initialization
can make the setup order and frozen contracts harder to understand.

## Example requirements

Every main-path example must:

- use an absolute local dataset path;
- show where `EVOLVE_RUNTIME_DIGEST` comes into the workflow without pretending
  a placeholder digest is runnable;
- use the generated workspace's `./evolve` console after initialization;
- state required authentication without placing credentials in `target/`;
- include `./evolve status .`, `./evolve report .`, and the relevant retained
  artifact paths;
- describe the expected observable outcome rather than only listing commands;
  and
- distinguish a deterministic framework smoke test from a real mutation run.

Commands and configuration must be verified against the current CLI, recipes,
and tests. No example may imply that any arbitrary Harbor adapter automatically
knows how to load candidate state from `target/`.

## Scope

This change rewrites the user-facing repository README and may add one focused
guide or example recipe only if the custom integration cannot remain accurate
and readable inline. It does not change runtime behavior, recipe semantics,
evaluator boundaries, or CLI interfaces.

## Verification

Before completion:

1. check every command against `evolve --help` and current recipe configuration;
2. initialize the built-in examples in temporary directories where credentials
   and runtime availability permit;
3. run the deterministic smoke path for documentation-level validation;
4. verify every local Markdown link and referenced path;
5. scan the README for undefined terms before first use and stale claims; and
6. review the final diff specifically for accidental deletion of security,
   license, support, or limitation information.

Live model/Docker evaluation is not required to validate a documentation-only
change, but any unexecuted live command must be clearly labeled as such.
