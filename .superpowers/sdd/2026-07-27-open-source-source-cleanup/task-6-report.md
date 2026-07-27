# Task 6 report: public community files

## RED

Command:

```bash
uv run pytest -q tests/test_public_repository.py
```

Result: `1 passed, 4 failed`. The expected failures identified the missing
`SECURITY.md`, `CODE_OF_CONDUCT.md`, and `SUPPORT.md` files and the missing
`.github/ISSUE_TEMPLATE` issue forms and configuration.

## GREEN

Command:

```bash
uv run pytest -q tests/test_public_repository.py
```

Result: `5 passed in 8.61s`.

## Full verification

Commands:

```bash
uv run pytest -q
uv run ruff check .
uv run python -c '<YAML parse and issue-form semantic assertions>'
git diff --check
```

Results: the full test suite completed successfully; Ruff reported `All checks
passed!`; YAML forms parsed and satisfied the required ordered IDs and security
configuration contract; and `git diff --check` reported no whitespace errors.

## Self-review

- `SECURITY.md` limits support to the latest `main` revision before 1.0,
  requires GitHub private vulnerability reporting, states three- and
  seven-business-day response targets, and commits to coordinated disclosure.
- `CODE_OF_CONDUCT.md` is Contributor Covenant 2.1 with repository maintainers
  as enforcement owners and the same private reporting route as `SECURITY.md`.
- `SUPPORT.md`, the issue configuration, and the README make public issue and
  private-report boundaries explicit.
- The forms preserve the required IDs, order, and validations; logs remain
  optional and include redaction guidance.
- The README links every policy, and the relative-link test covers each new
  Markdown file without asserting human-facing prose.

## Concerns

None. The shared private-reporting endpoint for conduct and security is
intentional and required by this task.
